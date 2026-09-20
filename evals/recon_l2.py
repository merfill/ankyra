"""L2 recon (LLM-free): size the ProntoQA-OOD and FOLIO L2 subsets.

Stage L2 of ``docs/reasoning_roadmap.md`` starts with a construct-level tally of the
two candidate gates (``docs/l2_plan.md`` §6). This script performs it deterministically
and prints a report; it makes no LLM calls and changes nothing else.

ProntoQA-OOD (``tasksource/prontoqa``, the OOD release of Saparov & He) is a set of
JSON files, one per (hop, rule type); each holds 100 entries with a ``test_example``.
This tally classifies every ``test_example`` by the L2 capability it needs:

* ``horn``     — a single positive/negative atom goal, no case split: L0/L1 already.
* ``l2_decomp``— a conjunctive (``and``) or disjunctive (``or``) **goal**, decidable
                 by goal decomposition (prove a disjunct / each conjunct).
* ``l2_reductio`` — the proof uses ``Assume`` (proof by cases / proof by
                 contradiction): the genuinely non-Horn part.

FOLIO (``github.com/Yale-LILY/FOLIO`` v0.0 validation) is tallied by the FOL
constructs of its annotation, reusing ``evals.build_folio_sample``.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "data" / ".cache" / "prontoqa_ood"
HF_TREE = "https://huggingface.co/api/datasets/tasksource/prontoqa/tree/main?recursive=1"
HF_RAW = "https://huggingface.co/datasets/tasksource/prontoqa/resolve/main/"
SOURCE_URL = "https://huggingface.co/datasets/tasksource/prontoqa"

# Rule types in the OOD release, most specific first (filenames embed them).
RULE_TYPES = (
    "ProofByContra",
    "OrElim",
    "OrIntro",
    "AndElim",
    "AndIntro",
    "ProofsOnly",
    "ModusPonens",
    "Composed",
)


def _download_files() -> list[Path]:
    """Download every JSON file of the OOD release into the cache (once)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    tree = json.load(urllib.request.urlopen(HF_TREE, timeout=60))
    files = [item["path"] for item in tree if item["path"].endswith(".json")]
    for name in files:
        dest = CACHE / name
        if dest.exists() and dest.stat().st_size > 1000:
            continue
        request = urllib.request.Request(HF_RAW + name, headers={"User-Agent": "ankyra-recon"})
        with urllib.request.urlopen(request, timeout=180) as response:
            dest.write_bytes(response.read())
    return sorted(CACHE.glob("*.json"))


def rule_type(path: Path) -> str:
    name = path.name
    for candidate in RULE_TYPES:
        if candidate in name:
            return candidate
    return "other"


def goal_of(query: str) -> str:
    return query.split(":", 1)[1].strip() if ":" in query else query


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=\.)\s+", text.strip()) if part.strip()]


def _surface_forms(question: str, goal: str) -> list[str]:
    """Which surface disjunction shapes a ``test_example`` uses (approximate tally).

    A sentence is a *rule antecedent* when it opens with a universal cue or contains
    "that is"; otherwise a sentence containing "or" is a *ground fact*. This is recon
    analysis over benchmark text, not product code.
    """
    forms: list[str] = []
    for sentence in _sentences(question):
        if " or " not in sentence:
            continue
        opener = sentence.split(" ", 1)[0].casefold()
        if opener in {"everything", "every", "each", "any", "all", "whatever"} or " that is " in sentence:
            forms.append("disjunctive_rule_antecedent")
        else:
            forms.append("disjunctive_ground_fact")
    if re.search(r"\bor\b", goal, re.IGNORECASE):
        forms.append("disjunctive_goal")
    if re.search(r"∃|there exists|\bsome\b", f"{question} {goal}", re.IGNORECASE):
        forms.append("existential")
    return forms


def classify(goal: str, proof: str) -> str:
    conjunctive = bool(re.search(r"\band\b", goal))
    disjunctive = bool(re.search(r"\bor\b", goal))
    reductio = "Assume" in proof
    decomposed = conjunctive or disjunctive
    if reductio and decomposed:
        return "l2_reductio+decomp"
    if reductio:
        return "l2_reductio"
    if decomposed:
        return "l2_decomp"
    return "horn"


def _prontoqa_report(paths: list[Path]) -> dict:
    total = 0
    classes: Counter[str] = Counter()
    by_rule: dict[str, Counter[str]] = defaultdict(Counter)
    surfaces = Counter()
    for path in paths:
        rule = rule_type(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        for entry in data.values():
            example = entry.get("test_example")
            if not example:
                continue
            total += 1
            goal = goal_of(example["query"])
            proof = " ".join(step.strip() for step in example["chain_of_thought"])
            kind = classify(goal, proof)
            classes[kind] += 1
            by_rule[rule][kind] += 1
            for form in set(_surface_forms(example["question"], goal)):
                surfaces[form] += 1
    return {"total": total, "classes": classes, "by_rule": by_rule, "surfaces": surfaces}


def _print_prontoqa(report: dict) -> None:
    print(f"ProntoQA-OOD: {report['total']} test_examples ({SOURCE_URL})")
    for kind, count in report["classes"].most_common():
        print(f"  {kind:24} {count:5}  ({100 * count / report['total']:.1f}%)")
    l2 = sum(count for kind, count in report["classes"].items() if kind != "horn")
    print(f"  L2 (any non-horn)        {l2:5}  ({100 * l2 / report['total']:.1f}%)")
    print("  by rule type:")
    for rule in sorted(report["by_rule"]):
        print(f"    {rule:16} {dict(report['by_rule'][rule])}")
    print("  surface forms:")
    for name, count in report["surfaces"].most_common():
        print(f"    {name:28} {count}")
    print("  CRITICAL: 'or' is over class-membership/property atoms (is_a), in rule")
    print("  antecedents, in ground facts and in goals; no existential is exercised.")


def _folio_report() -> dict:
    from evals.build_folio_sample import _load_rows, constructs, in_l1_negation

    rows = _load_rows()
    tally: Counter[str] = Counter()
    l2 = 0
    l2_labels: Counter[str] = Counter()
    beyond = {"equality", "xor", "biconditional", "multivar"}
    for row in rows:
        used = constructs(row)
        for name in used:
            tally[name] += 1
        if (used & {"disjunction", "existential"}) and not (used & beyond):
            l2 += 1
            l2_labels[row["label"]] += 1
    return {
        "rows": len(rows),
        "constructs": tally,
        "l1_negation": sum(1 for row in rows if in_l1_negation(row)),
        "l2": l2,
        "l2_labels": l2_labels,
    }


def _print_folio(report: dict) -> None:
    print(f"\nFOLIO v0.0 validation: {report['rows']} rows")
    print(f"  constructs: {dict(report['constructs'].most_common())}")
    print(f"  in L1 negation fragment: {report['l1_negation']}")
    print(f"  in L2 fragment (disjunction/existential, no eq/xor/biconditional/multivar): "
          f"{report['l2']} {dict(report['l2_labels'].most_common())}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LLM-free L2 recon over ProntoQA-OOD and FOLIO.")
    parser.add_argument("--prontoqa-only", action="store_true")
    parser.add_argument("--folio-only", action="store_true")
    args = parser.parse_args(argv)

    if not args.folio_only:
        _print_prontoqa(_prontoqa_report(_download_files()))
    if not args.prontoqa_only:
        _print_folio(_folio_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
