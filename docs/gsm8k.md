# GSM8K — collection notes

Operating notes for a grade-school math benchmark, considered as the **L4 stage**
of `docs/reasoning_roadmap.md`. Russian mirror: `docs/gsm8k_ru.md`. Related:
`docs/reasoning_roadmap.md`, `docs/task.md` §1.

Source: Cobbe et al., *Training Verifiers to Solve Math Word Problems*
(arXiv:2110.14168), dataset `openai/gsm8k` (MIT). Splits: `main` and `socratic`;
train ≈7.5k and test ≈1.3k questions (≈8.8k total). No committed sample yet.

## 1. What the benchmark is

Natural-language **grade-school math word problems**. Each record is a problem and
a reference solution written as a chain of thought; the final answer is a number.

| Field | Meaning |
|---|---|
| `question` | the word problem |
| `answer` | the reference chain of thought; each step carries `<<expr=result>>` annotations and the string ends with `#### <number>` |

The answer is a **free-form number**, not a truth value. Solving requires
multi-step arithmetic (×, ÷, %, fractions), unit handling, ratios, percentages,
and sometimes introducing an unknown and solving an equation.

## 2. Relation to Ankyra

GSM8K is **outside the symbolic spine**: there is no theory/query split and no
Horn clause to fire; the answer is produced by arithmetic, not by entailment. The
deferred comparison builtins (`=, neq, <, lte, >, gte`, range-restricted) only
compare literals — they do **not** compute. v0.1 builtins therefore do not make
GSM8K reachable.

`docs/task.md` §1 already places arithmetic beyond the deferred builtin layer out
of scope.

## 3. What testing would require (L4 — separate engine)

A **numeric** engine, not a new capability of the symbolic core:

- an arithmetic **term language** (quantities, units) proposed by the LLM;
- a **procedure**: expression evaluation and equation solving (e.g. sympy);
- **extraction** of the quantities and relations from the problem text;
- an **answer extractor** with numeric tolerance.

The propose/decide contract still applies — the LLM proposes the equations, the
numeric engine decides — but the *checking* is trivial relative to *modelling*.
Modelling quality is not a soundness property of the symbolic engine, so this
does not strengthen the core thesis.

## 4. Recommended form

**Tool-use, not an in-repo core.** The LLM drives an arithmetic/solver tool and
Ankyra verifies the formalization steps, not the arithmetic. Building a numeric
core in the repository is justified only if the product scope explicitly expands
to numeric reasoning.

## 5. Test plan (if pursued)

1. **Capability probe (no symbolic engine).** Send a handful of problems to the
   LLM with a calculator tool; measure end-to-end numeric accuracy and the
   formalization/answer-extraction failure rate separately.
2. **Committed sample.** A small deterministic subset with the reference
   `#### <number>` as ground truth.
3. **Adapter** `evals/gsm8k.py` — exact match (or tolerance) against the
   reference number; report the failure taxonomy (modelling vs arithmetic vs
   extraction).
4. **Gate:** numeric accuracy above threshold with **0 arithmetic errors**
   (the procedure is deterministic; arithmetic mistakes would mean a bug, not a
   reasoning miss).

## 6. Status

Out of scope / low priority, separate numeric engine (or tool-use). Documented so
the decision is explicit. See `docs/reasoning_roadmap.md` L4.
