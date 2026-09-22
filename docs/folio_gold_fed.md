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
  | `∀x (A(x) ∨ B(x))` premise (head-only) | conditionless `Rule` with a head-only variable (T5) |
  | `¬(A ∧ B)` / `¬(A ∨ B)` | De Morgan, pushed to literals |
  | `∃x (φ ∧ …)` premise | `Theory.existentials` |
  | ground / `∧` / `∨` / `∃x P(x)` conclusion | `Query.target`, or `Query.goals` + `goal_mode` |
  | `∀x (l₁ ∨ … ∨ lₙ)` conclusion (`∀x(A→B)`, `¬∃x φ`) | `Query.goals` + `goal_mode="forall"` (T3) |

  A formula outside the committed shape raises `FolParseError` → an honest
  `out_of_fragment`, never a guessed encoding. Scope limits: non-clause/conditional
  goals, an existential premise with a nested disjunction, nested quantifiers,
  function terms. A conjunctive existential conclusion with a shared witness
  (`∃x (A(x) ∧ B(x))`) was added to the fragment by Tier-1 item **T1**
  (`docs/t1_plan.md`): it is a joint `all` goal, decided with one witness for all
  conjuncts. A universal clause conclusion was added by **T3** (`docs/t3_plan.md`):
  it is a `goal_mode="forall"` goal, supported at a fresh constant and refuted by one
  named witness. A head-only universal premise (`∀x (A(x) ∨ B(x))`) was added by
  **T5** (`docs/t5_plan.md`): the head-only variable is grounded over the individual
  domain (the pool minus the `is_a` objects / class names).
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
| gold-fed open (= closed) | 35/45 |
| gold `out_of_fragment` | 6/45 |

Coverage (rows the committed L2 procedure can express and decide) is **39/45** —
Tier-1 item **T1** (`docs/t1_plan.md`) added four shared-witness rows
(`0033`, `0058`, `0059`, `0069`), **T3** (`docs/t3_plan.md`) added the
universal/`¬∃` rows (`0045`, `0107`), and **T5** (`docs/t5_plan.md`) added the twelve
head-only-universal rows. On the covered rows:

| label | gold-fed | text-fed |
|---|---|---|
| True | 12/13 | 6/13 |
| False | 10/13 | 4/13 |
| Uncertain | 13/13 | 12/13 |
| **total** | **35/39** | **22/39** |

No grounded false proof: every wrong gold answer is an abstention — `insufficient`
from the resolution budget (G4) or `unsupported`; none is a wrong determinate
answer.

The 6 remaining out-of-fragment rows:

- **6 the parser cannot express:** compound/conditional conclusions (nested `∧`/`∨`
  or an implication as the goal, T4: `0073`, `0020`), an existential premise with a
  nested disjunction (`∃x (A(x) ∧ (B(x) ∨ …))`, T2: `0006`, `0007`, `0008`), and one
  malformed annotation (`0109`). No `unsafe_rule` row remains.

## 4. Interpretation and decision

The raw gold-fed number (35/45) now leads text-fed (25/45); the remaining gap is the
6 honest abstentions (T4 goal, T2 premise, one malformed row) and the text-fed path's
abstraction errors. Restricted to the rows the committed L2 procedure covers,
**gold-fed (35/39) far leads text-fed (22/39)**.

Conclusion: the dominant ceiling on the L2 slice remains **coverage (the method)**,
not the language, and Tier-1 lowering closed most of it (T1/T3/T5: coverage
27→39/45). Per `docs/folio_ceilings.md` §7 and `D-FE-1`/`D-FE-2`, the remaining
Tier-1 items are T4 (non-flat goal) and T2 (nested-disjunction existential premise);
extraction G1–G4 remains worth doing on the rows the method already covers. The
explained plan, per-item yields and open decisions are in `docs/coverage_ceiling.md`.

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
