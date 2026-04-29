"""
v4 실험 2 — 5초 chunk Whisper 정확도 측정 러너.

사용:
    python experiments/v4_whisper/run_eval.py path/to/audio.wav
    python experiments/v4_whisper/run_eval.py audio.m4a --chunk 5 --reference reference.txt

동작:
- 입력 오디오 → 5초 chunk → Whisper API 순차 호출
- chunk 별 latency / text 출력
- reference.txt 가 있으면 WER 계산 (Levenshtein)
- 결과를 results.md 에 추가 append (파일별 섹션)

WER 임계: 20% 이하면 PASS (실전 통화 잡음 환경 기준 너그러운 임계).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from experiments.v4_whisper.chunker import (  # noqa: E402
    ChunkResult,
    StreamingTranscript,
    stream_transcribe,
)


HERE = Path(__file__).parent
RESULTS_MD = HERE / "results.md"


def _normalize(text: str) -> list[str]:
    """공백·구두점 제거 후 단어 토큰. 한국어는 공백 단위면 충분."""
    text = re.sub(r"[^\w\s가-힣]", " ", text)
    return [t for t in text.split() if t]


def _wer(reference: list[str], hypothesis: list[str]) -> float:
    """Levenshtein 기반 WER."""
    R, H = len(reference), len(hypothesis)
    if R == 0:
        return 0.0 if H == 0 else 1.0
    dp = [[0] * (H + 1) for _ in range(R + 1)]
    for i in range(R + 1):
        dp[i][0] = i
    for j in range(H + 1):
        dp[0][j] = j
    for i in range(1, R + 1):
        for j in range(1, H + 1):
            if reference[i - 1] == hypothesis[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[R][H] / R


def _on_chunk(c: ChunkResult) -> None:
    err = f" [ERR {c.error}]" if c.error else ""
    print(f"  chunk {c.index:>2d} [{c.start_sec:>5.1f}-{c.end_sec:>5.1f}s] ({c.latency_ms:>4d}ms): {c.text}{err}")


def _format_section(
    audio_path: Path,
    transcript: StreamingTranscript,
    reference_text: str | None,
    wer: float | None,
    chunk_sec: int,
) -> str:
    lines = [f"\n## {audio_path.name}\n"]
    lines.append(f"- chunk: {chunk_sec}s × {len(transcript.chunks)}개")
    lines.append(f"- 총 latency: {transcript.total_latency_ms / 1000:.1f}s (Whisper API 합)")
    avg = transcript.total_latency_ms / len(transcript.chunks) if transcript.chunks else 0
    lines.append(f"- chunk 평균 latency: {avg:.0f}ms")
    if wer is not None:
        verdict = "PASS ✅" if wer <= 0.20 else "FAIL ❌"
        lines.append(f"- WER: **{wer:.3f}** (임계 0.20 → {verdict})")
    lines.append("")
    lines.append("### chunk 별 transcript")
    lines.append("")
    for c in transcript.chunks:
        text = c.text.replace("|", "\\|")
        err = f" `[ERR {c.error}]`" if c.error else ""
        lines.append(f"- `{c.start_sec:>5.1f}–{c.end_sec:>5.1f}s` ({c.latency_ms}ms): {text}{err}")
    lines.append("")
    lines.append("### 누적 transcript")
    lines.append("")
    lines.append(f"```\n{transcript.text}\n```")
    if reference_text:
        lines.append("\n### reference\n")
        lines.append(f"```\n{reference_text.strip()}\n```")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("--chunk", type=int, default=5)
    parser.add_argument("--reference", type=Path, default=None, help="정답 transcript 텍스트 파일")
    parser.add_argument("--language", default="ko")
    parser.add_argument("--keep-chunks", action="store_true")
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY 가 설정되지 않았습니다 (.env 확인).", file=sys.stderr)
        return 2
    if not args.audio.exists():
        print(f"오디오 파일 없음: {args.audio}", file=sys.stderr)
        return 2

    print(f"audio: {args.audio} (chunk={args.chunk}s, language={args.language})")
    t0 = time.time()
    transcript = stream_transcribe(
        args.audio,
        chunk_sec=args.chunk,
        language=args.language,
        on_chunk=_on_chunk,
        keep_chunks=args.keep_chunks,
    )
    elapsed = time.time() - t0

    reference_text: str | None = None
    wer: float | None = None
    if args.reference:
        reference_text = args.reference.read_text(encoding="utf-8")
        wer = _wer(_normalize(reference_text), _normalize(transcript.text))

    print()
    print(f"completed in {elapsed:.1f}s")
    print(f"총 transcript: {transcript.text}")
    if wer is not None:
        print(f"WER: {wer:.3f}")

    section = _format_section(args.audio, transcript, reference_text, wer, args.chunk)
    if RESULTS_MD.exists():
        RESULTS_MD.write_text(RESULTS_MD.read_text(encoding="utf-8") + section, encoding="utf-8")
    else:
        header = "# v4 exp2 — 5초 chunk Whisper 결과\n"
        RESULTS_MD.write_text(header + section, encoding="utf-8")
    print(f"appended to {RESULTS_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
