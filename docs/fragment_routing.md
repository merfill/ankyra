# Fragment Routing — the declared-fragment contract

Status: **approved plan** (A1: validation-only first increment); not yet
implemented. Decisions `D-FR-1`…`D-FR-6` in §9 are **DECIDED**. This document is
the working plan for selecting a decision procedure from the structure Phase 0
produced, at stage level of `docs/reasoning_roadmap.md`.

Canonical language: English; Russian mirror: `docs/fragment_routing_ru.md`.
Related: `docs/reasoning_roadmap.md`, `docs/logic_layer.md` (the `Inference`
seam), `docs/l1_plan.md`, `docs/l2_plan.md`, `docs/defeasible_reasoning.md`,
`docs/task.md`.

## 1. Problem

How does Ankyra choose a logic for a problem when the logic is not known in
advance? The answer must preserve the design commitment (**the LLM proposes, the
engine decides**) and must not guess semantics.

Two tempting answers are rejected:

- **Try every logic.** Inefficient, and it lets a more expressive formalism
  override an honest weaker verdict, which makes the reported answer depend on
  the search rather than on the declared reading.
- **Ask the LLM which logic.** The LLM authors the formalization, not the
  semantics of the question; asking it to pick a logic re-delegates a decision it
  cannot own (`docs/task.md` §3.8).

The remaining answer — a deterministic, auditable selection over the **structure**
Phase 0 already produced — needs to be stated precisely, because "logic" conflates
three different things.

## 2. Three axes, three sources

| Axis | Examples | Source | When |
|---|---|---|---|
| **Fragment** (expressiveness) | `horn`, `negation`, `disjunction`, `existential`, `builtin` | **derived** from the built `Theory`/`Query` | static, before deciding |
| **Semantics** | open/closed world, monotonic/defeasible | **declared** by the question/benchmark (`Query.world_assumption`; `DEFEASIBLE`) | static |
| **Procedure** | Horn forward chaining, clausal resolution | **derived** from fragment ∧ semantics | static |

The critical separation: **the fragment is a function of the structure the LLM
produced; the semantics is declared from outside.** The engine never infers a
closed world from negation-as-failure or from the absence of facts (this is
already the rule of `docs/l1_plan.md` D-L1-4).

Corollary, stated honestly: the LLM *does* select the fragment **by the shape it
extracts** (a `StructDisjunction` vs a fact, `StructRule.consequents` vs
`consequent`, `StructExistential`). The engine does not remove that authority; it
makes it auditable and bounds its blast radius with the capability set (§4). The
commitment the engine guarantees is over **truth** (`proven`/`refuted`), not over
which fragment the extraction emitted.

## 3. Fragment derivation (pure)

The required fragment is computed from the built structures with the existing
structural predicates (`engine/horn.py`):

- `horn` — `not has_non_horn(theory)`, no `Theory.existentials`, and
  `query.goal_mode == "single"`.
- `negation` — non-empty `Theory.constraints` (disjointness) or a negated literal
  in a rule body/head.
- `disjunction` — `has_non_horn(theory)` (a disjunctive **head** or a disjunctive
  ground fact).
- `existential` — non-empty `Theory.existentials` or an existential goal.
- `compound_goal` — `query.goal_mode != "single"` (a conjunctive or disjunctive goal).
- `builtin` — a comparison predicate (`engine/builtins.is_builtin`).
- `equality` — the reserved `eq` predicate anywhere (`engine/clause.has_equality`,
  `docs/equality_plan.md`). Requires the clausal procedure; refused by the Horn path
  (which would treat `eq` as an opaque predicate).

Note: a disjunctive **antecedent** is already split by the builder into one Horn
rule per atom (`(A ∨ B) → C ≡ (A → C) ∧ (B → C)`); it does **not** raise the
fragment. Only a disjunctive head and a compound goal require the clausal
procedure.

## 4. Capability set (Approach A)

The flags enumerate the procedures a run **may** use; they do not name a
semantics.

| Capability | Flag | Default |
|---|---|---|
| `horn` | always available | on |
| `clausal` (L2) | `ANKYRA_LOGIC` ≠ `off` | off |
| `builtin` | `ANKYRA_BUILTINS` | off |
| `defeasible` | `ANKYRA_DEFEASIBLE` | off |

`world_assumption` is **not** a capability: it is the declared semantics, carried
by the query and defaulted by `ANKYRA_NEGATION_MODE` (`build/pipeline.py`).

The capability set is a **per-run parameter**:

- **benchmark gates / ablations** pin or narrow it, so "this number was produced
  by the Horn procedure" is a claim about a named formalism;
- the **product runtime** broadens it, so a single user query uses the strongest
  sound procedure its declared semantics allow, and refuses honestly otherwise.

The gate case is a special case of the product case (a set of size one). This is
why the design is a single mechanism, not two.

## 5. Decision and validation

A static, total decision (no iteration):

```python
class RoutingDecision:
    required_fragment: frozenset[FragmentFeature]
    declared_semantics: dict          # world_assumption, defeasible
    capabilities: frozenset[str]
    procedure: str                    # "horn" | "clausal"
    compatible: bool
    reasons: list[str]                # e.g. "disjunction:head_alternatives"
```

- fragment ⊆ `{horn, negation, builtin}` → `horn`;
- fragment contains `disjunction` or `existential` → `clausal`;
- `defeasible` declared → the defeasible layer over the chosen base procedure;
- if the chosen procedure cannot honor the **declared** semantics, or a required
  fragment is outside the capability set → `out_of_fragment`, with a named gap
  code (never a silent run under the wrong semantics).

The refusal codes are `out_of_fragment:non_horn`, `compound_goal`, `existential`,
`equality`, `stratification` and `naf_in_l2` (the pre-existing codes, preserved), plus
`defeasible_with_clausal_fragment` (D-FR-4).

Validation happens **before** deciding; gaps are not re-interpreted afterwards.

## 6. Where it lives

A pure `analyze_routing(theory, query) -> RoutingDecision` in
`engine/inference.py` (where `select_inference` already lives), called by
`verify`. The ad-hoc refusals in `engine/verify.py` (`out_of_fragment:non_horn`,
`compound_goal`, `stratification`, `naf_in_l2`) and the clausification refusals
become consequences of the decision, **preserving their gap codes** so the
existing suites stay green. `engine/explain.py` follows the same
`decision.procedure` so the explanation path cannot disagree with the verdict.

No schema or prompt change: the fragment is derived, never authored by the LLM.

## 7. The proposal cycle

No gap-driven escalation. The cycle (Phase 2) may **replace the structure** (the
LLM proposes a reformulation, classified `derivable`/`cited`/`hypothesis`/
`rejected`); the router recomputes the fragment on the new structure. That is the
only legitimate way the procedure changes within a run, and it is an auditable
proposal, not an engine guess.

Why a cascade over gaps is rejected, concretely:

- For a purely Horn structure, definite forward chaining is complete for ground
  entailment, so the clausal procedure adds nothing; for non-Horn content the
  required fragment is visible statically before the run. A gap-driven promotion
  therefore rescues no case it can reach and risks changing semantics.
- A `verify` under one procedure cannot diagnose "you need another procedure"
  without knowing other fragments' constructs, which violates the
  `docs/logic_layer.md` §2 seam.

## 8. Non-goals

- A `fragment` field authored by the LLM (a second source of truth that can
  disagree with the structure).
- Cause codes such as "you need L2" returned by `verify` (the analyzer knows
  statically).
- An iterative cascade with a stop condition.
- Inferring the world assumption from structure. It is declared, always.

## 9. Decisions

- **D-FR-1 — Capability set, not auto-procedure.** Flags declare allowed
  procedures; they never name a semantics. Semantics stays declared by the
  query/harness.
- **D-FR-2 — First increment is A1 (validation-only).** `select_inference` keeps
  its current behavior (`ANKYRA_LOGIC` on + goals → clausal); `analyze_routing`
  is added as a validator and refusal point. The minimal-sufficient choice within
  a broad capability set (A2) is **deferred** until a product runtime enables
  several capabilities at once and the behavior is measured on its own.
- **D-FR-3 — No escalation over gaps.** The procedure is chosen once, statically;
  the proposal cycle changes the structure, not the engine's logic.
- **D-FR-4 — Defeasible × disjunction is an explicit refusal.** The defeasible
  layer (`engine/defeasible.py`) ranges over the Horn closure and reads only
  `rule.consequence`, ignoring `alternatives`. A structure that is both
  defeasible and requires the clausal fragment is reported
  `out_of_fragment:defeasible_with_clausal_fragment`, never silently downgraded.
- **D-FR-5 — No LLM-declared fragment.** Derived from the structure.
- **D-FR-6 — The expected fragment is declared by the harness.** Each collection
  adapter asserts the fragment of its committed sample (ProofWriter tier D →
  `horn`; ProntoQA-OOD tier a → `clausal`). This is the honest home for a
  declaration; the engine derives.

## 10. Implementation plan (A1, minimal diff)

1. `engine/inference.py` — add `FragmentFeature`, `RoutingDecision`,
   `analyze_routing(theory, query)`; read capabilities via `get_setting`. Keep
   `select_inference` unchanged (D-FR-2).
2. `engine/verify.py` — call `analyze_routing` first; express the existing
   refusals (`non_horn`, `compound_goal`, `stratification`, `naf_in_l2`) as
   decision outcomes with unchanged gap codes; add
   `out_of_fragment:defeasible_with_clausal_fragment` (D-FR-4).
3. `engine/explain.py` — replace the `logic_enabled()` branch with
   `decision.procedure` so explanation and verdict agree.
4. Tests — a committed, LLM-free synthetic collection
   (`evals/build_routing_synthetic.py`, `evals/routing_synthetic.py`,
   `evals/data/routing_synthetic.jsonl`) covering every fragment feature and every
   refusal code, graded by `tests/test_evals_routing_synthetic.py`. Full
   `uv run pytest`.
5. Docs — this note; link it from `docs/reasoning_roadmap.md` §6 and
   `docs/logic_layer.md` §10.

## 11. Test plan

- **Unit (analyzer).** Per feature: Horn theory → `horn`; disjunctive head /
  compound goal → `clausal`; constraint / negated literal → `negation`;
  existential → `clausal`.
- **Refusal.** Required fragment outside the capability set → `out_of_fragment`
  with the named code; closed-world NAF under clausal → `naf_in_l2`; defeasible ×
  disjunction → `defeasible_with_disjunction`.
- **Gate invariant (D-FR-6).** Each collection harness asserts its expected
  fragment; 0 cases where a structure containing disjunction/existential is
  decided by the Horn procedure.
- **Regression.** The existing L1/L2/defeasible synthetic suites and
  `test_engine_inference.py` stay green under A1.

## 12. Status

**A1 implemented.** `analyze_routing` + `RoutingDecision` in `engine/inference.py`;
`verify` consults the decision before dispatching (the existing refusals keep their
gap codes, plus `defeasible_with_clausal_fragment`); `explain` follows
`decision.procedure`. The LLM-free gate `evals.routing_synthetic` is green
(**19/19**; every fragment feature, including `equality`, and every refusal code
covered). The deferred A2
increment (minimal sufficient procedure inside a broad capability set) is tracked
here and is a prerequisite for a multi-capability product runtime being able to
claim more than the pinned gate.
