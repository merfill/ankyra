# FOLIO task-notation guide

FOLIO problems are short natural-language premise sentences plus one conclusion; the
label is True / False / Uncertain under an open world. This guide describes how to read
the source phrasing into the committed L1/L2 structures. It is notation guidance, never
the answer to any example.

## Reading the premises (each sentence must produce at least one atom or rule)
- "All / Every A are B" -> a rule `is_a(?x, A) => is_a(?x, B)` (or the general
  predicate form `A(?x) -> B(?x)`); use `forall` for the quantifier's sort when the
  sentence is generic.
- "No A is/are B" -> disjointness: no individual is both A and B (a strict constraint),
  NOT a negation-as-failure rule.
- "Some A are B" / "There is an A that is B" -> an existential premise
  `∃x(is_a(x,A) ∧ is_a(x,B))`; record the quantifier, do not invent a constant.
- "Not all A are B" / "Some A are not B" -> `∃x(is_a(x,A) ∧ ¬is_a(x,B))`.
- "Only A are B" / "Only A is B" -> `B -> A` (a rule, not `A -> B`).
- "X is a/an A" / "X is B" about a NAMED individual -> a ground fact about X (e.g.
  `is_a(x, A)`); keep the name, never quantify over it.
- "X is not a/an A" / "X is not B" -> a ground NEGATED atom (`negated: true`), not a
  missing fact.
- "If A then B" / "A implies B" -> a rule `A => B`.
- "A unless B" -> `¬B => A` (equivalently `¬B ∨ A`).
- "Either A or B" / "… , or …" -> a disjunction (an `ask_any`/`or` clause), not two
  concurrent facts.
- "Neither A nor B" -> BOTH negated (`¬A ∧ ¬B`).
- "A if and only if B" / "exactly when" -> two implications.
- Keep EVERY premise: an atomic sentence about a named individual is a fact, not
  "obvious" background; dropping it is the dominant extraction loss on this collection.

## Reading the conclusion (the question's target)
- The target is the conclusion's own claim, in positive polarity (the builder/adapter
  reconciles "not" in the conclusion); a conclusion that is a rule/universal
  ("all X are Y", "no X is Y") is a universal goal, not a ground atom.
- A conclusion with "either … or …" is a disjunctive goal; a conjunction is a
  conjunctive goal; do not collapse a compound conclusion to one atom.
- "Uncertain" is the open-world default: absence of a proof is NOT a refutation — never
  close the world to force a True/False answer.
