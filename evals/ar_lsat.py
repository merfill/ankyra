"""AR-LSAT eval adapter for the L3 gate (``docs/l3_plan.md`` §13.2).

Three modes:

* describe (default): print the composition of a committed sample (LLM-free);
* ``--gold FILE``: evaluate hand-encoded real games through the engine (LLM-free);
* ``--live``: run the Phase-0 CSP extraction on a committed sample and decide each
  question (invokes the LLM; costs tokens, so it is an explicit, budgeted run).

Scoring maps the solver decision to the dataset's answer option. The only soundness
failure is a ``grounded_mismatch`` — a unique option verified but different from the
label; ``ambiguous``/``no_option``/``budget``/``build_error`` are honest abstentions.
The gate is 0 ``grounded_mismatch``.

Usage::

    uv run python -m evals.ar_lsat --sample dev
    uv run python -m evals.ar_lsat --sample eval --gold evals/data/ar_lsat_gold.jsonl
    uv run python -m evals.ar_lsat --sample dev --live --limit 4
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from ankyra.build.csp import CspBuildError, CspFragmentError, build_csp_game, build_csp_question
from ankyra.build.extract_csp import extract_csp_game, extract_csp_question
from ankyra.config.settings import get_setting, setting_overrides
from ankyra.engine.csp import CspGame, CspQuestion, decide
from evals.skills import skill_block

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
# The AR-LSAT skill (language + task specifics) is auto-loaded and injected into the
# Phase 0 prompts only for this harness (docs/task.md §0.6, `ANKYRA_LANGUAGE_SPEC`).
# Not part of the engine.
COLLECTION = "ar_lsat"


def sample_path(sample: str) -> Path:
    return DATA / f"ar_lsat_{sample}.jsonl"


def load_sample(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _shape(decision_index: int | None, status: str, expected: int | None) -> str:
    if status == "decided":
        return "correct" if decision_index == expected else "grounded_mismatch"
    return {"ambiguous": "ambiguous", "unknown": "no_option"}.get(status, "budget")


def _duplicate_option(options) -> str | None:
    """A general mis-read guard: two options encoding identically cannot be right."""
    seen: dict[str, int] = {}
    for index, option in enumerate(options):
        payload = option.model_dump()
        payload.pop("quote", None)
        if not payload.get("constraints") and not payload.get("values"):
            continue
        key = json.dumps(payload, sort_keys=True)
        if key in seen:
            return f"options {seen[key]} and {index} encode identically; re-read each option."
        seen[key] = index
    return None


def score_decision(record: dict, decision, *, extra: dict | None = None) -> dict:
    shape = _shape(decision.index, decision.status, record["answer_index"])
    result = {
        "id": record["id"],
        "kind": record.get("question_kind", "gold"),
        "expected": record["answer_index"],
        "picked": decision.index,
        "status": decision.status,
        "shape": shape,
    }
    if extra:
        result.update(extra)
    return result


def run_gold(gold_path: Path, *, limit: int = 0) -> list[dict]:
    """Evaluate the hand-encoded gold games (LLM-free)."""
    records = load_sample(gold_path)
    if limit:
        records = records[:limit]
    results = []
    for record in records:
        try:
            game = CspGame.model_validate(record["game"])
            question = CspQuestion.model_validate(record["question"])
        except Exception as exc:  # malformed gold record: honest failure, not a guess
            results.append(
                {
                    "id": record.get("id", "?"),
                    "kind": "gold",
                    "expected": record.get("expected_index"),
                    "picked": None,
                    "status": "gold_error",
                    "shape": "build_error",
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        with setting_overrides(CSP=True):
            decision = decide(game, question)
        results.append(score_decision(record | {"answer_index": record.get("expected_index")}, decision))
    return results


def run_live(records: list[dict], *, limit: int = 0, dump: Path | None = None) -> list[dict]:
    """Extract the CSP encoding and decide each question (paid, budgeted).

    ``dump`` writes one JSON line per record with the extracted game/question and the
    decision, for offline triage.
    """
    from ankyra.llm.client import create_chat_llm

    if limit:
        records = records[:limit]
    llm = create_chat_llm(role="extract")
    game_cache: dict[str, CspGame] = {}
    results: list[dict] = []
    dumps: list[dict] = []
    for record in records:
        entry = {"id": record["id"], "expected": record["answer_index"], "kind": record["question_kind"]}
        try:
            game = game_cache.get(record["passage"])
            if game is None:
                game = build_csp_game(
                    extract_csp_game(llm, text=record["passage"]), source_text=record["passage"]
                )
                game_cache[record["passage"]] = game
            stem = record["question"].strip().rstrip(".")
            options = "\n".join(
                f"{chr(65 + index)}. {option}" for index, option in enumerate(record["options"])
            )
            question_text = f"{stem}\n{options}"

            def _validate(structure, _game=game):
                duplicate = _duplicate_option(structure.options)
                if duplicate is not None:
                    return duplicate
                try:
                    probe = build_csp_question(structure, game=_game)
                except CspFragmentError:
                    return None  # out of fragment; re-encoding will not help
                except CspBuildError as exc:
                    return f"the encoding failed to build: {exc}"
                with setting_overrides(CSP=True):
                    outcome = decide(_game, probe)
                if outcome.status == "ambiguous":
                    return "your encoding made several options satisfiable at once."
                if outcome.status == "unknown":
                    return "your encoding made no option satisfiable."
                return None

            structure = extract_csp_question(
                llm,
                question=question_text,
                game=game,
                source_text=record["passage"],
                validate=_validate,
                repairs=int(get_setting("CSP_REPAIRS", 1) or 0),
            )
            question = build_csp_question(structure, game=game)
            with setting_overrides(CSP=True):
                decision = decide(game, question)
        except CspFragmentError as exc:
            results.append(
                {
                    "id": record["id"],
                    "kind": record["question_kind"],
                    "expected": record["answer_index"],
                    "picked": None,
                    "status": "out_of_fragment",
                    "shape": "out_of_fragment",
                    "detail": f"{type(exc).__name__}: {str(exc)[:200]}",
                }
            )
            dumps.append({**entry, "shape": "out_of_fragment", "detail": str(exc)[:500]})
            continue
        except (CspBuildError, ValueError, TypeError) as exc:
            results.append(
                {
                    "id": record["id"],
                    "kind": record["question_kind"],
                    "expected": record["answer_index"],
                    "picked": None,
                    "status": "build_error",
                    "shape": "build_error",
                    "detail": f"{type(exc).__name__}: {str(exc)[:200]}",
                }
            )
            dumps.append({**entry, "shape": "build_error", "detail": str(exc)[:500]})
            continue
        scored = score_decision(record, decision)
        results.append(scored)
        dumps.append(
            {
                **entry,
                "shape": scored["shape"],
                "picked": decision.index,
                "verified": decision.verified,
                "game": game.model_dump(),
                "question": question.model_dump(),
            }
        )
    if dump is not None:
        dump.parent.mkdir(parents=True, exist_ok=True)
        with Path(dump).open("w", encoding="utf-8") as handle:
            for item in dumps:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    return results


def describe(records: list[dict]) -> None:
    print(f"sample: {len(records)} questions")
    print(f"  kinds:       {dict(Counter(r['question_kind'] for r in records).most_common())}")
    print(f"  answers:     {dict(sorted(Counter(r['answer_letter'] for r in records).items()))}")
    print(f"  game types:  {dict(Counter(r['game_type'] for r in records).most_common())}")
    print(f"  lengths:     {dict(Counter(r['length'] for r in records).most_common())}")
    print(f"  assumptions: {dict(Counter(r['has_assumption'] for r in records))}")
    print(f"  families:    {sorted({r['fatherId'] for r in records})}")


def report(results: list[dict], *, title: str) -> bool:
    shapes = Counter(result["shape"] for result in results)
    by_kind: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for result in results:
        bucket = by_kind[result["kind"]]
        bucket[1] += 1
        bucket[0] += int(result["shape"] == "correct")
    correct = shapes.get("correct", 0)
    grounded = shapes.get("grounded_mismatch", 0)
    print()
    print(f"{title}: {correct}/{len(results)} correct, {grounded} grounded_mismatch")
    print(f"  shapes: {dict(shapes.most_common())}")
    for kind in sorted(by_kind):
        hit, total = by_kind[kind]
        print(f"    {kind:16} {hit}/{total}")
    for result in results:
        if result["shape"] == "grounded_mismatch":
            print(
                f"    GROUNDED {result['id']:24} expected={result['expected']} "
                f"picked={result['picked']} kind={result['kind']}"
            )
    return grounded == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AR-LSAT L3 adapter.")
    parser.add_argument("--sample", default="dev", choices=["dev", "eval"])
    parser.add_argument("--gold", default="", help="Hand-encoded gold JSONL (LLM-free).")
    parser.add_argument("--live", action="store_true", help="Run the paid extraction path.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--ids", default="")
    parser.add_argument("--dump", default="", help="Write extracted games/questions for triage.")
    args = parser.parse_args(argv)

    if args.gold:
        return 0 if report(run_gold(Path(args.gold), limit=args.limit), title="gold") else 1

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
    language_spec = skill_block(COLLECTION)
    with setting_overrides(CSP=True, LANGUAGE_SPEC=language_spec):
        results = run_live(sample, limit=args.limit, dump=dump)
    return 0 if report(results, title=f"live {args.sample}") else 1


if __name__ == "__main__":
    raise SystemExit(main())
