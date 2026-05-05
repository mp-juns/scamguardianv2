"""어드민 — 학습 세션 관리 (mDeBERTa 분류기 / GLiNER 엔티티)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException

from .models import StartTrainingRequest

router = APIRouter()

_ADMIN_RESPONSES: dict[int | str, dict] = {
    401: {"description": "어드민 토큰 누락 또는 무효"},
    500: {"description": "서버 내부 오류"},
}


@router.get(
    "/api/admin/training/data-stats",
    tags=["Admin — Training"],
    summary="학습 데이터 통계",
    description="현재 라벨링 데이터 라벨 분포 + 엔티티 수 — 학습 시작 전 충분성 판단용.",
    responses=_ADMIN_RESPONSES,
)
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


@router.post(
    "/api/admin/training/sessions",
    tags=["Admin — Training"],
    summary="fine-tune 세션 시작",
    description=(
        "subprocess 로 학습 세션 spawn — `.scamguardian/training_sessions/{id}/` 에 "
        "`status.json` / `metrics.jsonl` / `train.log` 출력.\n\n"
        "**Body** (`StartTrainingRequest`):\n"
        "- `model` — `classifier` (mDeBERTa) 또는 `gliner`\n"
        "- `epochs` (기본 3), `batch_size` (기본 8), `lora` (LoRA 사용)\n"
        "- `extra_jsonl` — 추가 데이터셋 경로\n"
        "- `val_ratio` (기본 0.1), `seed` (기본 17), `base_model`"
    ),
    responses={**_ADMIN_RESPONSES, 400: {"description": "유효성 실패"}},
)
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


@router.get(
    "/api/admin/training/sessions",
    tags=["Admin — Training"],
    summary="학습 세션 목록 + 활성 모델",
    description="모든 세션 메타 + 현재 파이프라인이 사용하는 active 모델 경로 (`active_models.json`).",
    responses=_ADMIN_RESPONSES,
)
async def admin_training_list(limit: int = 50) -> dict[str, Any]:
    try:
        from training import sessions as tsess
        items = await asyncio.to_thread(tsess.list_sessions, limit)
        return {"sessions": items, "active_models": tsess.get_active_models()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/api/admin/training/sessions/{session_id}",
    tags=["Admin — Training"],
    summary="세션 상세 + metrics tail + log tail",
    description="`session` 메타 + 마지막 500 metric 이벤트 + 마지막 8KB 로그.",
    responses={**_ADMIN_RESPONSES, 404: {"description": "session not found"}},
)
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


@router.post(
    "/api/admin/training/sessions/{session_id}/cancel",
    tags=["Admin — Training"],
    summary="학습 세션 취소",
    description="실행 중 subprocess 종료 + status `cancelled` 갱신.",
    responses={**_ADMIN_RESPONSES, 409: {"description": "취소할 수 없는 상태 (이미 끝남)"}},
)
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


@router.post(
    "/api/admin/training/sessions/{session_id}/activate",
    tags=["Admin — Training"],
    summary="학습 결과를 파이프라인에 적용",
    description=(
        "체크포인트 경로를 `.scamguardian/active_models.json` 에 기록 → "
        "`pipeline.active_models` 60s TTL 캐시가 무효화되어 즉시 swap.\n\n"
        "분류기 / GLiNER 각 1개씩 활성 가능. 경로 무효 시 base 모델로 fallback."
    ),
    responses={
        **_ADMIN_RESPONSES,
        400: {"description": "유효성 실패 (e.g. 체크포인트 경로 없음)"},
        404: {"description": "session not found 또는 모델 파일 없음"},
    },
)
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
