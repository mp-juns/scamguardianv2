"""어드민 라벨링 큐 + 분석 run 상세 + 미디어 스트리밍 + AI 초안.

엔드포인트:
- /api/admin/runs (목록·search·next)
- /api/admin/runs/{run_id} (상세·claim·annotations·ai-draft·media)
- /api/admin/metrics, /api/admin/stats
- /api/admin/scam-types
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from db import repository
from pipeline import eval as pipeline_eval
from pipeline.config import DEFAULT_SCAM_TYPES

from .common import normalize_catalog_payload, options_payload, require_db
from .models import ClaimRunRequest, HumanAnnotationRequest, ScamTypeCatalogRequest

router = APIRouter()


@router.get("/api/admin/runs")
async def admin_list_runs(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    try:
        require_db()
        runs = await asyncio.to_thread(
            repository.list_runs_for_labeling,
            limit=limit,
            offset=offset,
            status_filter=status,
        )
        return {"runs": runs, "limit": limit, "offset": offset}
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/admin/runs/{run_id}/claim")
async def admin_claim_run(run_id: str, payload: ClaimRunRequest) -> dict[str, Any]:
    try:
        require_db()
        labeler = payload.labeler.strip() or "Admin"
        ok = await asyncio.to_thread(repository.claim_run, run_id, labeler)
        if not ok:
            raise HTTPException(status_code=409, detail="다른 검수자가 이미 작업 중입니다.")
        return {"ok": True}
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/admin/runs/search")
async def admin_search_runs(
    q: str | None = None,
    scam_type: str | None = None,
    risk_level: str | None = None,
    labeled: str | None = None,
    limit: int = 30,
    offset: int = 0,
) -> dict[str, Any]:
    try:
        require_db()
        labeled_bool: bool | None = None
        if labeled == "true":
            labeled_bool = True
        elif labeled == "false":
            labeled_bool = False
        result = await asyncio.to_thread(
            repository.search_runs,
            query=q,
            scam_type=scam_type,
            risk_level=risk_level,
            labeled=labeled_bool,
            limit=limit,
            offset=offset,
        )
        return result
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/admin/runs/next")
async def admin_next_run() -> dict[str, Any]:
    try:
        require_db()
        run = await asyncio.to_thread(repository.get_next_unannotated_run)
        return {"run": run, "options": options_payload()}
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/admin/runs/{run_id}")
async def admin_run_detail(run_id: str) -> dict[str, Any]:
    try:
        require_db()
        detail = await asyncio.to_thread(repository.get_run_detail, run_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="해당 run을 찾을 수 없습니다.")
        detail["options"] = options_payload()
        return detail
    except HTTPException:
        raise
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/admin/runs/{run_id}/annotations")
async def admin_save_annotation(run_id: str, payload: HumanAnnotationRequest) -> dict[str, Any]:
    try:
        require_db()
        run = await asyncio.to_thread(repository.get_run_detail, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="해당 run을 찾을 수 없습니다.")

        labeler = (payload.labeler or "").strip() or "Admin"
        annotation = await asyncio.to_thread(
            repository.upsert_human_annotation,
            run_id=run_id,
            scam_type_gt=payload.scam_type_gt,
            entities_gt=payload.entities_gt,
            triggered_flags_gt=payload.triggered_flags_gt,
            labeler=labeler,
            transcript_corrected_text=payload.transcript_corrected_text,
            stt_quality=payload.stt_quality,
            notes=payload.notes,
        )
        return {"ok": True, "annotation": annotation}
    except HTTPException:
        raise
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


_MEDIA_MIME_BY_SUFFIX = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".aac": "audio/aac",
}


_UPLOADS_ROOT = (Path(".scamguardian") / "uploads").resolve()


def _resolve_admin_media_path(stored_path_str: str) -> Path:
    """저장된 미디어 경로가 uploads 디렉토리 안인지 검증 후 반환 (path traversal 방지)."""
    candidate = Path(stored_path_str).resolve()
    try:
        candidate.relative_to(_UPLOADS_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="허용되지 않은 경로입니다.") from exc
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="미디어 파일을 찾을 수 없습니다.")
    return candidate


@router.get("/api/admin/runs/{run_id}/media")
async def admin_get_media(run_id: str) -> FileResponse:
    """라벨링용으로 보존된 원본 업로드 파일을 스트리밍한다."""
    try:
        require_db()
        detail = await asyncio.to_thread(repository.get_run_detail, run_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="해당 run을 찾을 수 없습니다.")
        media = (detail["run"].get("metadata") or {}).get("media") or {}
        stored = media.get("stored_path")
        if not stored:
            raise HTTPException(status_code=404, detail="저장된 미디어가 없습니다.")
        path = _resolve_admin_media_path(stored)
        suffix = path.suffix.lower()
        media_type = _MEDIA_MIME_BY_SUFFIX.get(suffix, "application/octet-stream")
        filename = media.get("original_filename") or path.name
        return FileResponse(path, media_type=media_type, filename=filename)
    except HTTPException:
        raise
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/admin/metrics")
async def admin_metrics(scam_type: str | None = None) -> dict[str, Any]:
    try:
        require_db()
        records = await asyncio.to_thread(repository.fetch_annotated_pairs, scam_type)
        metrics = pipeline_eval.evaluate_annotated_runs(records)
        metrics["filters"] = {"scam_type": scam_type}
        return metrics
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/admin/runs/{run_id}/ai-draft")
async def admin_ai_draft(run_id: str) -> dict[str, Any]:
    """Claude API로 라벨링 초안을 자동 생성. 검수자는 초안 확인 후 수정/승인만."""
    try:
        require_db()
        detail = await asyncio.to_thread(repository.get_run_detail, run_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="해당 run을 찾을 수 없습니다.")

        from pipeline import claude_labeler

        run = detail["run"]
        transcript = run.get("transcript_text", "")
        predicted_scam_type = (run.get("classification_scanner") or {}).get("scam_type", "")
        predicted_entities = run.get("entities_predicted") or []
        predicted_flags = run.get("triggered_flags_predicted") or []

        draft = await asyncio.to_thread(
            claude_labeler.generate_draft,
            transcript,
            predicted_scam_type,
            predicted_entities,
            predicted_flags,
        )
        return {"ok": True, "draft": draft}
    except HTTPException:
        raise
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/admin/stats")
async def admin_stats() -> dict[str, Any]:
    try:
        require_db()
        stats = await asyncio.to_thread(repository.get_dashboard_stats)
        return stats
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/admin/scam-types")
async def admin_scam_types() -> dict[str, Any]:
    try:
        require_db()
        items = await asyncio.to_thread(repository.list_custom_scam_types)
        return {"items": items, "options": options_payload()}
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/admin/scam-types")
async def admin_add_scam_type(payload: ScamTypeCatalogRequest) -> dict[str, Any]:
    try:
        require_db()
        normalized = normalize_catalog_payload(payload)
        if not normalized["name"]:
            raise HTTPException(status_code=400, detail="스캠 유형 이름을 입력해주세요.")
        if normalized["name"] in DEFAULT_SCAM_TYPES:
            raise HTTPException(status_code=400, detail="기본 스캠 유형과 같은 이름은 추가할 수 없습니다.")

        item = await asyncio.to_thread(
            repository.upsert_custom_scam_type,
            name=normalized["name"],
            description=normalized["description"],
            labels=normalized["labels"],
        )
        return {"ok": True, "item": item, "options": options_payload()}
    except HTTPException:
        raise
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
