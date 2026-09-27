"""Drive LINC on the Ankyra sample rows with the Ankyra provider.

Runs inside the LINC virtualenv, with this repository on ``PYTHONPATH``::

    PROVER9=/path/to/prover9 \\
    PYTHONPATH=/path/to/ankyra \\
      /tmp/opencode/cmp/linc-venv/bin/python -m comparison.run_linc \\
      --repo /tmp/opencode/cmp/linc --collection folio_tier_a --nshot 1

Only LINC's own task pipeline is used: its prompt (with the official few-shot
examples), its ``postprocess_generation`` and its NLTK/Prover9 ``evaluate``. The
dataset is replaced by the converted Ankyra rows (``--own-data`` keeps LINC's
own test split instead); the model call goes through the shared provider shim.
``torch``/``accelerate`` are not needed because the OpenAI path bypasses LINC's
Hugging Face generation loop.

``--n-samples N --temperature T`` reproduce LINC's reported protocol (8-shot,
10 samples, T=0.8, majority vote); the default is a single greedy sample.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from collections import Counter
from pathlib import Path

from comparison import adapt, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
_LINC_MODES = {"FOLIO": "folio", "ProofWriter": "proofwriter"}
_ERROR = "Error"
_POSTPROCESS_LOCK = threading.Lock()


def _setup(repo: Path, prover9: str | None) -> str:
    sys.path.insert(0, str(repo))
    os.chdir(repo)
    os.environ["PATH"] = os.path.dirname(sys.executable) + os.pathsep + os.environ["PATH"]
    if prover9:
        os.environ["PROVER9"] = prover9
    return patch.install()


def run(repo: Path, collection: str | None, dataset: str | None, nshot: int, temperature: float,
        n_samples: int, limit: int | None, own_data: bool, prover9: str | None,
        out_path: Path, jobs: int = 1, stride: int = 1) -> None:
    model = _setup(repo, prover9)
    import openai  # noqa: PLC0415
    from eval.tasks import get_task  # noqa: PLC0415

    if own_data:
        if dataset not in _LINC_MODES:
            raise SystemExit("--own-data requires --dataset FOLIO or ProofWriter")
        mode = _LINC_MODES[dataset]
        label = f"own_{mode}"
    else:
        dataset, records = adapt.to_linc(collection)
        mode = _LINC_MODES[dataset]
        label = collection

    task_name = f"{mode}-neurosymbolic-{nshot}shot"
    print(f"task={task_name} model={model} n_samples={n_samples} T={temperature} own_data={own_data}")
    task = get_task(task_name)

    if own_data:
        indices = list(range(0, len(task.get_dataset()), stride))
        if limit:
            indices = indices[:limit]
        test = task.get_dataset().select(indices)
        ids = [str(i) for i in indices]
    else:
        import datasets  # noqa: PLC0415

        test = datasets.Dataset.from_list(records)
        if limit:
            test = test.select(range(min(limit, len(test))))
        ids = [test[i]["id"] for i in range(len(test))]
        task._test = test

    predictions = []
    total_cost = 0.0
    if len(test):
        task.get_prompt(test[0])  # warm the few-shot prompt cache before threads

    def process(idx: int) -> tuple[dict, float]:
        doc = test[idx]
        prompt = task.get_prompt(doc)
        cost = 0.0
        samples = []
        for _ in range(n_samples):
            response = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=1024,
                top_p=1.0,
                stop=task.stop_words,
            )
            cost += float((response.get("usage") or {}).get("cost") or 0.0)
            generation = response["choices"][0]["message"]["content"]
            try:
                with _POSTPROCESS_LOCK:
                    samples.append(task.postprocess_generation(generation, idx, completion_only=True))
            except Exception as exc:  # noqa: BLE001
                samples.append(f"{_ERROR}:{type(exc).__name__}")
        good = [s for s in samples if s != _ERROR and not s.startswith(f"{_ERROR}:")]
        pred = Counter(good).most_common(1)[0][0] if good else _ERROR
        reference = task.get_reference(doc)
        rec = {"id": ids[idx], "reference": reference, "prediction": pred, "samples": samples}
        print(f"  [{idx + 1}/{len(test)}] {ids[idx]}: {pred} (ref {reference}) good={len(good)}/{n_samples}")
        return rec, cost

    if jobs > 1:
        from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415

        with ThreadPoolExecutor(max_workers=jobs) as pool:
            results = list(pool.map(process, range(len(test))))
    else:
        results = [process(idx) for idx in range(len(test))]
    predictions = [rec for rec, _ in results]
    total_cost = sum(c for _, c in results)

    gens = [[p["prediction"]] for p in predictions]
    refs = [p["reference"] for p in predictions]
    metrics = task.process_results(gens, refs)
    metrics["cost_usd"] = round(total_cost, 4)
    print("metrics:", metrics)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"label": label, "task": task_name, "nshot": nshot,
                    "n_samples": n_samples, "temperature": temperature,
                    "metrics": metrics, "predictions": predictions},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"wrote {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--collection", choices=sorted(adapt.COLLECTIONS))
    ap.add_argument("--dataset", choices=sorted(_LINC_MODES))
    ap.add_argument("--own-data", action="store_true",
                    help="run on LINC's own test split (requires --dataset)")
    ap.add_argument("--nshot", type=int, default=1)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--n-samples", type=int, default=1)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--stride", type=int, default=1, help="own-data: take every k-th test item")
    ap.add_argument("--prover9", default=os.environ.get("PROVER9"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if not args.collection and not args.own_data:
        ap.error("--collection or --own-data is required")
    label = args.collection or f"own_{args.dataset.lower()}"
    out = Path(args.out) if args.out else (
        REPO_ROOT / "comparison" / "results" / f"linc_{label}.json"
    )
    run(Path(args.repo).resolve(), args.collection, args.dataset, args.nshot, args.temperature,
        args.n_samples, args.limit, args.own_data, args.prover9, out, args.jobs, args.stride)


if __name__ == "__main__":
    main()
