"""Adapt Ankyra committed samples to Logic-LM and LINC input formats.

Ankyra evaluates fixed subsamples of standard collections. To compare on the
*same tasks* with the same model, the external frameworks are fed exactly those
rows, translated into the schema each framework expects. This module is a pure
data transform: it reads ``evals/data/*.jsonl`` and emits records.

Collections (Ankyra file -> target dataset / split):

    proofwriter_tier_a.jsonl  -> Logic-LM ProofWriter / LINC ProofWriter
    proofwriter_tier_d.jsonl  -> Logic-LM ProofWriter / LINC ProofWriter
    prontoqa_tier_a.jsonl     -> Logic-LM ProntoQA
    prontoqa_tier_b.jsonl     -> Logic-LM ProntoQA
    folio_l2_tier_a.jsonl
    folio_negation_tier_a.jsonl (combined) -> Logic-LM FOLIO / LINC FOLIO
    ar_lsat_eval.jsonl        -> Logic-LM AR-LSAT

The polarities are declared per collection, never inferred from text.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANKYRA_DATA = ROOT / "evals" / "data"

# Ankyra collection -> (input files, logicllm dataset, linc dataset or None)
COLLECTIONS: dict[str, tuple[tuple[str, ...], str, str | None]] = {
    "proofwriter_tier_a": (("proofwriter_tier_a.jsonl",), "ProofWriter", "ProofWriter"),
    "proofwriter_tier_d": (("proofwriter_tier_d.jsonl",), "ProofWriter", "ProofWriter"),
    "prontoqa_tier_a": (("prontoqa_tier_a.jsonl",), "ProntoQA", None),
    "prontoqa_tier_b": (("prontoqa_tier_b.jsonl",), "ProntoQA", None),
    "folio_tier_a": (
        ("folio_l2_tier_a.jsonl", "folio_negation_tier_a.jsonl"),
        "FOLIO",
        "FOLIO",
    ),
    "ar_lsat_eval": (("ar_lsat_eval.jsonl",), "AR-LSAT", None),
}

# Logic-LM's custom split name written into data/<dataset>/<split>.json
SPLIT = {
    "proofwriter_tier_a": "ankyra_tier_a",
    "proofwriter_tier_d": "ankyra_tier_d",
    "prontoqa_tier_a": "ankyra_tier_a",
    "prontoqa_tier_b": "ankyra_tier_b",
    "folio_tier_a": "ankyra_tier_a",
    "ar_lsat_eval": "ankyra_eval",
}

_TRUE_FALSE = ["A) True", "B) False"]
_TRUE_FALSE_UNKNOWN = ["A) True", "B) False", "C) Unknown"]
_TRUE_FALSE_UNCERTAIN = ["A) True", "B) False", "C) Uncertain"]
_THREE_WAY_LETTER = {"True": "A", "False": "B", "Unknown": "C", "Uncertain": "C"}

_LETTERS = "ABCDEFGH"


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_collection(name: str) -> list[dict]:
    """Load and concatenate the Ankyra files of a collection (dedup by id)."""
    if name not in COLLECTIONS:
        raise KeyError(f"unknown collection {name!r}; known: {sorted(COLLECTIONS)}")
    files, _, _ = COLLECTIONS[name]
    seen: dict[str, dict] = {}
    for filename in files:
        for row in _read_jsonl(ANKYRA_DATA / filename):
            seen[row["id"]] = row
    return list(seen.values())


def _choice_question(statement: str, options: list[str]) -> str:
    kinds = [o.split(") ", 1)[1].lower() for o in options]
    listed = ", ".join(kinds[:-1]) + f", or {kinds[-1]}" if len(kinds) > 1 else kinds[0]
    return (
        f"Based on the above information, is the following statement "
        f"{listed}? {statement}"
    )


# --- Logic-LM builders ---------------------------------------------------


def _ll_proofwriter(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "context": r["theory"],
                "question": _choice_question(r["question"], _TRUE_FALSE_UNKNOWN),
                "options": _TRUE_FALSE_UNKNOWN,
                "answer": _THREE_WAY_LETTER[r["answer"]],
            }
        )
    return out


def _ll_prontoqa(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "context": r["context"],
                "question": r["question"],
                "options": _TRUE_FALSE,
                "answer": r["answer"],
            }
        )
    return out


def _ll_folio(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        premises = " ".join(p.strip() for p in r["premises"])
        out.append(
            {
                "id": r["id"],
                "context": premises,
                "question": _choice_question(r["conclusion"], _TRUE_FALSE_UNCERTAIN),
                "options": _TRUE_FALSE_UNCERTAIN,
                "answer": _THREE_WAY_LETTER[r["label"]],
            }
        )
    return out


def _ll_ar_lsat(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        options = [f"{letter}) {opt}" for letter, opt in zip(_LETTERS, r["options"])]
        out.append(
            {
                "id": r["id"],
                "context": r["passage"],
                "question": r["question"],
                "options": options,
                "answer": r["answer_letter"],
            }
        )
    return out


_LOGICLLM_BUILDERS = {
    "ProofWriter": _ll_proofwriter,
    "ProntoQA": _ll_prontoqa,
    "FOLIO": _ll_folio,
    "AR-LSAT": _ll_ar_lsat,
}


def to_logicllm(name: str) -> tuple[str, str, list[dict]]:
    """Return (dataset, split, records) for a Logic-LM run."""
    _, dataset, _ = COLLECTIONS[name]
    rows = load_collection(name)
    return dataset, SPLIT[name], _LOGICLLM_BUILDERS[dataset](rows)


# --- LINC builders (FOLIO and ProofWriter only) --------------------------


def _linc_folio(rows: list[dict]) -> list[dict]:
    return [
        {
            "id": r["id"],
            "premises": [p.strip() for p in r["premises"]],
            "conclusion": r["conclusion"].strip(),
            "label": r["label"],
        }
        for r in rows
    ]


def _punctuate(s: str) -> str:
    s = s.strip()
    return s if s and s[-1] in ".?!" else s + "."


def _linc_proofwriter(rows: list[dict]) -> list[dict]:
    # LINC scores open-world questions in its own vocabulary (Uncertain); its
    # training pipeline applies the same Unknown->Uncertain renaming.
    label_map = {"Unknown": "Uncertain"}
    return [
        {
            "id": r["id"],
            "premises": [_punctuate(p) for p in r["theory"].split(". ") if p.strip()],
            "conclusion": _punctuate(r["question"]),
            "label": label_map.get(r["answer"], r["answer"]),
        }
        for r in rows
    ]


_LINC_BUILDERS = {"FOLIO": _linc_folio, "ProofWriter": _linc_proofwriter}


def to_linc(name: str) -> tuple[str, list[dict]]:
    """Return (dataset, records) for a LINC run, or raise if unsupported."""
    _, _, dataset = COLLECTIONS[name]
    if dataset not in _LINC_BUILDERS:
        raise ValueError(f"LINC does not support collection {name!r} (dataset {dataset})")
    return dataset, _LINC_BUILDERS[dataset](load_collection(name))


# --- CLI -----------------------------------------------------------------


def _report() -> None:
    for name in COLLECTIONS:
        rows = load_collection(name)
        dataset, split, ll = to_logicllm(name)
        ids = [r["id"] for r in ll]
        assert len(ids) == len(set(ids)) == len(rows), f"id mismatch in {name}"
        line = f"{name:22s} -> {dataset:11s} split={split:13s} n={len(rows):3d}"
        if COLLECTIONS[name][2] is not None:
            linc_dataset, linc = to_linc(name)
            assert len(linc) == len(rows)
            line += f" | LINC {linc_dataset}: {linc[0]['premises'][:2]}"
        print(line)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write-logicllm", metavar="REPO", help="write data/ into a Logic-LM clone")
    ap.add_argument("--write-linc", metavar="DIR", help="write converted JSON for the LINC runner")
    args = ap.parse_args()

    if args.write_logicllm:
        repo = Path(args.write_logicllm)
        for name in COLLECTIONS:
            dataset, split, records = to_logicllm(name)
            dest = repo / "data" / dataset
            dest.mkdir(parents=True, exist_ok=True)
            (dest / f"{split}.json").write_text(
                json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"wrote {dest / f'{split}.json'} ({len(records)})")
    if args.write_linc:
        out = Path(args.write_linc)
        out.mkdir(parents=True, exist_ok=True)
        for name in COLLECTIONS:
            if COLLECTIONS[name][2] is None:
                continue
            dataset, records = to_linc(name)
            dest = out / f"{name}.json"
            dest.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"wrote {dest} ({len(records)})")
    if not args.write_logicllm and not args.write_linc:
        _report()
