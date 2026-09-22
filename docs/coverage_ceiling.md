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
(§9–§10), `docs/l2_plan.md` (the L2 procedure Tier 1 extends),
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

On the committed L2 tier a (45 gold problems), **24/45 formulas are outside the
committed fragment**. They fall into two families.

**(a) The engine refuses — 12 rows.** They all contain the same shape, a *universal
disjunctive fact*:

> `∀x (Rabbit(x) ∨ Squirrel(x))` — "every individual is a rabbit or a squirrel".
> Real rows: `∀x (FemaleTennis…(x) ∨ MaleTennis…(x))`,
> `∀x (Study(x) ∨ Teach(x))`, `∀x (ZahaHadidDesignStyle(x) ∨ KellyWearstlerDesignStyle(x))`, …

To use such a sentence you must instantiate it **for every individual in the story**
("Tom is a rabbit or a squirrel", "Dick is a rabbit or a squirrel", …). The current
grounding only instantiates the variables that appear in a rule's *body*; here the
whole sentence is a head, and it is refused as `unsafe_rule`. This is **not a
five-minute fix**: the ground term pool currently mixes individuals with class names
(`rabbit`, `squirrel`), and naively instantiating over all of them can manufacture a
false proof. It needs a proper soundness design (separate the individual domain from
the class names, or a fresh-domain semantics).

**(b) The formula has no representation — 12 rows.** The structure itself is absent
from the IR:

| sub-case | rows | example |
|---|---|---|
| shared-witness existential goal | 4 | `∃x (CityIn(butte, x) ∧ CityIn(pierre, x))` — *one* `x` satisfies both; splitting into two independent questions is weaker and wrong |
| existential premise with a nested disjunction | 3 | `∃x (GetMonkeypox(x) ∧ (Fever(x) ∨ Headache(x) ∨ …))` |
| universal / `¬∃` goal | 2 | `∀x (Pet(x) → ¬Cat(x))` ("no pets are cats"), `¬∃x (FinancialAid(x))` |
| non-flat compound/conditional goal | 2 | `Cute(rock) ∧ Still(rock) → Turtle(rock) ∧ Skittish(rock)` (a conjunction of clauses, not flat `∧`/`∨`) |
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
| gold-fed (perfect formulas, L2 procedure) | 17/45 |
| gold `out_of_fragment` | 24/45 |

`gold-fed < text-fed` is **not a paradox**. The live path sometimes "wins" hard rows
by *simplifying the hard construct away* and answering — occasionally correctly,
three times wrongly. The gold path refuses to guess on 24 rows. Restricted to the
**21 rows the committed L2 procedure covers, gold-fed is 17/21 versus text-fed
15/21**: wherever the engine *can* decide, it already beats the translator.

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
| T2 | existential premise with nested disjunction `∃x (A(x) ∧ (B∨C))` | 3 | `Existential` (a disjunctive part) + `engine/clause.py` | Skolemize, emit a disjunctive ground clause over the fresh constant |
| T3 | universal / conditional / `¬∃` goal form (G3) | 2 | `QuestionStructure` + `Query` target form; `engine/verify.py` | negate the goal, Skolemize, refute (a universal goal is refuted by one witness) |
| T4 | non-flat compound / conditional goal | 2 | target formula (CNF/DNF over literals), not only flat `all`/`any` | general flat-goal shape; keeps `proven` sound |
| T5 | head-only grounding `∀x (A(x) ∨ B(x))` | 12 | `engine/clause.py:_groundings` | **sensitive**: separate the individual domain from class names before instantiating head-only variables, or the extra instances can fabricate proofs |
| T6 | G4 resolution budget / unit propagation | 2 covered (+ enables others) | `engine/resolution.py` | exhaustion stays an honest `insufficient` |
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

## 7. Order and open decisions

- **Order (proposal).** Start with the *goal-form family* (T1 **done**, T3, T4: 8
  rows), which is IR-only and carries no new semantics (`D-FE-3`), then **T2** (3
  rows), then **T5** (12 rows, the largest but soundness-sensitive, so it waits for
  its design), then **T6**. Extraction G1–G4 (`docs/quality_findings.md` §G) runs on
  the rows the method already covers, in parallel, not first.
- **Open decision T-D1.** T5's domain: keep the strict refusal, or split the pool into
  individuals vs class names and ground head-only variables over individuals only?
  Needs a soundness argument and a synthetic negative control before any live run.
- **Open decision T-D2.** T4's goal form: a general goal *formula* (CNF/DNF) versus
  more `goal_mode` values. The former is more expressive but touches `Query` broadly.
- **Open decision T-D3.** Whether T1/T2/T3 land as one fragment or three, given they
  all extend `ANKYRA_LOGIC` (a single flag) but each needs its own synthetic gate.

## 8. Guardrails

- A construct enters only as a **named fragment** (`docs/fragment_routing.md`); never
  an ad-hoc branch. Beyond the finite domain it stays an honest `out_of_fragment`.
- **Never lower the semantics to pass a row.** Collapsing `∀x (P(x) → ¬Cat(x))` to the
  ground `¬is_a(pet, cat)` proves a sound fact about the *wrong* target
  (`docs/folio_ceilings.md` §8).
- No per-id tuning; the gold-fed bound (`evals.analyze_folio --subset l2`) is the
  free gate after each item: coverage up, **0 grounded false proofs**.
- Budget: no new live LLM run without an explicit, separate decision
  (`docs/reasoning_roadmap.md` §4).
