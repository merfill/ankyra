# GSM8K task-notation guide

These problems are grade-school word problems; the answer is a single number. This
guide describes the *notation* of the text (how to read it into exact quantities and
equations), never the answer to any problem.

## Reading the text
- Every named amount is a quantity: give it a snake_case id, state each directly given
  amount as a `const`, and introduce an unknown quantity for anything the text leaves
  free.
- "each" / "per" / "every" -> multiply by the count: `total = rate * count`.
- Ratios and fractions are exact arithmetic: "half as many" -> `a = b / 2`;
  "three times as many" -> `a = 3 * b`; "11/8 of the price" -> `a = b * (11 / 8)`.
- "N times as many X as Y" sets `X = N * Y`. Read the verb to decide whether the amount
  replaces or is added to a running count: "the number WAS N times the initial" replaces
  (`later = N * initial`), while "received/found N times as many new X" is new X added on
  top (`later = initial + N * initial`).
- Percentages are exact: "20% more" -> `a = b * (120 / 100)`; "25% off" ->
  `a = b - b * (25 / 100)`.
- "more than" / "less than" -> add / subtract; "how many left" -> a start amount minus
  what was spent or removed.
- "in total" / "altogether" -> a sum of the parts.
- A time or measure word is a constant from the problem ("a decade" -> 10, "a dozen" ->
  12, "a week" -> 7 days); state it as a `const` with the word as its quote.
- Keep every relation linear: a product of two unknown quantities is out of fragment.
  When the text relates two unknowns, write the linear equation it states (e.g. "one is
  4 more than the other" -> `big = small + 4`), not a product.
