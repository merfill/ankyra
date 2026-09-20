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
- **D3.** Monotonicity of the *base*: it only grows; the target is never weakened;
  no deletion of premises. The answer itself may change under defeasible semantics;
  such changes are recorded as `Revision` events (item 12), never by mutating the
  base. (Kept for now; can be relaxed later by policy.)
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
   strict vs abductive modes. Current (N=3): strict **45/45** (determinate 30/30 all
   `proven`, Unknown 15/15, no false positives); abduction 30/30 determinate but
   Unknown 7/15 (8 false positives). Added the quote re-formalization guard
   (`classify`, B8), the last-waves hint feedback (B9), and the Phase 0 copula /
   domain formalization (`StructAtom.predication`, `ProblemStructure.domain`) that
   closed the strict gaps. See `quality_findings` section E. The collection, its
   axes and the harness are documented in `docs/proofwriter.md`.
8. ~~**Copula / domain formalization (Phase 0).**~~ **DONE.** A one-place copula
   becomes `is_a(subject, complement)` (never a bare unary predicate), and a rule
   premise restricting a variable to a declared `domain` sort is dropped as the
   quantifier's domain. Closed the ProofWriter `Att*` generalization gaps without
   prompt special-cases.
   **Domain drop — NEEDS INVESTIGATION.** Two distinct effects were observed on
   synthetic structures (not reproduced on ProofWriter), so this is a finding to
   reproduce and size before any fix:
   - *(a) under-derivation:* `enrich.strip_domain_conditions` drops `is_a(?x,D)` for a
     global `domain` sort unconditionally, even when it is the variable's only binder;
     the rule then has no binder and can never fire. The per-rule
     `unroll._normalize_domain` deliberately keeps the sole binder, so the two paths
     disagree. Verified: `domain=["bird"]`, rule `is_a(?x,bird) => fly(?x)` becomes
     condition-less and derives nothing. Likely a bug, independent of over-declaration.
   - *(b) over-derivation (unsound):* when the sort is over-declared and the domain
     premise coexists with another binder, dropping it removes a real restriction and
     the rule fires for non-D individuals. Verified: `domain=["bird"]`, rule
     `is_a(?x,bird) AND has_wings(?x) => fly(?x)`, facts `is_a(rex,dog)`,
     `has_wings(rex)` derives `fly(rex)`.
   Open: whether to keep the premise when the sort is over-declared and never drop the
   sole binder, plus an auditable `over_declared_domain:` gap; reproduce on live
   extraction first (project rule: no speculative machinery).
9. **Staged ProofWriter expansion (tiers B–D) — DONE; D gate green.**
   The committed sample grows along the collection's axes in gated steps, each
   **run once** and re-run only on a mismatch (cost-aware;
   `ANKYRA_EXTRACT_SAMPLES=1`):
   A 45 (done) → B 75 (A + 30 NatLang; **74/75**, gate met) → C 150 (75 core + 75
   NatLang; **148/150**, gate met after the B8 span-overlap fix) → D 300
   (C + 150 `depth-3ext`; first run **296/300** with 2 grounded mismatches; after
   findings 21–22 were closed, a parallel re-run (`--jobs 5`) gave **297/300
   (99%), 0 grounded false proofs**, gate green); the full collection (6 368 theories,
   ≈11 h), Tier E, is **CANCELLED** — there is no free LLM access and API tokens
   are paid out of pocket; the all-questions set (54 848, ≈97 h) stays out of
   scope. **Tier D (300, 99%, 0 grounded false proofs) is the accepted proof of
   concept.**
   Gates per tier: 0 grounded false proofs, every determinate answer `proven`,
   kind accuracy ≥ 90% (B) / 95% (C, D); every remaining failure categorized. The
   tiers serve both measurement and debugging. Built by
   `evals.build_proofwriter_sample --tier`, run by `evals.proofwriter --tier`,
   debugged with `evals.narrate --traces-dir`. See `docs/proofwriter.md` §6–7.

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
3. ~~**Presupposition capture.**~~ **CLOSED (not reproduced / by design).**
   Explicit markers ("given that / assuming / suppose", RU "при условии что") are
   captured in live probes 7/7, and a no-marker control is not over-captured. The
   explicit `QuestionStructure.presuppositions` decomposition is implemented (routed
   to `Query.conditions`, never the theory), and explanation steps grounded on Gamma
   are tagged `source="presupposition"` (`docs/statement_sources.md`). A comma-joined
   declarative is read by Phase 0.2 as a descriptive fact, so its answer is honestly
   `supported`; forcing it into Gamma would demote given information to a
   hypothetical, so it is left as is. Remaining variation is model-side (C1); a
   cue-phrase detector is forbidden by `docs/task.md` §3.8, and raising
   `ANKYRA_EXTRACT_SAMPLES` is measured to give nothing (C1). Live presupposition
   cases are hard-asserted in `tests/test_evals_live.py`.
4. **Variance mitigations.** **Fixed policy: `ANKYRA_EXTRACT_SAMPLES=1` always.**
   Best-of-N extraction sampling is *not* used: it was measured not to improve
   outcomes (C1) — the selection ranker (`quality_key`/`_rank_key`) is a
   syntax/grounding metric that ties on logically different structures, so extra
   samples add cost and self-inflicted nondeterminism without buying correctness.
   Provider variance is handled by repeated independent runs in the harness, never
   by sampling. Historical runs in this document that mention
   `ANKYRA_EXTRACT_SAMPLES=3` predate this rule and stand only as measurements.
   `ANKYRA_EXTRACT_REPAIRS` bounded repair, and `enforce_grounded` are done. The
   provider is measured nondeterministic even at `T=0` (and `ANKYRA_SEED` is
   unverified, kept opt-in only). Selection was hardened: tie-break by canonical
   structural fingerprint (`extract._rank_key`, no arrival-order dependence),
   concurrent samples keep the LLM trace (`copy_context`), and per-role
   `ANKYRA_EXTRACT_TEMPERATURE=0` is honoured. Provider-level determinism is
   accepted as external and out of scope; self-consistency clustering and prompt
   stability remain optional robustness work.
5. ~~**Non-monotonic exceptions.**~~ **DONE** behind `ANKYRA_DEFEASIBLE` (default
   off): every rule is a default and only asserted facts are strict (neither
   extraction nor a predicate heuristic authors strength), the layer in
   `engine/defeasible.py` (NFA + specificity via `is_a`), `Answer.defeasible`, and
   `Explanation.conflict` with the `is_a` reason for resolved defeats and both
   branches for undecided ones. See `docs/defeasible_reasoning.md`.
6. ~~**Builtins case.**~~ **DONE.** Deterministic offline coverage through the full
   builder (`tests/test_build_builtins.py`: `gte`/`gt`/`lte`/string `neq` over
   structure → Theory/Query → verify → Answer, plus the below-threshold and
   flag-off negatives); `check_naming` no longer flags numeric literals or variables
   as object names; the live harness hard-asserts the expectation of the
   `builtins: true` problem, not merely its invariants.
7. ~~**LLM judge.**~~ **REJECTED (won't do).** The deterministic evaluators
   (invariants + expectations) plus a ground-truth benchmark (ProofWriter, strict
   45/45) already verify correctness, and soundness is symbolic — not a matter of
   judgement. An LLM judge would (a) have an unclear target (narration quality is
   cosmetic and mechanically derived; extraction quality is measurable
   deterministically via quote coverage, gaps and wave count), (b) be a stochastic
   judge of the same stochastic provider — noise on noise, no reproducibility, (c)
   give the LLM a deciding role in evaluation, against the engine's design commitment,
   and (d) cost calls for a rubric that cannot be trusted as a metric. Keep the
   `Evaluator` interface as an extension point; revisit only if a concrete qualitative
   question appears that deterministic metrics and ground truth cannot answer.
8. **`ARCHITECTURE.md`** — written (layers, flows, module map).
9. **Pluggable inference semantics — DEFERRED.** See `docs/logic_layer.md`: a
   placeholder, not a task. The second semantics (defeasible) already landed and is
   integrated through the `DEFEASIBLE` flag in `engine/horn.py:derive_closure`, so no
   seam is forced yet. Extract the narrow `Inference` protocol only when a genuinely
   new logic (ASP/probabilistic/…) or a demonstrated need appears; do not abstract
   speculatively.
10. ~~**Direct answer field.**~~ **DONE.** `Answer.kind`
    (`yes|no|unknown|contradiction|binding|instruction`) is computed deterministically
    and `engine.answer.render_answer` localizes it; `evals.narrate` prints it and the
    LLM narration starts from it. Benchmark scoring maps the
    `(kind, strength, defeasible)` tuple plus reason buckets per benchmark — the
    engine keeps no benchmark semantics.
11. ~~**Negation / polarity robustness (Phase 0 hardening).**~~ **DONE.** Two
    deterministic fixes from the ProofWriter runs: `settle_query` drops a condition
    complementary to the target ("is phi?" extracted as positive `phi` plus a `¬phi`
    premise is self-contradictory), and `classify` refuses a quote taken from the
    interrogative span (`_quote_in_question`) so the goal cannot be proved by citing
    the question. The remaining strict misses are honest `unknown` and C1 variance.
12. ~~**Answer revisions (non-monotonic answer audit).**~~ **DONE.** Monotonicity is
    stated for the *base*, not the answer; `Revision` (`wave`, `trigger`,
    `previous`, `current`, `source_ids`) is recorded whenever the answer changes
    between waves and attached to `Explanation.revisions`, and
    `Conflict.source_ids` names the hypotheses behind the competing branches of a
    specificity conflict. No typed-edge/layer ontology is introduced — a fixed
    `physical/vital/...` layer enum would trade domain-generality for a
    hardcoded ontology and is rejected.
13. ~~**Grounded refutation (abduction guard).**~~ **DONE.** Assuming `P` cannot
    refute `¬P`: a hypothesis-backed refutation is downgraded to `unsupported`
    (`hypothetical_refutation:`) and answers `unknown`/`not_proven`, removing the
    8 hypothetical-refutation misses on ProofWriter abductive mode. See
    `docs/quality_findings.md` section F.
14. ~~**Reproducibility plumbing.**~~ **DROPPED (won't do).** `ANKYRA_SEED` merges a
    seed into `ANKYRA_EXTRA_BODY`, and best-of-N extraction samples are issued
    concurrently (`ANKYRA_EXTRACT_PARALLEL`, default true). Provider-side seed
    support is not pursued in this project.
15. ~~**Question-begging guard.**~~ **DONE.** A non-cited fact hypothesis whose atom
    unifies the *closed* target is `rejected/question_begging`; cited descriptive
    facts and open-target bindings are exempt, so Example B is safe. See
    `docs/quality_findings.md` section F.
16. ~~**Structural quantifier sort.**~~ **DONE.** Rules carry `forall` (var → sort);
    `unroll` drops the matching `is_a(?x,sort)` premise as the quantifier's domain,
    keeping it when it is the variable's only binder. Removes the domain-vs-premise
    ambiguity (17–18 rules/run). See `quality_findings` B10.
17. ~~**Canonical property relation + `relation_kind`.**~~ **DONE.**
    `StructAtom.relation_kind ∈ {ascription, possession, action}`; ascription
    canonicalizes to `is_a(subject, property)` in every position, possession never
    does, legacy `predication` is mapped. Fixes the fact-vs-rule encoding mismatch
    (`quality_findings` B11).
18. **Conjunct-loss red flag — CLOSED (not reproduced).** Measured on 11 saved runs
    (~45 structures each): with `Slot.set` (AND) counted correctly the detector fires
    0/249 rules; the suspected "dropped conjunct" was a display artifact (`object.id`
    read while `object.set` held the items). A token-coverage variant false-fires
    ~37% on verb morphology (`need` vs "needs"), i.e. it would need lemmatisation and
    is not worth it. Not implemented.
19. ~~**Conditional-quote guard.**~~ **DONE.** A quote occurring in the source only
    inside a rule's sentence cannot license an axiom (`quote_only_in_conditional`;
    `quote_conditional` rejection, repairable `conditional_quote:` gap). Removed two
    strict false proofs; strict is 45/45. See `quality_findings` B12.
20. **Statement sources — origin vs logical role (design).** See
    `docs/statement_sources.md`. Origin (`cited` / `presupposition` / `hypothesis` /
    `external`) is audit-only and must never feed the closure; the logical role stays
    explicit. First concrete step: attribute explanation steps grounded on Gamma as
    `presupposition`, widening `ExplanationStep.source` so `external` is additive
    later. Beyond that first step, deferred — no source framework (cf. item 9).
21. ~~**Gamma/target injection via `reformalize_query`.**~~ **DONE.**
    `classify._reformalize` now treats the query as fixed by Phase 0: a condition
    absent from the query is `rejected/fabricated_condition`, a substituted target
    is `rejected/target_substituted`, and only `variables` may change (the target
    cannot be dropped). Tier D `RelNeg-OWA-D1-1025`. See `quality_findings` E.
22. ~~**Named-entity conditional over-generalized (extraction).**~~ **DONE.**
    `PROBLEM_SYSTEM` now requires a conditional about a named individual to keep its
    constant (a ground implication); only a generic statement is quantified over
    `?x`. Live case `named_conditional`. Tier D `AttNoneg-OWA-D0-2873`. See
    `quality_findings` E.
23. **Provider accepts an incomplete tool call — WON'T FIX (by design).** A
    function-calling response with an empty `question` (and truncated `facts`)
    validates silently (`ProblemStructure.question` defaults to `""`;
    `structured.py` accepts a non-empty `parsed`), so the question stage gets `""`
    and the query becomes `instruction` (post-fix Tier D `no target extracted`
    182/300). Not a soundness hole (0 grounded false proofs). The provider owns
    incomplete structured output; no guard is added. A bounded retry on an empty
    `question` in `extract_problem_structure` is the fallback if it must be
    mitigated later. See `quality_findings` E.
24. **L1 engine + synthetic gates — DONE.** Disjointness constraints
    (`Theory.constraints`), stratified negation-as-failure and the per-query
    closed-world assumption (`Query.world_assumption`, flag `ANKYRA_NEGATION_MODE`)
    are implemented; `verify` reports `out_of_fragment` for non-stratified
    programs. LLM-free gates: `evals.l1_synthetic` (40/40) and
    `evals.defeasible_synthetic` (8/8). ProntoQA and FOLIO harnesses with committed
    samples are in place; their live runs invoke the paid extractor and are
    pending budget. Plan and decisions: `docs/l1_plan.md`.

## 9. Reasoning roadmap (main axis)

The main development axis is the staged widening of **decidable formalisms**: the
LLM proposes a formalization in a logic `L`, and a sound decision procedure for
`L` decides it. Coverage is measured in named formalisms, not in untethered
"reasoning". The full description is `docs/reasoning_roadmap.md`; per-collection
notes are `docs/proofwriter.md`, `docs/prontoqa.md`, `docs/ar_lsat.md`,
`docs/gsm8k.md`, `docs/folio.md`.

Stages:

- **L0 — definite Horn** (current spine: `is_a`, complementary-pair negation,
  OWA). Benchmark ProofWriter; Tier D 297/300 (re-run, 0 grounded false proofs) is
  the accepted proof of concept.
- **L1 — stratified negation / negation-as-failure** with a declared world
  assumption, for disjointness and explicit negative knowledge. Benchmark
  ProntoQA; flag `ANKYRA_NEGATION_MODE`. **Implemented**: `Constraint` +
  `Query.world_assumption`, stratified NAF in `engine/horn.py`, CWA in
  `engine/verify.py`; primary gate `evals.l1_synthetic` (40/40, LLM-free), plus
  ProntoQA and FOLIO harnesses (`docs/l1_plan.md`; public runs pending budget).
- **L2 — disjunction / positive FOL / proof by cases**, for compositional chains.
  Benchmark ProntoQA-OOD (compositional); flag `ANKYRA_LOGIC`. Second gate
  **FOLIO** (`docs/folio.md`), stratified by FOL construct (in-fragment scored,
  functions/equality/schemas `out_of_fragment`); full FOL is semi-decidable, so
  the search is bounded and exhaustion is an honest `insufficient`.
  **Implemented** (finite-domain form): ground clause IR + bounded set-of-support
  resolution (`engine/clause.py`, `engine/resolution.py`), disjunction/case split,
  quantifiers by Skolemization + witness enumeration, compound/open goals, and the
  `Inference` protocol seam (`engine/inference.py`); primary LLM-free gate
  `evals.l2_synthetic` (**23/23**). **ProntoQA-OOD tier-a live gate green** —
  **41/42 (97.6%), 0 grounded false proofs**; **FOLIO L2 live is extraction-bound**
  (26/44, no engine unsoundness; backlog G1–G4 in `docs/quality_findings.md` §G).
  Full first-order unification is deferred (`docs/l2_plan.md`).
- **L3 — finite-domain CSP/SAT, a separate engine.** Benchmark AR-LSAT.
- **L4 — arithmetic, a separate numeric engine or tool-use.** Benchmark GSM8K.
- **D — defeasible** (behind `ANKYRA_DEFEASIBLE`); **implemented + synthetic gate**
  `evals.defeasible_synthetic` (8/8, LLM-free); a defeasible-NLI set remains a
  cheap, differentiating real-data gate.

Decisions: L3/L4 are separate engines and low priority; arithmetic is preferably
tool-use, not an in-repo core. The architecture seam is `docs/logic_layer.md`
(only semantics becomes pluggable). **Prerequisite:** close soundness findings
21–22 first. **Budget:** each stage enters with a small committed sample (no free
LLM access); full collections are separately budgeted.

## 10. Gating methodology on composite benchmarks

A collection is a **gate for one stage**, not a headline score, and a benchmark
whose gold annotation mixes constructs from different stages must be run as an
**in-fragment slice**. FOLIO (`docs/folio.md`) is the worked case: its gold FOL
spans constructs that belong to different stages (`∨`/`∃` → L2) and constructs that
belong to **no** committed stage (equality, function terms, `⊕`, `↔`, axiom schemas,
multi-variable quantification).

- **Run the slice, once, as a gate.** Select the subset whose annotation stays
  inside the stage's formalism (`in_l2`, `in_l1_negation`), run it once, record the
  result and move on; re-run only on a mismatch. The slice is a gate, never a
  progress number, and must not be tuned against — improvements come from the
  general extraction contract, not from individual ids (see §G of
  `docs/quality_findings.md`).
- **Whole-collection headline waits, but never becomes clean.** Accuracy over all
  rows is meaningful only once coverage is near-complete; yet the beyond-stage
  constructs lie outside L0–L4 as committed (L3 = CSP, L4 = numeric, separate
  engines), so full coverage is unreachable by design. FOLIO stays a composite
  benchmark, not the final scoreboard.
- **Two ceilings, named explicitly.** *Coverage* (formalism): how many rows the
  committed logic can express at all; `out_of_fragment` is an honest abstention
  that costs recall, never soundness. *Extraction* (model): of the covered rows,
  how many the LLM translates correctly. Evidence: ProntoQA-OOD — both clear
  (41/42); FOLIO L1 — coverage-bound (gold-fed 7/13, `docs/folio.md` §9); FOLIO L2
  — extraction-bound.
- **Gate ladder.** LLM-free synthetic (pure engine signal) → simple-surface real
  collection (ProntoQA-OOD) → hard real collection slice (FOLIO). Keep all three;
  the last is deliberately extraction-heavy.
- **Gold-fed upper bound is the counterfactual that separates the ceilings.** Feed
  the engine the gold FOL formulas and measure method-only accuracy on the same
  slice. It exists for the L1 negation shape but **not yet for L2**:
  `evals/folio_fol.py` parses only the L1 shape. **Next step before L3:** extend
  the parser to `∨`/`∃` (one file, LLM-free) so the L2 slice gains its gold-fed
  bound — if gold-fed ≫ text-fed the limit is language, otherwise method. This
  settles "model vs method" empirically rather than by intuition.
