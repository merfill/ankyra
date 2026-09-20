"""Build the committed defeasible synthetic collection (deterministic, LLM-free).

The defeasible layer (``ANKYRA_DEFEASIBLE``, ``engine/defeasible.py``) was
implemented but unbenchmarked (``docs/reasoning_roadmap.md`` D). This collection is
its gate: structured theory/query pairs with independently written expected
verdicts, run by ``evals.defeasible_synthetic`` with the layer enabled.

Usage:
    uv run python -m evals.build_defeasible_synthetic [--out PATH]

Cases cover resolved specificity (both polarities), an undecided conflict, a strict
fact overriding a default, and the negative control where the layer is off (the same
conflict becomes a strict contradiction).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.build_l1_synthetic import _is_a, _m, _query, _rule, _theory

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DEFAULT_OUT = DATA / "defeasible_synthetic.jsonl"


def _case(
    case_id: str,
    mechanism: str,
    theory: dict,
    query: dict,
    status: str,
    kind: str,
    *,
    defeasible: bool,
    strength: str | None = None,
    conflict: tuple[str, str] | None = None,
    layer: bool = True,
    note: str = "",
) -> dict:
    if strength is None:
        strength = "proven" if status in {"supported", "refuted"} else "not_proven"
    return {
        "id": case_id,
        "mechanism": mechanism,
        "note": note,
        "defeasible_layer": layer,
        "theory": theory,
        "query": query,
        "expected": {
            "status": status,
            "kind": kind,
            "strength": strength,
            "defeasible": defeasible,
            "conflict": list(conflict) if conflict else None,
        },
    }


def _penguin_axioms() -> list[dict]:
    return [_is_a("tweety", "penguin"), _is_a("penguin", "bird")]


def cases() -> list[dict]:
    collected = [
        _case(
            "penguin-refute-01",
            "specificity",
            _theory(
                objects=["tweety", "penguin", "bird"],
                morphisms=_penguin_axioms(),
                rules=[
                    _rule([_is_a("?x", "bird")], _m("fly", "?x")),
                    _rule([_is_a("?x", "penguin")], _m("fly", "?x", neg=True)),
                ],
            ),
            _query(_m("fly", "tweety")),
            "refuted", "no",
            defeasible=True,
            note="the penguin default is strictly more specific and wins",
        ),
        _case(
            "penguin-support-02",
            "specificity",
            _theory(
                objects=["tweety", "penguin", "bird"],
                morphisms=_penguin_axioms(),
                rules=[
                    _rule([_is_a("?x", "bird")], _m("fly", "?x", neg=True)),
                    _rule([_is_a("?x", "penguin")], _m("fly", "?x")),
                ],
            ),
            _query(_m("fly", "tweety")),
            "supported", "yes",
            defeasible=True,
            note="specificity is polarity-independent",
        ),
        _case(
            "nixon-undecided-03",
            "undecided",
            _theory(
                objects=["nixon", "quaker", "republican"],
                morphisms=[_is_a("nixon", "quaker"), _is_a("nixon", "republican")],
                rules=[
                    _rule([_is_a("?x", "quaker")], _m("pacifist", "?x")),
                    _rule([_is_a("?x", "republican")], _m("pacifist", "?x", neg=True)),
                ],
            ),
            _query(_m("pacifist", "nixon")),
            "unsupported", "unknown",
            defeasible=False,
            conflict=("defeasible", "undecided"),
            note="incomparable defaults are never guessed",
        ),
        _case(
            "strict-overrides-default-04",
            "strict",
            _theory(
                objects=["tweety", "penguin", "bird"],
                morphisms=[*_penguin_axioms(), _m("fly", "tweety", neg=True)],
                rules=[_rule([_is_a("?x", "bird")], _m("fly", "?x"))],
            ),
            _query(_m("fly", "tweety")),
            "refuted", "no",
            defeasible=False,
            note="a strict negative fact overrides a default",
        ),
        _case(
            "agreeing-defaults-05",
            "no_conflict",
            _theory(
                objects=["tweety", "penguin", "bird"],
                morphisms=_penguin_axioms(),
                rules=[
                    _rule([_is_a("?x", "bird")], _m("fly", "?x")),
                    _rule([_is_a("?x", "penguin")], _m("fly", "?x")),
                ],
            ),
            _query(_m("fly", "tweety")),
            "supported", "yes",
            defeasible=True,
            note="agreeing defaults derive normally",
        ),
        _case(
            "single-default-06",
            "no_conflict",
            _theory(
                objects=["tweety", "bird"],
                morphisms=[_is_a("tweety", "bird")],
                rules=[_rule([_is_a("?x", "bird")], _m("fly", "?x"))],
            ),
            _query(_m("fly", "tweety")),
            "supported", "yes",
            defeasible=True,
            note="a single default applies without conflict",
        ),
        _case(
            "resolved-conflict-in-explanation-07",
            "specificity",
            _theory(
                objects=["tweety", "penguin", "bird"],
                morphisms=_penguin_axioms(),
                rules=[
                    _rule([_is_a("?x", "bird")], _m("fly", "?x")),
                    _rule([_is_a("?x", "penguin")], _m("fly", "?x", neg=True)),
                ],
            ),
            _query(_m("fly", "tweety")),
            "refuted", "no",
            defeasible=True,
            conflict=("defeasible", "resolved"),
            note="the resolved conflict is recorded in the explanation",
        ),
        _case(
            "layer-off-control-08",
            "control",
            _theory(
                objects=["tweety", "penguin", "bird"],
                morphisms=_penguin_axioms(),
                rules=[
                    _rule([_is_a("?x", "bird")], _m("fly", "?x")),
                    _rule([_is_a("?x", "penguin")], _m("fly", "?x", neg=True)),
                ],
            ),
            _query(_m("fly", "tweety")),
            "contradiction", "contradiction",
            defeasible=False,
            layer=False,
            note="negative control: without the layer the two defaults are a strict contradiction",
        ),
    ]
    return collected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the defeasible synthetic collection.")
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
