# FOLIO — collection notes

Operating notes for an expert-written first-order-logic benchmark, planned as the
**L2 gate** of `docs/reasoning_roadmap.md`. Russian mirror: `docs/folio_ru.md`.
Related: `docs/reasoning_roadmap.md`, `docs/prontoqa.md`, `docs/task.md` §3.8.

Source: Han et al., *FOLIO: Natural Language Reasoning with First-Order Logic*
(arXiv:2209.00840, v3 2024). Data: `github.com/Yale-LILY/FOLIO` (MIT); current
release at HF `yale-nlp/FOLIO`; `data/v0.0` in the repo. No committed sample yet.

## 1. What the benchmark is

An expert-written, open-domain corpus of natural-language reasoning problems
paired with first-order logic (FOL) annotations. Each problem is a **story**: a
set of NL premises and a set of NL conclusions, each conclusion labelled `True`,
`False` or `Unknown`. Every premise and conclusion also carries a parallel FOL
formula, and the labels are machine-checked — an FOL inference engine verifies
that a `True`/`False` conclusion follows from (or contradicts) the premises.

- 1 430 conclusions (abstract) / 1 435 (Table 3) over **487 premise sets**;
- split 70/15/15 = 1 001 / 203 / 226 by **story**;
- 4 351-word vocabulary; reasoning depth 0–7 (mode 4); 28.7% need ≥5 steps;
- three-way label with an **open-world** `Unknown` (majority class 38.5%).

Everything needed for the label sits **inside the premises**: at the alignment
stage the annotators add the missing commonsense knowledge and the "intrinsic
properties" of predicates (e.g. `LocatedIn` is transitive, `BeFamily` is
symmetric) as explicit extra premises. The corpus is therefore self-contained,
which matches Ankyra's single-problem input assumption (`docs/task.md` §1).

Two construction methods, exposed as the `source` field:

- **WikiLogic** — written from scratch, seeded by random Wikipedia pages; 304
  stories, 1 353 premises, 753 conclusions; depth 1–5; 51 distinct ASTs; more
  varied sentence- and logic-level structures.
- **HybLogic** — hybrid: templates built by chaining valid syllogisms (the
  conclusion of one used as a premise of the next), then instantiated in NL by
  annotators; 183 stories, 1 054 premises, 682 conclusions; depth 5–8; 25 ASTs;
  simpler per-sentence logic but longer chains.

Baselines (test set): majority 38.5%, GPT-4 few-shot 64.2%, Logic-LM 78.1%.

## 2. Record fields

| Field | Meaning |
|---|---|
| `premises` | natural-language premises (a list) |
| `premises-FOL` | parallel FOL formulas for the premises |
| `conclusion` | the natural-language conclusion |
| `conclusion-FOL` | parallel FOL formula for the conclusion |
| `label` | `True` / `False` / `Unknown` |
| `story-id` | story id (premises shared across conclusions) |
| `example-id` | per-conclusion id |
| `source` | `WikiLogic` or `HybLogic` |

## 3. Axes

- **source** — WikiLogic (diverse, shorter) vs HybLogic (templated, longer);
- **reasoning depth** — 0–7 deductive steps (mode 4; ≥5 for 28.7%);
- **label** — True / False / Unknown (open-world);
- **logic inventory** — see §4.

## 4. Logic inventory → engine stage

The corpus is **not** a single fragment. Stratify each example by the constructs
its FOL annotation actually uses:

| FOL construct | Example | Ankyra stage |
|---|---|---|
| atomic ground fact | `WildTurkey(tom)` | L0 |
| universal implication | `∀x(WildTurkey(x) → …)` | L0 |
| conjunction in a rule body | `… ∧ …` | L0 |
| explicit negation | `¬EasternWildTurkey(tom)` | **L1** |
| disjunction | `A(x) ∨ B(x) ∨ …` | **L2** |
| existential quantifier | `∃x(…)` | **L2** |
| function / nested term | `f(x, y)` | fragment decision (beyond committed L2) |
| equality | `x = y` | fragment decision (beyond committed L2) |
| axiom schema | transitivity of `LocatedIn`, symmetry of `BeFamily` | fragment decision (explicit axioms) |

Notes:

- Most `True`/`False` labels need **negation and/or disjunction**, so the purely
  definite-Horn (L0) subset is small. FOLIO is an L1 **and** L2 gate, not L2
  alone; the L0 slice is the easy baseline.
- **Skolemization is not an extraction feature.** Eliminating an existential —
  a Skolem function/constant for a premise, a witness constant for the goal — is
  a clause-normal-form step inside the decision procedure, not something Phase 0
  emits. Phase 0 only needs to *record* quantifier structure (which variable,
  which scope); the prover Skolemizes.
- The label ground truth was itself produced by an FOL inference engine (paper
  Appendix G, a Prover9-class prover). L2 can reuse a resolution prover as its
  decision procedure rather than hand-rolling one; the reference procedure
  already exists.
- FOL entailment is only **semi-decidable**: `proven` is recognisable, refutation
  is not. L2 must run a **bounded** clausal search and report `insufficient` /
  budget exhaustion honestly (`docs/reasoning_roadmap.md` L2 risk).

## 5. Relation to Ankyra

- **In-fragment subset.** Examples whose FOL uses only atoms, universal
  implications, conjunction, negation and disjunction (no functions, no equality,
  no schemas) are the L1+L2 target. `HybLogic` is templated and per-sentence
  simpler, so it is the more predictable in-fragment slice; `WikiLogic` is more
  varied and stresses extraction.
- **Out-of-fragment subset.** Functions, equality and axiom schemas exceed the
  "positive FOL" fragment the roadmap commits to; those examples are reported
  `out_of_fragment` and are not gate failures. Closing them is a fragment
  decision, not a bug fix.
- **`Unknown` is the open-world default.** A correct `Unknown` must not be
  manufactured by closing the world: `ANKYRA_NEGATION_MODE` (L1) is set by the
  benchmark, never guessed (same rule as ProntoQA, `docs/prontoqa.md` §6).
- **Axiom schemas.** Transitivity/symmetry are not in the raw text as sentences
  in the general case; for the NL task the LLM must propose them. They are
  hypotheses unless the benchmark supplies the FOL annotation — a concrete case
  of the propose/decide boundary, recorded in the hypothesis ledger.

## 6. How the harness would use it

- `problem_text` = `premises` + the `conclusion` as the target statement, as for
  ProofWriter/ProntoQA.
- Target polarity-aware: `True` → entailed, `False` → refuted, `Unknown` →
  neither (honest `unsupported`/`insufficient`).
- Stratify by the FOL annotation (§4) to separate `in_fragment` from
  `out_of_fragment`; score only the in-fragment subset against the gate.
- The benchmark may also be run in an **FOL-fed** mode (feed `premises-FOL` /
  `conclusion-FOL` directly) to separate extraction error from engine error; this
  is a diagnostic, not the product path.
- Gates and cost hygiene follow `docs/proofwriter.md` §6–7: small committed
  sample, `ANKYRA_EXTRACT_SAMPLES=1`, run once, re-run only on a mismatch.

## 7. Risks

- **Fragment creep.** Full FOL is undecidable; promising to "decide FOLIO" would
  break the `proven` guarantee. The fragment must be explicit and the budget
  honest.
- **Extraction is the hard part.** A wrong FOL translation yields a confidently
  wrong label; the adapter must report encoding failures rather than guess.
- **Hardcoding temptation.** Transitivity/symmetry and the fixed syllogism
  templates invite a baked-in ontology, forbidden by `docs/task.md` §3.8.
- **Cost.** 226 test examples with long premise sets; `ANKYRA_EXTRACT_SAMPLES=1`
  and a small committed sample are mandatory.

## 8. Test plan

0. **Recon (no LLM).** Parse the committed FOL annotations and tally the
   construct distribution (§4) to size the in-fragment / out-of-fragment subsets
   precisely.
1. **Builder** `evals/build_folio_sample.py` — deterministic, stratified by
   source × depth × construct, committed as `evals/data/folio_tier_*.jsonl`
   (mirror `evals.build_proofwriter_sample`).
2. **Adapter** `evals/folio.py` — `load_sample` / `problem_text` /
   `score_record` / `_to_problem`, `--tier/--ids/--limit`, traces to
   `evals/out/folio/`, the same gate report.
3. **Gate:** 0 grounded false proofs, every determinate in-fragment answer
   `proven`, kind accuracy ≥ 95% (roadmap L2 threshold); `out_of_fragment`
   counted, not failed; every remaining failure categorized.

## 9. Status

Not implemented. Planned as the **L2 gate after ProntoQA-OOD**, and gated behind
closing soundness findings 21–22 (`docs/implementation_plan.md` §8). First task is
the LLM-free recon in step 0. See `docs/reasoning_roadmap.md` L2.
