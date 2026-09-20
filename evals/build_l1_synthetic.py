"""Build the committed L1 synthetic collection (deterministic, LLM-free).

The public collections do not exercise disjointness constraints, negation-as-failure
or the declared closed world (see ``docs/prontoqa.md`` §8 and ``docs/l1_plan.md``
§6/D-L1-5). This collection is the primary L1 gate: each case is a fully structured
theory/query pair with an independently written expected verdict, graded by
``evals.l1_synthetic``. It runs no LLM, so there is zero provider variance.

Usage:
    uv run python -m evals.build_l1_synthetic [--out PATH]

Cases are grouped by ``mechanism``; negative controls (open world must not derive a
CWA answer, non-stratifiable programs, one-sided disjointness) are mandatory so the
gate can fail without the new semantics.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DEFAULT_OUT = DATA / "l1_synthetic.jsonl"


def _m(pred: str, subject: str | None = None, obj: str | None = None, *, neg: bool = False) -> dict:
    return {"predicate": pred, "subject": subject, "object": obj, "negated": neg, "modality": "neutral"}


def _is_a(subject: str, obj: str, *, neg: bool = False) -> dict:
    return _m("is_a", subject, obj, neg=neg)


def _rule(conditions: list[dict], consequence: dict) -> dict:
    return {
        "conditions": conditions,
        "consequence": consequence,
        "kind": "implication",
        "forall": {},
        "source": "quote",
        "quote": None,
    }


def _constraint(left: str, right: str, quote: str | None = None) -> dict:
    return {"kind": "disjoint", "left": left, "right": right, "quote": quote}


def _theory(objects=(), morphisms=(), rules=(), constraints=()) -> dict:
    return {
        "objects": [{"id": oid} for oid in objects],
        "morphisms": list(morphisms),
        "rules": list(rules),
        "constraints": list(constraints),
        "source_text": "",
        "domain": [],
    }


def _query(target: dict, conditions=(), *, world: str = "open", answer_type: str = "yes_no") -> dict:
    return {
        "conditions": list(conditions),
        "target": target,
        "variables": {},
        "answer_type": answer_type,
        "world_assumption": world,
    }


def _case(case_id, mechanism, theory, query, status, kind, *, strength=None, note=""):
    if strength is None:
        strength = "proven" if status in {"supported", "refuted"} else "not_proven"
    return {
        "id": case_id,
        "mechanism": mechanism,
        "note": note,
        "theory": theory,
        "query": query,
        "expected": {"status": status, "kind": kind, "strength": strength},
    }


def _disjointness_cases() -> list[dict]:
    real_imaginary = [_constraint("real_number", "imaginary", "No real number is imaginary.")]
    cases = [
        _case(
            "disjoint-refute-01",
            "disjointness",
            _theory(objects=["a", "real_number", "imaginary"], morphisms=[_is_a("a", "real_number")], constraints=real_imaginary),
            _query(_is_a("a", "imaginary")),
            "refuted", "no",
            note="is_a(a, real_number) + disjoint derives NOT imaginary(a)",
        ),
        _case(
            "disjoint-refute-02",
            "disjointness",
            _theory(
                objects=["a", "prime", "real_number", "imaginary"],
                morphisms=[_is_a("a", "prime")],
                rules=[_rule([_is_a("?x", "prime")], _is_a("?x", "real_number"))],
                constraints=real_imaginary,
            ),
            _query(_is_a("a", "imaginary")),
            "refuted", "no",
            note="the constraint fires after the positive chain closes",
        ),
        _case(
            "disjoint-contradiction-03",
            "disjointness",
            _theory(objects=["a", "real_number", "imaginary"], morphisms=[_is_a("a", "real_number"), _is_a("a", "imaginary")], constraints=real_imaginary),
            _query(_is_a("a", "imaginary")),
            "contradiction", "contradiction", strength="not_proven",
            note="both sides hold: a real contradiction",
        ),
        _case(
            "disjoint-one-sided-04",
            "disjointness",
            _theory(objects=["a", "real_number", "imaginary"], morphisms=[_is_a("a", "real_number")], constraints=real_imaginary),
            _query(_is_a("a", "transcendental")),
            "unsupported", "unknown",
            note="a one-sided constraint draws no conclusion about an unrelated class",
        ),
        _case(
            "disjoint-holds-05",
            "disjointness",
            _theory(objects=["a", "real_number", "imaginary"], morphisms=[_is_a("a", "real_number")], constraints=real_imaginary),
            _query(_is_a("a", "real_number")),
            "supported", "yes",
            note="the held side is still provable",
        ),
        _case(
            "disjoint-symmetric-06",
            "disjointness",
            _theory(objects=["a", "real_number", "imaginary"], morphisms=[_is_a("a", "imaginary")], constraints=real_imaginary),
            _query(_is_a("a", "real_number")),
            "refuted", "no",
            note="disjointness is symmetric",
        ),
        _case(
            "disjoint-transitive-07",
            "disjointness",
            _theory(
                objects=["a", "p", "q", "real_number", "imaginary"],
                morphisms=[_is_a("a", "p")],
                rules=[
                    _rule([_is_a("?x", "p")], _is_a("?x", "q")),
                    _rule([_is_a("?x", "q")], _is_a("?x", "real_number")),
                ],
                constraints=real_imaginary,
            ),
            _query(_is_a("a", "imaginary")),
            "refuted", "no",
            note="constraint over the transitive closure of is_a",
        ),
        _case(
            "disjoint-unrelated-08",
            "disjointness",
            _theory(objects=["a", "cat", "dog"], morphisms=[_is_a("a", "cat")], constraints=[_constraint("cat", "dog")]),
            _query(_is_a("a", "fish")),
            "unsupported", "unknown",
            note="disjoint classes do not make an arbitrary third class false in an open world",
        ),
        _case(
            "disjoint-two-constraints-09",
            "disjointness",
            _theory(
                objects=["a", "real_number", "imaginary", "positive", "negative"],
                morphisms=[_is_a("a", "real_number"), _is_a("a", "positive")],
                constraints=[_constraint("real_number", "imaginary"), _constraint("positive", "negative")],
            ),
            _query(_is_a("a", "imaginary")),
            "refuted", "no",
            note="two independent constraints both fire",
        ),
        _case(
            "disjoint-different-individuals-10",
            "disjointness",
            _theory(
                objects=["a", "b", "real_number", "imaginary"],
                morphisms=[_is_a("a", "real_number"), _is_a("b", "cat")],
                constraints=[_constraint("real_number", "imaginary")],
            ),
            _query(_is_a("b", "imaginary")),
            "unsupported", "unknown",
            note="a constraint never crosses to a different individual",
        ),
        _case(
            "disjoint-and-naf-11",
            "disjointness",
            _theory(
                objects=["a", "real_number", "imaginary"],
                morphisms=[_is_a("a", "real_number")],
                rules=[
                    _rule(
                        [_is_a("?x", "real_number"), _is_a("?x", "imaginary", neg=True)],
                        _m("consistent_real", "?x"),
                    )
                ],
                constraints=[_constraint("real_number", "imaginary")],
            ),
            _query(_m("consistent_real", "a"), world="closed"),
            "supported", "yes",
            note="a constraint-derived negative satisfies a downstream NAF literal",
        ),
    ]
    return cases


def _negative_consequent_cases() -> list[dict]:
    real_to_not_imaginary = _rule([_is_a("?x", "real_number")], _is_a("?x", "imaginary", neg=True))
    cases = [
        _case(
            "negcon-refute-01",
            "negative_consequent",
            _theory(objects=["a", "real_number", "imaginary"], morphisms=[_is_a("a", "real_number")], rules=[real_to_not_imaginary]),
            _query(_is_a("a", "imaginary")),
            "refuted", "no",
            note="a negative rule consequent refutes the positive target",
        ),
        _case(
            "negcon-positive-chain-02",
            "negative_consequent",
            _theory(
                objects=["a", "prime", "real_number", "imaginary"],
                morphisms=[_is_a("a", "prime")],
                rules=[
                    _rule([_is_a("?x", "prime")], _is_a("?x", "real_number")),
                    real_to_not_imaginary,
                ],
            ),
            _query(_is_a("a", "real_number")),
            "supported", "yes",
            note="the positive chain still supports",
        ),
        _case(
            "negcon-negated-target-03",
            "negative_consequent",
            _theory(objects=["a", "real_number", "imaginary"], morphisms=[_is_a("a", "real_number")], rules=[real_to_not_imaginary]),
            _query(_is_a("a", "imaginary", neg=True)),
            "supported", "yes",
            note="a negated target matches the derived negative fact",
        ),
        _case(
            "negcon-explicit-axiom-04",
            "negative_consequent",
            _theory(objects=["a", "imaginary"], morphisms=[_is_a("a", "imaginary", neg=True)]),
            _query(_is_a("a", "imaginary")),
            "refuted", "no",
            note="an explicit negative axiom refutes the positive target",
        ),
        _case(
            "negcon-explicit-axiom-05",
            "negative_consequent",
            _theory(objects=["a", "imaginary"], morphisms=[_is_a("a", "imaginary", neg=True)]),
            _query(_is_a("a", "imaginary", neg=True)),
            "supported", "yes",
            note="an explicit negative axiom supports the negated target",
        ),
        _case(
            "negcon-chain-06",
            "negative_consequent",
            _theory(
                objects=["a", "prime", "real_number", "imaginary"],
                morphisms=[_is_a("a", "prime")],
                rules=[
                    _rule([_is_a("?x", "prime")], _is_a("?x", "real_number")),
                    real_to_not_imaginary,
                ],
            ),
            _query(_is_a("a", "imaginary")),
            "refuted", "no",
            note="negative consequent reached through a positive chain",
        ),
    ]
    return cases


def _naf_theory() -> dict:
    return _theory(
        objects=["alice", "person"],
        morphisms=[_is_a("alice", "person")],
        rules=[
            _rule(
                [_is_a("?x", "person"), _m("has_license", "?x", neg=True)],
                _m("needs_training", "?x"),
            )
        ],
    )


def _stratified_theory() -> dict:
    return _theory(
        objects=["alice", "person", "exempt"],
        morphisms=[_is_a("alice", "person")],
        rules=[
            _rule([_is_a("?x", "person"), _m("exempt", "?x", neg=True)], _m("must_pay", "?x")),
            _rule([_is_a("?x", "exempt")], _m("exempt", "?x")),
        ],
    )


def _non_stratifiable_theory() -> dict:
    return _theory(
        objects=["alice", "person"],
        morphisms=[_is_a("alice", "person")],
        rules=[
            _rule([_is_a("?x", "person"), _m("q", "?x", neg=True)], _m("p", "?x")),
            _rule([_m("p", "?x")], _m("q", "?x")),
        ],
    )


def _naf_cases() -> list[dict]:
    return [
        _case(
            "naf-derive-01",
            "naf",
            _naf_theory(),
            _query(_m("needs_training", "alice"), world="closed"),
            "supported", "yes",
            note="closed world: alice has no derivable license, so she needs training",
        ),
        _case(
            "naf-open-control-02",
            "naf-control",
            _naf_theory(),
            _query(_m("needs_training", "alice")),
            "unsupported", "unknown",
            note="negative control: an open world must not fire negation-as-failure",
        ),
        _case(
            "naf-blocked-03",
            "naf",
            _theory(
                objects=["alice", "person"],
                morphisms=[_is_a("alice", "person")],
                rules=[
                    _rule([_is_a("?x", "person")], _m("has_license", "?x")),
                    _rule([_is_a("?x", "person"), _m("has_license", "?x", neg=True)], _m("needs_training", "?x")),
                ],
            ),
            _query(_m("needs_training", "alice"), world="closed"),
            "refuted", "no",
            note="the negated literal fails because the license is derivable, so the "
            "atom is unprovable and the closed world refutes it",
        ),
        _case(
            "naf-explicit-negative-04",
            "naf",
            _theory(
                objects=["alice", "person"],
                morphisms=[_is_a("alice", "person"), _m("has_license", "alice", neg=True)],
                rules=[
                    _rule([_is_a("?x", "person"), _m("has_license", "?x", neg=True)], _m("needs_training", "?x"))
                ],
            ),
            _query(_m("needs_training", "alice"), world="closed"),
            "supported", "yes",
            note="an explicit negative fact also satisfies the literal",
        ),
        _case(
            "cwa-refute-05",
            "cwa",
            _theory(objects=["alice", "person"], morphisms=[_is_a("alice", "person")]),
            _query(_m("has_license", "alice"), world="closed"),
            "refuted", "no",
            note="closed world refutes an unprovable ground target",
        ),
        _case(
            "cwa-open-control-06",
            "cwa-control",
            _theory(objects=["alice", "person"], morphisms=[_is_a("alice", "person")]),
            _query(_m("has_license", "alice")),
            "unsupported", "unknown",
            note="negative control: an open world leaves it unknown",
        ),
        _case(
            "cwa-open-target-07",
            "cwa-control",
            _theory(objects=["alice", "person"], morphisms=[_is_a("alice", "person")]),
            _query(_m("has_license", "?who"), world="closed", answer_type="open"),
            "unsupported", "unknown",
            note="negative control: CWA never refutes an open (variable) target",
        ),
        _case(
            "cwa-negated-target-08",
            "cwa",
            _theory(objects=["alice", "person"], morphisms=[_is_a("alice", "person")]),
            _query(_m("has_license", "alice", neg=True), world="closed"),
            "supported", "yes",
            note="closed world supports the negated target by failure",
        ),
        _case(
            "cwa-provable-09",
            "cwa-control",
            _theory(objects=["alice", "person"], morphisms=[_is_a("alice", "person"), _m("has_license", "alice")]),
            _query(_m("has_license", "alice"), world="closed"),
            "supported", "yes",
            note="control: CWA does not override a provable target",
        ),
        _case(
            "stratified-derive-10",
            "stratification",
            _stratified_theory(),
            _query(_m("must_pay", "alice"), world="closed"),
            "supported", "yes",
            note="a stratified program derives through the lower stratum",
        ),
        _case(
            "stratified-blocked-11",
            "stratification",
            _theory(
                objects=["alice", "person", "exempt"],
                morphisms=[_is_a("alice", "person"), _is_a("alice", "exempt")],
                rules=[
                    _rule([_is_a("?x", "person"), _m("exempt", "?x", neg=True)], _m("must_pay", "?x")),
                    _rule([_is_a("?x", "exempt")], _m("exempt", "?x")),
                ],
            ),
            _query(_m("must_pay", "alice"), world="closed"),
            "refuted", "no",
            note="a provable lower-stratum atom blocks the NAF literal, so the head is "
            "unprovable and the closed world refutes it",
        ),
        _case(
            "non-stratifiable-12",
            "stratification",
            _non_stratifiable_theory(),
            _query(_m("p", "alice"), world="closed"),
            "out_of_fragment", "unknown", strength="not_proven",
            note="a negative cycle is reported out_of_fragment, never guessed",
        ),
        _case(
            "non-stratifiable-open-13",
            "stratification-control",
            _non_stratifiable_theory(),
            _query(_m("p", "alice")),
            "unsupported", "unknown",
            note="negative control: the open world never invokes stratification",
        ),
        _case(
            "naf-explicit-negative-open-14",
            "naf",
            _theory(
                objects=["alice", "person"],
                morphisms=[_is_a("alice", "person"), _m("has_license", "alice", neg=True)],
                rules=[
                    _rule([_is_a("?x", "person"), _m("has_license", "?x", neg=True)], _m("needs_training", "?x"))
                ],
            ),
            _query(_m("needs_training", "alice")),
            "supported", "yes",
            note="an explicit negative fact satisfies the literal in an open world",
        ),
        _case(
            "naf-unused-condition-15",
            "naf-control",
            _naf_theory(),
            _query(
                _m("needs_training", "alice"),
                conditions=[_is_a("bob", "ghost")],
                world="closed",
            ),
            "insufficient", "unknown",
            note="an unused question premise blocks support even when the target derives",
        ),
        _case(
            "naf-multistrata-derive-16",
            "stratification",
            _theory(
                objects=["alice", "person"],
                morphisms=[_is_a("alice", "person")],
                rules=[
                    _rule([_is_a("?x", "person"), _m("blocked", "?x", neg=True)], _m("approved", "?x")),
                    _rule([_is_a("?x", "person"), _m("approved", "?x", neg=True)], _m("pending", "?x")),
                ],
            ),
            _query(_m("approved", "alice"), world="closed"),
            "supported", "yes",
            note="a three-stratum NAF program derives through the first negation",
        ),
        _case(
            "naf-multistrata-blocked-17",
            "stratification",
            _theory(
                objects=["alice", "person"],
                morphisms=[_is_a("alice", "person")],
                rules=[
                    _rule([_is_a("?x", "person"), _m("blocked", "?x", neg=True)], _m("approved", "?x")),
                    _rule([_is_a("?x", "person"), _m("approved", "?x", neg=True)], _m("pending", "?x")),
                ],
            ),
            _query(_m("pending", "alice"), world="closed"),
            "refuted", "no",
            note="the second stratum sees the first fully computed: approved blocks pending",
        ),
    ]


def _more_cases() -> list[dict]:
    return [
        _case(
            "control-inconsistent-unrelated-01",
            "control",
            _theory(objects=["p", "q"], morphisms=[_m("p"), _m("p", neg=True), _m("q")]),
            _query(_m("q")),
            "supported", "yes",
            note="an inconsistency unrelated to the target does not change the answer",
        ),
        _case(
            "control-contradiction-target-02",
            "control",
            _theory(objects=["p"], morphisms=[_m("p"), _m("p", neg=True)]),
            _query(_m("p")),
            "contradiction", "contradiction", strength="not_proven",
            note="the target's own proof contains the complementary pair",
        ),
        _case(
            "disjoint-holds-after-chain-03",
            "disjointness",
            _theory(
                objects=["a", "p", "real_number", "imaginary"],
                morphisms=[_is_a("a", "p")],
                rules=[_rule([_is_a("?x", "p")], _is_a("?x", "real_number"))],
                constraints=[_constraint("real_number", "imaginary")],
            ),
            _query(_is_a("a", "real_number")),
            "supported", "yes",
            note="the positive side of a disjointness is still supported",
        ),
        _case(
            "negcon-refute-through-disjoint-04",
            "negative_consequent",
            _theory(
                objects=["a", "cat", "mammal", "cold_blooded"],
                morphisms=[_is_a("a", "cat")],
                rules=[
                    _rule([_is_a("?x", "cat")], _is_a("?x", "mammal")),
                    _rule([_is_a("?x", "mammal")], _is_a("?x", "cold_blooded", neg=True)),
                ],
            ),
            _query(_is_a("a", "cold_blooded")),
            "refuted", "no",
            note="negative property through a subsumption chain",
        ),
        _case(
            "cwa-chain-refute-05",
            "cwa",
            _theory(
                objects=["a", "p", "q"],
                morphisms=[_is_a("a", "p")],
                rules=[_rule([_is_a("?x", "p")], _m("r", "?x"))],
            ),
            _query(_m("s", "a"), world="closed"),
            "refuted", "no",
            note="closed world after a non-trivial closure still refutes an unprovable atom",
        ),
        _case(
            "cwa-unknown-predicate-06",
            "cwa",
            _theory(objects=["alice", "person"], morphisms=[_is_a("alice", "person")]),
            _query(_m("totally_unknown", "alice"), world="closed"),
            "refuted", "no",
            note="the declared closed world refutes even a predicate absent from the theory",
        ),
    ]


def cases() -> list[dict]:
    """The full deterministic collection, grouped by mechanism."""
    return (
        _disjointness_cases()
        + _negative_consequent_cases()
        + _naf_cases()
        + _more_cases()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the L1 synthetic collection.")
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
