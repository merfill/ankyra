# AR-LSAT — collection notes

Operating notes for an analytical-reasoning benchmark, planned as the **L3 gate**
of `docs/reasoning_roadmap.md`. Russian mirror: `docs/ar_lsat_ru.md`. Related:
`docs/reasoning_roadmap.md`, `docs/task.md` §3.8.

Source: AR-LSAT, Zhong et al. (arXiv:2104.06598); packaged for evaluation by
**AGIEval** (arXiv:2304.06364). Raw dataset: `github.com/zhongwanjun/AR-LSAT`. HF
mirrors: `tasksource/lsat-ar`, `olegbask/AR-LSAT`, `dmayhem93/agieval-lsat-ar`. No
committed sample yet.

## 1. What the benchmark is

LSAT **analytical reasoning** ("logic games"). Each item is one game: a `context`
describes a finite scenario — a set of entities, the positions or groups they
occupy, and a list of constraints. One context is shared by many questions. Each
question is a five-way multiple choice.

A verified example (`context` abbreviated):

> Exactly six trade representatives negotiate a treaty: Klosnik, Londi, Manley,
> Neri, Osata, Poirier. There are exactly six chairs evenly spaced around a
> circular table… Poirier sits immediately next to Neri. Londi sits immediately
> next to Manley, Neri, or both. Klosnik does not sit immediately next to Manley.
> If Osata sits immediately next to Poirier, Osata does not sit immediately next
> to Manley.
>
> **Question:** Which one of the following seating arrangements … would NOT
> violate the stated conditions?
>
> **answers:** five full arrangements; **label:** 1 (0-based index).

## 2. Record fields

| Field | Meaning |
|---|---|
| `context` | the game: entities, domains/positions, constraints |
| `question` | the multiple-choice question |
| `answers` | exactly five candidate answers (strings) |
| `label` | 0-based index of the correct option |
| `id_string` | game/question id, e.g. `199106_2-G_1_1` (only in `tasksource/lsat-ar`) |

The multiple-choice options are not always full assignments: they may be a pair, a
"complete and accurate list", or a single constraint, depending on the question
type.

## 3. Axes

- **game type** — linear ordering, circular ordering, grouping/splitting,
  assignment; often a mix;
- **question type** — which arrangement would / would NOT violate; which must be
  true; which could be true; a complete and accurate list; "if X then Y";
- **entities / slots** — small finite counts (typically 5–7 entities, equal or
  fewer positions/groups).

## 4. Relation to Ankyra

AR-LSAT is **not** Horn deduction. Solving a game is finite-domain constraint
satisfaction: positions are a permutation, "immediately next to" is adjacency,
"not next to" is a disequality constraint, and "if … then …" is a conditional
constraint. The question types have model-theoretic semantics:

| Question form | Meaning |
|---|---|
| which arrangement would NOT violate | find a model satisfying every constraint |
| which must be true | true in **every** model of the constraints |
| which could be true | true in **some** model |
| complete and accurate list | enumerate the models and read off the set |

The current engine cannot express all-different, adjacency, mutual exclusion or
finite-domain enumeration, and its open-world Horn closure has no notion of
enumerating models. A Horn encoding would answer at best `unknown`.

## 5. What testing would require (L3 — separate engine)

- a dedicated **CSP IR**: entities, finite domains, all-different, order,
  adjacency (possibly circular), conditional constraints, grouped positions,
  count comparison, and **boolean composition** of relations (`all`/`any`/`not` —
  real constraints are often "either before both X and Y, or after both");
- a **solver**: in-repo finite-domain/backtracking search (an external SAT/SMT solver
  is the documented fallback);
- a **multiple-choice adapter**: each option is checked against the solver —
  satisfiability for "could" / "not violate", no counter-model for "must",
  unsatisfiability for "cannot be true", model enumeration for "complete and
  accurate list"; question-local assumptions (Gamma) cover the "if" questions;
- an **extraction** step that turns the game text into the CSP IR. This is the
  main difficulty and the main risk.

Ankyra's role in L3 is orchestration: the LLM proposes the CSP encoding, the
solver decides. The soundness contract is preserved, but the decision procedure
is a second engine, not the Horn spine.

## 6. Risks and non-goals

- **Hardcoding temptation.** Positional/adjacency specifics invite a fixed
  ontology (circular-table, next-to), which `docs/task.md` §3.8 forbids. The IR
  must be general and the extraction prompt must carry the semantics.
- **Distance from domain-general Horn.** AR-LSAT exercises a different paradigm;
  it does not strengthen the deductive core and is therefore low priority.
- **Extraction accuracy.** A wrong CSP encoding yields confidently wrong answers;
  the adapter must report encoding failures honestly rather than guess.

## 7. Test plan (if pursued)

0. **Feasibility spike (no LLM).** Hand-encode 5 games into the CSP IR and solve
   them with the L3 solver; measure solver-side correctness and the IR's
   expressiveness. **Done** — in-repo finite-domain solver (`docs/l3_plan.md`
   D-L3-1).
1. **Extraction probe.** For the same 5 games, have the LLM propose the CSP IR;
   measure encoding accuracy against the hand-written IR (not the final answers).
2. **Committed sample.** A small stratified set (by game/question type) built
   deterministically from the raw dataset.
3. **Adapter** `evals/ar_lsat.py` with per-option solver checks.
4. **Gate:** encoding accuracy above threshold and 0 confidently-wrong answers
   (`answer scored but solver input inconsistent`); failures triaged per option
   type.

## 8. Status

Separate engine. The L3 plan (`docs/l3_plan.md`) is approved and milestones 1–3 are
**green** (LLM-free): a general CSP IR plus an in-repo finite-domain solver
(`engine/csp/`) decide hand-encoded games (spike 5/5), and the committed synthetic
gate `evals.l3_synthetic` is **31/31** (every constraint kind — including boolean
composition, count comparison and factor projection — and every question semantics,
including a value-target `complete_list`, with negative controls), 0 confidently-wrong
answers. The real collection also forced the IR's
boolean composition (`all`/`any`/`not`): analytical-reasoning constraints are often
disjunctions of relations, not flat conjunctions (`docs/l3_plan.md` D-L3-2). The Phase-0 CSP extraction path
(schema + deterministic builder + prompt) is in place and validated LLM-free
(`tests/test_build_csp.py`). The **gold-fed tier is green: 27/27 real questions over
7 development games, 0 `grounded_mismatch`** (`evals/build_ar_lsat_gold.py`,
`evals/ar_lsat.py --gold`), so the method handles real games; the dev/eval samples are
committed. Routing/answer/explanation are wired (`ANKYRA_CSP`, `Answer.kind "choice"`,
the `model` explanation step). **The live gates were run once (budgeted): dev 9/12, 0
`grounded_mismatch`; **eval 23/30, 0 `grounded_mismatch` → the eval gate is GREEN**
(77% accuracy; the 7 misses are honest abstentions) — no engine unsoundness; the method
is green (gold 27/27). Landed: the question call receives the five options; a stricter
option prompt; a bounded question-repair pass; a duplicate-option guard; and an
**error-driven language-spec block** (`ANKYRA_LANGUAGE_SPEC`,
`evals/skills/ar_lsat/` for LSAT idioms). These raised eval from 7→21 correct and
closed confidently-wrong to 0; the provider stays nondeterministic (C1). See
`docs/reasoning_roadmap.md` L3 and, for the language guide and its next increment
(collection skills), `docs/implementation_plan.md` §8 items 28 and
`docs/l3_plan.md` §11.

### 8.1 Extraction-error triage (LLM-free, from the live dumps)

`evals/out/ar_lsat_{dev,eval}_live.jsonl` hold the extracted game/question per record
(`--dump`), so the abstentions can be classified without new calls:

- **`complete_list` over a derived target (all of the `out_of_fragment` rows: 4 eval +
  2 dev).** No row names a declared variable; the target is derived from the model(s),
  in three clusters:
  - **a declared value** — "a complete and accurate list of the books placed on the
    bottom shelf" (`201110_2-G_4_19`/`22`), "bands any one of which could be the band
    that performs in slot one" (`201310_3-G_1_5`), "photographers who must be assigned"
    (`201412_2-G_4_20`). The answer is the set of **variables** assigned to that value
    across models (union for a "could" list, intersection for a "must" list). **This
    cluster is now in the fragment (D-L3-12):** `complete_list` declares
    `target_kind="value"` and `list_mode` (`could`/`must`), and the list is read only
    from a complete enumeration (a truncated one is `insufficient`). Hand-encoded as
    the T0 row `201310_3-G_1` q5 (`docs/l3_plan.md` §7, §13.2;
    `docs/l3_extension_plan.md` H3).
  - **an ordered sequence** — "the speeches given in the Gold Room, in the order in
    which they occur" (`201409_3-G_2_11`): the value-filtered variables ordered by
    their position.
  - **a derived relation** — "the buildings any one of which could be the building the
    Trents owned" (`201409_3-G_3_18`): a target that is neither a variable nor a value.
  The committed `complete_list` semantics enumerates one variable's values, so all three
  were an IR/fragment limit, not mis-reading. The value-target cluster is now supported
  (D-L3-12); the ordered-sequence and derived-relation clusters remain **outside** the
  fragment (`docs/l3_plan.md` §13.2, `docs/l3_extension_plan.md` H3).
- **Composite-factor games (3).** When one slot value packs two factors (room+time,
  screen+time), `same_group`/`different_group` compare whole values and go vacuous,
  and a single-factor claim ("begins at 9", "same room") is not expressible with the
  packed domain. **Now supported (D-L3-11):** a packed domain declares its `factors`
  with a `value_factors` decomposition, and a relation may name the `factor` to
  project onto; the game `201310_3-G_3` is hand-encoded as a T0 row
  (`docs/l3_plan.md` §7, §13.2; `docs/l3_extension_plan.md` H4).
- **Encoding errors (2 in this run).** "More X than Y" was written as two `count`
  constraints instead of one `count_compare`, and "at least N on each group" missed one
  group value; both under-constrain the game → `no_option`.
- **Latent vacuity.** The builder formerly accepted an empty `all`/`any`/`not`/
  `conditional`, which evaluates vacuously (`all([])=True`, `any([])=False`); it now
  raises `CspBuildError` (`docs/l3_plan.md` §3), so an incomplete composite becomes an
  honest, repairable build error. A **counted group is now a set of declared values**
  (membership): the solver formerly read only `values[0]`, so "exactly one of Kayne or
  Novetzke is assigned" (encoded as a count over all three countries) was silently
  weakened — and a hard one-value guard regressed four live rows, which is why the
  semantics is membership instead (`docs/l3_extension_plan.md` H1). Only an empty group
  or a missing count is a build error. The live eval followed **21 (baseline) → 17
  (one-value guard) → 23 (membership)** with 0 `grounded_mismatch`, i.e. membership
  recovered the four rows by meaning, not by the old `values[0]` luck.

### 8.2 Error-driven guide experiment (tried, reverted — research)

The two encoding errors above were attacked with a guide patch (explicit `count_compare`
negative example, "one `count` per group value", "never leave a composite empty"). It
was **reverted**: the eval run fell 21→18 correct with **1 `grounded_mismatch`**. The
new `count` emphasis is the plausible cause — the "Either … but not both" premise of
another game was encoded as `count(exactly 1)` (which counts only `values[0]`), changing
that game's semantics wholesale. Provider variance (C1) confounds a single run, but the
side effect is credible. The guide is back to the known-good text (checksum-locked).
The rules themselves are correct and worth re-trying **against a dev-validated case**.
The earlier note that the dev sample has no `count_compare` row is **wrong**: the
committed dev sample does contain it (`201409_3-G_3_15`/`_16`, "The Williamses owned
more of the buildings than the Yandells owned"), and the existing dev run already encoded
it correctly. So the dev sample can validate the rules as a **regression check** (they
must not regress the already-correct `count_compare` games) without extending it — it
does not reproduce the eval encoding error, which is why the eval run still decides.
Never tune on the eval gate (D-L3-10). See `docs/implementation_plan.md` §8 item 28.

**Dev validation of the guide rules (one run).** The `count_compare` rules were re-tried
on the committed dev sample: **9/12, 0 `grounded_mismatch`** — the metric is unchanged,
but the `count_compare` game `201409_3-G_3` regressed. `q15` went `correct`→`no_option`,
and the extraction **dropped the per-group counts** ("each family owned at least one
building": three `count(..., at_least 1)` constraints) while keeping only
`count_compare`. So the rules trade a correct `count_compare` row for a lost premise —
the **same failure mode as the eval regression** (a count rule displacing other
constraints). The rules are therefore **not promoted**, the guide is restored to the
known-good text, and the eval gate is **not re-run**. Provider variance (C1) confounds a
single run, but the side effect is the same class as before and the safe call is a
revert. The dev sample already contained a correct `count_compare` encoding, so this is
a genuine dev-validated negative, not a missing-data blocker. See
`docs/l3_extension_plan.md` H5.

The general fixes for the §8.1 findings (the `count`/`count_compare` shape guard, the
gold consistency invariant, the `complete_list` triage, the composite-factor IR and the
`count_compare` guide) are planned in `docs/l3_extension_plan.md`.
