# Reasoning Roadmap — staged formalisms

Main development axis of Ankyra: widen, one stage at a time, the class of
chain-of-thought that the engine can **mechanically decide**. Each stage adds a
formalism (a logic) with a sound decision procedure, is gated by an external
benchmark, and preserves the design commitment: the LLM proposes, the engine
decides.

Canonical language: English; Russian mirror: `docs/reasoning_roadmap_ru.md`.
Related: `docs/logic_layer.md` (the protocol seam), `docs/proofwriter.md`,
`docs/prontoqa.md`, `docs/ar_lsat.md`, `docs/gsm8k.md`,
`docs/defeasible_reasoning.md`, `docs/task.md`, `docs/implementation_plan.md`.

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
| **L0** | Definite Horn, `is_a`, complementary-pair negation | `supported / insufficient / unsupported / refuted` (OWA) | semi-naive forward chaining | ProofWriter | — | **done** (Tier D 296/300) |
| **L1** | Stratified negation / NAF, declared CWA | open/closed world per query; `¬atom` by failure | stratified closure | ProntoQA (negation/disjointness) | `ANKYRA_NEGATION_MODE` | planned |
| **L2** | Positive FOL: disjunction, `∃/∀`, proof by cases | entailment / refutation in a bounded clausal search | bounded resolution | ProntoQA-OOD (compositional), FOLIO | `ANKYRA_LOGIC` | planned |
| **L3** | Finite-domain constraints (CSP/SAT) | `must` = true in all models, `could` = true in some | SAT/SMT or finite-domain search | AR-LSAT | — | planned (separate engine, low priority) |
| **L4** | Arithmetic terms and equations | numeric answer, not entailment | evaluation / equation solving | GSM8K | — | low priority (separate engine / tool-use) |
| **D** | Defaults with specificity via `is_a` | answer plus resolved/undecided conflict | `engine/defeasible.py` | defeasible-NLI / αNLI | `ANKYRA_DEFEASIBLE` | implemented, **unbenchmarked** |

### L0 — Definite Horn (the current spine)

- **Formalism:** positive definite clauses; transitive `is_a`; unary and binary
  atoms; negation only as complementary pairs `P` / `¬P`; open-world.
- **Procedure:** `saturate` (semi-naive forward chaining to a fixed point);
  `verify` classifies `supported / insufficient / unsupported / refuted`; an
  optional range-restricted comparison layer (`=, neq, <, lte, >, gte`).
- **Benchmark:** ProofWriter; Tier D 296/300, accepted as the proof of concept.
  Tier E (full collection) is cancelled (no free LLM access).
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
- **Benchmark:** ProntoQA (`docs/prontoqa.md`), negation/disjointness subset.

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
- **Status:** implemented (`docs/defeasible_reasoning.md`) but **not
  benchmarked**. A defeasible/NLI collection (αNLI or defeasible-NLI) is cheap and
  high signal: it tests the layer that actually distinguishes Ankyra from
  ProofWriter-style deductive harnesses.

## 4. Budget policy

There is no free LLM access; API tokens are paid out of pocket. Therefore:

- each stage enters with a **small committed sample** (ProofWriter Tier A order
  of magnitude), built deterministically without LLM calls, run once, and re-run
  only on a mismatch;
- `ANKYRA_EXTRACT_SAMPLES=1` everywhere;
- gate numbers are recorded per stage; a full collection is a separate,
  explicitly budgeted decision (ProofWriter Tier E is cancelled).

## 5. Prerequisites

Open soundness findings 21–22 (`docs/implementation_plan.md` §8) must be closed
first. A new logic multiplies the ways an unsound proof can hide; adding stages
on top of a known false-proof hole is not acceptable.

## 6. Architecture seam

`docs/logic_layer.md` already names the seam: only **semantics** becomes
pluggable; policy and mechanics stay where they are. The roadmap is the reason to
extract the `Inference` protocol — L1/L2 are new semantics, and L3/L4 are
separate engines behind the same orchestration. Extract the protocol when the
**second** semantics lands (defeasible already qualifies); do not abstract
speculatively.

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
| L0 | ProofWriter | Tier D 300 | 0 grounded false proofs; determinate all `proven`; ≥95% | done (296/300) |
| L1 | ProntoQA (negation) | to build | same + declared CWA | planned |
| L2 | ProntoQA-OOD (compositional), then FOLIO | to build | same; FOLIO stratified by construct | planned |
| L3 | AR-LSAT | to build | per-option solver check | planned (separate engine) |
| L4 | GSM8K | to build | numeric match | low priority |
| D | defeasible-NLI | to choose | resolved/undecided conflict reported | unbenchmarked |
