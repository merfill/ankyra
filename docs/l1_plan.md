# L1 Plan — Stratified negation / negation-as-failure

Status: **implemented and gated** — L1 (disjointness constraints, stratified
negation-as-failure, declared CWA) landed; the decisions in §18 are **DECIDED**. This
is the working plan for stage **L1** of `docs/reasoning_roadmap.md`; the milestone
status is in §16.

Canonical language: English; Russian mirror: `docs/l1_plan_ru.md`. Related:
`docs/reasoning_roadmap.md` (§3 L1, §4–5), `docs/prontoqa.md`, `docs/folio.md`,
`docs/logic_layer.md`, `docs/task.md`, `docs/implementation_plan.md` (§8–9).

## 1. Goal

Widen the class of decidable reasoning by adding the L1 formalism: definite Horn
clauses plus **stratified negation**, **disjointness constraints**, and a
**declared closed-world assumption (CWA)** carried by the query. The LLM proposes,
the engine decides — the new machinery must stay inside the same boundary: nothing
enters the theory without a quote or an explicit hypothesis tag.

Concretely, L1 must enable answers that today are impossible:

- a **negative conclusion** from an explicit negative rule (`∀x(C → ¬P)`);
- a **disjointness** conclusion (no individual is both `Ci` and `Cj`);
- "not stated, therefore not holding" **when, and only when, a closed world is
  explicitly declared** for the query.

## 2. Scope and non-goals

- **In scope:** ProntoQA negation/disjointness subset (L1 gate), and the
  negated-premise subset of FOLIO as a secondary stress (`docs/folio.md`).
- **Out of scope:** compositional ProntoQA-OOD (disjunction, case splits, proof by
  contradiction) is **L2**, not L1. L3/L4 remain separate engines.
- No full-collection runs (no free LLM access; see §17).
- No NL heuristics: disjointness/negation must be extracted structurally by the LLM,
  never detected with cue phrases or word lists (`docs/task.md` §3.8).

## 3. Guardrails (gating)

- **CWA is a semantic choice, never guessed.** It is attached to the query (or the
  benchmark run), never inferred from wording.
- **A non-stratifiable program is not guessed.** It is reported `out_of_fragment`.
- **0 grounded false proofs** is the hard gate; every determinate answer must be
  `proven`. Do not add the stage on top of a known false-proof hole (findings 21–22
  are closed, which is why L1 can start).
- Every derived negative atom carries provenance, like any positive fact.

## 4. What L1 adds, and what already exists

Already present in the engine (usable as-is):

- negated atoms (`Morphism.negated`) for facts, rule conditions and rule
  consequences; `Rule.kind="exception"` flips a consequence's polarity;
- complementary-pair detection `P` / `¬P` (`horn.complementary`), surfaced as the
  `contradiction` status;
- per-query conditions (Gamma) and the hypothesis ledger.

Genuinely new for L1:

- **negative body literals** evaluated by failure (NAF);
- **disjointness constraints** as first-class theory objects;
- an explicit **world assumption** on the query, and a **stratified closure** that
  keeps NAF well-defined;
- extraction and explanation support for the above.

## 5. Benchmark and subset stratification

ProntoQA is heterogeneous (`docs/prontoqa.md` §5). A run must be **stratified by
proof shape**: the in-fragment subset is scored against the gate; everything else is
reported `out_of_fragment` and is not a failure. Mapping of proof steps
(`docs/prontoqa.md` §4): `AXIOM`, `ModusPonens`, `AndIntro/AndElim` are L0;
disjointness and negated properties are L1; `Or*` and `ProofByContra` are L2.

## 6. Step 0 — Recon (LLM-free)

First task, before any engine work (`docs/prontoqa.md` §7.0). No LLM calls.

- Build a tally of proof-step shapes over a few hundred examples to size the
  L0 / L1 / L2 subsets precisely.
- **Critical question:** is sibling disjointness expressed in the *surface context*,
  or only in the generator's formal ontology? If it is not in the text, then Ankyra
  cannot extract it without a forbidden heuristic, and the harness must supply it as
  benchmark-provided structure (testing the engine, not extraction). The recon
  settles this; it drives open decision D-L1-1.
- Output: a recon report (folded into `docs/prontoqa.md` §8) with the subset sizes
  and the disjointness verdict.

**Recon results (done, LLM-free).** Sources: `smoorsmith/prontoqa` (Logic-LLM mirror
of v1, 1500 rows) and the official generator (`asaparov/prontoqa` v1, `--model-name
json`, seed 7, 180 rows). Findings, detailed in `docs/prontoqa.md` §8:

- the collection is **L0 (positive chains) + L1 (explicit negated-property rules)**;
- **no disjointness in the surface text** and no proof uses it (the disjointness
  axioms live only in the generator's formal ontology);
- no `And`/`Or`/`ProofByContra` (those are the L2 OOD release);
- the existing engine **already** solves the explicit-negation subset (negative
  consequent + positive target → `refuted`/`proven`, checked offline).

Consequence: the new machinery below (constraints, NAF, CWA) is **not exercised** by
this collection. Scope is open decision **D-L1-5**; until it is settled, milestones
3–4 must not start as "needed by ProntoQA".

## 7. Semantics to add

### 7.1 Negative consequents (explicit negative knowledge)

`∀x(C(x) → ¬P(x))` is a definite rule with a negative head. The engine already
derives such atoms; L1 must ensure they participate in stratification and are
rendered in the explanation. This covers ProntoQA negated properties
("Every real number is not imaginary").

### 7.2 Negative antecedents / negation-as-failure

A body literal `not P(t)` holds when `P(t)` is **not derivable** (in the appropriate
stratum/world). This is the NAF reading. It is only meaningful under a declared
closed world for the relevant predicate; under an open world, `¬P(t)` means an
explicitly derived/asserted negative, not absence.

### 7.3 Disjointness constraints

`¬∃x(Ci(x) ∧ Cj(x))` is a first-class constraint, not an NAF rule. From a positive
`is_a(a, Ci)` and `disjoint(Ci, Cj)`, the engine derives `¬is_a(a, Cj)` as a strict
(classical) consequence. If both polarities are later derived, the existing
`contradiction` path reports it. Encoding disjointness as bidirectional NAF would be
a negative cycle (ASP territory) and is deliberately avoided — it is not stratified.

### 7.4 World assumption (CWA)

A per-query semantic choice, `open` (default) or `closed`:

- `open`: negated atoms match explicit negative facts only; absence is `unknown`.
- `closed`: an unprovable positive atom yields its negation by failure.

Carrier is open decision D-L1-4. The benchmark sets it; it is never read off text.

### 7.5 Stratification

Predicates are ordered by their dependencies; a negative dependency must go to a
strictly lower stratum. If no such ordering exists, the program is outside L1 and is
reported `out_of_fragment`. Granularity is open decision D-L1-2.

## 8. Engine changes (`engine/`)

- `horn.derive_closure(...)` is the single seam already used by `verify`,
  `winning_store_hit`, `frontier` and the defeasible layer. It gains the world
  assumption (and, internally, stratification).
- `horn.saturate`: evaluate NAF body literals against the running store within the
  stratified order; apply constraints to derive strict negatives.
- `_match_conditions`: add the NAF branch (a negative literal is a filter, like a
  builtin), distinct from the current "match an explicit negative fact" behavior.
- Termination: the universe stays finite; constraints are monotone; NAF evaluation
  is stratified, so the fixpoint is well-defined and bounded.
- `verify` / `answer` / `explain`: see §11.

## 9. Data model and extraction schema

- `core/models.py`: a `Constraint` model (`left`/`right` class atoms,
  kind `disjoint`), `Theory.constraints`; `Query.world_assumption`.
- `core/schemas.py`: a `StructDisjoint` shape and `ProblemStructure.disjoint` — a
  **structural** LLM output. `world_assumption` is deliberately **not** part of the
  extracted structure.
- `build/unroll.py` + `build/enrich.py`: compile `disjoint` into
  `Theory.constraints`; thread the world assumption into `Query`; keep constraints
  out of the Horn rule list so explanation/provenance stays explicit.

## 10. Phase 0 extraction (`build/extract.py`)

- `PROBLEM_SYSTEM`: teach the structural forms for negative consequents, negative
  antecedents, and disjointness sentences (e.g. "No X is a Y"), each with one
  verbatim quote; no cue-phrase lists, no word-level heuristics.
- `QUESTION_SYSTEM`: a negated yes/no question is still extracted as a positive ask;
  polarity is reconciled by the adapter (`docs/prontoqa.md` §6), as for ProofWriter.
- If recon shows disjointness is not in the surface text, no extraction is added for
  it (D-L1-1).

## 11. verify / answer / explain

- `verify`: under a declared closed world, failure to prove the target plus a
  CWA-eligible predicate yields `refuted`; the open-world behavior is unchanged.
  Constraint-derived negatives make the target `refuted` exactly as explicit
  negatives do today.
- `answer`: `refuted` maps to `no` for yes/no; CWA-based refutations are auditable in
  the verdict/trace, not silent.
- `explain`: a constraint step renders the `disjoint(Ci, Cj)` axiom and its
  `is_a` witness; a NAF step has no premises and is marked as a failure-based
  conclusion. New `ExplanationKind` value if needed.

## 12. Eval harnesses (`evals/`)

Three gates, deliberately separate. D-L1-5 = (b) with a synthetic primary.

### 12.1 Synthetic collection — **primary** (LLM-free, structural)

The public collections do not exercise constraints/NAF/CWA (§6), so our own
deterministic collection is the real gate for the new semantics.

- `evals/build_l1_synthetic.py` → `evals/data/l1_synthetic.jsonl`. Each case is a
  **structured** problem: `theory` (objects, morphisms, rules, constraints),
  `query` (conditions, target, world assumption), `expected` (status / kind /
  strength) and a `mechanism` tag. No LLM, no natural language in the primary set.
- `evals/l1_synthetic.py` — runner: builds `Theory`/`Query` directly, calls
  `verify` / `build_answer`, and reports the gate. No extraction, so zero provider
  variance.
- Coverage (~30–40 cases): constraint-derived negation, explicit negative
  consequent, NAF under declared CWA, stratification, `out_of_fragment`, and
  `contradiction`. **Negative controls are mandatory**: open world must not derive a
  CWA answer; a non-stratifiable program must be `out_of_fragment`; `disjoint` with
  only one side must yield no negative.
- Optional NL probes (a few cases through the full pipeline) live in
  `tests/test_evals_live.py`, not in the gate (LLM variance).

### 12.2 ProntoQA — L0 + explicit negation

- `evals/build_prontoqa_sample.py` — deterministic, stratified by proof shape,
  committed as `evals/data/prontoqa_tier_*.jsonl`.
- `evals/prontoqa.py` — adapter mirroring `evals/proofwriter.py`; sets
  `world_assumption` per record and reports an `out_of_fragment` bucket.
- Gates: L0 first, then L1. 0 grounded false proofs; determinate all `proven`;
  kind accuracy ≥ 95% in fragment.

### 12.3 FOLIO — **secondary** (real data, budgeted)

- Only the negation subset, as a cross-check on real text. Extraction is LLM-costly,
  so the sample is small and explicitly budgeted (§17); the synthetic gate must not
  wait on it. `docs/folio.md` has the construct stratification.

### 12.4 Defeasible parity (D)

The same structural pattern runs the currently unbenchmarked defeasible layer:
`evals/build_defeasible_synthetic.py` → `evals/data/defeasible_synthetic.jsonl` and
`evals/defeasible_synthetic.py`, exercising resolved and undecided specificity
conflicts. Separate harness and flag (`ANKYRA_DEFEASIBLE`), same gate shape.

## 13. Config and flags

- `ANKYRA_NEGATION_MODE` (`open` | `closed`, default `open`) in settings and
  `.env.example`. The benchmark overrides it per query (D-L1-4). Benchmark semantics
  never leak into the engine.

## 14. Tests

- `tests/test_engine_negation.py`: negative consequent derivation; constraint-derived
  `¬`; contradiction from both polarities; CWA target refutation; NAF strata;
  a non-stratifiable program → `out_of_fragment`; **negative guard**: closed world
  never activates on its own.
- `tests/test_build_prontoqa.py` / `tests/test_evals_prontoqa.py`: deterministic
  sample build and adapter scoring.
- `tests/test_evals_l1_synthetic.py` / `tests/test_eval_defeasible_synthetic.py`:
  the synthetic gates (structural, no LLM).
- Full regression: `uv run pytest` (offline; live tests skipped).

## 15. Documentation updates

- `docs/prontoqa.md`: recon results, subset sizes, gate numbers, L1 status.
- `docs/reasoning_roadmap.md`: L1 status and any change to the stage contract.
- `docs/implementation_plan.md`: backlog/milestones entries.
- `docs/logic_layer.md`: only if the `Inference` seam is touched (D-L1-3).
- This document, kept current as the plan evolves.

## 16. Work order (milestones)

1. ~~Recon (LLM-free) and the disjointness verdict.~~ **DONE** (§6).
2. ~~Data model, schema, builder plumbing (constraints + world assumption) with unit
   tests.~~ **DONE.**
3. ~~Constraints in the engine (disjointness and explicit negatives).~~ **DONE.**
4. ~~Stratified NAF + declared CWA behind `ANKYRA_NEGATION_MODE`.~~ **DONE.**
5. ~~Synthetic structural collection + runner (`l1_synthetic`) and the L1 gate.~~
   **DONE — 32/32 green (extended to 40/40).**
6. ~~ProntoQA builder + adapter.~~ **DONE. Live L0/L1 gates: tier a 48/48 and
   tier b 160/160 (100%), all `proven`, 0 grounded false proofs; 95% lower bound
   98.1% on tier b.**
7. ~~Defeasible synthetic collection + runner (`defeasible_synthetic`); D gate.~~
   **DONE — 8/8 green.**
8. ~~FOLIO negation subset (budgeted) as the real-data cross-check.~~ **DONE
   (offline: 13 in-fragment examples).** Pre-filter 23 → 9/23; filtered 13 → **7/13**
   (all `Uncertain` correct, no grounded mismatch). Gold-FOL diagnostic: text-fed =
   gold-fed open = 7/13, i.e. the remaining gap is the L2 fragment boundary, not
   extraction. Extraction fixes landed: bare-plural generics quantified, ground
   negatives kept, a conditional-quote soundness hole closed (finding B13).
9. ~~Extraction support for negated consequents / antecedents and disjointness
   (`build/extract.py`).~~ **DONE.**
10. Documentation and status updates. **IN PROGRESS.**

Each milestone lands reviewable on its own; no milestone starts on a red soundness
gate. Steps 2–4 are prerequisites for 5, which gates them.

**Status (engine).** Disjointness constraints, stratified negation-as-failure and the
per-query closed-world assumption are implemented and covered by the synthetic gates
(`evals.l1_synthetic` 40/40, `evals.defeasible_synthetic` 8/8, both LLM-free). The
ProntoQA L0/L1 live gates are green (tier a 48/48, tier b 160/160, all `proven`, 0
grounded false proofs). The FOLIO negation subset is built (13 in-fragment) and run
(7/13, all `Uncertain` correct, no grounded mismatch); the gold-FOL diagnostic shows
text-fed = gold-fed open, so the remaining gap is the L2 fragment boundary, not
extraction.

## 17. Budget

No free LLM access; tokens are paid out of pocket. A small committed sample
(ProofWriter Tier A order of magnitude), built deterministically without LLM calls,
run once and re-run only on a mismatch; `ANKYRA_EXTRACT_SAMPLES=1`. A full collection
is a separate, explicitly budgeted decision.

## 18. Decisions

D-L1-1 … D-L1-5 are **DECIDED**. Each entry keeps its background, options,
trade-offs and recommendation for the record. A new decision is opened here as it
arises; the plan must not proceed past a milestone affected by an open decision.

### D-L1-1 — Disjointness that is not in the surface text

**Status: DECIDED — option (a).** The harness supplies the disjointness
constraints as benchmark-provided structure; the subset tests the engine, not
extraction. The supplied constraints are marked in the trace as not extracted from
the source.

**Background.** ProntoQA makes sibling concepts disjoint (`are_children_disjoint`)
only in the generator's formal ontology. If the surface context does not state it,
Ankyra cannot extract it without a word-level heuristic, which `docs/task.md` §3.8
forbids. Recon decides whether this is the case.

**Options.**
- (a) The harness supplies the disjointness constraints as benchmark-provided
  structure. The subset then tests the **engine**, not extraction. Honest and cheap;
  the extraction gap is reported explicitly.
- (b) Drop the disjointness subset from the L1 gate, score it `out_of_fragment`, and
  gate L1 on negated properties only.
- (c) Wait for a surface-text variant that states disjointness, if one exists.

**Trade-offs.** (a) gives the strongest engine coverage but mixes harness-supplied
structure into a benchmark that is otherwise text-to-theory; (b) keeps the harness
"pure" but weakens the L1 claim; (c) is contingent.

**Recommendation.** (a) if recon confirms absence, with the supplied constraints
clearly marked in the trace.

### D-L1-2 — Stratification granularity

**Status: DECIDED — option (a).** Stratify over predicate symbols; disjointness is
a strict constraint, never NAF. Revisit (b) when L2 needs it.

**Background.** Stratification is usually over predicate symbols. Here
`is_a(X, class)` is a single predicate with the class in the object slot, so
`is_a(_, Ci)` and `is_a(_, Cj)` share a symbol; encoded as NAF, sibling disjointness
becomes a negative cycle (non-stratified).

**Options.**
- (a) Stratify over predicate symbols and handle disjointness as a strict
  constraint, never as NAF (§7.3). Simpler; keeps ordinary `is_a` intact.
- (b) Stratify over class-specialized atoms `(is_a, class)` (closer to unary FOL
  predicates). More faithful and more powerful, but a deeper change to the closure
  and to provenance.

**Trade-offs.** (a) is a smaller, safer diff and covers the L1 benchmark; (b) is more
general and may matter for L2, but adds complexity and risk now.

**Recommendation.** (a); revisit (b) when L2 needs it.

### D-L1-3 — Extract the `Inference` protocol now or later

**Status: DECIDED — option (a).** Defer the protocol refactor until functional L1 is
green; extract it afterwards as a separate, isolated change.

**Background.** `docs/logic_layer.md` §9 ties the protocol extraction to L1 landing;
the defeasible layer already landed through the `DEFEASIBLE` flag in
`derive_closure`. The project rule is minimal diff and no speculative abstraction.

**Options.**
- (a) Defer the protocol refactor until functional L1 is green, then extract it in a
  separate, isolated change.
- (b) Extract the protocol first and implement L1 as a second `Inference`.
- (c) Do not extract it at all for now; keep extending `derive_closure`.

**Trade-offs.** (a) keeps L1's diff focused and reviewable, at the cost of a later
refactor; (b) is architecturally cleaner but front-loads a large refactor before a
second semantics is proven; (c) risks the seam becoming a tangle.

**Recommendation.** (a).

### D-L1-4 — Where the world assumption lives

**Status: DECIDED — option (a).** `Query.world_assumption` (open/closed) plus the
config default `ANKYRA_NEGATION_MODE`. `Query` is not authored by the LLM, so this
does not let the model choose the world; see the clarification below.

**Background.** CWA must be an explicit, auditable semantic choice, set by the
benchmark and never guessed.

**Clarification — `Query` is not authored by the LLM.** The LLM authors
`QuestionStructure` (`core/schemas.py`); `Query` (`core/models.py`) is assembled
deterministically by `build_query` → `unroll_query_structure` → `settle_query`
(`build/pipeline.py`). A field on `Query` is therefore set by the deterministic
builder from a non-LLM source, not by the model. Three conditions make option (a)
safe: (1) the field is **not** in `QuestionStructure`; (2) the builder takes it from
config/state and never from the LLM JSON; (3) `classify._reformalize`
(`engine/classify.py`) keeps merging only `variables`, so a wave cannot alter it.
"On `Query`" means "carried by the query object for audit and for `verify`", not
"chosen by the LLM".

**Options.**
- (a) `Query.world_assumption` (open/closed) plus a config default
  `ANKYRA_NEGATION_MODE`. Per-query, visible in the trace, overridable.
- (b) Config only (`ANKYRA_NEGATION_MODE`), applied globally per run.
- (c) On `Theory` rather than `Query`.

**Trade-offs.** (a) is the most precise and auditable and lets a single run mix
problems; (b) is simplest but couples all problems in a run to one global switch and
invites leakage in tests; (c) conflates knowledge with a query-time choice.

**Recommendation.** (a).

### D-L1-5 — L1 gate scope, given that ProntoQA v1 does not exercise the new machinery

**Status: DECIDED — option (b), extended.** Build the full L1 formalism
(constraints, NAF, CWA), and gate it with a **new deterministic synthetic structural
collection** (primary; every mechanism plus negative controls, `evals/l1_synthetic`),
with the **FOLIO negation subset** as a budgeted real-data cross-check. ProntoQA v1
stays the L0 + explicit-negation gate. The same harness pattern is applied to the
defeasible layer (D), which is likewise unbenchmarked.

**Background.** Recon (§6) shows the public L1 subset is explicit negated-property
rules, already engine-supported; disjointness, NAF and CWA are not exercised. The
project rule forbids speculative machinery — but a deterministic synthetic gate that
fails without the new semantics removes the speculation.

**Options.**
- (a) Gate L1 on explicit negation with ProntoQA v1, defer
  constraints/NAF/CWA. Smallest step, leaves the roadmap's L1 unbuilt.
- (b) Build the full L1 and gate it with a synthetic collection (+ FOLIO), so the
  machinery is exercised and falsifiable.
- (c) Change the gate to a source that exercises NAF/CWA before writing engine code.

**Trade-offs.** (a) minimal but incomplete; (b) matches the roadmap contract and,
unlike naive (b), is not unbenchmarked thanks to the synthetic gate — at the cost of
building our own collection; (c) needs a suitable benchmark first.

**Recommendation / decision.** (b), with the synthetic gate primary and FOLIO
secondary (D-L1-5). The risk of testing to our own implementation is mitigated by
independently written expected verdicts and mandatory negative controls.
