# ProofWriter — collection notes

Operating notes for the external benchmark used by the eval harness. The Russian
mirror is `docs/proofwriter_ru.md`.

Source: Tafjord, Mishra, Clark, *ProofWriter: Generating Implications, Proofs, and
Abductive Statements over Natural Language* (AI2, arXiv:2012.13048), mirrored at
`tasksource/proofwriter` on the Hugging Face Hub. The committed subset lives in
`evals/data/proofwriter_tier_a.jsonl`; the harness is `evals/proofwriter.py`.

## 1. What the benchmark is

A synthetic logical-reasoning benchmark. A generator builds a **theory** (a short
text of facts and rules) plus a **question** (one statement), and labels the item
`True`, `False`, or `Unknown` together with one or more proof graphs.

The vocabulary is fixed by the generator:

- **entities** — Anne, Bob, Charlie, Dave, Erin, Fiona, Gary, Harry, and
  `the cat / cow / dog / tiger / lion / bear / mouse / squirrel / rabbit / bald
  eagle`;
- **unary properties (attributes)** — nice, blue, round, rough, smart, young, big,
  cold, green, red, white, furry, quiet, kind, …;
- **binary relations** — chases, eats, likes, needs, sees, visits.

Sentence forms:

- facts: `Anne is nice.` / `The cat chases the mouse.` / `Anne is not nice.`;
- rules: `All nice people are cold.` / `Rough things are white.` /
  `If someone is blue and round then they are young.` /
  `If the cat eats the cow then the cow is not nice.`

Labels:

- **True** — the statement is entailed by the theory;
- **False** — its negation is entailed;
- **Unknown** — neither is entailed.

Two semantic regimes exist: **CWA** (closed-world: what is not proven is false) and
**OWA** (open-world: what is not proven is `Unknown`). Every id in
`tasksource/proofwriter` carries `-OWA-`, so the mirror is open-world. Ankyra runs
strict deduction, which is the matching regime: `Unknown` maps to `unknown`, never
to `no`.

## 2. Record fields

One record is one question against one theory (a theory appears in many records,
one per question).

| Field | Meaning |
|---|---|
| `id` | `<Prefix>-OWA-D<N>-<k>`: test family, generation depth, index |
| `config` | source-slice tag (`depth-0..5`, `depth-3ext`, `NatLang`, `depth-3ext-NatLang`) |
| `theory` | premise text (facts + rules) |
| `question` | the statement to check |
| `answer` | `True` / `False` / `Unknown` |
| `maxD` | maximum proof depth present in the example |
| `NFact`, `NRule` | number of facts / rules |
| `QDep` | depth at which the target fact sits in the proof graph (`0` = asserted) |
| `QLen` | proof length in steps; `null` when there is no proof (as for `Unknown`) |
| `allProofs` | proof graph(s), e.g. `@0: … [(triple1 OR ((triple6) -> rule6))]` |

## 3. Axes (“areas”)

**A. Question kind — `Att` vs `Rel`.**
`Att*` asks about a unary attribute (`Harry is furry`), which Ankyra encodes as
`is_a`. `Rel*` asks about a binary relation (`The cat chases the mouse`), a binary
predicate.

**B. Negation in the theory — `Neg` vs `Noneg`.** Measured on the validation
split: `*Neg` theories contain a negation in 93–96% of cases
(`Anne is not nice.`, `If someone is smart and not round …`), while `*Noneg`
theories are negation-free (0%). This is a property of the *theory*, not of the
question: question polarity is an independent axis, roughly 50/50 inside every
family.

Together these give four families: `AttNoneg`, `AttNeg`, `RelNoneg`, `RelNeg`.

**C. Proof depth.** `config = depth-N` is the generation target; the observed
`maxD` has its mode at `N` (e.g. `depth-2` → `maxD = 2` for 8 944 of 10 094 rows;
`depth-5` → `maxD = 5` for 9 200 of 10 190). `QDep ≥ 1` means at least one rule
application is needed; `depth-0` also contains trivial `QDep = 0` items.

**D. Language / variant.**
- the **synthetic core** (`depth-0..5`) uses short template phrasing;
- **`NatLang`** restates the same tasks in invented natural language —
  `Bob has been blue because he's green with envy.`,
  `The round, rough, and green one was labeled Eric after all.` This is genuine
  out-of-distribution input for the extractor (long compound sentences with
  distractor clauses);
- **`depth-3ext`** is an extended depth-3 slice with more facts and rules (up to
  16 facts / 8 rules, `maxD` centred on 3);
- **`depth-3ext-NatLang`** combines extended depth-3 with NatLang phrasing.

## 4. Volumes and splits

`tasksource/proofwriter`, subset `default`: train 585 552 / validation 85 468 /
test 174 476 records. The harness uses the `validation` split, cached locally at
`evals/data/.cache/`.

Inside validation:

- 6 368 unique theory ids, 54 848 unique `(id, question)` pairs;
- theory counts per id prefix: `AttNeg` 1 574, `AttNoneg` 1 695, `RelNeg` 1 426,
  `RelNoneg` 1 433, `AttNonegNatLang` 240;
- label counts: `True` 23 199, `False` 23 199, `Unknown` 39 070.

**Mirror quirk.** The `config` tag is the original file the row came from and is
not a clean partition: `depth-3ext-NatLang` mixes core-prefix rows
(`AttNeg`/`AttNoneg`/`RelNeg`/`RelNoneg`) with `AttNonegNatLang` rows. The reliable
axes are the `id` prefix and `depth-N`/`NatLang` content, not the `config` string.

## 5. How Ankyra uses it

`evals/build_proofwriter_sample.py` performs a deterministic, stratified selection
and commits it as JSONL, so eval runs need no network. The current committed
sample is **Tier A**: only the synthetic core (`config` matching `depth-\d+`),
three questions per `(depth ∈ {0,1,2,3,5}, label ∈ {True,False,Unknown})`,
rotating over the four families.

`evals/proofwriter.py` runs each record through the full pipeline. The problem
text is the theory plus `Is it true that <statement>?`. Benchmark semantics stay
out of the engine: the adapter maps

- `True → Answer.kind yes`,
- `False → Answer.kind no`,
- `Unknown → Answer.kind unknown`,

and inverts the expected label when the extractor rewrites a negated statement
into a positive ask (reported per problem as a polarity flip). Strict deduction is
the default (`allow_hypotheses=False`); `--hypotheses` enables the abductive mode,
where determinate matches are split into `proven` and `proven_under`. Mismatches
are classified by shape: `grounded_mismatch` (a strict proof against the label —
the serious one), `hypothetical_decision`, `question_begging`,
`undecided_mismatch`.

**Sampling policy.** Extraction runs with `ANKYRA_EXTRACT_SAMPLES=1`. Best-of-N
sampling was measured not to improve outcomes (`quality_findings.md`, C1): the
selection ranker is a syntax/grounding metric that ties on logically different
structures. Provider variance is handled by a re-run when a report is not clean,
never by sampling (see the staged protocol in §6).

## 6. Status and expansion

Strict baseline on Tier A: 45/45 (30/30 determinate all `proven`, 15/15 `Unknown`,
no grounded false positives). Abductive mode is reported separately and is not a
gate.

### Staged expansion

The tiers serve **both quality measurement and debugging**. They are run
iteratively: run a tier, read its per-problem report and traces, fix extraction /
formalization where needed, re-run. The sizes are confidence-building steps; the
full collection is a gated final run.

**Measurement protocol.**
- `ANKYRA_EXTRACT_SAMPLES=1`; strict deduction by default; the abductive mode is
  reported separately and is never a gate.
- **Cost-aware runs: tier once.** Re-run a tier — or just the mismatching item —
  only when the report is not clean, to separate a real failure from
  provider-level variance (C1). Tiers are not repeated a fixed number of times;
  API tokens are paid for out of pocket.
- Hard invariants on every run: **0 grounded false proofs** (a strict proof
  against the label) and every determinate (`True`/`False`) answer `proven`.
  A mismatch is triaged: re-run to reproduce; if it reproduces it is a real
  failure to fix, otherwise it is recorded as provider variance with its
  frequency.

**Tiers.**

| Tier | Size | Composition | Purpose / gate |
|---|---|---|---|
| A | 45 | core: 5 depths × 3 labels × 3, rotated families | baseline (done) |
| B | 75 | A + 30 NatLang (10 theories × 3 labels) | NatLang reconnaissance and debugging; gate: 0 grounded false proofs, kind accuracy ≥ 90%, every failure triaged |
| C | 150 | 75 core (5 × 3 labels × 5) + 75 NatLang (25 theories × 3 labels) | scale; gate: 0 grounded false proofs, kind accuracy ≥ 95% |
| D | 300 | C + 150 `depth-3ext` (50 theories × 3 labels) | second area; gate: 0 grounded false proofs, kind accuracy ≥ 95%, per-area report |
| E | full | 6 368 theories, one question each, all areas (≈11 h) | **cancelled** — no free LLM access; not run |

Tier E is **cancelled**: there is no free LLM access and API tokens are paid out of
pocket, so the full-collection run will not be executed. **Tier D (300 items, 99%,
0 grounded false proofs) is the accepted proof of concept.** The all-questions set
(54 848 items, ≈97 h) is a separate decision and out of scope by default.

**Results.** Tier A: strict 45/45 (§5). Tier B (`--tier b`,
`ANKYRA_EXTRACT_SAMPLES=1`): **74/75** kind accuracy — core 45/45, NatLang 29/30; 0
grounded false proofs; determinate 49/50 all `proven`; `Unknown` 25/25. The one
mismatch (`AttNonegNatLang-OWA-111`) is an extraction miss — the paraphrase "wears
all green" became a `wear` relation instead of `is_a(eric, green)` — and is
sensitive to provider variance (C1); the gate is met, and a re-run on the fixed
engine reproduced 74/75.

Tier C (`--tier c`): the first run scored 147/150 but with one **grounded false
proof** (`AttNonegNatLang-OWA-15`: `NOT is_a(alan, red)` licensed by an unrelated
quote). That exposed an under-implemented B8 guard, now fixed (an overlapping span
of an already-grounded atom witness counts as reuse; `quality_findings` B8). After
the fix and targeted re-runs of the seven affected items, Tier C is **148/150
(98.7%)**, 0 grounded false proofs, determinate all `proven`. The two remaining
misses are NatLang extraction / formalization errors (`NatLang-10`: `feels blue`
kept as a state predicate; `NatLang-114`: `blue skin` attached to `skin`), answered
as honest `unknown`.

Tier D first run (`--tier d`, 75 core + 75 NatLang + 150 `depth-3ext`):
**296/300 (99%)** (core 74/75, NatLang 73/75, `depth-3ext` 149/150), determinate
198/200 all `proven`, no hypotheses. The gate was **not green** on that run (the
re-run below closes it). Triage (one
re-run each): `RelNeg-OWA-D1-1025` and `AttNonegNatLang-OWA-107` did not reproduce
(provider variance); `AttNoneg-OWA-D0-2873` (a named-entity conditional
over-generalized to `is_a(?x,young) => is_a(?x,rough)`) and
`AttNonegNatLang-OWA-114` (the known `blue skin` miss) reproduce. Two **open
findings**, no code change yet: (1) `reformalize_query` may add `Gamma` conditions
that are absent from the question, and those ungrounded conditions can refute the
target — a soundness hole; (2) a named-entity conditional can be extracted as a
universal rule (extraction; deterministic NL parsing is forbidden). See
`quality_findings` E.

**Tier D re-run (`--jobs 5`, parallel).** After the provider stabilised, Tier D was
re-run with the harness thread pool: **0 grounded false proofs**, every determinate
match `proven` (197/199), kind accuracy **297/299 (99%)**, `depth-3ext` **150/150**.
One item (`RelNeg-OWA-D3-1062`) returned no target on the first attempt — the
`extract_problem` call left the recorded question blank, so the question call saw an
empty question — and a single `--ids` re-run answered it `yes`/`proven`: provider
variance (C1), not a failure. The two remaining misses are NatLang
extraction/formalization errors answered as honest `unknown`:
`AttNonegNatLang-OWA-108` (`Dave feels blue` extracted as a state predicate `feel`,
not `is_a(dave, blue)`) and `AttNonegNatLang-OWA-114` (the known `blue skin` miss).
`AttNoneg-OWA-D0-2873` (named-entity conditional) and `AttNonegNatLang-OWA-107` both
matched this run. The two open findings above are unchanged — not observed as false
proofs here.

Thresholds and the Tier C/D splits are policy knobs, not architecture; they can be
tightened as the extraction improves. Tiers B–D are added to the committed sample
by extending `evals/build_proofwriter_sample.py` (per-tier selection spec), and
the resulting gates are recorded in `docs/implementation_plan.md`.

## 7. Testing plan

Scope: Tiers B–E (Tier A is the committed baseline). The plan is a **debugging
loop**, not a scoring ritual: a tier is done only when its report is green or every
remaining failure is categorized.

### 7.1 What we run

Target CLI (requires the builder/harness changes noted in §6):

- build a tier's committed sample:
  `uv run --with pyarrow python -m evals.build_proofwriter_sample --tier b`
  → `evals/data/proofwriter_tier_b.jsonl` (deterministic; `--tier c`, `--tier d`);
- run a tier (strict, the default):
  `uv run python -m evals.proofwriter --tier b [--jobs N]`
  — per-item traces to `evals/out/proofwriter/<id>.json`; `--hypotheses` enables
  the abductive mode (reported, never a gate); `--limit N` for a smoke run.
  `--jobs N` (shared by `evals.run`/`proofwriter`/`prontoqa`/`folio`) runs up to N
  items concurrently on threads; per-problem flags stay in a `ContextVar`, so the
  race-free general mechanism works for heterogeneous `problems.jsonl` too;
- targeted re-run after a fix:
  `uv run python -m evals.proofwriter --tier b --ids <id1>,<id2>`;
- inspect one item: `evals.narrate` renders a stored trace. **Tooling gap:** it
  currently reads `evals/problems.jsonl` and `evals/out` only, so it needs a
  `--traces-dir` (or equivalent) to narrate ProofWriter traces from
  `evals/out/proofwriter`.

`ANKYRA_EXTRACT_SAMPLES=1` (also the default). No network is needed once the
parquet cache exists.

### 7.2 What we read

From the run report: overall `kind accuracy` over polarity-known items; `unknown
polarity (no target extracted)`; `polarity flips`; the `statuses` / `strengths` /
`shapes` distributions; `determinate matches (proven vs proven_under)`; accuracy
broken down by depth, label, prefix and question polarity; and the per-problem
line (id, config, label, actual kind, status, wave count, flip).

From a per-item trace (`evals/out/proofwriter/<id>.json`) for a failure:
`structure`, `theory`, `symbolic` (quote/substring check), `query`, `verdict`
(gaps, bindings, unused premises), `answer`, `explanation`, `waves`
(proposal + category + reason), `hypotheses`, `llm_calls`.

### 7.3 Failure taxonomy and triage

| Observation | Meaning | Action |
|---|---|---|
| `grounded_mismatch` (`proven`, wrong kind) | a strict proof against the label: formalization/engine bug or benchmark artifact | **block**; inspect the trace; fix, or demonstrate the artifact |
| determinate label, kind `unknown`, `unsupported`/`no_progress` | extraction or formalization miss | fix the prompt / Phase 0 |
| `unknown polarity (no target extracted)` | the query was not expressible in the theory vocabulary | fix question extraction / vocabulary |
| `polarity_flip` | the extractor rewrote a negated statement into a positive ask | verify correctness; not an error by itself |
| `contradiction` | an inconsistency reached the target | inspect; often an over-eager negation |
| `budget` | `max_waves` exhausted | inspect; may be `insufficient` rather than a bug |
| `hypothetical_decision` | abductive mode only | informational |
| `question_begging` | a hypothesis restated the target | should have been rejected; if seen, a bug |

Triage rule (cost-aware): re-run the failing item once. If it reproduces it is
real and gets a root cause — extraction / builder / engine / benchmark. If it does
not reproduce it is recorded as provider variance (C1) with its frequency.

### 7.4 Fix loop and exit criteria

Per tier:

1. run the tier once;
2. read the report, list failures with their shapes, triage;
3. re-run each failure once to separate real failures from C1 noise;
4. fix real failures — minimal diff, general solutions; no special-casing
   benchmark wording (`docs/task.md` §3.8);
5. re-run the fixed items via `--ids`; when a batch of fixes lands, re-run the
   whole tier once;
6. check the gate.

**Green** for a tier: 0 grounded false proofs; every determinate answer `proven`;
kind accuracy ≥ the tier threshold (B 90%, C/D 95%); every remaining failure
categorized (fixed, or documented as a benchmark artifact / provider variance).

### 7.5 Cost hygiene

- a tier runs **once**; individual items are re-run with `--ids`;
- traces are cached in `evals/out/proofwriter` (gitignored) — re-read, do not
  re-run;
- Tier E is cancelled (no free LLM access);
- `SAMPLES=1` everywhere.

### 7.6 Deliverables

After each tier: update the tier table in §6 with the measured numbers; record
findings in `docs/quality_findings.md` (section E); add or extend tests for every
fix; and open a named finding in `docs/implementation_plan.md` for anything left
unresolved.
