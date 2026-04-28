"""
입력 어뷰즈 방어 — Claude API 무임승차/과사용 차단.

ScamGuardian 의 분석 엔드포인트는 호출당 Claude(분석+요약) + Whisper/Vision +
Serper + VT 비용이 드는데, 정상 라벨 분석이 아닌 잡담·도배·악의적 긴 입력은
무료 LLM 통로로 악용될 수 있다. 외부 API 호출 *전* 단계에서 차단.

가드 단계:
1. 길이 cap — max 5000자 / min 10자 (한국어 기준 토큰 ~1500-2500)
2. 반복 detection — 단일 문자·짧은 패턴이 80% 이상이면 의미 없는 입력
3. gibberish — 한국어 음절·영문·숫자 비율이 너무 낮으면 거부
4. duplicate — 같은 텍스트 같은 키 5분 내 N번 반복 시 throttle (in-memory)

이 모듈은 *외부 API 호출 0회* 로 동작 — 가드 자체가 비용을 만들면 의미 없음.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass


MAX_CHARS = int(os.getenv("ANALYZE_MAX_TEXT_LENGTH", "5000"))
MIN_CHARS = int(os.getenv("ANALYZE_MIN_TEXT_LENGTH", "10"))
REPETITION_TOP3_RATIO = 0.80   # 상위 3 글자 비율
GIBBERISH_VALID_RATIO = 0.50   # 의미 있는 글자 비율 minimum
DUP_WINDOW_SEC = 300           # 5분
DUP_LIMIT = 5                  # 같은 입력 같은 키 5분에 5번 이상 → throttle


_HANGUL_RE = re.compile(r"[가-힣]")
_LATIN_DIGIT_RE = re.compile(r"[A-Za-z0-9]")


@dataclass
class GuardReject:
    code: str           # MIN_LEN / MAX_LEN / REPETITIVE / GIBBERISH / DUPLICATE / EMPTY
    message: str
    detail: str = ""


_dup_lock = threading.Lock()
_dup_log: dict[str, list[float]] = defaultdict(list)


def _signature(text: str, key_id: str | None) -> str:
    h = hashlib.sha256()
    h.update((key_id or "anon").encode())
    h.update(b"::")
    h.update(text.strip().encode("utf-8"))
    return h.hexdigest()


def _check_duplicate(text: str, key_id: str | None) -> GuardReject | None:
    sig = _signature(text, key_id)
    now = time.time()
    cutoff = now - DUP_WINDOW_SEC
    with _dup_lock:
        log = _dup_log[sig]
        log[:] = [t for t in log if t > cutoff]
        if len(log) >= DUP_LIMIT:
            wait = max(1, int(DUP_WINDOW_SEC - (now - log[0]) + 0.5))
            return GuardReject(
                "DUPLICATE",
                "동일한 입력이 짧은 시간에 여러 번 반복됐어요. 잠시 후 다시 시도해 주세요.",
                detail=f"5분 내 {DUP_LIMIT}회 초과, 약 {wait}초 후 재시도 가능",
            )
        log.append(now)
    return None


def check(text: str, *, key_id: str | None = None, dedup: bool = True) -> GuardReject | None:
    """입력 분석 전에 호출. 거부 사유 있으면 GuardReject, 통과면 None."""
    if text is None:
        return GuardReject("EMPTY", "입력이 비어 있습니다.")
    stripped = text.strip()
    if not stripped:
        return GuardReject("EMPTY", "입력이 비어 있습니다.")

    n = len(stripped)
    if n < MIN_CHARS:
        return GuardReject(
            "MIN_LEN",
            f"입력이 너무 짧아요. 최소 {MIN_CHARS}자 이상 보내주세요.",
            detail=f"length={n}",
        )
    if n > MAX_CHARS:
        return GuardReject(
            "MAX_LEN",
            f"입력이 너무 길어요. 최대 {MAX_CHARS}자까지만 분석합니다 (현재 {n:,}자).",
            detail=f"length={n}",
        )

    # 반복 / 도배 검출
    no_space = re.sub(r"\s", "", stripped)
    if no_space:
        counter = Counter(no_space)
        if len(counter) <= 3:
            # 거의 한 두 글자만 반복
            return GuardReject(
                "REPETITIVE",
                "의미 있는 분석 대상으로 보이지 않아요. 의심되는 메시지·URL·문서를 보내주세요.",
                detail=f"unique_chars={len(counter)}",
            )
        top3_sum = sum(c for _, c in counter.most_common(3))
        if top3_sum / len(no_space) > REPETITION_TOP3_RATIO:
            return GuardReject(
                "REPETITIVE",
                "반복 문자 비율이 너무 높아요. 분석할 내용을 다시 확인해 주세요.",
                detail=f"top3_ratio={top3_sum / len(no_space):.2f}",
            )

    # 의미 글자 비율 — 한국어/영어/숫자 비율이 너무 낮으면 (이모지/특수기호만) 거부
    valid = len(_HANGUL_RE.findall(stripped)) + len(_LATIN_DIGIT_RE.findall(stripped))
    if valid / max(1, len(stripped)) < GIBBERISH_VALID_RATIO:
        return GuardReject(
            "GIBBERISH",
            "분석 가능한 문자가 거의 없어요. 한국어·영문 텍스트로 다시 보내주세요.",
            detail=f"valid_ratio={valid / max(1, len(stripped)):.2f}",
        )

    # 동일 입력 도배
    if dedup:
        rej = _check_duplicate(stripped, key_id)
        if rej is not None:
            return rej

    return None


def reset_state() -> None:
    """테스트용 — duplicate window 초기화."""
    with _dup_lock:
        _dup_log.clear()
