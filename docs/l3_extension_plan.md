# L3 Extension Plan — composite factors, complete-list, count hardening, AR-LSAT guide

Status: **approved plan; execution in order.** The L3 gate is already green
(`docs/l3_plan.md` §13.2: live eval 23/30, 0 `grounded_mismatch`), so this plan is
**accuracy and robustness hardening**, not a gate repair. It records the findings from
the L3 implementation (`docs/ar_lsat.md` §8.1) that were **recorded, not worked
around**, and the fix each one proposes.

Canonical language: English; Russian mirror: `docs/l3_extension_plan_ru.md`.

Related: `docs/l3_plan.md` (§3 guardrails, §7 IR, §8 procedure, §13.2 findings),
`docs/ar_lsat.md` (§8.1–§8.2), `docs/implementation_plan.md` §8 item 28,
`docs/task.md` §3.8 (no NL heuristics), `docs/l3_plan.md` D-L3-10 (no sampling).

## 1. Goal

Turn the five recorded L3 findings into general, collection-agnostic fixes — or, where
the general fix is not yet justified, into a reproducible record — **without per-id
tuning and without sampling**. Two are soundness/robustness hardening (H1, H2), two are
IR/extraction extensions (H3, H4), one is a budgeted extraction-guide step (H5).

## 2. Scope and non-goals

**In scope.** The builder guard and the AR-LSAT gold invariant (LLM-free), the
`complete_list` triage and any minimal IR extension it forces, the composite-factor IR
design and spike, and the `count_compare` guide step once a dev-validated case exists.

**Out of scope (unchanged).** Per-id tuning (`docs/coverage_ceiling.md` §8); sampling
and self-consistency (D-L3-10); a hardcoded LSAT ontology or per-game branch
(`docs/l3_plan.md` §2); lowering a construct onto a weaker one to pass a row (§3);
any live run other than the explicitly budgeted ones (§10).

## 3. The five findings

| id | finding | class | general fix |
|---|---|---|---|
| **H1** | `count` counts only `values[0]`; extra values are silently ignored. `count_compare` crashes (`ValueError`) when `values` has fewer than two. | soundness/robustness | **DONE (revised)** — a counted group is a **set of values** (membership); an empty group or a missing count is a build error, and `count_compare` needs two distinct values |
| **H2** | `201306_2-G_1` q4: the stored key contradicts its own constraints; the row is excluded, not explained. | reproducibility | **DONE** — the exclusion is a committed artifact (`build_ar_lsat_gold.exclusions()`) and the gold invariant asserts the disagreement |
| **H3** | `complete_list` targets that are not variables (`'bottom'`, `'middle'`, `'slot1'`, `'assigned'`) are `out_of_fragment`. | extraction **or** IR | **DONE** — triage found three clusters; the value-target cluster is a value-target `complete_list` (D-L3-12), the ordered/derived clusters stay out |
| **H4** | one slot value packs two factors (`screen1_7pm`); `same_group`/`different_group` compare the whole value and go vacuous; a single-factor claim is inexpressible. | IR | **DONE** — a declared factor/projection over the packed domain (D-L3-11); `201310_3-G_3` hand-encoded as T0 rows |
| **H5** | "more X than Y" was encoded as two `count`s and "at least N on each group" lost a value; the guide patch was reverted because it broke another game. | extraction | **CLOSED (negative)** — dev-validated: the rules regress a correct `count_compare` row; not promoted, guide reverted, eval not run |

Source of H1/H4: `src/ankyra/engine/csp/solver.py:128-151`, `src/ankyra/build/csp.py:90-104`.
Source of H3/H4/H5: `docs/ar_lsat.md` §8.1–§8.2. Source of H2: `docs/l3_plan.md` §13.2.

## 4. H1 — counted-group shape guard (LLM-free)

- **Finding.** `count` (`solver.py:132-140`) sums `assign[v] == values[0]`; any
  additional `values` pass `_check_values` and are silently dropped. `count_compare`
  (`solver.py:142-151`) needs exactly two values and raises `ValueError` otherwise — a
  crash, not an honest build error.
- **Fix (revised after a live run).** A counted group is the **set** of declared values:
  the solver counts the variables whose value **belongs to** the group, so a single value
  is the special case and a union is meaningful. An empty group or a missing count is a
  `CspBuildError`; `count_compare` needs exactly two distinct values.
- **Why membership, not a one-value guard.** The first implementation rejected a
  `count` with more than one value. The live eval then showed that four previously
  correct rows encode "exactly one of A or B is assigned" as a count over the **three
  country values** — a genuine value-set membership — and the hard guard turned them
  into build errors (21→17 on the gate). Membership is the general reading, restores
  those rows by semantics rather than by luck, and keeps every single-value case
  identical.
- **Artifacts.** `solver._holds` (membership), `build.csp._check_counted` (empty group /
  missing count only), schema/prompt wording, tests in `tests/test_build_csp.py` and
  `tests/test_engine_csp.py`, `docs/l3_plan.md` §3, `docs/ar_lsat.md` §8.1.
- **Cost.** 0 LLM calls; the live eval re-measurement is part of §10.

## 5. H2 — AR-LSAT gold consistency invariant (LLM-free)

- **Finding.** `201306_2-G_1` q4 (stored key D) is inconsistent with its own
  constraints: faithful encoding plus two independent checks show the key's option is
  satisfiable and the alternative is not. The row is excluded, not special-cased
  (`docs/l3_plan.md` §13.2).
- **Fix.** Do **not** rewrite the key and do **not** add a per-id branch. Instead make
  the discrepancy reproducible: a gold invariant in `tests/test_evals_ar_lsat.py` that,
  for every hand-encoded gold row, asserts the unique verified option equals the
  dataset key; the excluded row stays in a small explicit exclusion list with a reason
  code, and a companion test **confirms** the solver disagrees with the key (the
  discrepancy is a property of the data, asserted and visible), so a future dataset or
  engine change cannot silently re-classify it.
- **Artifacts.** The invariant and the exclusion record; a note in `docs/ar_lsat.md`
  §8.1. Reporting the inconsistency upstream is optional and out of code.
- **Cost.** 0 LLM calls.

## 6. H3 — `complete_list` over a derived sequence/entity (triage first)

- **Finding.** The `out_of_fragment` `complete_list` rows name a target that is not a
  game variable: `'bottom'`/`'middle'` (a shelf value), `'slot1'` (a slot value),
  `'assigned'` (a derived entity). The committed semantics enumerates one **variable's**
  possible values (`solver.py:312-322`), so a derived list is not expressible.
- **Triage result (DONE, LLM-free; `docs/ar_lsat.md` §8.1).** Every `out_of_fragment`
  row is a `complete_list` over a **derived** target, in three clusters, none of which
  is an extraction-naming error (the model read the question kind correctly):
  - **value target** (4 eval) — "books on the bottom shelf", "bands any one of which
    could be in slot one", "photographers who must be assigned": the answer is the set
    of **variables** assigned to a declared value, unioned over models ("could") or
    intersected ("must").
  - **ordered sequence** (1 dev) — "the speeches in the Gold Room, in order": the
    value-filtered variables ordered by position.
  - **derived relation** (1 dev) — "the building any one of which could be the building
    the Trents owned": neither a variable nor a value.
- **Fix.** Only the **value-target** cluster is a candidate for the committed fragment:
  a minimal, general `complete_list` mode whose target is a declared value and whose
  set is the variables assigned to it across models, `could` = union / `must` =
  intersection (decision **D-L3-12**). The ordered and derived-relation clusters are
  recorded as **outside** the fragment (they need ordering over a derived sequence and
  a derived relation respectively) — no ad-hoc branch.
- **Artifacts.** The triage table in `docs/ar_lsat.md` §8.1; the chosen rule/IR
  extension with a synthetic case in `evals.l3_synthetic` and a gold encoding if the
  row is hand-encodable.
- **Cost.** Triage 0 LLM; the extension LLM-free to build and test; at most one paid
  eval run (§10).

## 7. H4 — composite factors / projection (IR; D-L3-11)

- **Finding.** In `201310_3-G_3` the domain `slots` packs screen and time
  (`screen1_7pm`, …) while a separate `screens` domain is declared but unused.
  `same_group`/`different_group` (`solver.py:128-130`) compare two variables' values,
  which is a whole packed value — so "same screen" and "starts at 9" are either vacuous
  or inexpressible.
- **Fix (design decision D-L3-11, to be confirmed by the spike).** Give a domain a
  declared **factorization**: `CspDomain.factors: list[domain_id]` whose cartesian
  product is the value type, and let a constraint name a **factor** it applies to
  (projection), so `same_group(A, B, factor="screen")` compares the screen component
  only. The alternative — a variable ranging over a factor domain — is evaluated in the
  spike; the smaller form wins, and no per-game branch is added (§2).
- **Spike (LLM-free).** Hand-encode `201310_3-G_3` under the candidate IR and solve its
  three committed questions; accept only if all three decide soundly (0
  confidently-wrong). Record the forced shapes.
- **Artifacts.** IR + solver + builder + extraction schema/prompt; a synthetic case in
  `evals.l3_synthetic`; the hand-encoded `201310_3-G_3` as a new gold-fed (T0) row;
  `docs/l3_plan.md` §7 and `docs/ar_lsat.md` §8.1 updated.
- **Cost.** LLM-free design/spike/tests; at most one paid eval run (§10).

## 8. H5 — `count_compare` / "each group" guide (budgeted)

- **Finding.** The two encoding errors in §8.1 were attacked with a guide patch
  (explicit `count_compare` negative example; "one `count` per group value"; "never
  leave a composite empty"). It was **reverted**: eval fell 21→18 with 1
  `grounded_mismatch`, plausibly because the added `count` emphasis primed a
  mis-encoding of "either … but not both" as `count(exactly 1)`.
- **Plan.**
  1. ~~Extend the dev sample.~~ **Not needed:** the committed dev sample already
     contains `count_compare` (`201409_3-G_3_15`/`_16`, encoded correctly in the
     existing dev run); it is a **regression check** for the rules, not a reproduction
     of the eval error. (The earlier "no `count_compare` row" note was wrong.)
  2. Add the guide rules to `evals/skills/ar_lsat/` and run **one dev run**
     (`evals/ar_lsat.py --sample dev --live`): confirm the rules hold and do not
     regress the already-correct `count_compare` games.
  3. Only after dev validation, **one eval run** (the gate). Never tune on the gate
     (D-L3-10).
- **Artifacts.** The dev-sample criterion; the guide rules in
  `evals/skills/ar_lsat/`; the dev-then-eval numbers recorded in `docs/ar_lsat.md`
  §8.2 and `docs/implementation_plan.md` §8 item 28.
- **Cost.** 1 dev + 1 eval run (explicit budget decision).

## 9. Work order

1. **H1** (guard) then **H2** (gold invariant) — small, LLM-free, harden soundness and
   reproducibility.
2. **H3 triage** (LLM-free), then `H3` fix and/or **H4** design/spike (LLM-free); the
   triage may close part of H3 without IR work.
3. **H5** — paid, last, and as a separate budget decision.

Live runs are **batched**: at most one eval run covers H3 and H4 together, after their
LLM-free tests are green; H5 has its own dev/eval pair.

## 10. Budget

- 0 LLM calls: H1, H2, H3 triage, H3 fix, H4 design/spike, all tests.
- Budgeted live: **1 eval** for H3+H4 (optional — the gate is already green; run only
  if the extensions land), and **1 dev + 1 eval** for H5.

## 11. Decisions

- **D-L3-11 — RESOLVED.** Composite factors are a **declared factorization with
  projection**: `CspDomain.factors` + `value_factors` and a constraint `factor` that
  projects each value onto one factor (using that factor domain's topology);
  `all_different`/composites stay on the whole value. Not a per-game split and not a
  new constraint kind. Confirmed by the spike and the hand-encoded T0 rows.
- **D-L3-12 — RESOLVED.** `complete_list` targets a declared value (the set of
  **variables** assigned to it) when `target_kind="value"`, with a `could`/`must` mode
  (union/intersection of the per-model sets), covering the value-target cluster of §6;
  a list is read only from a complete enumeration. The ordered-sequence and
  derived-relation clusters stay outside the committed fragment.

## 12. Tests

- `tests/test_build_csp.py` — H1 negative shapes (`count` with 0/2 values,
  `count_compare` with 1/3/distinct-value violations).
- `tests/test_evals_ar_lsat.py` — H2 gold invariant plus the explicit exclusion record.
- `tests/test_build_csp.py` / `tests/test_engine_csp.py` / `evals.l3_synthetic` — the
  H3/H4 IR additions (projection evaluation, domain-target enumeration, negative
  controls).
- Full regression: `uv run pytest` (offline; live tests skipped).

## 13. Documentation updates

- `docs/ar_lsat.md` §8.1–§8.2 — the triage table and the H5 dev/eval result.
- `docs/l3_plan.md` §3, §7, §13.2 — the new guards, the IR extension and this plan.
- `docs/implementation_plan.md` §8 item 28 — the H5 outcome.
- `README.md` — L3 line and the documentation index; `docs/reasoning_roadmap.md` L3
  status if the gold-fed row count changes.

## 14. Status

- **H1:** DONE — `count` counts the variables whose value belongs to the **set** of its
  `values` (membership); `build.csp._check_counted` rejects only an empty group or a
  missing count, and keeps `count_compare` at exactly two distinct values. Locked by
  `tests/test_build_csp.py` (`test_count_needs_a_count_and_a_group`,
  `test_count_compare_needs_two_distinct_group_values`,
  `test_counted_group_in_an_option_is_checked`) and
  `tests/test_engine_csp.py::test_count_group_is_a_set_of_values`. (The one-value guard
  was the first attempt; the live run showed the model's multi-value counts are
  meaningful, so membership superseded it — `docs/ar_lsat.md` §8.2.)
- **H2:** DONE — `evals.build_ar_lsat_gold.exclusions()` records the excluded
  `201306_2-G_1` q4 with its reason, expected key and the engine's disagreeing option;
  `tests/test_evals_ar_lsat.py::test_excluded_gold_rows_record_their_disagreement`
  asserts the disagreement reproducibly (and `test_gold_gate_is_green_without_grounded_mismatch`
  remains the 27/27 T0 invariant).
- **H3:** DONE — the value-target `complete_list` (D-L3-12) is implemented:
  `CspQuestion.target_kind ∈ {variable, value}` and `list_mode ∈ {could, must}`;
  `solver._list_items` unions/intersects the per-model item sets over a **complete**
  enumeration (`SearchResult.complete`; a truncated enumeration is `insufficient`),
  and the builder validates a value target against the declared domain values. Tests:
  `tests/test_engine_csp.py` (union/intersection/completeness),
  `tests/test_build_csp.py` (value target, aliases), synthetic
  `evals.l3_synthetic` **29/29** then **31/31** (with H4), and a hand-encoded T0 row
  (`201310_3-G_1` q5) that raises the gold gate to **23/23** over 6 games. The
  ordered-sequence and derived-relation clusters stay outside the fragment (D-L3-12
  resolved).
- **H4:** DONE — a **product domain with factor projection** (D-L3-11):
  `CspDomain.factors` + `value_factors` decompose a packed value, and a constraint's
  `factor` projects each variable's value onto one factor before evaluating (using that
  factor domain's topology); `all_different` and the composites stay on the whole
  value. `solver._assigned_value`/`_domain_for` implement the projection; the builder
  validates the factorization (`_check_domains`) and every `factor` reference
  (`_check_factors`). Tests: `tests/test_engine_csp.py`
  (`test_factor_projection_is_load_bearing`, `test_factor_projection_compares_factor_values`),
  `tests/test_build_csp.py` (`test_product_domain_and_factor_projection_build`,
  `test_malformed_product_domains_are_refused`, `test_factor_constraints_are_validated`),
  synthetic `evals.l3_synthetic` **31/31**, and the packed-slot game `201310_3-G_3`
  hand-encoded as four T0 rows (q13/q15/q16/q18) that raise the gold gate to **27/27**
  over 7 games.
- **H5:** dev-validated **negative** — the `count_compare` rules were added and run on dev
  (one paid run): 9/12, 0 `grounded_mismatch`, but the `count_compare` game
  `201409_3-G_3` regressed (`q15` `correct`→`no_option`) because the extraction dropped
  the per-group counts while keeping `count_compare` — the same failure mode as the eval
  regression. The rules are **not promoted**, the guide is reverted to the known-good
  text, and the eval gate is **not re-run** (the safe call under C1). The committed dev
  sample did contain a correct `count_compare` row, so this is a real dev validation, not
  a missing-data blocker. Recorded in `docs/ar_lsat.md` §8.2 and item 28.
