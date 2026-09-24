# FOLIO scoreboard — the single integral view

Status: **canonical FOLIO evaluation summary** (documentation only, no code). This is
the one place that reconciles every FOLIO figure. The collection mechanics stay in
`docs/folio.md`, the gold-fed method in `docs/folio_gold_fed.md`, the two-ceiling model
in `docs/folio_ceilings.md`, and the coverage plan in `docs/coverage_ceiling.md`.

Canonical language: English; Russian mirror: `docs/folio_scoreboard_ru.md`.
Related: the four notes above, `docs/reasoning_roadmap.md` (L2),
`docs/implementation_plan.md` §10 (gating a composite benchmark),
`docs/fragment_routing.md` (the declared-fragment contract).

## 1. Why there is no single FOLIO score

FOLIO cannot have one headline number without lying about what was measured:

1. **It is a composite benchmark by construction.** Its gold FOL spans L0 (atoms,
   universal implications), L1 (negation), L2 (`∨`, `∃`) and constructs outside every
   committed stage (`⊕`, `↔`, equality, function terms, multi-variable quantification).
   A collection whose gold mixes formalisms is a gate for several stages, never one
   scoreboard (`docs/implementation_plan.md` §10).
2. **Open world.** 38.5% of labels are `Unknown`; a trivial "always `Unknown`" scores
   38.5%, so raw accuracy is dominated by the majority class.
3. **`out_of_fragment` is an abstention, not an error.** Counting it as wrong (or as a
   correct `unknown`) both corrupt the number. It costs recall, never soundness.
4. **Two independent ceilings.** *Coverage* (which formulas the committed logic can
   express at all) and *extraction* (how often the LLM translates a covered row) move
   independently; a single scalar conflates them.

The integral view is therefore a small **dashboard**, reproducible and LLM-free for the
method side.

## 2. The dashboard — four quantities

| # | quantity | definition | axis |
|---|---|---|---|
| 1 | **Coverage** | in-committed-fragment rows / all rows | formalism |
| 2 | **Method bound** | gold-fed correct / covered (LLM-free) | formalism |
| 3 | **Extraction** | text-fed correct / covered (live) | model |
| 4 | **Soundness** | grounded false proofs (`= 0`, an invariant) | engine |

Never collapse 2 and 3 into one number: their difference *is* the extraction headroom.

## 3. Whole-collection stratification (FOLIO v0.0 validation, 204 rows)

Reproduce the tally with `uv run python -m evals.recon_l2 --folio-only` (LLM-free).

| bucket | rows | note |
|---|---|---|
| validation total | 204 | |
| in the L1-negation fragment | 13 | gate 1, all committed (`folio_negation_tier_a.jsonl`) |
| in the L2 fragment (`∨`/`∃`, no eq/`⊕`/`↔`/multivar) | 93 | gate 2; 45 committed, **48 unrun** (budget) |
| in one of the two committed gate fragments | 106 | a **lower bound** on expressible rows |
| not in either gate fragment | ≤ 98 | carry `⊕`/multivar/`↔` (or an L0-only shape not sampled); reported `out_of_fragment`, not a failure |

Construct tally (overlapping within a row): negation 157, disjunction 76, existential
76, `⊕` 43, multivar 33, `↔` 6.

Consequences:

- **Coverage of the two committed gates ≈ 106/204 ≈ 52%.** The complement is the
  deliberate design boundary, not a pending bug.
- **48 of the 93 L2-fragment rows were never run** — a budget artifact, not a failure.
  Any "FOLIO accuracy" that silently uses 45 or 58 rows must say so.

## 4. The committed gates (current, reproducible)

Numbers below are `evals.analyze_folio` run on the committed samples over the local
saved traces (`evals/out/folio/`, git-ignored). The **gold-fed / coverage** columns are
reproducible from the repository alone; the **text-fed** columns need the saved traces
(or a fresh live run).

### 4.1 L1 negation slice — 13 rows

| metric | value |
|---|---|
| coverage | 13/13 (0 `out_of_fragment`) |
| method (gold-fed open) | 12/13 (closed: 10/13) |
| extraction (text-fed) | 11/13 |
| categories | ok 11, extraction 1, fragment 1 |
| soundness | 0 grounded false proofs |

Per label (text / gold): True 4/4 · 4/4, False 3/5 · 4/5, Uncertain 4/4 · 4/4.

### 4.2 L2 tier a — 45 rows

| metric | value |
|---|---|
| coverage | 44/45 (1 `out_of_fragment`: the malformed `0109`) |
| method (gold-fed open = closed) | 42/45; covered 42/44 |
| extraction (text-fed) | 29/45; covered 29/44 |
| categories | ok 29, extraction 13, fragment 3 |
| soundness | 0 grounded false proofs |

Per label (text / gold): True 9/15 · 15/15, False 5/15 · 12/15, Uncertain 15/15 · 15/15.

**Reading.** On covered rows the method bound is 42/44 and extraction 29/44: the ~13-row
gap is the extraction headroom, the dominant remaining FOLIO work (`docs/g1_g4_plan.md`).
Coverage is essentially closed for this slice (only `0109`, a dataset typo).

## 5. Number reconciliation

Every FOLIO figure quoted in the repository, with its denominator and why it differs:

| figure | source | denominator | meaning | current |
|---|---|---|---|---|
| 24/45 out-of-fragment | `folio_ceilings.md` §4 | 45 | coverage **before** Tier-1 (coverage 21/45) | **1/45** |
| gold-fed 17/45 | `folio_ceilings.md` §4 | 45 | method at diagnostic time | **42/45** |
| text-fed 25/45 | `folio_gold_fed.md` §3 | 45 | extraction at the Tier-1-era engine | **29/45** |
| gold-fed 42/45, covered 42/44 | `coverage_ceiling.md` §5 | 45 / 44 | after T1,T3,T5,T4,T2,T6 | unchanged |
| live 26/44 | `folio.md` §10 | 44 | the original **live** run | text-fed replay now 29/44 |
| 7/13 → 11/13 | `folio.md` §9 | 13 | neg slice: Horn path → clausal L2 path | 11/13 |
| gold-fed 12/13 open, 10/13 closed | this doc | 13 | clausal L2 path on the neg slice | — |

Two distinct causes of drift, both benign:

- **Engine evolution (no new LLM call).** Tier-1 (T1/T3/T5/T4/T2/T6) and later builder
  fixes let the *current* engine decide more of the *same saved extraction*; the
  text-fed replay rises (25 → 29) while the recorded live score stays at its run date.
- **Path change.** The neg slice was re-scored from the Horn path (7/13) to the clausal
  L2 path (11/13), per `docs/implementation_plan.md` §8 item 29.

`text-fed` (saved score) and `text-fed (replay)` (current engine on the saved
extraction) agree today; when the extraction prompt/schema changes, a live re-run is the
only way to update the saved score.

## 6. Reproduce

LLM-free (from the repository):

```
uv run python -m evals.recon_l2 --folio-only                       # the construct tally
uv run python -m evals.analyze_folio --subset l2                    # gold-fed + replay
uv run python -m evals.analyze_folio --subset negation              # gold-fed + replay
uv run pytest tests/test_evals_folio_fol.py -q                      # the parser/gold gate
```

Live (needs the paid extractor; budget decision, `docs/reasoning_roadmap.md` §4):

```
uv run python -m evals.folio --subset {negation,l2} [--jobs 5]     # writes evals/out/folio/
```

## 7. Non-goals and guardrails

- **No whole-collection FOLIO headline.** Full coverage is unreachable by design:
  constructs like equality/functions lie outside every committed stage, and full FOL
  entailment is only semi-decidable.
- **No lowering to pass a row.** Collapsing `∀x (P(x) → ¬Cat(x))` to a ground
  `¬is_a(pet, cat)` proves a sound fact about the wrong target
  (`docs/folio_ceilings.md` §8).
- **No per-id tuning.** Improvements come from the general extraction contract and named
  fragments under the declared-fragment contract.
- **`out_of_fragment` is an abstention**, reported explicitly and never scored as a
  correct `unknown`.
