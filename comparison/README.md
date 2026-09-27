# Ankyra vs Logic-LM vs LINC

Comparative evaluation of Ankyra against two open-source neuro-symbolic reasoning
systems on the **same task rows** and with the **same model/provider** Ankyra uses
(`ANKYRA_API_URL` / `ANKYRA_MODEL` from `.env`). External repositories are cloned
outside the Ankyra tree; this directory holds only adapters, drivers and results.

## Why a dedicated harness

The external frameworks were written for OpenAI's endpoint and the legacy
`openai<1` SDK. The shared shim `patch.py` redirects that SDK to the Ankyra
provider, forces every request to the Ankyra model, disables DeepSeek thinking
(matching the engine), and caches temperature-0 responses so re-runs are free.

## What is comparable

| Collection | Ankyra | Logic-LM | LINC |
|---|---|---|---|
| ProofWriter | tier A 45, tier D 300 | yes (PyKE) | yes (NLTK/Prover9) |
| FOLIO | L2 45 + negation 13 | yes (Prover9) | yes (Prover9) |
| AR-LSAT | eval 30 | yes (z3) | no |
| ProntoQA | tier a 48, tier b 160 | yes (different source dataset) | no |
| ProntoQA-OOD | tier a 42 | no | no |
| GSM8K | dev/eval | no | no |

L4 (arithmetic) has no counterpart in either framework; ProntoQA-OOD and
LogicalDeduction likewise. The comparison therefore covers L0-L3 only.

The comparison is **not** a reproduction of the papers: those used GPT-4 and
their own splits. Here every system sees the same Ankyra rows, the same prompt
style it ships, and the same model. Confidently wrong answers are the metric of
interest; abstentions and parse failures count as errors.

## Layout

```
comparison/
  adapt.py        Ankyra JSONL -> Logic-LM / LINC schemas (id-preserving)
  patch.py        legacy-openai -> Ankyra provider shim (+cache, thinking off)
  run_logicllm.py drive Logic-LM (prepare / generate / infer / evaluate)
  run_linc.py     drive LINC's task pipeline (prompt + NLTK/Prover9)
  score.py        unify external predictions into one table
  results/        committed outputs
  .cache/         LLM response cache (not committed)
```

## External checkouts (not committed)

```bash
git clone --depth 1 https://github.com/teacherpeterpan/Logic-LLM /tmp/opencode/cmp/logicllm
git clone --depth 1 https://github.com/benlipkin/linc        /tmp/opencode/cmp/linc
```

Environments (separate, so Ankyra's own venv is untouched):

```bash
uv venv /tmp/opencode/cmp/llm-venv  --python 3.11
uv pip install --python /tmp/opencode/cmp/llm-venv/bin/python \
  "openai==0.27.9" nltk z3-solver scitools-pyke python-constraint func-timeout backoff tqdm ply aiohttp

uv venv /tmp/opencode/cmp/linc-venv --python 3.10
uv pip install --python /tmp/opencode/cmp/linc-venv/bin/python \
  "openai==0.27.4" "datasets==2.16.1" "pyarrow==14.0.2" "numpy==1.26.4" "nltk==3.8.1"
```

Prover9 (needed by Logic-LM FOLIO and by LINC):

```bash
make -C /tmp/opencode/cmp/logicllm/models/symbolic_solvers/Prover9
```

## Commands

Logic-LM (`PYTHONPATH` must include the Ankyra root):

```bash
PYTHONPATH=$PWD /tmp/opencode/cmp/llm-venv/bin/python -m comparison.run_logicllm \
  --repo /tmp/opencode/cmp/logicllm --action prepare
PYTHONPATH=$PWD /tmp/opencode/cmp/llm-venv/bin/python -m comparison.run_logicllm \
  --repo /tmp/opencode/cmp/logicllm --action all --collection folio_tier_a
```

LINC:

```bash
PROVER9=/tmp/opencode/cmp/logicllm/models/symbolic_solvers/Prover9/bin/prover9 \
PYTHONPATH=$PWD /tmp/opencode/cmp/linc-venv/bin/python -m comparison.run_linc \
  --repo /tmp/opencode/cmp/linc --collection proofwriter_tier_a --nshot 1
```

## Phase 1 status (plumbing, offline verification)

All four symbolic back-ends were exercised on the frameworks' own committed
logic programs (no LLM cost), which validates the environment:

| Back-end | Dataset, split | Overall | Exe_Rate | Exe_Acc |
|---|---|---|---|---|
| Prover9 | FOLIO dev (their programs, gpt-4) | 70.1% | 79.9% | 80.4% |
| PyKE | ProofWriter dev (their programs, gpt-4) | 79.5% | 99.0% | 79.6% |
| PyKE | ProntoQA dev (their programs, gpt-4) | 83.2% | 100% | 83.2% |
| z3 | AR-LSAT dev (their programs, gpt-4) | 28.3% | 32.6% | 60.0% |

LINC's own FOLIO validation preprocessing accepts 182/204 rows; its pipeline
runs end-to-end on the converted Ankyra rows (3-row smoke: 2/3, references met).

The AR-LSAT z3 solver has a low executable rate on Logic-LM's own committed
programs (translator bugs and `No Output`; a 10 s timeout instead of their 1 s
changes nothing). This is Logic-LM's own behaviour, not a harness defect.

## Phase 2 (live comparison) - DONE

Live runs were executed on the Ankyra rows with the shared model. Each system
runs its native decoding (Ankyra greedy; Logic-LM greedy + self-refinement;
LINC 8-shot / 10 samples / T=0.8 / majority). Full results, evidence and caveats:
[`../docs/comparison.md`](../docs/comparison.md) and
[`results/summary.md`](results/summary.md).

| Collection (n) | Ankyra | Logic-LM | Logic-LM + refine | LINC (native) |
|---|---|---|---|---|
| ProofWriter tier A (45) | 100.0% | 8.9% | - (PyKE) | 86.7% |
| ProofWriter tier D (300) | 99.0% | 6.7% | - (PyKE) | 28.3%* |
| ProntoQA tier a (48) | 100.0% | 41.7% | - (PyKE) | - |
| FOLIO L2+negation (58) | 69.0% | 6.9% | 39.7% | 74.1% |
| AR-LSAT eval (30) | 76.7% | 53.3% | 63.3% | - |

Numbers are solver accuracy (correct / all rows; failures and abstentions count
as wrong). *LINC tier D is greedy (native budgeted for tier A and FOLIO only).

