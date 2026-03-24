"""
ScamGuardian v2 — STT 모듈
YouTube URL / 로컬 파일 / 텍스트 입력을 처리하여 텍스트를 반환한다.
"""

from __future__ import annotations

import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import whisper

_YOUTUBE_PATTERN = re.compile(
    r"https?://(www\.)?(youtube\.com|youtu\.be)/"
)

_whisper_model_cache: dict[str, whisper.Whisper] = {}


@dataclass
class TranscriptResult:
    text: str
    language: str = ""
    segments: list[dict] = field(default_factory=list)
    source_type: str = ""  # "youtube" | "file" | "text"


def _is_youtube_url(source: str) -> bool:
    return bool(_YOUTUBE_PATTERN.match(source.strip()))


def _is_file(source: str) -> bool:
    p = Path(source)
    return p.exists() and p.is_file()


def _download_youtube_audio(
    url: str,
    output_dir: str,
    debug: bool = False,
    logger: Callable[[str], None] | None = None,
) -> str:
    """yt-dlp로 YouTube 오디오를 추출하여 임시 wav 파일 경로를 반환한다."""
    import yt_dlp

    output_path = str(Path(output_dir) / "audio.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_path,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }
        ],
        "quiet": not debug,
        "no_warnings": not debug,
    }

    if logger:
        logger(f"[STT] YouTube 오디오 다운로드 시작: {url}")
    t0 = time.time()
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    if logger:
        logger(f"[STT] YouTube 오디오 다운로드 완료 ({time.time() - t0:.1f}s)")

    wav_path = str(Path(output_dir) / "audio.wav")
    if not Path(wav_path).exists():
        raise FileNotFoundError(f"YouTube 오디오 다운로드 실패: {url}")
    return wav_path


def _get_whisper_model(model_size: str) -> whisper.Whisper:
    if model_size not in _whisper_model_cache:
        t0 = time.time()
        _whisper_model_cache[model_size] = whisper.load_model(model_size)
        print(f"[STT] Whisper 모델 로드 완료: {model_size} ({time.time() - t0:.1f}s)")
    return _whisper_model_cache[model_size]


def transcribe(
    source: str,
    model_size: str = "medium",
    debug: bool = False,
    logger: Callable[[str], None] | None = None,
) -> TranscriptResult:
    """
    입력 소스를 텍스트로 변환한다.

    Args:
        source: YouTube URL, 로컬 파일 경로, 또는 텍스트
        model_size: Whisper 모델 크기 (tiny/base/small/medium/large)

    Returns:
        TranscriptResult 객체
    """
    # 1) 텍스트 입력
    if not _is_youtube_url(source) and not _is_file(source):
        return TranscriptResult(
            text=source.strip(),
            source_type="text",
        )

    # 2) YouTube URL
    if _is_youtube_url(source):
        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_path = _download_youtube_audio(
                source,
                tmp_dir,
                debug=debug,
                logger=logger,
            )
            if logger:
                logger(f"[STT] 오디오 파일 준비 완료: {audio_path}")
            model = _get_whisper_model(model_size)
            if logger:
                logger(f"[STT] Whisper 추론 시작 (model={model_size}, language=ko)")
            t0 = time.time()
            result = model.transcribe(audio_path, language="ko", verbose=debug)
            if logger:
                logger(
                    f"[STT] Whisper 추론 완료 ({time.time() - t0:.1f}s), "
                    f"segments={len(result.get('segments', []))}"
                )
        return TranscriptResult(
            text=result["text"],
            language=result.get("language", "ko"),
            segments=result.get("segments", []),
            source_type="youtube",
        )

    # 3) 로컬 파일
    model = _get_whisper_model(model_size)
    if logger:
        logger(f"[STT] 로컬 파일 Whisper 추론 시작: {source}")
    t0 = time.time()
    result = model.transcribe(source, language="ko", verbose=debug)
    if logger:
        logger(
            f"[STT] 로컬 파일 Whisper 추론 완료 ({time.time() - t0:.1f}s), "
            f"segments={len(result.get('segments', []))}"
        )
    return TranscriptResult(
        text=result["text"],
        language=result.get("language", "ko"),
        segments=result.get("segments", []),
        source_type="file",
    )
