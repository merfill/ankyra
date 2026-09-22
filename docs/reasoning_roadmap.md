# Reasoning Roadmap — staged formalisms

Main development axis of Ankyra: widen, one stage at a time, the class of
chain-of-thought that the engine can **mechanically decide**. Each stage adds a
formalism (a logic) with a sound decision procedure, is gated by an external
benchmark, and preserves the design commitment: the LLM proposes, the engine
decides.

Canonical language: English; Russian mirror: `docs/reasoning_roadmap_ru.md`.
Related: `docs/logic_layer.md` (the protocol seam), `docs/fragment_routing.md`
(the declared-fragment contract), `docs/l1_plan.md` (the L1
implementation plan), `docs/l2_plan.md` (the L2 implementation plan),
`docs/proofwriter.md`, `docs/prontoqa.md`, `docs/folio.md`,
`docs/folio_ceilings.md` (coverage vs extraction ceilings),
`docs/folio_extension_plan.md` (staged FOLIO extension, deferred),
`docs/coverage_ceiling.md` (the coverage ceiling explained, and the Tier-1 plan),
`docs/t1_plan.md` (Tier-1 item T1: shared-witness existential goal),
`docs/t3_plan.md` (Tier-1 item T3: universal/`¬∃` goal form),
`docs/t5_plan.md` (Tier-1 item T5: head-only universal premise),
`docs/t4_t2_plan.md` (Tier-1 items T4/T2: non-flat ground goal, nested-disjunction premise),
`docs/t6_plan.md` (Tier-1 item T6: ground unit propagation, G4),
`docs/ar_lsat.md`,
`docs/gsm8k.md`, `docs/defeasible_reasoning.md`, `docs/task.md`,
`docs/implementation_plan.md`.

## 1. Thesis

Ankyra is not "a Horn solver"; it is an **orchestrator of formalizations and
decision procedures**. The end goal is to cover the largest practical class of
chain-of-thought that has a decidable checking procedure: the LLM produces a
formalization in a logic `L`, and a sound procedure for `L` decides it. Coverage
is therefore measured in **named formalisms**, never in untethered "reasoning".

Boundary: where no sound decision procedure exists (full undecidable FOL,
probabilistic or statistical inference), Ankyra does not claim to decide. It may
still narrate, but it must not certify. Staying inside this boundary is what
keeps `proven` meaningful.

## 2. Stage contract

Every stage is defined by the same six items:

- **Formalism** `L` — the logic and the semantics of an answer.
- **Decision procedure** — sound for `L` (and, where claimed, complete).
- **Engine change** — what is added or refactored.
- **Extraction change** — what Phase 0 (and the proposal cycle) must be able to
  express, so the LLM can propose in `L`.
- **Benchmark gate** — an external collection with a small committed sample and
  hard invariants: 0 grounded false proofs, every determinate answer `proven`,
  kind accuracy above the stage threshold, every remaining failure categorized.
- **Flag** — off by default; benchmark semantics never leak into the engine.

## 3. Stages

| Stage | Formalism | Answer semantics | Procedure | Benchmark | Flag | Status |
|---|---|---|---|---|---|---|
| **L0** | Definite Horn, `is_a`, complementary-pair negation | `supported / insufficient / unsupported / refuted` (OWA) | semi-naive forward chaining | ProofWriter | — | **done** (Tier D 297/300) |
| **L1** | Stratified negation / NAF, declared CWA | open/closed world per query; `¬atom` by failure | stratified closure | ProntoQA (negation/disjointness) | `ANKYRA_NEGATION_MODE` | implemented; gates green (synthetic 40/40, ProntoQA 208/208) |
| **L2** | Positive FOL: disjunction, `∃/∀`, proof by cases | entailment / refutation in a bounded clausal search | bounded resolution | ProntoQA-OOD (compositional), FOLIO | `ANKYRA_LOGIC` | implemented; ProntoQA-OOD live 41/42 (0 grounded false proofs); FOLIO live extraction-bound |
| **L3** | Finite-domain constraints (CSP/SAT) | `must` = true in all models, `could` = true in some | SAT/SMT or finite-domain search | AR-LSAT | — | planned (separate engine, low priority) |
| **L4** | Arithmetic terms and equations | numeric answer, not entailment | evaluation / equation solving | GSM8K | — | low priority (separate engine / tool-use) |
| **D** | Defaults with specificity via `is_a` | answer plus resolved/undecided conflict | `engine/defeasible.py` | defeasible-NLI / αNLI | `ANKYRA_DEFEASIBLE` | implemented + synthetic gate |

### L0 — Definite Horn (the current spine)

- **Formalism:** positive definite clauses; transitive `is_a`; unary and binary
  atoms; negation only as complementary pairs `P` / `¬P`; open-world.
- **Procedure:** `saturate` (semi-naive forward chaining to a fixed point);
  `verify` classifies `supported / insufficient / unsupported / refuted`; an
  optional range-restricted comparison layer (`=, neq, <, lte, >, gte`).
- **Benchmark:** ProofWriter; Tier D re-run **297/300 (99%)**, 0 grounded false
  proofs, accepted as the proof of concept. Tier E (full collection) is cancelled
  (no free LLM access).
- **Status:** done. No new work; this is the baseline every later stage extends.

### L1 — Stratified negation / negation-as-failure

- **Formalism:** definite clauses plus stratified negation and negative
  constraints; a per-query world assumption (open vs closed).
- **Procedure:** stratify predicates by dependency; evaluate negated goals only
  after their stratum; under a declared closed world, derive `¬atom` when the
  atom is unprovable in a lower stratum.
- **Enables:** `False` answers that rest on **disjointness** (no individual is
  both `A` and `B`) or on explicit negative knowledge; "not stated, therefore not
  holding" when the closed world is explicitly declared.
- **Engine change:** represent negative constraints (a deny rule or a rule with a
  contradictory head); stratify `saturate`; extend `verify` with an explicit world
  assumption carried by the query.
- **Extraction change:** negative antecedents/consequents beyond the current
  single `negated` flag; disjointness sentences.
- **Risk:** CWA is a *semantic choice*. Applying it silently to an open-world
  benchmark manufactures false refutations. The mode must be attached to the
  query/benchmark, never guessed from wording.
- **Benchmark:** ProntoQA (`docs/prontoqa.md`), negation/disjointness subset; the
  negated-premise subset of **FOLIO** (`docs/folio.md`) is a secondary L1 stress.
- **Plan:** `docs/l1_plan.md` (working plan; open decisions `D-L1-1`…`D-L1-5`).
- **Status:** engine implemented (disjointness constraints, stratified NAF, declared
  CWA) and gated LLM-free by `evals.l1_synthetic` (**40/40**); the ProntoQA L0/L1
  live gates are green (tier a 48/48, tier b 160/160, all `proven`, 0 grounded false
  proofs), and the FOLIO negation subset was run as a secondary cross-check (6/13;
  mismatches are formalization/fragment, not unsoundness). ProntoQA v1 itself
  exercises only explicit negation, which was already supported (see
  `docs/prontoqa.md` §8). **ProntoQA is closed**: tested at L1, both tiers green,
  no further runs unless a later stage specifically needs the collection (then as
  its own budgeted decision).

### L2 — Positive FOL: disjunction, quantifiers, proof by cases

- **Formalism:** clauses with disjunctive antecedents or consequents (Horn is the
  special case), existential elimination, case splits, proof by contradiction.
- **Procedure:** bounded resolution / a clausal prover with an explicit step
  budget; provenance for each case branch.
- **Enables:** compositional chains — the OrIntro/OrElim, De Morgan and
  proof-by-contradiction examples of PrOntoQA-OOD — and a real share of "most
  CoT".
- **Engine change:** rules become clauses; `match_goal` handles disjunction;
  `Explanation` gains case-split steps; bounded search keeps termination honest
  (`insufficient` instead of a loop).
- **Note:** Phase 0 already exposes `Slot.variants` / `exclude`, but `unroll`
  expands them into **separate morphisms** (alternative fillers), not a logical
  disjunction. L2 is specifically about the latter.
- **Benchmark:** the compositional subset of ProntoQA-OOD first; then **FOLIO** as
  the second L2 gate (`docs/folio.md`). FOLIO's annotations span L1 (negation) and
  L2 (disjunction, `∃`) and add functions/equality/axiom schemas beyond the
  committed fragment, so a run must be **stratified by FOL construct**: only the
  in-fragment subset is scored, the rest is reported `out_of_fragment`. Entailment
  in full FOL is only semi-decidable — the search stays bounded and exhaustion is
  the honest `insufficient`.
- **Risk:** combinatorial blow-up; the budget must be explicit and the answer
  honest when it is exhausted.
- **Plan:** `docs/l2_plan.md` (approved plan; decisions `D-L2-1`…`D-L2-7`).
- **Status:** engine implemented behind `ANKYRA_LOGIC` — ground clause IR + bounded
  set-of-support resolution, disjunction/case split, finite-domain quantifiers
  (Skolemization + witness enumeration), compound/open goals, and the `Inference`
  protocol seam. LLM-free synthetic gate `evals.l2_synthetic` is green (**52/52**, 0
  grounded false proofs); the **ProntoQA-OOD tier-a live gate is green** (**41/42
  (97.6%), 0 grounded false proofs**), while FOLIO's L2 live gate is
  **extraction-bound** (26/44; the misses are no-target/out-of-fragment or a universal
  conclusion collapsed to a ground atom, not engine unsoundness). The LLM-free
  gold-fed   diagnostic for L2 (`docs/folio.md` §10) shows the deeper limit is
  **coverage**: on FOLIO L2 tier a only 21/45 gold formulas were in the committed
  fragment, but on those gold-fed (17/21) out-scores text-fed (15/21), pointing at
  Tier-1 lowering rather than extraction — the explained plan is
  `docs/coverage_ceiling.md`. **Tier-1 T1 (shared-witness `∃x(A(x)∧B(x))`) is done**
  (`docs/t1_plan.md`): a joint `all` goal with no new flag raised coverage to 25/45,
  gold-fed to 21/45 (covered 21/25), 0 grounded false proofs.   **Tier-1 T3 (universal
  clause goal `∀x(l₁ ∨ … ∨ lₙ)`, subsuming `∀x(A→B)` and `¬∃x φ`) is done**
  (`docs/t3_plan.md`): `goal_mode="forall"`, supported at a *fresh* constant and
  refuted by one named witness, raised coverage to 27/45 and gold-fed to 23/45
  (covered 23/27), 0 grounded false proofs; `evals.l2_synthetic` is now 36/36.
  **Tier-1 T5 (head-only universal premise `∀x(l₁ ∨ … ∨ lₙ)`) is done**
  (`docs/t5_plan.md`): the head-only variable is grounded over the **individual
  domain** (pool minus `is_a` objects; resolves T-D1), raising coverage to 39/45,
  gold-fed to 35/45 (covered 35/39), 0 grounded false proofs; `evals.l2_synthetic`
  41/41, `evals.routing_synthetic` 15/15. **Tier-1 T4 (non-flat ground goal) and T2
  (nested-disjunction existential premise) are done** (`docs/t4_t2_plan.md`): T4 is
  `Query.goal_clauses` (CNF) + `goal_mode="cnf"`, decided by unsatisfiability of
  `T ∧ ¬φ` / `T ∧ φ`; T2 Skolemizes a CNF existential body clause by clause. This
  raises coverage to **44/45**, gold-fed to **40/45** (covered 40/44), 0 grounded
  false proofs; `evals.l2_synthetic` 52/52, `evals.routing_synthetic` 17/17. **Tier-1
  T6 (G4 resolution budget / ground unit propagation) is done** (`docs/t6_plan.md`):
  a unit-propagation fixpoint before the set-of-support loop (each step a real
  resolution edge, same budget) decides the two budget-exhausted rows, raising
  gold-fed to **42/45** (covered 42/44), 0 grounded false proofs; `evals.l2_synthetic`
  56/56, `evals.routing_synthetic` 17/17. Tier-1 is
  complete; only the malformed FOLIO row `0109` stays `out_of_fragment`. Full
  first-order **unification** is
  deferred: a prototype diverges on `not_entailed` (semi-decidability); the committed
  collections are finite named domains, where grounding is sound and terminating.

### L3 — Finite-domain constraints (CSP/SAT) — *separate engine*

- **Formalism:** finite domains with all-different, ordering, adjacency and
  conditional constraints; "must be true" = true in every model, "could be true"
  = true in some model.
- **Procedure:** a SAT/SMT solver (Z3) or an in-repo finite-domain search over a
  dedicated CSP IR.
- **Enables:** AR-LSAT analytical reasoning (`docs/ar_lsat.md`).
- **Engine change:** a second engine (CSP IR + solver) and a multiple-choice
  adapter; Ankyra orchestrates the formalization, not the inference.
- **Risk:** extracting constraints is the hard part, and positional specifics
  tempt a hardcoded ontology (forbidden by `docs/task.md` §3.8). Low priority.

### L4 — Arithmetic and numeric terms — *separate engine or tool-use*

- **Formalism:** terms with arithmetic, equations, numeric answers with a
  tolerance.
- **Procedure:** term evaluation / equation solving (e.g. sympy) — not the
  symbolic core.
- **Enables:** GSM8K-style word problems (`docs/gsm8k.md`).
- **Note:** arithmetic checking is trivial; the difficulty is modelling, which is
  not a soundness question for the symbolic engine. The preferred form is
  tool-use (the LLM drives a numeric tool), not a new in-repo core.
- **Status:** low priority; explicitly outside the current scope in
  `docs/task.md` §1.

### D — Defeasible (cross-cutting, already implemented)

- **Formalism:** every rule is a default; only asserted facts are strict;
  specificity via `is_a`.
- **Procedure:** `engine/defeasible.py` (NFA + specificity), behind
  `ANKYRA_DEFEASIBLE`.
- **Status:** implemented (`docs/defeasible_reasoning.md`) and gated LLM-free by
  `evals.defeasible_synthetic` (**8/8**); a defeasible/NLI collection (αNLI or
  defeasible-NLI) remains a cheap real-data cross-check.

## 4. Budget policy

There is no free LLM access; API tokens are paid out of pocket. Therefore:

- each stage enters with a **small committed sample** (ProofWriter Tier A order
  of magnitude), built deterministically without LLM calls, run once, and re-run
  only on a mismatch;
- `ANKYRA_EXTRACT_SAMPLES=1` everywhere;
- gate numbers are recorded per stage; a full collection is a separate,
  explicitly budgeted decision (ProofWriter Tier E is cancelled).

## 5. Prerequisites

Findings 21–22 (`docs/implementation_plan.md` §8 — Gamma/target injection and the
named-entity conditional) are closed, so the prerequisite for L1/L2 is met. A new
logic multiplies the ways an unsound proof can hide, so soundness findings stay
gating: do not add a stage on top of a known false-proof hole.

## 6. Architecture seam

`docs/logic_layer.md` already names the seam: only **semantics** becomes
pluggable; policy and mechanics stay where they are. The roadmap is the reason to
extract the `Inference` protocol — L1/L2 are new semantics, and L3/L4 are
separate engines behind the same orchestration. Extract the protocol when the
**second** semantics lands (defeasible already qualifies); do not abstract
speculatively.

Choosing *which* semantics runs is specified separately as the declared-fragment
contract in `docs/fragment_routing.md`: the fragment is derived from the built
structure, the semantics is declared by the query/harness, and a mismatch is an
honest `out_of_fragment`, never a guess.

## 7. Non-goals

- A promise of "general reasoning" without a named decision procedure.
- A single monolithic engine that swallows CSP and arithmetic; those are separate
  procedures with their own IR.
- Hardcoded domain ontologies to pass a benchmark (forbidden by
  `docs/task.md` §3.8).
- Running full public collections while there is no free compute.

## 8. Status summary

| Stage | Benchmark | Committed sample | Gate | Status |
|---|---|---|---|---|
| L0 | ProofWriter | Tier D 300 | 0 grounded false proofs; determinate all `proven`; ≥95% | done (297/300 re-run) |
| L1 | ProntoQA (negation), FOLIO negation subset | ProntoQA tier a/b | same + declared CWA | implemented (engine) + synthetic gate; ProntoQA green and closed |
| L2 | ProntoQA-OOD (compositional), then FOLIO | ProntoQA-OOD tier a (44), FOLIO L2 tier a (45) | same; FOLIO stratified by construct | implemented; ProntoQA-OOD live 41/42 (0 grounded false proofs), FOLIO live extraction-bound (26/44); Tier-1 T1 (shared-witness ∃), T3 (universal clause goal), T5 (head-only universal premise), T4 (non-flat ground goal), T2 (nested-disjunction premise) and T6 (G4 ground unit propagation) raise gold-fed coverage to 44/45, 42/45 correct (`docs/t1_plan.md`, `docs/t3_plan.md`, `docs/t5_plan.md`, `docs/t4_t2_plan.md`, `docs/t6_plan.md`) |
| L3 | AR-LSAT | to build | per-option solver check | planned (separate engine) |
| L4 | GSM8K | to build | numeric match | low priority |
| D | defeasible-NLI | to choose | resolved/undecided conflict reported | implemented + synthetic gate |
