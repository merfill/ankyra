# Pluggable Logic Layer — design note (future)

Whether and when to abstract the inference semantics so different logics can be
used in perspective. Canonical language: English; Russian mirror:
`docs/logic_layer_ru.md`. Related: `docs/defeasible_reasoning.md`.

## 1. Context

Today Ankyra has exactly one inference semantics: monotonic Horn forward chaining
with transitive `is_a` and an optional, range-restricted comparison layer
(`docs/task.md`, Phase 1). The roadmap includes defeasible/non-monotonic rules
(`docs/defeasible_reasoning.md`) and, speculatively, further semantics such as
answer-set (stable-model) or probabilistic reasoning.

## 2. Principle: separate concerns, not everything

Three concerns are currently mixed inside `engine/`:

- **Policy** — configuration: hypotheses allowed, builtins, deontic prefixes, wave
  budget. Orthogonal to the logic.
- **Mechanics** — unification, atom store, fixpoint loop, provenance plumbing.
  Largely shared by any deductive logic.
- **Semantics** — entailment, consistency, the shape of an answer and its
  justification. This is what varies per logic.

Only the **semantics** should become pluggable, and it should be abstracted
narrowly. Policy and mechanics stay where they are.

## 3. Do not abstract speculatively

With a single implementation, an interface is a guess and tends to be wrong.
The rule is to extract the seam when the **second concrete logic** lands
(defeasible). That implementation will show what actually varies; the Horn path
must not become harder to read in the meantime.

## 4. Stable vs varying

- **Stable (logic-agnostic):** Phase 0 decomposition, the guided cycle, the
  hypothesis ledger, proposal classification, explanation rendering, and the
  LangGraph orchestration.
- **Varying (the seam):** `entails`, `answer`, `justification`, `consistent`, and
  capability flags.

## 5. Proposed protocol (sketch, not yet implemented)

```python
class Inference(Protocol):
    def entails(self, theory: Theory, atom: Morphism) -> bool: ...
    def answer(self, theory: Theory, query: Query) -> Verdict: ...
    def justification(self, theory: Theory, query: Query) -> Justification: ...
    def consistent(self, theory: Theory) -> bool: ...
    # capabilities: supports_hypotheses, supports_builtins, multi_model
```

`engine/horn.py` becomes the first implementation (`HornInference`); the cycle,
nodes and classification depend on the protocol, not on `saturate`.

## 6. Contract requirements

- **Three-valued and multi-model answers.** WFS yields true/false/unknown; ASP
  yields a set of stable models (brave/cautious answers). Design `Verdict` and
  `Justification` to accommodate this *before* ASP, or the seam will not fit.
- **Justification.** The explanation and hypothesis accounting need the whole
  derivation (a proof tree today; arguments under argumentation semantics). Today
  that currency is `Fact.premises` / `used` / `rule_index` plus the ledger; the
  protocol must expose an equivalent, possibly richer, structure.
- **Entailment for classification.** `derivable` vs `cited`/`hypothesis` depends on
  whether a proposal is already entailed. `engine/classify._adds_new_facts`
  currently calls `saturate` directly — that is the main coupling to remove.

## 7. Migration plan

1. **B3 / B2** (`docs/quality_findings.md`) — explanation fidelity and rule
   provenance. Logic-agnostic prerequisites, needed by any semantics.
2. Implement **defeasible** as a second semantics behind a flag
   (`docs/defeasible_reasoning.md`).
3. **Extract the `Inference` protocol** from the two implementations; make
   `classify`, `nodes` and the cycle depend on it.
4. Optionally add ASP / probabilistic by implementing the same protocol, extending
   `Verdict`/`Justification` to the multi-model contract if that step is taken.

## 8. Non-goals and risks

- Premature abstraction; a generic layer that makes the simple Horn path opaque.
- Unifying justifications across very different logics (Horn proofs vs ASP
  arguments) can force a lowest-common-denominator structure.
- Performance: the indirection must not cost the single-logic path.
- **Product scope:** if only Horn + defeasible are ever needed, the protocol is a
  thin, optional seam, not a framework.

## 9. Open question

Is a pluggable logic layer a **near-term** need (several semantics are planned) or
**speculative** (one Horn core plus defeasible will suffice)? Decide before
extracting the protocol; until then this note is a placeholder, not a task.
