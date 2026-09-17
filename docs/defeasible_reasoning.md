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

- `Rule.kind` today is `implication | exception`. Proposal: keep `kind` for the
  implication/exception shape and add a **strength** flag `strict | defeasible`.
  The extraction prompt decides it: definitional/universal statements are strict,
  generic defaults ("birds fly") are defeasible.
- Provenance already exists: every derived atom carries `premises` / `used` /
  `rule_index`, and `Hypothesis` records assumptions. Conflicting conclusions are
  two proof trees; specificity decides which one defeats the other.
- `is_a` transitive closure already exists and is exactly the specificity oracle:
  rule head about `C1` is more specific than one about `C2` when `is_a(C1, C2)`.
- Statuses map naturally to a three-valued semantics:
  `true → supported`, `false → refuted`, `unknown → unsupported`.
- Answer strength: add a `defeasible` marker so the user knows a default (not a
  strict fact) was applied.

## 5. Decision (proposed)

Adopt **defeasible logic realised as negation-as-failure over a strict Horn core,
with specificity from `is_a`, evaluated under well-founded semantics**:

1. **Strict rules** keep the monotonic Horn closure (sound, terminating).
2. **Defeasible rules** fire only if their head is not contradicted by a strict
   fact or by a *more specific* defeasible rule.
3. **Specificity** compares the classes in rule heads via `is_a`; a strictly more
   specific rule defeats a more general one, in either polarity.
4. **Unresolved conflicts** (equal or incomparable specificity) are reported
   honestly as `refuted` / `unsupported`, never guessed.
5. Results are three-valued, matching the existing status vocabulary.

Rationale: this is the minimal standard mechanism that handles both directions,
reuses the existing `is_a` hierarchy and provenance, and does not require a new
solver.

## 6. Algorithm sketch

```
effective_closure(theory):
    strict = saturate(strict_rules, strict_facts)          # monotonic, + is_a
    defeasible = set()
    repeat:
        for rule in defeasible_rules:
            if body is satisfied by strict ∪ defeasible:
                head = instantiate(rule)
                if contradicted_by_strict(head):        # NFA
                    continue
                if defeated_by_more_specific(rule, head, strict ∪ defeasible):
                    continue
                defeasible.add(head)
    until fixpoint                                          # WFS alternating fixpoint
    return strict, defeasible
```

`defeated_by_more_specific`: find a competing conclusion `¬head`; compare the
head class of the competing rule with this rule's head class via `is_a`; if the
competitor is strictly more specific, this rule is defeated.

## 7. Provenance and explanation

- A `refuted` goal should show **both** branches (the supporting and the
  attacking derivation) — this is item B3 in the backlog; it is a prerequisite for
  making defeasibility legible.
- A defeasible conclusion carries its rule and the exception that was set aside,
  so the explanation can say "by default, unless …".
- `materialize_rule_morphisms` must stop hiding rules (backlog B2), otherwise the
  defeated/defeating rules never appear in the trace.

## 8. Invariants and compatibility

- Monotonicity (D3) is preserved for the **strict core**; the defeasible layer is a
  separate, auditable *effective closure* on top, not a mutation of the theory.
- The feature is gated by a flag (e.g. `ANKYRA_DEFEASIBLE`, default off) so the
  current behaviour remains the baseline.
- Soundness is unchanged: no conclusion is emitted without a proof tree; conflicts
  that cannot be resolved by specificity are left `unsupported`.

## 9. Phased plan

1. **B3** — show both branches on `refuted` (no semantics change). Prerequisite.
2. **B2** — keep rule provenance (stop materialising consequences as axioms).
3. Add `strict | defeasible` to `Rule`, plus an extraction-prompt convention and
   examples; keep the flag off.
4. Implement the defeasible evaluation layer (NFA + specificity) behind a flag.
5. Map results to three-valued statuses and add `defeasible` to the answer; update
   explanations.
6. Eval cases: both directions, an equal-specificity conflict, and a strict-only
   case (regression).

## 10. Open questions / risks

- **Termination**: the alternating fixpoint must be bounded; the universe is finite
  so it is, but the implementation must cap iterations and report `budget`.
- **Missing hierarchy**: without `is_a` between the competing classes, specificity
  is undefined → honest `unknown` (do not guess).
- **Extraction quality**: strict vs defeasible is another thing the model must get
  right; it needs explicit prompt examples (same discipline as `is_a`).
- **Product semantics**: this is a deliberate choice, not a fact; it should be
  recorded and revisited if the product needs graded or probabilistic answers.
