"""v4 whisper chunker 인프라 테스트 (API 호출 없이 ffmpeg 로직만)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


pytestmark = pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg 필요")


def _make_silence(path: Path, seconds: int) -> Path:
    """ffmpeg 으로 N초 무음 wav 생성."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r=16000:cl=mono",
            "-t", str(seconds),
            "-c:a", "pcm_s16le",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def test_split_to_chunks_count(tmp_path):
    from experiments.v4_whisper.chunker import split_to_chunks

    audio = _make_silence(tmp_path / "silence.wav", seconds=12)
    chunks = split_to_chunks(audio, chunk_sec=5, out_dir=tmp_path / "chunks")
    # 12초 → 5+5+2 = 3 chunks
    assert len(chunks) == 3
    for p in chunks:
        assert p.exists()
        assert p.suffix == ".wav"


def test_split_to_chunks_short_audio(tmp_path):
    from experiments.v4_whisper.chunker import split_to_chunks

    audio = _make_silence(tmp_path / "short.wav", seconds=3)
    chunks = split_to_chunks(audio, chunk_sec=5, out_dir=tmp_path / "chunks")
    assert len(chunks) == 1


def test_audio_duration(tmp_path):
    from experiments.v4_whisper.chunker import _audio_duration_sec

    audio = _make_silence(tmp_path / "x.wav", seconds=7)
    duration = _audio_duration_sec(audio)
    assert 6.5 < duration < 7.5


def test_split_missing_file_raises(tmp_path):
    from experiments.v4_whisper.chunker import split_to_chunks

    with pytest.raises(FileNotFoundError):
        split_to_chunks(tmp_path / "does-not-exist.wav")
