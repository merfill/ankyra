# Architecture — Ankyra

Ankyra is a domain-general hybrid neuro-symbolic reasoning engine. Given a
self-contained natural-language problem (conditions plus a question), it emits a
step-by-step, mechanically verifiable reasoning trace and an answer with an
explicit logical status. The governing rule is **the LLM proposes, the symbolic
engine decides**: no fact enters the theory without a verbatim quote (`cited`) or
an explicit hypothesis tag (`hypothesis`).

## 1. Layers

```
                        ┌──────────────────────────────────────────┐
   user text ─────────▶ │  graph/    orchestration (LangGraph)      │
                        │  engine/cycle  linear driver (API)        │
                        └───────────────┬──────────────────────────┘
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        ▼                               ▼                               ▼
┌───────────────┐              ┌─────────────────┐            ┌──────────────────┐
│ build/        │              │ engine/         │            │ llm/             │
│ Phase 0       │              │ Phase 1–3       │            │ client,          │
│ unroll/enrich │              │ Horn + cycle +  │            │ structured JSON, │
│ extract/query │              │ explain         │            │ trace            │
└──────┬────────┘              └────────┬────────┘            └──────────────────┘
       │                                │
       └──────────────┬─────────────────┘
                      ▼
               ┌──────────────┐
               │ core/        │  domain models + Phase 0 schemas
               └──────────────┘
                      ▲
               ┌──────────────┐
               │ config/      │  Dynaconf (ANKYRA_*)
               └──────────────┘
```

- `core/` — the data model, shared by every layer. No I/O, no LLM.
- `config/` — Dynaconf settings, env prefix `ANKYRA`.
- `llm/` — provider client factories, the structured-JSON helper, and an opt-in
  call trace.
- `build/` — Phase 0: LLM extraction plus deterministic assembly of the theory and
  query.
- `engine/` — Phase 1 deterministic Horn engine (plus the flag-gated defeasible
  layer), Phase 2 guided cycle, Phase 3 explanation, and the pipeline nodes.
- `graph/` — the LangGraph adapter over the engine nodes.
- `evals/` — offline/live evaluation harness (not part of the package).

## 2. Data model (`core/`)

All models are Pydantic (`core/models.py`).

- `Object` — a canonical vertex (`id`).
- `Morphism` — an arrow: `predicate`, `subject`, `object`, `modality`
  (`permit|obligation|forbidden|neutral`), `quote`, `negated`. Negation is the
  same predicate with `negated=true`; modality is a field, never a predicate
  prefix. A single-argument atom canonicalizes to the `subject` slot, so theory and
  question agree on unary relations.
- `Rule` — a Horn clause: `conditions` (AND) → `consequence`, `kind`
  (`implication|exception`), `strength` (always `defeasible`: every rule is a
  default, only asserted facts/axioms are strict), `source` (`quote` or
  `hypothesis:<id>`), `quote`.
- `Theory` — `objects`, `morphisms` (asserted axioms), `rules`, `source_text`,
  `domain` (universe sorts; rule premises restricted to a domain sort are vacuous
  and dropped by the builder).
- `Query` — `conditions` (Gamma), `target` (phi, may contain `?x`), `variables`,
  `answer_type` (`yes_no|open|instruction`).
- `Fact` (engine-internal) — a ground atom plus provenance: `used` (transitive
  keys), `premises` (direct keys), `witness`, `axiom`, `rule_index`, `modality`.
  `FactKey = (predicate, subject, object, negated, modality)` — modality is part of
  atom identity.
- `Hypothesis` — `id`, `kind` (`rule|fact`), `payload`, `wave`, `rationale`.
- `Verdict` — `status`, `bindings`, `gaps`, `matched`, `shelf`, `unused_premises`.
- `Proposal` / `WaveRecord` — the auditable per-wave record.
- `Answer` — `value`, `kind` (`yes|no|unknown|contradiction|binding|instruction`,
  the machine-readable direct answer), `strength` (`proven|proven_under|not_proven`),
  `hypotheses_used`, `defeasible`. `engine.answer.render_answer` localizes it.
- `Explanation` / `ExplanationStep` / `Conflict` — the mechanical trace, plus the
  two branches of a contradicted or undecided goal (`kind` `strict|defeasible`,
  `status` `resolved|undecided`, `defeated`).

Phase 0 structures (`core/schemas.py`) are what the LLM actually authors: `Slot`,
`StructAtom`, `StructRule`, `StructObject`, `ProblemStructure`, `QuestionStructure`.
A `StructAtom` carries a `predication` (`copula|verb`): a one-place copula ("Gary is
cold") is emitted with the complement in `predicate` and becomes `is_a(subject,
predicate)`, while a `verb` one-place atom ("X has an engine") stays a unary
predicate — this keeps properties out of the `is_a` type hierarchy. A
`ProblemStructure` declares a `domain` (the universe sort(s) every individual
belongs to); rule premises that restrict a variable to a domain sort are the
quantifier's domain, not premises, and are dropped deterministically. A
deterministic builder turns the structures into finished triples; the model never
writes combinatorial morphisms. `llm_json_schema(model)` is used for prompts.

## 3. Phase 0 — decomposition (`build/`)

Two LLM calls, in order (the order is required: the question must see the
canonical theory vocabulary).

1. `extract.extract_problem_structure(text) -> ProblemStructure` — one call that
   also records the verbatim interrogative part (`question`). The LLM only
   decomposes structurally (sets, variants, exclusions, rules, modalities, quotes).
   With `ANKYRA_EXTRACT_SAMPLES` > 1 it is called N times and the best structure is
   picked deterministically by `symbolic.quality_key` (fewer repairable gaps →
   more source coverage → more compact); `ANKYRA_EXTRACT_REPAIRS` adds bounded
   repair passes over repairable gaps. The assembled theory is then passed through
   `symbolic.enforce_grounded`, which drops any atom/rule whose quote is not a real
   source substring (the core "no LLM-owned facts" invariant). The question call
   (`extract_question_structure`) follows the same sample/repair policy.
2. `unroll.unroll_problem_structure` → `enrich.enrich_theory` (exposed as
   `pipeline.build_theory`):
   - `unroll` expands slots into morphisms (`atom_to_morphisms`), carries modality
     as a field (prefixes only under `ANKYRA_DEONTIC_PREFIXES`), and builds rules
     (`exception` flips the consequent's polarity);
   - `enrich` rewrites polarity, dedupes, materialises rule consequences, heals
     self-contradictory rules, drops malformed atoms (empty predicate);
   - `symbolic.symbolic_check` reports quote/structure/naming gaps.
3. `extract.extract_question_structure(question, theory) -> QuestionStructure` —
   one call with the theory's vocabulary in the prompt.
4. `unroll.unroll_query_structure` → `query.settle_query` (exposed as
   `pipeline.build_query`): facts become conditions, `ask` becomes the target,
   `answer_type` is derived (`ask=null → instruction`, a variable → `open`, else
   `yes_no`); `settle` drops the goal echo and slims unused premises by
   re-verifying.

Helpers: `normalize` (syntactic predicate normalisation, `is_var`), `symbolic`
(strict quote-in-source, naming), `extract.format_theory_for_llm`, and the
`builtins_block` prompt paragraph (gated by `ANKYRA_BUILTINS`).

## 4. Phase 1 — the deterministic engine (`engine/`)

`horn.py` is the spine. `TheoryContext` resolves the theory's object/predicate
pools and query bindings. `unify_pattern` matches a pattern against a ground fact
(polarity, negation and modality must agree); `instantiate` grounds a pattern.
`AtomStore` dedupes ground atoms by `FactKey` and keeps the shortest proof.

- `saturate(theory, assumptions)` — semi-naive forward chaining to a fixed point
  over the finite universe. Axioms and query assumptions are seeded, rules fire,
  and neutral positive `is_a` edges are transitively closed. Each derived fact
  records direct `premises` and transitive `used`.
- `match_goal`, `complementary` (`P` vs `¬P`), `assumption_explained`,
  `frontier`.
- `builtins.py` — an optional, range-restricted comparison layer (`eq/neq/lt/lte/
  gt/gte`). A builtin is *evaluated* as a filter over a bound value, never matched
  against facts; `builtin_unsafe` enforces that every variable is bound by an
  earlier relational atom.
- `verify.py` — `verify(theory, query)`:
  - a complementary pair inside the target's proof → `contradiction`;
  - target matched and all conditions used → `supported`;
  - target matched but a premise unused → `insufficient` (+ `unused_premises`);
  - target unmatched; if its negation is entailed → `refuted` with a
    `target_refuted:` gap (a "no" answer); otherwise `unsupported`.
  - an inconsistency unrelated to the target is an `inconsistent_theory:` gap and
    does not change the answer.
- `derive_closure` / `derive_store` — the single entry point that returns the
  strict Horn closure, or the defeasible effective closure when
  `ANKYRA_DEFEASIBLE` is on.
- `defeasible.py` — the non-monotonic layer: strict closure first, then defeasible
  rule applications resolved by specificity over `is_a`; NFA (strict overrides),
  undecided conflicts (Nixon diamond) accepted by neither branch. See
  `docs/defeasible_reasoning.md`.

Gap codes: `target_unmatched:`, `condition_unmatched:`, `unused_premise:`,
`contradiction:`, `target_refuted:`, `inconsistent_theory:`, `undecided_conflict:`.
`winning_store_hit` / `winning_proof` return the store and the proof keys of a
supported verdict for explanation and hypothesis accounting.

## 5. Phase 2 — the guided cycle (`engine/`)

The inner loop is deterministic; only the proposal is an LLM call. One action per
wave (invariant G1).

- `state.py` — `WaveContext` (what the proposer sees), `PendingWave`, and the
  `ReasoningState` TypedDict. `history` and `hypotheses` are append-only
  (`operator.add` reducers); `merge_state` gives the same semantics to the linear
  driver.
- `proposal.py` — `ProposalDraft` schema, `build_hint` (problem + theory + verdict
  + gaps + frontier), `propose` (one structured call), `signature`/`to_proposal`.
- `classify.py` — `classify(draft, theory, query, ledger, ...)`: schema/safety
  checks, then `derivable | cited | hypothesis | rejected` (range restriction,
  `unsafe_builtin`, `hypotheses_forbidden`, `target_weakened`). Application is
  monotonic: axioms and rules are appended, hypotheses go to the ledger with a
  `hypothesis:<id>` source.
- `ledger.py` — `HypothesisLedger`; `used(store, proof_keys)` returns only the
  hypotheses that actually occur in the proof.
- `answer.py` — `build_answer`: `supported` → "yes"/binding, hypotheses → strength
  `proven_under`, `target_refuted` → "no", otherwise `not_proven`.
- `nodes.py` — `GraphDeps` (injected stages) and the pipeline nodes plus pure
  routers. `engine/cycle.py` drives the same nodes linearly (`run_cycle`,
  `CycleResult`), so there is one implementation of every step.

Stop conditions: `supported`, `refuted`, `no_progress` (two consecutive waves with
no theory/query growth), `budget` (`ANKYRA_MAX_WAVES`), `unsupported` (hypotheses
forbidden), `proposal_error`, `extraction_error`.

## 6. Phase 3 — explanation (`engine/explain.py`)

`build_explanation` branches on the terminal status: `supported`/`target_refuted`
walk the positive or negative proof from the goal through each fact's direct
`premises` (post-order DFS); `contradiction` and an undecided defeasible conflict
populate `Explanation.conflict` with both branches. Step kinds:
`axiom | assumption | rule | is_a | hypothesis`; `render_rule` shows the applied
rule (and marks it defeasible). `narrate.narrate_explanation` optionally
paraphrases a finished trace in a configurable language (`ANKYRA_LANG`), starting
from the deterministic direct answer (`render_answer`); it may not add facts.

## 7. Orchestration (`graph/`, `engine/nodes.py`)

`graph/build.py` compiles a `StateGraph` over `ReasoningState`:

```
START → extract_problem → build_theory → extract_question → build_query
      → verify → (propose → classify → verify)* → explain → END
```

Routing is pure (`route_after_stage`, `route_after_verify`, `route_after_propose`);
every status is committed by a node. `run_problem(text, ...) -> ProblemResult` is
the end-to-end entry point; `engine/cycle.run_cycle` is the reasoning-only API.

## 8. Configuration (`config/settings.py`)

Dynaconf, env prefix `ANKYRA`, from `.env`. Provider: `API_URL`, `API_KEY`, `MODEL`,
`TEMPERATURE`, `MAX_TOKENS`, `MAX_TOKENS_EXTRACT`, `EXTRA_BODY`,
`REASONING_EFFORT`. Engine: `MAX_WAVES`, `ALLOW_HYPOTHESES`, `BUILTINS`,
`DEFEASIBLE`, `LANG`, `DEONTIC_PREFIXES`, `STRICT_VOCAB`, `EXTRACT_SAMPLES`,
`EXTRACT_REPAIRS`. Tests: `LIVE`.

## 9. LLM layer (`llm/`)

- `client.py` — `create_chat_llm(role=...)`, token/temperature helpers.
- `structured.py` — `invoke_as_dict`: function-calling first; on failure it falls
  back to a plain JSON call with the **schema injected into the prompt**, then to a
  lenient JSON parse. Length-limit errors trigger a bounded token-cap retry.
- `trace.py` — an opt-in, in-memory trace of calls (prompt, raw, parsed, error,
  duration) used by the eval harness.

## 10. Evaluation (`evals/`)

- `problems.jsonl` — increasing-difficulty, domain-general problems with ideal
  expectations and optional flags (`builtins`, `allow_hypotheses`).
- `run.py` — runs each problem, writes `evals/out/<id>.json` (raw LLM calls plus
  `structure`/`symbolic`/`theory`/`query`/`verdict`/`waves`/`answer`/`explanation`),
  prints metrics.
- `evaluators.py` — `Evaluator` protocol, `InvariantEvaluator` (hard),
  `ExpectationEvaluator` (soft; compares `status`, `kind`, `strength`, `value`).
- `narrate.py` — reads saved traces and prints readable reasoning.
- `tests/test_evals_live.py` asserts invariants only; expectations are metrics.

## 11. Invariants and open items

Invariants: no LLM-owned facts; monotonic theory; freedom in proposal, determinism
in classification; theory and question are separate artifacts; every explanation
step maps to a real edge or a hypothesis; answer strength is explicit.

Open items (`docs/quality_findings.md`): explanation fidelity for refuted goals
and rule provenance in traces; question-presupposition capture; LLM variance;
non-monotonic exceptions (`docs/defeasible_reasoning.md` — design note ready).

Future direction: making the inference semantics pluggable is described in
`docs/logic_layer.md` (extract a narrow `Inference` protocol only when the second
semantics lands).
