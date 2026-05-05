"""어드민 — 학습 세션 관리 (mDeBERTa 분류기 / GLiNER 엔티티)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException

from .models import StartTrainingRequest

router = APIRouter()


@router.get("/api/admin/training/data-stats")
async def admin_training_data_stats() -> dict[str, Any]:
    """현재 라벨링 데이터 통계 — 라벨 분포, 학습 가능 여부."""
    try:
        from training import data as tdata
        cls = await asyncio.to_thread(tdata.load_classifier_dataset)
        gli = await asyncio.to_thread(tdata.load_gliner_dataset)
        return {
            "classifier": {
                "total": len(cls),
                "labels": tdata.label_distribution(cls),
            },
            "gliner": {
                "total": len(gli),
                "total_entities": sum(len(e.ner) for e in gli),
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/admin/training/sessions")
async def admin_training_start(payload: StartTrainingRequest) -> dict[str, Any]:
    try:
        from training import sessions as tsess
        params = tsess.SessionParams(
            model=payload.model,
            epochs=payload.epochs,
            batch_size=payload.batch_size,
            lora=payload.lora,
            extra_jsonl=payload.extra_jsonl,
            val_ratio=payload.val_ratio,
            seed=payload.seed,
            base_model=payload.base_model,
        )
        info = await asyncio.to_thread(tsess.start_session, params)
        return info
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/admin/training/sessions")
async def admin_training_list(limit: int = 50) -> dict[str, Any]:
    try:
        from training import sessions as tsess
        items = await asyncio.to_thread(tsess.list_sessions, limit)
        return {"sessions": items, "active_models": tsess.get_active_models()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/admin/training/sessions/{session_id}")
async def admin_training_detail(session_id: str) -> dict[str, Any]:
    try:
        from training import sessions as tsess
        info = await asyncio.to_thread(tsess.get_session, session_id)
        if info is None:
            raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
        metrics = await asyncio.to_thread(tsess.read_metrics, session_id, 500)
        log_tail = await asyncio.to_thread(tsess.read_log_tail, session_id, 8000)
        return {"session": info, "metrics": metrics, "log_tail": log_tail}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/admin/training/sessions/{session_id}/cancel")
async def admin_training_cancel(session_id: str) -> dict[str, Any]:
    try:
        from training import sessions as tsess
        ok = await asyncio.to_thread(tsess.cancel_session, session_id)
        if not ok:
            raise HTTPException(status_code=409, detail="취소할 수 없는 상태입니다.")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/admin/training/sessions/{session_id}/activate")
async def admin_training_activate(session_id: str) -> dict[str, Any]:
    try:
        from training import sessions as tsess
        result = await asyncio.to_thread(tsess.activate_session, session_id)
        return {"ok": True, **result}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
