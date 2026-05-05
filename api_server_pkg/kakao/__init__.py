"""카카오 챗봇 webhook + 멀티턴 컨텍스트 수집 흐름.

서브모듈 분할:
- `detect`        — URL/입력 감지 (`_kakao_detect_input`, `_kakao_materialize_url`)
- `commands`      — 시스템 명령 / 결과 요청 / soft warning / classify_error
- `tasks`         — 잡 상태 + 파이프라인 wrapper + 백그라운드 task
- `context_flow`  — 멀티턴 컨텍스트 수집 + done state 처리
- `router`        — `/webhook/kakao` 엔드포인트

`api_server.app` 는 `kakao.router` 를 include 하고, 테스트는 `from api_server import _kakao_detect_input`
처럼 가져오므로 아래 re-export 를 유지한다.
"""

from __future__ import annotations

from .commands import _is_system_command, _wrap_with_soft_warning
from .detect import _kakao_detect_input
from .router import router

__all__ = [
    "router",
    "_is_system_command",
    "_kakao_detect_input",
    "_wrap_with_soft_warning",
]
