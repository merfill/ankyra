# Comparison results - Phase 2

Same task rows, same model/provider (`routerai`, `~deepseek/deepseek-v4-flash-latest`).
Each system runs its own native decoding: Ankyra greedy (T=0.1), Logic-LM greedy
(T=0) + self-refinement where implemented, LINC 8-shot / 10 samples / T=0.8 /
majority. Full analysis and caveats: [`../../docs/comparison.md`](../../docs/comparison.md).

Solver accuracy = correct / all rows (non-executable programs and abstentions
count as wrong). Coverage = executed / all rows. Confidently wrong = executed
and incorrect.

## Solver accuracy

| Stage | Collection (n) | Ankyra | Logic-LM | Logic-LM + refine | LINC (native) |
|---|---|---|---|---|---|
| L0 | ProofWriter tier A (45) | **100.0%** | 8.9% | - (PyKE) | 86.7% |
| L0 | ProofWriter tier D (300) | **99.0%** | 6.7% | - (PyKE) | 28.3%\* |
| L1 | ProntoQA tier a (48) | **100.0%** | 41.7% | - (PyKE) | - |
| L2 | FOLIO L2+negation (58) | 69.0% | 6.9% | 39.7% | **74.1%** |
| L3 | AR-LSAT eval (30) | **76.7%** | 53.3% | 63.3% | - |

## Coverage (executed / all)

| Collection (n) | Ankyra | Logic-LM | Logic-LM + refine | LINC (native) |
|---|---|---|---|---|
| ProofWriter tier A (45) | 100% | 13.3% | - | 100% |
| ProofWriter tier D (300) | 100% | 7.7% | - | 32.0%\* |
| ProntoQA tier a (48) | 100% | 41.7% | - | - |
| FOLIO L2+negation (58) | 98.3% | 6.9% | 55.2% | 98.3% |
| AR-LSAT eval (30) | 100% | 60.0% | 70.0% | - |

## Confidently wrong (executed and incorrect)

| Collection | Ankyra | Logic-LM | Logic-LM + refine | LINC (native) |
|---|---|---|---|---|
| ProofWriter tier A | 0 | 2 | - | 6 |
| ProofWriter tier D | 0 | 3 | - | 11\* |
| ProntoQA tier a | 0 | 0 | - | - |
| FOLIO | 0 | 0 | 9 | 14 |
| AR-LSAT | 0 | 2 | 2 | - |

\* LINC tier D was run greedy (1 sample); native was budgeted for tier A and
FOLIO only. Greedy tier-A LINC is 22.2%, so tier D is a lower bound.

## Key evidence

- **Gold-fed back-ends** (no model): LINC/Prover9 54/58 = 93.1% on FOLIO;
  Logic-LM/Prover9 47/58 = 81.0%. Solvers are fine; translation is the wall.
- **Failure attribution**: on the model's own programs, the dominant failures
  are surface syntax (Markdown bullets, `x` vs `$x`), not wrong reasoning.
- **Model isolation** (LINC's own ProofWriter test, fixed 60-row subset). Only
  the deepseek column is our run; the GPT values are recomputed from LINC's
  committed generations (same task/config): GPT-4 100%, GPT-3.5 96.7%,
  deepseek-flash 85.0%.
- **Decoding ablation**: LINC FOLIO 34.5% -> 74.1% and ProofWriter A 22.2% ->
  86.7% when moved to its native sampling; Logic-LM best-of-5 at T=0.8 produced
  0/225 executable programs.

## Artifacts

- `linc_*_native.json` - LINC native protocol; `linc_*.json` (no suffix) - greedy.
- `linc_own_proofwriter_stride6.json` - model-isolation run.
- `*_deepseek-v4-flash*_backup-random.json` - Logic-LM per-row output
  (`flag` = success / parsing error / execution error); `*-multi-*` is best-of-5.
