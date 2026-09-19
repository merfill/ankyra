# Technical Specification — Ankyra: Hybrid Neuro-Symbolic Reasoning Engine

## 1. Purpose and Scope

Ankyra is a domain-general hybrid neuro-symbolic reasoning engine. Given a
natural-language problem that contains a set of conditions and a question, it
produces a step-by-step, mechanically verifiable reasoning trace and an answer,
together with the logical status of that answer.

Design commitment: **the LLM proposes, the symbolic engine decides.** The LLM
never owns truth. It may propose freely, but every proposal is deterministically
classified as one of:

| category | condition | engine action |
|---|---|---|
| `derivable` | already entailed by the current theory | accept as narration only |
| `cited` | a new fact grounded by a verbatim quote from the text | add to axioms |
| `hypothesis` | new knowledge not present in the text | record in the hypothesis ledger, tag `H` |
| `rejected` | fails schema, safety, or quote validation | drop with a reason code |

In scope: deduction to a fixed point, unification with variables, contradiction
detection, subsumption via `is_a`, answering with explicit hypothesis accounting,
and explanation built mechanically from proof provenance.

Out of scope: retrieval over an external corpus or fragment store — Ankyra is not
a retrieval system and has no fragments; the input is a single self-contained
problem. Also out of scope for v0: numeric/statistical scoring, and arithmetic
beyond the deferred builtin layer (see Open Decisions, D1).

## 2. Formal Problem Statement

**Input.** A problem in natural language containing conditions (facts,
constraints, "if … then …" rules) and a question.

**Output.**
- A step-by-step reasoning trace.
- The final answer, or an honest statement that the answer is not derivable.
- The status of the answer and, when applicable, the hypotheses it depends on.

**Answer types.**
- `yes_no` — the target `phi` is a closed goal.
- `open` — the target `phi` contains variables `?x` to be bound.
- `instruction` — there is no target (`phi = null`); the query is a set of
  conditions to be checked.

**Status.** `supported | insufficient | unsupported | refuted`, plus the process
states `no_progress | budget`.

**Guarantees.**
- Soundness is guaranteed **relative to the formalization and the explicit
  hypothesis ledger**. A `proven` answer uses no hypotheses; an answer that
  depends on hypotheses is always reported as `proven_under(H)`.
- Completeness of deduction is guaranteed by the engine (forward chaining to a
  fixed point). Completeness of the formalization is not claimed.

## 3. Design Principles and Invariants

1. **No LLM-owned facts.** Nothing enters the theory without either a valid quote
   (`cited`) or an explicit hypothesis tag (`hypothesis`). The legacy "add
   predicates" loop is rejected outright.
2. **Monotonicity (enabled now, policy-switchable later).** The *theory* only
   grows: axioms are added, hypotheses are added to the ledger, the target is
   never weakened, no premise is deleted. Monotonicity constrains the base, not
   the answer: under defeasible semantics a new fact can shift the answer, which
   is recorded as a `Revision` (see §4 and §8). Strict deduction stays monotone
   in the answer as well.
3. **Freedom in proposal, determinism in classification.** The LLM may name
   predicates and propose rules freely; the classification of a proposal is
   always deterministic.
4. **Separate theory from question.** Phase 0 emits them as distinct artifacts;
   the question is never asserted as a fact.
5. **Every step is verifiable.** An explanation step corresponds to a real
   derivation edge in the provenance graph, or to an identified hypothesis.
6. **Answer strength is explicit.** `proven`, `proven_under(H)`, or `not_proven`.
7. **Grounded refutation; the question is never a source.** A refutation must rest
   on grounded facts, not on a hypothesis: assuming `P` does not establish that
   `¬P` is false, so a hypothetical counter-proof reports `unknown`, not a definite
   "no". Likewise a quote drawn from the interrogative span cannot license an
   axiom, a quote that occurs only inside a conditional cannot assert a fact, and a
   non-cited fact hypothesis may not assert the closed target — so the goal can
   never be proved by citing or assuming the goal itself, nor by treating a
   conditional premise as an asserted fact.
8. **Deterministic code never parses natural language.** Normalizing identifiers and
   closed enum fields the LLM has *already extracted* — predicate/object ids,
   `modality`, `relation_kind`, `predication`, slot keys — is allowed: it operates on
   structured output, not on the source. Any heuristic over the raw `source_text` or
   `question` that keys on words, morphology, cue phrases, or a hand-written term
   list is forbidden (a "syntactic analyzer"): semantics belong to the extraction
   prompt and the symbolic engine, and term-level rules do not generalize across
   domains. The only legitimate operations on raw text are structural witness checks
   — a quote's verbatim substring/span, coverage, and length.

## 4. Data Model

All models are Pydantic.

- `Object` — a canonical vertex: `id` (lower snake/camel as chosen by convention).
- `Morphism` — an arrow: `predicate`, `subject`, `object`, `modality`, `quote`,
  `negated`. Negation is the same predicate with `negated = true`; there is no
  separate negative name. Modality is a typed field, not encoded in the predicate
  name.
- `Rule` — a Horn clause: `conditions: list[Morphism]` (AND) → `consequence:
  Morphism`. `kind ∈ {implication, exception}`; `source ∈ {quote, hypothesis:<id>}`.
- `Theory` — `objects`, `morphisms` (asserted axioms), `rules`, `domain`.
- `Query` — `conditions` (Gamma), `target` (phi, may contain `?x`), `variables`,
  `answer_type`.
- `Fact` (engine-internal) — a ground atom plus provenance: `used: frozenset`,
  `witness: str`, `rule_index: int | None`, `axiom: bool`.
- `Hypothesis` — `id`, `kind ∈ {rule, fact}`, `payload`, `wave`, `rationale`.
- `Verdict` — `status`, `bindings`, `gaps`, `matched`, `shelf`.
- `WaveRecord` — `wave`, `proposal`, `category`, `reason`, `verdict_after`.
- `Answer` — `value`, `strength ∈ {proven, proven_under, not_proven}`,
  `hypotheses_used`.
- `Revision` — an auditable answer change across waves: `wave`,
  `trigger ∈ {new_cited_fact, new_hypothesis, answer_change}`, `previous`,
  `current`, `source_ids` (the hypotheses accepted in the triggering wave).

Structure-extraction models (what the LLM actually authors; the ontology itself
is assembled deterministically):

- `Slot` — a role filler: `id` | `set` (AND) | `variants` (OR) | `exclude`.
- `StructAtom` — `predicate` (no modality prefix), `subject: Slot`, `object: Slot`,
  `relation_kind ∈ {ascription, possession, action}` (legacy `predication`
  `copula|verb` still accepted and mapped), `modality ∈ {permit, obligation,
  forbidden, neutral}`, `negated`, `quote`. `ascription` means the subject has a
  property/class (predicative "is/are" AND attributive modifiers); the builder emits
  `is_a(subject, property)` consistently in facts and rule atoms. `possession`
  ("X has an engine") stays a binary predicate and is never `is_a`; `action` is any
  other verb/relation.
- `StructRule` — `antecedent: list[StructAtom]`, `consequent: StructAtom`,
  `kind ∈ {implication, exception}`, `forall` (variable → universe sort; the
  quantifier's domain, recorded instead of an `is_a(?x,sort)` premise), `quote`.
- `ProblemStructure` — `objects`, `facts`, `rules`, `variants`, `references`,
  `domain` (legacy global form of `forall`; membership is vacuous).
- `QuestionStructure` — `facts`, `ask` (single target, may be null), `rules`,
  `variables`.

## 5. Phase 0 — Problem Decomposition

### 0.1 Identify the question
Separate the descriptive part from the interrogative part and decide the
`answer_type`. This boundary is explicit; the question is handled as its own
artifact from here on.

### 0.2 Extract the problem structure (LLM, one call)
`extract_problem_structure(text) -> ProblemStructure`. The LLM performs a
*structural* decomposition only: objects, facts, rules ("if … then …"),
enumerations ("and"), alternatives ("or"), exclusions, modalities, negations, and
quotes. It does **not** author finished triples or Horn clauses; the combinatorics
are left to the deterministic builder. Every fact/rule carries a minimal verbatim
quote.

### 0.3 Build the theory (deterministic)
- `unroll` — expand `Slot` sets/variants/exclusions into morphisms by
  subject × object; a `copula` one-place atom becomes `is_a(subject, complement)`
  (a `verb` one stays a unary atom); carry `modality` as a typed field (it is NOT
  baked into the predicate name); optionally lower modality to prefixes
  (`obligation → must_`, `forbidden → must_not_`, `permit → may_`) when
  `ANKYRA_DEONTIC_PREFIXES` is on; assemble `Rule`s (`exception` flips the
  consequence's `negated`); drop a rule premise `is_a(?x, sort)` that is exactly the
  rule's `forall` sort (the quantifier's domain, not a premise) — unless it is the
  variable's only binder, which would leave the rule unsafe. No LLM.
- `enrich` — canonicalize polarity (`isNot → is_a + negated`), dedupe, drop a rule
  premise restricted to the legacy global `domain` sort, materialize trivia, heal
  contradictions and dangling ends. No LLM.
- `symbolic_check` — verify that every quote is a real substring of the source,
  that names are canonical, and that the structure is well-formed. No LLM.
- When multiple samples are extracted, pick the best by a deterministic score:
  quote coverage of the source → fewer gaps → compactness (fewer morphisms/rules).

### 0.4 Extract the question structure (LLM, one call)
`extract_question_structure(question, theory) -> QuestionStructure`. The theory
vocabulary is embedded in the prompt so the LLM expresses the question over the
theory's predicates and objects. The `ask` (target) is the question's own
conclusion: a variable `?x` for genuinely open unknowns (what/which/who), a
constant otherwise, and `null` for instructions. If the question cannot be
expressed in the theory vocabulary, it is kept verbatim so verification can
honestly report `target_unmatched`.

### 0.5 Build the query (deterministic)
`unroll_query` — `facts → conditions` (Gamma), `ask → target` (phi); then
`settle` — ground terms onto theory ids, drop a goal echo, normalize polarity,
and slim unused premises (re-verifying after each drop). No LLM.

## 6. Phase 1 — The Deterministic Engine (the spine)

- `saturate(theory ∪ Gamma)` — semi-naive forward chaining to a fixed point over
  a finite universe, terminating on no progress. Every derived fact carries
  provenance (`used`, `witness`, `rule_index`).
- `unify` / `match_goal` — unification with variables; `match_goal` returns all
  goal hits with their substitutions and provenance.
- `complementary` — detect `P` and `¬P` on the same triple.
- `is_a` — transitive closure of positive `is_a` edges.
- `verify(theory ∪ Gamma ⊢ phi)`:
  - any complementary pair → `refuted`;
  - target matched and all premises used → `supported`;
  - target matched but some premises unused → `insufficient`;
  - nothing matched → `unsupported`.
  Structured gaps use codes: `target_unmatched:`, `condition_unmatched:`,
  `unused_premise:`, `contradiction:`.
- **Hypothetical refutation (policy).** When the refuting branch rests on a
  hypothesis, the cycle reports `unsupported` with a `hypothetical_refutation:`
  gap instead of `refuted` (see §3.7); the answer is the honest `unknown`.
- **Builtins:** v0 ships with none. Comparison predicates are an explicit,
  deferred extension (see D1); the interface exposes a single
  `evaluate(builtin_atom, subst)` hook.

This layer is sound and complete relative to the formalization, and is never
allowed to add knowledge.

## 7. Phase 2 — Guided Reasoning Cycle

The inner loop is deterministic. The outer loop alternates a hint, a free LLM
proposal, and a deterministic classification.

**Wave steps.**
1. `verify(state)` → verdict + structured gaps.
2. Terminal check: stop on `supported` / `refuted` / `no_progress` / budget.
3. Assemble the hint for the LLM: the problem structure, the theory vocabulary
   (allowed predicates and objects), a summary of the derived frontier, the gaps,
   the target, the allowed proposal actions, and the grounding rules.
4. LLM free reasoning → a natural-language narration **plus one typed proposal**:
   - `reformalize_query` — express Gamma/phi in the theory vocabulary;
   - `propose_rule` — a new rule (cited, or a tagged hypothesis);
   - `assert_cited_fact` — a new axiom backed by a valid quote;
   - `select_subgoal` — choose the next goal for the engine to pursue.
5. Deterministic classification and validation of the proposal: schema check,
   safety/range-restriction check, quote validation; assign
   `derivable | cited | hypothesis | rejected` and apply or drop it.
6. Record a `WaveRecord`; re-run the inner loop.

**Hypothesis ledger.** Every `hypothesis` is stored with an id, kind, payload,
wave, and rationale. The answer reports which hypotheses were used.

**Stop conditions.** `supported`, `refuted`, `no_progress` (the proposal is
identical to the previous one), budget exhausted (`max_waves`), or no reachable
hypothesis (honest `fragment_gap`/`unsupported`).

**Freedom ramp (policy).** Wave 0 may be permissive (free naming, hypotheses
allowed and tagged); later waves can constrain the vocabulary and optionally
forbid hypotheses (`ANKYRA_ALLOW_HYPOTHESES=false`).

## 8. Phase 3 — Explanation

The reasoning trace is built **mechanically** from provenance: starting from the
winning goal binding, walk the `used` facts and `rule_index` edges of the proof
to produce an ordered list of steps, each naming the rule, the bindings, and the
quote or hypothesis that licenses it. The LLM may only paraphrase this finished
derivation; it may not introduce facts. When the answer changes between waves,
the explanation carries the `Revision` events in wave order, so non-monotonic
answer movement is visible in the trace rather than hidden. Resolved and
undecided defeasible conflicts also name the hypotheses behind the competing
branches (`Conflict.source_ids`), i.e. which assumption introduced the `is_a`
edge that decided specificity.

## 9. Orchestration (LangGraph)

A single `StateGraph` over a Pydantic/TypedDict state with reducers for the
append-only `history` and `hypotheses`.

Nodes: `identify_question` → `extract_problem_structure` → `build_theory` →
`extract_question_structure` → `build_query` → `verify` →
(`propose` → `classify` → `verify`)* → `explain`.

State (fields): `problem_text`, `theory`, `query`, `hypotheses`, `closed_facts`,
`verdict`, `wave`, `max_waves`, `history`, `status`, `answer`.

Conditional edges: after `verify`, route to `explain` when terminal, otherwise to
`propose`; after `classify`, loop back to `verify`. Routing functions are pure;
status is committed by the node, never mutated inside an edge.

## 10. Configuration

Dynaconf, prefix `ANKYRA` (see `src/ankyra/config/settings.py`).

Existing: `ANKYRA_API_URL`, `ANKYRA_API_KEY`, `ANKYRA_MODEL`, `ANKYRA_TEMPERATURE`,
`ANKYRA_MAX_TOKENS`, `ANKYRA_MAX_TOKENS_EXTRACT`, `ANKYRA_EXTRA_BODY`,
`ANKYRA_REASONING_EFFORT`.

New: `ANKYRA_MAX_WAVES`, `ANKYRA_ALLOW_HYPOTHESES` (default `true`),
`ANKYRA_DEONTIC_PREFIXES`, `ANKYRA_EXTRACT_SAMPLES` (default `1`),
`ANKYRA_EXTRACT_REPAIRS` (default `0`), `ANKYRA_BUILTINS` (default `false`),
`ANKYRA_LIVE`.

## 11. Worked Examples (acceptance tests)

### Example A — rain (pure deduction, 1 wave, no hypotheses)
- Phase 0: theory = `{raining()}` with rule `R1: raining() => isWet(ground)`;
  question `phi = isWet(ground)`, type `yes_no`, `Gamma = {}`.
- Wave 0 (deterministic only): `saturate` fires `R1`; `verify` → `supported`.
- Expected: "yes", explanation from provenance, no LLM call in the loop.

### Example B — vehicle (abduction, N waves, hypotheses)
- Phase 0: theory = facts `hasEngine(X)`, `wheelCount(X,4)`, `power(X,150)`,
  `doorCount(X,4)`; **no rules** — the class rules are not present in the text.
  Question `phi = is_a(X, ?c)`, type `open`.
- Wave 0: closure yields nothing for `phi`; `verify` → `target_unmatched: is_a`.
- LLM proposes the class rules and the class hierarchy; they carry no text quote,
  so they are classified `hypothesis` (`H1`, `H2`, `H3`, `Hh`).
- Re-close: `is_a(X, motorVehicle)`, `is_a(X, car)`, `is_a(X, sedan)`, plus
  transitive `is_a`. `match_goal(is_a(X, ?c))` binds `?c`; "most specific" is now
  **defined** by the `is_a` chain, not guessed.
- Expected: "X is a sedan, **under** H1, H2, H3, Hh". With hypotheses forbidden:
  an honest "not derivable from the text". This example also demonstrates the key
  insight that the class rules were never in the source text.

## 12. Acceptance Criteria

- Example A yields `proven` in exactly one wave, with no hypotheses.
- Example B yields `proven_under(H)` and lists the hypotheses; with
  `ANKYRA_ALLOW_HYPOTHESES=false` it yields an honest non-proof.
- No answer is ever reported as `proven` when a hypothesis was used.
- Every explanation step maps to a provenance edge or a hypothesis id.
- With temperature 0 and a fixed model, the theory and the closure are
  deterministic; proposal classification is deterministic for any proposal.

## 13. Open Decisions

Tracked in `docs/implementation_plan.md`; summarized here.

- **D1 (comparisons/builtins) — decided.** v0 has none; thresholds are tagged
  hypotheses. v0.1 adds a minimal range-restricted builtin evaluator (`=`, `neq`,
  `<`, `lte`, `>`, `gte`) behind a flag; Option B (pure hypotheses) remains the
  fallback.
- **Hypothesis mode (decided).** Default is permissive-with-tags
  (`ANKYRA_ALLOW_HYPOTHESES=true`); strict-citation-only is available as a switch.
  Only hypotheses that actually enter the proof count toward answer strength.
- **Orchestration (decided).** LangGraph `StateGraph`, linear with the bounded
  reasoning cycle (section 9). `langgraph` stays a dependency.
- **Deontic modality (decided).** Modality is a first-class `Morphism.modality`
  field; predicate names carry no prefix by default. OntoLegal-style
  `must_`/`must_not_`/`may_` lowering is available behind `ANKYRA_DEONTIC_PREFIXES`
  (with the polarity fold and the double-prefix fix). Option A — always prefix —
  remains the fallback.
