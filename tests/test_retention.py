"""업로드 retention sweep 테스트."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from platform_layer import retention


def _mk(path: Path, content: bytes = b"x", age_days: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if age_days is not None:
        ts = time.time() - age_days * 86400
        os.utime(path, (ts, ts))
    return path


def test_sweep_keeps_recent_files(tmp_path):
    new_file = _mk(tmp_path / "a.png", age_days=1)
    res = retention.sweep(root=tmp_path, days=30)
    assert new_file.exists()
    assert res.files_deleted == 0
    assert res.files_scanned == 1


def test_sweep_deletes_old_files(tmp_path):
    old_file = _mk(tmp_path / "kakao" / "old.png", b"abc", age_days=60)
    keep = _mk(tmp_path / "kakao" / "new.png", b"xyz", age_days=1)
    res = retention.sweep(root=tmp_path, days=30)
    assert not old_file.exists()
    assert keep.exists()
    assert res.files_deleted == 1
    assert res.bytes_freed == 3


def test_sweep_removes_empty_dirs_after_delete(tmp_path):
    _mk(tmp_path / "run-1" / "video.mp4", b"vv", age_days=60)
    res = retention.sweep(root=tmp_path, days=30)
    assert res.files_deleted == 1
    assert res.dirs_removed == 1
    assert not (tmp_path / "run-1").exists()
    assert tmp_path.exists()  # root 자체는 유지


def test_sweep_days_zero_disables(tmp_path):
    old_file = _mk(tmp_path / "old.png", age_days=999)
    res = retention.sweep(root=tmp_path, days=0)
    assert old_file.exists()
    assert res.files_deleted == 0
    assert res.files_scanned == 0  # no-op


def test_sweep_missing_root_is_noop(tmp_path):
    target = tmp_path / "does-not-exist"
    res = retention.sweep(root=target, days=30)
    assert res.files_scanned == 0
    assert res.files_deleted == 0


def test_sweep_mixed_age_in_same_dir(tmp_path):
    nested = tmp_path / "kakao"
    _mk(nested / "old1.png", age_days=60)
    _mk(nested / "old2.pdf", age_days=45)
    keep = _mk(nested / "new.png", age_days=1)
    res = retention.sweep(root=tmp_path, days=30)
    assert res.files_deleted == 2
    assert keep.exists()
    # 디렉토리는 비어있지 않아 유지
    assert nested.exists()
