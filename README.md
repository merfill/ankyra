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

Tests: `uv run pytest` (offline), `ANKYRA_LIVE=1 uv run pytest -m live` (real LLM).

## Documentation

- `ARCHITECTURE.md` — layers, flows, data model, module map.
- `docs/task.md` — technical specification.
- `docs/implementation_plan.md` — roadmap and backlog.
- `docs/quality_findings.md` — eval findings and open quality gaps.
- `docs/defeasible_reasoning.md` — design note on exceptions/defaults.

## Status

Core engine, guided cycle, hypotheses, explanation and builtins are implemented
and covered by tests. Known open items (see `docs/quality_findings.md`): explanation
fidelity for refuted goals, rule provenance in traces, question-presupposition
capture, LLM variance, and non-monotonic exceptions (design note ready).
