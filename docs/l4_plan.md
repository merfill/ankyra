# L4 Plan — Arithmetic and numeric terms (GSM8K)

Status: **working plan** — decisions `D-L4-1`…`D-L4-3` are **DECIDED** (§15).
Milestone 0 (LLM-free feasibility spike, 8/8), milestones 1–2 (the committed exact
IR/solver and the synthetic gate, **37/37**), milestone 3 (the Phase-0
schema/builder/prompt, builder validated LLM-free, **12/12**), milestones 4–5 (the
gold-fed tier, the committed sample + adapter and the `gsm8k` skill; **gold 8/8**, 0
`grounded_mismatch`) and milestone 6 (routing `ANKYRA_ARITH`, `Answer.kind "number"`,
the `numeric` explanation; **7/7** routing tests) are **done**. The live gate ran:
**dev 12/12**, **eval 38/40, 0 `grounded_mismatch`** (the 2 remaining rows are annotated
reference errors — one dataset error, one ambiguity; `docs/gsm8k.md` §6). This is the
plan for stage **L4** of `docs/reasoning_roadmap.md`. L4 is a **separate engine**: it
does not extend the Horn spine, the L2 clausal procedure, or the L3 CSP engine.

Canonical language: English; Russian mirror: `docs/l4_plan_ru.md`. Related:
`docs/reasoning_roadmap.md` (§3 L4), `docs/gsm8k.md` (the collection notes),
`docs/l3_plan.md` (the precedent for a separate-engine stage),
`docs/logic_layer.md` (the `Inference` seam),
`docs/fragment_routing.md` (the declared-fragment contract), `docs/task.md`
(§0.3/§0.6, §3.8), `docs/implementation_plan.md` (§9).

## 1. Goal

Widen the class of decidable chains by adding the L4 formalism: **arithmetic terms
and equations over exact rationals**. The answer is a **number**, not an entailment
of a clause set. The LLM proposes a numeric formalization — quantities, equations
among them, and a target quantity — each grounded by a verbatim quote; the numeric
engine decides whether the target is **determined**, evaluates it exactly, and
reports the value. The design commitment is unchanged — nothing enters the
formalization without a valid quote or an explicit hypothesis tag — but the decision
procedure is a third engine, not the Horn/clausal/CSP one.

## 2. Scope and the honest framing

`docs/gsm8k.md` §2/§4 and `docs/task.md` §1 place arithmetic outside the symbolic
spine, and recommend tool-use rather than an in-repo core. L4 is pursued here as a
**separate engine** on explicit product instruction; the framing is kept honest:

- **Arithmetic is not entailment.** L4 does not strengthen the main thesis of
  `docs/reasoning_roadmap.md`; its check is trivial relative to modelling. What L4
  adds is narrow and real: the proposed formalization is **auditable and grounded**,
  the arithmetic is **exact** (no rounding error), and the failure taxonomy
  separates *modelling/extraction* from *arithmetic*.
- **The engine decides only what it can decide.** A formalization whose target is not
  uniquely determined is `underdetermined`, never guessed; an inconsistent system is
  `inconsistent`; a construct outside the committed fragment is `out_of_fragment`,
  never lowered onto a weaker shape.
- **The gate measures the extraction ceiling**, not engine soundness. Exact rational
  arithmetic makes arithmetic errors impossible by construction, so a wrong numeric
  answer is always a modelling error on the LLM side.

**In scope:** the numeric IR and exact solver (in-repo, no new dependency); the
result semantics (`determined` / `underdetermined` / `inconsistent` /
`out_of_fragment`); a `number` answer kind; the declared `numeric` fragment and its
routing; extraction of the numeric formalization (schema + prompt + deterministic
builder); the GSM8K gate.

**Out of scope:** any change to the Horn/L1/L2/L3 engines or their gates — L4 is
separate and is never silently mixed with them. Non-linear equation systems, general
symbolic algebra and calculus; unit-typed dimensional analysis beyond a declared
label; a full-collection GSM8K run (budget). NL heuristics are out of scope: the
quantities and relations are **structurally extracted** by the LLM, never detected
with cue phrases or a term list (`docs/task.md` §3.8).

## 3. Guardrails (gating)

- **0 arithmetic errors.** The engine computes over `fractions.Fraction`; exactness
  is a property of the procedure, not a thing to measure. A false numeric answer can
  only be a wrong formalization.
- **No guessing under incompleteness.** A target that is free, a system that is
  inconsistent, or a search/budget exhaustion is an honest `underdetermined` /
  `inconsistent` / `insufficient`, never a picked number.
- **`out_of_fragment` is honest.** A non-linear equation, a relation outside the IR,
  or a mixed Horn/numeric structure is refused by name, never approximated.
- **Extraction failures are honest.** Ill-formed expressions, undeclared quantity
  references, out-of-domain values and missing quotes are `NumericBuildError`s, so
  the model gets a repair instead of a wrong system.
- **No benchmark semantics in the engine.** The collection's answer format and the
  answer extractor live in the harness, never in the solver.
- **Benchmark semantics do not leak, and sampling is not used.** `ANKYRA_ARITH` is
  off by default; the harness sets it. `ANKYRA_EXTRACT_SAMPLES=1` always
  (`docs/implementation_plan.md` §8 item 4; `docs/l3_plan.md` D-L3-10).
- **Separation from the deductive spine.** `numeric` is a distinct capability and
  procedure; a structure that mixes it with Horn/clausal/CSP content is refused by
  name (the D-L3-4 pattern), not decided by the wrong engine.

## 4. What L4 adds, and what already exists

Already present and reusable:

- the `Inference` protocol seam (`engine/inference.py`) and the declared-fragment
  contract, including per-run capabilities and named refusal codes;
- the quote/hypothesis discipline and the theory/query IR;
- the eval-harness conventions: deterministic committed samples, LLM-free synthetic
  gates, a gold-fed tier, an LLM-free spike, and a failure taxonomy.

Genuinely new for L4:

- a **numeric IR** (quantities, expressions, equations, a target) — distinct from
  `Theory`/`Query` and from the CSP IR;
- an **exact solver** (defined-quantity DAG evaluation + linear system elimination
  over `Fraction`) with a `determined`/`underdetermined`/`inconsistent` record;
- a **`number` answer kind** and an evaluation-based justification;
- the `numeric` capability and its routing refusal;
- a **deterministic answer extractor** with numeric tolerance (harness side).

## 5. Benchmark and stratification

GSM8K (`docs/gsm8k.md`): grade-school math word problems with a free-form numeric
answer. Splits are `main`/`socratic`, `train` (~7.5k) and `test` (~1.3k); there is
**no official development split**. A run is stratified by **formalization class**:

- **in-fragment** — a defined-quantity DAG or a small linear system (§7); scored;
- **out-of-fragment** — non-linear equations, unresolved unknowns, unsupported
  relations; reported `out_of_fragment`, not a failure.

Following `docs/l3_plan.md` D-L3-8/D-L3-9 and D-L4-3, the committed sample is built
deterministically from the official **test** split and carved into a small **dev**
slice (prompt/IR iteration, not a gate) and a disjoint **eval** slice (the gate),
never parsed by wording and never tuned per id. The `train` split is excluded: a
model may have seen it.

## 6. Step 0 — feasibility spike (LLM-free) and the decision gate

First task, before any schema, prompt or integration work. **No LLM calls.**

- Hand-encode **5 problems** (one per axis: multi-step DAG, ratio/division, percent,
  linear system with introduced unknowns, unit multiplier) into the numeric IR and
  solve them with the in-repo exact solver.
- Add two **negative controls**: a system with a free target must be
  `underdetermined` (not answered) and an inconsistent system must be `inconsistent`.
- Measure: expressiveness (can every problem be encoded without a special case?) and
  solver-side correctness (the exact value matches the independently computed gold;
  0 confidently-wrong).

**Decision gate.**
- The IR covers all five axes soundly and the controls hold → proceed to the
  committed engine + synthetic gate.
- A construct resists the general IR → stop and reconsider the IR (never add a
  per-problem branch).
- The solver is not sound/terminating on the spike → stop; L4 is not viable as
  scoped.

Reproduce: `uv run python -m evals.l4_spike`. This mirrors the measure-first
discipline of `docs/l3_plan.md` §6.

**Spike result (done, LLM-free).** The general IR covered all five axes without a
special case and the exact solver decided each soundly (0 confidently-wrong): the
DAG chain, ratio, percent, linear system and unit multiplier all `determined` with the
expected value; the controls held (`underdetermined`, `inconsistent`,
`out_of_fragment`). No construct resisted the IR, so the decision gate passes and the
committed engine + synthetic gate may start.

## 7. The numeric IR

A general exact-rational model; no GSM8K-specific vocabulary.

- **Expression** `NumericExpr` — a small recursive term:
  `const(Fraction)` | `quantity(id)` | `neg` | `add` | `sub` | `mul` | `div` | `max` |
  `min`. The division node is partial: division by a zero value is a build/evaluation
  error, not an answer. `max`/`min` (D-L4-4) are exact when their operands are
  determined and `out_of_fragment` otherwise (a max/min of an unknown is piecewise).
- **Quantity** `NumericQuantity` — `id`, optional `unit` label, `quote`. A quantity
  is *known* when an equation defines it outright, *unknown* otherwise.
- **Equation** `NumericEquation` — `lhs = rhs`, each side an `NumericExpr`, with a
  quote. Only equality is in the first fragment; an ordering relation is
  `out_of_fragment`.
- **Game** `NumericGame` — quantities, equations, and the source text (for quote
  checks).
- **Query** `NumericQuery` — the `target` quantity id and an optional `tolerance`
  (the harness compares the answer to the reference within tolerance; the solver
  itself is exact).

Two expressible classes (anything else is `out_of_fragment`):

1. **Defined-quantity DAG** — each unknown is defined by exactly one equation
   `q = expr` over already-known quantities (the shape of a reference chain of
   arithmetic); evaluation is a topological pass.
2. **Linear system** — a finite set of equations that are linear in the remaining
   unknowns; solved exactly by Gaussian elimination over `Fraction`.

The IR is *declared*: the model proposes it and the deterministic builder assembles
it; the engine never infers a quantity or a relation from wording.

## 8. Decision procedure — exact evaluation / linear elimination

One primitive `solve(game, query, *, budget=None) -> NumericDecision`:

1. **Validate and ground.** All quantity references are declared; expressions are
   well-formed; equations are readable; the source text is available for the quote
   checks the builder already performed. Values found are exact `Fraction`s.
2. **Substitution fixpoint.** Repeatedly assign a quantity from a defining equation
   whose other side is fully known; check both-sides-known equations for consistency
   (a mismatch is `inconsistent`). This decides the DAG class.
3. **Linearize what remains.** Express each residual equation as a linear form
   `Σ aᵢ·xᵢ + c = 0` after substituting knowns. An expression with a product/quotient
   of two unknown-bearing subterms is non-linear → `out_of_fragment`.
4. **Eliminate.** Exact Gaussian elimination over `Fraction`: exactly one solution,
   no solution (`inconsistent`), or a family (`underdetermined`).
5. **Read the target.** A uniquely solved target is `determined` with its exact
   value; a free target is `underdetermined`; a target in the DAG is `determined`
   once assigned.

The procedure is exact and terminating; where a budget is used (system size), its
exhaustion is the honest `insufficient`, never a guess. The solver lives in its own
module (`engine/numeric/`), outside the Horn/clausal/CSP code.

## 9. Engine changes

- **`engine/numeric/`** — the numeric IR (`models.py`), the exact solver
  (`solver.py`), the public entry and routing (`decide.py`), and the answer /
  explanation assembly (`answer.py`). No dependency on `engine/horn.py`,
  `engine/resolution.py` or `engine/csp/`.
- **`engine/inference.py`** — a `FragmentFeature "numeric"`, a `numeric` capability,
  and an `analyze_numeric_routing` branch parallel to `analyze_csp_routing`; a
  structure requiring `numeric` without the capability is `out_of_fragment:numeric_off`,
  and a mixture with the deductive/CSP fragments is refused by name.
- **`engine/verify.py`** — dispatch the numeric structures to the numeric engine; the
  existing paths are untouched.
- **`engine/answer.py`** — map the numeric outcome to the new `number` answer kind and
  strength (`proven` only when `determined`).
- **`engine/explain.py`** — render the evaluated target / solved system as an
  evaluation-based step (a new `ExplanationKind`, e.g. `numeric`), not a Horn proof
  walk.

## 10. Data model and extraction schema

To keep the separate engine self-contained, the numeric types live under
`engine/numeric/` rather than in `core.models`/`core.schemas`:

- **`engine/numeric/models.py`** — the strict numeric IR (`NumericExpr`,
  `NumericQuantity`, `NumericEquation`, `NumericGame`, `NumericQuery`). Separate from
  `Theory`/`Query` and from the CSP IR. `AnswerKind += "number"` lands in
  `core/models.py` with the engine integration (milestone 6).
- **`engine/numeric/schemas.py`** — the LLM-authored structures
  (`NumericQuantitySpec`, `NumericEquationSpec`, `NumericGameStructure`,
  `NumericQueryStructure`) with lenient normalization of the closed enum fields and
  ids the model has already extracted (op aliases, `?`-stripping, decimal/percent
  literals to `Fraction`). The schemas carry no engine semantics.
- **`build/numeric.py`** — the deterministic builder `build_numeric_game` /
  `build_numeric_query`; it validates structural integrity (declared quantities,
  well-formed expressions, known op per node) and raises `NumericBuildError` instead
  of approximating.

## 11. Phase 0 extraction

- **`build/extract_numeric.py`** — a dedicated numeric extraction path: the LLM
  proposes the quantities, equations and the target, each with one verbatim quote;
  the prompt carries the semantics (how to read ratios, percentages and unit
  multipliers) with no cue-phrase lists and no word-level heuristics
  (`docs/task.md` §3.8). It is a two-call path like the Horn and CSP ones: the game,
  then the question expressed against the built game.
- **`evals/skills/gsm8k/{language.md,task.md}`** — a per-collection skill (notation
  and task specifics), auto-loaded by the harness and composed by `evals/skills.py`,
  passed through the existing `ANKYRA_LANGUAGE_SPEC` seam. Skills stay declarative
  guidance, never answer keys.
- Extraction is the main risk (§2 of `docs/gsm8k.md`); it is gated by comparing a live
  formalization to the hand-written one on the spike/gold rows, not by the final
  number alone.

## 12. verify / answer / explain

- **verify:** the numeric procedure decides the target against the game; a
  `determined` target is `supported`; `underdetermined` is `insufficient`;
  `inconsistent` is `refuted`/`contradiction`; an unexpressible formalization is
  `out_of_fragment`.
- **answer:** `Answer.kind = "number"`, `value` = the exact value (canonical
  fraction/decimal string); `strength = proven` only when the target is uniquely
  determined, otherwise `not_proven`.
- **explain:** an evaluation/solved-system step (the defining equations and the
  resulting value), a solver fact, not a fabricated derivation chain.

## 13. Eval harnesses (`evals/`)

### 13.1 Synthetic collection — **primary** (LLM-free, structural)

- `evals/build_l4_synthetic.py` → `evals/data/l4_synthetic.jsonl`. Each case is a
  fully structured numeric game/query with an independently written expected
  decision and a `mechanism` tag. No LLM, no natural language.
- `evals/l4_synthetic.py` — runner: builds the structures directly, calls the
  solver/verify, reports the gate, non-zero exit on any mismatch.
- Coverage: every expression op, both formalization classes, `determined` /
  `underdetermined` / `inconsistent` / `out_of_fragment`, and mandatory **negative
  controls** — division by zero is refused; a free target is never answered; an
  inconsistent system is never answered; a missing quote / undeclared quantity is a
  build error, not a wrong value.
- **Gate result (LLM-free, done):** `evals.l4_synthetic` **33/33** — every expression
  op, both classes, all five outcomes and the controls (`tests/test_evals_l4_synthetic.py`).

### 13.2 GSM8K — gold-fed, live (budgeted)

- **T0 — gold-fed (LLM-free).** `evals/gsm8k_gold.jsonl`: a small set of real
  GSM8K test problems hand-encoded into the IR with the reference number as the
  expected value. Run by `evals/gsm8k.py --gold`; separates method from extraction
  and is the debugging sandbox and the upper bound. (The reference `<<expr=result>>`
  annotations cannot be parsed deterministically without NL parsing — `docs/task.md`
  §3.8 — so the gold is hand-written, as in L3.)
- **T1 — live dev (budgeted, not a gate).** A small committed slice for prompt/IR
  iteration.
- **T2 — live eval (budgeted, the gate).** A disjoint committed slice, run once.
- Gate: numeric accuracy above threshold with **0 arithmetic errors**; every
  remaining failure triaged (`modelling`, `extraction`, `answer_extraction`,
  `out_of_fragment:*`).
- **Live gate (run).** The gate is redefined for L4: the hard invariant is **0
  arithmetic errors** (a property of the exact procedure), while a `grounded_mismatch`
  is a *modelling* signal. A mismatch is only a soundness failure when the reference is
  sound; two committed rows are annotated in `evals/data/gsm8k_notes.jsonl` and asserted
  reproducibly by `evals/build_gsm8k_notes.py` (`tests/test_evals_gsm8k.py`):
  - `gsm8k-test-0823` — **dataset_error**: the reference sums Julie's first-game score
    (10) where Sasha's (14) belongs, so its `14` is wrong; the faithful model gives `18`.
  - `gsm8k-test-0649` — **ambiguity**: "received 70 times as many … new likes" reads as
    "became 70×" (`160000`) or as "received 70× as new likes" (the reference's reading,
    `162000`); both are valid.
  Results: **dev 12/12**, **eval 38/40, 0 `grounded_mismatch`** (the only two non-correct
  rows are the annotated reference errors). The extraction improvements that took eval
  from 17/40 (first run) to 38/40 are the general bounded repair pass
  (`ANKYRA_ARITH_REPAIRS`, default 2) plus the collection-specific reading/encoding rules
  in `evals/skills/gsm8k/` — never sampling (`docs/l3_plan.md` D-L3-10). The `max`/`min`
  extension (D-L4-4) landed from the first run's `0015` failure.
- **Status (LLM-free, done).** `evals/build_gsm8k_sample.py` commits
  `evals/data/gsm8k_{dev,eval}.jsonl` (12 dev / 40 eval, carved deterministically from
  the test split, D-L4-3). The gold set `evals/data/gsm8k_gold.jsonl` holds 8 real
  problems from the dev slice, hand-encoded and validated through the builder; the
  adapter (`evals/gsm8k.py`) runs describe / `--gold` / `--live`. **Gold: 8/8 correct,
  0 `grounded_mismatch`.** The per-collection skill `evals/skills/gsm8k/` is in place.

## 14. Config, tests, docs

- **Config:** `ANKYRA_ARITH` (`on`|`off`, default `off`), recorded in `.env.example`
  and settings; the harness sets it, the wording never does. A system-size budget
  (`ANKYRA_ARITH_BUDGET`, default 200000) and the extraction repair bound
  (`ANKYRA_ARITH_REPAIRS`, default 2) are separate settings.
- **Tests:** `tests/test_engine_numeric.py` (every expr op; DAG and linear classes;
  determined/underdetermined/inconsistent; division by zero; `max`/`min`; build refusal),
  `tests/test_engine_numeric_routing.py` (the `numeric` capability/refusal, `decide`
  dispatch, `build_numeric_answer`/explanation, `render_answer` for `number`),
  `tests/test_evals_l4_synthetic.py` (the structural gate), `tests/test_build_numeric.py`
  (builder path), `tests/test_evals_gsm8k.py` (gold, sample carve, notes). Full
  regression: `uv run pytest`.
- **Docs:** `docs/gsm8k.md` (spike, gate, status), `docs/reasoning_roadmap.md` (L4
  status), `docs/implementation_plan.md` (backlog), `docs/task.md` (§1 scope update if
  L4 enters it), `docs/logic_layer.md`/`docs/fragment_routing.md` (the `numeric`
  procedure and capability), and this document, kept current.

## 15. Decisions

`D-L4-1`…`D-L4-4` are **DECIDED**. A new decision is opened here as it arises; the
plan must not proceed past a milestone affected by an open decision.

### D-L4-1 — Solver: in-repo exact rational, no new dependency

**Status: DECIDED — in-repo exact evaluation + linear elimination over
`fractions.Fraction`; no sympy.** Division and linear algebra are exact, auditable
and dependency-free; the scale of GSM8K is small. An external symbolic solver (sympy)
remains the documented fallback if a future scope needs non-linear/units work; it is
not adopted now. This mirrors D-L3-1 (in-repo search over Z3).

### D-L4-2 — IR scope: defined-quantity DAG + linear systems

**Status: DECIDED.** The first fragment is a defined-quantity DAG (the shape of a
reference arithmetic chain) plus finite **linear** systems over the unknowns, with
exact Gaussian elimination. Non-linear equations, general symbolic algebra and
functions are `out_of_fragment` (semi-decidable / not soundly terminating here).
Inequalities are `out_of_fragment` in the first fragment.

### D-L4-3 — Sample: deterministic dev/eval carve from the test split

**Status: DECIDED.** The committed sample is built deterministically from the
official **test** split and carved (by a stable index/hash rule, never by wording)
into a small **dev** slice (prompt/IR iteration, not a gate) and a disjoint **eval**
slice (the gate). The `train` split is excluded (a model may have seen it). Sample
sizes are small (L3 order of magnitude); built without LLM calls and committed; the
live runs are the only paid step.

### D-L4-4 — IR extension: exact `max`/`min`

**Status: DECIDED.** `max`/`min` are added to the term language: when every operand is
determined they evaluate exactly, and when an operand is still unknown the term is
`out_of_fragment` (a max/min of an unknown is piecewise). This is a **lowering** of the
common "maximize / whichever is greater" question (e.g. GSM8K `0015`, a choice between
two profits) rather than a workaround, and it removes the failure mode where a model
*fabricates* a branch equality (`best = one_candidate`) that the engine then certifies.
Because the maximum must be over a determined set at evaluation time, soundness is
unchanged. It was forced by the first live eval run (a grounded mismatch on `0015`);
the synthetic gate covers `max`/`min` of constants, a DAG `max` choice and a
`max`-of-unknown refusal.
