"""Drive Logic-LM on the Ankyra sample rows with the Ankyra provider.

Runs inside the Logic-LM virtualenv, with this repository on ``PYTHONPATH``::

    PYTHONPATH=/path/to/ankyra \\
      /tmp/opencode/cmp/llm-venv/bin/python -m comparison.run_logicllm \\
      --repo /tmp/opencode/cmp/logicllm --action prepare

Actions:
    prepare  write the converted Ankyra rows into the Logic-LM ``data/`` tree
    generate call the model to produce logic programs (paid)
    infer    execute the programs with the symbolic solver
    evaluate score the inference output (Logic-LM's own evaluator)
    all      generate -> infer -> evaluate
    offline  infer + evaluate a pre-existing program file (solver smoke test)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import comparison.adapt as adapt
from comparison import patch

MODEL_ALIAS = os.environ.get("COMPARISON_MODEL_ALIAS", "deepseek-v4-flash")


def _framework(repo: Path):
    """Enter the Logic-LM tree, install the provider shim, return real model id."""
    sys.path.insert(0, str(repo / "models"))
    sys.path.insert(0, str(repo))
    os.chdir(repo)
    # The z3 solver runs generated code through ``python`` from PATH; make sure
    # that resolves to this virtualenv, not the system interpreter.
    os.environ["PATH"] = os.path.dirname(sys.executable) + os.pathsep + os.environ["PATH"]
    real = patch.install()
    import utils  # noqa: PLC0415

    # The Ankyra provider is chat-only; Logic-LM's name check is bypassed here.
    utils.OpenAIModel.generate = lambda self, s, temperature=0.0: self.chat_generate(s, temperature)
    return real


def _program_args(dataset: str, split: str):
    from argparse import Namespace  # noqa: PLC0415

    return Namespace(
        data_path="./data",
        dataset_name=dataset,
        split=split,
        save_path="./outputs/logic_programs",
        api_key=os.environ.get("ANKYRA_API_KEY", "unused"),
        model_name=MODEL_ALIAS,
        stop_words="------",
        max_new_tokens=1024,
    )


def _infer_args(dataset: str, split: str, model: str, backup: str, result_dir: str):
    from argparse import Namespace  # noqa: PLC0415

    return Namespace(
        dataset_name=dataset,
        split=split,
        model_name=model,
        save_path=result_dir,
        backup_strategy=backup,
        backup_LLM_result_path="",
    )


def action_prepare(repo: Path) -> None:
    for name in adapt.COLLECTIONS:
        dataset, split, records = adapt.to_logicllm(name)
        dest = repo / "data" / dataset
        dest.mkdir(parents=True, exist_ok=True)
        (dest / f"{split}.json").write_text(
            __import__("json").dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"prepared {dataset}/{split}.json ({len(records)})")


def action_generate(repo: Path, dataset: str, split: str) -> None:
    _framework(repo)
    from logic_program import LogicProgramGenerator  # noqa: PLC0415

    generator = LogicProgramGenerator(_program_args(dataset, split))
    generator.logic_program_generation()


def action_infer(repo: Path, dataset: str, split: str, model: str, backup: str, result_dir: str) -> None:
    _framework(repo)
    from logic_inference import LogicInferenceEngine  # noqa: PLC0415

    engine = LogicInferenceEngine(_infer_args(dataset, split, model, backup, result_dir))
    engine.inference_on_dataset()


def action_refine(repo: Path, dataset: str, split: str, model: str, rounds: int, backup: str) -> None:
    """Logic-LM self-refinement (supported by its own code for FOLIO and AR-LSAT)."""
    if dataset not in {"FOLIO", "AR-LSAT"}:
        raise ValueError(f"self-refinement is not implemented by Logic-LM for {dataset}")
    _framework(repo)
    from argparse import Namespace  # noqa: PLC0415

    from self_refinement import SelfRefinementEngine  # noqa: PLC0415

    for current_round in range(1, rounds + 1):
        args = Namespace(
            split=split,
            model_name=model,
            dataset_name=dataset,
            backup_strategy=backup,
            api_key=os.environ.get("ANKYRA_API_KEY", "unused"),
            stop_words="------",
            max_new_tokens=1024,
            backup_LLM_result_path="",
        )
        print(f"self-refinement round {current_round}/{rounds}")
        SelfRefinementEngine(args, current_round).single_round_self_refinement()

    refined = repo / "outputs" / "logic_programs" / f"self-refine-{rounds}_{dataset}_{split}_{model}.json"
    promoted = repo / "outputs" / "logic_programs" / f"{dataset}_{split}_{model}-refined.json"
    promoted.write_text(refined.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"promoted {refined.name} -> {promoted.name}")


def action_generate_multi(repo: Path, dataset: str, split: str, samples: int, temperature: float) -> None:
    """Best-of-N ablation: sample N logic programs per row (Logic-LM does not use this)."""
    _framework(repo)
    from logic_program import LogicProgramGenerator  # noqa: PLC0415

    gen = LogicProgramGenerator(_program_args(dataset, split))
    raw = gen.load_raw_dataset(split)
    outputs = []
    for example in raw:
        prompt = gen.prompt_creator[dataset](example)
        programs = [
            gen.openai_api.generate(prompt, temperature=temperature).strip()
            for _ in range(samples)
        ]
        outputs.append({
            "id": example["id"], "context": example["context"], "question": example["question"],
            "answer": example["answer"], "options": example["options"],
            "raw_logic_programs": programs,
        })
    dest = repo / "outputs" / "logic_programs" / f"{dataset}_{split}_{MODEL_ALIAS}-multi.json"
    dest.write_text(json.dumps(outputs, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {dest} ({len(outputs)} rows x {samples} samples)")


def action_infer_multi(repo: Path, dataset: str, split: str, backup: str, result_dir: str) -> None:
    """Majority vote over the N sampled programs, per row."""
    _framework(repo)
    from logic_inference import LogicInferenceEngine  # noqa: PLC0415
    from collections import Counter  # noqa: PLC0415

    engine = LogicInferenceEngine(_infer_args(dataset, split, f"{MODEL_ALIAS}-multi", backup, result_dir))
    programs = json.loads((
        repo / "outputs" / "logic_programs" / f"{dataset}_{split}_{MODEL_ALIAS}-multi.json"
    ).read_text(encoding="utf-8"))
    outputs = []
    for example in programs:
        answers = []
        for prog in example["raw_logic_programs"]:
            ans, flag, _ = engine.safe_execute_program(example["id"], prog.strip())
            if flag == "success":
                answers.append(ans)
        if answers:
            predicted, flag = Counter(answers).most_common(1)[0][0], "success"
        else:
            predicted, flag = None, "all-failed"
        outputs.append({
            "id": example["id"], "context": example["context"], "question": example["question"],
            "answer": example["answer"], "flag": flag, "predicted_answer": predicted,
        })
    dest = repo / "outputs" / "logic_inference" / f"{dataset}_{split}_{MODEL_ALIAS}-multi_backup-{backup}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(outputs, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {dest}")


def action_evaluate(repo: Path, dataset: str, split: str, model: str, backup: str) -> None:
    _framework(repo)
    import evaluation  # noqa: PLC0415

    result_file = repo / "outputs" / "logic_inference" / f"{dataset}_{split}_{model}_backup-{backup}.json"
    print(f"evaluating {result_file}")
    evaluation.full_evaluation(str(result_file))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--action", required=True, choices=["prepare", "generate", "infer", "evaluate", "all", "offline", "refine", "generate-multi", "infer-multi"])
    ap.add_argument("--collection", help="Ankyra collection key (see adapt.COLLECTIONS)")
    ap.add_argument("--dataset", help="override dataset name (offline)")
    ap.add_argument("--split", help="override split (offline)")
    ap.add_argument("--model", default=MODEL_ALIAS)
    ap.add_argument("--backup", default="random", choices=["random", "LLM"])
    ap.add_argument("--result-dir", default="./outputs/logic_inference")
    ap.add_argument("--rounds", type=int, default=2, help="self-refinement rounds")
    ap.add_argument("--samples", type=int, default=5, help="best-of-N ablation sample count")
    ap.add_argument("--multi-temperature", type=float, default=0.8)
    args = ap.parse_args()
    repo = Path(args.repo).resolve()

    if args.action == "prepare":
        action_prepare(repo)
        return

    if args.collection:
        dataset, split, _ = adapt.to_logicllm(args.collection)
    else:
        dataset, split = args.dataset, args.split
    if not dataset or not split:
        ap.error("--collection or both --dataset/--split are required")

    if args.action == "generate":
        action_generate(repo, dataset, split)
    elif args.action == "generate-multi":
        action_generate_multi(repo, dataset, split, args.samples, args.multi_temperature)
    elif args.action == "infer-multi":
        action_infer_multi(repo, dataset, split, args.backup, args.result_dir)
        action_evaluate(repo, dataset, split, f"{MODEL_ALIAS}-multi", args.backup)
    elif args.action == "refine":
        action_refine(repo, dataset, split, args.model, args.rounds, args.backup)
    elif args.action == "infer":
        action_infer(repo, dataset, split, args.model, args.backup, args.result_dir)
    elif args.action == "evaluate":
        action_evaluate(repo, dataset, split, args.model, args.backup)
    elif args.action == "offline":
        action_infer(repo, dataset, split, args.model, args.backup, args.result_dir)
        action_evaluate(repo, dataset, split, args.model, args.backup)
    elif args.action == "all":
        action_generate(repo, dataset, split)
        action_infer(repo, dataset, split, args.model, args.backup, args.result_dir)
        action_evaluate(repo, dataset, split, args.model, args.backup)


if __name__ == "__main__":
    main()
