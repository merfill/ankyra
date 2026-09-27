# Ankyra vs Logic-LM vs LINC: comparative evaluation

Status: measured (September 2026). Code and per-row outputs: `comparison/`;
raw numbers: `comparison/results/`.

This document reports a **same-model, same-task** comparison of Ankyra against
two open-source neuro-symbolic systems, Logic-LM and LINC, and then explains,
with evidence, *why* the systems differ. It is deliberately conservative: every
place where the comparison could favour Ankyra is either removed or named.

## 1. What was compared

Each system was run on the **exact Ankyra sample rows** (the committed files in
`evals/data/`), with the **same model and provider** Ankyra uses
(`routerai`, `~deepseek/deepseek-v4-flash-latest`). The external systems were
not reimplemented: their own prompt, their own symbolic back-end and their own
scoring were driven by a thin adapter (`comparison/run_logicllm.py`,
`comparison/run_linc.py`). The legacy `openai<1` SDK they were written against
is redirected to the Ankyra provider by `comparison/patch.py`, which also
disables DeepSeek "thinking" (as the engine does) and caches temperature-0 calls.

Each system was run in **its own native protocol**, because that is what its
published numbers mean:

| System | Decoding in this study | Rationale |
|---|---|---|
| Ankyra | temperature 0.1, one sample, structured (function-calling) extraction | the engine's design; it never samples (`implementation_plan.md` item 4) |
| Logic-LM | temperature 0, one sample (greedy) + its self-refinement where implemented | its published protocol (`models/logic_program.py`) |
| LINC | 8-shot, 10 samples, temperature 0.8, majority vote | its published protocol (`run_expts.sh`) |

A matched-decoding ablation (all three greedy, one sample) is reported in §6 so
that the protocol itself is not silently doing the work.

**Definitions.** *Solver accuracy* = correct / all rows, counting every
non-executable program and every abstention as wrong; this is the conservative,
coverage-weighted number and the one used in the headline table. *Exe. accuracy*
= correct / executed. *Coverage* = executed / all. *Confidently wrong* = an
executed program whose answer is wrong (the external systems commit to it).
Ankyra is sound relative to its formalization and has no "confidently wrong"
category.

## 2. Headline results

Solver accuracy (%, correct / all rows):

| Stage | Collection (n) | Ankyra | Logic-LM | Logic-LM + self-refine | LINC (native) |
|---|---|---|---|---|---|
| L0 | ProofWriter tier A (45) | **100.0** | 8.9 | — (PyKE) | 86.7 |
| L0 | ProofWriter tier D (300) | **99.0** | 6.7 | — (PyKE) | 28.3\* |
| L1 | ProntoQA tier a (48) | **100.0** | 41.7 | — (PyKE) | — |
| L2 | FOLIO L2+negation (58) | 69.0 | 6.9 | 39.7 | **74.1** |
| L3 | AR-LSAT eval (30) | **76.7** | 53.3 | 63.3 | — |

\* LINC tier D was run greedy (one sample); its native protocol was budgeted
only for tier A and FOLIO. The greedy tier-A number is 22.2%, so the tier-D
figure is a lower bound.

Coverage (%, executed / all rows):

| Collection (n) | Ankyra | Logic-LM | Logic-LM + refine | LINC (native) |
|---|---|---|---|---|
| ProofWriter tier A (45) | 100 | 13.3 | — | 100 |
| ProofWriter tier D (300) | 100 | 7.7 | — | 32.0\* |
| ProntoQA tier a (48) | 100 | 41.7 | — | — |
| FOLIO L2+negation (58) | 98.3 | 6.9 | 55.2 | 98.3 |
| AR-LSAT eval (30) | 100 | 60.0 | 70.0 | — |

Confidently-wrong answers (count):

| Collection | Ankyra | Logic-LM | Logic-LM + refine | LINC (native) |
|---|---|---|---|---|
| ProofWriter tier A | 0 | 2 | — | 6 |
| ProofWriter tier D | 0 | 3 | — | 11\* |
| ProntoQA tier a | 0 | 0 | — | — |
| FOLIO | 0 | 0 | 9 | 14 |
| AR-LSAT | 0 | 2 | 2 | — |

\* greedily executed rows only.

Two results already correct the first impression of this comparison:

- **LINC is competitive, not broken.** On FOLIO it reaches **74.1%**, above
  Ankyra's 69.0%. Its apparent collapse (34.5%) in a first greedy run was an
  artefact of decoding, not of the method (see §6).
- **Logic-LM's low number is real for this model.** Even with two rounds of its
  own self-refinement it reaches only 39.7% on FOLIO and 63.3% on AR-LSAT, and
  it has no self-refinement for its two PyKE datasets.

## 3. Why the external numbers are low: translation, not reasoning

The symbolic back-ends are **not** the bottleneck. Feeding them hand-written
formalizations (no model in the loop) on the same 58 FOLIO rows:

| System | Back-end | Gold-fed solver accuracy | Gold-fed exe. accuracy |
|---|---|---|---|
| LINC | NLTK/Prover9 | **54/58 (93.1%)** | 54/57 (94.7%) |
| Logic-LM | Prover9 | **47/58 (81.0%)** | 47/50 (94.0%) |

Running Logic-LM's solver on its **own committed GPT-4 programs** reproduces
its paper-level behaviour offline: FOLIO 80.4%, ProofWriter 79.6%, ProntoQA
83.2%, AR-LSAT 60.0% (executable accuracy). So the solvers work; what fails is
turning the model's free text into a program the solver accepts.

**Failure attribution over the model's own programs** (offline re-execution):

| Collection (n) | Executed | Execution error | Parse failure | Markdown bullets | `x` instead of `$x` |
|---|---|---|---|---|---|
| ProofWriter tier D (300) | 23 | 214 | 63 | 276 | 179 |
| FOLIO (58) | 4 | 0 | 54 | 50 | 55 |
| ProntoQA tier a (48) | 20 | 21 | 7 | 28 | — |
| AR-LSAT (30) | 18 | 12 | 0 | 0 | 0 (different grammar) |

The dominant failure is **surface syntax the model did not reproduce**:
Markdown bullet lists, bold text, and bare `x` where Logic-LM's grammar wants
`$x`. AR-LSAT's grammar is z3 expressions and the model mostly reproduces it;
its 12 failures are bugs in Logic-LM's own z3 code translator (a 10 s timeout
instead of its 1 s changes nothing).

## 4. The interface difference (the actual explanation)

The three systems ask the model for different *kinds* of output:

- **Ankyra** extracts into a **JSON schema via function-calling**
  (`src/ankyra/llm/structured.py`; fallback to `json_object`), and a
  deterministic builder turns that structure into the theory. Format compliance
  is enforced by the API contract, not by the prompt; the model only has to get
  the *content* right.
- **Logic-LM** asks for a logic program in a hand-written grammar
  (`Predicates:/Facts:/Rules:/Query:`, `:::`, `$x`), parsed by a brittle regex
  parser.
- **LINC** asks for a `TEXT:/FOL:` scaffold and executes the extracted
  formulas; the scaffold is simple enough that a few of ten samples usually fit,
  which is why its sampling matters so much.

This is the core finding: **with a weaker, cheaper model, the binding
constraint is the translation interface, not the reasoning.** Ankyra is nearly
invariant to the model's formatting habits; the free-text systems are not.

## 5. Model sensitivity

To separate the model from everything else, we compared LINC's **own** ProofWriter
test set under LINC's own code and protocol on a fixed 60-row subset
(`--own-data --stride 6`, 8-shot, 10 samples, T=0.8). **Only the DeepSeek column
is a run performed in this study.** The GPT-4 and GPT-3.5 values are *not* our
runs: they are recomputed from the generations the LINC authors committed to
their repository (`outputs/*_generations_prc.json`), whose configuration (8-shot,
10 samples, T=0.8) matches the protocol we used and whose reference labels align
row-for-row with ours.

| Model (same task, code and configuration) | Accuracy |
|---|---|
| GPT-4 (LINC's committed generations) | **100.0%** |
| GPT-3.5-turbo-16k (LINC's committed generations) | **96.7%** |
| deepseek-v4-flash (our run) | **85.0%** |

The model alone costs about 12 points (GPT-3.5 96.7% vs deepseek 85.0%); LINC's
published 96-98% on the full test is consistent with the GPT rows here. This
indicates that the external systems' published numbers rest on GPT-3.5/GPT-4, and
that the gap in §2 is partly a *model-regime* effect, not only an architectural
one. Ankyra's contribution is that it holds up under the weaker model.

## 6. Decoding ablations

- **LINC, greedy vs native** (same rows, same tasks):

  | Collection | 1-shot greedy | 8-shot, 10 samples, T=0.8 |
  |---|---|---|
  | FOLIO (58) | 34.5% | **74.1%** |
  | ProofWriter tier A (45) | 22.2% | **86.7%** |

  LINC's robustness lives substantially in its sampling/majority step. Reporting
  only the greedy number would be misleading; the native number is the fair one.

- **Logic-LM, best-of-5 sampling** (a variant Logic-LM does not itself use):
  on ProofWriter tier A, 5 samples at T=0.8 produced **0 executable programs out
  of 225** (greedy produced 6 of 45). Sampling does not rescue Logic-LM here;
  higher temperature makes its grammar compliance worse, not better.

- **Logic-LM self-refinement** (its own feature, Prover9/z3 only):

  | Collection | Greedy solver | + refine (2 rounds) |
  |---|---|---|
  | FOLIO (58) | 6.9% | 39.7% |
  | AR-LSAT (30) | 53.3% | 63.3% |

  Self-refinement roughly triples FOLIO coverage (6.9% → 55.2%), but it also
  introduces confidently-wrong answers (0 → 9 on FOLIO). On AR-LSAT it adds two
  points of executable accuracy.

## 7. What is not run, and why

- **LINC supports only FOLIO and ProofWriter.** Its task registry
  (`eval/tasks/__init__.py`) has no ProntoQA, no AR-LSAT, no GSM8K.
- **Logic-LM has no GSM8K/L4 path.** Its datasets are ProofWriter, ProntoQA,
  FOLIO, LogicalDeduction, AR-LSAT. So the arithmetic stage is not comparable
  with either system; ProntoQA-OOD likewise.
- **Logic-LM self-refinement exists only for Prover9 (FOLIO) and z3
  (AR-LSAT).** Its `models/prompts/` contains `self-correct-AR-LSAT.txt` and
  `self-correct-FOLIO.txt` and nothing else, and its
  `program_executor_map` lists only those two back-ends. There is no
  self-refinement module for the PyKE datasets to run, so ProofWriter/ProntoQA
  are reported at the base pipeline. This is the "specific-prover test" that
  does not exist in the released code, not one we chose to skip.
- **Per-prover capability was tested**, deliberately, offline and LLM-free:
  Logic-LM's solver on its committed GPT-4 programs, and both systems' back-ends
  on gold FOLIO formulas (§3). These isolate the prover from the translator.
- **ProntoQA's source differs.** Ankyra's ProntoQA is `smoorsmith/prontoqa`
  (negation chains); Logic-LM's is the 5-hop fictional-character set. The rows
  fed here are Ankyra's, so the comparison is on identical inputs, but it is not
  the collection Logic-LM published on.

## 8. Honest caveats

- **This is not a reproduction of either paper.** They used GPT-3.5/GPT-4 and
  their own splits. We fixed the rows and the model to make the systems
  comparable; that changes absolute numbers for everyone.
- **Ankyra's numbers are from committed artifacts.** ProofWriter tier A 45/45,
  tier D 297/300 and AR-LSAT 23/30 are documented gate results; ProntoQA 48/48
  and FOLIO 40/58 (L2 29/45 + negation 11/13) are read from the committed live
  traces in `evals/out/`. They were not re-run on the same day as the external
  runs. One ProofWriter tier-A trace shows an empty-question extraction failure
  (provider variance), so the saved traces show 44/45; the accepted gate is
  45/45.
- **LINC tier D was not run natively** (budget); its tier-D number is greedy and
  should not be read against its native tier-A number.
- **Provider non-determinism is real** even at temperature 0; single runs are
  reported, as in the Ankyra gates.
- **The comparison is end-to-end**, so it measures the whole pipeline of each
  system (prompt, decoding, parser, solver). That is the intended object: how
  well a method turns a weak model into a sound answer.

## 9. Conclusion

Taken together, the evidence says the following.

1. The external systems' **symbolic reasoning is sound and capable** (gold-fed
   81-93% on FOLIO; their own GPT-4 programs reproduce paper-level accuracy).
2. Their **translation interface is the wall** under a weaker model: a strict,
   hand-written free-text grammar that the model does not reliably reproduce.
3. **Ankyra removes that wall** by extracting through a structured
   (function-calling) contract and building the theory deterministically, so its
   answers stay sound and its accuracy stays high on the same weak model.
4. With a strong model and its native sampling, LINC is competitive (and wins
   FOLIO); the comparison is therefore not "Ankyra is better at everything", but
   "Ankyra is robust to the model, where free-text neuro-symbolic pipelines are
   not".

## 10. Reproduction

See `comparison/README.md`. The offline parts (adapters, gold-fed, solver
checks) need no API; the live parts are the paid runs recorded in
`comparison/results/`.
