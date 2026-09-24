## The task

Encode the problem as a numeric model (quantities + equations) and the question as the
single quantity it asks for. The harness then solves the model exactly and compares the
value to the reference number.

- The **target** is the quantity the question asks for; choose one of the model's
  quantities, never a new one. Do not answer the question yourself and do not compute
  the value — the engine does the arithmetic.
- Introduce a distinct quantity for every amount the text names, including the amount
  the question asks about, and define derived quantities with equations.
- Every amount the problem states numerically MUST be defined by an equation (usually
  `q = const`). A quantity with no defining equation stays unknown and makes the target
  underdetermined — the engine never guesses a value.
- Operator arity: `sub` and `div` take exactly two operands; `add` and `mul` take two or
  more. Never pass three operands to `sub` or `div`.
- Each quote must be an exact substring of the problem text (copy it verbatim).
- Keep every relation linear: a product or quotient of two unknown quantities is out of
  fragment; write the linear equation the text states instead. A "maximize / whichever is
  greater" target is an exact `max(a, b)` (and `min` for "least"); encode both candidate
  quantities and take the max — never assert a guessed equality such as
  `best = one_candidate`. Both operands must be determined by the model; max/min of an
  unknown is out of fragment.
- State only relations the text states; never add an equation to make the numbers work.
- Every quantity and equation carries a minimal verbatim quote from the problem.
- If the text fixes no relation between two unknowns, leave the model underdetermined;
  do not invent a value.
