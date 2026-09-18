# Quality Findings — Ankyra eval harness

Classification of the cases where end-to-end quality falls short, with trace
evidence and proposed general fixes. Companion: `docs/quality_findings_ru.md`.

## Method

- 12 domain-general problems of increasing difficulty in `evals/problems.jsonl`.
- `python -m evals.run` runs the full pipeline and writes a trace per problem to
  `evals/out/<id>.json`: raw LLM calls (prompt, raw, parsed, error, duration) plus
  every intermediate artifact (`structure`, `symbolic`, `theory`, `query`,
  `verdict`, `waves`, `hypotheses`, `answer`, `explanation`).
- Hard engine invariants are asserted by `tests/test_evals_live.py`; ideal
  expectations are reported as soft metrics (`ExpectationEvaluator`).
- Reasoning can be read in natural language: `python -m evals.narrate --lang ru`
  (narration language via `ANKYRA_LANG`, default `en`).
- **ProofWriter Tier A** (`python -m evals.proofwriter` over the committed
  `evals/data/proofwriter_tier_a.jsonl`): 45 open-world synthetic-core problems
  at depth 0/1/2/3/5, with its own answer-kind scoring. Strict deduction by
  default; `--hypotheses` selects the abductive mode. See section E.

## Aggregate

| run | supported | proven | invariant_ok | llm_calls |
|---|---|---|---|---|
| baseline | 6 | 5 | 9 | 32 |
| after fixes | 8 | 7 | 10 | 24 |
| engine fixes (12 problems) | 8 | 8 | 12 | 29 |

The last run has no expectation misses (every soft metric passes) and
`vocab_reuse=1.00`; `vehicle` and `insufficient` match their expectations
(milestone 6 in `docs/implementation_plan.md`).

## A. Extraction (prompt / model)

- **A1. Atom shape (FIXED).** The model put the relation name in `id`/`name`
  instead of `predicate`; the `json_object` fallback had no schema in the prompt,
  yielding empty predicates. Fix: schema injected on fallback (`R7`), explicit atom
  grammar + few-shot examples (`R1`/`R2`/`R6`), malformed atoms dropped (`R3`).
- **A2. Universal quantification (FIXED).** "All / every / any X ..." was extracted
  with the class noun as the atom subject instead of a variable, producing inert
  rules (`is_a(animal, warm_blooded) => ...`). Fix: explicit convention + example
  (`?x`), verified on `chain`, `multihop`, `subsumption`.
- **A3. Ask polarity (FIXED).** "Can Tweety fly?" produced a negated ask copied
  from "cannot fly". Fix: the ask must be the question's conclusion in positive
  form (`R2`).
- **A4. Presupposition premise (FIXED engine side; model residual OPEN).**
  `settle_query` deleted every question premise no proof used, so `verify` could
  never report `insufficient` — "given that Socrates is a philosopher" *was*
  extracted, then silently dropped. Fix: unused premises are preserved and
  `insufficient` is terminal (slimming loop removed; `settle_query`/`build_query`
  no longer take the unused `theory`). The residual is model-side: a later live run
  extracted `facts=[]`, i.e. the model itself omitted the clause and `supported` is
  then legitimate. That residual is C1 (compliance/variance), not an engine bug.
- **A5. Code semantic guessing removed (FIXED).** `is`→`is_a`, `has`→`has_feature`,
  `isNot`→`is_a` deleted from the engine (`R5`); these are now prompt conventions.

## B. Engine / semantics

- **B1. Non-monotonic exceptions (FIXED, flag-gated).** "Birds fly" plus
  "penguins do not fly" no longer collapses to a contradiction. Every rule is a
  default (only asserted facts are strict); the layer in `engine/defeasible.py`
  resolves conflicts by specificity via `is_a`; equal specificity (the Nixon
  diamond) stays unknown. Behind `ANKYRA_DEFEASIBLE` (default off). See
  `docs/defeasible_reasoning.md`.
- **B2. Materialized consequences hide rules (FIXED).** `materialize_rule_morphisms`
  is gone; rule conclusions are no longer turned into axioms, so rules appear in the
  trace (`rain`). `heal_contradictory_axioms` is gone too: a real contradiction now
  reaches the engine instead of being silently collapsed.
- **B3. Explanation ignores terminal status (FIXED).** `build_explanation` branches
  on the status: `target_refuted` shows the negative proof; `contradiction` shows
  both branches in `Explanation.conflict`; an undecided defeasible conflict shows
  both competing rules; `unsupported`/`insufficient` stay empty.
- **B6. Contradictions were mislabeled (FIXED).** A complementary pair unrelated to
  the target made `verify` return `refuted`. Now the terminal status `contradiction`
  is reported only when the pair is in the target's proof; an unrelated inconsistency
  becomes an `inconsistent_theory:` gap and leaves the answer intact.
- **B4. Negated target (FIXED).** `¬phi` entailed → `refuted` with `target_refuted:`
  and a "no" answer (`R4`).
- **B5. Builtins (WORKS when enabled).** `ANKYRA_BUILTINS=true` plus a prompt block;
  `threshold` is currently solved with relational ids and a cited rule, so the
  builtin path needs a dedicated case.
- **B7. Open-query variables were pre-bound (FIXED).** `verify`/`winning_store_hit`/
  `build_explanation` passed `query.variables` to `build_context` as bindings, so a
  declaration label (`?c -> "vehicle_type"`) replaced the free variable and the open
  target never matched (`vehicle` ended `no_progress`). Now `variables` is a
  declaration only and the binding comes from unification (`vehicle` ->
  `supported`/`proven_under`/`H1`).
- **B8. Quote re-formalization guard (FIXED).** `classify` accepted any proposal
  whose quote was a lexical substring, so a rule could silently drop a condition
  (`nice => young` from `nice ∧ person => young`) or a fact could be grounded on a
  conditional sentence (`rough(bear)` quoted from "If the bear is rough and ...").
  Now a rule reusing an already-grounded quote is never `cited` — it is a
  hypothesis (`rejected/quote_reused` when hypotheses are forbidden) — and a fact
  may not quote a sentence already formalized as a rule
  (`rejected/quote_from_rule`). A fact may still reuse a quote that only grounds a
  morphism, which is required for legitimate corrections (`threshold`).
- **B9. Proposal feedback (DONE).** The hint lists the last three waves
  (`wave, category, action, reason`), so a `missing_payload` or `quote_reused`
  rejection is visible and the next proposal can correct the field/action instead
  of repeating it (`engine/proposal.py`, `WaveContext.history`).

## C. Reproducibility

- **C1. LLM variance (OPEN, provider-level).** The same problem gives different
  outcomes across runs (`chain`: `extraction_error` then `supported`;
  `contradiction`: "no" then `refuted`). The provider routes to subcontractors, so
  pinning a model is not possible. Mitigations: stricter/steadier prompts, lower
  temperature, provider seed if supported, and multi-sample extraction with a
  deterministic pick (`ANKYRA_EXTRACT_SAMPLES`).

## D. Explanation / narration

- **D1. Language (DONE).** `narrate_explanation(..., language=...)` + `ANKYRA_LANG`
  (default `en`); Russian narration verified faithful to the steps.
- **D2. Degenerate traces (FIXED).** Trivial successful cases name the rule again
  (`rain`) — consequence of B2.

## E. External benchmark — ProofWriter (Tier A)

Harness: `evals/proofwriter.py` over the committed Tier A sample (45 problems;
open-world synthetic core, depth 0/1/2/3/5; built by
`evals/build_proofwriter_sample.py`). Mapping: `True -> kind yes`,
`False -> kind no`, `Unknown -> kind unknown`, with an explicit polarity check for
negated statements (0 flips observed). No training, no benchmark semantics in the
engine.

Ankyra results (strict deduction is the default):

| mode | kind accuracy | determinate (True/False) | Unknown | false positives |
|---|---|---|---|---|
| strict (`allow_hypotheses=False`) | 40/45 (89%) | 25/30, all `proven` | 15/15 | 0 |
| abductive (`--hypotheses`) | 39/45 (87%) | 30/30 (28 proven, 2 proven_under) | 5/15 | 10 |

Hypotheses let the wave abduce the missing links and "prove" statements the
benchmark marks Unknown, so strict is the default and the abductive row is a
diagnostic. The strict misses are extraction generalization (a generic noun such
as "people" becomes a class: `is_a(?x, people) ∧ nice => young` is inert) plus the
B8 guard correctly blocking silent re-formalizations.

External reference (Tafjord et al., "ProofWriter", arXiv:2012.13048; fine-tuned
T5-11B, templated IID D5-test, ~70k training examples — NOT apples-to-apples):

| system | answer (CWA) | answer (OWA) | proof (OWA) |
|---|---|---|---|
| ProofWriter All-At-Once | 99.6 | 99.7 | ~95–98 |
| ProofWriter Iterative | 99.7 | 99.6 | 97.6 |
| PRover | 99.3 | — | 87.1 |

Out-of-domain (hand-written Birds/Electricity, different grammar): answer
All 85.5% / Iter 97.0%, proof All 84.5% / Iter 97.0%. The IID ~99% reflects a
model trained on the same generated distribution; the OOD row is closer to a
zero-shot setting. Our subset is 45 vs their ~12k, and our proof is mechanical
provenance (their metric is exact-match proof graphs), so only answer accuracy is
comparable.

## Priority

1. **C1** variance mitigations (sampling + prompt stability), including the
   model-side A4 residual.
2. **Extraction generalization** seen on ProofWriter (generic nouns, modifier
   retention): the wave may repair it via ledgered hypotheses, and strict mode
   surfaces the assumption instead of hiding it.
