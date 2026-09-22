# FOLIO ceilings — coverage, extraction, and what extension can reach

Status: **analysis note** (no code change). It answers one recurring question:
*can Ankyra "solve FOLIO" by adding logics and procedures?* Short answer: the
in-fragment slice can be widened soundly and cheaply, but whole-collection
coverage is unreachable by design, and the measured bottleneck today is
extraction, not the engine.

Canonical language: English; Russian mirror: `docs/folio_ceilings_ru.md`.
Related: `docs/folio.md`, `docs/folio_extension_plan.md` (the staged plan this
note motivates), `docs/implementation_plan.md` §10,
`docs/quality_findings.md` §G, `docs/reasoning_roadmap.md`,
`docs/fragment_routing.md`, `docs/l2_plan.md`.

## 1. Summary

FOLIO's gold annotation is written in a language **wider than any committed
Ankyra formalism**. A collection whose gold mixes constructs from several
formalisms (and some from none) is a **composite benchmark**, not the scoreboard
of a single stage. Therefore:

- only the **in-fragment slice** is a gate; the rest is reported
  `out_of_fragment` and is not a failure;
- there are **two independent ceilings** — coverage (formalism) and extraction
  (model) — and a diagnostic that separates them;
- extension can raise the coverage ceiling **partially and soundly**; the
  currently measured bottleneck on FOLIO is extraction.

## 2. A composite benchmark, not a named formalism

Ankyra measures coverage in **named formalisms** (`docs/reasoning_roadmap.md` §1),
each with a sound decision procedure and a flag off by default. FOLIO's gold FOL
touches, at once:

- in-fragment: atoms, `∀` implications, conjunction, **negation** (L1),
  **disjunction** and `∃` (L2);
- beyond every committed stage: **equality**, **function terms**, `⊕` (xor),
  `↔` (biconditional), **axiom schemas**, **multi-variable** quantification.

`L3` (CSP) and `L4` (numeric) are separate engines and do not cover FOL
constructs. So a "full FOLIO score" would require a language Ankyra deliberately
does not commit to — and full FOL entailment is only **semi-decidable**
(`docs/folio.md` §4), so no sound total procedure exists to certify it. Full
coverage is **unreachable by design**, not pending (`docs/implementation_plan.md`
§10: "full coverage is unreachable by design").

## 3. Two ceilings

They are independent and constantly conflated:

| Ceiling | Constrained by | Symptom | Fix |
|---|---|---|---|
| **Coverage** (formalism) | which sentences the committed logic can express at all | `out_of_fragment` | add a named formalism, or abstain |
| **Extraction** (model) | how often the LLM translates NL into the formalism correctly | `unknown`/`insufficient`, wrong target | extraction/repair work |

`out_of_fragment` is an **honest abstention**: it costs recall, never soundness.
Manufacturing an answer for an out-of-fragment sentence would break the meaning of
`proven` (`docs/reasoning_roadmap.md` §1).

## 4. The gold-fed diagnostic

Feed the engine the **gold FOL formulas** (not the LLM extraction) and measure
method-only accuracy on the same slice (`docs/folio.md` §9,
`docs/implementation_plan.md` §10). This is the counterfactual that separates the
ceilings:

- gold-fed also low → the limit is the **method** (coverage/formalism);
- gold-fed high but text-fed low → the limit is the **language** (extraction).

Observed, FOLIO L1 negation (13 in-fragment): text-fed 7/13, gold-fed open 7/13,
gold-fed closed 8/13 — i.e. **coverage-bound**: even the gold formulas need
reductio (L2) or a closed-world step, so no single world assumption fits
(`docs/folio.md` §9). The **L2** bound now exists (`docs/folio.md` §10):
`evals/folio_fol` parses `∨`/`∃` and `evals.analyze_folio --subset l2` runs it
LLM-free. On tier a (45), at the diagnostic's time: text-fed 25/45, gold-fed 17/45,
**out_of_fragment 24/45** (so coverage was only 21/45). On the covered rows gold-fed
was 17/21 versus text-fed 15/21 — the dominant limit is the **method** (coverage), and
where the committed L2 procedure can express the gold formula it already beats the
extractor. The 24 out-of-fragment rows named the Tier-1 work: 12 the parser could not
represent (universal/conditional goals, shared-witness existential conjunctions,
nested existentials, `¬∃`), 12 the engine refuses as `unsafe_rule` (a universal
disjunctive fact `∀x (A(x) ∨ B(x))` grounds an unbounded head variable). **Tier-1 T1
(shared-witness `∃x(A(x)∧B(x))`) is done** (`docs/t1_plan.md`): gold-fed 21/45,
`out_of_fragment` 20/45, coverage 25/45, covered 21/25, 0 grounded false proofs.

## 5. Constructs: in fragment, reachable, out of reach

| Construct | Status | Route |
|---|---|---|
| atoms, `∧`, `¬`, `→`, `∀` implications | **in L1/L2** | already supported |
| `∨`, `∃` | **in L2** | bounded resolution + finite grounding |
| `↔` | reachable (cheap) | lower to two clauses `A→B`, `B→A` (no new procedure) |
| `⊕` (xor) | reachable (cheap) | lower to `(A∨B) ∧ (¬A∨¬B)` (no new procedure) |
| multi-variable `∀x∃y` | reachable (moderate) | generalize the finite grounding/Skolemization of L2 |
| universal / conditional / `¬∃` **goals** (G3) | reachable (moderate) | a universal/conditional target form; the engine already has `ask_all`/`ask_any` |
| axiom schemas (transitivity, symmetry) | via proposal | the LLM proposes them as **hypotheses**; the ledger exists (`docs/folio.md` §5) |
| equality (`=`) | fragment decision | finite congruence or a ground builtin; needs a soundness validation |
| function terms | fragment decision | bounded finite grounding, else `out_of_fragment` |
| full FOL beyond finite domains | **out of reach** | semi-decidable; outside the design boundary |

## 6. What extension can reach (options, not commitments)

- **Tier 1 — no new procedure, lowering only:** `↔`, `⊕`, universal/conditional
  goals, multi-variable quantification over finite domains. These reuse the
  bounded clausal procedure; the work is IR/extraction, not semantics.
- **Tier 2 — a fragment decision, with a soundness gate:** finite equality and
  bounded function terms. These leave "positive FOL" and must be validated on
  their own synthetic gate before any live run.
- **Tier 3 — out of scope:** full FOL, non-finite terms. Not reachable soundly.

## 7. Recommended order

1. ~~**Gold-fed L2 bound** (LLM-free, cheap, decisive).~~ **DONE** (see §4): the
   limit on the L2 slice is the **method** (coverage was 21/45), not the language, so
   Tier 1 (item 3) comes before extraction on FOLIO. **Tier-1 T1 done** — coverage
   25/45, gold-fed 21/45 (`docs/t1_plan.md`).
2. **Extraction G1–G4** (`docs/quality_findings.md` §G) — still worth doing on the
   rows the method now covers.
3. **Tier 1 engine extension** — justified by the gold-fed bound.
4. **Tier 2** (equality/functions) — a separate fragment decision, not a bug fix.

The staged plan is `docs/folio_extension_plan.md`; the plain-language explanation of
the ceiling and the ordered Tier-1 backlog are `docs/coverage_ceiling.md`.

## 8. Guardrails

- A new construct enters only as a **named fragment** under the declared-fragment
  contract (`docs/fragment_routing.md`): a `FragmentFeature`, a capability, a flag,
  a synthetic gate. Never an ad-hoc branch.
- **Never lower the semantics to pass a row.** Collapsing `∀x(Pet→¬Cat)` to the
  ground `¬is_a(pet,cat)` (G3) is not a solution; it proves a sound fact about the
  wrong target.
- A composite benchmark is never tuned per id; improvements come from the general
  extraction contract.

## 9. Non-goals

- A whole-collection FOLIO headline.
- Supporting full FOL or non-finite function terms.
- Ad-hoc construct hacks that bypass the fragment contract.

## 10. References

- `docs/implementation_plan.md` §10 — gating methodology on composite benchmarks.
- `docs/quality_findings.md` §G — FOLIO L2 backlog G1–G4 (extraction-bound).
- `docs/folio.md` §4–§10 — FOLIO notes, recon, L1/L2 live results.
- `docs/reasoning_roadmap.md` L2 — the stage and its risk.
- `docs/fragment_routing.md` — how a new fragment would be declared.
