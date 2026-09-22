# FOLIO extension plan — raising the reachable coverage ceiling

Status: **draft plan, deferred** to a later iteration. Decisions `D-FE-1`…`D-FE-7`
(§9) are **proposed**, not yet DECIDED. No code in this note; it is the working
plan for widening how much of FOLIO Ankyra can cover *soundly*, once measured.

Canonical language: English; Russian mirror: `docs/folio_extension_plan_ru.md`.
Related: `docs/folio_ceilings.md` (coverage vs extraction ceilings),
`docs/folio.md`, `docs/quality_findings.md` §G, `docs/implementation_plan.md` §10,
`docs/fragment_routing.md`, `docs/l2_plan.md`, `docs/reasoning_roadmap.md`.

## 1. Goal

Raise the **reachable coverage ceiling** on FOLIO soundly, without pretending the
whole composite benchmark is a single-stage score. "Reachable" means: constructs
that lower into a committed decision procedure, or that become a new *named
fragment* with its own flag and gate. "Soundly" means: `proven` keeps its meaning,
and an unsupported construct stays an honest `out_of_fragment`.

The plan is **measure-first**: Phase 0 decides whether engine work is even the
right lever before any of it is built.

## 2. Principle

Two independent ceilings (`docs/folio_ceilings.md` §3):

- **Coverage** (formalism) — which sentences the committed logic can express.
- **Extraction** (model) — how often the LLM formalizes them correctly.

FOLIO's measured bottleneck today is extraction (`docs/quality_findings.md` §G):
the L2 procedure never derived a false conclusion from a correctly extracted
theory. So the plan front-loads the diagnostic and the extraction work, and treats
engine extension as conditional on the measurement.

## 3. Phase 0 — the decisive measurement (LLM-free, cheap)

**Goal.** Get the **gold-fed upper bound** for the L2 slice: feed the engine the
annotated FOL formulas (not the LLM extraction) and measure method-only accuracy.

**Actions.** Extend `evals/folio_fol.py` (today it parses only the L1 negation
shape) to `∨` and `∃`, and add a gold-fed mode for the L2 slice, mirroring the L1
gold-fed diagnostic (`docs/folio.md` §9). One file, LLM-free.

**Deliverable.** A gold-fed accuracy number on the committed L2 tier a (45
problems), overall and per label, alongside the existing text-fed number.

**Decision gate.**
- `gold-fed ≫ text-fed` → the limit is **language** → skip Phase 2/3, do Phase 1.
- `gold-fed ≈ text-fed`, both low → the limit is the **method** → Phase 2 is
  justified.

**Cost.** Zero LLM calls. This is the step named at
`docs/implementation_plan.md` §10 ("next step before L3").

## 4. Phase 1 — extraction generalization G1–G4 (highest value)

**Goal.** Move the extraction ceiling: the measured dominant loss on FOLIO L2.

| ID | Problem | Fix locus |
|---|---|---|
| G1 | non-range-restricted rules → `out_of_fragment` | extraction prompt (`build/extract.py`) + repair loop |
| G2 | lost premises / unlinked facts (0 morphisms) | premise extraction |
| G3 | universal / conditional / `¬∃` conclusions collapsed to a ground atom | extraction **and** a proper target form (Phase 2b) |
| G4 | ground-saturation budget exhausted | unit propagation / explicit budget (`engine/resolution.py`) |

**Gate.** A single budgeted live L2 tier a rerun: more correct determinate
answers, **no new unsoundness**, every remaining failure categorized. Full
collection is a separate, budgeted decision (`docs/reasoning_roadmap.md` §4).

**Note.** G3 is half engine work: even a correct extractor cannot express a
universal conclusion as a goal until the target form exists (Phase 2b).

## 5. Phase 2 — Tier 1: lowering, no new procedure

These are **not new formalisms**. They reuse the existing bounded clausal
procedure; the work is extraction + IR lowering, and the gate is an extension of
`evals.l2_synthetic`. The `ANKYRA_LOGIC` capability and the L2 semantics are
unchanged; new features flow through the declared-fragment contract
(`docs/fragment_routing.md`) as `FragmentFeature`s.

- **2a — `↔` and `⊕`.** Lower `A ↔ B` to two clauses `A→B`, `B→A`, and
  `A ⊕ B` to `(A∨B) ∧ (¬A∨¬B)`, in the builder (new `StructRule`/schema form →
  clauses). Cheap; no new decision procedure.
- **2b — universal / conditional / `¬∃` targets (G3).** Add a target form next to
  the existing `ask_all`/`ask_any` in `QuestionStructure`; the engine negates the
  goal, Skolemizes, and refutes. This is what makes a universal conclusion
  representable as a goal instead of a ground atom.
- **2c — multi-variable quantification over finite domains.** Generalize the
  finite grounding / witness enumeration (`engine/clause.py`, `_witness_pool`) from
  the current single-variable case. Risk: term/grounding blow-up — the budget must
  stay explicit and exhaustion must stay an honest `insufficient`.

**Gate.** Synthetic cases per construct; `out_of_fragment` beyond the finite
domain; the gold-fed L2 number re-measured.

The ordered Tier-1 backlog with per-item yields, loci, soundness notes and the open
decisions (`T-D1`…`T-D3`) is `docs/coverage_ceiling.md`.

## 6. Phase 3 — Tier 2: fragment decisions (with a soundness gate)

These leave "positive FOL" and are **separate fragment decisions**, not fixes.
Each enters only as a named fragment under `docs/fragment_routing.md`: a
`FragmentFeature`, a capability, a flag off by default, and its own synthetic
soundness gate before any live run.

- **3a — finite equality.** Finite congruence, or a ground equality builtin over
  the finite domain.
- **3b — bounded function terms.** Term representation (beyond the flat
  `subject`/`object` strings), clausification support, and bounded finite
  grounding; anything outside the finite range is `out_of_fragment`.

**Order.** Equality before functions (functions are harder and the classic
semi-decidability trap). Neither is a "bug fix".

## 7. Phase 4 — re-run as a gate

Run the FOLIO **in-fragment** slice once when a phase lands, record the number,
re-run only on a mismatch. It is a stage gate, never a headline; FOLIO stays a
composite benchmark (`docs/implementation_plan.md` §10).

## 8. Non-goals

- A whole-collection FOLIO score.
- Full FOL or non-finite function terms (semi-decidable; outside the boundary).
- Ad-hoc construct hacks that bypass the fragment contract.
- Lowering the semantics to pass a row (G3: `∀x(Pet→¬Cat)` → ground
  `¬is_a(pet,cat)` is a sound fact about the wrong target).
- Per-id tuning against the collection.

## 9. Decisions (proposed)

- **D-FE-1 — Measure before extending.** Phase 0's gold-fed L2 bound gates Phase
  2/3; without it engine work is aimed in the dark.
- **D-FE-2 — Extraction before engine.** Unless gold-fed shows a method ceiling,
  Phase 1 precedes Phase 2.
- **D-FE-3 — Tier 1 is lowering, not a new stage.** `↔`/`⊕`/targets/multi-variable
  reuse the L2 procedure and flag; gated by `evals.l2_synthetic`, not a new stage.
- **D-FE-4 — Tier 2 constructs are named fragments.** Equality and functions enter
  only via the declared-fragment contract, each with a flag and a soundness gate;
  equality before functions.
- **D-FE-5 — No semantic downgrade.** A conclusion the formalism cannot express is
  `out_of_fragment`; never re-encoded as a weaker fact to pass a row.
- **D-FE-6 — FOLIO is composite.** Only the in-fragment slice is scored; no
  headline, no per-id tuning.
- **D-FE-7 — Explicit budget.** G4 is fixed by unit propagation and/or a larger
  explicit budget, never by unbounded search; exhaustion stays `insufficient`.

## 10. Test plan

- **Phase 0.** Deterministic gold-fed runner (LLM-free); the number is committed
  as the L2 method bound.
- **Phase 2.** `evals.l2_synthetic` extended with a case per construct (lowering
  equivalence, universal/conditional goal, multi-variable, negative controls and
  `out_of_fragment`).
- **Phase 3.** A synthetic collection per new fragment: 0 grounded false proofs,
  determinate answers `proven`, kind accuracy above the L2 threshold, every
  remaining failure categorized.
- **Regression.** Existing L1/L2/defeasible/routing synthetic gates stay green.

## 11. Status

**Phase 0 done** (`docs/folio.md` §10): the L2 gold-fed bound exists and is
LLM-free. On tier a (45), coverage is 21/45 and on the covered rows gold-fed
(17/21) leads text-fed (15/21) — the limit is the **method**, so Phase 2 (Tier-1
lowering) is justified ahead of Phase 1 (extraction). The remaining phases are
still draft and deferred.

## 12. References

- `docs/folio_ceilings.md` — the ceiling model this plan operates on.
- `docs/quality_findings.md` §G — FOLIO L2 backlog G1–G4.
- `docs/implementation_plan.md` §10 — composite-benchmark gating methodology.
- `docs/folio.md` §4–§10 — FOLIO recon and live results.
- `docs/fragment_routing.md` — how a new fragment is declared.
- `docs/l2_plan.md` — the L2 procedure Tier 1 extends.
