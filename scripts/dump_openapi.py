"""FastAPI 가 자동 생성하는 OpenAPI spec 을 docs/openapi.json 으로 dump.

서버를 띄우지 않고 `app.openapi()` 직접 호출. CI 또는 docs PR 에서 spec 동기화 검증용.

사용:
    python scripts/dump_openapi.py
    python scripts/dump_openapi.py --check   # diff 만 표시 (CI)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = REPO_ROOT / "docs" / "openapi.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="기존 파일과 다르면 비제로 종료")
    args = parser.parse_args()

    sys.path.insert(0, str(REPO_ROOT))
    from api_server import app

    spec = app.openapi()
    paths = sorted(spec.get("paths", {}).keys())
    print(f"endpoint 수: {len(paths)}")
    for p in paths:
        methods = sorted(spec["paths"][p].keys())
        print(f"  {p}  [{','.join(methods)}]")

    new_text = json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if args.check:
        if not OUTPUT.exists():
            print(f"\n❌ {OUTPUT} 가 없습니다 — `python scripts/dump_openapi.py` 실행 필요")
            return 1
        old_text = OUTPUT.read_text(encoding="utf-8")
        if old_text != new_text:
            print(f"\n❌ {OUTPUT} 가 spec 과 다릅니다 — `python scripts/dump_openapi.py` 재실행 후 커밋")
            return 1
        print(f"\n✅ {OUTPUT} 최신 상태")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(new_text, encoding="utf-8")
    print(f"\n✅ wrote {OUTPUT.relative_to(REPO_ROOT)} ({len(new_text):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
