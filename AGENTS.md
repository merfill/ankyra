# AGENTS.md — Ankyra

Ankyra is a domain-general hybrid neuro-symbolic reasoning engine: given a
self-contained natural-language problem (conditions plus a question), it produces
a step-by-step, mechanically verifiable reasoning trace and an answer with its
logical status. Design commitment: **the LLM proposes, the symbolic engine
decides.** Nothing enters the theory without a valid quote (`cited`) or an
explicit hypothesis tag (`hypothesis`).

Phase 0 formalization (deterministic builder; see `docs/task.md` §0.3): a
predicative "is/are" (`predication: copula`) becomes `is_a(subject, complement)`,
while other one-place predications (`verb`, e.g. "has an engine") stay unary — this
keeps properties out of the `is_a` type hierarchy. A `ProblemStructure.domain`
names the universe sort(s) every individual belongs to; a rule premise that only
restricts a variable to a domain sort is the quantifier's domain, not a premise,
and is dropped.

## Design boundary: no NL parsers

Deterministic code must never interpret natural language. Normalizing identifiers
and closed enum fields the LLM has **already extracted** (`predicate`/`object` ids,
`modality`, `relation_kind`, `predication`, slot keys) is allowed — it acts on
structured output, not on the source. Heuristics over the raw `source_text`/`question`
that key on words, morphology, cue phrases ("given that …"), or a hand-written term
list are forbidden: they do not generalize across domains, and the semantics live in
the extraction prompt. The only raw-text operations allowed are structural witness
checks — verbatim quote substring/span, coverage, and length. Under this rule
`build/normalize.py`, `core/models.py:normalize_modality`, and the `core/schemas.py`
field coercion are acceptable; a cue-phrase detector would not be.

## Commands

- Package manager — **uv**, not `pip`. Requires Python ≥ 3.11.
- Sync dependencies: `uv sync`.
- Tests (offline; live ones are skipped): `uv run pytest`.
- Live tests (real LLM calls): `ANKYRA_LIVE=1 uv run pytest -m live`.
- Eval harness: `uv run python -m evals.run [--ids rain,vehicle]`, then read the
  reasoning with `uv run python -m evals.narrate --lang ru`.
- There are **no** linters / formatters / type checkers or CI in the repository —
  do not look for a command for them or invent one.

## Configuration

Dynaconf with env prefix `ANKYRA`, loaded from `.env` (see `.env.example`).
Notable flags: `ANKYRA_ALLOW_HYPOTHESES` (default `true`), `ANKYRA_BUILTINS`
(default `false`), `ANKYRA_MAX_WAVES` (default 8), `ANKYRA_LANG` (narration
language, default `en`).

## Documentation

- `README.md` — what it is, install, quick start.
- `ARCHITECTURE.md` — layers, flows, data model, module map.
- `docs/task.md` — technical specification.
- `docs/reasoning_roadmap.md` — **main development axis**: staged decidable
  formalisms (L0 Horn → L1 negation → L2 FOL → L3 CSP → L4 numeric; plus
  defeasible) and the benchmark gating each stage.
- `docs/implementation_plan.md` — roadmap and backlog.
- `docs/quality_findings.md` — eval-harness findings.
- `docs/proofwriter.md` — ProofWriter collection notes (eval harness).
- `docs/prontoqa.md` — ProntoQA collection notes (planned L1 gate).
- `docs/folio.md` — FOLIO collection notes (planned L2 gate, FOL with quantifiers).
- `docs/folio_gold_fed.md` — FOLIO gold-fed diagnostic: method vs extraction
  (Phase 0 result; the L2 coverage ceiling).
- `docs/coverage_ceiling.md` — what the coverage ceiling is, in plain terms, and
  the ordered Tier-1 plan to raise it.
- `docs/ar_lsat.md` — AR-LSAT collection notes (planned L3 gate, separate engine).
- `docs/gsm8k.md` — GSM8K collection notes (planned L4 stage, separate engine).
- `docs/defeasible_reasoning.md` — non-monotonic exceptions design note.
- `docs/logic_layer.md` — pluggable inference semantics (future) note.
- `docs/statement_sources.md` — origin vs logical role for assertions design note.
- English is canonical; Russian mirrors are `<name>_ru.md`.
- Glossary (Russian): `provenance` → «история вывода» (graph/edge → «граф/ребро
  вывода»); `justification` → «обоснование». Keep code identifiers in English.
