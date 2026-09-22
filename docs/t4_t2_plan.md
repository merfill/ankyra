# T4 + T2 Plan — non-flat ground goal and nested-disjunction existential premise

Status: **approved and implemented**. These are the last two items of the Tier-1
lowering backlog (`docs/coverage_ceiling.md` §6–§7). **T4** decides a non-flat
**ground** goal formula `φ` (`Cute ∧ Still → Turtle ∧ Skittish`,
`A ∨ B → C ∨ D`) and resolves the open decision **T-D2**. **T2** decides an
existential premise whose body has a nested disjunction
(`∃x (A(x) ∧ (B(x) ∨ C(x) ∨ …))`). Per `D-FE-3` both **reuse the existing bounded
clausal procedure** (`ANKYRA_LOGIC`): the work is IR/lowering, not new semantics.
Results are in §15.

Canonical language: English; Russian mirror: `docs/t4_t2_plan_ru.md`.

Related: `docs/coverage_ceiling.md` (the ordered backlog and T-D2), `docs/t1_plan.md`,
`docs/t3_plan.md`, `docs/t5_plan.md` (the per-item pattern this follows),
`docs/l2_plan.md` (the procedure both extend), `docs/folio_gold_fed.md` (the
measurement this follows), `docs/fragment_routing.md` (the named-fragment contract),
`docs/reasoning_roadmap.md`, `docs/implementation_plan.md` (§8 item 26).

## 1. Goal

Close the last two FOLIO L2 tier-a coverage gaps so the committed slice is decided
except one malformed annotation. Measured baseline (2026-09-22, after T1/T3/T5,
`uv run python -m evals.analyze_folio --subset l2`):

| verdict source | correct |
|---|---|
| text-fed | 25/45 |
| gold-fed open | 35/45 |
| gold `out_of_fragment` | 6/45 |
| covered (method) | 35/39 |
| covered (text) | 22/39 |

The 6 remaining `out_of_fragment` rows:

| id | label | first blocker | item |
|---|---|---|---|
| folio-validation-0006 | True | premise `∃x (GetMonkeypox(x) ∧ (Fever(x) ∨ …))` | **T2** |
| folio-validation-0007 | Uncertain | idem | **T2** |
| folio-validation-0008 | Uncertain | idem | **T2** |
| folio-validation-0073 | True | goal `GrowthCompanies’Stocks(kO) ∨ PriceVolatile(kO) → ¬Companies’Stocks(kO) ∨ ¬PriceVolatile(kO)` | **T4** |
| folio-validation-0020 | False | goal `Cute(rock) ∧ Still(rock) → Turtle(rock) ∧ Skittish(rock)` (premise already fixed by T5) | **T4** |
| folio-validation-0109 | False | stray `)` — malformed | — (data) |

Prototype (LLM-free, §9): T4 decides `0073`→`supported`/`yes` and `0020`→`refuted`/`no`;
T2 decides `0006`→`yes`, `0007`→`unknown`, `0008`→`unknown`. Together they are expected
to give coverage **44/45**, gold-fed **40/45**, `out_of_fragment` **1/45** (only `0109`),
covered gold-fed **40/44**, **0 grounded false proofs**.

## 2. Current blockers

### T4

- **Parser.** `_conclusion` (`evals/folio_fol.py:353–380`) refuses every non-flat,
  non-quantified conclusion outright:
  `raise FolParseError("compound conclusion is not a flat conjunction/disjunction")`
  (`evals/folio_fol.py:380`). `0073`/`0020` fall through to it after NNF.
- **IR.** `Query.goals` + `goal_mode` (`single | all | any | forall`,
  `core/models.py:23–27`) has no form for a general boolean combination of ground
  literals. `all` is each conjunct independently, `any` is a flat disjunction; neither
  is `(A∧B) → (C∧D)`.
- **The prover is already general enough.** `refute_support`
  (`engine/resolution.py:118`) accepts a *list* of assumed clauses, so
  `T ⊨ φ` is decidable as `T ∪ {¬φ}` unsatisfiable by placing the CNF of `¬φ` in the
  set of support. No new decision procedure is needed.

### T2

- **Parser.** `_existential_premise` (`evals/folio_fol.py:317–327`) requires the body
  to be a conjunction of literals:
  `raise FolParseError("existential premise is not a conjunction of literals")`. The
  body `GetMonkeypox(x) ∧ (Fever(x) ∨ …)` is not, so `0006/0007/0008` are refused.
- **IR.** `Existential` (`core/models.py:185–196`) carries only `atoms` (a conjunction
  of literals). There is no field for a disjunctive part of the body.
- **Clausification.** `_add_existentials` (`engine/clause.py:270–287`) emits one unit
  clause per atom over the Skolem constant; it cannot emit a disjunctive clause.

## 3. Scope and non-goals

**In scope.**
- **T4:** a **ground** boolean goal formula over literals (no quantifier, no free
  variable): `∀`-free implications between compounds, De Morgan combinations,
  conjunctions of clauses. Decided by the existing bounded resolution via the CNF of
  `φ` and of `¬φ`.
- **T2:** an existential premise `∃x φ(x)` whose body `φ` is a **CNF over literals in
  `x`** (a conjunction of unit and multi-literal clauses), e.g.
  `∃x (A(x) ∧ (B(x) ∨ C(x)))`. Skolemized to `A(sk) ∧ (B(sk) ∨ C(sk))`.
- The feature names, the synthetic gates and the routing controls; the gold-fed parser.

**Out of scope (unchanged, still `out_of_fragment`).**
- A goal formula with a **quantifier or free variable** (a `∀`/`∃` inside a compound
  goal); those stay the T1/T3 shapes or are refused.
- Nested quantifiers in an existential body, function terms, DNF-shape bodies beyond
  CNF (any propositional body is normalized to CNF; a quantifier inside is refused).
- The **live extraction wording** for a compound question or a nested-disjunction
  premise is the extraction track (G1–G4), not the method gates of T4/T2.
- No new flag, no new `.env` setting: the capability is the existing `clausal`
  (`ANKYRA_LOGIC`, off by default); `clause_goal` and `existential_disjunction` are
  derived `FragmentFeature`s, not procedures.
- No NL heuristics, no per-id tuning (`docs/task.md` §3.8;
  `docs/coverage_ceiling.md` §8).

## 4. T4 — construct and decision

### 4.1 Reading

`φ` is a propositional formula over **ground** literals (each atom is a named fact).
Classically, `T ⊨ φ` iff `T ∧ ¬φ` is unsatisfiable; `T ⊨ ¬φ` iff `T ∧ φ` is
unsatisfiable. Over the committed finite-domain clausal fragment these are exactly two
bounded resolution refutations.

### 4.2 Decision procedure (reusing bounded resolution)

Store the **CNF of `φ`** as `Query.goal_clauses: list[list[Morphism]]` (each inner list
a disjunction of literal Morphisms). Let `A(φ) = { frozenset(literal_of(l)) | l ∈ C }`
for each clause `C`.

- **supported** — `refute_support(clausification, CNF(¬φ))` derives the empty clause,
  where `CNF(¬φ)` is the cross-product of the negated literals of `goal_clauses`
  (`¬(C₁ ∧ … ∧ Cₘ) = ∨ᵢ ¬Cᵢ`, so each choice of one literal per clause gives the clause
  `{¬l₁, …, ¬lₘ}`).
- **refuted** — `refute_support(clausification, A(φ))` derives the empty clause.
- **contradiction** — both are entailed.
- otherwise **unknown**; an exhausted step budget is **budget** (`insufficient`, never
  a proof).

### 4.3 Why this is sound and general

- **Sound.** Both directions assume a formula and derive the empty clause; only a real
  resolution edge is recorded. `T ∧ ¬φ` unsat is the definition of `T ⊨ φ`, and the
  prover is sound (only an actual empty clause is `entailed`).
- **General.** Any propositional formula has a CNF, and the cross-product negation is
  exact, so the same two refutations decide every ground formula in the fragment.
- **The naive alternative is unsound, and rejected.** A recursive structural decision
  that reads `T ⊨ φ₁ ∨ φ₂` as `T ⊨ φ₁ or T ⊨ φ₂` is wrong (`T = {p ∨ q}` entails
  `p ∨ q` although neither disjunct). The unsat-based check is the correct one.
- **Bounded.** Each direction is one bounded resolution search; exhaustion is
  `insufficient`.

## 5. T4 design decisions

- **T4-D1 — Representation (resolves T-D2).** (a) `Query.goal_clauses: list[list[
  Morphism]]` holding the CNF of the ground goal, with `goal_mode="cnf"` and
  `Query.target = goal_clauses[0][0]` for echo/answer use; the parser lowers the gold
  formula to CNF. (b) A recursive `GoalFormula` model with NNF/CNF in the engine: more
  faithful rendering, but a new recursive model and a broader `Query`/engine change.
  (c) New `goal_mode` values: cannot express the shapes. **DECIDED (a)**; (b) recorded
  as the alternative.
- **T4-D2 — Decision.** (a) Two `refute_support` calls (§4.2): `CNF(¬φ)` for support,
  `A(φ)` for refutation. (b) A recursive structural entailment — **unsound** for `∨`.
  **DECIDED (a)**; (b) rejected.
- **T4-D3 — Fragment naming.** (a) Add a derived `clause_goal` `FragmentFeature`
  (`goal_mode == "cnf"`) mapped into the clausal fragment: an auditable name and a
  place for the routing control, no new capability/flag. (b) Reuse `compound_goal`.
  **DECIDED (a)** (mirrors T1-D3/T3-D3/T5-D3).
- **T4-D4 — Scope.** (a) **Ground** formulas only: no quantifier and no free variable
  anywhere in the goal. A quantified body inside a compound goal stays
  `out_of_fragment`. (b) Generalize to quantified sub-formulas — deferred (it is the
  goal-*formula* mixing T1/T3 with T4 and is not needed). **DECIDED (a).**

## 6. T2 — construct and decision

### 6.1 Reading

`∃x (A(x) ∧ (B(x) ∨ C(x)))` is Skolemized to `A(sk) ∧ (B(sk) ∨ C(sk))` — a unit clause
and a binary clause over one fresh constant. More generally, the body `φ(x)` is a CNF
over the literals in `x`, and each clause becomes a ground clause over `sk`.

### 6.2 Decision procedure

`_add_existentials` emits, for the `i`-th existential, a fresh `sk{i}` and the ground
clauses of `φ(sk{i})`: a unit clause per atom and one clause per disjunctive group.
The existing bounded resolution then decides any goal over the Skolem constant; no new
procedure.

### 6.3 Why this is sound and general

- **Sound.** Skolemization is satisfiability-preserving: the fresh constant appears
  nowhere else, so the emitted ground clauses are exactly the (Skolemized) existential.
- **General.** A CNF body covers every propositional combination of literals in `x`;
  `∃x ((A∧B) ∨ C)` is normalized to `∃x ((A∨C) ∧ (B∨C))` before Skolemization.
- **Bounded.** One fresh constant per existential; the clause set stays finite, and
  the step budget caps the search.

## 7. T2 design decisions

- **T2-D1 — Representation.** (a) Add `Existential.disjunctions: list[list[Morphism]]`
  (each inner list a disjunction of literals over the variable); `atoms` stay the unit
  clauses, so `atoms` + `disjunctions` is the CNF of the body. Backwards compatible
  (empty by default) and mirrors the `Rule.consequence`/`alternatives` naming.
  (b) Replace `atoms` with a single `clauses: list[list[Morphism]]` — cleaner name, but
  a broad churn across the builder, parser, symbolic checks and tests for no added
  expressiveness. **DECIDED (a)**; (b) recorded as the alternative.
- **T2-D2 — Decision.** Skolemize the CNF: one unit per atom, one ground clause per
  disjunctive group (§6.2). **DECIDED.**
- **T2-D3 — Fragment naming.** (a) Add a derived `existential_disjunction`
  `FragmentFeature` (an existential with a disjunctive part) mapped into the clausal
  fragment, no new capability/flag. (b) Reuse `existential`. **DECIDED (a)**
  (mirrors the T1/T3/T5 pattern).
- **T2-D4 — Body scope.** (a) One variable; the body is a CNF of literals in it
  (NNF then CNF); nested quantifiers and function terms stay `out_of_fragment`.
  (b) Generalize to nested quantifiers — deferred. **DECIDED (a).**

## 8. Engine changes

- **`core/models.py`.** `GoalMode` gains `"cnf"` (`core/models.py:23–27`); `Query`
  gains `goal_clauses: list[list[Morphism]]` (`core/models.py:242–262`); `Existential`
  gains `disjunctions: list[list[Morphism]]` (`core/models.py:185–196`), with
  `atoms` + `disjunctions` documented as the CNF of the body.
- **`engine/clause.py`.**
  - `_add_existentials` (`engine/clause.py:270–287`): emit a unit clause per atom and
    a ground clause per disjunctive group over `sk{i}` (skip a tautology).
  - `_class_names` (`engine/clause.py:127`): also scan `existential.disjunctions`
    (their `is_a` objects are class names for the T5 individual pool).
- **`engine/verify.py`.**
  - `_cnf_assumed(goal_clauses)` and `_cnf_assumed_negated(goal_clauses)` helpers
    (Units / cross-product of negated literals).
  - `_cnf_outcome(clausification, clauses, budget)` → `(outcome, target_result,
    complement_result, {})` per §4.2.
  - `_goals_of` (`engine/verify.py:269–274`) keeps returning the single anchor
    (`Query.target`) for `goal_mode == "cnf"`, so the clausal dispatch is selected; the
    `cnf` branch of `l2_outcomes` reads `goal_clauses` directly.
  - `l2_outcomes` (`engine/verify.py:570–597`): when `goal_mode == "cnf" and
    query.goal_clauses`, run `_cnf_outcome` and return one outcome; nothing else
    changes.
  - `_l2_status` (`engine/verify.py:469–497`): `"cnf"` maps the single outcome like
    `"forall"` (`supported→supported`, `refuted→refuted`, `contradiction`,
    `budget→insufficient`, `unknown→unsupported`).
  - `_verify_l2` (`engine/verify.py:532–567`): include `"cnf"` in the unused-premise
    check (its positive proof is a `refute_support` proof).
- **`engine/inference.py`.** Add `"clause_goal"` and `"existential_disjunction"` to
  `FragmentFeature` (`engine/inference.py:28`); `_has_clause_goal(query)` and
  `_has_existential_disjunction(theory)`; add both in `_fragment`
  (`engine/inference.py:116`). Routing is unchanged: `compound_goal`/`existential`
  already select `clausal`.
- **`engine/explain.py`.** `_goal_label` (`engine/explain.py:405`): render a cnf goal
  as `(l₁ OR l₂) AND (l₃)`; `_l2_explanation` already consumes `target.proof` /
  `complement.proof`.
- **`build/enrich.py`.** `_rewrite_existential` (`build/enrich.py:75–78`) also rewrite
  `disjunctions`; `_valid_existential` (`81–84`) accept a purely disjunctive body.
- **`build/symbolic.py` / `build/unroll.py` / `build/extract.py`.** Include
  `existential.disjunctions` where `existential.atoms` is scanned/rendered
  (`symbolic.py:217–218`; `unroll._unroll_existentials:272–288`; `extract.py:397–401`).
  Phase 0 extraction of the nested-disjunction shape is the **G-track**; `unroll`
  simply passes the field through when a `ProblemStructure` carries it.

## 9. Gold-fed parser (`evals/folio_fol.py`)

- **T4.** In `_conclusion` (`evals/folio_fol.py:353–380`), after NNF, when no shape
  above matches and the formula is **ground** (no `∀`/`∃` node, no free `_VARIABLES`
  term), compute its CNF (`_cnf`) and return `goal_clauses` with `goal_mode="cnf"`,
  `target = clauses[0][0]`. `_conclusion` returns a 4-tuple
  `(target, goals, goal_mode, goal_clauses)`; `to_theory_query`
  (`evals/folio_fol.py:403–434`) passes `goal_clauses` to `Query` and includes the
  clause atoms in `_object_names`. Replace the current flat refusal at line 380.
- **T2.** In `_existential_premise` (`evals/folio_fol.py:317–327`), NNF then CNF the
  body; split into `atoms` (unit clauses) and `disjunctions` (multi-literal clauses);
  raise `FolParseError` if a clause has a quantifier, an empty clause, or a term other
  than the existential variable. `_object_names` must include the disjunction atoms.

## 10. Synthetic gates

### `evals.l2_synthetic`

Add a `clause_goal` mechanism (T4) and an `existential_disjunction` mechanism (T2),
with mandatory controls. `_query` gains `goal_clauses=()` and `_theory` already
accepts existential dicts (now with `disjunctions`).

| case | theory / goal | expected |
|---|---|---|
| `clause-goal-01` | `A`, `B`, `A∧B→C`, `A∧B→D`; goal `(A∧B)→(C∧D)` | `supported`, `yes` |
| `clause-goal-02` | `A`, `B` only; goal `(A∨B)→C` | `insufficient` (**soundness control**: the unsound "flat ∨ of entailments" reading would say yes) |
| `clause-goal-03` | `A`, `B`, `¬C`; goal `(A∨B)→C` | `refuted`, `no` |
| `clause-goal-04` | `clause-goal-01` with `LOGIC_BUDGET=1` | `insufficient`, never proven |
| `clause-goal-05` | `clause-goal-01` under `logic="off"` | `out_of_fragment:compound_goal` |
| `exist-or-01` | `∃x(p(x) ∧ (q(x)∨r(x)))`, `p→¬r`; goal `q(sk0)` | `supported`, `yes` |
| `exist-or-02` | `∃x(p(x) ∧ (q(x)∨r(x)))`; goal `q(sk0)` | `unsupported`/`insufficient`, `unknown` |
| `exist-or-03` | `∃x(p(x) ∧ (q(x)∨r(x)))`, `p→q`; goal `¬q(sk0)` | `refuted`, `no` |
| `exist-or-04` | `exist-or-01` with `LOGIC_BUDGET=1` | `insufficient`, never proven |
| `exist-or-05` | `exist-or-01` under `logic="off"` | `out_of_fragment:existential` |
| `exist-or-06` | `exist-or-01` with an atom over a different free variable | `out_of_fragment` (a true nested quantifier is refused by the parser; `tests/test_evals_folio_fol.py`) |

Plus `routing_synthetic` cases asserting `clause_goal` and `existential_disjunction`
route to `clausal` when `ANKYRA_LOGIC` is on.

## 11. Tests and verification

Prototype (LLM-free, not committed): T4 decides `0073`→`supported` and
`0020`→`refuted`; T2 decides `0006`→`yes`, `0007`→`unknown`, `0008`→`unknown`; all six
match the labels. Expected combined gate:

| metric | baseline | expected |
|---|---|---|
| gold-fed open (correct) | 35/45 | **40/45** |
| gold `out_of_fragment` | 6/45 | **1/45** (only `0109`) |
| coverage (method) | 39/45 | **44/45** |
| covered gold-fed | 35/39 | **40/44** |
| grounded false proofs | 0 | **0** |

- `tests/test_engine_logic_l2.py`: cnf goal support/refutation/the budget control; the
  nested-disjunction existential support and its negative control; existing cases stay
  green.
- `tests/test_engine_resolution.py`: `refute_support` with a multi-clause assumption
  (`CNF(¬φ)`), and `_add_existentials` emitting a disjunctive Skolem clause.
- `tests/test_evals_folio_fol.py`: replace
  `test_conditional_compound_conclusion_is_out_of_fragment` with a parse test for
  `B(a)∧C(a)→D(a)∧E(a)` → `goal_mode="cnf"`; add a nested-disjunction existential
  parse test; update
  `test_gold_l2_shared_witness_with_a_nested_premise_is_fragment` (`0008` is now
  covered) to assert `not result["fragment"]` and the `Uncertain` answer.
- `tests/test_engine_inference.py` / `tests/test_evals_routing_synthetic.py`: the two
  features and their routing controls.
- `uv run pytest` (offline) — full regression.
- `uv run python -m evals.l2_synthetic` — new total, **0 mismatches**.
- `uv run python -m evals.routing_synthetic` — green.
- `uv run python -m evals.analyze_folio --subset l2` — LLM-free gold-fed re-measure:
  coverage up (to 44/45), `out_of_fragment` down (to 1/45), **0 grounded false proofs**.
  Record before/after in `docs/folio_gold_fed.md`.

## 12. Risks

- **T4 soundness is the `∨` direction.** An implementation that decides `φ₁ ∨ φ₂` by
  entailment of a disjunct (or that mis-negates the CNF) admits a false `yes`. The
  synthetic control `clause-goal-02` is the dedicated negative test; the gold-fed
  re-measure requires **0 grounded false proofs**.
- **CNF blow-up and cost.** The cross-product size is exponential in the number of
  clauses; the committed goals are tiny, and the step budget caps the search
  (exhaustion is `insufficient`).
- **T2 Skolem freshness.** One fresh constant per existential, not in the theory; a
  collision would be unsound. Assert uniqueness as T1/T3/T5 do.
- **Nested-quantifier leakage.** `∃x(p(x) ∧ ∃y q(x,y))` must raise, not be silently
  flattened. The synthetic control `exist-or-06` guards it.
- **Explanation fidelity.** A cnf goal renders its clause form; every step must still
  map to a real resolution edge.
- No full FOLIO live re-run without a separate budgeted decision
  (`docs/reasoning_roadmap.md` §4).

## 13. Work order (milestones)

1. Engine T4: `Query.goal_clauses`/`goal_mode="cnf"`, `_cnf_outcome`, `verify` wiring;
   unit tests. (Gates nothing live.)
2. Engine T2: `Existential.disjunctions`, `_add_existentials`, `_class_names`, the
   builder/symbolic scans; unit tests.
3. Synthetic `clause_goal` + `existential_disjunction` cases (soundness controls
   first); `evals.l2_synthetic` green.
4. `clause_goal` + `existential_disjunction` features and routing synthetic cases.
5. Gold parser + parser tests; LLM-free gold-fed re-measure; record the delta.
6. Docs: `coverage_ceiling.md` (T4/T2 done + numbers), `folio_gold_fed.md`,
   `l2_plan.md`, `reasoning_roadmap.md`, `implementation_plan.md` item 26;
   `docs/t4_t2_plan_ru.md` mirror.

Each milestone lands reviewable on its own; the soundness gates (step 3) precede the
gold-fed re-measure (step 5).

## 14. Guardrails

- Both constructs enter as **named fragments** (`docs/fragment_routing.md`); beyond the
  committed shape they stay an honest `out_of_fragment`.
- **Never lower the semantics to pass a row** (`docs/coverage_ceiling.md` §8): no
  deciding a disjunction by a disjunct, no dropping the nested disjunction.
- No per-id tuning; the LLM-free gold-fed bound is the free gate after each item:
  coverage up, **0 grounded false proofs**.

## 15. Results

Implemented (decisions T4-D1a…D4a and T2-D1a…D4a). LLM-free verification, 2026-09-22:

| gate | before | after |
|---|---|---|
| `evals.l2_synthetic` | 41/41 | **52/52** (`clause_goal` + `existential_disjunction`) |
| `evals.routing_synthetic` | 15/15 | **17/17** (two new features) |
| `uv run pytest` | 464 passed | **476 passed**, 26 skipped |

FOLIO L2 tier a, gold-fed (`uv run python -m evals.analyze_folio --subset l2`):

| metric | before | after |
|---|---|---|
| gold-fed open (correct) | 35/45 | **40/45** |
| gold `out_of_fragment` | 6/45 | **1/45** |
| coverage (method) | 39/45 | **44/45** |
| covered gold-fed | 35/39 | **40/44** |
| grounded false proofs | 0 | **0** |

T4 decided `0073` (`supported`/`True`) and `0020` (`refuted`/`False`); T2 decided
`0006` (`yes`/`True`), `0007` (`unknown`/`Uncertain`) and `0008`
(`unknown`/`Uncertain`). The only remaining `out_of_fragment` row is the malformed
annotation `0109`. The soundness controls `clause-goal-02` (a disjunction is not
decided by a disjunct) and `exist-or-02`/`exist-or-06` hold, and the gold-fed
re-measure has 0 grounded false proofs.
