"""Render narrations for existing eval traces (no extraction re-run).

Usage: ANKYRA_LIVE=1 uv run python -m evals.narrate --lang ru
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ankyra.core.models import Answer, Explanation, Theory
from ankyra.engine.answer import render_answer
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


def _render_steps(steps, indent: str = "  ") -> list[str]:
    lines: list[str] = []
    for step in steps:
        detail = f"{indent}{step.index}. [{step.kind}] {step.statement}"
        if step.premises:
            detail += f"  <- {step.premises}"
        if step.source:
            detail += f"  [{step.source}]"
        if step.quote:
            detail += f'  quote="{step.quote}"'
        lines.append(detail)
        if step.rule:
            lines.append(f"{indent}      rule {step.rule_index}: {step.rule}")
    return lines


def _steps(explanation: Explanation) -> str:
    lines = _render_steps(explanation.steps)
    return "\n".join(lines) if lines else "  (no derivation)"


def _conflict_block(explanation: Explanation) -> str:
    conflict = explanation.conflict
    if conflict is None:
        return ""
    detail = f"Conflict ({conflict.kind}, {conflict.status}, defeated={conflict.defeated}):"
    if conflict.reason:
        detail += f" {conflict.reason}."
    if conflict.note:
        detail += f" {conflict.note}"
    lines = [detail, "  supporting:"]
    lines += _render_steps(conflict.supporting, indent="    ") or ["    (none)"]
    lines.append("  attacking:")
    lines += _render_steps(conflict.attacking, indent="    ") or ["    (none)"]
    return "\n".join(lines)


def _verdict_block(trace: dict) -> str:
    verdict = trace.get("verdict") or {}
    lines = []
    if verdict.get("gaps"):
        lines.append(f"Gaps: {', '.join(verdict['gaps'])}")
    if verdict.get("bindings"):
        bindings = {k: v for k, v in verdict["bindings"].items() if k.startswith("?")}
        if bindings:
            lines.append(f"Bindings: {bindings}")
    if verdict.get("unused_premises"):
        lines.append(f"Unused premises: {verdict['unused_premises']}")
    if trace.get("frontier"):
        lines.append(f"Frontier: {', '.join(trace['frontier'])}")
    waves = trace.get("waves") or []
    if waves:
        lines.append("Waves: " + " | ".join(
            f"w{w.get('wave')}:{w.get('category')}{('(' + w['reason'] + ')') if w.get('reason') else ''}"
            for w in waves
        ))
    return "\n".join(lines)


def _load_items(args, wanted: set[str]) -> list[tuple[str, object, object, dict]]:
    """Return ``(id, text, level, trace)`` items from a traces dir or problem traces."""
    if args.traces_dir:
        items = []
        for path in sorted(Path(args.traces_dir).glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            trace = data.get("trace", data)
            problem_id = trace.get("id") or path.stem
            if wanted and problem_id not in wanted:
                continue
            items.append((problem_id, trace.get("text"), trace.get("level"), trace))
        return items

    out_dir = Path(args.out)
    items = []
    for problem in load_problems():
        if wanted and problem.get("id") not in wanted:
            continue
        path = out_dir / f"{problem['id']}.json"
        if not path.exists():
            print(f"[{problem.get('id')}] no trace at {path}")
            continue
        items.append((problem.get("id"), problem["text"], problem.get("level"),
                      json.loads(path.read_text(encoding="utf-8"))))
    return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Narrate existing eval traces.")
    parser.add_argument("--lang", default="ru", help="Narration language (name or code).")
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--ids", default="")
    parser.add_argument(
        "--traces-dir", default="",
        help="Directory of trace JSON files (e.g. evals/out/proofwriter); wrapper files are unwrapped.",
    )
    parser.add_argument(
        "--no-narration", dest="narration", action="store_false",
        help="Skip the LLM narration (render the mechanical trace only).",
    )
    args = parser.parse_args(argv)

    wanted = {item.strip() for item in args.ids.split(",") if item.strip()}
    llm = create_chat_llm(role="answer") if args.narration else None

    for problem_id, text, level, trace in _load_items(args, wanted):
        explanation = (
            Explanation.model_validate(trace["explanation"])
            if trace.get("explanation")
            else Explanation()
        )
        theory = Theory.model_validate(trace["theory"]) if trace.get("theory") else None
        explanation = _with_rule_text(explanation, theory)
        answer = Answer.model_validate(trace["answer"]) if trace.get("answer") else Answer()
        print("=" * 78)
        print(f"[{problem_id}] L{level} — {text}")
        print(render_answer(answer, args.lang))
        print("Mechanical steps:")
        print(_steps(explanation))
        if explanation.conflict is not None:
            print(_conflict_block(explanation))
        verdict_block = _verdict_block(trace)
        if verdict_block:
            print(verdict_block)
        print(
            f"Status: {trace.get('status')} | kind: {answer.kind} "
            f"| strength: {answer.strength} | value: {answer.value} "
            f"| hypotheses: {answer.hypotheses_used}"
        )
        if not args.narration:
            continue
        if explanation.steps or explanation.conflict is not None:
            narration = narrate_explanation(
                llm, explanation, answer=answer, language=args.lang
            )
            print(f"Narration ({args.lang}):")
            print("  " + narration.strip().replace("\n", "\n  "))
        else:
            print(f"Narration ({args.lang}): (nothing to narrate — no proof)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
