# Statement sources — origin vs logical role (design note)

Where every assertion in Ankyra comes from, and why "where it came from" must stay
separate from "how it behaves in inference". Canonical language: English; Russian
mirror: `docs/statement_sources_ru.md`. Related: `docs/logic_layer.md`,
`docs/task.md` (§3, §5), `docs/defeasible_reasoning.md`.

## 1. Context

An assertion in Ankyra can originate from several places:

- the **description text** — a cited axiom (`Theory.morphisms` with a quote);
- the **question itself** — a presupposition / condition, i.e. Gamma (`Query.conditions`);
- the **LLM's abduction** — a tagged hypothesis (the ledger, `proven_under(H)`);
- in the future, **external sources** — a knowledge base, a previous wave, a user
  correction, another engine.

Provenance exists today but is scattered: `Morphism.quote`, `Rule.source ∈
{quote, hypothesis:<id>}`, the `Hypothesis` ledger, `Query.conditions`, `Fact.axiom` /
`Fact.rule_index` / `Fact.witness` / `Fact.used`, `ExplanationStep.source`,
`Answer.hypotheses_used`, `Revision.source_ids`. There is no single vocabulary for
"where did this statement come from".

## 2. Principle: origin does not decide reasoning

Two axes must stay orthogonal:

- **Logical role** — decides what reasoning does. Is it a strict axiom, a defeasible
  default, or a non-axiom assumption? Does it enter the theory or stay a query
  condition?
- **Origin** — an audit label: where the statement came from.

Collapsing them into one tag breaks concrete behavior:

- `insufficient` exists precisely because a **question condition** is *not* a theory
  axiom; unused conditions are reported (`unused_premise:`) while unused theory facts
  are not. Folding Gamma into the theory would erase the honest status.
- Defeasibility distinguishes **axioms** (`axiom=True`, strict) from **assumptions**
  (`axiom=False`): a strict fact defeats a conflicting default, an assumption does not
  (`engine/defeasible.py` `_resolve`). A single "source" tag that decided both would
  lose this.

So: origin is metadata for explanation and accounting; it must never feed the
closure.

## 3. Current taxonomy

| origin | logical role | enters theory? | answer strength |
|---|---|---|---|
| `cited` (text quote) | axiom, strict | yes | no effect |
| `presupposition` (Gamma) | assumption (`axiom=False`) | **no** | no effect (used → part of the input; unused → `insufficient`) |
| `hypothesis` (LLM) | default, tagged | yes | `proven_under(H)` |
| `external:<source>` (future) | policy per source | depends | depends |

## 4. Proposed narrow design

1. **Keep the logical role explicit** in the engine: `Fact.axiom` plus rule strength
   (strict/defeasible). Do not hide it behind a source label.
2. **Add a small audit tag** — `SourceKind ∈ {cited, presupposition, hypothesis,
   external}` + an id and optional `meta` (wave number, source name). It flows only
   into `Explanation` and `Answer` accounting, never into unification or firing.
3. `ExplanationStep.source` (today `quote` / `hypothesis`) widens to this enum, so a
   step can be attributed to the description, to a question condition, to a named
   hypothesis, or to an external source. `Answer`/`Explanation` may then report a
   breakdown: proved from the text / resting on a question presupposition / under
   hypotheses `H1,H2` / from external source X.

Wave attribution already exists (`Hypothesis.wave`, `Revision.source_ids`) and plugs
into the same tag.

## 5. Non-goals and risks

- **No plugin registry / source framework.** As with the logic layer, do not abstract
  speculatively; three concrete origins plus one anticipated (`external`) justify a
  narrow enum, not an extensible engine.
- **Not the same as pluggable inference semantics** (`docs/logic_layer.md`): sources
  are provenance/accounting; inference is entailment. Keep them separate.
- Lowest-common-denominator risk: a single enum must not flatten the strict/assumption
  distinction (§2).

## 6. First concrete step

Attribute explanation steps grounded on Gamma as `presupposition`. Today the only
trace of a question premise is the `unused_premise:` gap; a used question condition is
invisible in the explanation. Doing this fixes the immediate visibility gap **and**
fixes the enum's shape so `external` can be added later without a breaking change.

**Status:** implemented — `engine/explain.py` tags Gamma-grounded steps with
`source="presupposition"` and a **fact** hypothesis now carries
`source="hypothesis:<id>"` (previously only rule hypotheses did), so every step names
its origin. `ExplanationStep.source` documents the origins. The world-expansion tests
(`tests/test_engine_world_expansion.py`) pin this behavior.

## 7. Open question

Is the `external` origin concrete enough to shape the enum now, or should it stay a
three-value enum (`cited` / `presupposition` / `hypothesis`) until the first external
source lands? Decide when that source becomes a real requirement; until then this note
is a design placeholder, not a task.
