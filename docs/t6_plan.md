# T6 Plan — G4 resolution budget / ground unit propagation

Status: **approved and implemented**. T6 is the sixth and last item of the
Tier-1 backlog (`docs/coverage_ceiling.md` §6–§7). It is an **optimization**, not a
new construct: it makes the committed bounded clausal procedure find a short
unit-propagation refutation that the naive pair loop misses, so rows that were
`insufficient` because of an exhausted step budget (backlog **G4**,
`docs/quality_findings.md` §G) become decided. Per `D-FE-7` the budget stays
explicit; exhaustion stays the honest `insufficient`. It introduces **no new flag
and no new `FragmentFeature`** — the capability is the existing `clausal`
(`ANKYRA_LOGIC`). Results are in §12.

Canonical language: English; Russian mirror: `docs/t6_plan_ru.md`.

Related: `docs/coverage_ceiling.md` (the ordered backlog, item T6),
`docs/t4_t2_plan.md`, `docs/t5_plan.md` (the per-item pattern T6 follows),
`docs/l2_plan.md` (§7.5 boundedness, §8 unit propagation), `docs/folio_gold_fed.md`
(the measurement this item follows), `docs/quality_findings.md` §G (G4),
`docs/folio_extension_plan.md` (D-FE-7), `docs/fragment_routing.md`,
`docs/reasoning_roadmap.md`, `docs/implementation_plan.md` (§8 item 26).

## 1. Goal

Remove the last coverage-side misses on the committed FOLIO L2 slice by making the
prover decide a short unit-propagation chain in far fewer steps, so `G4` budget
exhaustion stops blocking rows the formalism can already express. Measured baseline
(2026-09-22, after T1/T3/T5/T4/T2, `uv run python -m evals.analyze_folio --subset l2`):

| verdict source | correct |
|---|---|
| text-fed | 25/45 |
| gold-fed open | 40/45 |
| gold `out_of_fragment` | 1/45 |
| covered (method) | 40/44 |
| covered (text) | 25/44 |

The four wrong gold-fed rows decompose as: **0009** and **0010** —
`logic_budget:exhausted` (this is T6's yield of **2**), and **0047**, **0139** — an
honest `unsupported` (`not_entailed`, no proof exists in the fragment), not a
budget problem. The single `out_of_fragment` row is the malformed annotation `0109`.

| id | label | goal | status | gaps |
|---|---|---|---|---|
| folio-validation-0009 | True | `is_a(tom, ocellated)` | `insufficient` | `logic_budget:exhausted` |
| folio-validation-0010 | False | `is_a(tom, eastern)` | `insufficient` | `logic_budget:exhausted` |
| folio-validation-0047 | False | `love(...)` | `unsupported` | `target_unmatched:love` |
| folio-validation-0139 | False | `is_a(...)` | `unsupported` | `target_unmatched:is_a` |

Raising `ANKYRA_LOGIC_BUDGET` does not help: 200 000 gives the same answer, and
1 000 000 does not terminate in ten minutes. The limit is the **search shape**, not
the step count.

## 2. Current blocker

`refute_support` (`engine/resolution.py:121`) is a naive pair loop: at each round it
scans every clause in the set of support against every clause in the set and
resolves on every complementary pivot pair. It has no indexing and, crucially, does
not use **unit clauses**. On `0009`/`0010` the theory is small (6 rules) but wide:

- `∀x (WildTurkey(x) → E ∨ O ∨ G ∨ M ∨ R ∨ Oc)` grounds to a 7-literal disjunctive
  clause per term;
- the unit facts `WildTurkey(tom)`, `¬Eastern(tom)`, `¬Osceola(tom)`,
  `¬Goulds(tom)`, `¬Merriams(tom)`, `¬Riogrande(tom)` falsify all but `Oc(tom)`;
- 246 of the 261 clauses are transitive `is_a` instances.

A handful of unit resolutions (propagate `WildTurkey(tom)`, then each negated
conjunct) refutes the goal — `Oc(tom)` follows by a unit chain; `¬Eastern(tom)`
follows directly. The pair loop still explores the wide clause set and exhausts the
10 000-step budget before reaching it. This is exactly the `G4` finding
(`docs/quality_findings.md` §G): "larger stories (6–8 rules, many objects) exhaust
the 10000-step cap". `docs/l2_plan.md` §8 already names the fix — "on the ground
fragment, unit propagation run before case splits" — it was simply not implemented.

## 3. Scope and non-goals

**In scope.**
- A **ground unit-propagation** fast path inside `refute_support`: propagate every
  unit clause to a fixpoint before the general set-of-support loop, recording each
  propagation as a real resolution node; then run the existing loop on the
  simplified set.
- The budget accounting (D2), provenance (D3), the synthetic gate, and the tests.

**Out of scope (unchanged).**
- A full DPLL/CDCL rewrite (watched literals, conflict analysis, clause learning) —
  unnecessary for the committed finite-domain fragment.
- Hyper-resolution, self-subsuming resolution, DRAT, first-order unification.
- Any change to clausification (`engine/clause.py`), verdict assembly
  (`engine/verify.py`), or explanation rendering (`engine/explain.py`): the new
  nodes are ordinary resolution edges.
- No new flag, no new `.env` setting, **no new `FragmentFeature`**: T6 is a prover
  optimization, not a construct to declare.
- No semantic downgrade: `not_entailed` is unchanged; a disjunction is never decided
  by a disjunct; exhaustion is never a proof.
- No NL heuristics, no per-id tuning (`docs/task.md` §3.8;
  `docs/coverage_ceiling.md` §8).

## 4. The change

### 4.1 Reading

Ground unit resolution is the fact that from a unit clause `{l}` and a clause
`C ∪ {¬l}` one derives `C`. Iterating it to a fixpoint is **sound** (each step is a
binary resolution) and is the standard preprocessing that makes goal-directed
search cheap. `T ∪ {¬goal}` is unsatisfiable iff that closure derives the empty
clause; unit propagation reaching the empty clause is a genuine refutation, and
exhausting the budget without it stays the honest `budget`.

### 4.2 Procedure (reusing the same budget and proof DAG)

In `refute_support`:

1. Load the base clauses and the assumed (negated-goal / support) clauses exactly as
   today.
2. **Unit-propagation fixpoint.** Seed a queue with every unit clause in the set.
   For each popped unit `{l}`, for every clause `C` containing `¬l`, resolve on `l`:
   - the resolvent `C \ {¬l}` is added with node `(unit_key, clause_key, ¬l)`;
   - an **empty** resolvent is the refutation (`entailed`);
   - a **unit** resolvent is enqueued;
   - the resolvent is marked in-support when either parent is (set-of-support
     compatibility).
   Each propagation counts as one step against the same budget; hitting the budget
   returns `budget` (never a proof).
3. **General set-of-support loop** — unchanged, now run over the simplified clause
   set (the existing `_pivots`/`_resolve`/subsumption logic).

No new decision procedure is introduced; the fast path is an instance of the
existing binary resolution already recorded in the proof DAG.

### 4.3 Why this is sound and general

- **Sound.** Every propagation is a binary resolution on a real pivot; only an
  actually derived empty clause is `entailed`. No clause is fabricated, and no
  literal is dropped without a resolution edge.
- **Provenance-preserving.** Each propagated clause records
  `(unit_key, clause_key, pivot)` in `nodes` and inherits empty `origins`, exactly
  like a searched resolvent. `Proof.derivation()` and `engine.explain` consume the
  DAG unchanged.
- **Complete for the fragment.** Unit propagation only reorders the resolution
  derivation: it adds consequences that a full search would also derive. The
  set-of-support loop still runs after it, so the search remains refutation-complete
  relative to the budget.
- **Bounded.** The number of propagations is bounded by the clause count; the
  existing step budget caps the combined search, and exhaustion stays `budget`.

## 5. Design decisions

- **T6-D1 — Form.** (a) Integrate a ground unit-propagation fixpoint into
  `refute_support`, keeping the set-of-support loop and the proof DAG. (b) A full
  DPLL/CDCL rewrite — larger, unnecessary for the committed fragment. (c) Only raise
  the default budget — rejected: it does not terminate on `0009` even at 1 000 000
  and hides an unbounded cost behind an "explicit budget". **DECIDED (a)**; (b) and
  (c) recorded as rejected alternatives.
- **T6-D2 — Budget accounting.** (a) Every propagation counts as one step of the
  same budget; exhaustion is `budget`. (b) Propagation is free and only search
  resolutions count — this would turn the existing negative control `budget-01` into
  a proof and weaken the "exhausted budget is never a proof" guarantee. **DECIDED
  (a)**.
- **T6-D3 — Provenance.** Each propagated clause records a real resolution node
  `(unit_key, clause_key, ¬l)`; the empty clause is a node. **DECIDED**.
- **T6-D4 — Scope.** Ground unit propagation only; no hyper-resolution, indexing, or
  clause learning unless a measured blocker demands it. **DECIDED**.
- **T6-D5 — Fragment naming.** None: T6 adds no construct, so no `FragmentFeature`
  and no routing change (a deliberate departure from the T1/T3/T5/T4/T2 pattern,
  which each added a named fragment). **DECIDED**.

## 6. Engine changes

- **`engine/resolution.py`.** Extend `refute_support` with the unit-propagation
  fixpoint of §4.2 before the existing loop; add a small internal helper for the
  propagation step. `refute`, `refute_conjunction`, and `prove` are unchanged (they
  all delegate to `refute_support`). `DEFAULT_BUDGET` and the returned
  `ProverResult` shape are unchanged.
- **`engine/clause.py` / `engine/verify.py` / `engine/explain.py`.** No change.
- **`engine/inference.py`.** No change (no new `FragmentFeature`).

## 7. Gold-fed parser

No parser change.

## 8. Synthetic gate (`evals.l2_synthetic`)

Add a `unit_propagation` mechanism to `evals/build_l2_synthetic.py`, with mandatory
controls. The shape mirrors the `0009` obstruction: a disjunctive head whose body is
satisfied, plus unit negations that force exactly one disjunct.

| case | theory / goal | expected |
|---|---|---|
| `unit-prop-01` | `is_a(rex,w)`; `∀x(w(x) → a∨b∨c)`, `¬a(rex)`, `¬b(rex)`; goal `is_a(rex,c)` | `supported`, `yes` (propagation forces `c`) |
| `unit-prop-02` | same theory; goal `is_a(rex,d)` (a literal not forced) | `unsupported`, `unknown` (**soundness control**: propagation only closes genuinely forced branches) |
| `unit-prop-03` | `unit-prop-02` with `LOGIC_BUDGET=1` | `insufficient`, **never** a proof |
| `unit-prop-04` | `unit-prop-01` under `logic="off"` | `out_of_fragment:non_horn` |

The existing `budget-01` negative control (an exhausted budget is never a proof) must
stay green with the propagation step counted (D2); it is verified by the prototype.

## 9. Tests and verification

Prototype (LLM-free, not committed) with the unit-propagation fixpoint in
`refute_support`:

| metric | baseline | prototype |
|---|---|---|
| gold-fed open (correct) | 40/45 | **42/45** |
| gold `out_of_fragment` | 1/45 | 1/45 |
| coverage (method) | 44/45 | 44/45 |
| covered gold-fed | 40/44 | **42/44** |
| grounded false proofs | 0 | **0** |
| `evals.l2_synthetic` | 52/52 | **52/52** (controls preserved) |

`0009` and `0010` are decided; `0047`, `0139` remain honest `unsupported` and `0109`
the malformed annotation.

- `tests/test_engine_resolution.py`: unit propagation derives the forced literal and
  refutes; an unforced literal is not derived (soundness control); the budget
  exhausts honestly; the propagation nodes are recorded in the DAG.
- `tests/test_engine_logic_l2.py`: the `unit_propagation` cases end-to-end.
- `uv run pytest` (offline) — full regression.
- `uv run python -m evals.l2_synthetic` — new total, **0 mismatches**.
- `uv run python -m evals.routing_synthetic` — green (unchanged; no new feature).
- `uv run python -m evals.analyze_folio --subset l2` — LLM-free gold-fed re-measure:
  gold-fed 40→**42/45**, covered 40→**42/44**, `out_of_fragment` 1, and among covered
  rows **0 grounded false proofs**. Record before/after in `docs/folio_gold_fed.md`.

## 10. Risks

- **Provenance fidelity.** A propagation step must record a real resolution edge;
  otherwise the explanation fabricates a step. `tests/test_engine_resolution.py`
  checks the recorded nodes and `engine.explain` renders them.
- **Budget honesty (D2).** If propagation is not counted, `budget-01` becomes a
  proof and the "exhausted budget is never a proof" control is lost. The synthetic
  gate asserts exhaustion.
- **Search still exponential.** The fast path removes the unit-chain misses, not the
  worst case; the budget stays explicit and exhaustion stays `insufficient`.
- **No semantic downgrade.** `not_entailed` and the disjunction handling are
  unchanged; no disjunct is decided by a disjunct.
- No full FOLIO live re-run without a separate budgeted decision
  (`docs/reasoning_roadmap.md` §4).

## 11. Work order (milestones)

1. Engine: unit-propagation fixpoint in `refute_support`; unit tests. (Gates nothing
   live.)
2. Synthetic `unit_propagation` cases (soundness control first); `evals.l2_synthetic`
   green.
3. `uv run pytest` and `evals.routing_synthetic` regression.
4. LLM-free gold-fed re-measure; record the delta.
5. Docs: `coverage_ceiling.md` (T6 done + numbers), `folio_gold_fed.md`,
   `l2_plan.md` (`refute_support` milestone), `reasoning_roadmap.md`,
   `implementation_plan.md` item 26; `docs/t6_plan_ru.md` mirror.

Each milestone lands reviewable on its own; the soundness gate (step 2) precedes the
gold-fed re-measure (step 4).

## 12. Results

Implemented (decisions T6-D1a…T6-D5). LLM-free verification, 2026-09-22:

| gate | before | after |
|---|---|---|
| `evals.l2_synthetic` | 52/52 | **56/56** (new `unit_propagation` mechanism) |
| `evals.routing_synthetic` | 17/17 | 17/17 (unchanged; no new feature) |
| `uv run pytest` | 476 passed | **480 passed**, 26 skipped |

FOLIO L2 tier a, gold-fed (`uv run python -m evals.analyze_folio --subset l2`):

| metric | before | after |
|---|---|---|
| gold-fed open (correct) | 40/45 | **42/45** |
| gold `out_of_fragment` | 1/45 | 1/45 |
| coverage (method) | 44/45 | 44/45 |
| covered gold-fed | 40/44 | **42/44** |
| grounded false proofs | 0 | **0** |

`0009` (`supported`/`True`) and `0010` (`refuted`/`False`) are now decided by the
unit-propagation chain. `0047` and `0139` remain honest `unsupported`
(`not_entailed`), and `0109` stays the malformed annotation. The synthetic
soundness controls hold (`unit-prop-02` unforced literal is not derived,
`unit-prop-03` exhausted budget is never a proof), the existing `budget-01`
control stays green, and the gold-fed re-measure has 0 grounded false proofs.
