"""
per-key sliding window rate limit (분당) + monthly quota.

분당 RPM 은 인메모리 (단일 인스턴스 기준) — 멀티 워커 환경엔 Redis 권장.
월별 quota 는 DB(touch_api_key_usage) 에서 atomic 갱신.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from db import repository

_WINDOW_SEC = 60.0
_lock = threading.Lock()
_buckets: dict[str, deque[float]] = defaultdict(deque)


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int, scope: str):
        self.retry_after = retry_after
        self.scope = scope
        super().__init__(f"Rate limit exceeded ({scope})")


def check_and_consume(key_id: str, rpm_limit: int) -> None:
    """RPM 검사 + 통과 시 토큰 소진. 초과면 RateLimitExceeded."""
    now = time.time()
    with _lock:
        bucket = _buckets[key_id]
        cutoff = now - _WINDOW_SEC
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= rpm_limit:
            oldest = bucket[0]
            retry = max(1, int(_WINDOW_SEC - (now - oldest) + 0.5))
            raise RateLimitExceeded(retry, scope="rpm")
        bucket.append(now)


def consume_monthly_quota(key_id: str) -> dict:
    """월별 쿼터 차감 — 호출 수 quota 0 이면 RateLimitExceeded(scope='monthly')."""
    info = repository.touch_api_key_usage(key_id)
    if info is None:
        raise RateLimitExceeded(60, scope="invalid_key")
    if info.get("status") != "active":
        raise RateLimitExceeded(60, scope=f"status:{info.get('status')}")
    if info.get("remaining_month", 0) < 0:
        raise RateLimitExceeded(60 * 60 * 24, scope="monthly")
    return info


def check_monthly_usd_cap(key_id: str, usd_quota: float) -> None:
    """이번 달 누적 USD 가 quota 를 넘으면 RateLimitExceeded(scope='usd').

    호출 직후가 아닌 다음 호출 진입 시점에 계산되므로 약간의 over-shoot 가능.
    엄격 강제 필요시 호출 *전에* 평균 비용 추정해서 차감하는 방식으로 확장 가능.
    """
    if usd_quota <= 0:
        return  # 0 이하면 무제한 의미
    used = repository.get_monthly_usd_for_key(key_id)
    if used >= usd_quota:
        raise RateLimitExceeded(60 * 60 * 24, scope="usd")
