# T3 Plan — universal / conditional / `¬∃` goal form

Status: **approved and implemented** (decisions T3-D1a…T3-D4a). This is the third
item of the Tier-1 lowering backlog (`docs/coverage_ceiling.md` §6–§7). T3 raises
**coverage** (not extraction) on FOLIO L2 by making a **universally quantified clause
goal** — `∀x (l₁(x) ∨ … ∨ lₙ(x))`, which subsumes `∀x (A(x) → B(x))`, `¬∃x φ(x)` and
`∀x (A(x) ∨ B(x))` — decidable by the committed clausal fragment. Per `D-FE-3` it
**reuses the existing bounded clausal procedure** (`ANKYRA_LOGIC`) and the T1
conjunction refutation: no new decision procedure, no new semantics. Results are in
§13.

Canonical language: English; Russian mirror: `docs/t3_plan_ru.md`.
Related: `docs/coverage_ceiling.md` (the ordered backlog and open decisions
T-D1…T-D3), `docs/t1_plan.md` (the shared-witness goal T3 mirrors), `docs/folio.md`
(§9–§10), `docs/folio_gold_fed.md` (the measurement this item follows),
`docs/l2_plan.md` (the procedure T3 extends), `docs/fragment_routing.md` (the
named-fragment contract), `docs/reasoning_roadmap.md`, `docs/implementation_plan.md`
(§8 item 26).

## 1. Goal

Decide a universally quantified clause goal over the committed finite-domain clausal
fragment, so FOLIO L2 gold-fed coverage rises by the rows whose first blocker is this
shape. Measured baseline (2026-09-22, after T1,
`uv run python -m evals.analyze_folio --subset l2`):

| verdict source | correct |
|---|---|
| text-fed | 25/45 |
| gold-fed open | 21/45 |
| gold `out_of_fragment` | 20/45 |
| covered (method) | 21/25 |
| covered (text) | 17/25 |

The FOLIO L2 tier-a rows whose first blocker is a universal/`¬∃` conclusion (found by
inspecting `evals/data/folio_l2_tier_a.jsonl`):

| id | label | conclusion |
|---|---|---|
| folio-validation-0045 | Uncertain | `∀x (Pet(x) → ¬Cat(x))` ("no pets are cats") |
| folio-validation-0107 | False | `¬(∃x (FinancialAid(x)))` |

`docs/coverage_ceiling.md` counts **2** first-blockers for T3; the re-measure after the
change gives the exact coverage and correctness delta.

**Not T3.** `folio-validation-0007` (`Uncertain`, `∀x (Human(x) → ¬Flu(x))`) is also a
universal goal, but its first blocker is a **premise** —
`∃x (GetMonkeypox(x) ∧ (Fever(x) ∨ …))`, an existential with a nested disjunction →
**T2** (`docs/coverage_ceiling.md` §3b). It stays `out_of_fragment` until T2 lands.

## 2. Current blocker

- **Parser.** `evals/folio_fol.py:_conclusion` refuses a `∀` conclusion outright
  (`raise FolParseError("universal conclusion has no goal form (L2 target form
  pending)")`, `evals/folio_fol.py:331–332`). `¬(∃x …)` normalises by NNF to a `∀`
  formula and then falls through to
  `raise FolParseError("compound conclusion is not a flat conjunction/disjunction")`
  (`evals/folio_fol.py:356`). Both rows are `out_of_fragment`.
- **IR.** `Query.goals` + `goal_mode` cannot express a universal clause. `goal_mode`
  is `single | all | any` (`core/models.py:25`): `all` decides each conjunct
  **independently** with its own witness (`verify._conjunctive_outcome`), `any` is a
  disjunction over independently proved literals. Neither is `∀x(l₁ ∨ … ∨ lₙ)`.
- **The positive direction is not the finite-pool enumeration.** Proving `∀` by
  checking only the named individuals is **unsound** (see §4.3): a small pool makes a
  non-entailed universal vacuously "true". T3 must introduce a fresh constant for the
  positive direction.
- **The builder is not needed for the method gate.** T3 is decided from a structured
  `Query`; the live extraction wording for "all … are …" is the extraction track
  (G1–G4), not T3's method gate (as in T1).

## 3. Scope and non-goals

**In scope.**
- A universally quantified **clause** `∀x (l₁(x) ∨ … ∨ lₙ(x))` over **one** bound
  variable, each `lᵢ` a literal (ground or over the shared variable): `∀x(A→B)`,
  `∀x(¬A)`, `∀x(A∨B)`, `∀x(A∧B → C)`.
- The positive direction (entailment) with a **fresh constant**; the negative
  direction (refutation) by a named witness; the honest `unknown` and the honest
  `budget`.
- The gold-fed parser and the LLM-free synthetic gate.

**Out of scope (unchanged, still `out_of_fragment`).**
- Nested quantifiers (`∀x∀y`, `∃` under `∀`), a free variable beyond the bound one,
  function terms.
- A non-clause body: `∀x (A(x) ∧ B(x))` is not a clause and stays refused.
- The non-flat **conditional/compound goal** (`A∨B → C∨D`, `Cute ∧ Still → Turtle ∧
  Skittish`) → **T4**. A **ground** conditional (`Cow(ted) → ¬Pet(ted)`) already
  parses as a flat `any` goal and is unchanged.
- The existential **premise** with a nested disjunction → **T2**.
- Head-only grounding `∀x (A(x) ∨ B(x))` as a **premise** → **T5**.
- The **live** extraction wording for a universal question is the extraction track
  (G1–G4), not T3's method gate.
- No new flag, no new `.env` setting: the capability is the existing `clausal`
  (`ANKYRA_LOGIC`, off by default); the new `universal_goal` is a derived
  `FragmentFeature`, not a procedure.
- No NL heuristics, no per-id tuning (`docs/task.md` §3.8; `docs/coverage_ceiling.md`
  §8).

## 4. The construct and its decision

### 4.1 Reading

`∀x (l₁(x) ∨ … ∨ lₙ(x))` is read classically over the committed finite domain, but the
**positive** direction is read as a genuine universal, not over the named pool: `D` is
the universe of named individuals **plus an arbitrary fresh individual**. This is the
same domain-closure stance the procedure already takes for rule grounding, extended
with the universal-generalization constant (§4.3).

### 4.2 Decision procedure (reusing bounded resolution)

Let `uf` be a **fresh constant** (in no clause of the theory), and let `clausify`
ground the theory's rules over the named pool **∪ {uf}**. The goal is decided as:

- **supported** — `T ⊨ ∀x (l₁ ∨ … ∨ lₙ)`. Assume the negated clause at the fresh
  constant, `{¬l₁(uf)}, …, {¬lₙ(uf)}`, and derive the empty clause
  (`refute_conjunction`, `engine/resolution.py`). By universal generalization over the
  fresh `uf`, an empty clause means `T ∪ {⋀¬lᵢ(uf)}` is unsatisfiable, hence
  `T ⊨ ⋀lᵢ`-as-clause for an arbitrary individual, i.e. `T ⊨ ∀x(l₁ ∨ … ∨ lₙ)`.
- **refuted** — `T ⊨ ¬∀x(l₁ ∨ … ∨ lₙ) = ∃x (⋀¬lᵢ)`. Over the finite named pool, find
  a witness `d` with `T ⊨ ¬lᵢ(d)` for **every** `i` (each by `refute(lᵢ(d))` →
  `entailed`); the refutations merge into one proof of the negated goal.
- otherwise **unknown**; a decision that exhausts the step budget is **budget**
  (`insufficient`, never a proof).

Special cases. For a single literal (`¬∃x φ` = `∀x ¬φ`) the positive check is
`refute(φ(uf))`. A ground clause (`V = ∅`) reduces to the existing `single`/`any`
behaviour and is not the target of T3.

### 4.3 Why this is sound and general

- **The positive direction is sound.** `uf` occurs in no theory clause, so
  `T ⊨ cl(uf)` entails `T ⊨ ∀x cl(x)`; the fresh constant is exactly universal
  generalization. Deriving the empty clause from assumed `¬lᵢ(uf)` only ever records a
  real resolution edge.
- **The naive alternative is unsound, and rejected.** Proving `∀` by requiring the
  conjunction `⋀¬lᵢ` unsatisfiable **for every named individual only** yields a false
  `supported` when the pool is small: `A(rex), B(rex) ⊢ ∀x(A→B)` would be "proved"
  although an unnamed individual may violate it. Hence T3-D2(a) introduces `uf`.
- **The negative direction is sound.** A named witness `d` with all `¬lᵢ(d)` entailed
  is a proof of `∃x⋀¬lᵢ` and therefore `¬∀x(l₁∨…∨lₙ)`; no unnamed individual is
  needed to refute.
- **Reuses T1.** `refute_conjunction` is exactly the T1 negative check; the merged
  proof, the budget handling and the provenance rendering are shared.
- **Bounded.** One fresh constant, one resolution search per direction, an explicit
  step budget; exhaustion is the honest `budget`.

## 5. Design decisions (all DECIDED — option (a))

- **T3-D1 — Representation.** (a) A new `goal_mode="forall"`; `Query.goals` holds the
  clause literals `l₁…lₙ` and `Query.target = goals[0]` (so `answer`/`explain` see a
  target). No goal-formula tree (D-L2-7 stays intact). (b) Reuse `all` with the negated
  literals plus a polarity field: a second representation of the same construct and a
  broader `Query` change. **DECIDED (a).**
- **T3-D2 — Positive direction.** (a) Fresh constant `uf` added to the grounding pool,
  then `refute_conjunction` over the negated clause literals (sound universal
  generalization; §4.3). (b) Enumerate the named pool only and require all witnesses to
  satisfy — **unsound**, vacuously true on a small domain. **DECIDED (a)**; (b) is
  recorded as the rejected alternative.
- **T3-D3 — Fragment naming.** (a) Add a derived `universal_goal` `FragmentFeature`
  (`goal_mode == "forall"`) mapped into the clausal fragment (it always co-occurs with
  `compound_goal`, which already selects `clausal`): an auditable name and a place for
  the routing negative control, no new capability/flag. (b) Reuse `compound_goal` and
  add no feature. **DECIDED (a)** (mirrors T1-D3).
- **T3-D4 — Body scope.** (a) Exactly one bound variable; the body must be a **flat
  disjunction of literals** (normalized through NNF). Nested quantifiers, extra free
  variables and conjunctions (`∀x(A∧B)`) stay `out_of_fragment`. (b) Generalize to
  arbitrary quantifier/connective structure — that is the goal-*formula* representation
  (`T-D2`/T4) and is deferred. **DECIDED (a).**
- **T-D3 (one fragment or three).** T1/T3 (and later T4) each add a **derived feature**
  and a synthetic gate while sharing the single `clausal` capability — the pattern
  already established by T1 (`docs/t1_plan.md` T1-D3). So: one procedure, named
  fragments, per-item gates. **Resolved by T3-D3(a) + T3-D4(a).**

## 6. Engine changes

- **`core/models.py`.** `GoalMode = Literal["single", "all", "any", "forall"]`
  (`core/models.py:25`); extend the `goal_mode`/`goals` docstrings.
- **`engine/clause.py`.** Add an `extra_pool: Sequence[str] = ()` parameter to
  `clausify`; the grounding pool becomes
  `obj_pool ∪ skolems ∪ extra_pool` (`engine/clause.py:247`). Adding instances of
  universally quantified rules at one more term is a logical consequence of the
  theory, so this is sound. The fresh constant is **not** added to
  `Clausification.skolems` (it is not an existential witness).
- **`engine/verify.py`.**
  - `_fresh_constant(theory)` — `uf0, uf1, …`, skipping any name already in
    `build_context(theory).obj_pool` and the Skolem constants.
  - `_universal_outcome(clausification, goals, pool, fresh, budget)` → `(outcome,
    target_result, complement_result, binding)` in the shape the other outcomes use
    (§4.2). Supported returns the conjunction refutation as `target`; refuted returns a
    `MergedProof` of the per-literal witness refutations as `complement`.
  - `l2_outcomes` (`engine/verify.py:515`): when `goal_mode == "forall"`, compute
    `fresh`, call `clausify(..., extra_pool=[fresh])`, and return a single outcome;
    `single`/`all`/`any` are untouched.
  - `_l2_status`: `forall` falls through the `single` mapping
    (`supported→supported`, `refuted→refuted`, `budget→insufficient`,
    `unknown→unsupported`); no new status/gap code. `_verify_l2` already appends
    `target_refuted:` on `refuted`, so `answer` gives `no` (strength `proven`) and
    `unknown` otherwise.
- **`engine/explain.py`.** `_l2_explanation` (`engine/explain.py:404`): for
  `goal_mode == "forall"` render the goal as `∀x(l₁ OR …)` and use
  `target.proof` (supported) or `complement.proof` (refuted); `_l2_steps` already
  flattens a `MergedProof`. No fabricated step.
- **`engine/inference.py`.** Add `"universal_goal"` to `FragmentFeature`
  (`engine/inference.py:28`); `_has_universal_goal(query)`; add it in `_fragment`
  (`engine/inference.py:110`). Routing is unchanged: `compound_goal` already maps to
  `clausal`, and the Horn-path refusal for a non-`single` goal stays
  `out_of_fragment:compound_goal`.

## 7. Gold-fed parser (`evals/folio_fol.py`)

In `_conclusion`, normalize with `_nnf` first; when the result is a `forall` over a
single variable whose body is a **flat disjunction of literals** (`_head_literals`),
return `goals = [_morphism(l) …]`, `goal_mode="forall"`, `target = goals[0]`. Remove
the early `formula[0] == "forall"` refusal (`evals/folio_fol.py:331–332`). `¬(∃x …)`
is handled automatically by NNF (it becomes a `forall`). A `forall` whose body is a
conjunction, nested, or has more than one/free variable keeps raising `FolParseError`.
Remove/adjust the outdated scope note in the module docstring (`evals/folio_fol.py`
lines 14–15, 42–43).

Extraction (`build/extract.py`, `build/unroll.py`) already has `ask_all`/`ask_any` and
needs no change for T3's method gate.

## 8. Synthetic gate (`evals.l2_synthetic`)

Add a `universal_goal` mechanism to `evals/build_l2_synthetic.py` with mandatory
controls:

| case | theory / goal | expected |
|---|---|---|
| `universal-01` | `∀x(A→B), ∀x(B→C)`; goal `∀x(A→C)` | `supported`, `yes` (fresh-constant proof) |
| `universal-02` | `A(rex), B(rex)`; goal `∀x(A→B)` | `insufficient` (**soundness control**: named-pool enumeration would say yes) |
| `universal-03` | `A(rex), ¬B(rex)`; goal `∀x(A→B)` | `refuted`, `no` (named witness) |
| `universal-04` | `P(rex)`; goal `∀x(¬P)` (`¬∃x P`) | `refuted`, `no` |
| `universal-05` | `∀x(P→Q), ∀x(P→¬Q)`; goal `∀x(¬P)` | `supported`, `yes` |
| `universal-06` | 2-step `∀x(A→…→C)` chain, `LOGIC_BUDGET=1` | `insufficient`, never proven |
| `universal-07` | any universal goal under `logic="off"` | `out_of_fragment:compound_goal` |

Plus a `routing_synthetic` case asserting the `universal_goal` feature routes to
`clausal` when `ANKYRA_LOGIC` is on (fragment `["universal_goal", "compound_goal",
"horn"]`).

## 9. Tests and verification

- `tests/test_engine_logic_l2.py`: universal support via the fresh constant; the
  soundness control (`A(rex), B(rex) ⊢ ∀x(A→B)` → `insufficient`); refutation by a
  named witness; `¬∃` refutation; budget exhaustion; `logic="off"` refusal; and that
  the existing `shared_witness`/`all`/`any` cases stay green.
- `tests/test_evals_folio_fol.py`: replace
  `test_universal_conclusion_is_out_of_fragment` with a parse test for
  `∀x(Pet(x)→¬Cat(x))` → `goal_mode="forall"`; add `¬(∃x FinancialAid(x))` → `forall`;
  keep the refusals for `∀x(A(x)∧B(x))` and nested quantifiers.
- `tests/test_engine_inference.py` / `tests/test_evals_routing_synthetic.py`: the
  `universal_goal` feature and its routing control.
- `uv run pytest` (offline) — full regression.
- `uv run python -m evals.l2_synthetic` — new total, **0 mismatches**.
- `uv run python -m evals.routing_synthetic` — green.
- `uv run python -m evals.analyze_folio --subset l2` — LLM-free gold-fed re-measure:
  `out_of_fragment` down, gold-fed/covered up (by up to 2), and among covered rows
  **0 grounded false proofs** (no `yes`/`no` contradicting the label). Record before/after
  in `docs/folio_gold_fed.md`.

## 10. Risks

- **The positive direction is the soundness-sensitive one.** A bug that drops the fresh
  constant, or grounds it in the theory, would admit a false `yes`. The synthetic
  control `universal-02` is the dedicated negative test; the gold-fed re-measure
  requires **0 grounded false proofs**.
- **Fresh-constant collision.** The name must not appear in the theory; `_fresh_constant`
  skips existing names defensively.
- **Grounding over `uf` is a superset.** It adds instances of universal rules only
  (sound). It must not be used to shrink the refutation direction: refuted is `∃`, so an
  extra witness never blocks it.
- **Behavioural change to the parser.** The early `∀` refusal disappears; every other
  conclusion shape keeps its existing path. The existing parser suite is the check.
- **Cost.** One extra constant enlarges the ground clause set modestly; the budget caps
  the search and exhaustion is `insufficient`, never a guess.
- **Explanation fidelity.** A supported universal renders the conjunction refutation; a
  refuted one the merged witness proofs. Every step must map to a real resolution edge.
- No full FOLIO live re-run without a separate budgeted decision
  (`docs/reasoning_roadmap.md` §4).

## 11. Work order (milestones)

1. Engine: `extra_pool` in `clausify`, `_fresh_constant`, `_universal_outcome`,
   `l2_outcomes`/`_l2_status` wiring; unit tests. (Gates nothing live.)
2. `evals/folio_fol.py` parser + parser tests.
3. Synthetic `universal_goal` cases; `evals.l2_synthetic` green.
4. `universal_goal` fragment feature + routing synthetic case.
5. LLM-free gold-fed re-measure; record the delta.
6. Docs: `coverage_ceiling.md` (T3 done + numbers), `folio_gold_fed.md`, `l2_plan.md`
   (milestone), `reasoning_roadmap.md`, `implementation_plan.md` item 26.

Each milestone lands reviewable on its own; the soundness gate (step 3) precedes the
gold-fed re-measure (step 5).

## 12. Guardrails

- The construct enters as a **named fragment** (`docs/fragment_routing.md`); beyond the
  committed shape it stays an honest `out_of_fragment`.
- **Never lower the semantics to pass a row** (`docs/coverage_ceiling.md` §8): no
  collapsing `∀x(Pet(x)→¬Cat(x))` to the ground `¬is_a(pet, cat)`, and no proving a
  universal over the named pool alone.
- No per-id tuning; the LLM-free gold-fed bound is the free gate after the item:
  coverage up, **0 grounded false proofs**.

## 13. Results

Implemented (decisions T3-D1a/T3-D2a/T3-D3a/T3-D4a). LLM-free verification, 2026-09-22:

| gate | before | after |
|---|---|---|
| `evals.l2_synthetic` | 29/29 | **36/36** (new `universal_goal` mechanism) |
| `evals.routing_synthetic` | 13/13 | **14/14** (`universal_goal` feature) |
| `uv run pytest` | 453 passed | **462 passed**, 26 skipped |

FOLIO L2 tier a, gold-fed (`uv run python -m evals.analyze_folio --subset l2`):

| metric | before | after |
|---|---|---|
| gold-fed open (correct) | 21/45 | **23/45** |
| gold `out_of_fragment` | 20/45 | **18/45** |
| coverage (method) | 25/45 | **27/45** |
| covered gold-fed | 21/25 | **23/27** |
| grounded false proofs | 0 | **0** |

The two newly covered rows are `0045` (`∀x (Pet(x) → ¬Cat(x))`, not entailed → the
honest `unknown`, matching `Uncertain`) and `0107` (`¬(∃x FinancialAid(x))`, refuted by
the named `tom`, matching `False`). `0007` keeps a universal conclusion but its first
blocker is the nested-disjunction existential **premise** (T2), so it stays
`out_of_fragment`.

