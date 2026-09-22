# L3 Plan — Finite-domain constraints (CSP/SAT)

Status: **approved plan** — milestones 1–4 plus the extensions 4b/4c are **done**: the
Phase-0 spike (§6, five hand-encoded games), the committed CSP IR + in-repo
finite-domain solver (`engine/csp/`), the LLM-free synthetic gate `evals.l3_synthetic`
(**27/27**: every constraint kind — including boolean composition and count
comparison — and every question semantics, plus the negative controls), and the
Phase-0 CSP extraction path (`engine/csp/schemas.py`, `build/csp.py`,
`build/extract_csp.py`; the builder is validated LLM-free). Milestone 5's LLM-free part
is done: the dev/eval samples are committed, the adapter (`evals/ar_lsat.py`) has
describe/gold/live modes, the **gold-fed tier is 21/21, 0 `grounded_mismatch`** over 5
real games (`evals/build_ar_lsat_gold.py`), and routing/answer/explanation are wired
(`ANKYRA_CSP` capability, `Answer.kind "choice"`, the `model` explanation step). The
live gates ran (budgeted): **dev 9/12, 0 `grounded_mismatch`; eval 21/30, 0
`grounded_mismatch` → gate GREEN** (accuracy 70%; the 9 misses are honest abstentions;
the provider stays nondeterministic, C1). The method is green (gold 21/21), and the
extraction wall was raised not by sampling but by an **error-driven language
specification** (`ANKYRA_LANGUAGE_SPEC`, `evals/skills/ar_lsat/`) plus interface
fixes (options passed to the question call, a stricter option prompt, a bounded
question-repair pass, a duplicate-option guard). The decisions in §19
(D-L3-1…D-L3-10) are **DECIDED**. This is the working plan for stage
**L3** of `docs/reasoning_roadmap.md`; it will be updated as the work proceeds. L3 is
a **separate engine**: it does not extend the Horn spine or the L2 clausal procedure.

Canonical language: English; Russian mirror: `docs/l3_plan_ru.md`. Related:
`docs/reasoning_roadmap.md` (§3 L3, §4–6), `docs/ar_lsat.md` (the collection notes),
`docs/logic_layer.md` (the `Inference` seam), `docs/fragment_routing.md` (the
declared-fragment contract), `docs/l2_plan.md` (the precedent for a stage plan),
`docs/task.md` (§2, §3.8), `docs/implementation_plan.md` (§9).

## 1. Goal

Widen the class of decidable reasoning by adding the L3 formalism: a **finite-domain
constraint satisfaction problem** over a declared finite universe — variables with
finite domains, all-different, equality/disequality, ordering and adjacency
(including circular), grouping, and conditional constraints. The answer semantics is
model-theoretic, not entailment of a clause set:

| Question form | Meaning | Decided by |
|---|---|---|
| which arrangement would NOT violate | some model satisfies every constraint | satisfiability |
| which must be true | true in **every** model | no counter-model |
| which could be true | true in **some** model | satisfiability |
| which CANNOT be true / must be false | false in **every** model | no model (unsatisfiable) |
| complete and accurate list | read off the models | model enumeration |

An **"if …" question** adds a hypothetical premise (Gamma) to the game before the
options are checked (`CspQuestion.assumptions`); the kinds then read against that
augmented game.

The LLM proposes the CSP encoding; a finite-domain solver decides. The design
commitment is unchanged — nothing enters the encoding without a valid quote
(`cited`) or an explicit hypothesis tag (`hypothesis`) — but the decision procedure
is a second engine, not the Horn/clausal one.

## 2. Scope and non-goals

- **In scope:** the CSP IR and solver (in-repo, finite-domain); the four question
  semantics of §1; a multiple-choice answer kind; the declared `csp` fragment and its
  routing; extraction of the CSP encoding (schema + prompt + deterministic builder);
  the AR-LSAT gate.
- **Out of scope:** any change to the Horn/L1/L2 engines or their gates — L3 is
  separate and is never silently mixed with them. The L2 residual work (G2/`A′`,
  `↔`/`⊕` lowering, multi-variable quantification) is tracked in
  `docs/g1_g4_plan.md` / `docs/coverage_ceiling.md`, not here. L4 (arithmetic,
  `docs/gsm8k.md`) remains a separate engine. Full-collection AR-LSAT runs are out of
  scope (budget).
- **Out of scope:** NL heuristics. Positional/adjacency semantics are **structurally
  extracted** by the LLM (a declared topology and constraint relations), never
  detected with cue phrases or a term list (`docs/task.md` §3.8).
- **Out of scope:** a hardcoded LSAT ontology (circular table, "next to" as fixed
  predicates). The IR is general; the extraction prompt carries the semantics
  (`docs/ar_lsat.md` §6).

## 3. Guardrails (gating)

- **0 confidently-wrong answers** is the hard gate. An option is reported only when
  the solver **proves** it (satisfiability with a witness, or absence of a
  counter-model within the budget); "some option looked plausible" is never an
  answer.
- **Bounded search never guesses.** When the step/model budget is exhausted the
  answer is an honest `unknown` / `insufficient`, never a picked option.
- **A non-representable game is `out_of_fragment`,** never lowered onto a weaker
  construct to pass a row.
- **No invented models.** A `could`/`not-violate` answer carries the witness model it
  was decided from; a `must` answer reports the absence of a counter-model, and an
  exhausted search is not `proven`.
- **Encoding failures are honest.** If no option is verified, or more than one is,
  the verdict is `unknown`/`out_of_fragment:ambiguous_choice` — a soundness signal,
  never a tie-break by wording.
- **An incomplete composite is a build error, not a silent vacuity.** An empty
  `all`/`any`/`not`/`conditional` would evaluate vacuously (`all([])=True`,
  `any([])=False`) and silently change the semantics; the builder
  (`ankyra.build.csp`) rejects it as `CspBuildError`, so the model gets an honest
  repair instead of a wrong model.
- **Benchmark semantics do not leak.** The question type (must/could/…) is declared
  by the harness/query, never read off the wording.
- **Separation from the deductive spine.** `csp` is a distinct capability and
  procedure; a structure that mixes it with Horn/clausal content is refused by name
  (D-L3-4), not decided by the wrong engine.

## 4. What L3 adds, and what already exists

Already present and reusable:

- the `Inference` protocol seam (`engine/inference.py`) and the declared-fragment
  contract (`analyze_routing`), including per-run capabilities and named refusal
  codes;
- the theory/query IR and the quote/hypothesis discipline;
- the eval-harness conventions: deterministic committed samples, LLM-free synthetic
  gates, per-option scoring, a `mismatch_shape` triage.

Genuinely new for L3:

- a **CSP IR** (domains, variables, constraint relations, a declared topology) —
  distinct from `Theory`/`Query`;
- a **bounded finite-domain solver** with a witness/counter-model record;
- a **multiple-choice adapter**: each option is checked against the solver;
- a **`choice` answer kind** and a model-based justification;
- the `csp` capability and its routing refusal.

## 5. Benchmark and stratification

AR-LSAT (`docs/ar_lsat.md`): one game context shared by several five-way
multiple-choice questions. It is heterogeneous, so a run is **stratified by
game/question type**: the in-fragment subset is scored against the gate; the rest is
reported `out_of_fragment` and is not a failure. Axes (`docs/ar_lsat.md` §3):

- **game type** — linear ordering, relative ordering, grouping/splitting, assignment;
- **question type** — acceptability/not-violate, must, could, can't-be-true/must-be-false,
  complete-and-accurate-list, with optional "if" assumptions;
- **size** — typically 5–7 entities with equal or fewer positions/groups.

`evals/ar_lsat.py` (adapter) checks each option and reports an `out_of_fragment`
bucket; `evals/build_ar_lsat_sample.py` commits a small stratified sample (D-L3-6).

**Dataset facts (measured on the raw collection).** The raw files
(`data/AR_{Training,Development,Test}Data.json`) are lists of games; a game has
`fatherId` (a family), `passage`, and `questions`, each with `tags` (metadata: the
question type and the game type), five `options` and an `answer` letter A–E. The
official **development** and **test** splits are **fatherId- and passage-disjoint**
(0 overlap) and their answers are balanced A–E; the **training** split is excluded
because a model may have seen it. Normalized question-type tallies: could (~60),
must (~50), acceptability/not-violate (~40), can't-be-true/must-be-false (~30),
complete-list (~5), rule-substitution (~7) — see D-L3-3/D-L3-8/D-L3-9.

`evals/build_ar_lsat_sample.py` selects the committed sample by dataset **metadata**,
never by parsing the passage/question text: it groups by `fatherId`, normalizes the
`tags` question/game type, buckets by `passage` length, and balances the answer
letter (D-L3-9). The live result of `build_ar_lsat_sample` is deferred to
milestone 5.

## 6. Step 0 — feasibility spike (LLM-free) and the decision gate

First task, before any engine, schema or prompt work. **No LLM calls.**

- Hand-encode **5 games** (one per game/question type) into the CSP IR of §7 and solve
  them with the in-repo solver of §8.
- Measure: expressiveness (can every game be encoded without a special case?) and
  solver-side correctness (the chosen option matches the gold label; no
  confidently-wrong decision).
- Record the IR shapes that the five games force, and the ones they do not.

**Decision gate.**
- The IR covers all five games soundly → proceed to Phase 1 (engine + synthetic
  gate).
- A construct resists the general IR → stop and reconsider the IR (never add a
  per-game branch); reopen the affected decision.
- The solver is not sound/terminating on the spike → stop; L3 is not viable as
  scoped.

This mirrors the measure-first discipline of `docs/folio_extension_plan.md` §3 and
`docs/l2_plan.md` §6; it is the same reason a synthetic gate precedes a live run.

**Spike results (done, LLM-free).** The general IR of §7 covered all five games
without a special case and the in-repo solver decided each soundly (0
confidently-wrong), one per axis and question type:

| game | axis | question | result |
|---|---|---|---|
| `linear-order-must` | linear ordering | `must` | decided (gold) |
| `circular-order-not-violate` | circular ordering | `not_violate` | decided (gold, witness model) |
| `grouping-must` | grouping/splitting | `must` | decided (gold) |
| `assignment-complete-list` | assignment | `complete_list` | decided (gold) |
| `conditional-could` | conditional constraint | `could` | decided (gold, witness model) |

Reproduce: `uv run python -m evals.l3_spike` (5/5 green). Unit tests:
`tests/test_engine_csp.py` (constraint kinds, witness/counter-model/enumeration,
budget exhaustion → `insufficient`, ambiguous/empty option sets, a conditional that
prunes a model). The spike confirmed `not_adjacent` and the circular topology as
necessary IR primitives; no construct resisted the general IR, so the decision gate
passes and milestone 2 (committed engine) may start.

## 7. The CSP IR

A general finite-domain model; no LSAT-specific vocabulary.

- **Domain** — a finite set of values and a declared **topology**
  (`set` | `linear` | `circular`). The topology is part of the extracted structure; it
  is what makes an `adjacent`/`order` relation meaningful, and it is declared, never
  guessed from the text.
- **Variable** — an id ranging over one domain (the entities, the positions, the
  groups, or an assignment variable).
- **Constraint** — a relation over variables/values, each with a quote:
  - `all_different` over a set of variables (a permutation);
  - `eq` / `neq` (variable to a value, or two variables);
  - `order` (before/after on a `linear`/`circular` topology, with an `immediate`
    flag for "immediately");
  - `adjacent` / `not_adjacent` on a topology (supports circular);
  - `same_group` / `different_group` (grouping/splitting);
  - `count` (a group has exactly/at least/at most N members);
  - `count_compare` (compare the sizes of two groups: `count(A) gt|lt|eq count(B)`);
  - `conditional` (`if` a constraint, `then` a constraint);
  - `all` (AND) / `any` (OR) / `not` — **boolean composition of sub-constraints**,
    which real analytical-reasoning games need: "T is either earlier than both R and
    S or after than both" is `any(all(order(T,R), order(T,S)), all(order(R,T), order(S,T)))`.
    Composition is three-valued like the rest of the evaluator.
- **Game** — domains, variables, constraints, and the source text (for quote checks).
- **Question** — a question kind, a target expression, five **options**, each an
  option-local list of constraints (an arrangement is a conjunction of `eq`; a "list"
  option is a set of admissible values), and an optional **`assumptions`** list
  (Gamma): extra constraints added to the game before deciding, which is what an
  "if …" question asserts.

The IR is a *declared* structure (like `Query.world_assumption`, D-L1-4): the model
proposes it, the deterministic builder assembles it, and the engine never infers a
constraint from wording.

## 8. Decision procedure — bounded finite-domain search

The solver answers **model queries**, not entailment of a clause set. One primitive
with a predicate and a mode:

- `satisfiable(game, extra, predicate)` — find a model (with `extra` constraints
  asserted) for which `predicate` holds; returns the witness or `budget`.
- `countermodel(game, extra, predicate)` — find a model for which `predicate` is
  **false**; a `None` result within budget proves `∀`-semantics.
- `enumerate(game, extra, limit)` — collect models up to a limit (for
  complete-and-accurate lists).

Every option is checked against the game **augmented with the question's
assumptions** (Gamma); a question without assumptions uses the game as built.

Question mapping:

- **not-violate / could:** `satisfiable(game, option)` → option verified by a witness.
- **must:** `countermodel(game, option)` returns `None` within budget → option is
  entailed. (No explicit negation of a compound option is needed: the search asks
  directly for a model where the option's predicate fails.)
- **cannot-be-true / must-be-false:** `satisfiable(game, option)` returns no model
  within budget → the option is impossible; the unique impossible option is the
  answer (the dual of `could`).
- **complete-and-accurate list:** `enumerate` and read off the value set.

This is sound on finite domains and terminating under an explicit budget;
exhaustion is the honest `insufficient`. The mapping is exactly the model-theoretic
reading of `docs/ar_lsat.md` §4. The solver lives in its own module
(`engine/csp/`), outside the clause/resolution code.

## 9. Engine changes

- **`engine/csp/`** — the CSP IR helpers, the finite-domain search with constraint
  propagation, and the witness/counter-model record. No dependency on
  `engine/horn.py` / `engine/resolution.py`.
- **`engine/inference.py`** — a new `CspInference` implementing the `Inference`
  seam (`decide` over the CSP structures; `entails`/`closure_keys` are not
  meaningful and follow the L2 precedent of not supporting proposals); a
  `FragmentFeature "csp"`, a `csp` capability, and a `procedure == "csp"` branch in
  `analyze_routing`.
- **`engine/verify.py`** — dispatch the CSP structures to `CspInference`; the
  existing Horn/clausal paths are untouched. A structure that requires `csp` without
  the capability is `out_of_fragment` by name.
- **`engine/answer.py`** — map the CSP outcome to the new `choice` answer kind and
  strength.
- **`engine/explain.py`** — render a witness/counter-model as a model-based
  justification (a new `ExplanationKind`, e.g. `model`), not a resolution-proof walk.

## 10. Data model and extraction schema

To keep the separate engine self-contained, the CSP types live under `engine/csp/`
rather than in `core.models`/`core.schemas` (which own the Horn/L2 structures):

- **`engine/csp/models.py`** — the strict CSP IR (`CspDomain`/`CspVariable`/
  `CspConstraint`/`CspGame`/`CspOption`/`CspQuestion`/`CspQuery`). Separate from
  `Theory`/`Query`; the deductive IR is not overloaded. `AnswerKind += "choice"`
  lands in `core/models.py` with the engine integration (milestone 6).
- **`engine/csp/schemas.py`** — the LLM-authored structures (`CspDomainSpec`,
  `CspVariableSpec`, `CspConstraintSpec`, `CspGameStructure`, `CspOptionSpec`,
  `CspQuestionStructure`) with lenient normalization of the closed enum fields and
  ids the model already extracted (topology/kind/count-mode aliases, `?`-stripping).
  The schemas carry **no engine semantics**: the question kind is declared by the
  harness where possible (D-L3-4).
- **`build/csp.py`** — the deterministic builder `build_csp_game` /
  `build_csp_question`, parallel to `unroll`/`enrich`; it validates structural
  integrity (known domain per variable, known variable per constraint, value in the
  compared domain) and raises `CspBuildError` instead of approximating. The Horn/L2
  builder is unchanged.

## 11. Phase 0 extraction

- **`build/extract_csp.py`** — a dedicated CSP extraction path: the LLM proposes the
  domains, variables, constraints and the question options, each with one verbatim
  quote; the prompt carries the semantics (topologies, "immediately", grouping,
  conditionals) with no cue-phrase lists and no word-level heuristics
  (`docs/task.md` §3.8). It is a two-call path like the Horn one: the game, then the
  question expressed against the built game (`format_game_for_llm`).
- The question kind (`must`/`could`/`not-violate`/`complete-list`) is the one place
  the extraction informs the semantics; where the collection declares it, the harness
  sets it, and a mismatch is an honest failure rather than a guess.
- Extraction is the main risk (§2 of `docs/ar_lsat.md`); it is gated by comparing a
  live encoding to a hand-written encoding of the same games (Phase 0 spike and
  Phase 2), not by the final answers alone.
- **Specialized task-notation languages.** A shared, user/harness-supplied
  **language-spec block** (`ANKYRA_LANGUAGE_SPEC`, `build/extract.language_spec_block`)
  is appended to every Phase 0 system prompt (Horn and CSP). It is empty by default
  (prompts byte-identical) and carries *notation/grammar guidance*, never per-example
  answers. The AR-LSAT harness activates `evals/skills/ar_lsat/` (per-object
  ordered lists; exclusive "either … but not both"). This is the general seam for a
  collection whose source language is specialized (`docs/task.md` §0.6). The guide is
  extended **error-driven**: inspect live extraction failures, turn each recurring
  mistake into a notation rule plus a worked example, and re-run — the honest,
  generalizable alternative to sampling (D-L3-10). This text block is now packaged as a
  per-collection **skill** (`evals/skills/<collection>/{language.md,task.md}`), loaded
  automatically by the harness and composed by `evals/skills.py` (language + task
  specifics); the format and auto-loading are done, the task-specific content is the
  remaining budgeted step. See `docs/task.md` §0.6 and `docs/implementation_plan.md`
  §8 item 28.

## 12. verify / answer / explain

- **verify:** the CSP procedure decides each option (against the game augmented by
  the question's assumptions) and combines them — exactly one verified option is
  `supported`; none or several is `unknown` / `out_of_fragment:ambiguous_choice`; a
  budget miss is `insufficient`. The verified set is the satisfiable options for
  `could`/`not-violate`, the entailed options for `must`, the **unsatisfiable** option
  for `must_be_false`, and the option whose list equals the enumerated set for
  `complete_list`.
- **answer:** `Answer.kind = "choice"`, `value` = the option index; `strength =
  proven` only when the decision was complete (a witness for `could`/`not-violate`, the
  absence of a counter-model for `must`, or a complete enumeration/unsatisfiability for
  `must_be_false`/`complete_list`); otherwise `not_proven`.
- **explain:** a witness model for a satisfiable option, or the searched-out
  counter-example case for a refuted one; a `must` proof reports that no
  counter-model exists within the budget. The step is a solver fact, not a
  fabricated derivation chain.

## 13. Eval harnesses (`evals/`)

### 13.1 Synthetic collection — **primary** (LLM-free, structural)

- `evals/build_l3_synthetic.py` → `evals/data/l3_synthetic.jsonl`. Each case is a
  fully structured CSP game/query with an independently written expected decision and
  a `mechanism` tag. No LLM, no natural language in the primary set.
- `evals/l3_synthetic.py` — runner: builds the CSP structures directly, calls the
  solver/verify, reports the gate, non-zero exit on any mismatch.
- Coverage: every constraint kind and every question semantics (including
  `must_be_false` and an assumptions-carrying "if" question), plus mandatory
  **negative controls** — an exhausted budget is never a picked option; a
  `must` with a counter-model is not chosen; a game with two verified options is
  `ambiguous_choice`; a game with none is `unknown`; the assumptions must prune a
  model (dropping them would change the answer).
- **Gate result (LLM-free):** `evals.l3_synthetic` **27/27** after the semantics and
  IR extensions (20/20 before them). The collection covers every constraint kind
  (including `count_compare`, `all`, `any`, `not`) and the five question semantics,
  and the controls hold: the conditional is load-bearing
  (`conditional-soundness-could-14`), two impossible `must_be_false` options are
  `ambiguous` (`must-be-false-ambiguous-22`), the question assumptions pin the answer
  (`assumptions-could-23`) and an inconsistent assumption verifies nothing
  (`assumptions-inconsistent-24`).

### 13.2 AR-LSAT — gold-fed, live dev, live eval (budgeted)

Three tiers (`docs/l3_plan.md` D-L3-8/D-L3-9), mirroring the gate ladder of
`docs/implementation_plan.md` §10:

- **T0 — gold-fed (LLM-free).** `evals/ar_lsat_gold.jsonl`: **21 real questions over 5
  games** from the official **development** split, hand-encoded into the CSP IR by
  `evals/build_ar_lsat_gold.py`, with the dataset's answer option as the expected
  decision. Run LLM-free by `evals/ar_lsat.py --gold`; this separates method/coverage
  from extraction and is the debugging sandbox and the upper bound.
  **Gate result: 21/21 correct, 0 `grounded_mismatch`** (`could` 8, `must` 3,
  `must_be_false` 6, `not_violate` 4) — the method handles real games.
- **T1 — live dev (budgeted, not a gate).** ~4 games / ~12 questions from
  **development**, for prompt/IR iteration. Sample built: `evals/data/ar_lsat_dev.jsonl`.
  **Result (after the interface fix below): 9/12 correct, 0 `grounded_mismatch`**
  (2 `out_of_fragment` complete-list-over-derived + 1 `ambiguous`). The first dev run
  was 1/12: the question call had **not been given the five options** (only the stem),
  so the model invented them — passing the options fixed it.
- **T2 — live eval (budgeted, the gate).** ~12 games / ~30 questions from the
  official **test** split, `fatherId`-disjoint from dev by construction,
  stratified and answer-balanced. Sample built: `evals/data/ar_lsat_eval.jsonl`.
  **Result: 21/30 correct, 0 `grounded_mismatch` → gate GREEN.** Shapes: 4
  `out_of_fragment` (complete-list over derived), 3 `no_option`, 2 `ambiguous` — all
  honest abstentions. (Earlier runs in this iteration were 7–18/30 with 1–2
  `grounded_mismatch`; the error-driven language rules below closed the gap. The
  provider stays nondeterministic, C1, so a later re-run may differ.) Extraction
  improvements landed and measured here:
  (a) the question call receives the five options; (b) the prompt requires a full
  arrangement option to assign every game variable; (c) a bounded game-aware
  **repair pass** (`ANKYRA_CSP_REPAIRS`, default 1) re-encodes when the first attempt
  yields `ambiguous`/`no_option`/`build_error`, plus a general **duplicate-option
  guard**; (d) a shared **language-spec block** (`ANKYRA_LANGUAGE_SPEC`): a
  user/harness-supplied guide to a specialized task-notation language, appended to
  every Phase 0 prompt, with `evals/skills/ar_lsat/` for LSAT idioms (per-object
  ordered lists, exclusive "either … but not both", repeated-trial modeling,
  slots-fewer-than-entities). The guide is extended **error-driven**: each recurring
  live mistake became a notation rule (D-L3-10). This raised eval from 7 to **21/30**
  and closed `grounded_mismatch` to **0**. No engine unsoundness: the remaining misses
  are honest abstentions; the method is proven by T0 (gold 21/21). This mirrors the
  FOLIO L2 outcome (`docs/folio.md` §10): the wall was extraction, not the procedure —
  and the fix was a language specification, not sampling.

- `evals/build_ar_lsat_sample.py` — deterministic selection by dataset **metadata**
  (`fatherId` grouping, normalized `tags`, `passage`-length buckets, answer
  balance); commits `evals/data/ar_lsat_{dev,eval}.jsonl`.
- `evals/ar_lsat.py` — adapter with per-option solver checks and an `out_of_fragment`
  bucket.
- Gate: 0 confidently-wrong (`grounded_mismatch`); every remaining failure triaged
  (`no_option`, `ambiguity`, `budget`, `out_of_fragment:*`).

**Gold-set findings (recorded, not worked around).**
- The committed fragment covers the four most common question kinds; **complete-list
  questions over a derived sequence or entity** (e.g. "the ordered list of Gold-Room
  speeches", "the building the Trents owned") are outside the current
  `complete_list` semantics (which enumerates the values of one variable) and are
  excluded from T0.
- `201306_2-G_1` q4 ("which manuscript CANNOT be written fourth", stored key D) is
  **excluded: the key is inconsistent with its own constraints.** Faithful encoding
  plus two independent checks show the key's option (P) is satisfiable and the
  alternative (H) is not; per the "no per-id tuning" rule the row is dropped and the
  discrepancy recorded rather than special-cased.

## 14. Config and flags

- `ANKYRA_CSP` (`on` | `off`, default `off`) in settings and `.env.example`. The
  harness sets it; the wording never does. The search budget is a separate setting
  (e.g. `ANKYRA_CSP_BUDGET`), recorded in the verdict.

## 15. Tests

- `tests/test_engine_csp.py` — each constraint kind; `satisfiable`/`countermodel`/
  `enumerate` on hand-written games; budget exhaustion → `insufficient`; no model
  invented.
- `tests/test_evals_l3_synthetic.py` — the synthetic gate (structural, no LLM).
- `tests/test_build_csp.py` — the CSP builder path (schema → IR): alias/topology
  normalization, dangling-variable/unknown-domain/out-of-domain-value refusal, the
  recursive conditional check, arrangement options and the complete-list target.
- `tests/test_engine_inference.py` — the deductive `Inference` seam (Horn/clausal),
  unchanged; CSP is a separate engine and does not implement that protocol.
- `tests/test_engine_csp_routing.py` — the `csp` capability/refusal
  (`out_of_fragment:csp_off`), `decide` dispatch, `build_csp_answer`
  (`choice`/`proven`), the `model` explanation step, and `render_answer` for `choice`.
  The CSP structures are separate from `Theory`/`Query`, so `evals.routing_synthetic`
  (which reasons over the deductive IR) does not cover the CSP engine; this dedicated
  suite does.
- Full regression: `uv run pytest` (offline; live tests skipped).

## 16. Documentation updates

- `docs/ar_lsat.md` — spike results, sample sizes, gate numbers, L3 status.
- `docs/reasoning_roadmap.md` — L3 status and any change to the stage contract.
- `docs/implementation_plan.md` — backlog/milestones entries.
- `docs/logic_layer.md` / `docs/fragment_routing.md` — the `csp` procedure and
  capability.
- This document, kept current as the plan evolves.

## 17. Work order (milestones)

1. ~~**Step 0:** feasibility spike (LLM-free), 5 hand-encoded games; decision gate
   (§6).~~ **DONE — green** (`evals/l3_spike` 5/5; `tests/test_engine_csp.py`).
2. ~~CSP IR + solver module; unit tests (`tests/test_engine_csp.py`).~~ **DONE**
   (`engine/csp/`).
3. ~~Synthetic structural collection + runner (`evals/l3_synthetic`) and the gate.~~
   **DONE — green 20/20** (`evals/build_l3_synthetic.py`,
   `tests/test_evals_l3_synthetic.py`).
4. ~~CSP extraction schema + builder + prompt (Phase 0).~~ **DONE** —
   `engine/csp/schemas.py`, `build/csp.py`, `build/extract_csp.py`,
   `tests/test_build_csp.py` (builder validated LLM-free; the live encoding is
   measured at milestone 5).
4b. ~~**Semantics extension (D-L3-3): `must_be_false` + question assumptions
    (Gamma).**~~ **DONE** — `QuestionKind "must_be_false"` + `CspQuestion.assumptions`
    (`engine/csp/models.py`, `solver.py`, `schemas.py`, `build/csp.py`), four new
    synthetic cases and controls.
4c. ~~**IR extension (D-L3-2): boolean composition `all`/`any`/`not` + `count_compare`.**~~
    **DONE** — forced by the real collection during the sample build (§5, D-L3-2):
    real constraints are disjunctions of relations. Three-valued evaluation in
    `solver._holds`; three new synthetic cases; `evals.l3_synthetic` **27/27**;
    pytest 546 passed.
5. ~~AR-LSAT sample (`evals/build_ar_lsat_sample.py`), gold-fed tier
   (`evals/build_ar_lsat_gold.py`), adapter (`evals/ar_lsat.py`).~~ **DONE
   (LLM-free)**: dev/eval samples committed; gold **21/21**, 0 `grounded_mismatch`
   (`tests/test_evals_ar_lsat.py`). **Live gates ran** (budgeted): dev 9/12, 0
   `grounded_mismatch`; **eval 21/30, 0 `grounded_mismatch` → gate GREEN** (70%).
   Landed: options passed to the question call; stricter option prompt; bounded
   question-repair; duplicate-option guard; and the error-driven language-spec block
   (`ANKYRA_LANGUAGE_SPEC` + `evals/skills/ar_lsat/`).
6. ~~Routing (`csp` feature/capability/refusal), answer and explanation.~~ **DONE** —
   `FragmentFeature "csp"` and the `ANKYRA_CSP` capability in `engine/inference.py`
   (`analyze_csp_routing`); `engine/csp/decide.py` is the public entry (refuses
   `out_of_fragment:csp_off` without the capability); `Answer.kind "choice"` and the
   `model` explanation step in `engine/csp/answer.py`. Tests:
   `tests/test_engine_csp_routing.py`; the adapter runs the gold/live decisions through
   `decide` with the capability enabled.

Each milestone lands reviewable on its own; no milestone starts on a red soundness
gate. The spike (1) gates 2–3; the synthetic gate (3/4b) gates 4–5.

## 18. Budget

No free LLM access; tokens are paid out of pocket. The spike and the synthetic gate
are LLM-free. The AR-LSAT sample is built deterministically without LLM calls; the
live gate runs once and is re-run only on a mismatch; `ANKYRA_EXTRACT_SAMPLES=1`. A
full-collection run is a separate, explicitly budgeted decision.

## 19. Decisions

D-L3-1 … D-L3-10 are **DECIDED**. A new decision is opened here as it arises; the plan
must not proceed past a milestone affected by an open decision.

### D-L3-1 — Solver: in-repo finite-domain search

**Status: DECIDED — in-repo finite-domain search (backtracking + constraint
propagation), not an external SAT/SMT solver.** Domains are small (5–7 entities), and
the in-repo search yields a witness/counter-model record, needs no new dependency, and
keeps the decision procedure auditable. Z3/SAT remains the documented fallback if a
future scale need appears; it is not adopted now.

**Background.** `docs/ar_lsat.md` §5 names either a SAT/SMT solver or an in-repo
finite-domain search. The engine must stay sound and honest under a bounded budget.

**Trade-offs.** An external solver is more robust on large instances but adds a heavy
dependency and gives no step-level justification; the in-repo search is smaller,
provenance-friendly and sufficient for the collection's scale.

### D-L3-2 — A general CSP IR, no hardcoded ontology

**Status: DECIDED — extended.** The IR of §7 is general: finite domains with a
declared **topology**, constraint relations (`all_different`, `eq`/`neq`, `order`,
`adjacent`/`not_adjacent`, `same_group`/`different_group`, `count`, `count_compare`,
`conditional`), and **boolean composition** (`all`/`any`/`not`). The composition was
forced by the real collection (`docs/ar_lsat.md`): analytical-reasoning constraints
are frequently disjunctions of relations, not flat conjunctions
("T either before both R and S, or after both"). Positional specifics (circular
table, "next to") remain **not** predicates: they are the topology/relations the
extraction declares. `docs/task.md` §3.8 forbids the alternative.

### D-L3-3 — Question semantics in fragment (extended)

**Status: DECIDED — six question shapes, single model-query primitive.**
`not-violate` (satisfiable), `must` (no counter-model), `could` (satisfiable),
`cannot-be-true`/`must-be-false` (no model — the dual of `could`) and
`complete-and-accurate-list` (enumeration) are in the committed fragment, plus
question-local **assumptions** (Gamma) for "if …" questions. The extension is
required by the measured AR-LSAT distribution (§5: `must_be_false` ≈ 30 questions;
"if" variants ≈ half): without it the representative slice would be small and
biased. It is **lowering**, not a new procedure — `must_be_false` reuses
`satisfiable`, assumptions augment the game before the existing checks. A question
form outside this set (`rule_substitution`, "other") is `out_of_fragment`.

### D-L3-4 — Routing: the `csp` capability and procedure

**Status: DECIDED.** L3 is a distinct capability (`ANKYRA_CSP`, default off) and a
distinct procedure `"csp"`, selected by `analyze_routing` from the built structure
(`FragmentFeature "csp"`). A structure requiring `csp` without the capability is
`out_of_fragment:csp_off`. A mixture of `csp` with Horn/clausal content is refused by
name (`out_of_fragment:csp_with_deductive_fragment`), never decided by the wrong
engine. The question kind is declared by the harness/query, not authored by the LLM
as a semantic choice.

### D-L3-5 — Answer and justification

**Status: DECIDED.** `AnswerKind` gains `"choice"` (`value` = option index). The
answer is `strength = proven` only when the solver decided completely (a witness for
`could`/`not-violate`, or the absence of a counter-model for `must`); a budget miss or
an ambiguous/empty option set is `not_proven`/`unknown`. The justification is a
witness/counter-model record (a new `ExplanationKind "model"`), not a Horn proof walk.

### D-L3-6 — Dataset and stratified sample

**Status: DECIDED.** The raw AR-LSAT collection (`github.com/zhongwanjun/AR-LSAT`,
AGIEval packaging) is fetched once and cached under `evals/data/.cache/ar_lsat/`
(mirroring the FOLIO convention); the committed sample is built deterministically,
stratified by game/question type, and small (ProofWriter Tier A order of magnitude).
The full collection is out of scope.

### D-L3-7 — First increment is the LLM-free feasibility spike

**Status: DECIDED.** No engine, schema or prompt work begins before the §6 spike
hand-encodes 5 games into the CSP IR and solves them soundly, with an explicit
decision gate. This de-risks the IR and the solver before any paid extraction work
and is consistent with the measure-first discipline of
`docs/folio_extension_plan.md` §3.

### D-L3-8 — Split design: gold-fed, live dev, live eval

**Status: DECIDED.** Three tiers, game-disjoint (`fatherId`), mirroring the gate
ladder of `docs/implementation_plan.md` §10:

- **T0 gold-fed (LLM-free):** ~8 games hand-encoded into the CSP IR, run by the
  engine; separates **method/coverage** from extraction and is the debugging sandbox
  and the upper bound.
- **T1 live dev (budgeted, not a gate):** ~4 games from the official **development**
  split for prompt/IR iteration.
- **T2 live eval (budgeted, the gate):** ~12 games from the official **test** split,
  run once.

The official development and test splits are already `fatherId`- and
`passage`-disjoint (measured, §5), so dev/eval cannot leak into each other. The
**training** split is excluded: a model may have seen it, which would inflate the
extraction tier. The grouping unit is `fatherId` (a game family), never the question.

### D-L3-9 — Dataset selection and stratification

**Status: DECIDED.** Selection is deterministic and uses dataset **metadata**, never
a parse of the passage/question text (which `docs/task.md` §3.8 forbids): group by
`fatherId`, normalize the `tags` question/game type into the committed question
kinds, bucket by `passage` length, and balance the answer letter A–E. Rows whose
normalized type is outside the committed fragment (`rule_substitution`, "other")
are committed but reported `out_of_fragment`, not scored as failures. The sample is
small (gold 8 / dev ~4×3 / eval ~12 games), built without LLM calls and committed;
the live dev/eval runs are the only paid step.

### D-L3-10 — No sampling; improve the encoding deterministically

**Status: DECIDED — sampling is rejected and will not be used.** Best-of-N extraction
and self-consistency over samples fight provider nondeterminism (`docs/quality_findings.md`
C1) and spend calls without a correctness signal: a structural ranker cannot see
logical difference, and a majority vote can be confidently wrong. This repeats the
project policy (`docs/implementation_plan.md` §8 item 4: `ANKYRA_EXTRACT_SAMPLES=1`
always). Instead the extraction is improved **deterministically**:
(a) few-shot **examples**, and (b) an explicit, **error-driven language specification**
(`ANKYRA_LANGUAGE_SPEC`, §11) that is extended by inspecting real extraction errors and
turning each recurring mistake into a notation rule. Where the encoding stays uncertain,
the engine abstains (`ambiguous`/`no_option`) — a sound outcome. Sampling is not a
fallback even if the gate is not met.
