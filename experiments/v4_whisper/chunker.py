"""
v4 실험 2 — 5초 chunk Whisper 인프라.

목적:
- 통화 중 사용자 발화 오디오를 5초 단위로 잘라 OpenAI Whisper API 에 보내고
  누적 transcript 를 만든다.
- v4.0 알파의 처리 핵심 — 통화 끝까지 기다리지 않고 chunk 단위로 즉시 분석.

지금 단계 (인프라만):
- 입력: 임의 길이 오디오 파일 (wav/m4a/mp3 등 ffmpeg 가 읽는 모든 포맷).
- 처리: ffmpeg 으로 5초 chunk 분할 → 16kHz mono PCM 변환 → Whisper API 순차 호출.
- 출력: chunk 별 (start_sec, end_sec, text, latency_ms) 리스트 + 누적 transcript.

다음 단계 (v4.0 본 구현, 별도 작업):
- WebSocket 으로 실시간 PCM 스트림 받기 (브라우저 AudioWorklet)
- chunk 누적 시점을 wall-clock 기준 5초마다로 변경 (지금은 파일 기반이라 의미 X)
- chunk 단위로 Haiku 의도 분류기 호출 → 임계 초과 시 경보 push
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

CHUNK_SEC_DEFAULT = 5
SAMPLE_RATE = 16000


@dataclass
class ChunkResult:
    index: int
    start_sec: float
    end_sec: float
    text: str
    latency_ms: int
    error: str | None = None


@dataclass
class StreamingTranscript:
    chunks: list[ChunkResult]

    @property
    def text(self) -> str:
        return " ".join(c.text for c in self.chunks if c.text).strip()

    @property
    def total_latency_ms(self) -> int:
        return sum(c.latency_ms for c in self.chunks)


def _require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg 이 설치되어 있지 않습니다 (apt install ffmpeg).")
    return path


def _audio_duration_sec(path: Path) -> float:
    """ffprobe 로 오디오 길이(초). 없으면 ffmpeg 에 의존."""
    probe = shutil.which("ffprobe")
    if probe:
        out = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(out.stdout.strip())
    # fallback: ffmpeg 으로 메타데이터 읽기
    out = subprocess.run(
        ["ffmpeg", "-i", str(path), "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    for line in out.stderr.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            hms = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = hms.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    raise RuntimeError("오디오 길이 추출 실패")


def split_to_chunks(
    audio_path: Path | str,
    chunk_sec: int = CHUNK_SEC_DEFAULT,
    out_dir: Path | None = None,
) -> list[Path]:
    """ffmpeg 로 16kHz mono wav chunk 들로 분할. 반환: chunk 파일 경로 리스트."""
    _require_ffmpeg()
    src = Path(audio_path)
    if not src.exists():
        raise FileNotFoundError(src)
    target_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="v4chunk_"))
    target_dir.mkdir(parents=True, exist_ok=True)
    pattern = target_dir / "chunk_%04d.wav"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-ar", str(SAMPLE_RATE),
        "-ac", "1",
        "-f", "segment",
        "-segment_time", str(chunk_sec),
        "-c:a", "pcm_s16le",
        str(pattern),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    chunks = sorted(target_dir.glob("chunk_*.wav"))
    if not chunks:
        raise RuntimeError("chunk 분할 결과 0개")
    return chunks


def _transcribe_one(chunk_path: Path, language: str = "ko") -> str:
    from openai import OpenAI
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 가 설정되지 않았습니다.")
    client = OpenAI(api_key=api_key)
    with chunk_path.open("rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language=language,
        )

    duration = _audio_duration_sec(chunk_path)
    if duration > 0:
        try:
            from platform_layer.cost import record_openai_whisper
            record_openai_whisper(duration)
        except Exception:
            pass

    return (response.text or "").strip()


def stream_transcribe(
    audio_path: Path | str,
    chunk_sec: int = CHUNK_SEC_DEFAULT,
    language: str = "ko",
    on_chunk: Callable[[ChunkResult], None] | None = None,
    keep_chunks: bool = False,
) -> StreamingTranscript:
    """
    파일 → 5초 chunk → Whisper API 순차 호출 → 누적 transcript.

    on_chunk(result) 가 있으면 chunk 마다 호출 (실시간 UI 업데이트 시뮬레이션).
    keep_chunks=True 면 임시 디렉토리 유지 (디버깅용).
    """
    chunks_paths = split_to_chunks(audio_path, chunk_sec=chunk_sec)
    tmp_dir = chunks_paths[0].parent
    results: list[ChunkResult] = []
    try:
        for i, p in enumerate(chunks_paths):
            t0 = time.time()
            err: str | None = None
            text = ""
            try:
                text = _transcribe_one(p, language=language)
            except Exception as exc:  # noqa: BLE001
                err = f"{type(exc).__name__}: {exc}"
            res = ChunkResult(
                index=i,
                start_sec=i * chunk_sec,
                end_sec=(i + 1) * chunk_sec,
                text=text,
                latency_ms=int((time.time() - t0) * 1000),
                error=err,
            )
            results.append(res)
            if on_chunk:
                on_chunk(res)
    finally:
        if not keep_chunks:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    return StreamingTranscript(chunks=results)


def iter_chunk_audio(audio_path: Path | str, chunk_sec: int = CHUNK_SEC_DEFAULT) -> Iterable[Path]:
    """generator 버전 — chunk 파일 경로 yield. 호출자가 파일 처리 후 unlink 책임."""
    chunks = split_to_chunks(audio_path, chunk_sec=chunk_sec)
    for p in chunks:
        yield p
