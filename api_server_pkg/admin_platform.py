"""어드민 — 로그인 / API key 관리 / observability / cost / abuse-blocks."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter, HTTPException

from db import repository
from platform_layer import api_keys as api_key_module

from .common import require_db
from .models import AdminLoginRequest, CreateApiKeyRequest

router = APIRouter()

_ADMIN_RESPONSES: dict[int | str, dict] = {
    401: {"description": "어드민 토큰 누락 또는 무효"},
    400: {"description": "DB 미설정 또는 유효성 실패"},
    500: {"description": "서버 내부 오류"},
}


@router.post(
    "/api/admin/login",
    tags=["Admin — Platform"],
    summary="어드민 로그인",
    description=(
        "단일 admin token 검증. `SCAMGUARDIAN_ADMIN_TOKEN` 환경변수와 비교(`hmac.compare_digest`). "
        "성공 시 호출자(Next.js)가 같은 값을 httpOnly 쿠키로 저장.\n\n"
        "**Body**: `{token: str}`. **이 엔드포인트만 admin 인증 면제** (검증 자체가 목적)."
    ),
    responses={
        401: {"description": "토큰 불일치"},
        503: {"description": "ADMIN_TOKEN 미설정 — 어드민 비활성"},
    },
)
async def admin_login(payload: AdminLoginRequest) -> dict[str, Any]:
    """단일 admin token 검증. 성공 시 호출자(Next.js)가 같은 값을 httpOnly 쿠키로 저장."""
    import hmac as _hmac
    expected = (os.getenv("SCAMGUARDIAN_ADMIN_TOKEN") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="SCAMGUARDIAN_ADMIN_TOKEN 이 설정되지 않아 어드민 접근이 비활성화되어 있습니다.",
        )
    if not payload.token or not _hmac.compare_digest(expected, payload.token.strip()):
        raise HTTPException(status_code=401, detail="토큰이 일치하지 않습니다.")
    return {"ok": True}


@router.post(
    "/api/admin/api-keys",
    tags=["Admin — Platform"],
    summary="API key 발급",
    description=(
        "외부 클라이언트용 `sg_<urlsafe>` API key 발급. **plaintext 는 응답에 1회만** 노출되며 "
        "DB 에는 sha256 해시만 저장된다.\n\n"
        "**Body** (`CreateApiKeyRequest`):\n"
        "- `label` — 클라이언트 식별용 (예: `\"discord-bot\"`)\n"
        "- `monthly_quota` — 월별 호출 수 (기본 1000)\n"
        "- `rpm_limit` — 분당 호출 제한 (기본 30)\n"
        "- `monthly_usd_quota` — 월별 비용 한도 USD (기본 5.0)"
    ),
    responses=_ADMIN_RESPONSES,
)
async def admin_create_api_key(payload: CreateApiKeyRequest) -> dict[str, Any]:
    try:
        require_db()
        record = await asyncio.to_thread(
            api_key_module.issue,
            label=payload.label,
            monthly_quota=payload.monthly_quota,
            rpm_limit=payload.rpm_limit,
            monthly_usd_quota=payload.monthly_usd_quota,
        )
        return record
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/api/admin/api-keys",
    tags=["Admin — Platform"],
    summary="API key 목록",
    description="모든 키 메타데이터(plaintext 제외) + 사용량 카운터.",
    responses=_ADMIN_RESPONSES,
)
async def admin_list_api_keys() -> dict[str, Any]:
    try:
        require_db()
        keys = await asyncio.to_thread(api_key_module.list_keys)
        return {"keys": keys}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/api/admin/api-keys/{key_id}/revoke",
    tags=["Admin — Platform"],
    summary="API key revoke",
    description="키 status 를 `revoked` 로 전환. 이후 모든 요청 401/403.",
    responses={**_ADMIN_RESPONSES, 404: {"description": "key not found"}},
)
async def admin_revoke_api_key(key_id: str) -> dict[str, Any]:
    try:
        require_db()
        ok = await asyncio.to_thread(api_key_module.revoke, key_id)
        if not ok:
            raise HTTPException(status_code=404, detail="키를 찾을 수 없습니다.")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/api/admin/observability",
    tags=["Admin — Platform"],
    summary="Request log 요약 + 최근",
    description=(
        "`request_log` 테이블 — 모든 요청의 status / latency / error 기록.\n\n"
        "**Query**: `hours` (기본 24), `recent_limit` (기본 100)."
    ),
    responses=_ADMIN_RESPONSES,
)
async def admin_observability(hours: int = 24, recent_limit: int = 100) -> dict[str, Any]:
    try:
        require_db()
        summary = await asyncio.to_thread(repository.request_log_summary, hours=hours)
        recent = await asyncio.to_thread(repository.request_log_recent, recent_limit)
        return {"summary": summary, "recent": recent}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/api/admin/cost",
    tags=["Admin — Platform"],
    summary="비용 집계 (cost ledger)",
    description=(
        "`cost_events` 테이블 ledger — provider × api_key × 일자별 USD 합계. "
        "Claude / OpenAI Whisper / Serper / VirusTotal 분리.\n\n"
        "**Query**: `days` (기본 30)."
    ),
    responses=_ADMIN_RESPONSES,
)
async def admin_cost(days: int = 30) -> dict[str, Any]:
    try:
        require_db()
        return await asyncio.to_thread(repository.aggregate_costs, days=days)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/api/admin/abuse-blocks",
    tags=["Admin — Platform"],
    summary="현재 차단된 사용자 목록",
    description="abuse_guard 가 자동 블록한 user_id + 만료 시각.",
    responses=_ADMIN_RESPONSES,
)
async def admin_abuse_blocks() -> dict[str, Any]:
    """현재 일시 차단된 user_id 목록."""
    from platform_layer import abuse_guard as _ag
    return {"blocks": _ag.list_blocks()}


@router.post(
    "/api/admin/abuse-blocks/{user_id}/unblock",
    tags=["Admin — Platform"],
    summary="사용자 차단 해제",
    description="자동 블록을 수동으로 해제. False positive 보정용.",
    responses=_ADMIN_RESPONSES,
)
async def admin_abuse_unblock(user_id: str) -> dict[str, Any]:
    from platform_layer import abuse_guard as _ag
    ok = _ag.unblock(user_id)
    return {"ok": ok}
