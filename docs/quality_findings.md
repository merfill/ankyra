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
- **ProofWriter tiers** (`python -m evals.proofwriter --tier a|b|c|d` over the
  committed `evals/data/proofwriter_tier_<x>.jsonl`): staged open-world samples
  (A 45 core; B 75 +NatLang; C 150; D 300 +`depth-3ext`), each with its own
  answer-kind scoring. Strict deduction by default; `--hypotheses` selects the
  abductive mode. See section E and `docs/proofwriter.md`.

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
- **A4. Presupposition premise (FIXED; residual not reproduced).**
  `settle_query` deleted every question premise no proof used, so `verify` could
  never report `insufficient` — "given that Socrates is a philosopher" *was*
  extracted, then silently dropped. Fix: unused premises are preserved and
  `insufficient` is terminal (slimming loop removed; `settle_query`/`build_query`
  no longer take the unused `theory`). The residual is model-side: a later live run
  extracted `facts=[]`, i.e. the model itself omitted the clause and `supported` is
  then legitimate. That residual is C1 (compliance/variance), not an engine bug.
  Follow-up measurement (live): explicit markers ("given that / assuming / suppose",
  RU "при условии что") are captured 7/7, and a no-marker control is not
  over-captured, so the residual is not currently reproducible. A comma-joined
  declarative ("Socrates is a philosopher, is Socrates mortal?") is read by Phase 0.2
  as a descriptive fact, not a question condition, so the answer is honestly
  `supported`; this is by design, not a miss. Item closed; the explicit
  `QuestionStructure.presuppositions` decomposition and the `presupposition`
  explanation source are implemented. See `docs/statement_sources.md`.
- **A5. Code semantic guessing removed (FIXED).** `is`→`is_a`, `has`→`has_feature`,
  `isNot`→`is_a` deleted from the engine (`R5`); these are now prompt conventions.
- **A6. Dropped conjunction (NOT REPRODUCED — closed).** A suspected extraction loss
  of a coordinated modifier ("Furry, young people are smart") was checked on 11 saved
  runs: the model encodes comma lists as `Slot.set` (AND), which expands to one
  condition per item, so a count-based detector fires 0/249 rules. The earlier alarm
  was a reporting bug (reading `object.id` while `object.set` held the items). A
  token-coverage detector false-fires ~37% on verb morphology (`need`/`needs`) and
  would need lemmatisation; not worth it. No detector added.

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
  Now any rule or fact reusing an already-grounded quote for a different atom is
  never `cited` — it is a hypothesis (`rejected/quote_reused` when hypotheses are
  forbidden). One quote is the witness of exactly one formalization, for facts and
  rules alike; a fact may not be grounded on a quote that already states something
  else (e.g. `is_a(fiona, person)` quoted from "Fiona is nice"). Overlapping spans
  count as reuse too: a broader quote containing an already-grounded quote (or a
  fragment of one) is not a fresh witness, so widening the sentence that already
  grounds another atom cannot license a new fact.
- **B9. Proposal feedback (DONE).** The hint lists the last three waves
  (`wave, category, action, reason`), so a `missing_payload` or `quote_reused`
  rejection is visible and the next proposal can correct the field/action instead
  of repeating it (`engine/proposal.py`, `WaveContext.history`).
- **B10. Structural quantifier sort (DONE).** The dominant extraction defect was
  domain-vs-premise: "All furry people are smart" was encoded with
  `is_a(?x,person)` as a *premise* and `domain=[]`, so the rule was inert without a
  fact asserting anyone is a person (17–18 rules/run in the strict traces). A rule
  now carries `forall` (variable → sort) structurally, and `unroll` drops the
  matching `is_a(?x,sort)` premise as the quantifier's domain — but keeps it when it
  is the variable's only binder, so the rule stays range-restricted. `Rule.forall`
  records the sort for audit; the engine ignores it. Proper-subset conditions
  (`is_a(?x,young)`) are untouched. See `docs/task.md` §0.3.
- **B11. Canonical property relation (DONE).** The same lexeme could be encoded as
  an `is_a` class in a fact and as a unary predicate in a rule (`is_a(gary,blue)` vs
  `blue(?x)`), which never unifies; measured on 3 of 405 structures (e.g.
  `AttNeg-OWA-D1-10`). `StructAtom.relation_kind ∈ {ascription,possession,action}`
  makes the logical role explicit: ascription canonicalizes to
  `is_a(subject, property)` in every position, possession ("has …") stays a binary
  predicate, action is unchanged. The legacy `predication` is still accepted and a
  copula implies ascription. This removes reliance on the model's surface label.
- **B12. Conditional-quote guard (DONE).** A strict false proof came from a fact
  grounded only on a conditional phrase: `is_a(harry,red)` cited "Harry is red" from
  inside "If Harry is red then Harry is furry", and `see(rabbit,rabbit)` cited a rule
  sentence. `classify` already had `_quote_in_use`, but it ignored rule atom quotes.
  `symbolic.quote_only_in_conditional` now rejects a proposal whose quote occurs in
  the source only inside a rule's sentence (`quote_conditional` when hypotheses are
  forbidden; a repairable `conditional_quote:` gap on the extraction path). A quote
  that also occurs standalone stays usable. The two proofs became honest `unknown`;
  strict N=3 is 45/45 again.

- **B13. Conditional-quote guard defeated by edge punctuation (DONE, soundness).**
  Found on FOLIO `folio-validation-0050`: the LLM proposed `is_a(1984,
  streaming_service)` as an `assert_cited_fact` with the full conditional sentence
  `"If 1984 is a streaming service, then 1984 is a hardcover book."` as the quote.
  `quote_only_in_conditional` (B12) missed it because the rule's stored quote had no
  trailing period, so the proposed span extended one character past the rule span.
  The fact was cited, and the target became `supported` — a false proof against the
  benchmark label. `symbolic._core` now strips edge punctuation before the span
  comparison, so a quote whose only occurrence is the conditional (with or without a
  trailing period) is rejected again. Reproduced in `test_build_symbolic` and
  `test_engine_classify`; the example is now `unknown` and FOLIO has no
  `grounded_mismatch`.

## C. Reproducibility

- **C1. LLM variance (provider-level; selection hardened).** The same problem gives
  different outcomes across runs. Measured on one ProofWriter problem (5 extractions
  each): `T=0.1` → 2 distinct structures; `T=0` → 2 distinct; `T=0` + seed → 2
  distinct. So the router is nondeterministic even at `T=0`, and the seed does not
  fix it (sometimes it looks worse), confirming that a model can not be pinned.
  What the engine *can* control:
  - `ANKYRA_EXTRACT_SAMPLES` best-of-N (`symbolic.quality_key`: repairable gaps →
    source coverage → compactness). `quality_key` is a syntax/grounding metric and
    **frequently ties on logically different structures** (measured: 5 samples of
    one problem split 4:1 yet all scored `(0, -220, 10)`). Ties are now broken by a
    canonical structural fingerprint (`extract._rank_key`), so the pick no longer
    depends on thread/arrival order — the previous nondeterminism was partly
    self-inflicted by concurrent sampling. **Consequence: raising
    `ANKYRA_EXTRACT_SAMPLES` does not improve outcomes and is not pursued** — the
    ranker cannot see the logical difference it would need to select on.
  - `ANKYRA_EXTRACT_PARALLEL` issues samples concurrently; each worker runs in a
    copied context, so the LLM trace records every sample again (it silently lost
    all `extract_problem`/`extract_question` calls before).
  - `ANKYRA_EXTRACT_REPAIRS` bounded repair over repairable gaps, and
    `enforce_grounded` (an atom/rule without a valid source quote is dropped).
  - per-role `ANKYRA_EXTRACT_TEMPERATURE=0` is now honoured (was ignored because
    `0` is falsy in the old `or` fallback).
  Provider-level determinism is accepted as **external and out of scope**: the
  router is not ours to fix, and residual run-to-run variation does not change the
  project's guarantees (strict answers stay `proven`, hypothetical ones stay
  labelled). Optional robustness remains: self-consistency selection and prompt
  stability; see `implementation_plan.md` item 4.

## D. Explanation / narration

- **D1. Language (DONE).** `narrate_explanation(..., language=...)` + `ANKYRA_LANG`
  (default `en`); Russian narration verified faithful to the steps.
- **D2. Degenerate traces (FIXED).** Trivial successful cases name the rule again
  (`rain`) — consequence of B2.
- **D3. Answer revisions (DONE).** The answer can change between waves (unknown
  becomes bound, hypothesis accounting changes); `Revision` records each such
  change with its trigger and the accepted hypotheses, and `Explanation.revisions`
  carries them in wave order. `Conflict.source_ids` names the hypotheses behind the
  competing branches of a specificity conflict, so a defeasible shift is
  attributable. The base is untouched, keeping D3 monotone.

## E. External benchmark — ProofWriter (staged tiers)

Harness: `evals/proofwriter.py` over the committed Tier A sample (45 problems;
open-world synthetic core, depth 0/1/2/3/5; built by
`evals/build_proofwriter_sample.py`). Mapping: `True -> kind yes`,
`False -> kind no`, `Unknown -> kind unknown`, with an explicit polarity check for
negated statements (0 flips observed). No training, no benchmark semantics in the
engine.

Ankyra results (strict deduction is the default; `ANKYRA_EXTRACT_SAMPLES=3`,
several runs — LLM variance is visible run to run, see C1):

| mode | kind accuracy | determinate (True/False) | Unknown | grounded false positives |
|---|---|---|---|---|
| strict (`allow_hypotheses=False`) | 43–45/45 | 29–30/30 | 14–15/15 | 0 |
| abductive (`--hypotheses`) | 43–44/45 | 30/30 | 12–14/15 | 0 |

After B10 (per-rule quantifier sort) a strict N=3 run scored **45/45** (30/30
determinate, all `proven`; 15/15 Unknown), every mismatch shape `match`; the earlier
misses came from the domain-vs-premise ambiguity. Before B10 the misses were honest
`unknown` (`unsupported` / `no_progress` / one `contradiction`) — extraction failed
to supply a rule or a fact, so the engine never turned a miss into a definite
"yes"/"no". The strict gaps that were
closed (see `docs/task.md` §0.3): a one-place copula becomes
`is_a(subject, complement)` (via `StructAtom.predication`), and a rule premise
that only restricts a variable to a declared `ProblemStructure.domain` sort is
dropped as the quantifier's domain rather than treated as an inert
`is_a(?x, person)` condition. Both are deterministic builder rules.

The abductive misses are all hypothetical decisions (`proven_under`), never
grounded; they are analyzed in section F, and the hypothetical-refutation class
has been removed by a guard.

One caveat: the quantifier sort is a formalization assumption authored by the
extractor. An over-declared sort drops a real condition, so it must stay auditable:
it is carried per rule on `Rule.forall` (and the legacy global `Theory.domain`) and
shown in the trace. B10 makes it per-rule rather than global, so one over-declared
sort no longer cuts conditions in unrelated rules.

Two follow-up synthetic observations (**NEEDS INVESTIGATION**; not reproduced on
ProofWriter): (a) *under-derivation* — `enrich.strip_domain_conditions` drops a
global-domain premise even when it is the variable's only binder, leaving a
condition-less rule that can never fire (the per-rule `unroll._normalize_domain`
deliberately keeps the sole binder); (b) *over-derivation, unsound* — an over-declared
sort whose premise coexists with another binder makes the rule fire for non-sort
individuals. See `implementation_plan.md` milestone 8 for the verified examples.

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

**Tier B (75, staged expansion) — measured.** The tiers (`docs/proofwriter.md` §6)
add NatLang on top of the 45 core items. Run (`--tier b`,
`ANKYRA_EXTRACT_SAMPLES=1`): **74/75** kind accuracy (core 45/45, NatLang 29/30), 0
grounded false proofs, determinate 49/50 all `proven`, `Unknown` 25/25. The single
mismatch (`AttNonegNatLang-OWA-111`) is an extraction miss — the paraphrase "wears
all green" became a `wear` relation instead of `is_a(eric, green)` — sensitive to
provider variance (C1); a re-run on the fixed engine reproduced 74/75.

**Tier C (150, staged expansion) — measured; one soundness bug found and fixed.**
First run 147/150 with one **grounded false proof**: `AttNonegNatLang-OWA-15`
(statement `Alan is not red`, label `Unknown`) was "proved" by a cited fact
`NOT is_a(alan,red)` whose quote was the irrelevant `"Alan is very big for being so
young"`. The quote is a valid substring and not from the question, so the classifier
accepted it; B8 was under-implemented — `_quote_in_use` compared quotes exactly,
while the model had *widened* an already-grounded atom witness (`"Alan is very
big"`). Fixed by counting an overlapping span of an already-grounded atom witness
as reuse (rule sentences stay exact, so a standalone fact inside a conditional is
still citable); unit tests added. After the fix and targeted re-runs of the seven
affected items, Tier C is **148/150 (98.7%)**, 0 grounded false proofs, determinate
all `proven`; the two remaining misses are NatLang extraction / formalization
errors (`NatLang-10`: `feels blue` kept as a state predicate; `NatLang-114`:
`blue skin` attached to `skin`), honestly `unknown`.

**Tier D (300, staged expansion) — measured; gate green after the re-run.**
First run, 75 core + 75 NatLang + 150 `depth-3ext`: **296/300 (99%)** (core 74/75,
NatLang 73/75, `depth-3ext` 149/150), determinate 198/200 all `proven`, 0
hypotheses. Four mismatches, triaged by one re-run each: `RelNeg-OWA-D1-1025` and
`AttNonegNatLang-OWA-107` are provider variance (did not reproduce);
`AttNoneg-OWA-D0-2873` and `AttNonegNatLang-OWA-114` reproduce (both findings
below, now CLOSED). After the fixes, a parallel re-run (`--jobs 5`) gave
**297/300 (99%)**, **0 grounded false proofs**, determinate 197/199 all `proven`,
`depth-3ext` **150/150**. One item (`RelNeg-OWA-D3-1062`) hit the item-23 provider
behaviour (empty `question` → no target); a single `--ids` re-run answered it
`proven`, so it is provider variance, not a failure. The only two misses are honest
NatLang extraction errors: `AttNonegNatLang-OWA-108` (`feels blue` kept as a state
predicate) and `AttNonegNatLang-OWA-114` (`blue skin`). See `docs/proofwriter.md`
§6.

- **Gamma/target injection via `reformalize_query` (soundness hole) — CLOSED.**
  `RelNeg-OWA-D1-1025` ("The lion does not chase the lion", `Unknown`) was refuted
  by a wave-0 `reformalize_query` that added the conditions `is_a(lion,red)` and
  `NOT like(lion,rabbit)` — neither is in the question. `classify._reformalize` now
  treats the whole query as fixed by Phase 0: a condition absent from the query is
  `rejected/fabricated_condition`, a substituted target is
  `rejected/target_substituted`, and only `variables` may change (the target may
  still not be dropped, `target_weakened`). Unit tests
  (`tests/test_engine_classify.py`) cover fabrication, substitution and removal.
- **Named-entity conditional over-generalized (extraction) — CLOSED.**
  `AttNoneg-OWA-D0-2873` ("Gary is not rough", `Unknown`) was refuted because "If
  Harry is young then Harry is rough" was extracted as the universal
  `is_a(?x,young) => is_a(?x,rough)`, which fires for Gary. Deterministic code
  cannot catch this without NL parsing (forbidden), so `PROBLEM_SYSTEM` now states
  that a conditional about a specific named individual keeps its constant and is a
  ground implication; only a generic statement is quantified over `?x`. Live case
  `named_conditional` in `evals/problems.jsonl` (see `tests/test_evals_live.py`).
- **Provider accepts an incomplete tool call — WON'T FIX (by design).** A post-fix
  Tier D run rejected 182/300 as "no target extracted": the extractor often returns
  a `ProblemStructure` whose `question` is empty (and `facts` truncated), e.g.
  `facts=1, question=""`. `ProblemStructure.question` defaults to `""`
  (`core/schemas.py`) and `structured.py` accepts a function-calling `parsed` when
  `model_dump()` is non-empty, so the missing field validates silently; the
  question stage then gets `""`, returns `ask=null` and the query becomes
  `instruction`. Reproduced with the pre-fix prompt, so it is independent of the
  two findings above and of the code. This is **not** a soundness hole — every
  mismatch is `undecided_mismatch`/`instruction` with 0 grounded false proofs — it
  only degrades coverage. Decision: the provider owns incomplete structured output;
  no guard is added. If it must be mitigated later, the candidate is a bounded
  retry on an empty `question` in `extract_problem_structure` (a missing required
  output, not NL parsing).

## F. Abduction — false proofs are hypothetical decisions

Harness: `evals/proofwriter.py --hypotheses`, `ANKYRA_EXTRACT_SAMPLES=3`; every run
also records the committed `/tmp`-independent traces under `evals/out/pw_*` (ignored
by git). `score_record` now tags each mismatch with a `shape`
(`mismatch_shape`): `grounded_mismatch`, `hypothetical_decision`,
`question_begging`, `undecided_mismatch`, or `match`.

**Before the refutation guard** the 8 abductive misses shared one shape: every one
was a *negated* Unknown target, answered `refuted` / `proven_under` / `no`. The
wave abduced the missing body literal of a rule whose head is the complement of
the target, and the derived complement "refuted" the negation:

| id | missing literal abduced | rule head |
|---|---|---|
| AttNoneg-OWA-D0-101 | `is_a(erin,green)` | `is_a(erin,round)` |
| AttNeg-OWA-D2-1020 | `is_a(gary,rough)` | `is_a(gary,furry)` |
| AttNoneg-OWA-D2-1021 | `is_a(harry,red)` | `is_a(harry,green)` |
| AttNoneg-OWA-D5-1022 | `is_a(gary,cold)` + `is_a(gary,green)` | `is_a(gary,rough)` |
| RelNoneg-OWA-D0-1011 | `like(cow,bear)` | `need(cow,bald_eagle)` |
| RelNeg-OWA-D2-1012 | `is_a(bear,rough)`, `NOT chase(cow,bear)` | `visit(cow,bear)` |
| RelNeg-OWA-D3-1062 | `see(rabbit,rabbit)` | `is_a(rabbit,young)` |
| RelNoneg-OWA-D3-1033 | `is_a(cow,cold)` | `visit(rabbit,rabbit)` |

This is sound but not grounded: the answers were already labeled `proven_under(H)`,
so it is an *abduction semantics* artifact, not a soundness bug. **Guard (added):**
assuming `P` cannot refute `¬P`; `verify_node` downgrades a hypothesis-backed
refutation to `unsupported` with gap `hypothetical_refutation:` and answers
`unknown`/`not_proven` (`engine/answer.refutation_is_hypothetical`). Unit tests
cover a hypothetical refutation (→ `unknown`) and a hypothetical positive support
(→ unchanged `proven_under`, so Example B is untouched). After the guard no
hypothetical refutation remains in any abductive run.

**Question-begging fact hypothesis (fixed).** The wave could assert the closed
target itself as a fact hypothesis (`RelNoneg-OWA-D1-1009` proposed
`NOT eat(bear,bear)`) and then "derive" the goal from it as `proven_under(H)`.
Now a non-cited fact hypothesis whose atom unifies the *closed* target is
`rejected/question_begging` (`classify._asserts_closed_target`); the guard runs only
where a hypothesis would be created, so a cited descriptive fact that states the
target stays `cited`, and open targets are exempt (a hypothesis may still supply
the binding — Example B is untouched). Live re-check: the problem now returns
`unknown`/`no_progress`.

**Remaining abductive misses.** Extraction contradictions / `no_progress`: honest
`unknown`; C1.

**Two deterministic Phase 0 hardening fixes** came out of these runs (both
unit-tested):

- `settle_query` drops a condition complementary to the target: "is phi?"
  extracted as positive `phi` plus a `¬phi` premise is self-contradictory and made
  the engine report `contradiction`.
- `classify` refuses a quote taken from the interrogative span
  (`_quote_in_question`): one abductive run proved the goal by citing the question
  sentence itself. This enforces "the question is never asserted as a fact" against
  the proposal path, not just extraction.

## Priority

1. **Extraction generalization** seen on ProofWriter (generic nouns, modifier
   retention): the wave may repair it via ledgered hypotheses, and strict mode
   surfaces the assumption instead of hiding it.
2. **Optional: self-consistency selection** (cluster best-of-N extraction samples,
   take the modal structure) — robustness against an unlucky sample, not
   determinism. Provider-level variance itself (C1) is accepted as external and not
   pursued.

## Results summary

State after the extraction-canonicalization, soundness-guard and staged-benchmark
work (`ANKYRA_EXTRACT_SAMPLES=1`):

- **ProofWriter staged tiers (strict, 0 hypotheses):** A **45/45**, B **74/75**,
  C **148/150** (after the B8 span-overlap fix), D first run **296/300**, re-run
  **297/300** (75 core + 75 NatLang + 150 `depth-3ext`); every determinate answer
  `proven` and **0 grounded false proofs** in the re-run. D's gate is now green;
  findings 21–22 are closed. See `docs/proofwriter.md` §6.
- **Abductive mode:** hypothetical refutations are removed (B, guard); the remaining
  misses are hypothetical decisions/question-begging, both explicitly guarded and
  labelled `proven_under`; no grounded false proof.
- **Soundness guards added:** a hypothesis cannot refute (A/B), a non-cited fact
  hypothesis cannot assert the closed target (B), a quote from the question or from
  only inside a conditional cannot license an axiom (B12), and an overlapping span
  of an already-grounded atom witness counts as reuse (B8).
- **Extraction canonicalization:** `relation_kind` ascription/possession/action
  (A, B11); per-rule quantifier sort `forall` (B, B10).
- **Reproducibility:** provider nondeterminism accepted as external; deterministic
  tie-break by structural fingerprint; no best-of-N sampling (`SAMPLES=1`).
- **Closed without implementation:** dropped-conjunct detector (A6, not reproduced).
- Tests: `285 passed, 24 skipped`.
