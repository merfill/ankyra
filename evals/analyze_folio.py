"""Analyze FOLIO results: fragment vs extraction (gold-FOL vs text-fed).

For each record it compares three verdicts against the label:
  * text-fed  — the engine run over LLM-extracted structure (from a saved trace);
  * gold-open — the engine over the annotated FOL, open world;
  * gold-closed — the same, closed world.

A case where the gold formalization already fails in the open world is a **fragment**
gap (needs L2 / a different semantics); a case where the gold formalization succeeds
but text-fed fails is an **extraction** gap. LLM-free.

Usage:
    uv run python -m evals.analyze_folio [--sample PATH] [--traces DIR]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from ankyra.engine.answer import build_answer
from ankyra.engine.ledger import HypothesisLedger
from ankyra.engine.verify import verify
from evals.folio_fol import expected_kind, to_theory_query

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "data" / "folio_negation_tier_a.jsonl"
TRACES = ROOT / "out" / "folio"


def load_sample(path: Path = SAMPLE) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _gold_kind(record: dict, world: str) -> tuple[str, str]:
    theory, query = to_theory_query(record, world_assumption=world)
    verdict = verify(theory, query)
    answer = build_answer(theory, query, verdict, HypothesisLedger(), verdict.status)
    return answer.kind, verdict.status


def _text_kind(record: dict, traces: Path) -> tuple[str | None, str | None]:
    path = Path(traces) / f"{record['id']}.json"
    if not path.exists():
        return None, None
    data = json.loads(path.read_text(encoding="utf-8"))
    score = data.get("score") or {}
    return score.get("actual_kind"), score.get("status")


def analyze(record: dict, traces: Path = TRACES) -> dict:
    expected = expected_kind(record["label"], False)
    text_kind, text_status = _text_kind(record, traces)
    gold_open_kind, gold_open_status = _gold_kind(record, "open")
    gold_closed_kind, _ = _gold_kind(record, "closed")
    text_ok = text_kind == expected
    gold_open_ok = gold_open_kind == expected
    gold_closed_ok = gold_closed_kind == expected
    if gold_open_ok:
        category = "ok" if text_ok else "extraction"
    elif gold_closed_ok:
        category = "semantics"  # needs the closed world / reductio
    else:
        category = "fragment"
    return {
        "id": record["id"],
        "label": record["label"],
        "expected": expected,
        "text": (text_kind, text_status),
        "gold_open": (gold_open_kind, gold_open_status),
        "gold_closed": gold_closed_kind,
        "text_ok": text_ok,
        "gold_open_ok": gold_open_ok,
        "gold_closed_ok": gold_closed_ok,
        "category": category,
    }


def run_all(records: list[dict], traces: Path = TRACES) -> list[dict]:
    return [analyze(record, traces) for record in records]


def _report(results: list[dict]) -> None:
    print(
        f"{'id':>6} {'label':9} {'exp':7} {'text':7} {'gold-open':9} "
        f"{'gold-closed':11} cat"
    )
    for result in results:
        print(
            f"{result['id'][-4:]:>6} {result['label']:9} {result['expected']:7} "
            f"{str(result['text'][0]):7} {str(result['gold_open'][0]):9} "
            f"{str(result['gold_closed']):11} {result['category']}"
        )
    total = len(results)
    text_ok = sum(result["text_ok"] for result in results)
    gold_open_ok = sum(result["gold_open_ok"] for result in results)
    gold_closed_ok = sum(result["gold_closed_ok"] for result in results)
    print()
    print(f"text-fed correct:    {text_ok}/{total}")
    print(f"gold-fed open:       {gold_open_ok}/{total}")
    print(f"gold-fed closed:     {gold_closed_ok}/{total}")
    print(f"categories:          {dict(Counter(r['category'] for r in results).most_common())}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FOLIO fragment-vs-extraction analysis.")
    parser.add_argument("--sample", default=str(SAMPLE))
    parser.add_argument("--traces", default=str(TRACES))
    args = parser.parse_args(argv)
    _report(run_all(load_sample(Path(args.sample)), Path(args.traces)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
