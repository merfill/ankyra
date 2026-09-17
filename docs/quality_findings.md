# Quality Findings — Ankyra eval harness

Classification of the cases where end-to-end quality falls short, with trace
evidence and proposed general fixes. Companion: `docs/quality_findings_ru.md`.

## Method

- 10 domain-general problems of increasing difficulty in `evals/problems.jsonl`.
- `python -m evals.run` runs the full pipeline and writes a trace per problem to
  `evals/out/<id>.json`: raw LLM calls (prompt, raw, parsed, error, duration) plus
  every intermediate artifact (`structure`, `symbolic`, `theory`, `query`,
  `verdict`, `waves`, `hypotheses`, `answer`, `explanation`).
- Hard engine invariants are asserted by `tests/test_evals_live.py`; ideal
  expectations are reported as soft metrics (`ExpectationEvaluator`).
- Reasoning can be read in natural language: `python -m evals.narrate --lang ru`
  (narration language via `ANKYRA_LANG`, default `en`).

## Aggregate

| run | supported | proven | invariant_ok | llm_calls |
|---|---|---|---|---|
| baseline | 6 | 5 | 9 | 32 |
| after fixes | 8 | 7 | 10 | 24 |

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
- **A4. Presupposition loss (OPEN).** "given that Socrates is a philosopher" is
  dropped from the question conditions despite a rule and an explicit example.
  Effect: `insufficient` is reported as `supported`. Likely a model-compliance
  limit; needs broader coverage examples and/or a dedicated question-side pass.
- **A5. Code semantic guessing removed (FIXED).** `is`→`is_a`, `has`→`has_feature`,
  `isNot`→`is_a` deleted from the engine (`R5`); these are now prompt conventions.

## B. Engine / semantics

- **B1. Non-monotonic exceptions (OPEN, design decision).** "Birds fly" plus
  "penguins do not fly" yields `P` and `¬P`; the monotonic engine reports
  `refuted`/`not_proven` rather than the expected "no". Requires a specificity /
  defeasible-rule policy, which conflicts with the current monotonicity invariant
  (D3) — needs an explicit product decision.
- **B2. Materialized consequences hide rules (OPEN).** `enrich.materialize_rule_morphisms`
  adds a rule's consequence as an axiom, so the explanation shows the conclusion as
  an axiom and never mentions the rule (see `rain`). Fix: stop materializing into
  axioms, or keep the materialization provenance.
- **B3. Explanation ignores terminal status (OPEN, bug).** For `refuted` (and
  unsupported) the explanation module still builds a *positive* proof — e.g.
  `exception` shows `fly(tweety)` while the verdict is `refuted`. Fix: thread the
  status into `build_explanation`; `target_refuted` → negative proof,
  `contradiction`/unsupported → empty trace.
- **B4. Negated target (FIXED).** `¬phi` entailed → `refuted` with `target_refuted:`
  and a "no" answer (`R4`).
- **B5. Builtins (WORKS when enabled).** `ANKYRA_BUILTINS=true` plus a prompt block;
  `threshold` is currently solved with relational ids and a cited rule, so the
  builtin path needs a dedicated case.

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
- **D2. Degenerate traces (OPEN).** Trivial successful cases produce one-step
  explanations (`rain`) — consequence of B2.

## Priority

1. **B3** (misleading explanations) and **B2** (rule provenance) — correctness.
2. **C1** variance mitigations (sampling + prompt stability) and **A4**.
3. **B1** non-monotonic policy — a product decision, then implementation.
