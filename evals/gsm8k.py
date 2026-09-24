"""GSM8K eval adapter for the L4 gate (``docs/l4_plan.md`` §13.2).

Three modes:

* describe (default): print the composition of a committed sample (LLM-free);
* ``--gold FILE``: evaluate hand-encoded real problems through the engine (LLM-free);
* ``--live``: run the Phase-0 numeric extraction on a committed sample and solve each
  problem (invokes the LLM; costs tokens, so it is an explicit, budgeted run).

Scoring maps the solver decision to the dataset's reference number. The only soundness
failure is a ``grounded_mismatch`` — the target was determined but differs from the
reference (a modelling error, never an arithmetic one, since arithmetic is exact);
``underdetermined``/``inconsistent``/``out_of_fragment``/``insufficient`` are honest
abstentions. The gate is 0 ``grounded_mismatch``.

Usage::

    uv run python -m evals.gsm8k --sample dev
    uv run python -m evals.gsm8k --gold evals/data/gsm8k_gold.jsonl
    uv run python -m evals.gsm8k --sample dev --live --limit 4
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from ankyra.build.extract_numeric import extract_numeric_game, extract_numeric_query
from ankyra.build.numeric import NumericBuildError, build_numeric_game, build_numeric_query
from ankyra.config.settings import get_setting, setting_overrides
from ankyra.engine.numeric import NumericError, NumericGame, NumericQuery, solve
from evals.skills import skill_block

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
# The GSM8K skill (language + task specifics) is auto-loaded and injected into the
# Phase 0 prompts only for this harness (docs/task.md §0.6, `ANKYRA_LANGUAGE_SPEC`).
COLLECTION = "gsm8k"


def sample_path(sample: str) -> Path:
    return DATA / f"gsm8k_{sample}.jsonl"


def gold_path() -> Path:
    return DATA / "gsm8k_gold.jsonl"


def notes_path() -> Path:
    return DATA / "gsm8k_notes.jsonl"


def load_notes(path: Path | None = None) -> dict[str, str]:
    """Committed annotations of rows whose reference is unsound or ambiguous, by id."""
    path = path or notes_path()
    if not Path(path).is_file():
        return {}
    return {row["id"]: row["kind"] for row in load_sample(Path(path))}


def load_sample(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _shape(status: str, value, reference: str) -> str:
    if status == "determined":
        return "correct" if str(value) == str(reference) else "grounded_mismatch"
    return status


def _score(record: dict, decision, reference: str, *, detail: str | None = None) -> dict:
    result = {
        "id": record["id"],
        "sample_id": record.get("sample_id", record["id"]),
        "expected": str(reference),
        "actual": str(decision.value) if decision.value is not None else None,
        "status": decision.status,
        "shape": _shape(decision.status, decision.value, reference),
    }
    if detail:
        result["detail"] = detail
    return result


def _failed(record: dict, reference: str, shape: str, detail: str) -> dict:
    return {
        "id": record["id"],
        "sample_id": record.get("sample_id", record["id"]),
        "expected": str(reference),
        "actual": None,
        "status": shape,
        "shape": shape,
        "detail": detail,
    }


def run_gold(path: Path, *, limit: int = 0) -> list[dict]:
    """Evaluate the hand-encoded gold problems (LLM-free)."""
    records = load_sample(path)
    if limit:
        records = records[:limit]
    results = []
    for record in records:
        try:
            game = NumericGame.model_validate(record["game"])
            query = NumericQuery.model_validate(record["query"])
            decision = solve(game, query)
        except (NumericError, ValueError, TypeError) as exc:
            results.append(_failed(record, record["reference"], "build_error", f"{type(exc).__name__}: {exc}"))
            continue
        results.append(_score(record, decision, record["reference"]))
    return results


def run_live(records: list[dict], *, limit: int = 0, dump: Path | None = None) -> list[dict]:
    """Extract the numeric model and solve each problem (paid, budgeted)."""
    from ankyra.llm.client import create_chat_llm

    if limit:
        records = records[:limit]
    llm = create_chat_llm(role="extract")
    repairs = int(get_setting("ARITH_REPAIRS", 2) or 0)
    results: list[dict] = []
    dumps: list[dict] = []
    for record in records:
        text = record["question"]
        entry = {"id": record["id"], "expected": record["reference"]}
        try:
            def _validate_game(structure, _text=text):
                try:
                    build_numeric_game(structure, source_text=_text)
                except NumericBuildError as exc:
                    return f"the encoding failed to build: {exc}"
                return None

            game = build_numeric_game(
                extract_numeric_game(llm, text=text, validate=_validate_game, repairs=repairs),
                source_text=text,
            )

            def _validate_query(structure, _game=game):
                try:
                    build_numeric_query(structure, game=_game)
                except NumericBuildError as exc:
                    return f"the encoding failed to build: {exc}"
                return None

            structure = extract_numeric_query(
                llm, question=text, game=game, source_text=text,
                validate=_validate_query, repairs=repairs,
            )
            query = build_numeric_query(structure, game=game)
            decision = solve(game, query)
        except NumericBuildError as exc:
            results.append(_failed(record, record["reference"], "build_error", f"NumericBuildError: {exc}"))
            dumps.append({**entry, "shape": "build_error", "detail": str(exc)[:500]})
            continue
        except (NumericError, ValueError, TypeError) as exc:
            results.append(_failed(record, record["reference"], "build_error", f"{type(exc).__name__}: {exc}"))
            dumps.append({**entry, "shape": "build_error", "detail": str(exc)[:500]})
            continue
        scored = _score(record, decision, record["reference"])
        results.append(scored)
        dumps.append({**entry, "shape": scored["shape"], "status": decision.status, "game": game.model_dump(mode="json"), "query": query.model_dump(mode="json")})
    if dump is not None:
        dump.parent.mkdir(parents=True, exist_ok=True)
        with Path(dump).open("w", encoding="utf-8") as handle:
            for item in dumps:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    return results


def describe(records: list[dict]) -> None:
    lengths = Counter("short" if len(r["question"]) < 200 else "long" for r in records)
    print(f"sample: {len(records)} problems")
    print(f"  length: {dict(lengths)}")
    print(f"  ids: {', '.join(r['id'] for r in records[:6])}{' …' if len(records) > 6 else ''}")


def report(results: list[dict], *, title: str) -> bool:
    annotations = load_notes()
    for result in results:
        if result["shape"] == "grounded_mismatch" and result["id"] in annotations:
            result["annotated"] = annotations[result["id"]]
            result["shape"] = annotations[result["id"]]
    shapes = Counter(result["shape"] for result in results)
    correct = shapes.get("correct", 0)
    grounded = shapes.get("grounded_mismatch", 0)
    print()
    print(f"{title}: {correct}/{len(results)} correct, {grounded} grounded_mismatch")
    print(f"  shapes: {dict(shapes.most_common())}")
    for result in results:
        if "annotated" in result:
            print(f"    ANNOTATED ({result['annotated']}) {result['id']} expected={result['expected']} actual={result['actual']}")
        elif result["shape"] == "grounded_mismatch":
            print(
                f"    GROUNDED {result['id']:22} expected={result['expected']} "
                f"actual={result['actual']}"
            )
    return grounded == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GSM8K L4 adapter.")
    parser.add_argument("--sample", default="dev", choices=["dev", "eval"])
    parser.add_argument("--gold", default="", help="Hand-encoded gold JSONL (LLM-free).")
    parser.add_argument("--live", action="store_true", help="Run the paid extraction path.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--ids", default="")
    parser.add_argument("--dump", default="", help="Write extracted models for triage.")
    args = parser.parse_args(argv)

    if args.gold:
        path = Path(args.gold)
        return 0 if report(run_gold(path, limit=args.limit), title="gold") else 1

    sample = load_sample(sample_path(args.sample))
    wanted = {item.strip() for item in args.ids.split(",") if item.strip()}
    if wanted:
        sample = [record for record in sample if record["id"] in wanted]

    if not args.live:
        describe(sample)
        return 0

    if not sample:
        print("empty sample")
        return 1
    dump = Path(args.dump) if args.dump else None
    with setting_overrides(LANGUAGE_SPEC=skill_block(COLLECTION)):
        results = run_live(sample, limit=args.limit, dump=dump)
    return 0 if report(results, title=f"live {args.sample}") else 1


if __name__ == "__main__":
    raise SystemExit(main())
