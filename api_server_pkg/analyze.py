"""/api/analyze 와 /api/analyze-upload — 외부 API 클라이언트용."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from db import repository

from .common import resolve_source, run_pipeline
from .models import AnalyzeRequest

router = APIRouter()


@router.post("/api/analyze")
async def analyze(payload: AnalyzeRequest, request: Request) -> dict:
    log = logging.getLogger("api_analyze")
    source = resolve_source(payload)
    log.info(
        "/api/analyze 요청:\n"
        "  source: %s\n"
        "  whisper_model: %s, skip_verification: %s, use_llm: true(강제), use_rag: %s",
        source[:100], payload.whisper_model, payload.skip_verification,
        payload.use_rag,
    )
    # 어뷰즈 가드 — 텍스트 입력에 한해 외부 API 호출 전 차단
    if payload.text and not payload.source:
        from platform_layer import abuse_guard as _ag
        key_id = getattr(request.state, "api_key_id", None)
        user_id = request.headers.get("x-user-id", "").strip() or None
        rej = _ag.guard(payload.text, key_id=key_id, user_id=user_id)
        if rej is not None:
            status = 423 if rej.code == "BLOCKED" else 400
            raise HTTPException(
                status_code=status,
                detail={"code": rej.code, "message": rej.message, "detail": rej.detail},
            )
    try:
        result = await asyncio.to_thread(run_pipeline, payload)
        log.info(
            "/api/analyze 완료: scam_type=%s, risk=%s/100 (%s)",
            result.get("scam_type", "?"),
            result.get("total_score", "?"),
            result.get("risk_level", "?"),
        )
        return result
    except ValueError as exc:
        log.warning("/api/analyze 입력 오류: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EnvironmentError as exc:
        log.warning("/api/analyze 환경 오류: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.error("/api/analyze 서버 오류: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/analyze-upload")
async def analyze_upload(
    file: UploadFile = File(...),
    whisper_model: str = Form("medium"),
    skip_verification: bool = Form(True),
    use_llm: bool = Form(True),
    use_rag: bool = Form(False),
) -> dict:
    """영상/음성 파일을 업로드 받아 로컬 파일로 저장한 뒤 파이프라인을 수행한다."""
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
    media_persisted = False
    try:
        with tmp_handle:
            if file.file is None:
                raise HTTPException(status_code=400, detail="업로드된 파일 본문을 읽을 수 없습니다.")
            shutil.copyfileobj(file.file, tmp_handle)

        if tmp_path.stat().st_size == 0:
            raise HTTPException(status_code=400, detail="업로드된 파일이 비어 있습니다(0 bytes).")

        # v3 Phase 1: 이미지·PDF 는 vision OCR 라우팅 — ffmpeg 단계 skip
        from pipeline import vision as _vision_mod
        is_visual = _vision_mod.supported(tmp_path)
        if is_visual:
            payload = AnalyzeRequest(
                source=str(tmp_path),
                whisper_model=whisper_model,
                skip_verification=skip_verification,
                use_llm=True,
                use_rag=use_rag,
            )
        else:
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
                use_llm=True,
                use_rag=use_rag,
            )
        result = await asyncio.to_thread(run_pipeline, payload)

        run_id = result.get("analysis_run_id") if isinstance(result, dict) else None
        media_persisted = False
        if run_id:
            try:
                target_dir = Path(".scamguardian") / "uploads" / str(run_id)
                target_dir.mkdir(parents=True, exist_ok=True)
                target_path = target_dir / f"source{suffix or ''}"
                shutil.move(str(tmp_path), str(target_path))
                media_persisted = True
                try:
                    repository.merge_run_metadata(run_id, {
                        "media": {
                            "kind": "uploaded_file",
                            "original_filename": file.filename,
                            "stored_path": str(target_path),
                            "size_bytes": target_path.stat().st_size,
                            "suffix": suffix or "",
                        }
                    })
                except Exception as exc:
                    logging.getLogger("upload").warning(
                        "media metadata merge 실패 (run_id=%s): %s", run_id, exc,
                    )
            except Exception as exc:
                logging.getLogger("upload").warning(
                    "원본 업로드 파일 보존 실패 (run_id=%s): %s", run_id, exc,
                )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if not media_persisted:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
        try:
            wav_path.unlink(missing_ok=True)
        except Exception:
            pass
