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

Every live adapter (`evals.run`, `evals.proofwriter`, `evals.prontoqa`,
`evals.prontoqa_ood`, `evals.folio`) takes `--jobs N` to run up to N problems
concurrently on threads; per-problem flags stay in a `ContextVar`, so the pool is safe
for heterogeneous problems.

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
| L2 | disjunction, case split, finite-domain quantifiers | synthetic (LLM-free) | 23/23 |
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
uv run python -m evals.defeasible_synthetic  # defeasible synthetic gate (offline)
uv run python -m evals.build_prontoqa_ood_sample --tier a  # ProntoQA-OOD L2 sample
uv run python -m evals.analyze_folio         # FOLIO fragment-vs-extraction diagnostic
```

**L2** (disjunction, case split, finite-domain quantifiers) is implemented behind
`ANKYRA_LOGIC` (default `off`). It is gated LLM-free by the synthetic collection
**23/23** (0 grounded false proofs), and its first live gate — **ProntoQA-OOD tier a —
is green: 41/42 (97.6%), 0 grounded false proofs** (`evals.prontoqa_ood`). FOLIO's L2
live gate (45 problems) is **extraction-bound: 26/44**, with no engine unsoundness —
the misses are no-target/`out_of_fragment` or a universal/conditional conclusion
collapsed to a ground atom. The earlier FOLIO L1 negation slice scored 7/13, and the
gold-FOL diagnostic (`evals.analyze_folio`) showed text-fed equals gold-fed, i.e. the
gap is logic/extraction, not the engine core.

## Documentation

- `ARCHITECTURE.md` — layers, flows, data model, module map.
- `docs/task.md` — technical specification.
- `docs/reasoning_roadmap.md` — staged formalisms and gates (the main axis).
- `docs/l2_plan.md` — L2 implementation plan (L2 is implemented).
- `docs/implementation_plan.md` — roadmap and backlog.
- `docs/quality_findings.md` — eval findings and open quality gaps.
- `docs/defeasible_reasoning.md` — design note on exceptions/defaults.

## Status

Core engine, guided cycle, hypotheses, explanation and builtins are implemented and
covered by tests. **L0 is gated**: definite Horn on ProofWriter, Tier D re-run
**297/300 (99%)** with 0 grounded false proofs and every determinate answer `proven`.
**L1 is implemented and gated**: stratified negation-as-failure, disjointness
constraints and the per-query declared closed world (`ANKYRA_NEGATION_MODE`), with
ProntoQA 208/208 (tiers a+b, all `proven`, 0 grounded false proofs; the collection
is considered closed) and LLM-free synthetic gates 40/40 (L1) and 8/8 (defeasible).
**L2 is implemented and gated** behind `ANKYRA_LOGIC`: disjunction and case splits,
conjunctive/disjunctive and open goals, and finite-domain quantifiers (Skolemization
plus witness enumeration). The LLM-free synthetic gate is **23/23** with 0 grounded
false proofs; the ProntoQA-OOD and FOLIO L2 harnesses are built with live gates
pending a separate budget decision. The defeasible layer (D) is implemented behind
`ANKYRA_DEFEASIBLE`.

Known open items: FOLIO L2 extraction (universal/conditional conclusions collapsing to
ground atoms) and its `out_of_fragment` constructs; the gold-fed L2 diagnostic parser
(`∨`/`∃`); full first-order unification (deferred — grounding is sound and terminating
on the committed finite domains); extraction robustness on real text (`docs/folio.md`
§9); and the items in `docs/quality_findings.md`.
