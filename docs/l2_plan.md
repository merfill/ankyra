# L2 Plan — Positive FOL: disjunction, quantifiers, proof by cases

Status: **approved plan** — implementation complete. All decisions in §18
(D-L2-1…D-L2-7) are **DECIDED**. **Milestones 1–11 are done** (recon; data model +
schema + builder plumbing; ground clause IR + bounded resolution; verify/answer/explain
integration; synthetic gate **23/23**; finite-domain quantifiers; extraction support;
`Inference` protocol; docs — §6, §7.4, §7.5, §8, §9, §10, §11, §12.1, §15, §16). The
**ProntoQA-OOD tier-a live gate is green** (**41/42 (97.6%)**, 0 grounded false proofs);
the **FOLIO L2 live gate is extraction-bound** (26/44, no engine unsoundness; backlog
G1–G4 in `docs/quality_findings.md` §G). Recon narrowed the scope and added D-L2-7.
This document is the working plan for stage **L2** of `docs/reasoning_roadmap.md`; it
will be updated as the work proceeds.

Canonical language: English; Russian mirror: `docs/l2_plan_ru.md`. Related:
`docs/reasoning_roadmap.md` (§3 L2, §4–6), `docs/l1_plan.md` (precedent and stage
contract), `docs/prontoqa.md`, `docs/folio.md`, `docs/logic_layer.md`, `docs/task.md`,
`docs/implementation_plan.md` (§9).

## 1. Goal

Widen the class of decidable reasoning by adding the L2 formalism: clauses with
**disjunctive heads or bodies**, **existential quantifiers** (eliminated by
Skolemization inside the procedure), **case splits** and **proof by contradiction**.
Horn (L0/L1) is the special case. The LLM proposes a formalization in `L2`; a
**bounded resolution** procedure decides it. The design commitment is unchanged:
nothing enters the theory without a valid quote (`cited`) or an explicit hypothesis
tag (`hypothesis`); the LLM proposes, the engine decides.

Concretely, L2 must enable answers that are out of the current fragment:

- a conclusion from a **disjunctive rule head** (`A ∨ B ← C`), proved by **cases**;
- a conclusion that rests on a **disjunction inside a premise** or a De Morgan
  rewrite (`¬(A ∧ B) ⊢ ¬A ∨ ¬B`);
- a goal concluded by **proof by contradiction** (reductio), not present as a rule;
- an **existentially quantified** premise or goal (`∃x P(x)`), by Skolemization.

## 2. Scope and non-goals

- **In scope (first):** the compositional subset of ProntoQA-OOD — conjunctive and
  disjunctive **goals**, **disjunctive ground facts** with **case splits**, and
  **reductio/contrapositive**, over fictional ground individuals. Recon (§6) sizes it
  at 3266/5800 examples (56.3%).
- **In scope (second):** FOLIO as the second L2 gate (`docs/folio.md`), stratified by
  FOL construct; its L2 slice is 93/204 validation rows. FOLIO is where **`∃` is
  actually exercised** (76 rows); ProntoQA-OOD has **no existential** (0/5800), so the
  first-order/Skolem layer is a FOLIO gate, not a first-gate need. Only the in-fragment
  subset (atoms, `∀` implications, conjunction, negation, **disjunction**, **`∃`**) is
  scored; functions, equality and axiom schemas are reported `out_of_fragment`.
- **Out of scope:** full undecidable FOL. Entailment is only semi-decidable, so the
  search stays **bounded** and exhaustion is the honest `insufficient`/`budget`
  (`docs/reasoning_roadmap.md` L2 risk). Function terms (and equality outside the
  finite ground fragment) remain a later fragment decision, not a bug fix; finite
  equality itself landed as the named fragment `equality` (milestone 17,
  `docs/equality_plan.md`).
- **Out of scope:** L3 (CSP/SAT) and L4 (arithmetic) — separate engines.
- No full-collection runs (no free LLM access; §17).
- No NL heuristics: disjunction and quantifier structure are **structurally**
  extracted by the LLM, never detected with cue phrases or word lists
  (`docs/task.md` §3.8).

## 3. Guardrails (gating)

- **0 grounded false proofs** is the hard gate; every determinate answer must be
  `proven`. A new logic multiplies the ways an unsound proof can hide, so the
  synthetic soundness gate precedes any live run (`docs/reasoning_roadmap.md` §5).
- **Bounded search never guesses.** When the step budget is exhausted the answer is
  `insufficient`/`budget`, never a wrong `proven`/`refuted`.
- **Non-Horn input under a Horn-only configuration is `out_of_fragment`,** never
  silently mangled into Horn.
- **Provenance is mandatory.** Every resolution step and every case branch carries
  its premises, like any Horn derivation; `explain` is built only from real edges.
- **Benchmark semantics do not leak.** The logic fragment and the world assumption
  are set by the harness/query, never read off the wording (`docs/l1_plan.md`
  D-L1-4).
- **Horn/L2 parity.** The Horn-only consequences (transitive `is_a`, disjointness)
  are lowered into clauses (§9) and are not evaluated by the forward chain in L2, so
  the two engines must return the **same** verdict on Horn theories. A parity
  regression over `l1_synthetic` and the ProntoQA sample is part of the gate.
- **No OR-as-AND.** Logical disjunction is a first-class structural form; it is
  **never** lowered into concurrent (AND) facts. `ProblemStructure.variants`, which
  `build/unroll` currently appends to `morphisms` (`build/unroll.py:173`), must not
  be used for logical disjunction and must not silently become an AND (it is either
  the new disjunction form or `out_of_fragment`).
- **L2 is classical.** The L2 procedure reasons with classical negation only. The L1
  machinery (declared CWA / negation-as-failure) is **not** mixed into it: an
  unprovable atom stays `unknown` unless the query explicitly declares a closed
  world through the L1 path. Combining CWA with resolution is out of L2 scope.
- **No invented witnesses.** An existentially quantified goal is proved with a fresh
  witness; the answer reports a binding only when the witness is a named object,
  otherwise the fact of existence without a fabricated id (§11).

## 4. What L2 adds, and what already exists

Already present (usable as-is):

- the `Theory`/`Query` IR, the quote/hypothesis discipline, the hypothesis ledger,
  the guided cycle and proposal classification;
- `Facts`/`AtomStore` provenance (`premises` / `used` / `rule_index`) and the
  explanation renderer;
- `Status` already includes `budget` and `out_of_fragment`; `ExplanationKind` already
  includes `naf` and `constraint`;
- `Slot.variants` / `exclude`, which `build/unroll` expands into **alternative
  fillers** (separate morphisms). This is *not* logical disjunction; L2 leaves the
  filler semantics alone and adds a separate logical-disjunction form (§9). The
  current lowering of `ProblemStructure.variants` into `morphisms`
  (`build/unroll.py:173`) is a latent OR-as-AND hole that L2 closes.

Genuinely new for L2:

- a **clause IR** (disjunctive heads/bodies) alongside the Horn `Rule`;
- a **bounded resolution procedure** with an explicit step budget and proof
  recording, as a separate module (§8, D-L2-1);
- **Skolemization** of existentials and a **case-split** proof shape;
- extraction and explanation support for the above;
- the `ANKYRA_LOGIC` flag and a dispatch seam in `verify` (§13).

## 5. Benchmark and subset stratification

Both collections are heterogeneous, so a run must be **stratified by construct**:
the in-fragment subset is scored against the gate; everything else is reported
`out_of_fragment` and is not a failure.

- **ProntoQA-OOD (compositional).** Proof steps map to stages (`docs/prontoqa.md`
  §4): `AXIOM`, `ModusPonens`, `AndIntro`/`AndElim` are L0/L1; `OrIntro`/`OrElim`
  and `ProofByContra` are **L2**. Recon (§6) sizes this subset.
- **FOLIO.** Stratify by the FOL annotation (`docs/folio.md` §4): atoms, `∀`
  implications, conjunction, negation, **disjunction**, **`∃`** are in-fragment;
  functions, equality and axiom schemas are `out_of_fragment`. The gold-FOL
  diagnostic (`evals/folio_fol.py`) separates extraction error from logic error.

## 6. Step 0 — Recon (LLM-free)

First task, before any engine work. No LLM calls.

- Fetch ProntoQA-OOD (`github.com/asaparov/prontoqa` `main` +
  `generated_ood_data.zip`; HF `tasksource/prontoqa`) and tally the **proof-step
  shapes** over a few hundred examples to size the L2 compositional subset and the
  `OrIntro`/`OrElim`/`ProofByContra` distribution.
- FOLIO: extend the existing recon to count **disjunction** and **`∃`** constructs
  (§4) and size the in-fragment slice precisely.
- **Critical question:** is surface `or` (i) a disjunction of *propositional* atoms
  (ground, resolvable without unification), (ii) a disjunction of *class membership*
  atoms over `is_a`, or (iii) a disjunction of *object fillers* already covered by
  `Slot.variants`? The answer decides the first gate's scope (D-L2-4) and the schema
  shape (D-L2-3), and whether `∃` is actually exercised.
- Output: a recon report folded into `docs/prontoqa.md` and `docs/folio.md`, with
  subset sizes and the disjunction/`∃` verdict.

**Recon results (done, LLM-free).** Reproduce with
`uv run python -m evals.recon_l2` (`docs/prontoqa.md` §9, `docs/folio.md` §10).

- **ProntoQA-OOD:** 5800 `test_example`s over 58 files. `horn` 2534 (43.7%),
  `l2_decomp` (∧/∨ goal) 1993 (34.4%), `l2_reductio` 935 (16.1%),
  `l2_reductio+decomp` 338 (5.8%) — **L2 3266 (56.3%)**. Rule shapes: `AndElim`
  1200 horn, `AndIntro` 1400 ∧-goal, `ProofsOnly` 900 horn, `ModusPonens` 100 horn,
  `OrElim` 600 proof-by-cases, `OrIntro` 400 ∨-goal, `ProofByContra` 300 reductio+∧-goal,
  `Composed` 900 mixed.
- **Critical question answered:** surface `or` is over **class-membership/property
  atoms** (`is_a`) — in rule antecedents (Horn-splittable, 1211), in **ground facts**
  (600) and in **goals** (587). It is neither arbitrary propositional disjunction nor
  object fillers (`Slot.variants`).
- **`∃` is not exercised** by ProntoQA-OOD (0/5800). FOLIO's validation split has
  **76** existential rows and an L2 slice of **93/204**. The first-order/Skolem layer
  (milestone 8) is therefore gated by FOLIO, not by the first gate.
- **Scope correction:** ProntoQA-OOD needs (a) ∧-goal and ∨-goal decomposition (D-L2-7),
  (b) **disjunctive ground facts** with case split (not only disjunctive rule heads),
  and (c) reductio/contrapositive. It does not need quantifiers. This narrowed the plan
  and fixed the §9 modelling of disjunctive facts.

## 7. Semantics to add

### 7.1 Disjunctive heads

`A(x) ∨ B(x) ← C(x)` is a clause with two positive head literals. It is not
representable by a Horn rule; it is decided by **case analysis**: assume `¬A` in one
branch and `¬B` in the other, and refute each. Provenance records each branch.

### 7.2 Disjunctive bodies

`A(x) ← B(x) ∨ C(x)` is equivalent to the two rules `A←B` and `A←C`; the lowering
(§9) may split it. This is included for extraction fidelity and for mutual
recursion, not because it needs a new procedure.

### 7.3 Negation, De Morgan and reductio

Under L1 negation and the new disjunction, De Morgan rewrites (`¬(A∧B) ⊢ ¬A∨¬B`) and
**proof by contradiction** (negate the goal, derive the empty clause) become
available. These are properties of the procedure, never of the extraction: Phase 0
records the surface structure; the prover rewrites and searches.

### 7.4 Existential quantifiers

A premise `∃x P(x)` is Skolemized to a fresh constant/function during clausification;
a goal `∃x P(x)` is proved by negating it, introducing a witness, and refuting.
**Skolemization is not an extraction feature** (`docs/folio.md` §4): Phase 0 only
records which variable is quantified and its scope; the prover Skolemizes. M8
Skolemizes a conjunctive existential premise to a **fresh constant** (added to the
finite pool) and decides an existential/open goal by **witness enumeration** over the
pool. Function terms and existentials nested under universals are outside the committed
fragment (`unsupported`).

### 7.5 Boundedness

Entailment in FOL is semi-decidable. The resolution search carries an explicit step
budget; exhaustion yields `insufficient`/`budget` with the partial proof, never a
guess. The budget value is configurable (§13) and recorded in the verdict.

### 7.6 Disjunctive ground facts and compound goals

Recon (§6) shows the dominant non-Horn shapes are not disjunctive rule heads but:

- **disjunctive ground facts** (`A∨B∨C`, `OrElim`): the prover decides the goal by
  **case split** — assume each disjunct and prove the goal under it;
- **conjunctive goals** (`A∧B`, `AndIntro`/`ProofByContra`): `T ⊢ A∧B` iff each
  conjunct is proved (deterministic decomposition);
- **disjunctive goals** (`A∨B∨C`, `OrIntro`): proved by proving a disjunct; with a
  positive Horn theory this is complete (the least model decides each disjunct), and
  otherwise a missing disjunct is the honest `unknown`, never a fabricated proof.

The handling of compound goals is D-L2-7.

## 8. Engine changes (`engine/`)

`Rule`/`saturate`/`derive_closure` stay the Horn spine. L2 is a **separate
procedure** (D-L2-1) with its own modules:

- **`engine/clause.py`** — clausification: lower `Theory.rules` and the new clause
  IR into CNF; Skolemize existentials; keep a back-reference from each clause to its
  source rule/quote for provenance. **It also owns the Horn-only axioms**: transitive
  `is_a` (the standard two-clause schema) and the disjointness `Constraint`s become
  ordinary clauses here, so the Horn forward chain (`_close_is_a`,
  `_apply_constraints`, `engine/horn.py:425–473`) is not invoked on the L2 path and
  the two engines cannot silently diverge.
- **`engine/resolution.py`** — the bounded refutation prover: unification, binary
  resolution (with factoring where needed), an explicit step budget, and a recorded
  proof DAG (resolvent → parent clauses → source). Clause normalization (tautology
  deletion, subsumption) and, on the ground fragment, unit propagation run before
  case splits, to keep the search small.
- **`engine/verify.py`** — dispatch: when `ANKYRA_LOGIC` is enabled the L2 procedure
  decides; otherwise the Horn path runs and a **non-Horn clause in the theory is
  reported `out_of_fragment`** (never lowered silently). The L2 verdict reuses
  `Status` (`supported`/`refuted`/`insufficient`/`budget`/`out_of_fragment`).
- **`engine/explain.py`** — render resolution proofs as `ExplanationStep`s: new
  kinds (`case`, `resolution`, and a Skolem step if needed), ordered premises → goal;
  a case split renders both branches; the proof DAG is cut to the parent chains that
  the goal actually uses (as `_trace` already does for `premises`).
- **`engine/answer.py`** — map the new verdicts to `Answer` kinds; largely unchanged.
- **`engine/classify.py`** — the proposal loop is the one place where `_adds_new_facts`
  (`engine/classify.py:35`) calls the Horn closure directly. **D-L2-6: L2 decisions
  run in wave 0 with proposals disabled** until the `Inference` protocol lands
  (milestone 10); this keeps the first L2 gates deterministic and comparable to
  ProntoQA. The protocol extraction then routes `classify` through the same decision
  procedure as `verify`.

Termination: the search is bounded by (clauses × steps); no unbounded loop.

**Implemented (M3).** `engine/clause.py` lowers a theory into ground clauses
(axioms → units; rules → ``¬body ∨ head…`` per grounding; transitive `is_a` and
`Constraint`s → clauses; unsafe rules and builtins → `unsupported`).
`engine/resolution.py` is the bounded refutation: **set-of-support** binary resolution
(only clauses descended from the negated goal drive new resolvents) with tautology
filtering and subsumption, an explicit step budget (default 10000,
`ANKYRA_LOGIC_BUDGET`), and a recorded proof DAG (`Proof.nodes` / `Proof.origins`,
`Proof.derivation()`); statuses are `entailed`, `not_entailed`, `budget`,
`unsupported`. Ground/propositional only (D-L2-4); the first-order layer (unification,
Skolemization) is M8. Tests: `tests/test_engine_resolution.py`.

**Unit propagation (T6).** `refute_support` first resolves every unit clause to a
fixpoint (T6, `docs/t6_plan.md`), each step a real binary resolution recorded in the
proof DAG and counted against the same budget; the general set-of-support loop then
runs on the simplified set. This is the "unit propagation run before case splits"
named above and removes the `G4` budget misses without changing the procedure or the
flag.

## 9. Data model and extraction schema

Decided in D-L2-3: **extend `Rule`**, do not add a second `Clause` model.

- `core/models.py`: `Rule` gains an optional **disjunctive head** (`head:
  list[Morphism]`; today's single `consequence` is the one-element case). A
  **disjunctive body is not stored**: `A ← B ∨ C` is split into two rules during
  lowering, so only the non-Horn head needs a new field. Horn rules remain the stored
  form; clausification is a lowering step owned by `engine/clause.py`, not a second
  copy of the knowledge.
- `core/models.py`: `ExplanationKind` gains `case` / `resolution` (and a Skolem kind
  if the renderer needs it); a parent-clause edge structure for the resolution proof
  is carried alongside (or extends `ExplanationStep`), since `Fact.premises` /
  `rule_index` are Horn-specific.
- `core/schemas.py`: structural forms for a **disjunctive head** (a list of
  alternative atoms), a **disjunctive body**, a **disjunctive ground fact** and an
  **existentially quantified atom/variable**. These are *logical* forms, distinct
  from `Slot.variants` (object fillers). A disjunctive ground fact **is in-fragment**
  (recon: ProntoQA-OOD `OrElim` supplies `A∨B∨C` as a fact and the prover cases over
  it), so it is represented as a clause, never as a set of concurrent facts.
- `core/schemas.py` + `core/models.py` (existentials): `StructExistential` and
  `ProblemStructure.existentials` compile to `Theory.existentials` (`Existential`);
  the prover Skolemizes. `enrich`/`symbolic` carry and ground-check them.
- `core/models.py` and `core/schemas.py` (goals): recon shows the question target may
  be a **conjunction** (`AndIntro`, `ProofByContra`) or a **disjunction** (`OrIntro`).
  D-L2-7 decides how the goal is represented: a goal **formula** (∧/∨ over atoms) or a
  deterministic decomposition into one target per conjunct/disjunct before the prover.
- `build/unroll.py`: lower the new structure into rules/CNF; split disjunctive bodies
  into rules; **use every head alternative** (the current
  `consequents[0]` at `build/unroll.py:184–187` drops the rest and must be fixed);
  stop appending `ProblemStructure.variants` to `morphisms` as AND-facts
  (`build/unroll.py:173`). Transitive `is_a` and `constraints` stay in the theory and
  are lowered to clauses by `engine/clause.py`.

**Implemented (M2).** The clause IR is in place:

- `Rule.alternatives` (+ `head`/`is_horn` properties); a conditionless rule with
  alternatives is a disjunctive ground fact.
- `Query.goals` + `Query.goal_mode` (`single`/`all`/`any`).
- `StructRule.consequents` (disjunctive head), `StructRule.disjunctive_antecedent`
  (OR-body, split into one rule per disjunct), `StructDisjunction` +
  `ProblemStructure.disjunctions` (disjunctive ground facts),
  `QuestionStructure.ask_all`/`ask_any` (compound goals).
- `unroll` compiles all of the above; `ProblemStructure.variants` now compiles to a
  disjunctive clause, never concurrent facts (OR-as-AND closed).
- The Horn guard: `engine/horn.has_non_horn` and `_fire_rules` skips non-Horn rules
  (deriving the first disjunct would be unsound); `defeasible` skips them too;
  `verify` reports `out_of_fragment` for non-Horn input and compound goals until the
  L2 procedure lands (M4).
- Deliberate note (updated in M9): a single `consequent` whose slot `set` (AND)
  expands to several morphisms is now split into **one rule per conjunct** (the old
  first-only behaviour dropped conjuncts); the disjunctive path is
  `consequents`/`disjunctions`/`variants`.

## 10. Phase 0 extraction (`build/extract.py`)

- `PROBLEM_SYSTEM` / `QUESTION_SYSTEM`: teach the structural forms for a disjunctive
  conclusion ("X is either A or B"), a disjunctive condition, and an existential
  statement, each with one verbatim quote; no cue-phrase lists, no word-level
  heuristics.
- A yes/no question is still extracted as a positive ask; proof by contradiction is
  the prover's job, not the extractor's.
- A conditional inside a question keeps the existing treatment (conditions → Gamma).

## 11. verify / answer / explain

- `verify`: under `ANKYRA_LOGIC`, run the bounded resolution procedure and map the
  outcome (entailed → `supported`, refuted → `refuted`, budget exhausted →
  `insufficient`/`budget`, out-of-fragment construct → `out_of_fragment`). Without
  the flag, behavior is unchanged and a non-Horn clause is `out_of_fragment`.
- `answer`: `supported` → `yes` (yes/no) as today; `refuted` → `no`; budget/
  insufficient → `unknown`. No silent answers.
- `answer`, existential goal: a proof of `∃x P(x)` yields a fresh witness; the
  binding is reported **only when the witness is a named theory object**, otherwise
  the answer states existence without a fabricated id (guardrail "no invented
  witnesses").
- `explain`: a case-split proof shows both branches; a reductio shows the negated
  assumption and the empty clause. Every step maps to a real resolution edge or a
  source rule/quote.

**Implemented (M4).** `verify` dispatches on `ANKYRA_LOGIC`: off → the Horn/L1 path
(unchanged); on and ground goals → `_verify_l2`, which clausifies with Gamma as
assumptions, decides each goal (and its complement) by bounded resolution, combines
∧/∨ goals (`all`/`any`), maps `entailed → supported`, `complement → refuted`, both →
`contradiction`, budget → `insufficient` + `logic_budget:` gap, unsupported construct
→ `out_of_fragment`; an unused question condition still yields `insufficient`. A
closed-world NAF theory under L2 is `out_of_fragment:naf_in_l2` (CWA is not mixed in).
`explain` renders the resolution DAG with the new `resolution` steps (input clauses map
to `axiom`/`rule`/`constraint`/`is_a`/`assumption`, resolved clauses to `resolution`);
a contradiction shows both branches. `answer` is unchanged (`refuted` now carries the
`target_refuted:` gap). Tests: `tests/test_engine_logic_l2.py`.

## 12. Eval harnesses (`evals/`)

### 12.1 Synthetic collection — **primary** (LLM-free, structural)

- `evals/build_l2_synthetic.py` → `evals/data/l2_synthetic.jsonl`. Each case is a
  fully structured theory/query pair with an independently written expected verdict
  and a `mechanism` tag. No LLM, no natural language in the primary set.
- `evals/l2_synthetic.py` — runner: builds `Theory`/`Query` directly, calls
  `verify` / `build_answer`, reports the gate, non-zero exit on any mismatch
  (mirrors `evals/l1_synthetic.py`).
- Coverage: disjunctive head + case split; disjunctive body; De Morgan;
  proof by contradiction; conjunctive/disjunctive **goals** (D-L2-7); disjunctive
  ground fact with case split; existential premise and goal; budget exhaustion;
  `out_of_fragment` for functions/equality. **Negative controls are mandatory**: a
  Horn-only configuration must not consume a disjunctive clause; an exhausted budget
  must not yield `proven`; soundness must not depend on the flag.

### 12.2 ProntoQA-OOD compositional — first live gate

- `evals/build_prontoqa_ood_sample.py` — deterministic, stratified by proof shape,
  committed as `evals/data/prontoqa_ood_tier_*.jsonl`.
- `evals/prontoqa_ood.py` — adapter mirroring `evals/prontoqa.py`, with an
  `out_of_fragment` bucket.
- Gate: 0 grounded false proofs; determinate all `proven`; kind accuracy ≥95% in
  fragment.
- **Live result (tier a, `--jobs 5`): GREEN.** 42 scored targets: **41/42 (97.6%)**,
  **0 grounded false proofs**, every supported/refuted answer `proven`; 2 no-target
  (unknown) and 1 honest `contradiction` (an inconsistent extracted theory). Two
  defects were fixed to get there: `verify` no longer downgrades a proved goal when
  its complement times out, and the adapter scores compound goals by the whole claim.

### 12.3 FOLIO — second live gate

- Extend `evals/build_folio_sample.py` and `evals/folio.py` with L2 constructs;
  stratify by construct (`docs/folio.md` §4). The `evals/folio_fol.py` gold-fed mode
  is the diagnostic that separates fragment from extraction. Budgeted (§17).

## 13. Config and flags

- `ANKYRA_LOGIC` (`off` | `ground` | `fol`, default `off`) in settings and
  `.env.example`. `off` keeps the Horn spine and reports non-Horn input
  `out_of_fragment`; the harness sets the level, never the wording.
- The resolution **step budget** is a separate setting (e.g.
  `ANKYRA_LOGIC_BUDGET`), recorded in the verdict. Benchmark semantics never leak
  into the engine.

## 14. Tests

- `tests/test_core_clause.py`: the clause IR (`Rule.alternatives`/`head`/`is_horn`,
  `Query.goals`/`goal_mode`).
- `tests/test_build_disjunction.py`: lowering of disjunctive heads, disjunctive
  bodies, disjunctive ground facts and compound goals; `variants` no longer becomes
  AND-facts; the Horn engine skips a disjunctive rule; `verify` reports
  `out_of_fragment` for non-Horn input and compound goals.
- `tests/test_engine_resolution.py` (M3+): disjunctive head by cases; disjunctive
  body; De Morgan; proof by contradiction; `∃` premise and goal; budget exhaustion →
  `insufficient`/`budget`; non-Horn input under `ANKYRA_LOGIC=off` →
  `out_of_fragment`.
- `tests/test_build_disjunction.py`: structure → clause IR lowering; every head
  alternative survives; `ProblemStructure.variants` no longer becomes AND-facts.
- `tests/test_evals_l2_synthetic.py` / `tests/test_evals_prontoqa_ood.py`: the
  synthetic gate and adapter scoring.
- `tests/test_logic_parity.py`: on Horn theories (`l1_synthetic` plus the ProntoQA
  sample, including `is_a` transitivity and disjointness) the L2 engine returns the
  **same verdict** as the Horn engine (guardrail "Horn/L2 parity").
- Full regression: `uv run pytest` (offline; live tests skipped).

## 15. Documentation updates

- `docs/prontoqa.md`: OOD recon results, subset sizes, gate numbers, L2 status.
- `docs/folio.md`: L2 construct stratification and results.
- `docs/reasoning_roadmap.md`: L2 status and any change to the stage contract.
- `docs/implementation_plan.md`: backlog/milestones entries.
- `docs/logic_layer.md`: when the `Inference` protocol is extracted (D-L2-2).
- This document, kept current as the plan evolves.

## 16. Work order (milestones)

1. ~~Recon (LLM-free) and the disjunction / `∃` verdict (§6).~~ **DONE**;
   narrowed scope, added D-L2-7.
2. ~~Data model, clause IR, schema, builder plumbing (§9); unit tests (`D-L2-3`).~~
   **DONE** (`tests/test_core_clause.py`, `tests/test_build_disjunction.py`); the Horn
   guard reports non-Horn input `out_of_fragment`.
3. ~~`engine/clause.py` + `engine/resolution.py`: ground/propositional bounded prover
   with proof recording; LLM-free tests (`D-L2-4`).~~ **DONE**
   (`tests/test_engine_resolution.py`).
4. ~~`verify` / `answer` / `explain` integration behind `ANKYRA_LOGIC`; unit tests.~~
   **DONE** (`tests/test_engine_logic_l2.py`).
5. ~~Synthetic structural collection + runner (`evals/l2_synthetic`) and the L2 gate.~~
   **DONE — green** (19/19 initially; extended to **23/23** by M8/M9)
   (`evals/build_l2_synthetic.py`, `evals/l2_synthetic.py`,
   `tests/test_evals_l2_synthetic.py`).
6. ProntoQA-OOD compositional builder + adapter; budgeted live gate. **DONE** —
   harness (LLM-free: `evals/build_prontoqa_ood_sample.py`, `evals/prontoqa_ood.py`,
   44-problem tier a, `tests/test_evals_prontoqa_ood.py`) and **live tier a GREEN**
   (**41/42 (97.6%), 0 grounded false proofs**).
7. FOLIO L2 slice builder + adapter; budgeted live gate (gold-fed diagnostic).
   **Harness DONE** (LLM-free: `evals/build_folio_sample.py --subset l2` commits
   `folio_l2_tier_a.jsonl` — 45 problems, 15/label; `evals/folio.py` gained
   `--subset`/logic; `tests/test_evals_folio.py`). **Live gate (tier a)**: 26/44
   scored, extraction-bound (6 `out_of_fragment`, 9 no target, 12 `insufficient`),
   **no engine unsoundness** — the proven-but-wrong cases are extraction collapses
   (universal/conditional conclusions as ground atoms). The gold-fed diagnostic parser
   is still L1-only (extending it to `∨`/`∃` is a follow-up).
8. First-order layer: quantifiers, unification, existential goal witnesses; extend
   the synthetic gate. **Gated by FOLIO** (`∃`), not by ProntoQA-OOD (§6).
   **DONE (finite-domain form).** Quantifiers are handled by clausification plus
   witness enumeration: `∃` premises are Skolemized to fresh constants added to the
   pool; open/`∃` goals are decided by enumerating the finite pool (a propositional
   ✕ first-order trade-off that keeps `not_entailed` terminating — see §8). Full
   first-order **unification** is deferred: a prototype diverges on `not_entailed`
   queries (semi-decidability), which would turn honest negatives into `budget`; the
   committed collections are over finite named domains where grounding is sound and
   complete. `Theory.existentials` + witness enumeration + `tests/test_engine_logic_l2.py`
   and the synthetic `existential`/`open_goal` mechanisms land here.
9. Extraction support for disjunction and existentials (`build/extract.py`).
   **DONE.** `PROBLEM_SYSTEM` teaches `consequents` (disjunctive head),
   `disjunctive_antecedent` (OR-body), `disjunctions` (disjunctive ground fact) and
   `existentials`; `QUESTION_SYSTEM` teaches `ask_all`/`ask_any` (compound goals); the
   theory context renders the new forms. The conjunctive-conclusion lowering is fixed
   (one rule per conjunct). Tests: `tests/test_build_extract.py`,
   `tests/test_build_disjunction.py`.
10. ~~Extract the `Inference` protocol as an isolated change (D-L2-2).~~ **DONE** —
    `engine/inference.py` (`Inference`, `HornInference`, `ClausalInference`,
    `select_inference`); `verify` delegates through it and `classify` uses the Horn
    closure. `docs/logic_layer.md` §10; tests: `tests/test_engine_inference.py`.
11. ~~Documentation and status updates.~~ **DONE** — plan, roadmap, implementation
    plan, collection notes, `quality_findings` §G (FOLIO backlog) and `README` are
    current.
12. **Tier-1 lowering — T1 DONE** (`docs/coverage_ceiling.md` §6–§7,
    `docs/t1_plan.md`). A conjunctive existential conclusion with a shared witness
    `∃x (A(x) ∧ B(x))` is a **joint `all` goal**: one witness assignment for every
    conjunct (`verify._conjunctive_outcome`), the negative check per witness
    (`resolution.refute_conjunction`), and a merged proof for `explain`. Feature
    `shared_witness` (`engine/inference.py`), no new flag; the gold parser no longer
    refuses the shape. FOLIO L2 tier a gold-fed `out_of_fragment` 24→20, gold-fed
    17→**21/45**, coverage 21→**25/45**, covered 21/25, 0 grounded false proofs.
    Remaining Tier-1 items (T2–T6) stay open in `docs/coverage_ceiling.md`.
13. **Tier-1 lowering — T3 DONE** (`docs/coverage_ceiling.md` §6–§7,
    `docs/t3_plan.md`). A universal clause goal `∀x (l₁ ∨ … ∨ lₙ)`, subsuming
    `∀x (A→B)` and `¬∃x φ`, is `Query.goal_mode="forall"`: **supported** by refuting
    the negated clause at a **fresh constant** (universal generalization; `clausify`
    gained an `extra_pool` and `verify._universal_outcome`), **refuted** by one named
    witness (`resolution.refute` per literal, merged for `explain`). Feature
    `universal_goal` (`engine/inference.py`), no new flag; the gold parser no longer
    refuses the shape. FOLIO L2 tier a gold-fed `out_of_fragment` 20→18, gold-fed
    21→**23/45**, coverage 25→**27/45**, covered 23/27, 0 grounded false proofs.
    `evals.l2_synthetic` 36/36, `evals.routing_synthetic` 14/14. **T-D3 resolved:**
    one `clausal` capability with per-item named fragments and synthetic gates.
14. **Tier-1 lowering — T5 DONE** (`docs/coverage_ceiling.md` §6–§7,
    `docs/t5_plan.md`). A head-only universal premise `∀x (l₁ ∨ … ∨ lₙ)` (and Horn
    `∀x A(x)`, and a body rule with an extra head variable) grounds the head-only
    variable over the **individual domain** `D_ind` = pool \ `is_a` objects
    (`clause._individual_pool`, `_groundings`); body variables keep the full pool.
    This resolves **T-D1**: class names are lowered unary predicates, not elements of
    the universe, so instantiating there would fabricate proofs and block refutations.
    Feature `head_only_rule` (`engine/inference.py`), no new flag. FOLIO L2 tier a
    gold-fed `out_of_fragment` 18→**6**, gold-fed 23→**35/45**, coverage 27→**39/45**,
    covered 35/39, 0 grounded false proofs. `evals.l2_synthetic` 41/41,
    `evals.routing_synthetic` 15/15. Remaining Tier-1: T4 (2 rows), T2 (3 rows).
15. **Tier-1 lowering — T4 + T2 DONE** (`docs/coverage_ceiling.md` §6–§7,
    `docs/t4_t2_plan.md`). **T4:** a general **ground** goal formula is
    `Query.goal_clauses` (its CNF) with `goal_mode="cnf"` — supported when `T ∪ {¬φ}`
    is unsatisfiable, refuted when `T ∪ {φ}` is (`verify._cnf_outcome`,
    `resolution.refute_support`); this resolves **T-D2**. **T2:** an existential
    premise with a nested disjunction is a CNF body (`Existential.disjunctions`),
    Skolemized clause by clause (`clause._add_existentials`). Features `clause_goal`
    and `existential_disjunction` (`engine/inference.py`), no new flag. FOLIO L2 tier
    a gold-fed `out_of_fragment` 6→**1** (only the malformed `0109`), gold-fed
    35→**40/45**, coverage 39→**44/45**, covered 40/44, 0 grounded false proofs.
    `evals.l2_synthetic` 52/52, `evals.routing_synthetic` 17/17.
16. **Tier-1 lowering — T6 DONE** (`docs/coverage_ceiling.md` §6–§7,
    `docs/t6_plan.md`). Ground unit propagation: a fixpoint before the set-of-support
    loop in `resolution.refute_support`, each propagation a real binary resolution
    recorded in the proof DAG, sharing the step budget; an empty resolvent is the
    refutation. It removes the G4 budget misses without a new procedure or flag (no
    new `FragmentFeature`). FOLIO L2 tier a gold-fed: `0009`/`0010` decided, gold-fed
    40→**42/45**, covered 40/44→**42/44**, `out_of_fragment` **1** (malformed `0109`),
    0 grounded false proofs. `evals.l2_synthetic` 56/56, `evals.routing_synthetic`
    17/17; pytest 480 passed. Tier-1 is complete.
17. **Tier-2 item 3a — finite equality DONE (synthetic only)**
    (`docs/equality_plan.md`). The reserved `eq` predicate enters as a named fragment on
    the clausal procedure: an asserted unit ground equality builds a union-find
    partition, terms are canonicalized (substitution), and reflexivity plus
    unique-names units are added over the individual domain (declared finite named
    domain, EQ-D2). `FragmentFeature "equality"`, refusal `out_of_fragment:equality`,
    no new flag. It moves no FOLIO number (FOLIO v0 has no equality; v2's is entangled
    with multi-variable quantification / nested `∃`). `evals.l2_synthetic`
    56→**65/65**, `evals.routing_synthetic` 17→**19/19**; pytest **505 passed**. Item
    3b (functions) stays deferred.

Each milestone lands reviewable on its own; no milestone starts on a red soundness
gate. Milestone 5 gates 2–4; milestone 3 (Horn path untouched) can proceed while the
protocol extraction (10) is deferred.

## 17. Budget

No free LLM access; tokens are paid out of pocket. Each live gate enters with a
small committed sample (ProofWriter Tier A order of magnitude), built
deterministically without LLM calls, run once and re-run only on a mismatch;
`ANKYRA_EXTRACT_SAMPLES=1`. ProntoQA-OOD and FOLIO live runs are separate, explicitly
budgeted decisions; the synthetic gate must not wait on them.

## 18. Decisions

D-L2-1 … D-L2-7 are **DECIDED**. Each entry keeps its background, options,
trade-offs and recommendation for the record. A new decision is opened here as it
arises; the plan must not proceed past a milestone affected by an open decision.

### D-L2-1 — The decision procedure

**Status: DECIDED — option (a).** A new **bounded resolution prover** as a separate
procedure (`engine/clause.py`, `engine/resolution.py`), behind `ANKYRA_LOGIC`. The
Horn spine (`saturate` / `derive_closure`) is left untouched.

**Background.** L2 needs a genuinely different procedure: clausal refutation with
case splits. The existing spine is forward-chaining Horn saturation.

**Options.**
- (a) A separate bounded-resolution procedure. Clean separation, keeps the Horn path
  readable, and gives full control over provenance for `explain`.
- (b) Extend the Horn engine with disjunction. Fewer modules, but the core becomes
  harder to read and the fixpoint semantics change.
- (c) An external prover (Z3 / a Prover9-class reference). Reuses a mature procedure,
  but yields no provenance, so `explain` and the hypothesis accounting cannot be
  built mechanically.

**Trade-offs.** (a) is more code but preserves the design commitment (mechanical,
auditable proofs) and the minimal-diff rule for the core; (b) risks the spine; (c)
breaks explainability.

**Recommendation / decision.** (a).

### D-L2-2 — Extract the `Inference` protocol now or after L2

**Status: DECIDED — option (b), extended.** Land a **working L2** first, behind an
isolated dispatch in `verify`; then extract the `Inference` protocol
(`docs/logic_layer.md`) as a separate, isolated change. The protocol extraction is
milestone 10, after the synthetic gate is green.

**Background.** `docs/l1_plan.md` D-L1-3 deferred the protocol until functional L1
was green (it is), and `docs/logic_layer.md` §9 ties the extraction to that point.
The roadmap §6 also names L1/L2 as the reason for the seam. But L2 itself is the
largest single diff in the roadmap.

**Options.**
- (a) Extract the protocol first; implement L2 as a second `Inference`.
- (b) Implement L2 behind an isolated dispatch, then extract the protocol as a
  separate change once L2 is green.
- (c) Do not extract the protocol at all for now.

**Trade-offs.** (a) is architecturally cleaner but front-loads a large refactor
before the second procedure is proven; (b) keeps L2 reviewable at the cost of a
later, small refactor; (c) risks the seam becoming a tangle.

**Recommendation / decision.** (b), with the protocol extraction explicitly scheduled
(milestone 10) so it is not dropped.

### D-L2-3 — Clause IR: extend `Rule` or add `Clause`

**Status: DECIDED — option (a).** Extend `Rule` with an optional **disjunctive
head**; a disjunctive body is split into rules during lowering. Clausification is
owned by `engine/clause.py` and lowers the Horn-only axioms (`is_a` transitivity,
`Constraint`s) too. One stored representation; no second copy of the knowledge.
**Recon correction:** a **disjunctive ground fact** (`A∨B∨C`) is *in-fragment* — it is
the `OrElim` premise — so it is stored as a clause and cases over it, not reported
`out_of_fragment` (this refines the earlier draft note).

**Background.** `Rule` is a Horn clause (`conditions` AND → single `consequence`).
L2 needs disjunctive heads/bodies. A second representation risks divergence from the
Horn one.

**Options.**
- (a) Extend `Rule` with optional disjunctive head/body fields; Horn stays the
  degenerate case. One stored form; clausification is a lowering step.
- (b) Add a separate `Clause` model and `Theory.clauses`, converted from `Rule`.
  Closer to resolution, but two representations of the same knowledge.

**Trade-offs.** (a) is a smaller, safer diff and avoids divergence; (b) is more
faithful to the procedure but duplicates knowledge and invites drift.

**Recommendation / decision.** (a), with clausification owned by `engine/clause.py`.

### D-L2-4 — First gate scope: ground-first or full FO

**Status: DECIDED — option (a).** Ground/propositional first (milestones 2–6),
first-order layer second (milestones 7–8). If recon (§6) shows the OOD disjunction is
not ground, the split moves but the order stands.

**Background.** ProntoQA-OOD compositional examples are over ground fictional
individuals; FOLIO needs real quantifier reasoning. Ground/propositional resolution
is far smaller than first-order resolution with unification.

**Options.**
- (a) Ground/propositional first (milestones 2–6), first-order layer second
  (milestones 7–8). De-risks the prover and lands a gate early.
- (b) Full first-order resolution from the start; one procedure for both gates.

**Trade-offs.** (a) delivers the ProntoQA-OOD gate sooner and isolates the hardest
part; (b) is one implementation but front-loads the risk and delays any gate.

**Recommendation / decision.** (a), unless recon (§6) shows the OOD disjunction is
not ground.

### D-L2-5 — Where the fragment/flag semantics live

**Status: DECIDED — option (a), extended.** `ANKYRA_LOGIC` (`off` | `ground` | `fol`)
is a run-wide config level set by the harness, plus the automatic `out_of_fragment`
when a non-Horn clause is present under `off`. Revisit a per-query `Query.logic`
(option (b)) only if a single run must mix fragments.

**Background.** `ANKYRA_NEGATION_MODE` is a config default with a per-query
override (`Query.world_assumption`), because CWA is a per-query semantic choice
(`docs/l1_plan.md` D-L1-4). L2's fragment/budget is analogous but coarser: it is a
property of the theory's logic, not of the query alone.

**Options.**
- (a) Config only (`ANKYRA_LOGIC` as a run-wide level); the harness sets it.
- (b) Per-query `Query.logic` (like `world_assumption`), set by the deterministic
  builder from config, never by the LLM.
- (c) On `Theory` (the clauses themselves already signal non-Horn).

**Trade-offs.** (a) is simplest and matches "benchmark sets semantics"; (b) is the
most precise and lets one run mix problems, mirroring L1; (c) conflates knowledge
with a procedure choice.

**Recommendation / decision.** (a) for the level, plus the automatic
`out_of_fragment` when a non-Horn clause is present under `off`; revisit (b) only if a
run must mix fragments.

### D-L2-6 — The proposal cycle under L2

**Status: DECIDED — option (a).** L2 decisions run in **wave 0 with proposals
disabled** until the `Inference` protocol is extracted (D-L2-2, milestone 10). This
keeps the first L2 gates deterministic and comparable to the Horn gates, and avoids
the `classify._adds_new_facts` coupling (`engine/classify.py:35`), which calls the
Horn closure directly.

**Background.** `_adds_new_facts` classifies a proposal by comparing Horn closures.
Under L2 a proposal whose effect is visible only to resolution would be
misclassified (`derivable` instead of `cited`) and the cycle would be unstable.

**Options.**
- (a) Wave 0 only (proposals disabled) until the protocol lands.
- (b) Add an `entails`-style dispatch now and route `classify` through the L2
  procedure immediately.

**Trade-offs.** (a) is the smallest, safest diff and keeps the first gates
deterministic, at the cost of deferring L2 proposal cycles; (b) is more complete but
front-loads part of the protocol refactor and enlarges the first L2 diff.

**Recommendation / decision.** (a); (b) is subsumed by milestone 10.

### D-L2-7 — Compound goals (conjunctive / disjunctive)

**Status: DECIDED — option (a).** Decompose compound goals **deterministically**
before the prover: a conjunctive goal becomes one target per conjunct (all must be
proved), a disjunctive goal becomes a disjunction over proving a disjunct (any
disjunct suffices). No goal-formula representation is added to `Query`.

**Background.** Recon (§6) shows ProntoQA-OOD goals are often conjunctions (`AndIntro`
1400, `ProofByContra`) or disjunctions (`OrIntro` 400), which the single-Morphism
`Query.target` cannot express. `T ⊢ A∧B` iff both conjuncts; for a positive Horn
theory `T ⊢ A∨B` iff a disjunct is provable (the least model decides each disjunct),
so decomposition is sound and complete there.

**Options.**
- (a) Deterministic goal decomposition before the prover; keep `Query.target` a single
  atom. Small diff, sound; the answer is `yes` iff every conjunct / some disjunct is
  proved.
- (b) Add a goal formula (∧/∨ tree) to `Query.target` and let the prover handle it.
  More general, but a larger change to the query model, the proposal cycle and the
  answer mapping.
- (c) Treat compound goals as `out_of_fragment`, gate only single-atom goals. Smallest,
  but discards 34% of the OOD compositional set and misstates the roadmap's L2 scope.

**Trade-offs.** (a) covers the measured benchmark with a minimal model change and no
risk of unsound ∨-introduction; (b) is more faithful but front-loads an IR change; (c)
under-delivers. The completeness caveat of (a) for negation-heavy goals (a disjunct
provable only via reductio) is handled by the prover branch, not by the decomposition.

**Recommendation / decision.** (a), with the decomposition owned by the builder/verify
seam; revisit (b) only if FOLIO shows nested goals that decomposition cannot express.
