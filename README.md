# Ankyra

A domain-general hybrid neuro-symbolic reasoning engine. Given a self-contained
natural-language problem (conditions plus a question), Ankyra produces a
step-by-step, mechanically verifiable reasoning trace and an answer with its
logical status.

**Design commitment: the LLM proposes, the symbolic engine decides.** The model
never owns truth. It may name predicates and propose rules freely, but every
proposal is deterministically classified as one of:

| category | condition | engine action |
|---|---|---|
| `derivable` | already entailed by the theory | accept as narration only |
| `cited` | a new fact grounded by a verbatim quote | add to the axioms |
| `hypothesis` | knowledge not present in the text | record in the ledger, tag `H` |
| `rejected` | fails schema, safety or quote checks | drop with a reason code |

An answer is reported with its strength: `proven`, `proven_under(H)` (depends on
tagged hypotheses), or `not_proven`.

## How it works

1. **Phase 0 — decompose.** Two LLM calls. First, split the text and extract a
   structural decomposition of the descriptive part (`ProblemStructure`); a
   deterministic builder unrolls and enriches it into a `Theory`. Then express the
   question over the theory's canonical vocabulary (`QuestionStructure`) and settle
   it into a `Query`.
2. **Phase 1 — decide.** A deterministic Horn engine (`saturate`, `unify`,
   `match_goal`, `complementary`, transitive `is_a`, `verify`) derives the target
   to a fixed point. Every derived fact carries provenance.
3. **Phase 2 — guided cycle.** While the answer is unresolved, the LLM proposes
   one action per wave; the engine classifies it deterministically and applies or
   drops it. The theory only grows; hypotheses are tracked in a ledger.
4. **Phase 3 — explain.** The trace is built mechanically from the provenance
   (no LLM). The model may only paraphrase the finished derivation.

Orchestration is a LangGraph `StateGraph`; the same steps are also available as a
plain library API. See `ARCHITECTURE.md`.

## Install

Requires Python ≥ 3.11 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env   # then set ANKYRA_API_KEY (and URL/model if different)
```

Configuration is Dynaconf with the `ANKYRA_` prefix (see `.env.example`).

### LLM providers

The LLM is reached through a provider-agnostic factory (`ankyra.llm.providers`)
behind the common LangChain `BaseChatModel` interface, so nothing above it depends
on a concrete provider. `ANKYRA_LLM_PROVIDER` (default `openai`) selects the
binding; `openai` covers **any OpenAI-compatible endpoint** (OpenAI, RouterAI,
DeepSeek, OpenRouter, vLLM, Ollama's OpenAI API, …) configured by `ANKYRA_API_URL`,
`ANKYRA_API_KEY` and `ANKYRA_MODEL`.

To add a different SDK, register a builder in `PROVIDERS`
(`src/ankyra/llm/providers.py`) — the engine and the extractors are untouched. An
unknown provider is a clear configuration error, never a silent fallback.

## Quick start

```python
from ankyra.graph.build import run_problem

result = run_problem("It is raining. If it is raining, the ground is wet. Is the ground wet?")
print(result.status)                 # supported
print(result.answer.strength)        # proven
print(result.answer.value)           # yes

for step in result.explanation.steps:
    print(step.index, step.kind, step.statement, step.rule or "")
```

A reasoning-only entry point (no Phase 0) is available as
`ankyra.engine.cycle.run_cycle`.

### Readable reasoning

The explanation is generated deterministically; an LLM may paraphrase it:

```python
from ankyra.engine.narrate import narrate_explanation
from ankyra.llm.client import create_chat_llm

print(narrate_explanation(create_chat_llm(role="answer"), result.explanation, language="ru"))
```

Narration language is configurable (`ANKYRA_LANG`, default `en`).

## Worked examples

- **Pure deduction (rain).** Theory `{raining()}` plus the rule
  `raining() => is_wet(ground)`; the answer is `proven` with a two-step trace.
- **Abduction (vehicle).** The text lists a vehicle's features but no class rules.
  The engine derives nothing, then the LLM proposes class rules; they carry no
  quote, so they become tagged hypotheses and the answer is
  `proven_under(H1, …)`. With `ANKYRA_ALLOW_HYPOTHESES=false` it refuses honestly.

## Numeric thresholds (optional)

With `ANKYRA_BUILTINS=true`, a closed set of range-restricted comparisons
(`eq`, `neq`, `lt`, `lte`, `gt`, `gte`) is available. A builtin is evaluated as a
filter over a bound value, never matched against facts, e.g.
`has_power(?x, ?p) AND gte(?p, 50)`. Every variable in a builtin must be bound by
an earlier relational atom.

## Evaluation

The `evals/` harness runs a set of increasing-difficulty problems and writes a
full trace (raw LLM calls plus every intermediate artifact) per problem:

```bash
uv run python -m evals.run                 # all problems -> evals/out/<id>.json
uv run python -m evals.run --ids rain,vehicle
uv run python -m evals.narrate --lang ru   # read the reasoning
```

Every live adapter (`evals.run`, `evals.proofwriter`, `evals.prontoqa`,
`evals.prontoqa_ood`, `evals.folio`, `evals.ar_lsat`) takes `--jobs N` to run up to N
problems concurrently on threads; per-problem flags stay in a `ContextVar`, so the pool
is safe for heterogeneous problems.

Tests: `uv run pytest` (offline), `ANKYRA_LIVE=1 uv run pytest -m live` (real LLM).

### Staged-formalism gates

Coverage is measured in **named formalisms** (`docs/reasoning_roadmap.md`), not in
untethered "reasoning". Committed gates:

| Stage | Formalism | Benchmark | Result |
|---|---|---|---|
| L0 | definite Horn | ProofWriter Tier D | **297/300 (99%)**, 0 grounded false proofs (accepted proof of concept) |
| L0 | definite Horn | ProofWriter Tier A (strict) | 45/45 |
| L1 | explicit negation | ProntoQA tier a | 48/48 (100%), all `proven` |
| L1 | explicit negation | ProntoQA tier b | **160/160 (100%)**, all `proven` |
| L1 | disjointness, NAF, declared CWA | synthetic (LLM-free) | 40/40 |
| L2 | disjunction, case split, finite-domain quantifiers, finite equality | synthetic (LLM-free) | 65/65 |
| L2 | disjunction, quantifiers, equality | ProntoQA-OOD tier a | 41/42 (97.6%), 0 grounded false proofs |
| L3 | finite-domain CSP (boolean composition, count_compare, factor projection) | synthetic (LLM-free) | 31/31 |
| L3 | finite-domain CSP | AR-LSAT gold-fed, 7 real games (LLM-free) | 27/27 |
| L3 | finite-domain CSP | AR-LSAT eval tier (live) | **23/30**, **0 `grounded_mismatch`** |
| L4 | exact arithmetic + `max`/`min` | synthetic (LLM-free) | 37/37 |
| L4 | exact arithmetic | GSM8K gold-fed, 8 real problems (LLM-free) | 8/8 |
| L4 | exact arithmetic | GSM8K dev/eval (live) | dev **12/12**, eval **38/40**, **0 `grounded_mismatch`** |
| D | defeasible | synthetic (LLM-free) | 8/8 |

The ProntoQA runs have **0 grounded false proofs** and every determinate answer is
`proven`; the one-sided 95% Clopper–Pearson lower bound on per-problem accuracy is
98.1% for tier b (n=160). The synthetic runners build engine models directly (no
extraction, no LLM), so they gate the semantics with zero provider variance.

The ProofWriter Tier D re-run (`--jobs 5`) has **0 grounded false proofs**, every
determinate answer `proven` (197/199), and `depth-3ext` **150/150**; the two
remaining misses are NatLang extraction errors answered as honest `unknown`, and the
one no-target item was provider variance (a single `--ids` re-run answered it
`proven`). ProntoQA is used as the L1 gate and is considered closed — no further
runs unless a later stage specifically needs it.

```bash
uv run --with pyarrow python -m evals.build_prontoqa_sample --tier b
uv run python -m evals.prontoqa --tier b     # live LLM run
uv run python -m evals.l1_synthetic          # L1 synthetic gate (offline)
uv run python -m evals.l2_synthetic          # L2 synthetic gate (offline)
uv run python -m evals.l3_synthetic          # L3 CSP synthetic gate (offline)
uv run python -m evals.l3_spike              # L3 feasibility spike (offline)
uv run python -m evals.ar_lsat --gold evals/data/ar_lsat_gold.jsonl  # L3 gold-fed (offline)
uv run python -m evals.ar_lsat --sample eval --live                  # L3 AR-LSAT live gate
uv run python -m evals.l4_synthetic          # L4 numeric synthetic gate (offline)
uv run python -m evals.l4_spike              # L4 feasibility spike (offline)
uv run python -m evals.gsm8k --gold evals/data/gsm8k_gold.jsonl      # L4 gold-fed (offline)
uv run python -m evals.gsm8k --sample eval --live                    # L4 GSM8K live gate
uv run python -m evals.defeasible_synthetic  # defeasible synthetic gate (offline)
uv run python -m evals.routing_synthetic     # declared-fragment routing gate (offline)
uv run python -m evals.build_prontoqa_ood_sample --tier a  # ProntoQA-OOD L2 sample
uv run python -m evals.analyze_folio         # FOLIO fragment-vs-extraction diagnostic
```

**L2** (disjunction, case split, finite-domain quantifiers, finite equality) is
implemented behind `ANKYRA_LOGIC` (default `off`). It is gated LLM-free by the synthetic
collection **65/65** (0 grounded false proofs), and its first live gate —
**ProntoQA-OOD tier a — is green: 41/42 (97.6%), 0 grounded false proofs**
(`evals.prontoqa_ood`). On FOLIO L2 tier a the method covers **44/45** (gold-fed 42/45,
0 grounded false proofs); text-fed is **extraction-bound (29–31/45)**, backlog G1–G4
complete, residual wall G2 (missing premises). The FOLIO **negation slice** is
L1-fragment by construction but **fragment-bound**: on the Horn path gold-fed == text-fed
== 7/13, and its residual is reductio/contrapositive, so it is now scored by the clausal
L2 procedure (`evals.folio.default_logic`) — gold-fed **12/13**, live **11/13**, **0
grounded false proofs**, with the residual now extraction (the G2 wall) and no closed
world applied (a global CWA would wrongly refute the four `Uncertain` rows). The gold-FOL
diagnostic (`evals.analyze_folio`) separates method from extraction, i.e. the FOLIO gap
is coverage/extraction, not the engine core.

**L4** (exact rational arithmetic, with exact `max`/`min`) is implemented behind
`ANKYRA_ARITH` as a separate numeric engine: a defined-quantity DAG plus finite linear
systems over `fractions.Fraction`, decided exactly (`determined` / `underdetermined` /
`inconsistent` / `out_of_fragment`). It is gated LLM-free by the synthetic collection
**37/37** and hand-encoded gold **8/8** (0 `grounded_mismatch`), and the **live gate is
green: dev 12/12, eval 38/40, 0 `grounded_mismatch`** — the only two non-correct rows are
annotated reference errors (one dataset error, one ambiguity,
`evals/data/gsm8k_notes.jsonl`). The L4 soundness invariant is **0 arithmetic errors**
(a property of the exact procedure); a wrong number is a modelling error, never an
arithmetic one. The extraction ceiling was raised by a general bounded repair pass
(`ANKYRA_ARITH_REPAIRS`) and per-collection reading rules in `evals/skills/gsm8k/`, never
by sampling.

## Documentation

- `ARCHITECTURE.md` — layers, flows, data model, module map.
- `AGENTS.md` — contributor/agent workflow and the no-NL-parsers design boundary.
- `docs/concepts.md` — conceptual overview: the engines and the reasoning cycle
  (Russian mirror `docs/concepts_ru.md`).

**Theory**

- `docs/doxa_and_logos.tex` — *Doxa and Logos*: the non-formalizable source and the
  formal functions through which it interacts with the engine (Russian mirror
  `docs/doxa_and_logos_ru.tex`).

**Spec and roadmap**

- `docs/task.md` — technical specification.
- `docs/reasoning_roadmap.md` — staged formalisms and gates (the main axis).
- `docs/implementation_plan.md` — roadmap, backlog, milestones.
- `docs/fragment_routing.md` — declared-fragment contract (which procedure runs).
- `docs/logic_layer.md` — pluggable inference semantics.
- `docs/statement_sources.md` — origin vs logical role for assertions.

**Stage plans**

- `docs/l1_plan.md` — L1: stratified negation/NAF and declared CWA.
- `docs/l2_plan.md` — L2: positive FOL (implemented).
- `docs/l3_plan.md` — L3: finite-domain CSP (implemented).
- `docs/l3_extension_plan.md` — L3 post-gate hardening (composite factors, value-target
  `complete_list`, `count` membership, AR-LSAT gold invariant).
- `docs/equality_plan.md` — Tier-2 3a finite equality.
- `docs/l4_plan.md` — L4: exact arithmetic (implemented).
- `docs/defeasible_reasoning.md` — exceptions/defaults (the D layer).

**Collections, gates and findings**

- `docs/proofwriter.md` — ProofWriter (the L0 gate).
- `docs/prontoqa.md` — ProntoQA (the L1 gate).
- `docs/folio.md`, `docs/folio_gold_fed.md`, `docs/folio_ceilings.md`,
  `docs/folio_extension_plan.md`, `docs/g1_g4_plan.md` — FOLIO (the L2 gate) and the
  coverage-ceiling work.
- `docs/coverage_ceiling.md` — the method ceiling and the Tier-1 backlog
  (`docs/t1_plan.md`, `docs/t3_plan.md`, `docs/t4_t2_plan.md`, `docs/t5_plan.md`,
  `docs/t6_plan.md`).
- `docs/ar_lsat.md` — AR-LSAT (the L3 gate).
- `docs/gsm8k.md` — GSM8K (the L4 gate).
- `docs/quality_findings.md` — eval findings and open quality gaps.

## Status

Core engine, guided cycle, hypotheses, explanation and builtins are implemented and
covered by tests. **L0 is gated**: definite Horn on ProofWriter, Tier D re-run
**297/300 (99%)** with 0 grounded false proofs and every determinate answer `proven`.
**L1 is implemented and gated**: stratified negation-as-failure, disjointness
constraints and the per-query declared closed world (`ANKYRA_NEGATION_MODE`), with
ProntoQA 208/208 (tiers a+b, all `proven`, 0 grounded false proofs; the collection
is considered closed) and LLM-free synthetic gates 40/40 (L1) and 8/8 (defeasible).
**L2 is implemented and gated** behind `ANKYRA_LOGIC`: disjunction and case splits,
conjunctive/disjunctive and open goals, finite-domain quantifiers (Skolemization plus
witness enumeration) and finite equality (`=`/`≠`, fragment `equality`). The LLM-free
synthetic gate is **65/65** with 0 grounded false proofs, and the **ProntoQA-OOD tier-a
live gate is green: 41/42 (97.6%), 0 grounded false proofs**. On FOLIO L2 tier a the
method covers **44/45** (gold-fed 42/45, 0 grounded false proofs); text-fed is
extraction-bound (29–31/45, backlog G1–G4 complete, residual wall G2 missing premises).
The FOLIO **negation slice** is L1-fragment by construction but fragment-bound, so it is
scored by the clausal L2 procedure: gold-fed **12/13**, live **11/13**, 0 grounded false
proofs (the residual is extraction, G2). The defeasible layer (D) is implemented behind
`ANKYRA_DEFEASIBLE`. The
declared-fragment contract (`docs/fragment_routing.md`) derives the required fragment
from the built structure and refuses an unsupported one with a named
`out_of_fragment`, instead of guessing; its LLM-free gate is **19/19**.
**L3 is implemented and gated** as a separate engine behind `ANKYRA_CSP`: a general
finite-domain CSP IR (boolean composition `all`/`any`/`not`, `count` over a value set,
`count_compare`, factor projection, declared topologies) and a bounded in-repo solver,
orchestrated by the LLM. LLM-free gates:
synthetic **31/31**, gold-fed real games **27/27** (7 games), both 0 `grounded_mismatch`. The
**AR-LSAT live eval gate is green: 23/30, 0 `grounded_mismatch`** (the 7 misses are
honest abstentions). The extraction ceiling there was raised not by sampling (rejected,
`docs/l3_plan.md` D-L3-10) but by an **error-driven, per-collection language
specification** (`ANKYRA_LANGUAGE_SPEC`, `docs/task.md` §0.6). The guide is packaged as
a per-collection **skill** (`evals/skills/<collection>/`, loaded by the harness via
`evals/skills.py`); the format and auto-loading are done, and the task-specific content
is the **budgeted step** — the `count`-rule attempt was dev-validated as a regression and
reverted, so any further content needs a new dev-validated case
(`docs/implementation_plan.md` §8 item 28, `docs/l3_extension_plan.md` H5).
**L4 is implemented and gated** as a separate numeric engine behind `ANKYRA_ARITH`:
exact rational arithmetic (defined-quantity DAG, linear systems, exact `max`/`min`),
Phase-0 extraction with a bounded repair pass, `Answer.kind "number"` and the `numeric`
explanation. LLM-free gates: synthetic **37/37** and hand-encoded gold **8/8** (both 0
`grounded_mismatch`); the **live gate is green: dev 12/12, eval 38/40, 0
`grounded_mismatch`** (the only two non-correct rows are annotated reference errors — one
dataset error, one ambiguity). The L4 soundness invariant is 0 arithmetic errors; a wrong
number is a modelling error.

Known open items: FOLIO L2 extraction (residual **G2** — missing premises; the deferred
`A′` repair); the FOLIO **negation slice is fragment-bound** and now scored at L2 (its
open step is the language guide on the extraction-bound L2 tier a, `docs/implementation_plan.md`
§8 item 29); the AR-LSAT **skill task-specific content** (item 28); Tier-2 **3b** bounded
function terms (deferred — no function terms in the available FOLIO splits); the
reachable-but-absent **2a** `↔`/`⊕` lowering and **2c** multi-variable quantification;
full first-order unification (deferred — grounding is sound and terminating on the
committed finite domains); extraction robustness on real text (`docs/folio.md` §9); and
the items in `docs/quality_findings.md`.
