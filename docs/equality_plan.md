# Equality Plan — Tier-2 item 3a (finite equality)

Status: **approved and implemented**. Tier-2 of `docs/folio_extension_plan.md` §6 is
split into **3a finite equality** (this note) and **3b bounded function terms**
(deferred, §5). The fragment is gated **synthetically only** (`evals.l2_synthetic`),
because no available collection exercises equality in a clean slice (§2). No new
decision procedure: it reuses the existing bounded clausal procedure behind
`ANKYRA_LOGIC`. Results are in §8.

Canonical language: English; Russian mirror: `docs/equality_plan_ru.md`.

Related: `docs/folio_extension_plan.md` (§6 Phase 3, `D-FE-4`), `docs/coverage_ceiling.md`
(the Tier-1 backlog this follows), `docs/l2_plan.md` (the procedure it extends),
`docs/fragment_routing.md` (the named-fragment contract), `docs/folio.md` §4 (the
construct inventory), `docs/quality_findings.md` §G, `docs/implementation_plan.md` §8,
`docs/reasoning_roadmap.md`.

## 1. Goal

Decide the finite ground equality `=` / `≠` inside the committed L2 fragment:
substitution (congruence), reflexivity, symmetry, and unique names, without leaving the
bounded clausal procedure and without lowering `proven`. A construct the fragment cannot
decide stays an honest `out_of_fragment` / `unsupported`, never a guess.

## 2. The finding that sizes the fragment: there is no external gate

The plan in `docs/folio_extension_plan.md` §6 listed equality as "reachable but absent
from the committed sample". Measurement (LLM-free, 2026-09-22) shows it is **absent from
the whole available collection**, and function terms are absent everywhere:

| source | rows | `=` | function term |
|---|---|---|---|
| FOLIO v0 `validation` (`evals/data/.cache/folio/validation.jsonl`, the committed source) | 204 | **0** | **0** |
| FOLIO v0 `train` (no `conclusion-FOL`) | 1004 | 0 | 0 |
| FOLIO v2 `validation` (`tasksource/folio`, `folio_v2_validation.jsonl`) | 203 | 33 | **0** |
| FOLIO v2 `train` (`tasksource/folio`, `folio_v2_train.jsonl`) | 1001 | 162 | **0** |

Worse, in FOLIO v2 equality is entangled with constructs the committed fragment does not
cover: of 33 validation equality rows, 30 use `var = var` (multi-variable quantification,
a deferred Tier-1 item), and a further filter leaves only 11 rows even without
XOR/biconditional/arity-3/nested quantifiers — several of which still use `∀x∀y` or
`∃x∃y` with two witnesses. So there is **no clean equality slice** to gate against, and
**no function term anywhere** (3b is not implemented; it stays the semi-decidability
trap named in `docs/l2_plan.md` §8).

Consequence (D-FE-4): equality enters as a **named fragment with a synthetic soundness
gate**, and the absent external gate is recorded here rather than papered over.

## 3. Scope and non-goals

**In scope.**
- The reserved binary predicate `eq` (subject/object; negation via `Morphism.negated`);
  `=` / `!=` normalize to it.
- Ground equality: substitution by canonicalization, reflexivity `eq(t,t)`, symmetry
  (via canonicalization), unique names `neq(a,b)` for distinct ground names.
- Equality in asserted facts, rule heads and bodies, existential atoms, and goals.
- The declared `equality` fragment feature, its refusal code, the synthetic gate, tests
  and docs.

**Out of scope (unchanged).**
- **Function terms** (`f(x,y)`) — no data; a separate deferred fragment (3b).
- Full first-order unification and non-ground equality; only ground equality over the
  finite named domain is decided.
- Equality in the Horn path: with `ANKYRA_LOGIC` off the structure is refused by name.
- Extraction / Phase 0 emission of `=` / `!=` (no live path is gated); the gold FOLIO v2
  parser; any new live LLM run (`docs/reasoning_roadmap.md` §4).
- No NL heuristics, no per-id tuning (`docs/task.md` §3.8).

## 4. Design decisions

- **EQ-D1 — Representation.** One reserved predicate id `eq`; `=` / `==` / `!=` map to
  it, negation is the existing `Morphism.negated` flag (there is no separate `neq`
  predicate). *Collision:* `engine/builtins.py` already maps `eq` / `neq` to the numeric
  comparison builtin. On the clausal/equality path `eq` is routed to the equality
  preprocessor (`engine/clause.py`), not to the builtin filter; the numeric builtin
  remains Horn-path-only (`ANKYRA_BUILTINS`). This keeps a single canonical id.
- **EQ-D2 — Semantics: finite named domain (declared).** The equality fragment reads the
  finite ground domain the L2 grounding already assumes: a term denotes its own name, so
  **distinct ground names are distinct unless an asserted ground equality merged them**.
  This is a *declared* semantics of the fragment (like the declared CWA of L1,
  `docs/l1_plan.md` D-L1-4), never guessed from wording, and off by default with
  `ANKYRA_LOGIC`. The soundness control `eq-control-diseq-07` pins the boundary: a
  disequality-conditioned rule does not fire for the excluded individual.
- **EQ-D3 — Lowering.** `engine/clause.py`, at clausification: an asserted **unit** ground
  equality builds a union-find partition; every term is canonicalized to its
  representative (substitution for free); then reflexivity units and both orientations of
  unique-names units are added over the individual domain. Asserted **conditional** or
  **disjunctive** equalities do not define the partition (they are not assertions); they
  are left to the prover and, where undecidable, stay honest. `resolution.py` is
  unchanged: every axiom is an ordinary resolution step.
- **EQ-D4 — Fragment / capability.** New `FragmentFeature "equality"` in
  `engine/inference.py`, decided by the existing `clausal` capability — **no new flag**
  (the T1/T3/T5/T4/T2 pattern). When the clausal capability is off and `eq` is present,
  the refusal is `out_of_fragment:equality`; equality is also in the clausal-fragment set
  so `defeasible × equality` refuses (D-FR-4).
- **EQ-D5 — Query canonicalization.** The query (target/goals/conditions) and the witness
  pool are canonicalized with the same partition as the theory (`verify.l2_outcomes`), so
  a goal over a merged name matches the canonical clause set.
- **EQ-D6 — Functions and the external gate.** 3b is not implemented (no data);
  Tier-2 is gated synthetically only (§2).

## 5. Engine changes

- **`engine/clause.py`.** `equality_partition` (asserted unit ground equalities +
  Skolemized existential atoms), `canonicalize_theory` / `canonicalize_query`, the
  `Clausification.canon` map, `has_equality` / `query_equality_terms`, and
  `_add_equality_axioms` (reflexivity + unique names); `clausify` gains
  `equality_terms=` and exempts `eq` from the builtin refusal.
- **`engine/inference.py`.** `FragmentFeature "equality"`, `_has_equality`, membership in
  `_CLAUSAL_FRAGMENT`, and the `out_of_fragment:equality` refusal on the Horn path.
- **`engine/verify.py`.** `l2_outcomes` passes the query's equality terms to `clausify`,
  canonicalizes the query and the witness pool, and canonicalizes a Gamma condition in
  `_unused_l2`.
- **`engine/resolution.py` / `engine/explain.py`.** No change (equality axioms are
  ordinary resolution edges).

## 6. Synthetic gate (`evals.l2_synthetic`, mechanism `equality`)

| case | theory / goal | expected |
|---|---|---|
| `eq-subst-01` | `is_a(rex,cat)`, `eq(rex,tom)`, `is_a(?x,cat)→is_a(?x,animal)`; goal `is_a(tom,animal)` | `supported`, `yes` (substitution) |
| `eq-reflexive-02` | `is_a(rex,cat)`; goal `eq(rex,rex)` | `supported`, `yes` |
| `eq-unique-names-03` | `is_a(rex,cat)`, `is_a(tom,cat)`; goal `eq(rex,tom)` negated | `supported`, `yes` |
| `eq-distinct-refuted-04` | same; goal `eq(rex,tom)` | `refuted`, `no` |
| `eq-symmetry-05` | `eq(rex,tom)`; goal `eq(tom,rex)` | `supported`, `yes` |
| `eq-body-disequality-06` | rule body `?x != rex`; goal `is_a(tom,special)` | `supported`, `yes` |
| `eq-control-diseq-07` | same; goal `is_a(rex,special)` | `unsupported` (**soundness control**) |
| `eq-control-flag-off-08` | `eq` structure, `logic="off"` | `out_of_fragment:equality` |
| `eq-control-budget-09` | substitution case, `budget=1` | `insufficient`, **never** a proof |

`evals.build_routing_synthetic` adds `equality-18` (feature, clausal) and
`refuse-equality-19` (refusal with L2 off).

## 7. Tests and verification

- `tests/test_engine_equality.py` — partition, canonicalization, axiom injection,
  substitution, reflexivity, unique names, symmetry, body disequality + control, routing
  refusal.
- `tests/test_evals_l2_synthetic.py` / `tests/test_evals_routing_synthetic.py` — gate and
  coverage updates.
- `uv run pytest`, `uv run python -m evals.l2_synthetic`,
  `uv run python -m evals.routing_synthetic`,
  `uv run python -m evals.analyze_folio --subset l2` (unchanged: no equality in FOLIO v0).

## 8. Results

Implemented 2026-09-22 (decisions EQ-D1…EQ-D6). LLM-free verification:

| gate | before | after |
|---|---|---|
| `evals.l2_synthetic` | 56/56 | **65/65** (9 `equality` cases) |
| `evals.routing_synthetic` | 17/17 | **19/19** (feature + refusal) |
| `uv run pytest` | 480 passed | **505 passed**, 26 skipped |
| FOLIO L2 tier a gold-fed | 42/45 | 42/45 (unchanged; `out_of_fragment` 1, covered 42/44) |

No FOLIO number moves, because FOLIO v0 contains no equality. The fragment is proven by
the synthetic gate, whose controls hold: the disequality rule does not fire for the
excluded individual, an exhausted budget is never a proof, and equality with L2 off is
refused by name.

## 9. Guardrails

- A construct enters only as a named fragment (`docs/fragment_routing.md`); outside the
  finite ground domain it stays an honest `out_of_fragment` / `unsupported`.
- The unique-names reading is **declared** (EQ-D2), never inferred from wording; the
  numeric `eq` builtin is not reused on the clausal path (EQ-D1).
- No semantic downgrade: a disequality is never assumed away, and an excluded individual
  never fires a rule by substitution.
- No per-id tuning; the gate is structural and LLM-free.
- No new live LLM run without an explicit, separate decision
  (`docs/reasoning_roadmap.md` §4).
