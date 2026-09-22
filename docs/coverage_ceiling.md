# The coverage ceiling — what it is, and the plan to raise it

Status: **explanation + Tier-1 plan**. Companion to the measurement in
`docs/folio_gold_fed.md`. This note first explains, in plain terms, what the
*coverage* ceiling is and why FOLIO L2 hits it, then lays out the ordered Tier-1
backlog that raises it. No code; it is the working plan for `ANKYRA_LOGIC`.

*Coverage* (formalism) is the share of a benchmark's gold formulas that the committed
logic can express and decide: `|in fragment| / |all|`, i.e. `1 − out_of_fragment`.
It is a membership ratio, not an open cover: `out_of_fragment` is the primitive.
English keeps the established term *coverage*; the Russian mirror uses «охват» to
avoid the topological reading of «покрытие».

Canonical language: English; Russian mirror: `docs/coverage_ceiling_ru.md`.
Related: `docs/folio_gold_fed.md` (the measurement this plan follows),
`docs/folio_ceilings.md` (the ceiling model), `docs/folio_extension_plan.md`
(the staged extension plan and decisions `D-FE-1`…`D-FE-7`), `docs/folio.md`
(§9–§10), `docs/l2_plan.md` (the L2 procedure Tier 1 extends), `docs/t1_plan.md`
(the shared-witness goal), `docs/t3_plan.md` (the universal/`¬∃` goal form),
`docs/t5_plan.md` (the head-only universal premise),
`docs/t4_t2_plan.md` (the non-flat ground goal and the nested-disjunction premise),
`docs/t6_plan.md` (the G4 unit-propagation optimization),
`docs/fragment_routing.md` (how a named fragment is declared),
`docs/quality_findings.md` §G (G1–G4), `docs/implementation_plan.md` §8–§10,
`docs/reasoning_roadmap.md`.

## 1. Two independent ceilings

Ankyra is a pipeline: the LLM **translates** a natural-language problem into formal
formulas, and a symbolic procedure **decides** them. Two different things can go
wrong, and they must not be confused:

- **Extraction (model)** — how often the LLM translates correctly. Failure = "the
  translator lied".
- **Coverage (formalism)** — which formulas the committed logic can
  accept and decide at all. Failure = "I don't speak that language", not a wrong
  answer.

They are independent. A perfect translator still stops at the wall if the logic
cannot express half the formulas.

## 2. What coverage means, on a calculator

Think of a calculator that handles `+` and `×` but not `√`. You enter `√9`. It does
not print `3`, and it does not print a wrong number — it says **"I can't do that."**

`out_of_fragment` in Ankyra is exactly this "I can't do that". The engine refuses
*not because it failed to find an answer, but because it cannot express the task* in
its logic. This is a deliberate choice: a silent drop would be a lie.

## 3. The FOLIO-L2 coverage wall, concretely

On the committed L2 tier a (45 gold problems), **24/45 formulas were outside the
committed fragment** when this plan was written (1/45 after Tier-1 T1, T3, T5, T4, T2
and T6, §6). They fall into two families.

**(a) The engine refuses — 12 rows — covered by T5.** They all contain the same shape,
a *universal disjunctive fact*:

> `∀x (Rabbit(x) ∨ Squirrel(x))` — "every individual is a rabbit or a squirrel".
> Real rows: `∀x (FemaleTennis…(x) ∨ MaleTennis…(x))`,
> `∀x (Study(x) ∨ Teach(x))`, `∀x (ZahaHadidDesignStyle(x) ∨ KellyWearstlerDesignStyle(x))`, …

To use such a sentence you must instantiate it **for every individual in the story**
("Tom is a rabbit or a squirrel", "Dick is a rabbit or a squirrel", …). The original
grounding only instantiated the variables that appear in a rule's *body*; here the
whole sentence is a head, and it was refused as `unsafe_rule`. This was **not a
five-minute fix**: the ground term pool mixes individuals with class names (`rabbit`,
`squirrel`), and naively instantiating over all of them fabricates proofs. **T5**
(`docs/t5_plan.md`) resolves it: the head-only variable is grounded over the *individual
domain* (the pool minus the `is_a` objects / class names), with a synthetic soundness
control; the 12 rows are decided, 0 grounded false proofs.

**(b) The formula has no representation — 12 rows.** The structure itself is absent
from the IR (11 of the 12 are now covered by T1/T3/T4/T2; one malformed annotation
remains):

| sub-case | rows | example |
|---|---|---|
| shared-witness existential goal — **T1 done** | 4 | `∃x (CityIn(butte, x) ∧ CityIn(pierre, x))` — *one* `x` satisfies both; splitting into two independent questions is weaker and wrong |
| existential premise with a nested disjunction — **T2 done** | 3 | `∃x (GetMonkeypox(x) ∧ (Fever(x) ∨ Headache(x) ∨ …))` |
| universal / `¬∃` goal — **T3 done** | 2 | `∀x (Pet(x) → ¬Cat(x))` ("no pets are cats"), `¬∃x (FinancialAid(x))` |
| non-flat compound/conditional goal — **T4 done** | 2 | `Cute(rock) ∧ Still(rock) → Turtle(rock) ∧ Skittish(rock)` (a conjunction of clauses, not flat `∧`/`∨`) |
| malformed annotation | 1 | a stray `)` in the dataset — not our bug |

## 4. An honest refusal is not an error

Faced with `∀x (Rabbit(x) ∨ Squirrel(x))`, the engine has two options: silently drop
the sentence and answer anyway (lying), or refuse. It refuses. That is what keeps the
word `proven` meaningful — there is no guess behind it. `out_of_fragment` costs
**recall**, never **soundness**.

## 5. Reading the gold-fed numbers

From `docs/folio_gold_fed.md` (FOLIO L2 tier a, 45):

| verdict source | correct |
|---|---|
| text-fed (live LLM extraction) | 25/45 |
| gold-fed (perfect formulas, L2 procedure) | 42/45 |
| gold `out_of_fragment` | 1/45 |

The older `gold-fed < text-fed` was **not a paradox**: the live path sometimes "won"
hard rows by *simplifying the hard construct away* and answering — occasionally
correctly, three times wrongly — while the gold path refused to guess. After
T1/T3/T5/T4/T2 and T6 the gold path leads (42 vs 25). Restricted to the **44 rows the
committed L2 procedure covers, gold-fed is 42/44 versus text-fed 25/44**: wherever the
engine *can* decide, it already beats the translator. (Numbers after Tier-1
T1/T3/T5/T4/T2/T6, `docs/t4_t2_plan.md` §15, `docs/t6_plan.md` §12.)

So the dominant wall is **coverage**, not language.

## 6. The plan — Tier-1 lowering (no new decision procedure)

Per `D-FE-3`, Tier-1 constructs **reuse the existing bounded clausal procedure**
(`ANKYRA_LOGIC`); the work is IR/extraction/lowering, not new semantics. Each item
enters as a **named fragment** under `docs/fragment_routing.md`: a `FragmentFeature`,
a capability, an off-by-default flag, and a synthetic gate in `evals.l2_synthetic`,
then a re-measured gold-fed bound. Estimated yield is the count of the 24
out-of-fragment rows whose *first* blocker is that item.

| # | item | yield | locus | soundness note |
|---|---|---|---|---|
| T1 | shared-witness existential goal `∃x (A(x) ∧ B(x))` — **DONE** | 4 | `Query.goals` with one shared binding; `engine/verify.py` | negative of the goal is `∀x ¬(A∧B)` = `¬A ∨ ¬B` for all x; refute per witness |
| T2 | existential premise with nested disjunction `∃x (A(x) ∧ (B∨C))` — **DONE** | 3 | `Existential` (a disjunctive part) + `engine/clause.py` | Skolemize, emit a disjunctive ground clause over the fresh constant |
| T3 | universal / conditional / `¬∃` goal form (G3) — **DONE** | 2 | `Query.goal_mode="forall"` + `engine/verify.py` | supported at a *fresh* constant (universal generalization); refuted by one named witness |
| T4 | non-flat compound / conditional goal — **DONE** | 2 | target formula (CNF/DNF over literals), not only flat `all`/`any` | general flat-goal shape; keeps `proven` sound |
| T5 | head-only grounding `∀x (A(x) ∨ B(x))` — **DONE** | 12 | `engine/clause.py:_groundings` | head-only variables range over the **individual domain** (pool minus `is_a` objects); a class name is not a universe element, so instantiating there would fabricate proofs |
| T6 | G4 resolution budget / ground unit propagation — **DONE** | 2 covered | `engine/resolution.py` | exhaustion stays an honest `insufficient`; every propagation is a real resolution edge |
| — | malformed annotation | 1 | — | not fixable (data) |

Reachable but absent from the committed L2 sample: **2a** `↔`/`⊕` lowering (two
clauses / `(A∨B)∧(¬A∨¬B)`), **2c** multi-variable quantification over finite domains
(generalize grounding/witness enumeration). Kept on the list so the fragment is
declared once, not per-id.

**T1 done.** A conjunctive existential conclusion with a shared witness is now a
**joint `all` goal**: one witness assignment is enumerated and every conjunct must hold
under it; the group is `refuted` when the conjunction is unsatisfiable for every
witness (`engine/verify.py`, `refute_conjunction` in `engine/resolution.py`). FOLIO L2
tier a gold-fed: `out_of_fragment` **24 → 20**, gold-fed **17 → 21/45**, coverage
**21 → 25/45**, covered gold-fed **17/21 → 21/25**, **0 grounded false proofs**
(`docs/t1_plan.md`, `docs/folio_gold_fed.md` §3). The feature is named `shared_witness`
in the fragment (`docs/fragment_routing.md`), decided by the existing `clausal`
capability (`ANKYRA_LOGIC`) with no new flag.

**T3 done.** A universal clause goal `∀x (l₁ ∨ … ∨ lₙ)` — subsuming `∀x (A→B)` and
`¬∃x φ` — is now decided: **supported** by assuming the negated clause at a *fresh*
constant and refuting it (universal generalization), **refuted** by one named witness
that falsifies every literal (`engine/verify.py`, `_universal_outcome`;
`Query.goal_mode="forall"`). The fresh constant is what keeps the positive direction
sound: proving `∀` over the named pool alone would accept the non-entailed
`A(rex) ∧ B(rex) ⊢ ∀x(A→B)`. FOLIO L2 tier a gold-fed: `out_of_fragment` **20 → 18**,
gold-fed **21 → 23/45**, coverage **25 → 27/45**, covered gold-fed **21/25 → 23/27**,
**0 grounded false proofs** (`docs/t3_plan.md`, `docs/folio_gold_fed.md` §3). The feature
is named `universal_goal` in the fragment, decided by the existing `clausal` capability
(`ANKYRA_LOGIC`) with no new flag.

**T5 done.** A head-only universal premise `∀x (l₁(x) ∨ … ∨ lₙ(x))` — and a Horn
`∀x A(x)`, and a body rule with an extra head variable — is now decided: the head-only
variable is grounded over the **individual domain** `D_ind` = pool \ `is_a` objects
(`engine/clause.py:_individual_pool`, `_groundings`); body variables keep the full pool
(a class variable must reach class names). Class names are lowered unary predicates,
not elements of the universe, so instantiating a universal there is not a consequence
of it and can both fabricate proofs and block legitimate refutations. FOLIO L2 tier a
gold-fed: `out_of_fragment` **18 → 6**, gold-fed **23 → 35/45**, coverage
**27 → 39/45**, covered gold-fed **23/27 → 35/39**, **0 grounded false proofs**
(`docs/t5_plan.md`, `docs/folio_gold_fed.md` §3). The feature is named `head_only_rule`
in the fragment, decided by the existing `clausal` capability (`ANKYRA_LOGIC`) with no
new flag.

**T4 done.** A general **ground** goal formula `φ` is now decided as
`Query.goal_clauses` (its CNF) with `goal_mode="cnf"`: **supported** when `T ∪ {¬φ}` is
unsatisfiable (`refute_support` on `CNF(¬φ)`, the cross-product of the negated
literals), **refuted** when `T ∪ {φ}` is unsatisfiable (`refute_support` on `CNF(φ)`),
`contradiction` when both (`engine/verify.py`, `_cnf_outcome`). Deciding a disjunction
by a disjunct would be unsound and is rejected. FOLIO L2 tier a gold-fed:
`0073` → `supported`/`True`, `0020` → `refuted`/`False`. The feature is named
`clause_goal` in the fragment, decided by the existing `clausal` capability
(`ANKYRA_LOGIC`) with no new flag. This resolves the open decision **T-D2**.

**T2 done.** An existential premise `∃x φ(x)` whose body `φ` is a CNF over literals in
`x` is now Skolemized to a unit clause per atom and a ground clause per disjunctive
group (`Existential.disjunctions`, `engine/clause.py:_add_existentials`). FOLIO L2
tier a gold-fed: `0006` → `yes`, `0007`/`0008` → `unknown`. The feature is named
`existential_disjunction` in the fragment, decided by the existing `clausal` capability
(`ANKYRA_LOGIC`) with no new flag.

**T4 + T2 gate.** FOLIO L2 tier a gold-fed: `out_of_fragment` **6 → 1** (only the
malformed `0109`), gold-fed **35 → 40/45**, coverage **39 → 44/45**, covered gold-fed
**35/39 → 40/44**, **0 grounded false proofs** (`docs/t4_t2_plan.md`,
`docs/folio_gold_fed.md` §3).

**T6 done.** A ground unit-propagation fixpoint now runs before the general
set-of-support loop in `refute_support` (`engine/resolution.py`): each propagation is
a real binary resolution recorded in the proof DAG, shares the step budget, and an
empty resolvent is the refutation. This decides the two `logic_budget:exhausted` rows
(`0009`, `0010`). FOLIO L2 tier a gold-fed: gold-fed **40 → 42/45**, covered gold-fed
**40/44 → 42/44**, `out_of_fragment` **1** (only `0109`), **0 grounded false proofs**;
LLM-free gates `evals.l2_synthetic` (56/56) and `evals.routing_synthetic` (17/17).
No new flag or `FragmentFeature` (a prover optimization, not a construct). The feature
is internal; the row-level record is `docs/t6_plan.md`.

## 7. Order and open decisions

- **Order.** Tier-1 is **complete** (T1, T3, T5, T4, T2, T6 done); the only remaining
  `out_of_fragment` row is the malformed annotation `0109`. Extraction
  G1–G4 (`docs/quality_findings.md` §G) runs on the rows the method already covers, in
  parallel, not first.
- **Open decision T-D1 (resolved).** T5's domain: ground head-only variables over the
  **individual domain** (`D_ind` = pool minus `is_a` objects), not the full pool. The
  soundness argument and the synthetic negative control (`head-only-03`) are in
  `docs/t5_plan.md` §4/§8.
- **Open decision T-D2 (resolved).** T4's goal form: a general ground goal **formula**
  stored as its CNF (`Query.goal_clauses`, `goal_mode="cnf"`), not new `goal_mode`
  values (`docs/t4_t2_plan.md` T4-D1).
- **Open decision T-D3 (resolved).** One `clausal` capability with per-item named
  fragments and synthetic gates — the pattern set by T1 and followed by T3/T5/T4/T2
  (`docs/t1_plan.md` T1-D3, `docs/t3_plan.md` T3-D3).

## 8. Guardrails

- A construct enters only as a **named fragment** (`docs/fragment_routing.md`); never
  an ad-hoc branch. Beyond the finite domain it stays an honest `out_of_fragment`.
- **Never lower the semantics to pass a row.** Collapsing `∀x (P(x) → ¬Cat(x))` to the
  ground `¬is_a(pet, cat)` proves a sound fact about the *wrong* target
  (`docs/folio_ceilings.md` §8).
- A head-only universal never ranges over `is_a` objects (class names): they are not
  elements of the universe (`docs/t5_plan.md` §4).
- A disjunction is never decided by a disjunct: a non-flat goal is decided by
  unsatisfiability of `T ∧ ¬φ` / `T ∧ φ`, and a nested disjunction is never dropped
  (`docs/t4_t2_plan.md` §4/§6).
- No per-id tuning; the gold-fed bound (`evals.analyze_folio --subset l2`) is the
  free gate after each item: coverage up, **0 grounded false proofs**.
- Budget: no new live LLM run without an explicit, separate decision
  (`docs/reasoning_roadmap.md` §4).
