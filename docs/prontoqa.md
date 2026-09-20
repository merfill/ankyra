# ProntoQA — collection notes

Operating notes for a synthetic deductive benchmark, planned as the **L1 gate** of
`docs/reasoning_roadmap.md`. Russian mirror: `docs/prontoqa_ru.md`. Related:
`docs/reasoning_roadmap.md`, `docs/l1_plan.md` (L1 implementation plan),
`docs/proofwriter.md`, `docs/task.md` §3.8.

Sources: Saparov & He, *Language Models Are Greedy Reasoners: A Systematic Formal
Analysis of Chain-of-Thought* (ICLR 2023, arXiv:2210.01240) and
*Testing the General Deductive Reasoning Capacity of Large Language Models Using
OOD Examples* (NeurIPS 2023, arXiv:2305.15269). Generator and data:
`github.com/asaparov/prontoqa` (Apache-2.0); the original release is the `v1`
branch, the OOD release is `main` + `generated_ood_data.zip`. HF mirrors:
`tasksource/prontoqa` (official link), `smoorsmith/prontoqa` (Logic-LLM format),
`renma/ProntoQA` (Logic-LM format). No committed sample yet.

## 1. What the benchmark is

A synthetic question-answering benchmark with machine-generated chains of thought.
The generator builds an **ontology** — a tree or DAG of fictional (or real)
concepts, each with a parent and possibly properties and negated properties — then
asserts the type of one individual and asks a membership question about it. Every
example carries a formal proof (`chain_of_thought`).

Sentence forms (theories are short and syntactically simple):

- subsumption rules: `Every X is a Y.` / `Each X is a Y.` / `X are Y.`;
- an assertion: `131071 is a Mersenne prime.` / `Wren is a numpus.`;
- negated properties (negation variant): `Every real number is not imaginary.`;
- the question: `Is the following statement true or false? 131071 is not real.`

Two question families exist:

- **membership / subsumption** — a chain of `is_a` steps (the classic 5-hop
  PrOntoQA; the OOD release adds 3/5/7-hop);
- **compositional** (PrOntoQA-OOD) — nested conjunction, disjunction and negation,
  proof by cases and proof by contradiction.

Ontology-generation knobs: `generate_negation`, `generate_properties`,
`require_properties`, `max_child_count`, `stop_probability`, and the distractor
options `generate_distractor_parents` / `generate_distractor_branch` (multiple
inheritance). Sibling concepts are made **disjoint** (`are_children_disjoint`)
only when negation is enabled, via `¬∃x (Cᵢ(x) ∧ Cⱼ(x))`.

## 2. Record fields

The generated JSON and the HF mirrors differ slightly. The Logic-LLM/first-rows
shape is:

| Field | Meaning |
|---|---|
| `index` | row index |
| `id` | example id (`example1`, …) |
| `context` | the theory: subsumption rules and the assertion |
| `question` | `Is the following statement true or false? <statement>` |
| `options` | fixed `["A) True", "B) False"]` |
| `answer` | `A` or `B` (the truth value of the statement) |
| `chain_of_thought` | the proof, `Step N: <sentence>.` lines |

The official generator writes its own JSON (proof steps, not a rendered
`chain_of_thought`): `run_experiment.py --model-name json` with `--min-hops`,
`--max-hops`, `--hops-skip`, `--ontology fictional|true|false`, `--ordering
postorder|preorder|random`, `--num-trials`, `--few-shot-examples`.

## 3. Axes

- **hop count** — 1/3/5/7 deduction steps;
- **negation** — negated properties and/or sibling disjointness;
- **ontology** — fictional concepts vs a real one (biology, number theory);
- **compositional** — nesting of And/Or/Not, proof by contradiction;
- **ordering** — postorder / preorder / random sentence order;
- **distractors** — unrelated entities, distractor parents (multiple inheritance).

## 4. Proof shapes

The generator emits a proof over a fixed vocabulary of steps; each maps to a
required engine capability:

| Proof step | Meaning | Ankyra stage |
|---|---|---|
| `AXIOM` | an asserted fact | L0 |
| `ModusPonens` (universal instantiation) | `∀x(X→Y)`, `X(a)` ⊢ `Y(a)` | L0 |
| `AndIntro` / `AndElim` | conjunction of defining properties | L0 if extracted as an AND rule body |
| `OrIntro` / `OrElim` | disjunction, proof by cases | **L2** |
| `ProofByContra` | proof by contradiction | **L2** |
| disjointness `¬∃ (Cᵢ ∧ Cⱼ)` | sibling concepts cannot overlap | **L1** |
| negated property `∀x(C → ¬P)` | explicit negative conclusion | **L1** |

## 5. Relation to Ankyra

- **Positive membership is L0.** `Every X is a Y` becomes
  `is_a(?x, X) => is_a(?x, Y)`; the asserted type and the `is_a` closure answer
  the question directly. This is exactly the ProofWriter `Att` structure, so the
  risk is low.
- **A "False" answer is ambiguous.** Some false questions are *negative
  statements refuted by a positive chain* (e.g. `131071 is not real` is false
  because `is_a(131071, real)` is derived) — L0 handles them. Others require
  **disjointness** or explicit negation, which need **L1** (stratified negation /
  negative constraints). This is the reason ProntoQA is the L1 gate.
- **Compositional questions need L2** (disjunction, case splits, proof by
  contradiction) and are out of the Horn fragment by design.

Because the collection is heterogeneous, an Ankyra run must be **stratified by
proof shape**: the in-fragment subset is scored against the gate; the rest is
reported as `out_of_fragment` and is not a failure.

## 6. How the harness would use it

- `problem_text` = `context` + the question, as for ProofWriter.
- The target is the statement as written; the adapter is polarity-aware (a
  negated statement may be extracted as a positive ask), mapping
  `answer A (True)` → statement entailed and `answer B (False)` → statement
  refuted.
- Strict deduction is the default; for the L1 subset the declared world
  assumption (`ANKYRA_NEGATION_MODE`) must be set **by the benchmark**, not
  guessed.
- Gates and cost hygiene follow `docs/proofwriter.md` §6–7: small committed
  sample, `ANKYRA_EXTRACT_SAMPLES=1`, run once, re-run only on a mismatch.

## 7. Test plan

0. **Recon (no LLM).** Generate a few hundred examples with the official
   generator (`--model-name json`) and tally the proof-step distribution, to size
   the L0 / L1 / L2 subsets precisely.
1. **Builder** `evals/build_prontoqa_sample.py` — deterministic, stratified,
   committed as `evals/data/prontoqa_tier_*.jsonl` (mirror
   `evals.build_proofwriter_sample`).
2. **Adapter** `evals/prontoqa.py` — `load_sample` / `problem_text` /
   `score_record` / `_to_problem`, `--tier/--ids/--limit`, traces to
   `evals/out/prontoqa/`, the same gate report.
3. **L0 gate:** 0 grounded false proofs, determinate all `proven`, kind accuracy
   ≥ 95% on the in-fragment subset; `out_of_fragment` counted, not failed.
4. **L1 stage:** enable stratified negation for the disjointness/negation subset,
   with its own gate and its own report line.

## 8. Status and recon results

**Recon done (LLM-free).** Two sources were tallied:

- `smoorsmith/prontoqa` (Logic-LLM mirror of ProntoQA v1; 500 rows each in
  train/val/test, 1500 total);
- the official generator `asaparov/prontoqa` v1 (`run_experiment.py --model-name
  json`, seed 7, 180 rows), as a cross-check.

Findings:

- **L0 / L1 split.** 760/1500 rows are positive `ModusPonens` subsumption chains
  (L0); 740/1500 conclude via an **explicit negated-property rule** of the form
  `Every X is not Y` (L1).
- **No disjointness, no composition.** The surface context contains **no**
  disjointness sentence ("No X is a Y") and no proof uses disjointness; there is no
  `And`/`Or`/`ProofByContra` in this release (those are the OOD release
  `tasksource/prontoqa`, i.e. L2).
- The official generator behaves the same: negation is always rendered as an
  explicit negated-property rule. Disjointness formulas exist only in the
  generator's **formal ontology** (`get_disjointness_formulas`), never in the
  surface context — so they are not extractable from text (this is the plan §6
  question; `docs/l1_plan.md` D-L1-1(a) applies if such questions are ever used).
- **The existing engine already solves the explicit-negation subset.** A rule with
  a negative consequent plus a positive target is `refuted` with strength `proven`
  (checked offline: `is_a(real)->¬is_a(imaginary)` refutes `imaginary(a)`);
  `supported` still works for the positive chain.

**Implication.** ProntoQA v1 gates **L0 + explicit negation (negative rule
consequents), which is already engine-supported**; the new L1 machinery (constraints,
NAF, CWA) is **not exercised** by this collection. Scope is therefore an open
decision (`docs/l1_plan.md` D-L1-5).

**Harness implemented.** `evals.build_prontoqa_sample` commits
`evals/data/prontoqa_tier_a.jsonl` (48) and `prontoqa_tier_b.jsonl` (160), stratified
by proof shape × statement polarity; `evals.prontoqa --tier a|b` is the polarity-aware
adapter (mirrors the ProofWriter harness, sets `world_assumption="open"`). The
LLM-free primary L1 gate is `evals.l1_synthetic`.

**Gate report (strict deduction, `ANKYRA_EXTRACT_SAMPLES=1`).**

| Tier | Problems | Positive | Negation | Kind accuracy | Strength | Grounded false proofs |
|---|---|---|---|---|---|---|
| a | 48 | 24/24 | 24/24 | **48/48 (100%)** | all `proven` | 0 |
| b | 160 | 80/80 | 80/80 | **160/160 (100%)** | all `proven` | 0 |

Both gates pass with 0 grounded false proofs and every determinate answer `proven`;
all 208 problems answered in wave 0 (deterministic closure, no hypotheses/proposals).
One-sided 95% Clopper–Pearson lower bound on the per-problem accuracy: 94.0% (tier a,
n=48) and **98.1%** (tier b, n=160), so tier b supports the "≥95%" claim
statistically. Caveat: ProntoQA v1 is uniformly 10-hop, so the sample measures
extraction robustness rather than reasoning depth (depth is covered by the
ProofWriter Tier D 296/300). See `docs/reasoning_roadmap.md` L1 and
`docs/l1_plan.md`.
