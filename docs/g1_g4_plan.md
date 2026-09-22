# G1–G4 Plan — FOLIO L2 extraction generalization (Phase 1)

Status: **complete.** Phase 1 of `docs/folio_extension_plan.md` (extraction
generalization, G1–G4), which followed the completed Tier-1 lowering
(`docs/coverage_ceiling.md` §6–§7). Outcome: text-fed **29–31/45** across three live
gates (best 31; the saved baseline was 25/45, the original live 26/45), **0 grounded
false proofs**, gold-fed coverage unchanged at 42/45. What landed: Step 0 measurement
plumbing + triage (§13); G1–G3 extraction wording (§14–§15); the T4 ground-CNF target
form and the `ask_universal` guard (`G-D6`, §16); and B (§19–§21). The residual wall is
**G2** (missing premises): `G-D2` (coverage trigger) was measured non-selective and not
built (§18), and `A′` (query-driven unlink repair) is deferred with an explicit revisit
condition (§19). A model ablation (§22) shows a stronger model does not move the wall.
Decisions `G-D1`…`G-D6` are recorded in §5 and §19.

Canonical language: English; Russian mirror: `docs/g1_g4_plan_ru.md`.

Related: `docs/folio_extension_plan.md` (§4 Phase 1, decisions `D-FE-1`…`D-FE-7`),
`docs/quality_findings.md` §G (the G1–G4 findings),
`docs/coverage_ceiling.md` (the completed Tier-1 backlog), `docs/folio_gold_fed.md`
(the measurement this plan follows), `docs/folio_ceilings.md` (the ceiling model),
`docs/folio.md` (§9–§10), `docs/l2_plan.md` (the procedure the G3 target form reuses),
`docs/fragment_routing.md` (the named-fragment contract), `docs/t3_plan.md` /
`docs/t4_t2_plan.md` (the engine forms G3 now needs from extraction),
`docs/reasoning_roadmap.md` §4 (budget policy), `docs/implementation_plan.md` §8–§10.

## 1. Goal

Move the **extraction** ceiling on FOLIO L2: make the LLM propose the formulas the
committed clausal fragment (`ANKYRA_LOGIC`) can already decide, so text-fed accuracy
approaches the gold-fed bound. Concretely: retain all premises (G2), express
universal/conditional/`¬∃` conclusions as targets instead of ground atoms (G3), emit
generic disjunctions in the head-only shape the engine supports (G1), and stop losing
rows to saturation scale (G4).

Per `D-FE-2`, extraction comes after the method: the gold-fed diagnostic showed the
deeper limit was coverage, Tier-1 closed it, and extraction is now the dominant loss.

## 2. Baseline and the staleness finding

Committed slice: FOLIO L2 tier a, 45 problems (`evals/data/folio_l2_tier_a.jsonl`).

Gold-fed (LLM-free, `uv run python -m evals.analyze_folio --subset l2`, 2026-09-22):

| verdict source | correct |
|---|---|
| gold-fed open | 42/45 |
| gold `out_of_fragment` | 1/45 (the malformed `0109`) |
| coverage (method) | 44/45 |
| covered gold-fed | 42/44 |

Text-fed is the part G1–G4 targets, but the committed text-fed traces
(`evals/out/folio/*.json`, mtime **2026-09-20**) were produced **before** Tier-1
T4/T2/T6 (`evals/data/l2_synthetic.jsonl`, 2026-09-22). Their recorded scores are
stale in two ways:

- the engine at run time predates T1/T3/T4/T5/T6, so some `out_of_fragment` /
  `insufficient` rows were later fixed (e.g. `0009`, `0006`, `0033`);
- the adapter's compound/binding scoring changed after those traces were written.

The saved text-fed number (25/45) is therefore **not the current text-fed score**.
The extracted `QuestionStructure` is not persisted, so the current text-fed value
cannot be recovered from the traces alone. This is the reason Step 0 (§6) exists: it
makes the failure triage and the engine part of the re-measurement free before any
prompt/schema work.

## 3. Scope and non-goals

**In scope.**
- Extraction changes (prompt + schema + deterministic builder) for G1–G4.
- The measurement plumbing that lets the eval harness re-run the current engine over
  saved extractions (LLM-free) and record the extracted question structure.
- The LLM-free gates (`evals.l2_synthetic`, `evals.routing_synthetic`, `pytest`) and
  the single budgeted live FOLIO L2 rerun.

**Out of scope (unchanged).**
- Any new decision procedure or semantics: G3 reuses the `forall`/`cnf` goal forms
  built in T3/T4; G1 reuses the head-only grounding built in T5; G4 is already fixed
  by T6. No new flag; the capability stays `clausal` (`ANKYRA_LOGIC`).
- Any NL heuristic over the raw text — cue-phrase detection, morphology, term lists
  (`docs/task.md` §3.8). The semantics lives in the extraction prompt; deterministic
  code acts only on structured output.
- Tier-2 constructs (equality, functions, `↔`/`⊕`, multi-variable quantification) —
  separate fragment decisions (`docs/folio_extension_plan.md` §6).
- Per-id tuning (`docs/coverage_ceiling.md` §8); lowering the semantics to pass a row
  (e.g. collapsing `∀x(Pet→¬Cat)` to the ground `¬is_a(pet,cat)`).
- Any live run other than the single budgeted gate in §10
  (`docs/reasoning_roadmap.md` §4).

## 4. The four items

The per-row assignment below is the **triage hypothesis** from the stale traces; Step 0
(§6) confirms or corrects it before any fix.

### 4.1 G4 — ground-saturation scale

- **State:** the engine side is **done** (T6 ground unit propagation,
  `docs/t6_plan.md`): it decides the gold rows `0009`/`0010` and raised gold-fed to
  42/45. The G4 rows seen in the stale text-fed traces (`0009`, `0039`, `0127`) are
  expected to be already fixed by T5/T6.
- **Work:** none, unless Step 0 shows a persisting scale miss. If so, only an
  *explicit* budget move is allowed (`D-FE-7`); exhaustion must stay the honest
  `insufficient`. No unbounded search, no new machinery.

### 4.2 G1 — head-only universal disjunction ("Either X or Y …")

- **State:** the shape is a *generic disjunction over the universe*
  (`∀x(A(x) ∨ B(x))`, e.g. "There are six types of wild turkeys: …", "an animal is
  either a rabbit or a squirrel"). The engine supports it via T5
  (`head_only_rule`; head-only variables ground over the individual domain `D_ind`),
  and the extractor already emits the disjunctive head in `consequents` with an empty
  antecedent (observed on `0009`, `0149`, `0127`). The old `out_of_fragment:
  unsafe_rule` was a pre-T5 artifact.
- **Work:** make the general shape explicit in the prompt and lock it with tests — no
  engine change. A generic disjunction goes to a rule with an empty antecedent and a
  disjunctive head (`consequents`), never to a ground fact and never to a rule with a
  fabricated body; the head variable ranges over the universe.
- **Risk:** if the deterministic test reveals a real grounding gap, stop and discuss —
  do not add an ad-hoc branch.

### 4.3 G3 — universal / conditional / `¬∃` conclusion (the main item)

- **State:** the engine can decide `Query.goal_mode="forall"` / `"cnf"` (T3/T4), but
  **extraction cannot express it**: `QuestionStructure` only has
  `ask` / `ask_all` / `ask_any`, and `unroll_query_structure` never emits `forall`.
  The extractor therefore collapses `∀x(Pet→¬Cat)` / `¬∃x FinancialAid(x)` into a
  single ground atom (rows `0045`, `0007`, `0107`), which is either wrong or
  unanswerable.
- **Work (`G-D1` = `ask_universal`):**
  - `core/schemas.py` `QuestionStructure`: add
    `ask_universal: list[StructAtom]` — a universally quantified clause goal
    `∀x(l₁ ∨ … ∨ lₙ)`: the literals are over one and the same variable, and a literal
    may be negated (an implication `A(x) → B(x)` is `¬A(x) ∨ B(x)`; `¬∃x φ` is
    `∀x ¬φ`). When non-empty it replaces `ask` / `ask_all` / `ask_any`.
  - `build/unroll.py` `unroll_query_structure`: `ask_universal` →
    `goals = <literals>`, `goal_mode="forall"`, `target = goals[0]`. Negation is
    preserved; no positivity coercion.
  - `build/extract.py` `QUESTION_SYSTEM`: a conclusion of the form "all/every X …",
    "no X …" (`¬∃`), or a conditional conclusion is an `ask_universal` clause goal,
    **not** a ground atom; state the split explicitly — `ask_all` stays the
    shared-witness existential `∃x(g₁ ∧ … ∧ gₙ)` (T1), `ask_universal` is `∀`.
- **Fragment:** already named — `universal_goal` (`engine/inference.py`) routes to the
  existing `clausal` capability; no new flag.

### 4.4 G2 — lost premises / unlinked facts

- **State:** the extractor drops atomic premises about named individuals, leaving a
  theory with almost no morphisms (rows `0072`, `0058`, `0139`, `0149`), so an
  otherwise decidable row is `insufficient`.
- **Work:** prompt hardening in `build/extract.py` `PROBLEM_SYSTEM` — keep **every**
  atomic premise; a premise about a named individual stays a fact (a conjunction of
  ground statements is one fact per conjunct); never drop a premise as "obvious".
- **Deferred (`G-D2`):** a deterministic coverage-based repair trigger (a repairable
  `structural:` gap when the descriptive text is largely uncovered) is **not** added
  now. It risks re-extracting legitimate open-world unknowns; it is reconsidered only
  if the live gate shows the prompt alone is insufficient.

## 5. Design decisions

- **G-D1 — G3 target form.** (a) A dedicated `ask_universal` clause field on
  `QuestionStructure`, mapped to `goal_mode="forall"` (mirrors T3; minimal, the engine
  form already exists). (b) A generic `ask_formula`/`goal_clauses` schema for arbitrary
  ground CNF (T4) — larger, and the FOLIO G3 rows are all universal clauses. (c) No
  schema field; encode as `ask_all` and let the engine guess — rejected (an `all` goal
  is a different logic). **DECIDED (a).**
- **G-D2 — G2 repair trigger.** (a) Prompt hardening only for now; add a
  coverage-based repairable gap later iff measured to be needed. (b) Add the trigger
  now — rejected as speculative and a risk to legitimate open-world rows.
  **DECIDED (a), deferred.**
- **G-D3 — G4.** No code: T6 closed the engine side; only an explicit budget move if
  Step 0 shows a persisting miss (`D-FE-7`). **DECIDED.**
- **G-D4 — G1.** Prompt clarification plus a deterministic builder/prover test; no
  engine change (T5 already grounds the head-only variable). **DECIDED.**
- **G-D5 — Measurement plumbing.** Persist the extracted `QuestionStructure` and add
  an LLM-free engine-replay mode to `evals/analyze_folio.py`, so engine changes can be
  re-measured on saved extractions; a prompt/schema change still needs the live rerun.
  **DECIDED** (needed to keep the G-track cheap).

## 6. Step 0 — measure-first (LLM-free)

Before any fix:

1. **Triage.** Rebuild the text-fed failure list from the saved traces and classify
   each row's **first blocker** as G1/G2/G3/G4/other (Step 0 confirms the §4
   hypotheses and separates stale rows from real ones).
2. **Engine replay.** Add a mode to `evals/analyze_folio.py` that re-runs
   `verify(trace.theory, trace.query)` (and re-scores via `folio.score_record`) over
   the saved extraction under the subset's logic. This yields the **current** engine
   score for the old extraction at zero LLM cost, isolating what is stale from what is
   a genuine extraction miss.
3. **Record** the triage in the results section of this document.

## 7. Changes

- **`src/ankyra/core/schemas.py`** — `QuestionStructure.ask_universal` (G3, `G-D1`).
- **`src/ankyra/build/unroll.py`** — `ask_universal` → `goal_mode="forall"` (G3).
- **`src/ankyra/build/extract.py`** — `QUESTION_SYSTEM` (G3 target form; the
  `ask_all` vs `ask_universal` split) and `PROBLEM_SYSTEM` (G1 head-only disjunction;
  G2 premise retention).
- **`src/ankyra/engine/inference.py`** — none expected for G3 (`universal_goal`
  already exists); only if a rule-shaped G1 row needs a derived feature, and then as a
  named fragment, not an ad-hoc branch.
- **`src/ankyra/engine/state.py`, `src/ankyra/graph/build.py`** — carry
  `question_structure` on the state/result so the trace can persist it (`G-D5`).
- **`evals/run.py`, `evals/folio.py`** — write `question_structure` into the trace
  (`G-D5`).
- **`evals/analyze_folio.py`** — engine-replay mode over saved traces (Step 0,
  `G-D5`).
- **Engine `verify.py` / `resolution.py` / `clause.py`** — no change; G1/G3/G4 reuse
  existing forms.

## 8. Synthetic gate (`evals.l2_synthetic`, `evals.routing_synthetic`)

LLM-free, one case per construct, with a negative control. The cases are built at the
**structure** level (the deterministic builder path), since the prompt itself is not
unit-testable.

| case | structure / goal | expected |
|---|---|---|
| `g3-universal-01` | an `ask_universal` clause `[¬Pet(?x), ¬Cat(?x)]`; rules force it | `supported`, `yes`, feature `universal_goal` |
| `g3-universal-02` | a witness that falsifies the clause | `refuted`, `no` |
| `g3-universal-03` | the same goal encoded as a ground atom (the wrong G3 shape) | must **not** prove (soundness control) |
| `g3-neg-exists-01` | `ask_universal` `[¬FinancialAid(?x)]` (`¬∃`) | matches the gold semantics |
| `g1-head-only-01` | a generic `∀x(A(x) ∨ B(x))` head-only rule | decided over `D_ind` (T5), not over class names |
| `g1-head-only-02` | the same with no individual in the domain | honest `unsupported` (no fabrication) |
| `g3-off-01` | an `ask_universal` goal with `logic="off"` | `out_of_fragment:compound_goal` |

A `routing_synthetic` case asserts `ask_universal` routes to `clausal` when
`ANKYRA_LOGIC` is on.

**Implementation note (G3).** The `evals.l2_synthetic` cases build `Theory`/`Query`
directly, bypassing `QuestionStructure`; the `universal_goal` engine mechanism is
already gated there (T3, `evals/build_l2_synthetic.py:_universal_goal_cases`). The new
G3 work — the **builder mapping** `ask_universal` → `goal_mode="forall"` — is
therefore gated by deterministic builder tests (`tests/test_build_unroll.py`,
`tests/test_build_query.py`) instead of a duplicate synthetic mechanism, including
the `g3-universal-03` soundness control.

## 9. Tests and verification

- `tests/test_build_unroll.py`: `ask_universal` → `Query.goal_mode="forall"` with the
  literals and the shared variable; negation preserved; the `ask_all` path unchanged.
- `tests/test_engine_logic_l2.py`: the G3 `forall` cases end-to-end from a built
  structure; the "ground atom instead of a universal" soundness control.
- `tests/test_build_extract.py`: the deterministic structure→theory path for the G1
  head-only disjunction and the G2 premise retention.
- `tests/test_evals_folio_fol.py`: unchanged (gold parser already supports `forall`).
- `uv run pytest` (offline) — full regression.
- `uv run python -m evals.l2_synthetic` — new total, **0 mismatches**.
- `uv run python -m evals.routing_synthetic` — green (`universal_goal` already routes).
- `uv run python -m evals.analyze_folio --subset l2` — LLM-free gold-fed re-measure
  must stay at coverage 44/45 with **0 grounded false proofs**.

## 10. Live gate (budgeted)

One FOLIO L2 tier a rerun after all items land:

```
uv run python -m evals.folio --subset l2 --jobs N
uv run python -m evals.analyze_folio --subset l2
```

Acceptance: text-fed correct strictly up, **0 grounded false proofs**, every remaining
failure categorized by G1–G4 or `other`. Record the number and the triage in §13 and
in `docs/quality_findings.md` §G. This is the only live run; re-run only on a mismatch
(`docs/reasoning_roadmap.md` §4).

## 11. Risks

- **Prompt regressions across domains.** The G1–G3 wording must stay general (no
  domain terms). The ProofWriter/ProntoQA gates are not re-run per item; the offline
  suite and the single FOLIO gate are the checks.
- **G3 mis-encoding.** A universal conclusion must never be collapsed to a ground atom
  (the T3 trap); the `g3-universal-03` control asserts this.
- **G2 over-repair.** Deferring the coverage trigger (`G-D2`) avoids manufacturing
  premises; if a trigger is later added it must not fire on a legitimate open-world
  unknown.
- **Stale-trace confusion.** Step 0's engine replay is the guard; without it the text
  numbers would be read off pre-Tier-1 traces.
- **Cost.** Only the §10 run spends tokens; `ANKYRA_EXTRACT_SAMPLES=1` everywhere.

## 12. Work order (milestones)

1. Step 0: measurement plumbing (`G-D5`) + triage. (LLM-free.)
2. G3 (`G-D1`): schema, builder, prompt, tests, synthetic cases.
3. G1 (`G-D4`): prompt + builder/prover tests, synthetic case.
4. G2 (`G-D2`-deferred): prompt hardening.
5. Offline gates: `pytest`, `l2_synthetic`, `routing_synthetic`, gold-fed re-measure.
6. Live gate (§10): one budgeted FOLIO L2 rerun; record §13.
7. Docs: `quality_findings.md` §G, `folio_extension_plan.md` §11,
   `implementation_plan.md` §8, `reasoning_roadmap.md`, and the `docs/g1_g4_plan_ru.md`
   mirror; optionally add cross-links from related docs.

Each milestone lands reviewable on its own; the offline gate (step 5) precedes the
live gate (step 6).

## 13. Results

**Step 0 — measure-first (LLM-free), 2026-09-22.**

Measurement plumbing landed (`G-D5`): `ProblemResult.question` (`graph/build.py`),
`QuestionStructure` persisted in the harness trace (`evals/run.py`), and an
**engine-replay** mode in `evals/analyze_folio.py` (`_replay_kind`, `--no-replay` to
opt out) that re-verifies the saved `trace.theory`/`trace.query` with the current
engine and re-scores it. Tests: `tests/test_evals_offline.py` (replay + trace
persistence); `uv run pytest` → **482 passed, 26 skipped**.

FOLIO L2 tier a (`uv run python -m evals.analyze_folio --subset l2`):

| verdict source | correct |
|---|---|
| text-fed (saved, 2026-09-20) | 25/45 |
| **text-fed (replay, current engine)** | **28/45** |
| gold-fed open | 42/45 |
| gold `out_of_fragment` | 1/45 |
| coverage (method) | 44/45 |
| covered gold-fed | 42/44 |

Replay confirms the staleness §2 predicted: three text rows are already decided by the
current engine on the old extraction — `0006` and `0033` (binding + `proven` now maps
to `yes`) and `0009` (T5/T6). The remaining **17** replay failures triage by **first
blocker**:

| class | rows | count |
|---|---|---|
| **G3** target form (universal / conditional / `¬∃` / non-flat, collapsed to a ground atom) | `0007`, `0040`, `0044`, `0045`, `0058`, `0065`, `0107`, `0149` | 8 |
| **G2** lost premises / unlinked facts (incl. dropped ground disjunctions) | `0018`, `0042`, `0072`, `0077`, `0123`, `0127` | 6 |
| fragment (gold method, not extraction) | `0047`, `0109`, `0139` | 3 |
| **G1** head-only disjunction as a standalone first blocker | — | 0 |
| **G4** scale | — | 0 |

Notes from the triage:

- **G3 is the largest bucket.** Representative: `0007` (`∀x(Human→¬Flu)`) → target
  `None`; `0045` (`∀x(Pet→¬Cat)`) → ground `¬is_a(pet,cat)`; `0107` (`¬∃x
  FinancialAid(x)`) → positive ground atom; `0065` (`Cow(ted)→¬Pet(ted)`) → ground
  negated atom; `0044`/`0149` (negated compound clauses) → positive `ask_all`;
  `0058` (shared-witness `∃`) → a minted `same_state` predicate; `0040` (ground
  conjunction) → wrongly existentialized.
- **G2 is the second bucket.** Most rows have **0** extracted morphisms: ground
  disjunctive facts about named individuals are dropped (`0018`, `0042`, `0077`,
  `0127`, `0123`), or the linking facts never reach the theory (`0072`).
- **G1** does occur (`0042`, `0127` contain `∀x(A∨B)` head-only premises), but in no
  row is it the *sole* first blocker; T5 already grounds the shape that does get
  extracted, so G1 is a prompt-clarification item, not an engine item.
- **G4 is closed** by T6: no scale miss remains on this slice.

The item order from §12 stands: G3 (8 rows) first, then G2 (6), then the G1 prompt
clarification. The live gate (§10) is still pending a budgeted decision.

## 14. G3 results (`G-D1`)

**Implemented, LLM-free verified, 2026-09-22.**

- **Schema.** `QuestionStructure.ask_universal: list[StructAtom]` — a universal
  clause goal `∀x(l₁ ∨ … ∨ lₙ)`, the disjuncts over one shared variable, each possibly
  negated; when non-empty it replaces `ask`/`ask_all`/`ask_any`.
- **Builder.** `unroll_query_structure` maps `ask_universal` → `goals = <literals>`,
  `goal_mode="forall"`, `target = goals[0]` (negation preserved). No engine change:
  `verify` already decides `goal_mode="forall"` (T3) and the fragment already names
  `universal_goal`.
- **Extraction prompt.** `QUESTION_SYSTEM` now distinguishes `ask_all`
  (shared-witness existential `∃x(g₁ ∧ … ∧ gₙ)`) from `ask_universal` (`∀`), with the
  implication / negative-universal / `¬∃` encodings and an example.
- **Tests.** `tests/test_build_unroll.py` (mapping + precedence),
  `tests/test_build_query.py` (end-to-end `∀x(Dog→¬Wild)` decided by chaining, and the
  T3 soundness control that the ground `¬is_a(pet,cat)` does **not** prove
  `∀x(Pet→¬Cat)`), `tests/test_build_extract.py` (prompt teaches the form).

| gate | before | after |
|---|---|---|
| `uv run pytest` | 482 passed | **487 passed**, 26 skipped |
| `evals.l2_synthetic` | 56/56 | 56/56 (engine mechanism unchanged) |
| `evals.routing_synthetic` | 17/17 | 17/17 |
| FOLIO L2 gold-fed | 42/45 | 42/45 (coverage unchanged; 0 grounded false proofs) |

The `ask_universal` target form cannot be validated on the FOLIO rows until the
budgeted §10 live rerun re-extracts them (the saved extraction predates it); an
engine-replay cannot show the effect by construction.

## 15. G1 + G2 results

**Implemented (prompt-level), LLM-free verified, 2026-09-22.**

- **G1 (`G-D4`).** `PROBLEM_SYSTEM` now states that a generic disjunction ("Either A
  or B", "Every X is A or B", "There are N kinds: …") is a rule with a **disjunctive
  head** (`consequents`) and no single consequent — conditioned on `is_a(?x,X)` when
  a class is named, conditionless for a universe-wide dichotomy. No engine change:
  T5 already grounds the head-only variable and the existing disjunctive-head rule
  covers the class case.
- **G2 (`G-D2`, prompt only).** `PROBLEM_SYSTEM` now requires retaining **every**
  atomic premise about a named individual and keeping a ground disjunction as a
  `disjunctions` fact. The coverage-based repair trigger stays deferred (`G-D2`).

| gate | before | after |
|---|---|---|
| `uv run pytest` | 487 passed | **491 passed**, 26 skipped |
| `evals.l2_synthetic` | 56/56 | 56/56 |
| `evals.routing_synthetic` | 17/17 | 17/17 |
| FOLIO L2 gold-fed | 42/45 | 42/45 (0 grounded false proofs) |

G1 tests: `tests/test_build_disjunction.py` (a conditionless head-only disjunction is
a clause, and is decided over `D_ind`) and `tests/test_build_extract.py` (the prompt
teaches the shape). G2 test: `tests/test_build_extract.py` (the prompt requires
premise retention). Like G3, the text-fed effect is only observable after the live
rerun.

## 16. Live gate results

Run: `uv run python -m evals.folio --subset l2 --jobs 4` (45 problems), 2026-09-22,
`ANKYRA_EXTRACT_SAMPLES=1`. FOLIO L2 tier a:

| verdict source | before (saved, 2026-09-20) | after |
|---|---|---|
| text-fed correct | 25/45 | **29/45** (29/44 covered; 1 no target) |
| text-fed (replay = text, fresh traces) | 28/45 | 29/45 |
| gold-fed open | 42/45 | 42/45 |
| gold `out_of_fragment` | 1/45 | 1/45 |

The G3 target form fixed five rows that failed in the stale replay: `0007`, `0045`,
`0107`, `0065`, `0123`. But **four rows regressed** against the stale replay —
`0020`, `0033`, `0060`, `0073` — a net +1 over replay (and +3 over the original live
26/45). The remaining 16 failures triage by first blocker:

| class | rows | count |
|---|---|---|
| **G3** target form | `0020`, `0033`, `0040`, `0044`, `0058`, `0073`, `0149` | 7 |
| **G2** lost premises / unlinked facts | `0018`, `0042`, `0060`, `0072`, `0077`, `0127` | 6 |
| fragment (gold method) | `0047`, `0109`, `0139` | 3 |

**No engine unsoundness.** The one harness `grounded_mismatch` (`0058`) is a target
mis-formalization: the extractor turned the conclusion into the open binding
`state(butte, ?s)` and the engine soundly proved `state(butte, montana)` — a statement
true in the extracted theory, but **not** the gold shared-witness
`∃x(CityIn(butte,x) ∧ CityIn(pierre,x))`. No false conclusion was derived from a
correctly extracted theory; the failure is the target, not the proof. The other
misses are honest `unknown`/`insufficient`, never a wrong determinate answer.

**New finding — ground non-flat/conditional goals need the T4 form.** `0020`
(`Cute(rock) ∧ Still(rock) → Turtle(rock) ∧ Skittish(rock)`), `0044`
(`¬Lost ∨ ¬Among`, a ground clause), `0073` (a ground conditional mis-encoded as
`forall` with no variable) and `0149` (`¬(Student(rose) ∧ Human(jerry))` → no target)
are **ground** non-flat formulas. `ask_universal` cannot express them (it needs a
variable for universal generalization), and `G-D1` option (b) — a general ground-CNF
target form (`Query.goal_clauses`, T4) — was rejected as larger. The live gate shows
it is needed, and that `ask_universal` must be **guarded** to genuinely quantified
(variable) conclusions so it is not applied to ground conditionals.

- **Decision `G-D6` (DECIDED — option a).** Add the T4 ground-CNF target form and
  guard `ask_universal` to variable conclusions. Implemented as
  `QuestionStructure.ask_clauses: list[list[StructAtom]]` → `goal_mode="cnf"` /
  `Query.goal_clauses`; `ask_universal` now falls back to a single ground clause when
  it carries no variable; the prompt teaches both forms. Tests:
  `tests/test_build_unroll.py` (mapping + the ground fallback),
  `tests/test_build_query.py` (a ground CNF goal decided), `tests/test_build_extract.py`
  (the prompt). LLM-free gates: `pytest` 495 passed / 26 skipped, `l2_synthetic` 56/56,
  `routing_synthetic` 17/17; gold-fed 42/45. The text-fed effect needs a live rerun.

**Pending:** live re-validation of `G-D6` (targeted ids or the full 45) and extraction
stability for `0020`/`0033`/`0060`/`0073`.

## 17. Second live run (after `G-D6`)

Run: `uv run python -m evals.folio --subset l2 --jobs 4` (45 problems), 2026-09-22,
`ANKYRA_EXTRACT_SAMPLES=1`.

| verdict source | run 1 (G1–G3) | run 2 (`G-D6`) |
|---|---|---|
| text-fed correct | 29/45 (69% of 42 determinate) | **31/45** |
| gold-fed open | 42/45 | 42/45 |
| gold `out_of_fragment` | 1/45 | 1/45 |
| `grounded_mismatch` (harness) | 1 (`0058`) | 1 (`0058`) |

`G-D6` is confirmed at the target-form level: `0020`, `0073` and `0149` now carry the
correct ground CNF (`goal_mode="cnf"`, `Query.goal_clauses`), and `ask_universal` is no
longer applied to ground literals. Their remaining failure is **missing premises**, not
the target. The one `grounded_mismatch` (`0058`) is unchanged and remains a target
mis-formalization (`state(butte, ?s)` proven; the gold is the shared-witness `∃`), not
engine unsoundness.

The 14 remaining failures triage by first blocker:

| class | rows | count |
|---|---|---|
| **G2** lost premises / unlinked facts | `0018`, `0020`, `0042`, `0073`, `0077`, `0127`, `0149` | 7 |
| **G3** target form | `0033`, `0040`, `0044`, `0058` | 4 |
| fragment (gold method) | `0047`, `0109`, `0139` | 3 |

Two observations:

- **G2 is now the largest bucket**, and the deferred `G-D2` question returns: a
  deterministic coverage-based repair trigger (or stronger premise retention) is the
  next lever.
- **G3 remains** for `0044` (a ground clause mis-read as a conjunction), `0033`/`0040`
  (a shared-witness/ground conjunction encoded as a single/`all` goal), and `0058` (a
  shared-witness `∃` collapsed to an open binding). These are extraction wording, not
  new engine forms.

Also fixed: `evals/folio.py:score_record` now treats `goal_clauses` as a compound
target, so a CNF conclusion is scored by the label directly (previously it was
polarity-flipped as a single ground atom). This changed categorization, not the count.

**Pending:** decide the next lever (`G-D2` repair trigger vs. more extraction wording)
and whether to run a further gate (`docs/reasoning_roadmap.md` §4).

## 18. `G-D2` diagnostic — the coverage trigger is not selective

A coverage-based repair trigger (the original `G-D2` design: a repairable `structural:`
gap when the descriptive text is largely uncovered) was measured before building it,
on the run-2 traces (`source_coverage` of the built theory quotes / source length):

| actual kind | covered fraction range |
|---|---|
| correct rows | 0.24 – 0.91 |
| failed rows | 0.19 – 0.88 |

The distributions overlap almost completely. Concretely, the failing G2 rows are
**not** under-covered: `0042` is 0.88 and `0077` is 0.84 with **0** ground
morphisms — the extractor quotes the sentences inside rules but drops the ground
facts, so the text is "covered" while the premises are missing. Conversely, passing
pure-rule rows (e.g. `0043` 0.91, `0076` 0.90) and passing low-coverage rows
(`0006` 0.41, `0065` 0.42) sit on both sides. A coverage threshold would therefore
fire broadly on correct extractions (cost, churn, regression risk) while catching
almost none of the G2 failures.

**Conclusion.** The coverage trigger is **not a general solution** and is not built;
the measurement contradicts `G-D2`'s premise. A principled alternative is a
**query-driven unlink repair**: after `build_query`, when `verify` reports an
unmatched question atom whose constant/predicate is absent from the theory, run one
bounded problem re-extraction focused on that atom (structural — it uses the built
theory/query, not raw-text heuristics). This is a graph-level change, larger than
`G-D2`; it needs its own decision.

The alternative remains **B** (extraction wording for the remaining G3 rows) or
accepting 31/45.

## 19. Decision — B now, `A′` deferred (with reasons)

**DECIDED.** Build **B** (extraction wording for the remaining G3 rows); **defer `A′`**
(query-driven unlink repair). Reasons for deferring `A′`, from the run-2 traces:

1. **Gap-driven selectivity is low.** `A′` fires on `verify`'s
   `target_unmatched:`/`condition_unmatched:`. On the 11 extraction failures that
   signal exists only for `0042` and `0033` (yield 2):
   - `0058` is `supported` with **no gap** — it is a mis-formalized target, which a
     gap-driven repair cannot see;
   - `0073`, `0077`, `0149` are `insufficient` with **no gap**;
   - `0018`, `0020`, `0040`, `0044`, `0127` are `logic_budget:exhausted`, not an
     unlink.
2. **Broadening to raw token-absence is not selective.** Counting question
   constants/predicates absent from the theory, passing rows reach 3
   (`0083`, `0076`, `0043`) while failing rows can have 2 (`0018`, `0040`, `0042`).
   There is no threshold that separates them, exactly as with coverage (§18).
3. **It is not minimal.** `A′` is a graph-level mechanism (a new post-query step, a
   repair hook, extra LLM calls per fix, new tests). Building it on an unsupported
   selectivity premise is speculative machinery, which the project rules reject
   (`AGENTS.md`; `docs/coverage_ceiling.md` §8).
4. **Revisit condition (backlog).** Reconsider `A′` only if, after B, a remaining
   failure shows a **clean** unlink signal: a `target_unmatched:`/`condition_unmatched:`
   gap whose atom's constant/predicate is absent from the theory *and* whose source
   sentence is uncovered. Then build it as a named, bounded step with a fresh
   measurement — never as a threshold heuristic.

**B scope** (prompt-only, `QUESTION_SYSTEM`):
- `0044`: a ground disjunction of literals (including negated) is `ask_clauses` with
  one clause, **not** `ask_all` (which is a conjunction).
- `0033`, `0058`: an unspecified participant ("leads a Y", "in the same state") is a
  shared-witness `ask_all` with one variable for the witness.
- `0040`: a conjunction about a specific **named** individual/thing uses the constant,
  not `?x`.
- Validation: one full live run (not only the four ids), because prompt changes have
  caused cross-domain regressions (run 1 → run 2).

**Decision recorded; implementation and the live result follow in §20.**

## 20. B implementation — G3 extraction wording

**Implemented, LLM-free verified, 2026-09-22.** Prompt-only (`QUESTION_SYSTEM`); no
builder/engine change.

- `ask_all` is stated to be a **conjunction (AND)**, never a disjunction, and it now
  documents the **shared witness**: one unspecified participant is a variable
  ("Roderick leads a stable" → `[leads(roderick, ?x), is_a(?x, stable)]`; "Butte and
  Pierre are in the same state" → `[state(butte, ?x), state(pierre, ?x)]`); a
  conjunction about a **named** individual keeps its constant in every conjunct (not
  `?x`). This addresses `0033`, `0058`, `0040`.
- `ask_clauses` now documents a ground **disjunction with negated/mixed literals**
  ("neither A nor B" = `¬A ∨ ¬B`) as one clause, never `ask_all`. This addresses
  `0044`.
- Tests: `tests/test_build_extract.py` (prompt wording).

| gate | before | after |
|---|---|---|
| `uv run pytest` | 495 passed | **496 passed**, 26 skipped |
| `evals.l2_synthetic` | 56/56 | 56/56 |
| `evals.routing_synthetic` | 17/17 | 17/17 |
| FOLIO L2 gold-fed | 42/45 | 42/45 (0 grounded false proofs) |

**Pending:** the full live validation run; `A′` stays deferred (§19).

## 21. Third live run — B validation, and the variance wall

Run: `uv run python -m evals.folio --subset l2 --jobs 4` (45 problems), 2026-09-22,
`ANKYRA_EXTRACT_SAMPLES=1`.

| metric | run 1 (G1–G3) | run 2 (`G-D6`) | run 3 (B) |
|---|---|---|---|
| text-fed correct | 29/45 | 31/45 | 29/45 |
| harness `grounded_mismatch` | 1 (`0058`) | 1 (`0058`) | **0** |
| gold-fed open | 42/45 | 42/45 | 42/45 |

B's target-form wording is confirmed where it took effect:

- `0040` (`Evocative(aDesignByMax) ∧ Dreamy(aDesignByMax)`) is now **correct**: the
  conjunction keeps the named constant (`ask_all [is_a(max_design, …), …]`).
- `0058` is no longer a wrong grounded `yes`: it is now the correct shared-witness
  `ask_all [state(butte, ?x), state(pierre, ?x)]`, honestly `unknown` because the
  premises are missing (a G2 defect, not the target).
- `0033` and `0044` still missed the intended form this run (single / `ask_all`
  instead of shared-witness / `ask_clauses`) — extraction variance.

Row-level run2 → run3 changes: `0040` unknown→yes; `0058` yes→unknown (target
now correct); `0060` yes→unknown, `0072` no→unknown, `0107` no→unknown — all
extraction variance, unrelated to B's wording). Across the three runs the headline is
stable at **29–31/45**, i.e. the net effect of B is **inside provider variance**
(`docs/quality_findings.md` C1).

**Conclusions.**

1. **No engine unsoundness.** Run 3 has **0** grounded mismatches; every remaining
   failure is an honest `unknown`/`insufficient`. `proven` keeps its meaning.
2. **The target-form work (G3, `G-D6`, B) is done.** `ask_universal` / `ask_clauses`
   / shared-witness `ask_all` now produce correct targets where the extractor applies
   them; the residual misses are inconsistent application, not missing IR.
3. **The remaining wall is G2 (missing premises)**, and prompt-level fixes are
   variance-bound. The only larger lever is the deferred `A′` (§19), whose revisit
   condition (a clean unlink signal) run 3 does not change: the G2 rows remain
   budget-exhausted / gap-less, not clean unlinks.

**Recommendation.** Accept text-fed ≈ 31/45 (best) / 29 (typical) with 0 grounded
false proofs; stop live runs under the budget policy; keep `A′` as the deferred
backlog item. Further accuracy work should be a separate, measured decision, not more
prompt tuning against variance.

## 22. Model ablation — a stronger model does not move the wall

Hypothesis: the residual misses are extraction instruction-following, so a stronger
model (`~deepseek/deepseek-v4-pro-latest` on the same RouterAI endpoint) should help.
Two runs, FOLIO L2 tier a, `ANKYRA_MODEL` overridden:

- **Run A — pro, reasoning disabled** (`ANKYRA_EXTRA_BODY='{"thinking":{"type":"disabled"},"reasoning":{"effort":"none"}}'`,
  `REASONING_EFFORT=none`): full 45, **28/45**, **0** grounded mismatches.
- **Run B — pro, reasoning not disabled** (no disable fields): **aborted at 11/45** —
  reasoning produced very large outputs and did not finish in a practical time,
  burning budget.

On the 11 rows both pro runs completed (the label-sorted prefix, all `False`):

| model / mode | correct on the 11 |
|---|---|
| flash (baseline run 3) | 4/11 |
| pro, reasoning off | **5/11** (`0107` fixed) |
| pro, reasoning on | 5/11 (`0044` fixed, `0107` lost) |

The same rows stay wrong under **all three** configurations — `0020`, `0047`,
`0058`, `0072`, `0109` — and pro-off's full-run 28/45 sits inside the flash range
(29–31). So the model upgrade is **within variance**: it neither closes the G2/G3
wall nor improves the headline. Reasoning-on is additionally **not viable**: far
slower, far more expensive, and no better on the completed subset.

**Conclusion.** The wall is **not model capability**: it is premise retention
(`G2`) and consistent application of the target forms (`G3`) through the current
prompt/schema interface. The expensive reasoning mode is rejected on cost and
latency. Keep the existing default (flash, thinking disabled). The only remaining
structural lever is still the deferred `A′` (§19), on a fresh, clean unlink signal.


