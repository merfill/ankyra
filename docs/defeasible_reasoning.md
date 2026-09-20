# Defeasible Reasoning — design note

How to handle exceptions and defaults (non-monotonic reasoning) in Ankyra's
monotonic Horn engine. Canonical language: English; Russian mirror:
`docs/defeasible_reasoning_ru.md`.

## 1. The problem

The engine is monotonic: facts and rules only accumulate, and a derived atom is
never retracted. But natural-language rules come in two flavours:

- **strict** — "all men are mortal", "a sedan is a car": definitional, no exceptions;
- **defeasible** — "birds fly": a default that admits exceptions ("penguins do not fly").

With a monotonic engine the default and the exception both fire and produce a
contradiction. Example (L3 `evals/problems.jsonl`):

```
Birds can fly. Penguins are birds, but penguins cannot fly. Tweety is a penguin.
```

Theory: `is_a(?x,bird) => fly(?x)` and `is_a(?x,penguin) => ¬fly(?x)`.
Closure derives both `fly(tweety)` and `¬fly(tweety)` → `refuted` / `not_proven`.
The honest refusal is sound, but not useful.

## 2. Why "negation wins" is wrong

A naive priority "negation overrides affirmation" fails immediately on the
inverse case:

```
Birds cannot fly. Penguins can fly. Tweety is a penguin.
```

Here the correct answer is "yes", but negation-priority would pick `¬fly`. The
principle that works in **both** directions is **specificity / defeat**: the more
specific piece of knowledge overrides the more general one, regardless of its
polarity. In both examples the penguin rule is more specific than the bird rule,
so it wins — whichever sign it carries.

## 3. Standard semantics (map)

| approach | idea | strength | cost |
|---|---|---|---|
| Negation as failure (CWA) | conclude `C` unless `¬C` is derivable | direction-agnostic, simple | needs careful stratification |
| Default logic (Reiter) | `premise : justification / conclusion`; extensions | precise | multiple extensions, fixed points |
| Answer Set Programming | stable models; `not` in the body | expressive, ground truth | new solver, ASP semantics |
| Well-Founded Semantics (WFS) | unique three-valued model (true/false/unknown) | always defined, unique | alternating-fixpoint algorithm |
| Defeasible logic (Nute) | strict + defeasible rules, priorities | designed for this exact case | priority/specificity bookkeeping |
| Argumentation (Dung) | arguments + attack, grounded/preferred semantics | handles conflicts uniformly | argument/attack construction |
| Circumscription / autoepistemic | minimise abnormality / introspection | theoretical | hard to operationalise |
| Probabilistic | distribution over conclusions | graded confidence | different product semantics |

There is **no single "correct" semantics** — it is a design choice. The task is to
pick one that is standard, sound, and fits the existing engine.

## 4. Mapping onto Ankyra

- `Rule.kind` stays `implication | exception`. **Every rule is a default**
  (`Rule.strength` is always `defeasible`); only asserted facts/axioms are strict.
  Neither the LLM nor a predicate heuristic decides: an `is_a` conflict is resolved
  by specificity like any other, and reported undecided when it cannot be. This
  avoids mis-classifying property defaults that extraction happens to phrase with
  the `is_a` predicate (e.g. "Quakers are pacifists").
- Provenance already exists: every derived atom carries `premises` / `used` /
  `rule_index`, and `Hypothesis` records assumptions. Conflicting conclusions are
  two proof trees; specificity decides which one defeats the other.
- `is_a` transitive closure already exists and is exactly the specificity oracle:
  rule head about `C1` is more specific than one about `C2` when `is_a(C1, C2)`.
- Statuses map naturally to a three-valued semantics:
  `true → supported`, `false → refuted`, `unknown → unsupported`.
- Answer carries `Answer.defeasible` so the user knows a default (not a strict
  fact) was applied.

## 5. Decision (implemented behind `ANKYRA_DEFEASIBLE`)

Adopt **defeasible logic realised as negation-as-failure over a strict Horn core,
with specificity from `is_a`, evaluated under well-founded semantics**:

1. **Asserted facts** (and the `is_a` closure over them) keep the monotonic Horn
   closure (sound, terminating); every rule is a default.
2. **A default rule** fires only if its head is not contradicted by a strict fact
   or by a *more specific* conflicting application.
3. **Specificity** compares the class conditions of the competing applications via
   `is_a`; a strictly more specific rule defeats a more general one, in either
   polarity.
4. **Unresolved conflicts** (equal or incomparable specificity) are reported
   honestly as `unsupported` with an `undecided_conflict:` gap, never guessed.
5. Results are three-valued, matching the existing status vocabulary.

Rationale: this is the minimal standard mechanism that handles both directions,
reuses the existing `is_a` hierarchy and provenance, and does not require a new
solver.

## 6. Algorithm (`engine/defeasible.py`)

```
effective_closure(theory, assumptions):
    strict = saturate(theory, assumptions, strengths={"strict"})   # + is_a closure
    accepted = {}
    repeat:                                                       # bounded alternating fixpoint
        base = strict ∪ accepted
        order = transitive is_a order over base
        candidates = all grounded rule applications (every rule is a default)
        accepted, unresolved, defeats = resolve(candidates, strict, order)
    until accepted is stable
    return strict ∪ accepted, unresolved, defeats
```

Resolution: a head already in strict, or whose negation is in strict, never enters
by default (NFA: strict overrides). For each `P` / `¬P` pair, a candidate is
defeated when the opposing side has a **strictly more specific** application;
if one side alone survives it is accepted, otherwise the pair is *unresolved* and
neither is accepted.

**Specificity is computed over the provenances of the two rule applications**: the
class atoms (`is_a(subject, class)`) among the directly matched body facts are
compared through the strict `is_a` order. Candidate applications are enumerated by
matching rule bodies against the closure (not read from a single stored proof), so
an atom with several derivations does not hide the class-carrying one.

## 7. Provenance and explanation

- `refuted` shows the negative branch; a strict `contradiction` shows **both**
  branches in `Explanation.conflict` (backlog B3, done).
- A **resolved** defeasible win attaches `Explanation.conflict`
  (`kind=defeasible`, `status=resolved`, `defeated=attacking`) with the defeated
  rule and `reason` = the `is_a` witness (e.g. `penguin is-a bird`).
- An **undecided** conflict shows both competing rules
  (`status=undecided`, `defeated=none`) and `reason` = why specificity failed
  (e.g. `no is_a relation decides between quaker and republican`); the goal carries
  the `undecided_conflict:` gap.
- The LLM narrative does not choose: the narration prompt is told to follow the
  trace and to say plainly when a conflict could not be resolved.
- `materialize_rule_morphisms` is gone (backlog B2), so defeated and defeating
  rules can appear in the trace.

## 8. Invariants and compatibility

- Monotonicity (D3) is preserved for the **strict core**; the defeasible layer is a
  separate, auditable *effective closure* on top, not a mutation of the theory.
- The feature is gated by a flag (e.g. `ANKYRA_DEFEASIBLE`, default off) so the
  current behaviour remains the baseline.
- Soundness is unchanged: no conclusion is emitted without a proof tree; conflicts
  that cannot be resolved by specificity are left `unsupported`.

## 9. Phased plan (done)

1. **B3** — explanation branches on status; negative proof and both-branch
   `contradiction` conflict. Done.
2. **B2** — rule provenance preserved; silent contradiction healing removed. Done.
3. All rules are defaults, facts/axioms strict; neither extraction nor a predicate
   heuristic authors strength. Done.
4. Defeasible evaluation layer (NFA + specificity) behind `ANKYRA_DEFEASIBLE`. Done.
5. Three-valued statuses, `Answer.defeasible`, conflict explanations. Done.
6. Eval cases `exception`, `defeasible_reverse`, `diamond`. Done.
7. All rules are defaults, only asserted facts are strict; resolved defeats carry
   their `is_a` witness as the reason. Done.
8. **Synthetic gate.** `evals.build_defeasible_synthetic` commits
   `evals/data/defeasible_synthetic.jsonl` (8 cases: resolved specificity both
   polarities, undecided Nixon diamond, strict-over-default, no-conflict, and a
   layer-off control), run by `evals.defeasible_synthetic` with `ANKYRA_DEFEASIBLE`
   per case. **8/8 green (LLM-free).** This closes the "implemented but
   unbenchmarked" status from `docs/reasoning_roadmap.md` D; the AlphaNLI/defeasible
   NLI collection remains a future real-data cross-check.

## 10. Open questions / risks

- **Termination**: the fixpoint is capped (`_MAX_ITERATIONS`); the universe is
  finite. Reporting a `budget` status on exhaustion is not yet wired.
- **Missing hierarchy**: without `is_a` between the competing classes, specificity
  is undefined → the pair stays unresolved (honest unknown, no guessing).
- **Specificity is polarity-local**: it compares classes only when the competing
  body facts share their subject; a conflict expressed through unrelated predicates
  (e.g. `militarist` vs `pacifist` with no explicit negation) is invisible.
- **No strict rules**: a definitional rule can in principle be overridden by a more
  specific default. Strictness belongs to asserted facts; a real taxonomy can still
  be asserted as facts rather than derived by rules.
- **Product semantics**: this is a deliberate choice, not a fact; it should be
  recorded and revisited if the product needs graded or probabilistic answers.
