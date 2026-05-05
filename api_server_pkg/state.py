"""모듈 전역 상태 — 카카오 멀티턴 잡, 결과 토큰, 백그라운드 task 보관.

여러 라우터·헬퍼가 공유하므로 한 곳에 모아둔다. 단일 프로세스 가정 (수평 확장 시 외부 store 필요).
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

# 카카오 콜백 타임아웃 — 카카오 60초 한도, 여유 5초
KAKAO_CALLBACK_TIMEOUT = 55
# 폴링 모드 최대 대기 (STT/분석 백그라운드 시간)
KAKAO_POLL_TIMEOUT = 600
# 완료된 결과 보관 시간 (초)
KAKAO_JOB_TTL = 600

# 결과 상세 페이지 토큰 TTL — 카카오 카드의 "자세히 보기" 링크
RESULT_TOKEN_TTL = 3600

# user_id → job state dict (구조는 kakao.new_job_state 참조)
pending_jobs: dict[str, dict[str, Any]] = {}
# 다중 사용자 동시 접속 race 방지
jobs_lock = threading.Lock()

# asyncio bg task 가 GC 되지 않도록 보관
bg_tasks: set[asyncio.Task] = set()

# token → {result, user_context, input_type, expires_at, user_id, chat_history}
result_tokens: dict[str, dict[str, Any]] = {}

# 공개 URL 캐시 — _get_public_base_url() 60초 캐시
public_url_cache: dict[str, Any] = {"url": "", "expires": 0.0}


def spawn_bg(coro) -> asyncio.Task:
    """asyncio bg task 등록 + GC 방지 참조 보관."""
    task = asyncio.create_task(coro)
    bg_tasks.add(task)
    task.add_done_callback(bg_tasks.discard)
    return task
