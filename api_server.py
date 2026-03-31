"""
ScamGuardian v2 FastAPI server.

기존 파이프라인을 웹에서 호출할 수 있도록 HTTP API로 노출한다.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

from db import repository
from pipeline import eval as pipeline_eval
from pipeline import rag
from pipeline.config import DEFAULT_SCAM_TYPES, SCORING_RULES, get_runtime_scam_taxonomy
from pipeline.runner import ScamGuardianPipeline


class AnalyzeRequest(BaseModel):
    source: str | None = None
    text: str | None = None
    whisper_model: str = Field(
        default="medium",
        pattern="^(tiny|base|small|medium|large)$",
    )
    skip_verification: bool = True
    use_llm: bool = False
    use_rag: bool = False


class HumanAnnotationRequest(BaseModel):
    labeler: str | None = None
    scam_type_gt: str
    entities_gt: list[dict[str, Any]] = Field(default_factory=list)
    triggered_flags_gt: list[dict[str, Any]] = Field(default_factory=list)
    transcript_corrected_text: str | None = None
    stt_quality: int | None = Field(default=None, ge=1, le=5)
    notes: str = ""


class ScamTypeCatalogRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=200)
    labels: list[str] = Field(default_factory=list)


def _resolve_source(payload: AnalyzeRequest) -> str:
    return (payload.text or payload.source or "").strip()


def _options_payload() -> dict[str, Any]:
    taxonomy = get_runtime_scam_taxonomy()
    return {
        "scam_types": taxonomy["scam_types"],
        "label_sets": taxonomy["label_sets"],
        "flags": list(SCORING_RULES.keys()),
    }


def _normalize_catalog_payload(payload: ScamTypeCatalogRequest) -> dict[str, Any]:
    normalized_labels: list[str] = []
    seen: set[str] = set()
    for raw_label in payload.labels:
        label = raw_label.strip()
        if not label or label in seen:
            continue
        seen.add(label)
        normalized_labels.append(label)

    return {
        "name": payload.name.strip(),
        "description": (payload.description or "").strip(),
        "labels": normalized_labels,
    }


def _require_db() -> None:
    if not repository.database_configured():
        raise EnvironmentError(
            "DB 기능을 사용하려면 SCAMGUARDIAN_DATABASE_URL(Postgres) 또는 "
            "SCAMGUARDIAN_SQLITE_PATH(SQLite)가 설정되어야 합니다."
        )


def _persist_run(
    pipeline: ScamGuardianPipeline,
    payload: AnalyzeRequest,
    source: str,
    report_dict: dict[str, Any],
) -> str | None:
    if not repository.persistence_enabled():
        return None

    transcript_text = (
        pipeline.last_transcript_result.text if pipeline.last_transcript_result is not None else source
    )
    metadata = {
        "source_type": (
            pipeline.last_transcript_result.source_type
            if pipeline.last_transcript_result is not None
            else "text"
        ),
        "steps": [
            {
                "name": step.name,
                "duration_ms": step.duration_ms,
                "detail": step.detail,
            }
            for step in pipeline.steps
        ],
        "rag_context": report_dict.get("rag_context"),
    }

    run_id = repository.save_analysis_run(
        input_source=source,
        whisper_model=payload.whisper_model,
        skip_verification=payload.skip_verification,
        use_llm=payload.use_llm,
        use_rag=payload.use_rag,
        transcript_text=transcript_text,
        classification_scanner={
            "scam_type": report_dict.get("scam_type", ""),
            "confidence": report_dict.get("classification_confidence", 0.0),
            "is_uncertain": report_dict.get("is_uncertain", False),
        },
        entities_predicted=report_dict.get("entities", []),
        verification_results=pipeline.last_report.all_verifications if pipeline.last_report else [],
        triggered_flags_predicted=report_dict.get("triggered_flags", []),
        total_score_predicted=report_dict.get("total_score", 0),
        risk_level_predicted=report_dict.get("risk_level", ""),
        llm_assessment=report_dict.get("llm_assessment"),
        metadata=metadata,
    )

    try:
        embedding = rag.compute_transcript_embedding(transcript_text)
        repository.save_transcript_embedding(run_id, embedding, rag.embedding_model_name())
    except Exception:
        # 분석 결과 저장은 유지하고, 임베딩 저장 실패만 조용히 건너뛴다.
        pass

    return run_id


def _run_pipeline(payload: AnalyzeRequest) -> dict:
    source = _resolve_source(payload)
    if not source:
        raise ValueError("분석할 텍스트 또는 URL을 입력해주세요.")

    pipeline = ScamGuardianPipeline(whisper_model=payload.whisper_model)
    report = pipeline.analyze(
        source,
        skip_verification=payload.skip_verification,
        use_llm=payload.use_llm,
        use_rag=payload.use_rag,
    )
    report_dict = report.to_dict()
    # 프론트에서 "전체 전사"를 화면에 그대로 보여줄 수 있게 원문 텍스트도 함께 내려준다.
    report_dict["transcript_text"] = (
        pipeline.last_transcript_result.text if pipeline.last_transcript_result is not None else ""
    )
    run_id = _persist_run(pipeline, payload, source, report_dict)
    if run_id:
        report_dict["analysis_run_id"] = run_id
    return report_dict


app = FastAPI(
    title="ScamGuardian API",
    version="0.1.0",
    description="ScamGuardian v2 파이프라인을 웹에서 호출하기 위한 API",
)

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "SCAMGUARDIAN_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    if repository.database_configured():
        repository.init_db()


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(payload: AnalyzeRequest) -> dict:
    try:
        return await asyncio.to_thread(_run_pipeline, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/analyze-upload")
async def analyze_upload(
    file: UploadFile = File(...),
    whisper_model: str = Form("medium"),
    skip_verification: bool = Form(True),
    use_llm: bool = Form(False),
    use_rag: bool = Form(False),
) -> dict:
    """
    영상/음성 파일을 업로드 받아 로컬 파일로 저장한 뒤 파이프라인을 수행한다.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="업로드된 파일 이름이 비어 있습니다.")

    suffix = Path(file.filename).suffix
    upload_dir = Path(".scamguardian") / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    tmp_handle = tempfile.NamedTemporaryFile(
        mode="wb",
        delete=False,
        dir=str(upload_dir),
        prefix="upload_",
        suffix=suffix,
    )
    tmp_path = Path(tmp_handle.name)
    wav_path = tmp_path.with_suffix(".wav")
    try:
        with tmp_handle:
            if file.file is None:
                raise HTTPException(status_code=400, detail="업로드된 파일 본문을 읽을 수 없습니다.")
            shutil.copyfileobj(file.file, tmp_handle)

        if tmp_path.stat().st_size == 0:
            raise HTTPException(status_code=400, detail="업로드된 파일이 비어 있습니다(0 bytes).")

        # Whisper 디코딩 호환성을 위해 먼저 wav(16k mono)로 추출한다.
        # 영상 컨테이너/코덱에 따라 whisper.load_audio가 0-length로 읽히는 케이스를 방지한다.
        extract = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(tmp_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "wav",
                str(wav_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if extract.returncode != 0 or not wav_path.exists() or wav_path.stat().st_size == 0:
            raise HTTPException(
                status_code=400,
                detail="업로드된 파일에서 오디오를 추출하지 못했습니다. 다른 파일(코덱)로 시도해주세요.",
            )

        payload = AnalyzeRequest(
            source=str(wav_path),
            whisper_model=whisper_model,
            skip_verification=skip_verification,
            use_llm=use_llm,
            use_rag=use_rag,
        )
        return await asyncio.to_thread(_run_pipeline, payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            wav_path.unlink(missing_ok=True)
        except Exception:
            pass


@app.get("/api/admin/runs/next")
async def admin_next_run() -> dict[str, Any]:
    try:
        _require_db()
        run = await asyncio.to_thread(repository.get_next_unannotated_run)
        return {"run": run, "options": _options_payload()}
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/runs/{run_id}")
async def admin_run_detail(run_id: str) -> dict[str, Any]:
    try:
        _require_db()
        detail = await asyncio.to_thread(repository.get_run_detail, run_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="해당 run을 찾을 수 없습니다.")
        detail["options"] = _options_payload()
        return detail
    except HTTPException:
        raise
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/runs/{run_id}/annotations")
async def admin_save_annotation(run_id: str, payload: HumanAnnotationRequest) -> dict[str, Any]:
    try:
        _require_db()
        run = await asyncio.to_thread(repository.get_run_detail, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="해당 run을 찾을 수 없습니다.")

        annotation = await asyncio.to_thread(
            repository.upsert_human_annotation,
            run_id=run_id,
            scam_type_gt=payload.scam_type_gt,
            entities_gt=payload.entities_gt,
            triggered_flags_gt=payload.triggered_flags_gt,
            labeler=payload.labeler,
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


@app.get("/api/admin/metrics")
async def admin_metrics(scam_type: str | None = None) -> dict[str, Any]:
    try:
        _require_db()
        records = await asyncio.to_thread(repository.fetch_annotated_pairs, scam_type)
        metrics = pipeline_eval.evaluate_annotated_runs(records)
        metrics["filters"] = {"scam_type": scam_type}
        return metrics
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/scam-types")
async def admin_scam_types() -> dict[str, Any]:
    try:
        _require_db()
        items = await asyncio.to_thread(repository.list_custom_scam_types)
        return {"items": items, "options": _options_payload()}
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/scam-types")
async def admin_add_scam_type(payload: ScamTypeCatalogRequest) -> dict[str, Any]:
    try:
        _require_db()
        normalized = _normalize_catalog_payload(payload)
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
        return {"ok": True, "item": item, "options": _options_payload()}
    except HTTPException:
        raise
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
