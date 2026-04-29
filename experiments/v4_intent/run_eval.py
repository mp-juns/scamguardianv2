"""
Haiku 의도 분류기 평가 — synthetic_utterances.jsonl 32개에 대해 confusion matrix.

사용:
    python experiments/v4_intent/run_eval.py
    python experiments/v4_intent/run_eval.py --concurrency 4
    python experiments/v4_intent/run_eval.py --model claude-haiku-4-5-20251001

출력:
- stdout: per-class precision/recall/F1 + confusion matrix + 오분류 목록
- experiments/v4_intent/results.md: 위 내용 마크다운 저장
- experiments/v4_intent/raw_predictions.jsonl: 발화별 예측 + 원본 응답
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# api 키 로드 (.env)
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from experiments.v4_intent.classify_haiku import LABELS, classify  # noqa: E402


HERE = Path(__file__).parent
DATA = HERE / "synthetic_utterances.jsonl"
RAW_OUT = HERE / "raw_predictions.jsonl"
RESULTS_MD = HERE / "results.md"


def _load_dataset() -> list[dict[str, str]]:
    samples: list[dict[str, str]] = []
    for line in DATA.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        samples.append(json.loads(line))
    return samples


def _eval_sample(sample: dict[str, str], model: str | None) -> dict[str, Any]:
    t0 = time.time()
    try:
        pred, raw = classify(sample["text"], model=model)
        err = None
    except Exception as exc:  # noqa: BLE001
        pred = "NORMAL"
        raw = ""
        err = f"{type(exc).__name__}: {exc}"
    return {
        "id": sample["id"],
        "label": sample["label"],
        "text": sample["text"],
        "pred": pred,
        "raw": raw,
        "latency_ms": int((time.time() - t0) * 1000),
        "error": err,
    }


def _confusion(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    cm: dict[str, dict[str, int]] = {gt: {p: 0 for p in LABELS} for gt in LABELS}
    for r in records:
        cm[r["label"]][r["pred"]] += 1
    return cm


def _per_class_metrics(cm: dict[str, dict[str, int]]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for cls in LABELS:
        tp = cm[cls][cls]
        fn = sum(cm[cls][p] for p in LABELS if p != cls)
        fp = sum(cm[gt][cls] for gt in LABELS if gt != cls)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        out[cls] = {"precision": prec, "recall": rec, "f1": f1, "support": tp + fn}
    return out


def _macro_f1(metrics: dict[str, dict[str, float]]) -> float:
    return sum(m["f1"] for m in metrics.values()) / len(metrics)


def _accuracy(records: list[dict[str, Any]]) -> float:
    if not records:
        return 0.0
    return sum(1 for r in records if r["pred"] == r["label"]) / len(records)


def _format_results(
    records: list[dict[str, Any]],
    cm: dict[str, dict[str, int]],
    metrics: dict[str, dict[str, float]],
    accuracy: float,
    macro_f1: float,
    avg_latency: float,
    model: str,
    threshold: float,
) -> str:
    lines: list[str] = []
    lines.append("# v4 exp1 — Haiku 의도 분류 평가\n")
    lines.append(f"- 모델: `{model}`")
    lines.append(f"- 샘플 수: {len(records)}")
    lines.append(f"- 평균 latency: {avg_latency:.0f}ms")
    lines.append(f"- 정확도: **{accuracy:.3f}**")
    lines.append(f"- macro F1: **{macro_f1:.3f}** (임계 {threshold:.2f} → {'PASS ✅' if macro_f1 >= threshold else 'FAIL ❌'})")
    lines.append("")

    lines.append("## per-class metrics\n")
    lines.append("| label | precision | recall | F1 | support |")
    lines.append("|---|---|---|---|---|")
    for cls in LABELS:
        m = metrics[cls]
        lines.append(
            f"| {cls} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} | {int(m['support'])} |"
        )
    lines.append("")

    lines.append("## confusion matrix (행=정답, 열=예측)\n")
    header = "| GT \\ pred | " + " | ".join(LABELS) + " |"
    lines.append(header)
    lines.append("|---|" + "---|" * len(LABELS))
    for gt in LABELS:
        row = f"| {gt} | " + " | ".join(str(cm[gt][p]) for p in LABELS) + " |"
        lines.append(row)
    lines.append("")

    misses = [r for r in records if r["pred"] != r["label"]]
    if misses:
        lines.append(f"## 오분류 ({len(misses)}개)\n")
        for r in misses:
            err = f" — error: {r['error']}" if r.get("error") else ""
            lines.append(f"- `{r['id']}` GT={r['label']} pred={r['pred']} | {r['text']}{err}")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--model", default=None)
    parser.add_argument("--threshold", type=float, default=0.85)
    args = parser.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY 가 설정되지 않았습니다 (.env 확인).", file=sys.stderr)
        return 2

    samples = _load_dataset()
    print(f"loaded {len(samples)} samples")
    model = args.model or os.getenv("ANTHROPIC_HAIKU_MODEL", "claude-haiku-4-5-20251001")
    print(f"model: {model}, concurrency: {args.concurrency}")

    records: list[dict[str, Any]] = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(_eval_sample, s, args.model) for s in samples]
        for fut in as_completed(futures):
            r = fut.result()
            records.append(r)
            mark = "✓" if r["pred"] == r["label"] else "✗"
            err = f" [ERR {r['error']}]" if r.get("error") else ""
            print(f"  {mark} {r['id']:>4s} GT={r['label']:<14s} pred={r['pred']:<14s} ({r['latency_ms']}ms){err}")

    elapsed = time.time() - t0
    records.sort(key=lambda r: r["id"])

    cm = _confusion(records)
    metrics = _per_class_metrics(cm)
    acc = _accuracy(records)
    macro = _macro_f1(metrics)
    avg_latency = sum(r["latency_ms"] for r in records) / len(records)

    print()
    print(f"completed in {elapsed:.1f}s")
    print(f"accuracy: {acc:.3f}, macro F1: {macro:.3f}, avg latency: {avg_latency:.0f}ms")

    RAW_OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        encoding="utf-8",
    )
    md = _format_results(records, cm, metrics, acc, macro, avg_latency, model, args.threshold)
    RESULTS_MD.write_text(md, encoding="utf-8")
    print(f"\nwrote {RAW_OUT.relative_to(ROOT)}")
    print(f"wrote {RESULTS_MD.relative_to(ROOT)}")
    return 0 if macro >= args.threshold else 1


if __name__ == "__main__":
    raise SystemExit(main())
