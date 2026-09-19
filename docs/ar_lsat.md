# AR-LSAT — collection notes

Operating notes for an analytical-reasoning benchmark, planned as the **L3 gate**
of `docs/reasoning_roadmap.md`. Russian mirror: `docs/ar_lsat_ru.md`. Related:
`docs/reasoning_roadmap.md`, `docs/task.md` §3.8.

Source: AR-LSAT, Zhong et al. (arXiv:2104.06598); packaged for evaluation by
**AGIEval** (arXiv:2304.06364). Raw dataset: `github.com/zhongwanjun/AR-LSAT`. HF
mirrors: `tasksource/lsat-ar`, `olegbask/AR-LSAT`, `dmayhem93/agieval-lsat-ar`. No
committed sample yet.

## 1. What the benchmark is

LSAT **analytical reasoning** ("logic games"). Each item is one game: a `context`
describes a finite scenario — a set of entities, the positions or groups they
occupy, and a list of constraints. One context is shared by many questions. Each
question is a five-way multiple choice.

A verified example (`context` abbreviated):

> Exactly six trade representatives negotiate a treaty: Klosnik, Londi, Manley,
> Neri, Osata, Poirier. There are exactly six chairs evenly spaced around a
> circular table… Poirier sits immediately next to Neri. Londi sits immediately
> next to Manley, Neri, or both. Klosnik does not sit immediately next to Manley.
> If Osata sits immediately next to Poirier, Osata does not sit immediately next
> to Manley.
>
> **Question:** Which one of the following seating arrangements … would NOT
> violate the stated conditions?
>
> **answers:** five full arrangements; **label:** 1 (0-based index).

## 2. Record fields

| Field | Meaning |
|---|---|
| `context` | the game: entities, domains/positions, constraints |
| `question` | the multiple-choice question |
| `answers` | exactly five candidate answers (strings) |
| `label` | 0-based index of the correct option |
| `id_string` | game/question id, e.g. `199106_2-G_1_1` (only in `tasksource/lsat-ar`) |

The multiple-choice options are not always full assignments: they may be a pair, a
"complete and accurate list", or a single constraint, depending on the question
type.

## 3. Axes

- **game type** — linear ordering, circular ordering, grouping/splitting,
  assignment; often a mix;
- **question type** — which arrangement would / would NOT violate; which must be
  true; which could be true; a complete and accurate list; "if X then Y";
- **entities / slots** — small finite counts (typically 5–7 entities, equal or
  fewer positions/groups).

## 4. Relation to Ankyra

AR-LSAT is **not** Horn deduction. Solving a game is finite-domain constraint
satisfaction: positions are a permutation, "immediately next to" is adjacency,
"not next to" is a disequality constraint, and "if … then …" is a conditional
constraint. The question types have model-theoretic semantics:

| Question form | Meaning |
|---|---|
| which arrangement would NOT violate | find a model satisfying every constraint |
| which must be true | true in **every** model of the constraints |
| which could be true | true in **some** model |
| complete and accurate list | enumerate the models and read off the set |

The current engine cannot express all-different, adjacency, mutual exclusion or
finite-domain enumeration, and its open-world Horn closure has no notion of
enumerating models. A Horn encoding would answer at best `unknown`.

## 5. What testing would require (L3 — separate engine)

- a dedicated **CSP IR**: entities, finite domains, all-different, order,
  adjacency (possibly circular), conditional constraints, and grouped positions;
- a **solver**: SAT/SMT via Z3 or an in-repo finite-domain/backtracking search;
- a **multiple-choice adapter**: each option is checked against the solver —
  satisfiability for "could" / "not violate", entailment (unsat of the negation)
  for "must", model enumeration for "complete and accurate list";
- an **extraction** step that turns the game text into the CSP IR. This is the
  main difficulty and the main risk.

Ankyra's role in L3 is orchestration: the LLM proposes the CSP encoding, the
solver decides. The soundness contract is preserved, but the decision procedure
is a second engine, not the Horn spine.

## 6. Risks and non-goals

- **Hardcoding temptation.** Positional/adjacency specifics invite a fixed
  ontology (circular-table, next-to), which `docs/task.md` §3.8 forbids. The IR
  must be general and the extraction prompt must carry the semantics.
- **Distance from domain-general Horn.** AR-LSAT exercises a different paradigm;
  it does not strengthen the deductive core and is therefore low priority.
- **Extraction accuracy.** A wrong CSP encoding yields confidently wrong answers;
  the adapter must report encoding failures honestly rather than guess.

## 7. Test plan (if pursued)

0. **Feasibility spike (no LLM).** Hand-encode 5 games into the CSP IR and solve
   them with Z3; measure solver-side correctness and the IR's expressiveness.
1. **Extraction probe.** For the same 5 games, have the LLM propose the CSP IR;
   measure encoding accuracy against the hand-written IR (not the final answers).
2. **Committed sample.** A small stratified set (by game/question type) built
   deterministically from the raw dataset.
3. **Adapter** `evals/ar_lsat.py` with per-option solver checks.
4. **Gate:** encoding accuracy above threshold and 0 confidently-wrong answers
   (`answer scored but solver input inconsistent`); failures triaged per option
   type.

## 8. Status

Not implemented; low priority, separate engine. Documented so the decision is
explicit. See `docs/reasoning_roadmap.md` L3.
