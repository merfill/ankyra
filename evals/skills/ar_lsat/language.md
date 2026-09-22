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
