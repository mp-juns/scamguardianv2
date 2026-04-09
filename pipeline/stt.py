"""
ScamGuardian v2 — STT 모듈
YouTube URL / 로컬 파일 / 텍스트 입력을 처리하여 텍스트를 반환한다.

STT 백엔드:
- OPENAI_API_KEY 환경변수가 있으면 OpenAI Whisper API 사용 (빠름, 유료)
- 없으면 로컬 openai-whisper 사용 (느림, 무료)
"""

from __future__ import annotations

import os
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
    try:
        p = Path(source)
        return p.exists() and p.is_file()
    except OSError:
        return False


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
                "preferredcodec": "mp3",
                "preferredquality": "64",
            }
        ],
        # 앞 5분만 추출 (카카오 콜백 1분 제한 + OpenAI API 25MB 제한 대응)
        "postprocessor_args": {"ExtractAudio": ["-t", "300"]},
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

    mp3_path = str(Path(output_dir) / "audio.mp3")
    if not Path(mp3_path).exists():
        raise FileNotFoundError(f"YouTube 오디오 다운로드 실패: {url}")
    return mp3_path


def _get_whisper_model(model_size: str) -> whisper.Whisper:
    if model_size not in _whisper_model_cache:
        t0 = time.time()
        _whisper_model_cache[model_size] = whisper.load_model(model_size)
        print(f"[STT] Whisper 모델 로드 완료: {model_size} ({time.time() - t0:.1f}s)")
    return _whisper_model_cache[model_size]


def _transcribe_with_openai_api(
    audio_path: str,
    logger: Callable[[str], None] | None = None,
) -> dict:
    """OpenAI Whisper API로 음성 파일을 텍스트로 변환한다."""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    if logger:
        logger("[STT] OpenAI Whisper API 호출 시작")
    t0 = time.time()
    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="ko",
        )
    if logger:
        logger(f"[STT] OpenAI Whisper API 완료 ({time.time() - t0:.1f}s)")
    return {"text": response.text, "language": "ko", "segments": []}


def _ensure_audio_nonempty(path: str) -> None:
    """
    Whisper/ffmpeg 디코더가 오디오를 읽었을 때 길이가 0이면
    (오디오 트랙 없음/깨진 파일/디코딩 실패 등) 명확한 에러로 중단한다.
    """
    audio = whisper.load_audio(path)
    if getattr(audio, "size", 0) == 0:
        raise ValueError(
            "오디오를 읽지 못했습니다. 오디오 트랙이 없는 영상이거나 파일이 손상됐을 수 있습니다."
        )


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

    use_api = bool(os.environ.get("OPENAI_API_KEY"))

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
            _ensure_audio_nonempty(audio_path)
            if use_api:
                result = _transcribe_with_openai_api(audio_path, logger=logger)
            else:
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
    _ensure_audio_nonempty(source)
    if use_api:
        result = _transcribe_with_openai_api(source, logger=logger)
    else:
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
