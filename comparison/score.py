"""Unify external framework results into one comparison table.

Logic-LM writes its inference output into its own tree
(``outputs/logic_inference/<dataset>_<split>_<model>_backup-<backup>.json``);
LINC results are written by ``run_linc`` into ``comparison/results/``. This tool
normalizes both into accuracy / executable rate / executable accuracy.

Usage::

    python -m comparison.score --logicllm-repo /tmp/opencode/cmp/logicllm \
        --dataset FOLIO --split dev --model gpt-4 --backup random
    python -m comparison.score --linc comparison/results/linc_folio_tier_a.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _get_choice(answer: str) -> str | None:
    answer = (answer or "").strip()
    for choice in ("A", "B", "C", "D", "E", "F", "G", "H"):
        if answer.startswith(choice):
            return choice
    return None


def score_logicllm(path: Path) -> dict:
    rows = json.loads(path.read_text(encoding="utf-8"))
    n = len(rows)
    correct = exe = exe_correct = 0
    for row in rows:
        gold = row["answer"].replace("(", "").replace(")", "").strip()
        pred = _get_choice(row.get("predicted_answer") or "")
        ok = pred == gold
        correct += ok
        if row["flag"] == "success":
            exe += 1
            exe_correct += ok
    return {
        "system": "Logic-LM",
        "n": n,
        "accuracy": correct / n if n else 0.0,
        "exe_rate": exe / n if n else 0.0,
        "exe_accuracy": exe_correct / exe if exe else 0.0,
        "solver_accuracy": exe_correct / n if n else 0.0,
    }


def score_linc(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    preds = data["predictions"]
    n = len(preds)
    correct = exe = 0
    for p in preds:
        pred = str(p["prediction"])
        if pred.startswith("ERROR:") or pred == "Error":
            continue
        exe += 1
        correct += p["prediction"] == p["reference"]
    return {
        "system": "LINC",
        "n": n,
        "accuracy": correct / n if n else 0.0,
        "exe_rate": exe / n if n else 0.0,
        "exe_accuracy": correct / exe if exe else 0.0,
        "solver_accuracy": correct / n if n else 0.0,
    }


def _print(rows: list[dict]) -> None:
    header = (
        f"{'system':10s} {'n':>4s} {'accuracy':>9s} {'exe_rate':>9s} "
        f"{'exe_acc':>9s} {'solver_acc':>10s}"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['system']:10s} {r['n']:>4d} {r['accuracy']:>9.3f} {r['exe_rate']:>9.3f} "
            f"{r['exe_accuracy']:>9.3f} {r['solver_accuracy']:>10.3f}"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--logicllm-repo")
    ap.add_argument("--dataset")
    ap.add_argument("--split")
    ap.add_argument("--model")
    ap.add_argument("--backup", default="random")
    ap.add_argument("--linc", nargs="*", default=[])
    args = ap.parse_args()

    rows = []
    if args.logicllm_repo:
        path = (
            Path(args.logicllm_repo)
            / "outputs"
            / "logic_inference"
            / f"{args.dataset}_{args.split}_{args.model}_backup-{args.backup}.json"
        )
        rows.append(score_logicllm(path))
    for src in args.linc:
        rows.append(score_linc(Path(src)))
    _print(rows)


if __name__ == "__main__":
    main()
