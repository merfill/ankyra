"""Build the committed L2 synthetic collection (deterministic, LLM-free).

The L2 procedure is gated by a structural collection: each case is a fully structured
theory/query pair with an independently written expected verdict, graded by
``evals.l2_synthetic``. No LLM, no natural language, zero provider variance.

Coverage (``docs/l2_plan.md`` §12.1): disjunctive head + case split, disjunctive body,
De Morgan, proof by contradiction/reductio, conjunctive and disjunctive goals (D-L2-7),
a disjunctive ground fact with a case split, budget exhaustion, out-of-fragment
constructs, and mandatory negative controls (the Horn flag must not consume a
disjunctive clause; an exhausted budget must not yield a proof; a Horn theory gives
the same answer under both engines).

Usage:
    uv run python -m evals.build_l2_synthetic [--out PATH]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DEFAULT_OUT = DATA / "l2_synthetic.jsonl"


def _m(pred: str, subject: str | None = None, obj: str | None = None, *, neg: bool = False) -> dict:
    return {"predicate": pred, "subject": subject, "object": obj, "negated": neg, "modality": "neutral"}


def _is_a(subject: str, obj: str, *, neg: bool = False) -> dict:
    return _m("is_a", subject, obj, neg=neg)


def _rule(conditions: list[dict], consequence: dict, alternatives: list[dict] | None = None) -> dict:
    return {
        "conditions": conditions,
        "consequence": consequence,
        "alternatives": list(alternatives or []),
        "kind": "implication",
        "forall": {},
        "source": "quote",
        "quote": None,
    }


def _fact(consequence: dict, alternatives: list[dict]) -> dict:
    """A disjunctive ground fact: a conditionless clause with a head OR."""
    return _rule([], consequence, alternatives)


def _constraint(left: str, right: str) -> dict:
    return {"kind": "disjoint", "left": left, "right": right, "quote": None}


def _theory(morphisms=(), rules=(), constraints=(), objects=(), existentials=()) -> dict:
    return {
        "objects": [{"id": oid} for oid in objects],
        "morphisms": list(morphisms),
        "rules": list(rules),
        "constraints": list(constraints),
        "existentials": list(existentials),
        "source_text": "",
        "domain": [],
    }


def _query(target, conditions=(), *, goals=(), goal_mode: str = "single", answer_type: str = "yes_no") -> dict:
    return {
        "conditions": list(conditions),
        "target": target,
        "goals": list(goals),
        "goal_mode": goal_mode,
        "variables": {},
        "answer_type": answer_type,
        "world_assumption": "open",
    }


def _case(
    case_id,
    mechanism,
    theory,
    query,
    status,
    kind,
    *,
    strength=None,
    logic="ground",
    budget=None,
    note="",
):
    if strength is None:
        strength = "proven" if status in {"supported", "refuted"} else "not_proven"
    case = {
        "id": case_id,
        "mechanism": mechanism,
        "note": note,
        "theory": theory,
        "query": query,
        "expected": {"status": status, "kind": kind, "strength": strength},
        "logic": logic,
    }
    if budget is not None:
        case["budget"] = budget
    return case


def _common_consequence_rules() -> list[dict]:
    return [
        _rule([_is_a("?x", "a")], _is_a("?x", "c")),
        _rule([_is_a("?x", "b")], _is_a("?x", "c")),
    ]


def _disjunctive_head_cases() -> list[dict]:
    head = _rule(
        [_is_a("?x", "prim")],
        _is_a("?x", "a"),
        alternatives=[_is_a("?x", "b")],
    )
    theory = _theory(morphisms=[_is_a("rex", "prim")], rules=[head, *_common_consequence_rules()])
    return [
        _case(
            "head-case-split-01",
            "disjunctive_head",
            theory,
            _query(_is_a("rex", "c")),
            "supported",
            "yes",
            note="a disjunctive head forces a proof by cases over both disjuncts",
        ),
        _case(
            "head-no-disjunct-02",
            "disjunctive_head",
            theory,
            _query(_is_a("rex", "a")),
            "unsupported",
            "unknown",
            note="negative control: A or B does not entail a disjunct",
        ),
    ]


def _disjunctive_body_cases() -> list[dict]:
    # ``A or B => C`` lowers to one rule per disjunct (build/unroll), so the engine
    # sees two Horn rules; the case documents the lowering's semantics.
    theory = _theory(
        morphisms=[_is_a("rex", "b")],
        rules=[_rule([_is_a("?x", "a")], _is_a("?x", "c")), _rule([_is_a("?x", "b")], _is_a("?x", "c"))],
    )
    return [
        _case(
            "body-or-01",
            "disjunctive_body",
            theory,
            _query(_is_a("rex", "c")),
            "supported",
            "yes",
            note="a disjunctive body is a Horn split into one rule per disjunct",
        ),
        _case(
            "body-or-02",
            "disjunctive_body",
            _theory(rules=[_rule([_is_a("?x", "a")], _is_a("?x", "c")), _rule([_is_a("?x", "b")], _is_a("?x", "c"))]),
            _query(_is_a("rex", "c")),
            "unsupported",
            "unknown",
            note="negative control: neither disjunct holds",
        ),
    ]


def _de_morgan_cases() -> list[dict]:
    # ``~(A and B)`` is the clause ``~A or ~B``; with ``B`` it entails ``~A``.
    clause = _fact(_is_a("rex", "a", neg=True), [_is_a("rex", "b", neg=True)])
    return [
        _case(
            "demorgan-01",
            "de_morgan",
            _theory(morphisms=[_is_a("rex", "b")], rules=[clause]),
            _query(_is_a("rex", "a", neg=True)),
            "supported",
            "yes",
            note="~A or ~B with B entails ~A",
        ),
        _case(
            "demorgan-02",
            "de_morgan",
            _theory(rules=[clause]),
            _query(_is_a("rex", "a", neg=True)),
            "unsupported",
            "unknown",
            note="negative control: without B the disjunction decides nothing",
        ),
    ]


def _reductio_cases() -> list[dict]:
    theory = _theory(
        morphisms=[_is_a("rex", "b", neg=True)],
        rules=[_rule([_is_a("?x", "a")], _is_a("?x", "b"))],
    )
    return [
        _case(
            "reductio-01",
            "reductio",
            theory,
            _query(_is_a("rex", "a", neg=True)),
            "supported",
            "yes",
            note="contrapositive: A => B and ~B entail ~A",
        ),
        _case(
            "reductio-02",
            "reductio",
            theory,
            _query(_is_a("rex", "b", neg=True)),
            "supported",
            "yes",
            note="the asserted negative is entailed directly",
        ),
    ]


def _compound_goal_cases() -> list[dict]:
    both = _theory(morphisms=[_is_a("rex", "a"), _is_a("rex", "b")])
    only_a = _theory(morphisms=[_is_a("rex", "a")])
    return [
        _case(
            "goal-all-01",
            "conjunctive_goal",
            both,
            _query(_is_a("rex", "a"), goals=[_is_a("rex", "a"), _is_a("rex", "b")], goal_mode="all"),
            "supported",
            "yes",
            note="both conjuncts hold",
        ),
        _case(
            "goal-all-02",
            "conjunctive_goal",
            only_a,
            _query(_is_a("rex", "a"), goals=[_is_a("rex", "a"), _is_a("rex", "b")], goal_mode="all"),
            "insufficient",
            "unknown",
            note="negative control: a missing conjunct blocks support",
        ),
        _case(
            "goal-any-01",
            "disjunctive_goal",
            only_a,
            _query(_is_a("rex", "a"), goals=[_is_a("rex", "a"), _is_a("rex", "b")], goal_mode="any"),
            "supported",
            "yes",
            note="one provable disjunct suffices",
        ),
        _case(
            "goal-any-02",
            "disjunctive_goal",
            _theory(),
            _query(_is_a("rex", "a"), goals=[_is_a("rex", "a"), _is_a("rex", "b")], goal_mode="any"),
            "insufficient",
            "unknown",
            note="negative control: no disjunct is provable",
        ),
    ]


def _disjunctive_fact_cases() -> list[dict]:
    fact = _fact(_is_a("rex", "a"), [_is_a("rex", "b"), _is_a("rex", "c")])
    rules = [
        _rule([_is_a("?x", "a")], _is_a("?x", "d")),
        _rule([_is_a("?x", "b")], _is_a("?x", "d")),
        _rule([_is_a("?x", "c")], _is_a("?x", "d")),
    ]
    partial = [
        _rule([_is_a("?x", "a")], _is_a("?x", "d")),
    ]
    return [
        _case(
            "fact-case-split-01",
            "disjunctive_fact",
            _theory(rules=[fact, *rules]),
            _query(_is_a("rex", "d")),
            "supported",
            "yes",
            note="a disjunctive ground fact is decided by cases over its disjuncts",
        ),
        _case(
            "fact-case-split-02",
            "disjunctive_fact",
            _theory(rules=[_fact(_is_a("rex", "a"), [_is_a("rex", "b")]), *partial]),
            _query(_is_a("rex", "d")),
            "unsupported",
            "unknown",
            note="negative control: a disjunct with no route to the goal blocks it",
        ),
    ]


def _shared_witness_cases() -> list[dict]:
    goals = [_is_a("?x", "p"), _is_a("?x", "q")]
    one_witness = _theory(
        objects=["rex"], morphisms=[_is_a("rex", "p"), _is_a("rex", "q")]
    )
    two_witnesses = _theory(
        objects=["a", "b"], morphisms=[_is_a("a", "p"), _is_a("b", "q")]
    )
    refuting = _theory(
        objects=["a", "b"],
        morphisms=[_is_a("a", "p"), _is_a("b", "p")],
        rules=[_rule([_is_a("?x", "p")], _is_a("?x", "q", neg=True))],
    )
    partial = _theory(objects=["a"], morphisms=[_is_a("a", "p")])
    budgeted = _theory(
        objects=["rex"],
        morphisms=[_is_a("rex", "p"), _is_a("rex", "r")],
        rules=[_rule([_is_a("?x", "r")], _is_a("?x", "q"))],
    )
    return [
        _case(
            "shared-witness-01",
            "shared_witness",
            one_witness,
            _query(_is_a("?x", "p"), goals=goals, goal_mode="all", answer_type="open"),
            "supported",
            "binding",
            note="one witness satisfies every conjunct",
        ),
        _case(
            "shared-witness-02",
            "shared_witness",
            two_witnesses,
            _query(_is_a("?x", "p"), goals=goals, goal_mode="all", answer_type="open"),
            "insufficient",
            "unknown",
            note="negative control: independent witnesses do not satisfy a shared one",
        ),
        _case(
            "shared-witness-03",
            "shared_witness",
            refuting,
            _query(_is_a("?x", "p"), goals=goals, goal_mode="all"),
            "refuted",
            "no",
            note="every witness makes the conjunction unsatisfiable",
        ),
        _case(
            "shared-witness-04",
            "shared_witness",
            partial,
            _query(_is_a("?x", "p"), goals=goals, goal_mode="all", answer_type="open"),
            "insufficient",
            "unknown",
            note="negative control: no witness satisfies both conjuncts",
        ),
        _case(
            "shared-witness-05",
            "shared_witness",
            budgeted,
            _query(_is_a("?x", "p"), goals=goals, goal_mode="all", answer_type="open"),
            "insufficient",
            "unknown",
            budget=1,
            note="negative control: an exhausted budget is never a proof",
        ),
        _case(
            "shared-witness-06",
            "shared_witness",
            one_witness,
            _query(_is_a("?x", "p"), goals=goals, goal_mode="all", answer_type="open"),
            "out_of_fragment",
            "unknown",
            logic="off",
            note="negative control: with L2 off a compound goal is out_of_fragment",
        ),
    ]


def _universal_goal_cases() -> list[dict]:
    chain = _theory(
        rules=[
            _rule([_is_a("?x", "a")], _is_a("?x", "b")),
            _rule([_is_a("?x", "b")], _is_a("?x", "c")),
        ]
    )
    forall_ac = _query(
        _is_a("?x", "a", neg=True),
        goals=[_is_a("?x", "a", neg=True), _is_a("?x", "c")],
        goal_mode="forall",
    )
    forall_ab = _query(
        _is_a("?x", "a", neg=True),
        goals=[_is_a("?x", "a", neg=True), _is_a("?x", "b")],
        goal_mode="forall",
    )
    forall_not_p = _query(
        _is_a("?x", "p", neg=True),
        goals=[_is_a("?x", "p", neg=True)],
        goal_mode="forall",
    )
    return [
        _case(
            "universal-01",
            "universal_goal",
            chain,
            forall_ac,
            "supported",
            "yes",
            note="a universal chain A=>B=>C proves forall A=>C at a fresh constant",
        ),
        _case(
            "universal-02",
            "universal_goal",
            _theory(objects=["rex"], morphisms=[_is_a("rex", "a"), _is_a("rex", "b")]),
            forall_ab,
            "insufficient",
            "unknown",
            note="soundness control: a named individual satisfying A=>B does not prove "
            "the universal (the named-pool enumeration would say yes)",
        ),
        _case(
            "universal-03",
            "universal_goal",
            _theory(objects=["rex"], morphisms=[_is_a("rex", "a"), _is_a("rex", "b", neg=True)]),
            forall_ab,
            "refuted",
            "no",
            note="a named witness falsifies every literal of the clause",
        ),
        _case(
            "universal-04",
            "universal_goal",
            _theory(objects=["rex"], morphisms=[_is_a("rex", "p")]),
            forall_not_p,
            "refuted",
            "no",
            note="forall ~P (not exists P) is refuted by the named P",
        ),
        _case(
            "universal-05",
            "universal_goal",
            _theory(
                rules=[
                    _rule([_is_a("?x", "p")], _is_a("?x", "q")),
                    _rule([_is_a("?x", "p")], _is_a("?x", "q", neg=True)),
                ]
            ),
            forall_not_p,
            "supported",
            "yes",
            note="P=>Q and P=>~Q prove forall ~P at the fresh constant",
        ),
        _case(
            "universal-06",
            "universal_goal",
            chain,
            forall_ac,
            "insufficient",
            "unknown",
            budget=1,
            note="negative control: an exhausted budget is never a proof",
        ),
        _case(
            "universal-07",
            "universal_goal",
            chain,
            forall_ac,
            "out_of_fragment",
            "unknown",
            logic="off",
            note="negative control: with L2 off a compound goal is out_of_fragment",
        ),
    ]


def _budget_cases() -> list[dict]:
    theory = _theory(morphisms=[_is_a("rex", "p")], rules=[_rule([_is_a("?x", "p")], _is_a("?x", "q"))])
    return [
        _case(
            "budget-01",
            "budget",
            theory,
            _query(_is_a("rex", "q")),
            "insufficient",
            "unknown",
            budget=1,
            note="an exhausted budget is the honest unknown, never a false proof",
        )
    ]


def _out_of_fragment_cases() -> list[dict]:
    return [
        _case(
            "oof-builtin-01",
            "out_of_fragment",
            _theory(rules=[_rule([_m("gte", "?p", "50")], _m("big", "?p"))]),
            _query(_m("big", "x")),
            "out_of_fragment",
            "unknown",
            note="a builtin comparison is outside the ground clause fragment",
        ),
        _case(
            "oof-unsafe-01",
            "out_of_fragment",
            _theory(morphisms=[_is_a("rex", "a")], rules=[_rule([_is_a("?x", "a")], _is_a("?y", "b"))]),
            _query(_is_a("rex", "b")),
            "out_of_fragment",
            "unknown",
            note="a head variable not bound by the body is an unsafe rule",
        ),
    ]


def _control_cases() -> list[dict]:
    head = _rule([_is_a("?x", "prim")], _is_a("?x", "a"), alternatives=[_is_a("?x", "b")])
    disjunctive = _theory(morphisms=[_is_a("rex", "prim")], rules=[head, *_common_consequence_rules()])
    horn = _theory(morphisms=[_is_a("rex", "p")], rules=[_rule([_is_a("?x", "p")], _is_a("?x", "q"))])
    return [
        _case(
            "control-flag-off-01",
            "control",
            disjunctive,
            _query(_is_a("rex", "c")),
            "out_of_fragment",
            "unknown",
            logic="off",
            note="negative control: with L2 off a non-Horn theory is out_of_fragment, not guessed",
        ),
        _case(
            "control-horn-parity-02",
            "control",
            horn,
            _query(_is_a("rex", "q")),
            "supported",
            "yes",
            note="a Horn theory is decided the same way by the ground procedure",
        ),
    ]


def _existential_cases() -> list[dict]:
    existentials = [{"variable": "?x", "atoms": [_is_a("?x", "animal")], "quote": None}]
    theory = _theory(existentials=existentials, rules=[_rule([_is_a("?x", "animal")], _is_a("?x", "mortal"))])
    return [
        _case(
            "exist-ground-01",
            "existential",
            theory,
            _query(_is_a("sk0", "animal")),
            "supported",
            "yes",
            note="an existential premise is Skolemized to a fresh constant",
        ),
        _case(
            "exist-open-01",
            "existential",
            theory,
            _query(_is_a("?x", "mortal"), answer_type="open"),
            "supported",
            "binding",
            note="the existential goal is proved by the Skolem witness",
        ),
        _case(
            "exist-control-01",
            "existential",
            theory,
            _query(_is_a("?x", "plant"), answer_type="open"),
            "unsupported",
            "unknown",
            note="negative control: no witness satisfies the open goal",
        ),
    ]


def _open_goal_cases() -> list[dict]:
    theory = _theory(morphisms=[_is_a("a", "cat"), _is_a("b", "cat")])
    return [
        _case(
            "open-witness-01",
            "open_goal",
            theory,
            _query(_is_a("?x", "cat"), answer_type="open"),
            "supported",
            "binding",
            note="an open goal returns the first witness from the finite domain",
        )
    ]


def cases() -> list[dict]:
    """The full deterministic collection, grouped by mechanism."""
    return (
        _disjunctive_head_cases()
        + _disjunctive_body_cases()
        + _de_morgan_cases()
        + _reductio_cases()
        + _compound_goal_cases()
        + _disjunctive_fact_cases()
        + _existential_cases()
        + _open_goal_cases()
        + _shared_witness_cases()
        + _universal_goal_cases()
        + _budget_cases()
        + _out_of_fragment_cases()
        + _control_cases()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the L2 synthetic collection.")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    collected = cases()
    with out.open("w", encoding="utf-8") as handle:
        for case in collected:
            handle.write(json.dumps(case, ensure_ascii=False) + "\n")
    print(f"wrote {len(collected)} cases to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
