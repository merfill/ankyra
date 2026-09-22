# T5 Plan — head-only universal premise (`∀x (l₁(x) ∨ … ∨ lₙ(x))`)

Status: **approved and implemented**. This is the fifth item of the Tier-1 lowering
backlog (`docs/coverage_ceiling.md` §6–§7) and the largest. T5 raises **coverage**
(not extraction) on FOLIO L2 by making a **head-only** universal premise decidable:
a clause whose variables are not bound by any body, e.g.
`∀x (Rabbit(x) ∨ Squirrel(x))`. Per `D-FE-3` it **reuses the existing bounded
clausal procedure** (`ANKYRA_LOGIC`): the work is the grounding domain, not new
semantics. It resolves the open decision **T-D1** of `docs/coverage_ceiling.md` §7.
Results are in §13.

Canonical language: English; Russian mirror: `docs/t5_plan_ru.md`.

Related: `docs/coverage_ceiling.md` (the ordered backlog and the open decision
T-D1), `docs/t1_plan.md`, `docs/t3_plan.md` (the per-item pattern T5 follows),
`docs/l2_plan.md` (the procedure T5 extends), `docs/folio_gold_fed.md` (the
measurement this item follows), `docs/fragment_routing.md` (the named-fragment
contract), `docs/reasoning_roadmap.md`, `docs/implementation_plan.md` (§8 item 26).

## 1. Goal

Decide a head-only universal premise — a clause `∀x (l₁(x) ∨ … ∨ lₙ(x))` whose
variable is not bound by a body — inside the committed finite-domain clausal
fragment, so FOLIO L2 gold-fed coverage rises by the rows whose first blocker is
this shape. Measured baseline (2026-09-22, after T1/T3,
`uv run python -m evals.analyze_folio --subset l2`):

| verdict source | correct |
|---|---|
| text-fed | 25/45 |
| gold-fed open | 23/45 |
| gold `out_of_fragment` | 18/45 |
| covered (method) | 23/27 |
| covered (text) | 17/27 |

The 18 `out_of_fragment` rows decompose as: **T5 12**, T2 3 (`0006/0007/0008`,
existential premise with a nested disjunction), T4 1 (`0073`, non-flat goal),
T4+T5 1 (`0020`), malformed 1 (`0109`). The 12 T5 first-blockers, all refused as
`unsafe_rule`:

| id | label | conclusion | head-only premise |
|---|---|---|---|
| folio-validation-0016 | Uncertain | `Turtle(rock)` | `∀x (Rabbit(x) ∨ Squirrel(x))` |
| folio-validation-0017 | Uncertain | `¬Turtle(rock)` | idem |
| folio-validation-0018 | True | `Turtle(rock) ∨ Cute(rock)` | idem |
| folio-validation-0039 | Uncertain | `MassProductDesign(aDesignByMax)` | `∀x (ZahaHadidDesignStyle(x) ∨ KellyWearstlerDesignStyle(x))` |
| folio-validation-0040 | True | `Evocative(aDesignByMax) ∧ Dreamy(aDesignByMax)` | idem |
| folio-validation-0042 | True | `AmongMostActivePlayersInMajorTennis(cocoGauff)` | `∀x (FemaleTennisPlayersAtRolandGarros2022(x) ∨ MaleTennisPlayersAtRolandGarros2022(x))` |
| folio-validation-0043 | Uncertain | `LostToRafaelNadal(cocoGauff)` | idem |
| folio-validation-0044 | False | `¬LostToIgaŚwiątek(cocoGauff) ∨ ¬AmongMostActivePlayersInMajorTennis(cocoGauff)` | idem |
| folio-validation-0076 | Uncertain | `Tuition(mary)` | `∀x (Takeout(x) ∨ DiningHall(x))` |
| folio-validation-0077 | True | `NotPicky(mary) ∧ Eating(mary)` | idem |
| folio-validation-0127 | False | `¬ HaveWings(rock)` | (head-only body-unbound variable) |
| folio-validation-0149 | False | `¬(Student(rose) ∧ Human(jerry))` | (head-only body-unbound variable) |

`docs/coverage_ceiling.md` counts **12** first-blockers for T5; the re-measure after
the change gives the exact coverage and correctness delta.

## 2. Current blocker

- **Grounding.** `_groundings` (`engine/clause.py:116–124`) refuses a rule as soon as
  a **head** variable is not a body variable (`if head_vars - body_vars: return None`),
  so `clausify` records `unsafe_rule:<i>` (`engine/clause.py:263–266`) and `verify`
  returns `out_of_fragment`. A conditionless disjunctive universal is encoded by the
  parser as exactly such a rule (`evals/folio_fol.py:_clause_rule`, 264–276:
  `conditions=[]`, `consequence=A(?x)`, `alternatives=[B(?x)]`).
- **The Horn engine cannot see it.** `_fire_rules` skips every rule with no conditions
  (`engine/horn.py:409–410`), so a head-only universal is neither fired nor safe there;
  the L2 procedure is the only candidate.
- **Two different domains in one pool.** The clausification pool is
  `build_context(theory).obj_pool ∪ skolems ∪ extra_pool` (`engine/clause.py:257`),
  and `obj_pool` (`engine/horn.py:49–60`) collects **every** subject and object of
  every atom. For the FOLIO encoding — where a unary `P(a)` is lowered to
  `is_a(a, p)` — the pool therefore mixes **individuals** (`rock`, `cocoGauff`) with
  **predicate/class names** (`rabbit`, `femaletennis…`, the `is_a` objects). Grounding
  a head-only universal over that pool instantiates it at class names, which are not
  elements of the intended first-order universe: the extra clauses are not consequences
  of the original universal and can both fabricate proofs and block legitimate
  refutations (§4.3).

## 3. Scope and non-goals

**In scope.**
- A rule with a **head-only variable**: a variable occurring in the head and in no
  condition. Two shapes, handled uniformly:
  - a conditionless disjunctive universal `∀x (l₁(x) ∨ … ∨ lₙ(x))` (the FOLIO rows);
  - a conditionless Horn universal `∀x A(x)`, and a body rule with an extra head
    variable (`A(?x) → B(?y)`), meaning `∀x,y (A(x) → B(y))`.
- Grounding head-only variables over the **individual domain** (§4.1); the honest
  `unsupported` / `budget`; the gold-fed parser is unchanged.
- The synthetic gate and the routing control.

**Out of scope (unchanged, still `out_of_fragment`).**
- Nested/multi-variable quantifiers beyond the head-only variables, function terms.
- The **existential premise with a nested disjunction** → **T2**; the **non-flat
  goal** → **T4**.
- Changing body-variable grounding: `?c` in `is_a(?x, ?c)` must keep ranging over
  class names, so the body pool stays the full pool (§4.3). T5 touches only the
  head-only variables.
- No new flag, no new `.env` setting: the capability is the existing `clausal`
  (`ANKYRA_LOGIC`, off by default); `head_only_rule` is a derived `FragmentFeature`,
  not a procedure.
- No NL heuristics, no per-id tuning (`docs/task.md` §3.8; `docs/coverage_ceiling.md`
  §8).

## 4. The construct and its decision

### 4.1 Reading — two domains

`∀x (l₁(x) ∨ … ∨ lₙ(x))` is read classically over the committed finite domain. The
encoding distinguishes two kinds of term:

- **Individuals** — the intended universe of discourse: any term in a **subject**
  position, or in the **object** position of a **non-`is_a`** atom. This is the same
  domain `folio_fol._object_names` already uses to build `Theory.objects`.
- **Class names** — the **objects of `is_a` atoms** (the lowered unary predicates),
  e.g. `rabbit`, `cocoGauff`-style predicate ids. They are encoding artifacts, not
  elements of the universe.

Define the **individual domain**

```
D_ind = (ground terms of the theory) \ {o : o occurs as the object of an is_a atom}
```

(including Skolem constants and T3's `extra_pool`, which are individuals and never
`is_a` objects). Class names that also happen to occur as a subject are a documented
boundary (§10); the committed collections do not exhibit it.

### 4.2 Decision procedure (reusing bounded resolution)

No new procedure: grounding plus the existing bounded resolution decides the goal. In
`clausify`, a rule's head-only variables are instantiated over `D_ind` (the body
variables stay over the full pool, §4.3). The grounding produces, for each individual
`d`, the clause `¬body₁ ∨ … ∨ l₁(d) ∨ …`, and the goal is then decided by `verify`'s
existing L2 paths (`supported` / `refuted` / `contradiction` / `unknown` / `budget`).
A head-only variable with **no** individual in `D_ind` keeps the honest `unsafe_rule`
refusal.

### 4.3 Why this is sound and general

- **Sound.** `D_ind` is the intended universe; `∀x φ(x)` entails `φ(d)` for every
  `d ∈ D_ind`, so the ground instances are consequences of the premise. Instantiating
  at class names is not: they are not domain elements, so those clauses are not
  entailed and can make the clause set unsatisfiable where the theory is satisfiable
  — a fabricated proof.
- **Complete for the encoding.** Every individual occurs as a subject or as a
  non-`is_a` argument, hence in `D_ind`; the only excluded terms are class names,
  which no individual query denotes. No needed instance is lost.
- **The naive alternative is unsafe, and rejected.** Grounding head-only variables
  over the full pool (individuals **and** class names) is what `docs/coverage_ceiling.md`
  §3 warns about: a prototype over the committed rows is both unsound in principle and
  empirically worse (§9) — the spurious class instances block the refutations of the
  three `False` rows. A synthetic control proves a true fact about a class name that
  the individual-only grounding leaves `unsupported` (§8, `head-only-03`).
- **Body variables are deliberately unchanged.** A class variable (`?c` in
  `is_a(?x, ?c)`, a rule body over `is_a`) must range over class names; its instances
  only fire through derivable body atoms, which is the existing, already-gated
  behaviour. Restricting them is a separate, broader change and out of T5 scope.
- **Bounded.** `D_ind` is finite; the existing step budget caps the search and
  exhaustion stays the honest `budget`.

## 5. Design decisions

- **T5-D1 — Domain (resolves T-D1).** (a) Ground head-only variables over `D_ind`
  (individual domain); body variables unchanged. (b) Ground over the full pool
  (naive) — rejected (non-consequence instances; worse on the committed rows).
  (c) Keep the strict refusal — no coverage. **DECIDED (a).**
- **T5-D2 — Individual-domain definition.** (a) `D_ind = ground terms \ is_a objects`
  (strict; a class name is never an individual). (b) `D_ind = ground terms \ (is_a
  objects \ terms occurring as a subject or non-`is_a` argument)` (loose; a name used
  as both stays an individual). Both give the identical result on FOLIO (§9); (a) is
  simpler and handles class hierarchies (`is_a(car, vehicle)`) correctly. **DECIDED
  (a)**; (b) recorded as the alternative.
- **T5-D3 — Fragment naming.** (a) Add a derived `head_only_rule` `FragmentFeature`
  (a rule with a head-only variable) mapped into the clausal fragment: an auditable
  name and a place for the routing control, no new capability/flag. (b) Reuse
  `disjunction`. **DECIDED (a)** (mirrors T1-D3/T3-D3). Note: the FOLIO rows also set
  `disjunction`; a Horn `∀x A(x)` sets only `head_only_rule`.
- **T5-D4 — Scope.** (a) Any rule with a head-only variable (conditionless
  disjunctive universal, conditionless Horn universal, body rule with an extra head
  variable), grounded over `D_ind`. (b) Only the conditionless disjunctive shape.
  **DECIDED (a)** — one uniform grounding rule, no shape special-casing.

## 6. Engine changes

- **`engine/clause.py`.**
  - `_individual_pool(theory, pool)` — `D_ind` from §4.1: the pool terms minus
    terms minus the `is_a` objects (class names), for ground terms only.
  - `_groundings(rule, pool, individuals)` — for each variable, use `pool` when it is a
    body variable and `individuals` when it is head-only; `None` (unsafe) only when the
    chosen domain is empty.
  - `clausify` — compute `individuals` once and pass it through; the body pool is
    unchanged (`engine/clause.py:257`). No signature change to `clausify` itself.
- **`engine/inference.py`.** Add `"head_only_rule"` to `FragmentFeature`
  (`engine/inference.py:28`); `_has_head_only_rule(theory)` (reuse `_rule_variables`),
  added in `_fragment` (`engine/inference.py:116`). Routing is unchanged: the FOLIO
  rows already carry `disjunction`; the Horn-path refusal stays as is.
- **`engine/verify.py` / `engine/explain.py`.** No change: the new instances are
  ordinary ground clauses; `_verify_l2` and `_l2_explanation` decide/render them as
  before, and `render_rule` already renders an empty body as `TRUE`
  (`engine/explain.py:47`). Verify that `_classify_clause` maps `rule:<i>` to the
  head-only rule in the trace (it does; `engine/explain.py:340–343`).
- **`evals/folio_fol.py`.** No change: `_premise`/`_clause_rule` already produce the
  head-only rule; the engine now grounds it. `folio_fol._object_names` already keeps
  `Theory.objects` equal to `D_ind` for the FOLIO encoding.

## 7. Gold-fed parser

No parser change. The T5 rows already parse (`_clause_rule`, 264–276) and were only
refused by the engine (`unsafe_rule`); after T5 they are decided. `0020` keeps its
non-flat goal (`T4`) and stays `out_of_fragment`.

## 8. Synthetic gate (`evals.l2_synthetic`)

Add a `head_only` mechanism to `evals/build_l2_synthetic.py` with mandatory controls
(the `_rule(conditions=[], consequence=A(?x), alternatives=[B(?x)])` shape):

| case | theory / goal | expected |
|---|---|---|
| `head-only-01` | `is_a(rex,prim)`; `∀x(a(x)∨b(x))`, `a→c`, `b→c`; goal `is_a(rex,c)` | `supported`, `yes` (domain closure over `rex`) |
| `head-only-02` | same; goal `is_a(rex,d)` with `a→¬d`, `b→¬d` | `refuted`, `no` (every individual is `a` or `b`) |
| `head-only-03` | same as 01; goal `is_a(prim,c)` (`prim` is a class name) | `unsupported`, `unknown` (**soundness control**: full-pool grounding would say `yes`) |
| `head-only-04` | `head-only-02` with `LOGIC_BUDGET=1` | `insufficient`, never proven |
| `head-only-05` | `head-only-01` under `logic="off"` | `out_of_fragment:non_horn` |
| `head-only-06` | head-only rule, only class names in `D_ind` | `unsupported`/`out_of_fragment`, **never** a false proof |

Plus a `routing_synthetic` case asserting `head_only_rule` routes to `clausal` when
`ANKYRA_LOGIC` is on (fragment `["head_only_rule", "disjunction", "horn"]`).

Prototype check of the three decisive controls (individual-only vs naive full pool):

| case | individual-only | naive full pool |
|---|---|---|
| `head-only-01` | supported / yes | supported / yes |
| `head-only-02` | refuted / no | refuted / no |
| `head-only-03` | **unsupported / unknown** | **supported / yes (false)** |

## 9. Tests and verification

Prototype (LLM-free, not committed) over all 45 FOLIO L2 tier-a rows with
individual-only head-only grounding:

| metric | baseline | prototype |
|---|---|---|
| gold-fed open (correct) | 23/45 | **35/45** |
| gold `out_of_fragment` | 18/45 | **6/45** |
| coverage (method) | 27/45 | **39/45** |
| covered gold-fed | 23/27 | **35/39** |
| grounded false proofs | 0 | **0** |

The 12 T5 rows are 12/12 correct (with naive full-pool only 9/12: the three `False`
rows degrade to honest `unknown`). No previously covered row regressed.

- `tests/test_engine_logic_l2.py`: head-only support (01), refutation (02), the
  class-name soundness control (03), budget (04), `logic="off"` (05), empty-`D_ind`
  refusal (06), and a regression pass over the existing cases.
- `tests/test_engine_resolution.py`: `_individual_pool` excludes `is_a` objects and keeps
  subjects / non-`is_a` arguments / Skolems.
- `tests/test_engine_inference.py` / `tests/test_evals_routing_synthetic.py`: the
  `head_only_rule` feature and its routing control.
- `uv run pytest` (offline) — full regression.
- `uv run python -m evals.l2_synthetic` — new total, **0 mismatches**.
- `uv run python -m evals.routing_synthetic` — green.
- `uv run python -m evals.analyze_folio --subset l2` — LLM-free gold-fed re-measure:
  coverage up by 12 (27→39), `out_of_fragment` down (18→6), and among covered rows
  **0 grounded false proofs**. Record before/after in `docs/folio_gold_fed.md`.

## 10. Risks

- **The individual/class boundary is the soundness-sensitive part.** A bug that falls
  back to the full pool when `D_ind` is empty, or that includes `is_a` objects, admits
  a false `yes`. The synthetic control `head-only-03` is the dedicated negative test;
  the gold-fed re-measure requires **0 grounded false proofs**.
- **A class name that is also a subject.** Under T5-D2(a) it is excluded from `D_ind`.
  If a problem genuinely uses such a name as an individual, its head-only instances
  are missed (honest `unsupported`, never unsound). Documented boundary; the committed
  collections do not exhibit it.
- **Body-vs-head asymmetry.** Body variables keep the full pool, so body-grounded
  instances at class names remain possible (pre-existing, gated by the current 0
  false-proof result). T5 must not be read as having fixed that; aligning body
  grounding to `D_ind` is a separate, broader change.
- **Explanation fidelity.** A head-only rule renders as `IF TRUE => a(x) OR b(x)`;
  every step must still map to a real resolution edge, no fabricated step.
- **Cost.** Grounding adds one clause per individual per head-only rule; `D_ind` is
  small on FOLIO and the budget caps the search (exhaustion is the honest `budget`).
- No full FOLIO live re-run without a separate budgeted decision
  (`docs/reasoning_roadmap.md` §4).

## 11. Work order (milestones)

1. Engine: `_individual_pool`, `_groundings` domains, `clausify` wiring; unit tests.
   (Gates nothing live.)
2. Synthetic `head_only` cases; `evals.l2_synthetic` green — the soundness gate
   (`head-only-03`) precedes anything else.
3. `head_only_rule` fragment feature + routing synthetic case.
4. LLM-free gold-fed re-measure; record the delta.
5. Docs: `coverage_ceiling.md` (T5 done + numbers), `folio_gold_fed.md`, `l2_plan.md`
   (milestone), `reasoning_roadmap.md`, `implementation_plan.md` item 26;
   `docs/t5_plan_ru.md` mirror.

Each milestone lands reviewable on its own; the soundness gate (step 2) precedes the
gold-fed re-measure (step 4).

## 12. Guardrails

- The construct enters as a **named fragment** (`docs/fragment_routing.md`); beyond
  the committed shape it stays an honest `out_of_fragment`.
- **Never lower the semantics to pass a row** (`docs/coverage_ceiling.md` §8): no
  instantiating a universal at class names, and no collapsing `∀x(A(x)∨B(x))` to a
  ground fact.
- No per-id tuning; the LLM-free gold-fed bound is the free gate after the item:
  coverage up, **0 grounded false proofs**.

## 13. Results

Implemented (decisions T5-D1a…T5-D4a). LLM-free verification, 2026-09-22:

| gate | before | after |
|---|---|---|
| `evals.l2_synthetic` | 36/36 | **41/41** (new `head_only` mechanism) |
| `evals.routing_synthetic` | 14/14 | **15/15** (`head_only_rule` feature) |
| `uv run pytest` | 462 passed | **464 passed**, 26 skipped |

FOLIO L2 tier a, gold-fed (`uv run python -m evals.analyze_folio --subset l2`):

| metric | before | after |
|---|---|---|
| gold-fed open (correct) | 23/45 | **35/45** |
| gold `out_of_fragment` | 18/45 | **6/45** |
| coverage (method) | 27/45 | **39/45** |
| covered gold-fed | 23/27 | **35/39** |
| grounded false proofs | 0 | **0** |

The twelve newly covered rows are the head-only-universal rows (`0016`–`0018`,
`0039`–`0044`, `0076`, `0077`, `0127`, `0149`); all are correct, and no previously
covered row regressed. The 6 remaining `out_of_fragment` rows are T4 (`0073`),
T4+T5 (`0020`), T2 (`0006`, `0007`, `0008`) and one malformed annotation (`0109`).
`0020` still needs T4's non-flat goal, so T5 alone does not cover it. The soundness
control `head-only-03` confirms that a class name is never instantiated (a goal about
the class name `prim` stays `unsupported`), and the gold-fed re-measure has 0 grounded
false proofs.
