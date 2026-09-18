# Implementation Plan — Ankyra

Status: **draft**. Design agreed in discussion; open decisions marked `OPEN`.
This document records the agreed architecture and every alternative we must not forget.
The technical spec (`docs/task.md`) will be rewritten to match this plan once the
open decisions below are closed.

## 1. Goal

A domain-general hybrid neuro-symbolic reasoning engine. The LLM proposes; a
deterministic symbolic engine classifies, derives and verifies. The LLM never
owns truth: it may propose freely, but every proposal is either licensed by the
theory, grounded in a quote, or recorded as an explicit hypothesis.

## 2. Agreed architecture

### Phase 0 — decomposition (special text processing)

One dedicated stage that produces three separate artifacts and never mixes them:

- `theory_structure` — facts and rules extracted from the descriptive part;
- `question_structure` — the target `phi` (with variables for what/which/who),
  the question constants, and the conditions `Gamma` the question asserts;
- `answer_type ∈ {yes_no, open, instruction}` (instruction ⇒ `phi = null`).

Hard rule: the question is never asserted as a fact (equivalent of OntoLegal's
`_drop_goal_echo`). The question is expressed over the theory vocabulary when
possible; if it cannot be expressed, it is kept verbatim so verification can
honestly report `target_unmatched`.

### Phase 1 — deterministic engine (the spine)

- Data model: `Object`, `Morphism` (`predicate, subject, object, quote, negated`),
  `Rule` (`conditions` AND → `consequence`), `Theory` (`objects`, `morphisms`
  = axioms, `rules`), `Query` (`conditions`, `target`, `variables`).
- `saturate`: forward chaining to a fixed point (semi-naive), terminating on a
  finite universe; every derived fact carries provenance (`used`, `witness`,
  `rule_index`).
- `unify` / `match_goal`, `complementary` (P ∧ ¬P), transitive closure of
  positive `is_a`.
- `verify(Theory ∪ Gamma ⊢ phi)` → verdict with status
  `supported | insufficient | unsupported | refuted` and structured gaps
  (`target_unmatched:`, `condition_unmatched:`, `unused_premise:`, `contradiction:`).
- This layer alone is sound and complete **relative to the formalization**. It is
  not allowed to add knowledge.

### Phase 2 — guided cycle

Inner loop (deterministic, no LLM): `saturate` to a fixed point.
Outer wave (LLM), repeated:

1. `verify(state)` → verdict + structured gaps.
2. Assemble the hint: problem structure + theory vocabulary + derived frontier +
   gaps + target + grounding rules.
3. LLM free reasoning → one typed proposal + narration.
4. Deterministic classification of the proposal:
   | category | condition | engine action |
   |---|---|---|
   | `derivable` | already derivable | accept as narration only |
   | `cited` | new fact with a valid verbatim quote | add to axioms |
   | `hypothesis` | new rule/fact not in the text | hypothesis ledger, tagged `H` |
   | `rejected` | schema / safety / quote fails | drop with a reason code |
5. Apply accepted additions, re-run the inner loop, re-verify.
6. Stop on `supported` / `refuted` / `no_progress` / budget / no reachable hypothesis.

Freedom ramp (policy, not architecture): wave 0 is permissive (free predicate
naming, hypotheses allowed and tagged); later waves constrain — canonicalize
names, reuse the established vocabulary, optionally forbid hypotheses
(`ANKYRA_ALLOW_HYPOTHESES=false`).

### Phase 3 — explanation

The reasoning trace is built **mechanically** from provenance (`used`/`witness`).
The LLM may only paraphrase the finished derivation tree; it may not introduce
facts. Answer strength is explicit: `proven`, `proven_under(H)`, or `not_proven`.

## 3. Invariants (fixed now, changeable by policy later)

- **D2.** No LLM-authored fact enters the theory without either a valid quote
  (`cited`) or an explicit hypothesis tag (`hypothesis`). The old ReAct
  `new_predicates` injection is rejected outright.
- **D3.** Monotonicity: the base only grows; the target is never weakened; no
  deletion of premises. (Kept for now; can be relaxed later by policy.)
- **D4.** Answer strength is always reported (`proven` vs `proven_under(H)`).
- **D5.** Phase 0 separates theory from question.
- **D6.** Freedom in proposal, determinism in classification.
- **G1.** Only one proposal action per wave; every wave leaves an auditable trace.
- **Confirmed (decision):** the hypothesis ledger, answer strength, proposal
  classification, and `Rule.source` are **core**, not optional. Default hypothesis
  mode is permissive-with-tags (`ANKYRA_ALLOW_HYPOTHESES=true`); strict-citation-only
  is a switch. Only hypotheses that enter the proof count toward answer strength.
- **Confirmed (decision):** modality is a first-class `Morphism.modality` field;
  predicate names carry no prefix by default; OntoLegal-style lowering is behind
  `ANKYRA_DEONTIC_PREFIXES`.
- **Confirmed (decision):** orchestration uses LangGraph (`StateGraph`) as a linear
  graph with the bounded reasoning cycle.

## 4. Worked examples as acceptance tests

### Example A — rain (pure deduction, 1 wave, no hypotheses)

- Phase 0: theory = `{raining()}` + rule `R1: raining() => isWet(ground)`;
  question `phi = isWet(ground)`, type `yes_no`, `Gamma = {}`.
- Wave 0 (deterministic only): `saturate` fires `R1`; `verify` → `supported`.
- Expected: answer "yes", explanation from provenance. No LLM call in the loop.

### Example B — vehicle (abduction, N waves, hypotheses)

- Phase 0: theory = facts `hasEngine(X)`, `wheelCount(X,4)`, `power(X,150)`,
  `doorCount(X,4)`; **no rules** (class rules are not in the text);
  question `phi = is_a(X, ?c)`, type `open`.
- Wave 0: closure yields nothing for `phi`; `verify` → gap `target_unmatched: is_a`.
- LLM proposes class rules + hierarchy. They carry no text quote ⇒ `hypothesis`
  (`H1`, `H2`, `H3`, `Hh` for `is_a(car, motorVehicle)`, `is_a(sedan, car)`).
- Re-close: `is_a(X, motorVehicle)`, `is_a(X, car)`, `is_a(X, sedan)` + transitive
  `is_a`. `match_goal(is_a(X, ?c))` binds `?c`; "most specific" is now **defined**
  by the `is_a` chain, not guessed.
- Expected: "X is a sedan, **under** H1,H2,H3,Hh". With hypotheses forbidden:
  honest refusal. This example also demonstrates the key insight that the class
  rules were never in the source text.

### Example C — Nixon diamond (defeasible conflict, undecided)

- Phase 0: facts `is_a(nixon, quaker)`, `is_a(nixon, republican)`; rules
  `R1: is_a(?x, quaker) => pacifist(?x)` and
  `R2: is_a(?x, republican) => NOT pacifist(?x)`, both defaults (all rules are);
  question `phi = pacifist(nixon)`, type `yes_no`. `ANKYRA_DEFEASIBLE` on.
- Strict closure yields the two `is_a` facts and no `pacifist`. Both defaults
  produce candidates; there is no `is_a` between `quaker` and `republican`, so
  specificity is undefined.
- `verify` → `unsupported` with gap `undecided_conflict:pacifist`; answer
  `not_proven`.
- Explanation: `Explanation.conflict` (`kind = defeasible`, `status = undecided`,
  `defeated = none`) with both rule applications.
- This is the boundary of defeasibility: equal or incomparable specificity is
  never guessed.

### Example D — penguin, both directions (specificity + defeasible marker)

- (a) "Birds can fly. Penguins are birds, but penguins cannot fly. Tweety is a
  penguin." → `is_a(penguin, bird)` makes the penguin default strictly more
  specific: `refuted` with `target_refuted:fly`, answer "no",
  `Answer.defeasible = true`.
- (b) "Birds cannot fly. Penguins can fly. Tweety is a penguin." → the same
  specificity picks the other polarity: `supported`, answer "yes",
  `Answer.defeasible = true`.
- Demonstrates that defeat is polarity-independent and that the answer marks a
  default as such.

### Example E — strict contradiction (inconsistent theory)

- "All dogs are mammals. Rex is a dog. Rex is not a mammal. Is Rex a mammal?"
  Strict closure derives `is_a(rex, mammal)` and holds `NOT is_a(rex, mammal)`;
  the pair is in the target's proof → `Status.contradiction`, answer `not_proven`,
  `Explanation.conflict` (`kind = strict`, both branches).
- An inconsistency unrelated to the target (`q ∧ ¬q`, question about `p`) is a
  weaker case: the answer is produced normally and the theory carries an
  `inconsistent_theory:` gap (decision D-G).

## 5. DECIDED — comparisons / builtins (decision D1)

Status: **DECIDED** — v0 ships without builtins; v0.1 adds the evaluator.
This bites Example B (`power > 50`, `wheelCount >= 4`).

### Option A — minimal range-restricted builtin evaluator

- Closed set: `=`, `neq`, `<`, `lte`, `>`, `gte` over literal numbers.
- Safety: every variable used in a builtin goal must be bound by an earlier
  positive relational atom in the same rule body; otherwise the rule is rejected.
- Semantics: a builtin atom is not matched against facts — it is *evaluated*,
  filtering substitutions during unification.
- Pros: thresholds/properties are expressible directly; avoids polluting the
  hypothesis ledger with trivial arithmetic; deterministic and still sound (a
  builtin is computable, not learned); closes Example B without hypotheses for
  the numeric part.
- Cons: needs a value domain (numeric literals), parsing of numbers extracted
  from text, and strict range-restriction enforcement to keep termination.

### Option B — no builtins; thresholds as explicit predicates/hypotheses

- The LLM proposes e.g. `powerAbove50(X)` as a hypothesis fact, or a discretized
  predicate. Everything stays a Horn fact; no value domain.
- Pros: engine stays trivial; no new machinery.
- Cons: the ledger fills with trivial numeric facts; the number → discrete-class
  mapping becomes a fresh hypothesis each time (poor reuse); the discretization
  is exactly where mistakes hide.

### Decision

- **v0:** engine ships **without** builtins; Example B expresses thresholds as
  `hypothesis` facts. `unify`/`saturate` are designed with a single extension
  point (an `evaluate(builtin_atom, subst)` hook) so Option A plugs in without
  rework.
- **v0.1:** add Option A as the first extension, under the closed-set + safety
  spec above, behind a flag.
- Keep Option B as the documented fallback.

## 6. Other open questions

- **Hypothesis mode (DECIDED).** Default permissive-with-tags
  (`ANKYRA_ALLOW_HYPOTHESES=true`); strict-citation-only behind the switch.
- **Orchestration (DECIDED).** LangGraph `StateGraph`, linear with a bounded cycle
  (section 9 of `docs/task.md`). `langgraph` stays a dependency.
- **Retrieval (DECIDED — not applicable).** Ankyra is not a retrieval system and has
  no fragments. The input is a single self-contained problem; the engine reasons over
  it directly. No recall/rerank/alignment-to-fragment layer.
- **Deontic modality (DECIDED).** Modality is a first-class `Morphism.modality`
  field; predicate names carry no prefix by default. OntoLegal-style
  `must_`/`must_not_`/`may_` lowering lives behind `ANKYRA_DEONTIC_PREFIXES`
  (with the polarity fold and the double-prefix fix). Option A (always prefix)
  remains the documented fallback.

## 7. Milestones (tentative)

1. Data model + Phase 0 extraction schemas.
2. Deterministic engine (saturate / unify / verify / provenance) + tests on
   Example A.
3. Guided cycle with hypothesis ledger + tests on Example B.
4. Mechanical explanation from provenance; optional LLM narration.
5. Extension point for builtins (Option A) behind a flag.
6. ~~**Open-query binding & honest insufficiency.**~~ **DONE.** `Query.variables` is a
   declaration of unknowns only — the binding comes from unification
   (`verify`/`explain` no longer seed `build_context` with it); `settle_query`
   never deletes a question premise, so an unused one reaches `verify` as
   `insufficient`, which the cycle treats as terminal. Fixes `vehicle`
   (`no_progress` → `supported`/`proven_under`) and `insufficient`
   (`supported` → `insufficient`). See `quality_findings` A4/B7.
7. ~~**Public benchmark harness (ProofWriter).**~~ **DONE.** Committed Tier A sample
   (45 open-world synthetic-core problems, depth 0/1/2/3/5) built deterministically
   by `evals.build_proofwriter_sample`; `evals.proofwriter` maps
   True/False/Unknown to `Answer.kind` with explicit polarity handling and reports
   strict vs abductive modes. Baseline: strict **40/45** (determinate 25/30 all
   `proven`, Unknown 15/15, no false positives); abduction 30/30 determinate but
   Unknown 5/15. Added the quote re-formalization guard (`classify`, B8) and the
   last-waves hint feedback (B9). See `quality_findings` section E.

## 8. Backlog (from the eval harness)

Source: `docs/quality_findings.md`. Ordered by priority.

1. ~~**Explanation fidelity (bug).**~~ **DONE.** `build_explanation` branches on the
   status: `target_refuted` -> negative proof; `contradiction` -> both branches in
   `Explanation.conflict`; an undecided defeasible conflict -> both competing rules;
   `unsupported` / `insufficient` -> empty trace. A new terminal status
   `contradiction` is reported only when the complementary pair is in the target's
   proof; an unrelated inconsistency is an `inconsistent_theory:` gap.
2. ~~**Rule provenance in explanations.**~~ **DONE.** `materialize_rule_morphisms`
   and `heal_contradictory_axioms` are gone: rule consequences are not axioms, and a
   real contradiction reaches the engine.
3. **Presupposition capture.** Get "given that / assuming" clauses into question
   conditions reliably (stricter question prompt + broader examples, or a dedicated
   question pass).
4. **Variance mitigations.** `ANKYRA_EXTRACT_SAMPLES` multi-sample extraction with a
   deterministic pick; steadier prompts; provider seed if available.
5. ~~**Non-monotonic exceptions.**~~ **DONE** behind `ANKYRA_DEFEASIBLE` (default
   off): every rule is a default and only asserted facts are strict (neither
   extraction nor a predicate heuristic authors strength), the layer in
   `engine/defeasible.py` (NFA + specificity via `is_a`), `Answer.defeasible`, and
   `Explanation.conflict` with the `is_a` reason for resolved defeats and both
   branches for undecided ones. See `docs/defeasible_reasoning.md`.
6. **Builtins case.** A dedicated eval that actually exercises `gte`/`gt` thresholds.
7. **LLM judge.** Implement `LLMJudgeEvaluator` (correctness + efficiency against a
   per-problem rubric) on the existing `Evaluator` interface.
8. **`ARCHITECTURE.md`** — written (layers, flows, module map).
9. **Pluggable inference semantics (future).** See `docs/logic_layer.md`: extract a
   narrow `Inference` protocol only when the second semantics (defeasible) lands; do
   not abstract speculatively.
10. ~~**Direct answer field.**~~ **DONE.** `Answer.kind`
    (`yes|no|unknown|contradiction|binding|instruction`) is computed deterministically
    and `engine.answer.render_answer` localizes it; `evals.narrate` prints it and the
    LLM narration starts from it. Benchmark scoring maps the
    `(kind, strength, defeasible)` tuple plus reason buckets per benchmark — the
    engine keeps no benchmark semantics.
