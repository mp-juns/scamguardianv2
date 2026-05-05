"""5개 합성 샘플 batch 실행 + WER aggregation.

실행:
    python experiments/v4_whisper/batch_eval.py
    python experiments/v4_whisper/batch_eval.py --speakerphone   # _spk.wav 도 포함

각 샘플마다 5초 chunk Whisper 호출, WER 계산, 종합 results.md 작성.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from experiments.v4_whisper.chunker import stream_transcribe  # noqa: E402
from experiments.v4_whisper.run_eval import _normalize, _wer  # noqa: E402

HERE = Path(__file__).parent
AUDIO_DIR = HERE / "audio"
DATA = HERE / "synthetic_samples.jsonl"
RESULTS_MD = HERE / "results.md"
WER_THRESHOLD = 0.20


def _load_samples(include_speakerphone: bool) -> list[dict]:
    items = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines() if line.strip()]
    out: list[dict] = []
    for it in items:
        sid = it["id"]
        mp3 = AUDIO_DIR / f"{sid}.mp3"
        if mp3.exists():
            out.append({**it, "path": mp3, "variant": "clean"})
        if include_speakerphone:
            spk = AUDIO_DIR / f"{sid}_spk.wav"
            if spk.exists():
                out.append({**it, "path": spk, "variant": "speakerphone"})
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunk", type=int, default=5)
    parser.add_argument("--speakerphone", action="store_true")
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY 미설정 (.env 확인)", file=sys.stderr)
        return 2

    samples = _load_samples(include_speakerphone=args.speakerphone)
    if not samples:
        print(f"audio/ 디렉토리에 합성 샘플이 없습니다. 먼저: python experiments/v4_whisper/generate_synthetic.py", file=sys.stderr)
        return 2

    print(f"총 {len(samples)}개 샘플 (chunk={args.chunk}s)\n")
    rows: list[dict] = []
    t0 = time.time()
    for s in samples:
        print(f"━━━ {s['id']} ({s['variant']}) — {s['scenario']}")
        print(f"    voice: {s['voice']}")
        print(f"    text:  {s['text']}")
        ts0 = time.time()
        transcript = stream_transcribe(
            s["path"], chunk_sec=args.chunk, language="ko",
            on_chunk=lambda c: print(f"      [{c.start_sec:>4.1f}-{c.end_sec:>4.1f}s] ({c.latency_ms:>4d}ms) {c.text}{' [ERR ' + (c.error or '') + ']' if c.error else ''}"),
        )
        elapsed = time.time() - ts0

        wer = _wer(_normalize(s["text"]), _normalize(transcript.text))
        verdict = "PASS ✅" if wer <= WER_THRESHOLD else "FAIL ❌"
        avg_latency = transcript.total_latency_ms / max(1, len(transcript.chunks))
        print(f"    → hyp:  {transcript.text}")
        print(f"    WER: {wer:.3f} ({verdict}) | {len(transcript.chunks)} chunks, avg {avg_latency:.0f}ms / chunk\n")

        rows.append({
            "id": s["id"],
            "variant": s["variant"],
            "scenario": s["scenario"],
            "voice": s["voice"],
            "ref": s["text"],
            "hyp": transcript.text,
            "wer": wer,
            "verdict": verdict,
            "chunks": len(transcript.chunks),
            "avg_latency_ms": int(avg_latency),
            "elapsed_sec": elapsed,
        })

    # 종합 통계
    wers = [r["wer"] for r in rows]
    mean_wer = sum(wers) / len(wers)
    n_pass = sum(1 for r in rows if r["wer"] <= WER_THRESHOLD)
    avg_latency_all = sum(r["avg_latency_ms"] for r in rows) / len(rows)
    total_elapsed = time.time() - t0

    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"전체 {len(rows)}개 — mean WER: {mean_wer:.3f} | PASS: {n_pass}/{len(rows)} | avg chunk latency: {avg_latency_all:.0f}ms")
    print(f"총 소요 {total_elapsed:.1f}s")

    # results.md 작성
    lines: list[str] = []
    lines.append("# v4 exp2 — Whisper API 5초 chunk 한국어 정확도 측정\n")
    lines.append(f"- 모델: OpenAI Whisper API (`whisper-1`)")
    lines.append(f"- chunk: {args.chunk}s")
    lines.append(f"- 샘플: {len(rows)} (TTS 합성, edge-tts 한국어 3개 voice)")
    lines.append(f"- 평균 WER: **{mean_wer:.3f}** (임계 {WER_THRESHOLD:.2f} → {'PASS ✅' if mean_wer <= WER_THRESHOLD else 'FAIL ❌'})")
    lines.append(f"- PASS: {n_pass}/{len(rows)}")
    lines.append(f"- chunk 평균 latency: {avg_latency_all:.0f}ms")
    lines.append("")

    lines.append("## 샘플별 결과\n")
    lines.append("| ID | variant | 시나리오 | WER | 판정 | chunks | 평균 latency |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append(
            f"| `{r['id']}` | {r['variant']} | {r['scenario']} | "
            f"{r['wer']:.3f} | {r['verdict']} | {r['chunks']} | {r['avg_latency_ms']}ms |"
        )
    lines.append("")

    lines.append("## 발화별 reference vs hypothesis\n")
    for r in rows:
        lines.append(f"### `{r['id']}` ({r['variant']}) — {r['scenario']}")
        lines.append("")
        lines.append(f"- reference: {r['ref']}")
        lines.append(f"- hypothesis: {r['hyp']}")
        lines.append(f"- WER: **{r['wer']:.3f}** | {r['verdict']}")
        lines.append("")

    lines.append("## 비고\n")
    lines.append("- **WER 정의**: word error rate (Levenshtein 토큰 거리). 한국어는 공백 분리 토큰.")
    lines.append("- **임계 0.20**: 통화 환경 잡음 가정. 실전 마이크 녹음에서 합성 음성 대비 WER 1.5~2배 증가하는 게 일반적이라 클린 합성에서는 0.10~0.15 정도면 안전.")
    lines.append("- **다음 검증**: 실제 한국어 통화 녹음 (스피커폰 + 배경잡음) 으로 동일 측정 — `--speakerphone` 옵션이 1차 시뮬.")
    lines.append("")

    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {RESULTS_MD.relative_to(ROOT)}")

    return 0 if mean_wer <= WER_THRESHOLD else 1


if __name__ == "__main__":
    raise SystemExit(main())
