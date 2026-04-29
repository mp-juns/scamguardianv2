#!/usr/bin/env python3
"""
업로드 retention 1회 실행 스크립트 (cron 용).

사용:
    python scripts/cleanup_uploads.py              # env 의 UPLOAD_RETENTION_DAYS (기본 30)
    python scripts/cleanup_uploads.py --days 7
    python scripts/cleanup_uploads.py --root /path/to/uploads --days 0  # no-op
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 모듈 import 가 가능하도록 프로젝트 루트를 sys.path 에 추가
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from platform_layer import retention  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="업로드 retention sweep")
    parser.add_argument("--root", default=None, help="청소 대상 루트 (기본 .scamguardian/uploads)")
    parser.add_argument("--days", type=int, default=None, help="보존 일수 (기본 env)")
    args = parser.parse_args()

    result = retention.sweep(root=args.root, days=args.days)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
