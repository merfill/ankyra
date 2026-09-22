"""Build the committed routing synthetic collection (deterministic, LLM-free).

The declared-fragment contract (``docs/fragment_routing.md``) is gated by a
structural collection: each case is a fully structured theory/query pair with an
independently written expected ``RoutingDecision`` (fragment, procedure, refusal)
and expected verdict. Run by ``evals.routing_synthetic``. No LLM, no natural
language, zero provider variance.

Coverage: every fragment feature (horn, negation, disjunction, existential,
builtin, compound_goal, shared_witness) and every refusal code (non_horn, compound_goal,
existential, naf_in_l2, defeasible_with_clausal_fragment), plus controls for the
A1 policy (the L2 flag selects the clausal procedure even for a Horn structure)
and the second refusal layer (clausification refuses a builtin).

Usage:
    uv run python -m evals.build_routing_synthetic [--out PATH]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.build_l2_synthetic import (
    _common_consequence_rules,
    _constraint,
    _is_a,
    _m,
    _query,
    _rule,
    _theory,
)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DEFAULT_OUT = DATA / "routing_synthetic.jsonl"


def _case(
    case_id: str,
    mechanism: str,
    theory: dict,
    query: dict,
    *,
    fragment: list[str],
    procedure: str,
    status: str,
    kind: str,
    refusal: str | None = None,
    logic: str = "ground",
    defeasible: bool = False,
    builtins: bool = False,
    note: str = "",
) -> dict:
    return {
        "id": case_id,
        "mechanism": mechanism,
        "note": note,
        "logic": logic,
        "defeasible": defeasible,
        "builtins": builtins,
        "theory": theory,
        "query": query,
        "expected": {
            "fragment": sorted(fragment),
            "procedure": procedure,
            "refusal": refusal,
            "status": status,
            "kind": kind,
        },
    }


def _closed(query: dict) -> dict:
    query = dict(query)
    query["world_assumption"] = "closed"
    return query


def _disjunctive_theory() -> dict:
    head = _rule(
        [_is_a("?x", "prim")],
        _is_a("?x", "a"),
        alternatives=[_is_a("?x", "b")],
    )
    return _theory(morphisms=[_is_a("rex", "prim")], rules=[head, *_common_consequence_rules()])


def _naf_theory() -> dict:
    return _theory(
        rules=[_rule([_is_a("?x", "p"), _is_a("?x", "q", neg=True)], _is_a("?x", "r"))]
    )


def cases() -> list[dict]:
    """The full deterministic collection, grouped by mechanism."""
    return [
        _case(
            "horn-single-01",
            "horn",
            _theory(morphisms=[_is_a("rex", "p")], rules=[_rule([_is_a("?x", "p")], _is_a("?x", "q"))]),
            _query(_is_a("rex", "q")),
            fragment=["horn"],
            procedure="horn",
            status="supported",
            kind="yes",
            logic="off",
            note="a single-target Horn theory needs only the Horn fragment",
        ),
        _case(
            "horn-negation-02",
            "negation",
            _theory(morphisms=[_is_a("rex", "cat")], constraints=[_constraint("cat", "dog")]),
            _query(_is_a("rex", "dog")),
            fragment=["horn", "negation"],
            procedure="horn",
            status="refuted",
            kind="no",
            logic="off",
            note="a disjointness constraint is the negation feature, decided by the Horn path",
        ),
        _case(
            "disjunction-head-03",
            "disjunction",
            _disjunctive_theory(),
            _query(_is_a("rex", "c")),
            fragment=["horn", "disjunction"],
            procedure="clausal",
            status="supported",
            kind="yes",
            note="a disjunctive head requires the clausal procedure",
        ),
        _case(
            "existential-04",
            "existential",
            _theory(
                existentials=[{"variable": "?x", "atoms": [_is_a("?x", "animal")], "quote": None}],
                rules=[_rule([_is_a("?x", "animal")], _is_a("?x", "mortal"))],
            ),
            _query(_is_a("sk0", "animal")),
            fragment=["horn", "existential"],
            procedure="clausal",
            status="supported",
            kind="yes",
            note="an existential premise requires the clausal procedure (Skolemization)",
        ),
        _case(
            "compound-goal-05",
            "compound_goal",
            _theory(morphisms=[_is_a("rex", "a"), _is_a("rex", "b")]),
            _query(
                _is_a("rex", "a"),
                goals=[_is_a("rex", "a"), _is_a("rex", "b")],
                goal_mode="all",
            ),
            fragment=["compound_goal", "horn"],
            procedure="clausal",
            status="supported",
            kind="yes",
            note="a compound goal requires the clausal procedure",
        ),
        _case(
            "shared-witness-13",
            "shared_witness",
            _theory(morphisms=[_is_a("rex", "p"), _is_a("rex", "q")]),
            _query(
                _is_a("?x", "p"),
                goals=[_is_a("?x", "p"), _is_a("?x", "q")],
                goal_mode="all",
                answer_type="open",
            ),
            fragment=["shared_witness", "compound_goal", "horn"],
            procedure="clausal",
            status="supported",
            kind="binding",
            note="a conjunctive goal with a shared variable is the shared_witness feature",
        ),
        _case(
            "universal-goal-14",
            "universal_goal",
            _theory(
                rules=[
                    _rule([_is_a("?x", "a")], _is_a("?x", "b")),
                    _rule([_is_a("?x", "b")], _is_a("?x", "c")),
                ]
            ),
            _query(
                _is_a("?x", "a", neg=True),
                goals=[_is_a("?x", "a", neg=True), _is_a("?x", "c")],
                goal_mode="forall",
            ),
            fragment=["universal_goal", "compound_goal", "horn"],
            procedure="clausal",
            status="supported",
            kind="yes",
            note="a universal clause goal is the universal_goal feature and requires the clausal procedure",
        ),
        _case(
            "refuse-non-horn-06",
            "refusal",
            _disjunctive_theory(),
            _query(_is_a("rex", "c")),
            fragment=["horn", "disjunction"],
            procedure="horn",
            status="out_of_fragment",
            kind="unknown",
            refusal="out_of_fragment:non_horn",
            logic="off",
            note="negative control: with L2 off a disjunctive head is refused, never guessed",
        ),
        _case(
            "refuse-compound-07",
            "refusal",
            _theory(morphisms=[_is_a("rex", "a"), _is_a("rex", "b")]),
            _query(
                _is_a("rex", "a"),
                goals=[_is_a("rex", "a"), _is_a("rex", "b")],
                goal_mode="all",
            ),
            fragment=["compound_goal", "horn"],
            procedure="horn",
            status="out_of_fragment",
            kind="unknown",
            refusal="out_of_fragment:compound_goal",
            logic="off",
            note="negative control: the Horn path decides a single target only",
        ),
        _case(
            "refuse-existential-08",
            "refusal",
            _theory(existentials=[{"variable": "?x", "atoms": [_is_a("?x", "animal")], "quote": None}]),
            _query(_is_a("sk0", "animal")),
            fragment=["horn", "existential"],
            procedure="horn",
            status="out_of_fragment",
            kind="unknown",
            refusal="out_of_fragment:existential",
            logic="off",
            note="negative control: an existential is refused by the Horn path, not ignored",
        ),
        _case(
            "refuse-naf-in-l2-09",
            "refusal",
            _naf_theory(),
            _closed(_query(_is_a("rex", "r"))),
            fragment=["horn", "negation"],
            procedure="clausal",
            status="out_of_fragment",
            kind="unknown",
            refusal="out_of_fragment:naf_in_l2",
            note="declared CWA under the clausal procedure is out of fragment",
        ),
        _case(
            "refuse-defeasible-clausal-10",
            "refusal",
            _disjunctive_theory(),
            _query(_is_a("rex", "c")),
            fragment=["horn", "disjunction"],
            procedure="clausal",
            status="out_of_fragment",
            kind="unknown",
            refusal="out_of_fragment:defeasible_with_clausal_fragment",
            defeasible=True,
            note="the defeasible layer would be silently dropped under the clausal procedure",
        ),
        _case(
            "control-horn-logic-on-11",
            "control",
            _theory(morphisms=[_is_a("rex", "p")], rules=[_rule([_is_a("?x", "p")], _is_a("?x", "q"))]),
            _query(_is_a("rex", "q")),
            fragment=["horn"],
            procedure="clausal",
            status="supported",
            kind="yes",
            note="A1 control: the L2 flag selects clausal even for a Horn structure (no routing downgrade)",
        ),
        _case(
            "control-builtin-12",
            "control",
            _theory(rules=[_rule([_m("gte", "?p", "50")], _m("big", "?p"))]),
            _query(_m("big", "x")),
            fragment=["builtin", "horn"],
            procedure="clausal",
            status="out_of_fragment",
            kind="unknown",
            builtins=True,
            note="control: the decision is compatible, but clausification refuses the builtin (second layer)",
        ),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the routing synthetic collection.")
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
