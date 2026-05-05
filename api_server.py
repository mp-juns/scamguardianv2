"""ScamGuardian v2 FastAPI server — entry point.

세부 라우터·헬퍼는 `api_server_pkg/` 에 분리되어 있다.
이 파일은 진입점 (`uvicorn api_server:app`) 과 테스트 호환용 re-export 만 담당한다.
"""

from __future__ import annotations

import logging

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

from api_server_pkg.app import create_app

app = create_app()

# ── 테스트 호환 re-export ──
# tests/test_kakao_*, tests/test_abuse_block, tests/test_safety_parser 가
# `from api_server import _kakao_detect_input` 등으로 직접 가져옴.
from api_server_pkg.admin_runs import _resolve_admin_media_path  # noqa: E402
from api_server_pkg.kakao import (  # noqa: E402
    _is_system_command,
    _kakao_detect_input,
    _wrap_with_soft_warning,
)

__all__ = [
    "app",
    "_is_system_command",
    "_kakao_detect_input",
    "_resolve_admin_media_path",
    "_wrap_with_soft_warning",
]
