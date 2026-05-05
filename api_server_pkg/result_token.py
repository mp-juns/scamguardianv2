"""결과 상세 페이지 토큰 시스템 — 발급·만료·조회.

카카오 카드의 "자세히 보기" 링크가 가리키는 1시간 유효 토큰. 메모리 저장 (state.result_tokens).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from fastapi import APIRouter, HTTPException

from db import repository
from pipeline import kakao_formatter

from . import state

router = APIRouter()


def get_public_base_url() -> str:
    """결과 링크 베이스 URL 동적 조회. env 우선, 없으면 ngrok local API 자동 탐색.

    60초 캐시. ngrok 재시작 시에도 환경변수 따로 안 바꿔도 됨.
    """
    now = time.time()
    if now < state.public_url_cache.get("expires", 0):
        return state.public_url_cache.get("url", "")

    env = os.getenv("SCAMGUARDIAN_PUBLIC_URL", "").strip().rstrip("/")
    url = env
    if not url:
        try:
            import json as _json
            import urllib.request as _ureq
            with _ureq.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=1) as resp:
                data = _json.loads(resp.read().decode())
                for t in data.get("tunnels", []):
                    pu = (t.get("public_url") or "").strip()
                    if pu.startswith("https"):
                        url = pu.rstrip("/")
                        break
        except Exception:
            pass

    state.public_url_cache["url"] = url
    state.public_url_cache["expires"] = now + 60
    return url


def cleanup_expired_result_tokens() -> None:
    now = time.time()
    expired = [t for t, e in state.result_tokens.items() if e.get("expires_at", 0) < now]
    for t in expired:
        del state.result_tokens[t]


def issue_result_token(
    *,
    result: dict[str, Any],
    user_context: dict[str, Any] | None,
    input_type: kakao_formatter.InputType,
    user_id: str | None,
    chat_history: list[Any] | None = None,
) -> tuple[str, str | None]:
    """결과 상세 토큰 발급 + 공개 URL 반환. URL 은 SCAMGUARDIAN_PUBLIC_URL 미설정 시 None."""
    import secrets
    cleanup_expired_result_tokens()
    token = secrets.token_urlsafe(16)
    state.result_tokens[token] = {
        "result": result,
        "user_context": user_context,
        "input_type": input_type.value if hasattr(input_type, "value") else str(input_type),
        "expires_at": time.time() + state.RESULT_TOKEN_TTL,
        "user_id": user_id,
        "chat_history": [
            {"role": getattr(t, "role", ""), "message": getattr(t, "message", "")}
            for t in (chat_history or [])
        ],
    }
    base = get_public_base_url()
    url = f"{base}/result/{token}" if base else None

    logging.getLogger("token").info(
        "result_token issued: token=%s run_id=%s risk_level=%s total_score=%s flags=%d",
        token[:8],
        (result or {}).get("analysis_run_id"),
        (result or {}).get("risk_level"),
        (result or {}).get("total_score"),
        len((result or {}).get("triggered_flags") or []),
    )

    run_id = (result or {}).get("analysis_run_id")
    if run_id and repository.persistence_enabled():
        try:
            chat_dump = [
                {"role": getattr(t, "role", ""), "message": getattr(t, "message", "")}
                for t in (chat_history or [])
            ]
            partial = {}
            if user_context:
                partial["user_context"] = user_context
            if chat_dump:
                partial["chat_history"] = chat_dump
            if partial:
                repository.merge_run_metadata(run_id, partial)
        except Exception as exc:
            logging.getLogger("token").warning(
                "metadata merge 실패 (run_id=%s): %s", run_id, exc,
            )

    return token, url


@router.get("/api/result/{token}")
async def get_result_by_token(token: str) -> dict[str, Any]:
    """카카오 카드의 '자세히 보기' 링크 백엔드 — 토큰으로 분석 결과 반환.

    1시간 TTL. 토큰 없거나 만료 시 404/410.
    """
    cleanup_expired_result_tokens()
    entry = state.result_tokens.get(token)
    if entry is None:
        raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.")
    if entry.get("expires_at", 0) < time.time():
        state.result_tokens.pop(token, None)
        raise HTTPException(status_code=410, detail="결과 링크가 만료됐어요 (1시간 후 만료).")
    from pipeline.config import flag_rationale
    flag_info: dict[str, dict[str, str]] = {}
    for f in (entry["result"].get("triggered_flags") or []):
        key = (f.get("flag") or "").strip()
        if key and key not in flag_info:
            info = flag_rationale(key)
            if info:
                flag_info[key] = info
    return {
        "result": entry["result"],
        "user_context": entry.get("user_context"),
        "input_type": entry.get("input_type"),
        "chat_history": entry.get("chat_history") or [],
        "flag_rationale": flag_info,
        "expires_at": entry["expires_at"],
    }
