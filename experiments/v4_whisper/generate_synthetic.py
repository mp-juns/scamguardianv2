"""한국어 합성 음성 5종 생성 (edge-tts) + 스피커폰 시뮬 옵션.

실행:
    python experiments/v4_whisper/generate_synthetic.py
    python experiments/v4_whisper/generate_synthetic.py --speakerphone   # 음질 저하 추가

산출물:
    experiments/v4_whisper/audio/{id}.mp3 (또는 _spk.wav 시뮬)
    experiments/v4_whisper/audio/{id}.txt  (reference transcript)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "synthetic_samples.jsonl"
AUDIO_DIR = HERE / "audio"


async def _synth_one(item: dict, out: Path) -> None:
    import edge_tts
    communicate = edge_tts.Communicate(item["text"], voice=item["voice"])
    await communicate.save(str(out))


def _speakerphone_degrade(src: Path, dst: Path) -> None:
    """스피커폰 환경 시뮬 — 8kHz 저샘플링 + low-pass + 약한 노이즈 + 압축 자국.

    실전에서는 통화 코덱이 8kHz 좁은 대역 → Whisper 정확도 살짝 떨어짐.
    """
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-af",
        # high-pass 300Hz, low-pass 3400Hz (전화 대역) + 약간의 화이트 노이즈
        "highpass=f=300,lowpass=f=3400,"
        "anlmdn=s=0.0001:p=0.001:r=0.0001,"
        "volume=0.9",
        "-ar", "16000", "-ac", "1",
        str(dst),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--speakerphone", action="store_true", help="전화 대역 시뮬 wav 추가")
    args = parser.parse_args()

    if shutil.which("edge-tts") is None and not _has_edge_tts():
        print("edge-tts 가 설치되지 않음. `pip install edge-tts`", file=sys.stderr)
        return 2

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    samples = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"loaded {len(samples)} samples")

    for item in samples:
        sid = item["id"]
        mp3 = AUDIO_DIR / f"{sid}.mp3"
        ref = AUDIO_DIR / f"{sid}.txt"
        ref.write_text(item["text"], encoding="utf-8")

        if mp3.exists():
            print(f"  ✓ skip (이미 있음): {mp3.name}")
        else:
            print(f"  → synth {sid} ({item['voice']}, {item['scenario']})")
            await _synth_one(item, mp3)

        if args.speakerphone:
            spk = AUDIO_DIR / f"{sid}_spk.wav"
            if spk.exists():
                print(f"  ✓ skip spk: {spk.name}")
            else:
                print(f"    + speakerphone degrade → {spk.name}")
                _speakerphone_degrade(mp3, spk)
                # spk 도 같은 reference 사용
                (AUDIO_DIR / f"{sid}_spk.txt").write_text(item["text"], encoding="utf-8")

    print(f"\nwrote audio + reference to {AUDIO_DIR.relative_to(HERE.parent.parent)}")
    return 0


def _has_edge_tts() -> bool:
    try:
        import edge_tts  # noqa: F401
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
