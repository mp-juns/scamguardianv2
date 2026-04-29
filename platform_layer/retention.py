"""
업로드 파일 retention — `.scamguardian/uploads/**` 의 오래된 파일 자동 삭제.

배경:
- `/api/analyze-upload` 와 카카오 webhook 의 이미지/PDF/영상 업로드는
  `.scamguardian/uploads/{run_id}/...` 또는 `.scamguardian/uploads/kakao/{uuid}.{ext}`
  로 영구 저장된다 (분석은 즉시 끝나도 파일은 안 지워짐).
- 디스크 누수 + 사용자 데이터 보존기간 정책 부재 → 운영 위험.

이 모듈:
- mtime 기준 N일 (`UPLOAD_RETENTION_DAYS`, 기본 30) 지난 *파일* 만 삭제.
- 빈 디렉토리 정리.
- 외부 호출 0회. 동기 호출만 (호출자가 asyncio.to_thread 또는 별도 스레드로 wrap).
- DB record 와는 무관 — 파일만 청소. analysis_runs 등은 오래된 row 그대로 둠.

진입점:
- `sweep(root=None, days=None)` — 1회 실행. 결과 dict 반환.
- `start_background_sweeper(loop, interval_sec=86400)` — 백그라운드 24h 주기.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("retention")

DEFAULT_ROOT = Path(".scamguardian") / "uploads"
DEFAULT_DAYS = int(os.getenv("UPLOAD_RETENTION_DAYS", "30"))
DEFAULT_INTERVAL_SEC = int(os.getenv("UPLOAD_RETENTION_SWEEP_SEC", str(60 * 60 * 24)))


@dataclass
class SweepResult:
    root: str
    cutoff_unix: float
    files_scanned: int = 0
    files_deleted: int = 0
    bytes_freed: int = 0
    dirs_removed: int = 0
    errors: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "cutoff_unix": self.cutoff_unix,
            "files_scanned": self.files_scanned,
            "files_deleted": self.files_deleted,
            "bytes_freed": self.bytes_freed,
            "dirs_removed": self.dirs_removed,
            "errors": self.errors or [],
        }


def sweep(root: Path | str | None = None, days: int | None = None) -> SweepResult:
    """오래된 파일 삭제. days=0 이면 청소 비활성화 (no-op)."""
    target_root = Path(root) if root else DEFAULT_ROOT
    keep_days = days if days is not None else DEFAULT_DAYS
    cutoff = time.time() - keep_days * 86400
    result = SweepResult(root=str(target_root), cutoff_unix=cutoff)
    if keep_days <= 0:
        log.info("retention disabled (days=%s)", keep_days)
        return result
    if not target_root.exists():
        log.info("retention root missing — nothing to do (%s)", target_root)
        return result

    errors: list[str] = []
    # 1) 파일 삭제
    for path in target_root.rglob("*"):
        if not path.is_file():
            continue
        result.files_scanned += 1
        try:
            mtime = path.stat().st_mtime
        except OSError as exc:
            errors.append(f"stat {path}: {exc}")
            continue
        if mtime >= cutoff:
            continue
        try:
            size = path.stat().st_size
            path.unlink()
            result.files_deleted += 1
            result.bytes_freed += size
        except OSError as exc:
            errors.append(f"unlink {path}: {exc}")

    # 2) 빈 디렉토리 정리 (root 자체는 유지)
    for path in sorted(target_root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path == target_root or not path.is_dir():
            continue
        try:
            next(path.iterdir())
        except StopIteration:
            try:
                path.rmdir()
                result.dirs_removed += 1
            except OSError as exc:
                errors.append(f"rmdir {path}: {exc}")
        except OSError as exc:
            errors.append(f"iterdir {path}: {exc}")

    if errors:
        result.errors = errors
    log.info(
        "retention sweep: scanned=%d deleted=%d freed=%dB dirs_removed=%d errors=%d (root=%s, keep=%dd)",
        result.files_scanned,
        result.files_deleted,
        result.bytes_freed,
        result.dirs_removed,
        len(errors),
        target_root,
        keep_days,
    )
    return result


async def _run_periodic(interval_sec: int) -> None:
    while True:
        try:
            await asyncio.to_thread(sweep)
        except Exception as exc:  # noqa: BLE001
            log.warning("retention sweep failed: %s", exc)
        await asyncio.sleep(interval_sec)


def start_background_sweeper(
    loop: asyncio.AbstractEventLoop | None = None,
    interval_sec: int | None = None,
) -> asyncio.Task[None]:
    """백그라운드 sweep task 등록. FastAPI startup 에서 1회 호출."""
    interval = interval_sec if interval_sec is not None else DEFAULT_INTERVAL_SEC
    target_loop = loop or asyncio.get_event_loop()
    task = target_loop.create_task(_run_periodic(interval))
    log.info("retention background sweeper started — every %ds", interval)
    return task
