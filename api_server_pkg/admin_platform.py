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


@router.post("/api/admin/login")
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


@router.post("/api/admin/api-keys")
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


@router.get("/api/admin/api-keys")
async def admin_list_api_keys() -> dict[str, Any]:
    try:
        require_db()
        keys = await asyncio.to_thread(api_key_module.list_keys)
        return {"keys": keys}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/admin/api-keys/{key_id}/revoke")
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


@router.get("/api/admin/observability")
async def admin_observability(hours: int = 24, recent_limit: int = 100) -> dict[str, Any]:
    try:
        require_db()
        summary = await asyncio.to_thread(repository.request_log_summary, hours=hours)
        recent = await asyncio.to_thread(repository.request_log_recent, recent_limit)
        return {"summary": summary, "recent": recent}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/admin/cost")
async def admin_cost(days: int = 30) -> dict[str, Any]:
    try:
        require_db()
        return await asyncio.to_thread(repository.aggregate_costs, days=days)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/admin/abuse-blocks")
async def admin_abuse_blocks() -> dict[str, Any]:
    """현재 일시 차단된 user_id 목록."""
    from platform_layer import abuse_guard as _ag
    return {"blocks": _ag.list_blocks()}


@router.post("/api/admin/abuse-blocks/{user_id}/unblock")
async def admin_abuse_unblock(user_id: str) -> dict[str, Any]:
    from platform_layer import abuse_guard as _ag
    ok = _ag.unblock(user_id)
    return {"ok": ok}
