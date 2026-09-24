# How Ankyra Works — A Conceptual Overview

Ankyra is a domain-general hybrid neuro-symbolic reasoning engine. Given a
self-contained natural-language problem — a set of conditions and a question — it
produces a step-by-step, mechanically verifiable reasoning trace and an answer with
an explicit logical status. Its governing principle is:

> **The language model proposes; the symbolic engine decides.**

This document explains the design as a whole: who the two participants are, how a
problem travels through the system, which engines exist, how the reasoning cycle
works, how a procedure is chosen, and what the engine does and does not guarantee.
It is the conceptual companion to `ARCHITECTURE.md` (module map), `docs/task.md`
(technical specification) and `docs/reasoning_roadmap.md` (the staged logics).

## 1. The idea: two participants, one truth

Reading a natural-language problem and translating it into a precise formal
language is what large language models do well. Deriving consequences soundly,
tracking exactly which premises were used, and refusing to guess are what symbolic
procedures do well. Ankyra gives each side the job it is good at and keeps them
apart.

The model reads the text and speaks two languages: it decomposes the problem into a
*structure* (objects, facts, rules, quotes) and, while the answer is still open, it
proposes additional steps. The symbolic engine owns the *formal* side: it turns the
structure into a theory, closes it by deduction, matches the question against it,
and certifies what follows.

The dividing line is absolute. **The model never owns truth.** It may name
predicates and propose rules freely, but nothing enters the theory unless the engine
can licence it — either by a verbatim quote from the text or by an explicit tag that
marks the statement as an assumption rather than a fact.

## 2. The proposal contract

Every statement the model wants to add is classified deterministically. The
classification is not a judgement call; it depends only on whether the statement is
already entailed, whether it is grounded in the text, or whether it is an
assumption.

| Category | Condition | What the engine does |
|---|---|---|
| `derivable` | already entailed by the current theory | accepts it as narration only |
| `cited` | a new statement backed by a verbatim quote from the text | adds it to the axioms |
| `hypothesis` | knowledge not present in the text | records it in the ledger, tagged `H` |
| `rejected` | fails a schema, safety or quote check | drops it with a reason code |

The distinction between `cited` and `hypothesis` is what makes answers honest. A
conclusion that uses only quoted facts is **`proven`**. A conclusion that leans on
assumptions is **`proven_under(H)`** and names those assumptions. If nothing is
established, the answer is **`not_proven`**. An answer is therefore never stronger
than the evidence behind it, and an assumption can never masquerade as a fact.

## 3. The path of a problem: four phases

A problem passes through four phases. The first does the translation, the second
does the deduction, the third fills the gaps that the model can close, and the
fourth turns the derivation into a readable trace.

```
natural-language problem
        │
        ▼
Phase 0 — decompose      two model calls + a deterministic builder
        │                (build/): structure ─▶ Theory + Query
        ▼
Phase 1 — decide         the symbolic engine derives to a fixed point
        │                (engine/)
        ▼
Phase 2 — guided cycle   while unresolved: propose → classify → verify
        │                (engine/cycle.py, engine/nodes.py)
        ▼
Phase 3 — explain        mechanically from the proof's history
        │                (engine/explain.py)
        ▼
reasoning trace + answer + status
```

### Phase 0 — decomposition

The text is split into a descriptive part and an interrogative part, and the two
are treated as separate artifacts from this point on. **The question is never
asserted as a fact.**

Two model calls follow, in a fixed order, because the question must be expressed in
the vocabulary the theory has already established:

1. `extract_problem_structure` — the model decomposes the descriptive part
   *structurally* only: which objects exist, which facts and conditionals are
   stated, how alternatives and groupings are written, where negations and
   modalities sit, and a short verbatim quote for each. It does not write finished
   logical formulas; the combinatorics are left to deterministic code.
2. `extract_question_structure` — the model expresses the question over the
   theory's canonical predicates and objects, producing a target (a constant, a
   variable for genuinely open questions, or nothing for an instruction) together
   with any conditions the question itself asserts.

Between and after these calls, a deterministic builder (`build/`) assembles the
`Theory` and the `Query`:

- `unroll` expands groupings and alternatives into individual atoms, carries
  modality as a typed field rather than baking it into a predicate name, and builds
  rules; an ascription ("Gary is cold") becomes an `is_a` relation in both facts and
  rules, so the two can meet.
- `enrich` canonicalises polarity, removes duplicates, materialises rule
  consequences, heals self-contradictory rules and drops malformed atoms.
- `symbolic_check` and `enforce_grounded` verify that every quote is a real
  substring of the source; anything whose quote cannot be found is discarded. This
  is the mechanical enforcement of "no model-owned facts".
- `settle_query` turns the question's facts into conditions (`Gamma`), its `ask`
  into the target (`phi`), derives the answer type, drops an echo of the goal, and
  removes premises that play no role.

The result is a formal theory plus a formal question, both expressed over the same
vocabulary, with every element traceable to a quote.

### Phase 1 — decide

The symbolic engine takes over. It derives all consequences of the theory to a
fixed point and checks whether the target follows. Every derived fact carries its
history: which facts directly produced it, which rule fired, and a witness. The
engine adds no knowledge of its own; it is sound and complete *relative to the
formalization it was given*.

### Phase 2 — guided cycle

If the theory as built does not yet settle the question, the engine does not stop at
a bare "unknown". It reports exactly where it is stuck, and the model gets a bounded
chance to help — by proposing one step at a time. This is the guided reasoning
cycle, described in detail in §5.

### Phase 3 — explain

Once the answer is settled, the reasoning trace is assembled **mechanically** from
the proof's history — not by the model. The trace is an ordered list of steps, each
naming the rule that fired, the bindings it used, and the quote or hypothesis that
licences it. The model may later paraphrase this finished trace into fluent prose,
but it may not introduce new facts. The explanation is a rendering of the proof, not
a second opinion about it.

## 4. The data model in one paragraph

Everything the engine reasons about is built from a few small pieces. An `Object` is
a canonical named entity. A `Morphism` is a single relation — a predicate applied to
a subject and an object — carrying its modality and whether it is negated; negation
is the same predicate flagged as false, never a separate name. A `Rule` is a
conditional: a conjunction of conditions implying a consequence, marked as an
implication or an exception, and carrying its source (a quote or a hypothesis id). A
`Theory` collects objects, asserted morphisms and rules. A `Query` holds the
conditions the question asserts (`Gamma`), the target it asks about (`phi`), and its
answer type. Inside the engine, a `Fact` is a ground atom plus its history. The
Phase 0 structures the model actually authors are separate and deliberately loose:
roles can hold a single filler, a conjunction (`set`), a disjunction (`variants`) or
an exclusion, and the deterministic builder turns them into the precise pieces
above.

## 5. The reasoning cycle

The inner loop of the cycle is purely deterministic. Only the *proposal* is a model
call. The cycle alternates a hint, a free-form proposal, and a deterministic
classification, and it accepts at most one proposal per wave — so every wave leaves
an auditable trace.

Each wave proceeds as follows:

1. **Verify.** The engine closes the current theory and checks the target, producing
   a verdict and a set of structured gaps (for example `target_unmatched:` when the
   goal predicate appears nowhere, or `unused_premise:` when a condition the
   question supplied was not needed).
2. **Terminal check.** If the verdict is already decisive — `supported`, `refuted`,
   `contradiction`, `insufficient` — the cycle stops.
3. **Assemble the hint.** The model receives the problem structure, the theory's
   allowed predicates and objects, a summary of what has been derived so far, the
   current gaps, the target, and the kinds of proposal it may make.
4. **Propose.** The model returns a short narration plus exactly one typed proposal:
   re-express the question in the theory's vocabulary, add a rule, assert a quoted
   fact, or choose the next subgoal.
5. **Classify and apply.** The engine checks the proposal against the schema,
   safety rules and the text, assigns it one of the four categories from §2, and
   applies or drops it. Application is monotonic: the theory only grows.
6. **Record.** The wave is written to the history, the inner loop re-runs, and the
   cycle begins again.

The cycle stops on a decisive verdict, on `no_progress` (two consecutive waves that
change nothing), on the wave budget (`ANKYRA_MAX_WAVES`), or when assumptions are
forbidden and none may be added. None of these outcomes is a failure of soundness:
each is an honest stopping point.

**Monotonic base, moving answer.** The *base* — axioms, rules, hypotheses — only
grows: premises are never deleted and the target is never weakened. The *answer* may
nevertheless change as new information arrives. Such changes are not hidden; each
one is recorded as a `Revision` naming the triggering wave and the assumptions
involved, and the revisions travel with the explanation. This is how the system
stays auditable under non-monotonic reasoning without ever mutating its base.

## 6. The engines

Ankyra is not a single monolithic solver. It is an **orchestrator of formalizations
and decision procedures**: for each problem the model produces a formalization in
some logic, and a sound procedure for that logic decides it. Different kinds of
problems call for genuinely different procedures, each with its own internal
representation. The stages below are the named logics the engine currently covers;
the full development plan is `docs/reasoning_roadmap.md`.

| Stage | Logic | What it decides | Procedure | Flag |
|---|---|---|---|---|
| L0 | definite Horn clauses, `is_a`, negation as complementary pairs | facts, subclass relations, "supported / refuted" in the open world | semi-naive forward chaining to a fixed point | — (always on) |
| L1 | stratified negation, negation-as-failure, declared closed world | disjointness and explicit negative knowledge; "not stated, therefore not holding" when declared | stratified closure | `ANKYRA_NEGATION_MODE` |
| L2 | positive first-order fragment: disjunction, `∃`/`∀`, equality | entailment and refutation with case analysis | bounded resolution over ground clauses | `ANKYRA_LOGIC` |
| L3 | finite-domain constraints (CSP/SAT) | "must" (true in every model) and "could" (true in some model) | in-repo finite-domain search | `ANKYRA_CSP` |
| L4 | arithmetic terms and equations | a numeric answer | exact evaluation and linear elimination over rationals | `ANKYRA_ARITH` |
| D | defaults with specificity | an answer together with a resolved or undecided conflict | the defeasible layer | `ANKYRA_DEFEASIBLE` |

### L0 — definite Horn (the spine)

This is the baseline everything else extends. Its logic is definite clauses over
unary and binary atoms, a transitive `is_a` relation, and negation only as
complementary pairs `P` / `¬P` in an open world. Its procedure is `saturate`:
semi-naive forward chaining, in which rules fire until nothing new is produced.
`verify` then sorts the outcome into four statuses — the target follows
(`supported`), the target follows but some question condition went unused
(`insufficient`), nothing matched (`unsupported`), or the target's complement
follows (`refuted`, i.e. a "no"). An optional comparison layer
(`ANKYRA_BUILTINS`) adds numeric and string comparisons as *filters over bound
values*, never as facts matched against the theory.

The Horn spine is also the substrate for two extensions: the negation layer (L1) and
the default layer (D), both described below.

### L1 — stratified negation and the closed world

The same Horn engine gains a second kind of statement: negative constraints that
declare two properties disjoint, and negated goals evaluated by
**negation-as-failure**. Under the open world, a goal that cannot be proved is
simply unknown. Under a declared **closed world** — a semantic choice attached to
the query, never guessed from the wording — an unprovable atom is taken to be false.
The engine stratifies the rules by dependency and evaluates negated goals only after
the stratum they depend on; a program that cannot be stratified is reported as
outside the fragment rather than decided. This is what lets Ankyra answer "no"
because a category is disjoint from another, or because the text explicitly says so,
rather than by accident.

### D — defaults and specificity

Behind `ANKYRA_DEFEASIBLE`, every rule becomes a default and only asserted facts are
strict. The engine first computes the strict closure, then resolves competing
defaults by **specificity**: a more specific class overrides a more general one
along the `is_a` hierarchy. If specificity cannot decide — the two rules are equally
specific or incomparable, the classic "Nixon diamond" — neither branch wins and the
result is an honest `undecided` conflict, not a guess. Whether an answer depended on
a default is reported explicitly.

### L2 — disjunction, quantifiers and proof by cases

When a problem needs genuine disjunction, existential or universal quantification,
or proof by contradiction, the Horn engine is replaced by a clausal one. A theory is
lowered into **ground clauses** over its finite domain: facts become unit clauses,
each rule becomes the clause "not body or head", and existential premises are
Skolemised with fresh constants. A bounded **set-of-support resolution** procedure
then searches for a contradiction, with an explicit step budget. Within that budget
it can split into cases and reason through disjunctions, instantiate quantifiers by
enumerating the finite domain, and decide equality over the named individuals. When
the budget runs out without a proof, the answer is the honest `insufficient` — the
logic is only semi-decidable, so exhaustion must never be mistaken for refutation.
The procedure carries proof histories too, so case splits appear in the explanation.
The `ANKYRA_LOGIC` flag is off by default, because this engine substitutes for the
Horn one rather than layering on top of it.

### L3 — finite-domain constraints (a separate engine)

Analytical-reasoning problems ("arrange these items under these conditions") are not
logical entailment; they are constraint satisfaction. This engine is therefore
separate, with its own representation: finite domains of values, and constraints such
as all-different, ordering, adjacency, grouping, counting and conditionals. The
question is decided by search over the finite domain — "must be true" means true in
every model, "could be true" means true in some model. It is reached through
`ANKYRA_CSP`.

### L4 — exact arithmetic (a separate engine)

Arithmetic word problems produce a number, not an entailment. This engine is also
separate: it models the problem as a directed graph of defined quantities and
solves the resulting linear system over exact rationals, with exact maximum and
minimum. Because the arithmetic is exact, an arithmetic error is impossible by
construction; the engine can only be *incomplete* about the model, in which case it
reports `underdetermined`, `inconsistent` or `out_of_fragment` rather than a
fabricated number.

### What the engines share

Every engine is **sound with respect to the formalization it was given**, and every
one of them abstains honestly rather than guessing. The symbolic layers are designed
to be complete relative to the formalization too — forward chaining reaches a fixed
point — but completeness of the *translation* is not claimed: a model can always
miss a premise in the text. That is why the distinction between a wrong answer and a
missing one is preserved everywhere.

## 7. Choosing a procedure: the declared fragment

Because the engines differ, the system must decide which one runs — and it must do so
without ever guessing. The answer is a **declared-fragment contract**
(`docs/fragment_routing.md`).

The engine inspects the *built* theory and query and derives the set of features
they require: is there a disjunctive head, an existential, a compound goal,
negation, a builtin, equality? That is the **fragment** — an objective property of
the formalization, not an intention. Separately, the run *declares* its semantics:
which procedures are enabled (the `ANKYRA_*` flags) and whether the query is read
under an open or closed world. A routing decision combines the two and validates
them against each other.

If the fragment is within the enabled capabilities, the corresponding procedure is
selected. If not — the structure needs a logic the run has not enabled, or asks for a
combination a chosen procedure cannot honour — the result is a named
**`out_of_fragment`** gap, never a silent downgrade to a weaker procedure. The seam
through which all this happens is the `Inference` protocol
(`engine/inference.py`): the semantics — entailment, the shape of a verdict, the
closure a proposal is classified against — is pluggable, while policy (which
procedure to use) and mechanics stay where they are. Today it has a Horn
implementation and a clausal one.

## 8. What "proven" means: honesty by construction

The value of the system rests on a small number of guarantees, each enforced
mechanically rather than by good intentions:

- **No model-owned facts.** A statement enters the theory only with a real quote or
  an explicit hypothesis tag. Quotes are checked as literal substrings of the
  source.
- **The question is never a source.** A quote taken from the interrogative part of
  the text cannot license a fact, a statement that appears only inside a conditional
  cannot be asserted as a fact, and an assumption may not simply restate the goal.
  The engine cannot prove a target by citing or assuming the target.
- **No natural-language parsing in deterministic code.** The builder may normalise
  identifiers and closed enum fields the model has already produced, but it never
  inspects the raw text for cue words, morphology or hand-written term lists. All
  meaning comes from the extraction step; deterministic code only operates on
  structured output and on structural checks of quotes.
- **Grounded refutation.** Assuming `P` cannot refute `¬P`. A refutation supported
  only by a hypothesis is reported as the honest `unknown`, not a definite "no".
- **Contradiction is distinguished from inconsistency.** A complementary pair on the
  target's own proof is a contradiction; an inconsistency elsewhere in the theory is
  reported as a gap and does not silently change the answer.
- **No silent strengthening.** An answer that used assumptions is always marked
  `proven_under(H)`; an answer that used none is `proven`; otherwise it is
  `not_proven`.

Together these mean that "proven" is not a confidence score. It is a statement about
the proof: the conclusion follows from quoted material by sound steps, and the trace
of those steps is available.

## 9. Orchestration and configuration

The whole pipeline is a single LangGraph `StateGraph` over one shared state object:

```
START → extract_problem → build_theory → extract_question → build_query
      → verify → (propose → classify → verify)* → explain → END
```

The same node functions are also driven linearly by `engine/cycle.py`, so there is
exactly one implementation of every step; only the orchestration differs. Routing
functions are pure, and every status is committed by a node rather than mutated
inside an edge. `run_problem` is the end-to-end entry point; `run_cycle` exposes the
reasoning cycle alone for callers that already have a theory and query.

Configuration is Dynaconf under the `ANKYRA_` prefix. The flags that shape reasoning
are:

| Flag | Default | Effect |
|---|---|---|
| `ANKYRA_MAX_WAVES` | `8` | maximum number of reasoning waves |
| `ANKYRA_ALLOW_HYPOTHESES` | `true` | whether assumptions may be added |
| `ANKYRA_NEGATION_MODE` | `open` | default world assumption for L1 |
| `ANKYRA_LOGIC` | `off` | enable the clausal L2 procedure |
| `ANKYRA_LOGIC_BUDGET` | — | resolution step budget |
| `ANKYRA_DEFEASIBLE` | `off` | enable the defeasible layer |
| `ANKYRA_BUILTINS` | `false` | enable the comparison filter layer |
| `ANKYRA_CSP` | `off` | enable the finite-domain CSP engine |
| `ANKYRA_ARITH` | `off` | enable the numeric engine |
| `ANKYRA_EXTRACT_SAMPLES` | `1` | number of extraction attempts |
| `ANKYRA_LANGUAGE_SPEC` | empty | optional notation guide for a collection |

## 10. How it is checked

Coverage is measured in **named formalisms**, never in untethered "reasoning". Every
stage is gated by an external benchmark with a small committed sample and hard
invariants: zero grounded false proofs, every determinate answer `proven`, and every
remaining failure categorised. The gates form a ladder:

1. **LLM-free synthetic collections** exercise the semantics directly, with no
   extraction and no provider variance — the pure engine signal.
2. **A simple-surface real collection** (for example ProntoQA for L1 and
   ProntoQA-OOD for L2) adds real text over a clean notation.
3. **A hard real collection slice** (FOLIO) is deliberately extraction-heavy.

Across the ladder, a **gold-fed** run — feeding the engine hand-written formal
formulas instead of extracted ones — separates two different limits. *Coverage* is
how many problems the committed logic can express at all; exceeding it is an honest
`out_of_fragment` that costs recall, never soundness. *Extraction* is how many of the
covered problems the model translates correctly. Keeping these apart is what tells
us whether an improvement must come from the engine or from the interface. The
current stage-by-stage results and their gates are recorded in
`docs/reasoning_roadmap.md` and `README.md`.

## 11. Glossary

- **Atom / morphism** — a single relation, a predicate applied to a subject and an
  object, possibly negated and carrying a modality.
- **Rule** — a conditional: a conjunction of conditions implying a consequence.
- **Theory** — the formalized descriptive part of the problem: objects, asserted
  atoms and rules.
- **Query** — the formalized question: its conditions (`Gamma`), its target
  (`phi`), and its answer type.
- **Closure / saturate** — the set of all facts derivable from the theory, computed
  to a fixed point.
- **Provenance** — the recorded history of a derived fact: which facts and rule
  produced it.
- **Hypothesis** — a statement not present in the text, recorded in the ledger and
  tagged; answers that use one are reported as `proven_under`.
- **Fragment** — the set of logical features a built theory and query require.
- **`out_of_fragment`** — an honest refusal to decide, because the structure needs a
  logic the current run does not provide.
- **CWA (closed-world assumption)** — the declared choice to treat an unprovable
  atom as false.
- **NAF (negation as failure)** — deriving a negative conclusion from the failure to
  prove its positive counterpart, under a declared world assumption.
- **Specificity** — the relation by which a more specific default defeats a more
  general one, based on the `is_a` hierarchy.
- **Grounded false proof** — an answer that is certified with certainty yet is wrong
  according to the benchmark's own formalization; the invariant every gate forbids.

## 12. Where to read more

- `ARCHITECTURE.md` — layers, module map and the code-level flow.
- `docs/task.md` — the technical specification, invariants and data model.
- `docs/reasoning_roadmap.md` — the staged logics and their benchmark gates.
- `docs/fragment_routing.md` — the declared-fragment contract in full.
- `docs/logic_layer.md` — the pluggable inference seam.
- `docs/defeasible_reasoning.md` — defaults and specificity.
- `docs/statement_sources.md` — origin versus logical role of a statement.
- `docs/doxa_and_logos.md` — the conceptual foundation: the non-formalizable
  source (doxa) and the formal functions through which it interacts with the engine.
