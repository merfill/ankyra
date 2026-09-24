"""Build the committed GSM8K dev/eval samples for the L4 gate (deterministic).

Source: Cobbe et al., ``openai/grade-school-math`` (MIT), ``data/test.jsonl``. There is
no official development split, so (D-L4-3) the official **test** split is carved
deterministically — by a stable per-index hash, never by wording — into a small **dev**
slice (prompt/IR iteration, not a gate) and a disjoint **eval** slice (the gate). The
**train** split is excluded: a model may have seen it.

The reference value is the trailing ``#### <number>`` of the dataset's ``answer``.

Usage::

    uv run python -m evals.build_gsm8k_sample [--out-dir evals/data]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CACHE = DATA / ".cache" / "gsm8k"

SOURCE = "openai/grade-school-math (test)"
_URL = "https://raw.githubusercontent.com/openai/grade-school-math/master/grade_school_math/data/test.jsonl"

DEV_SIZE = 12
EVAL_SIZE = 40
_MARKER = "####"


def _download() -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "test.jsonl"
    if not path.exists():
        print(f"downloading {_URL}")
        with urllib.request.urlopen(_URL, timeout=120) as response:
            path.write_bytes(response.read())
    return path


def reference(answer: str) -> str:
    """The trailing ``#### <number>`` of the dataset answer, comma-stripped."""
    tail = (answer or "").rsplit(_MARKER, 1)[-1].strip()
    return tail.replace(",", "")


def rows() -> list[dict]:
    text = _download().read_text(encoding="utf-8")
    collected: list[dict] = []
    for index, line in enumerate(text.splitlines()):
        if not line.strip():
            continue
        row = json.loads(line)
        collected.append(
            {
                "id": f"gsm8k-test-{index:04d}",
                "source": SOURCE,
                "split": "test",
                "index": index,
                "question": row["question"],
                "answer": row["answer"],
                "reference": reference(row["answer"]),
            }
        )
    return collected


def _carve_key(row: dict) -> str:
    return hashlib.sha256(f"gsm8k-carve:{row['index']}".encode()).hexdigest()


def carve(collected: list[dict]) -> dict[str, list[dict]]:
    ordered = sorted(collected, key=_carve_key)
    dev = sorted(ordered[:DEV_SIZE], key=lambda row: row["index"])
    evaluation = sorted(ordered[DEV_SIZE : DEV_SIZE + EVAL_SIZE], key=lambda row: row["index"])
    return {"dev": dev, "eval": evaluation}


def cases() -> dict[str, list[dict]]:
    return carve(rows())


def _write(path: Path, selected: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in selected:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the GSM8K dev/eval samples.")
    parser.add_argument("--out-dir", default=str(DATA))
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    built = cases()
    for tier, selected in built.items():
        out = out_dir / f"gsm8k_{tier}.jsonl"
        _write(out, selected)
        print(f"{tier}: {len(selected)} problems, wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
