# FOLIO — collection notes

Operating notes for an expert-written first-order-logic benchmark, the **L2 gate** of
`docs/reasoning_roadmap.md`. Russian mirror: `docs/folio_ru.md`.
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

**Negation subset implemented (offline).** Recon over the v0.0 validation split (the
only GitHub split carrying `conclusion-FOL`): 204 examples, of which **13 stay in the
L1 negation fragment** (explicit negation, universal implication, conjunction, atomic
facts, and a **ground** conclusion; no disjunction/existential/equality/XOR/
biconditional/multi-variable quantification). `evals.build_folio_sample` commits them
as `evals/data/folio_negation_tier_a.jsonl` and `evals.folio` is the polarity-aware
adapter (label `True/False/Uncertain` → yes/no/unknown, open world).

**Live runs.** Pre-filter 23-example sample: 9/23. Filtered 13-example sample: **7/13**
(all 4 `Uncertain` correct; **no grounded mismatch**). Two defects found here were
fixed:

- a `grounded_mismatch` was an unsound **classification hole**, not extraction: the
  LLM cited the full conditional (`"If 1984 is a streaming service, then …"`) to
  assert `is_a(1984, streaming_service)`, and the conditional-quote guard missed it
  because of a trailing period (finding B13 in `docs/quality_findings.md`). Fixed; the
  example is now `unknown`.
- `Plungers suck.` was formalized as the constant fact `suck(plunger)` instead of the
  rule `is_a(?x,plunger) → suck(?x)`; the extraction prompt now quantifies bare
  plurals, and the example is correct.

The remaining mismatches are `undecided_mismatch` (the gold formalization also fails
in the open world — reducible to L2), not extraction.

All `Uncertain` labels were correctly left unknown. No engine unsoundness remains
observed.

**Gold-fed diagnostic (decisive).** `evals.analyze_folio` parses the annotated FOL
directly (`evals.folio_fol`, the FOL-fed mode of §6) and separates **fragment** from
**extraction**: if the gold formalization already fails, the gap is the logic, not
extraction. On the 13-example sample:

| verdict source | correct |
|---|---|
| text-fed (LLM extraction) | 7/13 |
| gold-fed, open world | 7/13 |
| gold-fed, closed world | 8/13 |

Categorization: **ok 6** (4 `Uncertain` + 2 ground facts), **semantics/reductio 5**
(gold-fed succeeds only under a closed world), **fragment 1**, **extraction 1**
(question-stage predicate drift, provider variance). So the low score is dominated by
the fragment boundary, not extraction: most `False` labels and the negated `True`
labels need **reductio/contrapositive** (L2) or a closed-world step, while `Uncertain`
needs the **open** world — no single world assumption fits. text-fed now matches
gold-fed (both 7/13), i.e. the remaining gap is the logic, not the extractor.

Conclusion: FOLIO's in-fragment L1 slice is genuinely tiny and still needs L2; it is
correctly the **L2 gate**, not an L1 gate. Higher yield needs L2 (reductio) and/or
the gated HF v2 release (full FOL for train). Function terms are not separately
detected in v0.0 (no clean field); a documented fragment limitation. See
`docs/reasoning_roadmap.md` L2 and `docs/l1_plan.md`.

## 10. L2 recon (LLM-free)

Reproduce with `uv run python -m evals.recon_l2 --folio-only`. Over the v0.0
validation split (204 rows), the construct tally is: negation 157, **disjunction
76**, **existential 76**, xor 43, multivar 33, biconditional 6 (constructs overlap
within a row). The **L2 fragment** — a disjunction or an existential, with no
equality/xor/biconditional/multi-variable quantification — is **93 rows** (True 33,
Unknown 34, False 26). This is the intended second L2 gate.

Key point: FOLIO is where **`∃` is actually exercised** (76 rows, e.g.
`∃x (GetMonkeypox(x) ∧ Coughing(x))`), unlike ProntoQA-OOD, which has none
(`docs/prontoqa.md` §9). So the first-order/Skolem layer of L2 (plan milestone 8) is
gated by FOLIO, not by the first (ProntoQA-OOD) gate. Function/equality detection
remains a documented limitation of v0.0 (§9).

**L2 harness implemented (LLM-free); live run pending budget.**
`evals.build_folio_sample --subset l2` commits `evals/data/folio_l2_tier_a.jsonl`
(45 problems, 15 per label: True/False/Uncertain) — the L2 fragment (disjunction or
existential, no equality/XOR/biconditional/multi-variable quantification).
`evals.folio` gained `--subset negation|l2` and a `logic` level (the L2 subset runs
`logic="ground"`, open world); the L1 negation subset is unchanged. Offline tests:
`tests/test_evals_folio.py`. The gold-fed diagnostic (`evals/folio_fol.py`) still
parses only the L1 negation shape; extending its parser to `∨`/`∃` (to separate
fragment from extraction on the L2 slice) is a follow-up.
