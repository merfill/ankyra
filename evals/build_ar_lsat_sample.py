"""Build the committed AR-LSAT samples for the L3 gate (deterministic, LLM-free).

Selection uses only dataset **metadata** — never a parse of the passage/question text
(``docs/task.md`` §3.8): it groups by ``fatherId`` (a game family), normalizes the
``tags`` question/game type into the committed question kinds, buckets by ``passage``
length and balances the answer letter A–E (``docs/l3_plan.md`` D-L3-9).

Splits (D-L3-8): the official **development** and **test** splits are
``fatherId``/``passage``-disjoint, so they are used as the live **dev** and **eval**
pools; the **training** split is excluded (a model may have seen it). Four games share
a ``fatherId``, so dev = one family (4 games) and eval = three families (12 games).

The gold-fed tier (hand-encoded real games) is authored separately.

Usage::

    uv run python -m evals.build_ar_lsat_sample [--out-dir evals/data]
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CACHE = DATA / ".cache" / "ar_lsat"

SOURCE = "zhongwanjun/AR-LSAT"
_URL = "https://raw.githubusercontent.com/zhongwanjun/AR-LSAT/main/data/{name}.json"
_FILES = {
    "development": "AR_DevelopmentData",
    "test": "AR_TestData",
}

# Question kinds in the committed L3 fragment. Everything else is committed but
# reported `out_of_fragment` (never scored as a failure).
IN_FRAGMENT = {"not_violate", "must", "could", "must_be_false", "complete_list"}
# Metadata words that mark a question outside the fragment.
_OUT_WORDS = (
    "except", "substitution", "how many", "total number", "minimum", "maximum",
    "earliest", "latest", "determine", "supply the if", "could be false",
)

TIERS = {"dev": ("development", 1, 12), "eval": ("test", 3, 30)}


def _download(split: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{split}.json"
    if not path.exists():
        url = _URL.format(name=_FILES[split])
        print(f"downloading {url}")
        with urllib.request.urlopen(url, timeout=120) as response:
            path.write_bytes(response.read())
    return path


def normalize_kind(tag: str) -> str:
    """Map a dataset ``tags`` question type to a committed kind (metadata only)."""
    text = (tag or "").strip().lower()
    if not text:
        return "other"
    if any(word in text for word in _OUT_WORDS):
        return "out"
    if "complete and accurate list" in text:
        return "complete_list"
    if "cannot be true" in text or "must be false" in text:
        return "must_be_false"
    if "could be true" in text:
        return "could"
    if "must be true" in text:
        return "must"
    if "acceptab" in text:
        return "not_violate"
    return "other"


def has_assumption(tag: str) -> bool:
    """Whether the tag marks an "if …" question (a hypothetical premise)."""
    text = (tag or "").strip().lower()
    return "if" in text or "pifq" in text


def length_bucket(passage: str) -> str:
    size = len(passage or "")
    if size < 500:
        return "short"
    if size < 650:
        return "medium"
    return "long"


def _rows(split: str) -> list[dict]:
    games = json.loads(_download(split).read_text(encoding="utf-8"))
    rows: list[dict] = []
    for game in games:
        passage = game["passage"]
        for question in game["questions"]:
            tags = question.get("tags") or ["", "", "", ""]
            tag = (tags[1] if len(tags) > 1 else "") or ""
            game_tag = (tags[2] if len(tags) > 2 else "") or ""
            letter = str(question.get("answer") or "").strip().upper()
            answer_index = ord(letter) - ord("A") if len(letter) == 1 and "A" <= letter <= "E" else None
            rows.append(
                {
                    "id": question.get("id") or f"{game['id']}_{question.get('questionId')}",
                    "fatherId": game["fatherId"],
                    "split": split,
                    "source": SOURCE,
                    "passage": passage,
                    "question": question["question"],
                    "options": list(question["options"]),
                    "answer_letter": letter,
                    "answer_index": answer_index,
                    "raw_tag": tag,
                    "game_type": game_tag or "other",
                    "question_kind": normalize_kind(tag),
                    "has_assumption": has_assumption(tag),
                    "length": length_bucket(passage),
                }
            )
    for row in rows:
        row["in_fragment"] = row["question_kind"] in IN_FRAGMENT and row["answer_index"] is not None
    return rows


def _select_families(rows: list[dict], count: int) -> list[str]:
    """Pick families maximizing question-kind diversity, then in-fragment rows."""
    by_family: dict[str, list[dict]] = {}
    for row in rows:
        by_family.setdefault(row["fatherId"], []).append(row)
    scored = []
    for father, members in by_family.items():
        kinds = {m["question_kind"] for m in members if m["in_fragment"]}
        in_fragment = sum(1 for m in members if m["in_fragment"])
        scored.append((len(kinds), in_fragment, father))
    scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [item[2] for item in scored[:count]]


def _select_questions(rows: list[dict], target: int) -> list[dict]:
    """Greedily balance the (question kind, answer letter) cells, tie-break by id."""
    pool = sorted((row for row in rows if row["in_fragment"]), key=lambda row: row["id"])
    selected: list[dict] = []
    kind_seen: Counter = Counter()
    answer_seen: Counter = Counter()
    while pool and len(selected) < target:
        pool.sort(key=lambda row: (kind_seen[row["question_kind"]], answer_seen[row["answer_letter"]], row["id"]))
        row = pool.pop(0)
        selected.append(row)
        kind_seen[row["question_kind"]] += 1
        answer_seen[row["answer_letter"]] += 1
    return selected


def build_tier(tier: str) -> list[dict]:
    split, families_n, target = TIERS[tier]
    rows = _rows(split)
    chosen_families = _select_families(rows, families_n)
    family_rows = [row for row in rows if row["fatherId"] in set(chosen_families)]
    selected = _select_questions(family_rows, target)
    selected.sort(key=lambda row: (row["fatherId"], row["id"]))
    return selected


def cases() -> dict[str, list[dict]]:
    return {tier: build_tier(tier) for tier in TIERS}


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the AR-LSAT dev/eval samples.")
    parser.add_argument("--out-dir", default=str(DATA))
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    built = cases()
    for tier, rows in built.items():
        out = out_dir / f"ar_lsat_{tier}.jsonl"
        _write(out, rows)
        kinds = Counter(row["question_kind"] for row in rows)
        answers = Counter(row["answer_letter"] for row in rows)
        games = sorted({row["id"].rsplit("_", 1)[0] for row in rows})
        print(
            f"{tier}: {len(rows)} questions over {len(games)} games "
            f"(families {sorted({row['fatherId'] for row in rows})})"
        )
        print(f"  kinds:   {dict(kinds.most_common())}")
        print(f"  answers: {dict(sorted(answers.items()))}")
        print(f"  wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
