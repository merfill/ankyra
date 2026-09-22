# AR-LSAT task-notation guide

These games assign a fixed set of entities (people, items, buildings, …) to
positions/slots, times, or groups. This guide describes the *notation* of the games
(how to read the source), never the answer to any question.

## Reading the game
- Positions are numbered as the text numbers them ("lockers 1 through 5", "hangers 1
  through 6"): use those labels as the domain values ("1".."N"), and make one variable
  per entity ranging over that domain (or one variable per slot ranging over the
  entities). Keep one consistent direction.
- "immediately before/after" -> order with immediate=true; "before/after" -> order;
  "next to" / "adjacent" -> adjacent; "not next to" -> not_adjacent.
- "around a table" / "in a circle" -> set the domain topology to "circular".
- "in the same room/group" -> same_group; "in different rooms/groups" ->
  different_group.
- "either … or …", "or both", "at least one of" -> any(...) (inclusive);
  "both … and …" -> all(...).
- "either … or …, BUT NOT BOTH", "at some time after either A or B, but not both" is
  EXCLUSIVE. Encode the "not both": for a relation rel(X, ·),
  any(all(rel(A,X), not(rel(B,X))), all(rel(B,X), not(rel(A,X)))). Never drop the
  "not both", and never read "either" as "both".
- "at least/at most/exactly N of a group" -> count with the matching count_mode;
  "more/fewer … than" comparing two groups -> count_compare.

## Reading the options
The question is given with its five options labelled A–E; encode each option's full
claim, in order (A is index 0). Never encode which option you think is correct.
- A complete order/sequence ("Ginny, Fernando, Hakim, Kevin, Juanita") lists every
  entity in order: encode one eq per entity (entity -> its position value).
- A slot assignment ("1: wool; 2: gauze; …") is eq(entity, slot) for each entry.
- A per-object list ("F: Seamus, Reynaldo; G: Yuki, Seamus; …") lists, for each object
  (slot/position/room), the entities that use it. When the game tracks an ordered
  sequence per object (e.g. a day-by-day schedule), the k-th entity in the list is the
  k-th step of that object's sequence: with per-(entity, step) variables, encode the
  k-th listed entity in object O as eq(entity_stepK, O). Encode the whole list — never
  collapse it to its first entity.
- "which MUST be true" -> must; "which COULD be true" -> could; "which CANNOT be true"
  / "must be false" -> must_be_false; "which arrangement/order is possible / does not
  violate" -> not_violate; "complete and accurate list" -> complete_list (set target
  and put the candidate lists in the options' "values").
- A question with an "If … " stem puts the hypothetical premise in "assumptions"
  (never in the options) and then encodes the five options against that premise.

## Modeling conventions (learned from observed extraction errors)
- **Repeated trials (two days, k rounds).** When each entity acts once per round, use
  one variable per (entity, round): entity_round1, entity_round2, … . Add all_different
  over each round's variables. If the text says an entity does something DIFFERENT in
  the second round ("a different bicycle on the second day"), add a per-entity neq:
  neq(entity_round1, entity_round2). Do not omit it.
- **"X is one of the users/testers of V"** (at least once across rounds) ->
  any(eq(X_round1, V), eq(X_round2, V)); never all(...) (that would force every round).
- **A cross-round statement** ("the V that X uses in round 1 is used by Y in round 2")
  -> a single cross-variable eq: eq(Y_round2, X_round1). Not a conditional.
- **Fewer slots than entities.** Model one variable per SLOT ranging over the entities
  (each slot holds one entity), with all_different over the slots; entities left unused
  are simply not constrained. Never invent a value such as "unassigned".
- **Ordered per-object lists in an option** ("F: A, B; G: C, D; …"): for each object O,
  the k-th listed entity uses O at round k -> eq(entity_roundK, O). Worked example with
  objects F,G,H,J and rounds 1..2: "F: Seamus, Reynaldo; G: Yuki, Seamus" ->
  eq(Seamus_round1, F), eq(Reynaldo_round2, F), eq(Yuki_round1, G), eq(Seamus_round2, G).
  Never put two entries of the same object's list on the same round, and never collapse
  a list to its first entity.
