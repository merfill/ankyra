# T1 Plan — shared-witness existential goal `∃x (A(x) ∧ B(x))`

Status: **approved and implemented** (decisions T1-D1a/T1-D2a/T1-D3a). This is the
first item of the Tier-1 lowering backlog (`docs/coverage_ceiling.md` §6–§7). T1
raises **coverage** (not extraction) on FOLIO L2 by making a construct the committed
clausal fragment can already decide internally; per `D-FE-3` it **reuses the existing
bounded clausal procedure** (`ANKYRA_LOGIC`) — no new decision procedure, no new
semantics. Results are in §13.

Canonical language: English; Russian mirror: `docs/t1_plan_ru.md`.
Related: `docs/coverage_ceiling.md` (the ordered backlog and open decisions
T-D1…T-D3), `docs/folio_gold_fed.md` (the measurement this item follows),
`docs/l2_plan.md` (the procedure T1 extends), `docs/folio.md` §9–§10,
`docs/fragment_routing.md` (the named-fragment contract),
`docs/reasoning_roadmap.md`, `docs/implementation_plan.md` (§8 item 26).

## 1. Goal

Decide a conjunctive existential conclusion with a **single shared witness**,
`∃x (g₁(x) ∧ … ∧ gₙ(x))`, inside the committed finite-domain clausal fragment, so
FOLIO L2 gold-fed coverage rises by the rows whose first blocker is this shape.
Measured baseline (2026-09-22, `uv run python -m evals.analyze_folio --subset l2`):

| verdict source | correct |
|---|---|
| text-fed | 25/45 |
| gold-fed open | 17/45 |
| gold `out_of_fragment` | 24/45 |
| covered (method) | 17/21 |
| covered (text) | 15/21 |

The FOLIO L2 tier-a rows whose gold conclusion is a shared-witness existential
conjunction (found by inspection of `evals/data/folio_l2_tier_a.jsonl`):

| id | label | conclusion |
|---|---|---|
| folio-validation-0033 | True | `∃x (Leads(roderickstrong, x) ∧ ProfessionalWrestlingStable(x))` |
| folio-validation-0069 | True | `∃x (ScriptEditorFor(andrewcollins, x) ∧ Series(x) ∧ WorkingTitle(thesecretdudesociety, x))` |
| folio-validation-0058 | False | `∃x (CityIn(butte, x) ∧ CityIn(pierre, x))` |
| folio-validation-0059 | Uncertain | `∃x (CityIn(pierre, x) ∧ CityIn(bismarck, x))` |
| folio-validation-0008 | Uncertain | `∃x (GetMonkeypox(x) ∧ Coughing(x))` |

`docs/coverage_ceiling.md` counts **4** first-blockers for T1; the re-measure after
the change gives the exact coverage and correctness delta.

## 2. Current blocker

- **Parser.** `evals/folio_fol.py:_conclusion` refuses the shape outright when more
  than one conjunct mentions the quantified variable:
  `raise FolParseError("existential conclusion with a shared witness is out of
  fragment")` (`evals/folio_fol.py:346–347`), so the row is `out_of_fragment`.
- **IR.** `Query.goals` + `goal_mode` cannot express "one witness for all conjuncts".
  `goal_mode="all"` decides each goal **independently** (`verify._goal_outcome` calls
  `_l2_outcome` per goal, each with its own witness enumeration), i.e. it implements
  `(∃x g₁) ∧ … ∧ (∃x gₙ)` — weaker than `∃x (g₁ ∧ … ∧ gₙ)`. That is why the shape is
  refused rather than silently decided.
- **Builder/extraction are already able to express it.** `QuestionStructure.ask_all`
  compiles to `Query.goals` + `goal_mode="all"` (`build/unroll.py:396–404`); atoms may
  carry the shared `?x`. So no schema change is needed for the method gate.

## 3. Scope and non-goals

**In scope.**
- `∃x (g₁(x) ∧ … ∧ gₙ(x))`: each `gᵢ` a literal (ground, or over the shared
  variable(s)), with a **common** witness; finite named domain.
- The positive direction (entailment), the negative direction (refutation), the
  honest `unknown` and the honest `budget`.
- The gold-fed parser and the LLM-free synthetic gate.

**Out of scope (unchanged, still `out_of_fragment`).**
- Function terms, nested quantifiers, `∃` nested under `∀`.
- `¬∃`, universal/conditional goal form → **T3**.
- An existential **premise** with a nested disjunction → **T2**.
- Head-only grounding `∀x (A(x) ∨ B(x))` → **T5**.
- The **live** extraction wording for "is there an x that is both … and …?" is the
  extraction track (G1–G4), not T1's method gate.
- No new flag, no new `.env` setting: the capability is the existing `clausal`
  (`ANKYRA_LOGIC`, off by default).
- No NL heuristics, no per-id tuning (`docs/task.md` §3.8; `docs/coverage_ceiling.md`
  §8).

## 4. The construct and its decision

### 4.1 Reading

`∃x (g₁(x) ∧ … ∧ gₙ(x))` is read **classically** over the finite domain `D` the
ground procedure already assumes (the theory's object pool ∪ Skolem constants
∪ conclusion constants; the same domain-closure stance as witness enumeration,
`verify._witness_pool`). Under an open world, "not proved" is never "false": `D` is
the universe of **named** individuals the problem committed to.

### 4.2 Decision procedure (reusing bounded resolution)

Collect the goal variables `V`; let `D` be the pool. Enumerate assignments
`σ: V → D` (`|D|^|V|`). For each `σ`, ground every goal `gᵢσ`:

- **proved(σ)** — `T ∪ Γ ⊢ gᵢσ` for every `i`, each by ground resolution
  (`refute(clausification, literal_of(gᵢσ))`).
- **refuted(σ)** — `T ∪ Γ ⊨ ¬(g₁σ ∧ … ∧ gₙσ)`, checked by assuming every conjunct as
  its own unit clause and deriving the empty clause (`refute_conjunction` in
  `engine/resolution.py`): the assumed units `{g₁σ},…,{gₙσ}` are jointly unsatisfiable.
  (Assuming the non-pivotal conjuncts while refuting the first was tried and rejected:
  the base theory becomes unsatisfiable, which breaks set-of-support completeness.)
- otherwise **open(σ)**.

Then:

| group outcome | condition | verdict status |
|---|---|---|
| `supported` | some σ is proved | `supported` (report the binding) |
| `refuted` | every σ is refuted | `refuted` |
| `budget` | no verdict above and some decision exhausted the step budget | `insufficient` + `logic_budget:` |
| `unknown` | no σ proved and some σ open | `insufficient`/`unsupported` |

Special case `V = ∅` (ground conjunction): one empty σ; **proved** iff all entailed
(the existing `all` support), **refuted** iff the conjunction is unsatisfiable. For a
single goal the procedure degenerates to today's `single` path.

### 4.3 Why this is sound and general

- **Shared, not independent.** Requiring one `σ` for all conjuncts is exactly `∃x`
  (the reading now refused); the independent reading is a strictly weaker
  over-approximation and is the bug the parser was guarding against.
- **The generalization is safe.** For goals with **distinct** variables the joint
  enumeration is `∏ (∃xᵢ gᵢ)` — logically equal to the current independent handling;
  for **ground** goals the empty σ reduces to today's behaviour. So `goal_mode="all"`
  becomes uniformly "conjunctive query with existential variables" with no regression
  in the existing cases.
- **Refutation is complete enough for the False rows.** `∀x (A(x) → ¬B(x))` (row 0058)
  refutes `∃x (A∧B)` per witness even though neither `∀x ¬A` nor `∀x ¬B` holds — the
  old "any conjunct refuted" rule would have abstained. The joint check adds no
  unsoundness: it derives the empty clause.
- **Bounded.** Witness growth is `|D|^|V|`; the step budget is explicit and exhaustion
  is the honest `budget`.

## 5. Design decisions (all three DECIDED — option (a))

- **T1-D1 — Representation.** (a) Generalize `goal_mode="all"` to the joint reading
  (recommended): no new field, the variable is already in the goals, the distinct-
  variable and ground cases are unchanged. (b) Add a new mode/field
  (`goal_mode="witness"` or `Query.witness`): more explicit, but a second representation
  and a broader change to `Query`, `builtin`/Horn dispatch and the proposal cycle for
  no added expressiveness. **DECIDED (a).**
- **T1-D2 — Refutation for ground conjunctions.** (a) Use the joint unsatisfiability
  check for every `all` (recommended; needed for 0058, sound, more complete). (b) Keep
  "refuted iff some conjunct refuted" for ground goals and use the joint check only
  when variables are present (smaller behavioural change, but two semantics for one
  mode). **DECIDED (a)**; the regression re-measure confirmed it (§9).
- **T1-D3 — Fragment naming** (relates to `T-D3`). (a) Add a derived
  `shared_witness` `FragmentFeature` (goal_mode `all` with a variable) mapped into the
  clausal fragment (recommended): auditable name, a place for the routing negative
  control, no new capability/flag. (b) Reuse `compound_goal` and add no feature.
  **DECIDED (a).**

## 6. Engine changes (`src/ankyra/engine/`)

- **`verify.py`.** Add a joint conjunctive decision for `goal_mode="all"`:
  `_conjunctive_outcome(clausification, goals, pool)` → `(outcome, binding, target,
  complement)`, enumerating σ and applying §4.2. Wire `l2_outcomes` so an `all` query
  yields one group outcome; propagate a winning witness binding into
  `verdict.bindings`. The `single` and `any` paths are untouched (`any` is already
  correct: `∃x(A∨B) ≡ ∃xA ∨ ∃xB`).
- **`resolution.py`.** Generalize the prover: `refute_support(clausification,
  assumed)` seeds the set of support from a **list** of assumed clauses (a single unit
  for a literal goal; one unit per conjunct for a conjunction). `refute` is the
  single-literal wrapper and `refute_conjunction` the T1 negative check; no new
  semantics. (`Clausification.with_units` was considered and dropped — the multi-unit
  support is the clean, complete form.)
- **`explain.py`.** For a supported group, render the union of the winning witness's
  per-conjunct resolution proofs (`MergedProof`, flattened by `_l2_steps`); the goal
  label is the conjunctive goal, the binding is the witness. Refuted/unknown render
  empty.
- **`inference.py`.** Add the derived `shared_witness` feature (T1-D3) to `_fragment`;
  `compound_goal` already maps to the clausal procedure, so `analyze_routing` yields
  `clausal` through the existing capability. No new refusal code, no new flag.
- **`answer.py`.** No change required: with `answer_type="open"` the binding comes
  from `verdict.bindings` (`answer.py:136–139`). Note: `build_answer` computes
  hypothesis strength through the Horn `winning_proof`, which is `None` for a
  non-Horn L2 proof; that is a pre-existing limitation, out of T1 scope.

## 7. Gold-fed parser (`evals/folio_fol.py`)

In `_conclusion`, replace the shared-witness refusal (`folio_fol.py:346–347`) with the
flat `all` construction already used for a ground conjunction: `goals` are all
conjuncts, `goal_mode="all"`, the quantified variable stays in the morphisms. The
engine's joint semantics (T1-D1a) makes the same representation correct for both the
shared-witness and the ground case. No new schema field. Nested quantifiers and
non-literal bodies keep raising `FolParseError`.

Extraction (`build/extract.py`, `build/unroll.py`) already supports `ask_all` with
variables; no prompt change is part of T1's method gate.

## 8. Synthetic gate (`evals/l2_synthetic`)

Add a `shared_witness` mechanism to `evals/build_l2_synthetic.py` with mandatory
controls:

| case | theory / goal | expected |
|---|---|---|
| `shared-witness-01` | one `x` is both `p` and `q`; goal `∃x(p(x)∧q(x))` | `supported`, binding |
| `shared-witness-02` | `p(a)`, `q(b)`, `a≠b`; goal `∃x(p(x)∧q(x))` | `insufficient` (trap: the old independent reading would say yes) |
| `shared-witness-03` | `p(a), p(b)`, rule `p(?x) → ¬q(?x)`; goal `∃x(p(x)∧q(x))` | `refuted` (joint per-witness unsat) |
| `shared-witness-04` | only `p(a)`; goal `∃x(p(x)∧q(x))` | `insufficient` |
| `shared-witness-05` | a 2-step witness chain, forcing `LOGIC_BUDGET=1` | `insufficient`, never proven |
| `shared-witness-06` | same goal under `logic="off"` | `out_of_fragment:compound_goal` |

Plus a `routing_synthetic` case asserting the `shared_witness` feature routes to
`clausal` when `ANKYRA_LOGIC` is on.

## 9. Tests and verification

- `tests/test_engine_logic_l2.py`: joint support with binding, joint trap
  (`p(a), q(b)` → `insufficient`), joint refutation, and that the existing ground
  `goal-all` cases stay green.
- `tests/test_engine_resolution.py`: `refute_conjunction` refutes `p∧q` under
  `q → ¬p` while neither conjunct is refuted alone.
- `tests/test_evals_folio_fol.py`: replace
  `test_existential_conjunction_conclusion_is_out_of_fragment` with a test that the
  shape parses to `goal_mode="all"` with the shared variable; keep the nested/universal
  refusals.
- `uv run pytest` (offline) — full regression.
- `uv run python -m evals.l2_synthetic` — new total, **0 mismatches**.
- `uv run python -m evals.routing_synthetic` — green.
- `uv run python -m evals.analyze_folio --subset l2` — LLM-free gold-fed re-measure:
  `out_of_fragment` down, covered/gold-fed up by up to 4, and a check that among
  covered rows there is **0 grounded false proof** (no `yes`/`no` that contradicts the
  label). Record before/after in `docs/folio_gold_fed.md`.

## 10. Risks

- **Behavioural change to ground `all` refutation** (T1-D2a) touches FOLIO ground
  compound goals and the existing synthetic cases; the regression and the gold-fed
  re-measure are the check. If it costs a correct row, fall back to T1-D2b.
- **Cost.** `|D|^|V|` witnesses × n conjuncts × resolution. FOLIO L2 domains are small;
  the budget caps it and exhaustion is `insufficient`, never a guess.
- **Domain closure.** Enumeration over the named pool treats it as the universe
  (already the engine's stance); an individual named only in the conclusion is in the
  pool via `_object_names`.
- **Explanation fidelity.** A group support has n sub-proofs; the union must still map
  every step to a real resolution edge (no fabricated step).
- No full FOLIO live re-run without a separate budgeted decision
  (`docs/reasoning_roadmap.md` §4).

## 11. Work order (milestones)

1. Engine: `refute_support`/`refute_conjunction`, joint conjunctive decision,
   `verify` wiring; unit tests. (Gates nothing live.)
2. `evals/folio_fol.py` parser + parser tests.
3. Synthetic `shared_witness` cases; `evals.l2_synthetic` green.
4. `shared_witness` fragment feature + routing synthetic case.
5. LLM-free gold-fed re-measure; record the delta.
6. Docs: `coverage_ceiling.md` (T1 done + numbers), `folio_gold_fed.md`, `l2_plan.md`
   (milestone), `reasoning_roadmap.md`, `implementation_plan.md` item 26.

Each milestone lands reviewable on its own; the soundness gate (step 3) precedes the
gold-fed re-measure (step 5).

## 12. Guardrails

- The construct enters as a **named fragment** (`docs/fragment_routing.md`); beyond the
  finite domain it stays an honest `out_of_fragment`.
- **Never lower the semantics to pass a row** (`docs/coverage_ceiling.md` §8): no
  collapsing the shared witness to independent witnesses.
- No per-id tuning; the LLM-free gold-fed bound is the free gate after the item:
  coverage up, **0 grounded false proofs**.

## 13. Results

Implemented (decisions T1-D1a/T1-D2a/T1-D3a). LLM-free verification, 2026-09-22:

| gate | before | after |
|---|---|---|
| `evals.l2_synthetic` | 23/23 | **29/29** (new `shared_witness` mechanism) |
| `evals.routing_synthetic` | 12/12 | **13/13** (`shared_witness` feature) |
| `uv run pytest` | green | **453 passed**, 26 skipped |

FOLIO L2 tier a, gold-fed (`uv run python -m evals.analyze_folio --subset l2`):

| metric | before | after |
|---|---|---|
| gold-fed open (correct) | 17/45 | **21/45** |
| gold `out_of_fragment` | 24/45 | **20/45** |
| coverage (method) | 21/45 | **25/45** |
| covered gold-fed | 17/21 | **21/25** |
| grounded false proofs | 0 | **0** |

The four newly covered rows are `0033`, `0058`, `0059`, `0069`; `0058` is refuted per
witness, `0033`/`0069` are supported with a witness, `0059` stays an honest `unknown`
(matching `Uncertain`). `0008`'s first blocker is T2 (an existential premise with a
nested disjunction), so it stays `out_of_fragment`. This carried the numbers into
`docs/coverage_ceiling.md`, `docs/folio_gold_fed.md`, `docs/l2_plan.md`,
`docs/reasoning_roadmap.md` and `docs/implementation_plan.md` (item 26).
