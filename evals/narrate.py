"""Render narrations for existing eval traces (no extraction re-run).

Usage: ANKYRA_LIVE=1 uv run python -m evals.narrate --lang ru
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ankyra.core.models import Explanation, Theory
from ankyra.engine.explain import render_rule
from ankyra.engine.narrate import narrate_explanation
from ankyra.llm.client import create_chat_llm

from evals.run import OUT, load_problems


def _with_rule_text(explanation: Explanation, theory: Theory | None) -> Explanation:
    """Fill rule text from the theory for traces written before it was embedded."""
    if theory is None:
        return explanation
    steps = []
    for step in explanation.steps:
        if step.rule is None and step.rule_index is not None and 0 < step.rule_index <= len(theory.rules):
            step = step.model_copy(update={"rule": render_rule(theory.rules[step.rule_index - 1])})
        steps.append(step)
    return explanation.model_copy(update={"steps": steps})


def _steps(explanation: Explanation) -> str:
    lines = []
    for step in explanation.steps:
        detail = f"  {step.index}. [{step.kind}] {step.statement}"
        if step.premises:
            detail += f"  <- {step.premises}"
        if step.source:
            detail += f"  [{step.source}]"
        if step.quote:
            detail += f'  quote="{step.quote}"'
        lines.append(detail)
        if step.rule:
            lines.append(f"        rule {step.rule_index}: {step.rule}")
    return "\n".join(lines) if lines else "  (no derivation)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Narrate existing eval traces.")
    parser.add_argument("--lang", default="ru", help="Narration language (name or code).")
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--ids", default="")
    args = parser.parse_args(argv)

    wanted = {item.strip() for item in args.ids.split(",") if item.strip()}
    out_dir = Path(args.out)
    llm = create_chat_llm(role="answer")

    for problem in load_problems():
        if wanted and problem.get("id") not in wanted:
            continue
        path = out_dir / f"{problem['id']}.json"
        if not path.exists():
            print(f"[{problem.get('id')}] no trace at {path}")
            continue
        trace = json.loads(path.read_text(encoding="utf-8"))
        explanation = (
            Explanation.model_validate(trace["explanation"])
            if trace.get("explanation")
            else Explanation()
        )
        theory = Theory.model_validate(trace["theory"]) if trace.get("theory") else None
        explanation = _with_rule_text(explanation, theory)
        answer = trace.get("answer") or {}
        print("=" * 78)
        print(f"[{problem.get('id')}] L{problem.get('level')} — {problem['text']}")
        print("Mechanical steps:")
        print(_steps(explanation))
        print(
            f"Status: {trace.get('status')} | strength: {answer.get('strength')} "
            f"| value: {answer.get('value')} | hypotheses: {answer.get('hypotheses_used')}"
        )
        if explanation.steps:
            narration = narrate_explanation(llm, explanation, language=args.lang)
            print(f"Narration ({args.lang}):")
            print("  " + narration.strip().replace("\n", "\n  "))
        else:
            print(f"Narration ({args.lang}): (nothing to narrate — no proof)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
