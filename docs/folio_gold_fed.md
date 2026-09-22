# FOLIO gold-fed diagnostic — method vs extraction

Status: **implemented and measured** (FOLIO L2 tier a, LLM-free). This note records
the Phase 0 work that extended the gold-FOL diagnostic from the L1 negation shape to
L2 (`∨`/`∃`) and the result that decides the FOLIO priority.

Canonical language: English; Russian mirror: `docs/folio_gold_fed_ru.md`.
Related: `docs/folio.md` (§9–§10), `docs/folio_ceilings.md` (§4, §7),
`docs/folio_extension_plan.md` (§3, Phase 0), `docs/quality_findings.md` §G,
`docs/l2_plan.md`, `docs/implementation_plan.md` §10, `docs/reasoning_roadmap.md`.

## 1. Question

FOLIO has two independent ceilings (`docs/folio_ceilings.md` §3): **coverage**
(formalism — which rows the committed logic can express) and **extraction** (model —
how often the LLM translates a covered row correctly). The live number mixes both
and is therefore ambiguous. The decisive counterfactual is the **gold-fed** bound:
feed the engine the annotated FOL formulas instead of the LLM extraction and measure
method-only accuracy.

- `gold-fed ≫ text-fed` → the limit is the **language** (extraction);
- `gold-fed ≈ text-fed`, both low → the limit is the **method** (coverage).

## 2. Method (LLM-free)

- **`evals/folio_fol.py`** — deterministic parser of the annotated FOL into the
  L1/L2 models: recursive descent with precedence `→` > `∨` > `∧` > `¬` > atom,
  `∀`/`∃`, unicode identifiers (e.g. `Companies’Stocks`), negation normal form and
  CNF. Mapping:

  | gold form | representation |
  |---|---|
  | `A ∧ B → C`, `∀x (A(x) → B(x))` | `Rule(conditions, consequence)` |
  | `∀x (… → B(x) ∨ C(x))`, `A → ¬(B ∨ C)` | `Rule.alternatives` |
  | `A ∨ B → C` | two rules `A → C`, `B → C` |
  | `A ∨ B` (ground) | conditionless `Rule` with `alternatives` |
  | `¬(A ∧ B)` / `¬(A ∨ B)` | De Morgan, pushed to literals |
  | `∃x (φ ∧ …)` premise | `Theory.existentials` |
  | ground / `∧` / `∨` / `∃x P(x)` conclusion | `Query.target`, or `Query.goals` + `goal_mode` |

  A formula outside the committed shape raises `FolParseError` → an honest
  `out_of_fragment`, never a guessed encoding. Scope limits: universal/conditional
  goals, a shared-witness existential conjunction `∃x (A(x) ∧ B(x))`, an existential
  premise with a nested disjunction, nested quantifiers, function terms.
- **`evals/analyze_folio.py`** — `--subset {negation,l2}`. The L2 gold pass runs
  under `setting_overrides(LOGIC="ground")` (the L2 clausal procedure); the negation
  pass stays on the Horn/L1 path. An `out_of_fragment` gold verdict is an abstention
  and is **never scored as a correct `unknown`**.
- **Gate:** `tests/test_evals_folio_fol.py` (parser + gold-run on committed records,
  LLM-free).

Reproduce:

```
uv run python -m evals.analyze_folio --subset l2
uv run python -m evals.analyze_folio --subset negation
```

## 3. Result

### L1 negation (13 in-fragment) — unchanged

| source | correct |
|---|---|
| text-fed | 7/13 |
| gold-fed open | 7/13 |
| gold-fed closed | 8/13 |

Categories: ok 6, semantics 5, fragment 1, extraction 1 — coverage-bound (the `False`
labels need reductio/CWA), as recorded in `docs/folio.md` §9.

### L2 tier a (45) — new

| source | correct |
|---|---|
| text-fed (LLM extraction) | 25/45 |
| gold-fed open (= closed) | 17/45 |
| gold `out_of_fragment` | 24/45 |

Coverage (rows the committed L2 procedure can express and decide) is **21/45**. On
the covered rows:

| label | gold-fed | text-fed |
|---|---|---|
| True | 6/7 | 5/7 |
| False | 5/8 | 4/8 |
| Uncertain | 6/6 | 6/6 |
| **total** | **17/21** | **15/21** |

No grounded false proof: every wrong gold answer is an abstention — `insufficient`
from the resolution budget (G4) or `unsupported`; none is a wrong determinate
answer.

The 24 out-of-fragment rows split evenly:

- **12 the parser cannot express:** compound/conditional conclusions (nested `∧`/`∨`
  or an implication as the goal), an existential premise with a nested disjunction
  (`∃x (A(x) ∧ (B(x) ∨ …))`), shared-witness existential conjunctions
  (`∃x (A(x) ∧ B(x))`), a universal `¬∃` conclusion, and one malformed annotation.
- **12 the engine refuses as `unsafe_rule`:** a universal disjunctive fact
  `∀x (A(x) ∨ B(x))` grounds a head variable its body never binds
  (`engine/clause.py`, `_groundings`).

## 4. Interpretation and decision

The raw gold-fed number (17/45) is below text-fed (25/45) only because 24 rows are
honest abstentions; the text-fed path decides those rows by abstracting the hard
disjunction away and pays with 3 extraction errors. Restricted to the rows the
committed L2 procedure covers, **gold-fed (17/21) leads text-fed (15/21)**.

Conclusion: the dominant ceiling on the L2 slice is **coverage (the method)**, not
the language. Per `docs/folio_ceilings.md` §7 and `D-FE-1`/`D-FE-2`, Tier-1 lowering
(`docs/folio_extension_plan.md` §5) precedes extraction work: universal/conditional
targets (the G3 target form), head-only grounding for `∀x (A(x) ∨ B(x))`, existential
conjunctions, and nested-existential premises. The explained plan, per-item yields and
open decisions are in `docs/coverage_ceiling.md`. Extraction G1–G4 remains worth doing
on the rows the method already covers.

Caveat: this is a **method bound, not a strict upper bound** — a more complex gold
formalization can cost more than the LLM's abstraction (the budget misses and the L2
agreement on `Uncertain` show this). It answers "method vs language", not "what is
achievable".

## 5. Guardrails

- `out_of_fragment` is an honest abstention: it costs recall, never soundness, and is
  never scored as a correct `unknown`.
- Never lower the semantics to pass a row (`∀x (P(x) → ¬Cat(x))` collapsed to the
  ground `¬is_a(pet, cat)` is a sound fact about the wrong target;
  `docs/folio_ceilings.md` §8).
- No per-id tuning; improvements come from the general extraction contract and named
  Tier-1 fragments under the declared-fragment contract
  (`docs/fragment_routing.md`).
