"""잡 상태 관리 + 파이프라인 wrapper + 백그라운드 task 모음.

흐름:
- _kakao_run_pipeline / _kakao_transcribe_only / _kakao_analyze_with_context — 동기 함수, 백그라운드 실행 대상
- _kakao_callback_task — 단발 callback 모드
- _kakao_stt_only_task → _async_maybe_trigger_analyze → _kakao_analyze_only_task — 컨텍스트 수집 모드 백그라운드 체인
- _kakao_refine_text_task — 사용자 답변 보강 후 LLM phase 만 재호출
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import requests as _requests

from db import repository
from pipeline import kakao_formatter, stt as stt_module
from pipeline.runner import ScamGuardianPipeline

from .. import state
from ..common import persist_run
from ..models import AnalyzeRequest
from ..result_token import issue_result_token
from .commands import _classify_error

# 다른 서브모듈(router.py, context_flow.py) 가 import 하는 심볼 — Pylance "private not accessed" 경고 차단.
__all__ = [
    "_new_job_state",
    "_cleanup_expired_jobs",
    "_kakao_run_pipeline",
    "_kakao_transcribe_only",
    "_kakao_analyze_with_context",
    "_kakao_callback_task",
    "_async_maybe_trigger_analyze",
    "_kakao_refine_text_task",
    "_kakao_stt_only_task",
    "_kakao_analyze_only_task",
]


# ──────────────────────────────────
# 잡 상태 helpers
# ──────────────────────────────────


def _new_job_state(
    *,
    source: str,
    input_type: kakao_formatter.InputType,
) -> dict[str, Any]:
    return {
        "status": "running",
        "phase": "collecting_context",
        "result": None,
        "input_type": input_type,
        "source": source,
        "chat_history": [],
        "stt_done": False,
        "stt_result": None,
        "context_done": False,
        "user_context": None,
        "analyzing_started": False,
        "result_ready_announced": False,
        "done_notice_sent": False,
        "refine_started": False,
        "refined": False,
        "started_at": time.time(),
        "finished_at": None,
        "error": None,
    }


def _cleanup_expired_jobs() -> None:
    now = time.time()
    with state.jobs_lock:
        expired = [
            uid for uid, job in state.pending_jobs.items()
            if job["status"] != "running" and (now - (job.get("finished_at") or now)) > state.KAKAO_JOB_TTL
        ]
        for uid in expired:
            del state.pending_jobs[uid]


# ──────────────────────────────────
# 파이프라인 실행 helpers (kakao 전용)
# ──────────────────────────────────


def _kakao_run_pipeline(source: str, use_llm: bool = False) -> dict:
    """파이프라인을 실행하고 report_dict를 반환한다."""
    use_llm = True
    pipeline = ScamGuardianPipeline()
    report = pipeline.analyze(
        source,
        skip_verification=False,
        use_llm=use_llm,
        use_rag=False,
    )
    report_dict = report.to_dict()
    report_dict["transcript_text"] = (
        pipeline.last_transcript_result.text
        if pipeline.last_transcript_result is not None
        else source
    )
    persist_run(
        pipeline,
        AnalyzeRequest(
            source=source,
            skip_verification=False,
            use_llm=True,
            use_rag=False,
        ),
        source,
        report_dict,
    )
    return report_dict


def _kakao_transcribe_only(source: str) -> stt_module.TranscriptResult:
    return stt_module.transcribe(source)


def _kakao_analyze_with_context(
    source: str,
    transcript_result: stt_module.TranscriptResult,
    user_context: dict[str, Any] | None,
) -> dict[str, Any]:
    pipeline = ScamGuardianPipeline()
    report = pipeline.analyze(
        source,
        skip_verification=False,
        use_llm=True,
        use_rag=False,
        precomputed_transcript=transcript_result,
        user_context=user_context,
    )
    report_dict = report.to_dict()
    report_dict["transcript_text"] = (
        pipeline.last_transcript_result.text
        if pipeline.last_transcript_result is not None
        else source
    )
    if user_context:
        report_dict["user_context"] = user_context
    persist_run(
        pipeline,
        AnalyzeRequest(
            source=source,
            skip_verification=False,
            use_llm=True,
            use_rag=False,
        ),
        source,
        report_dict,
        user_context=user_context,
    )
    return report_dict


# ──────────────────────────────────
# 백그라운드 task: STT + 1차 분석 + refine + callback
# ──────────────────────────────────


async def _kakao_callback_task(
    source: str,
    callback_url: str,
    input_type: kakao_formatter.InputType,
    use_llm: bool = True,
) -> None:
    """분석을 백그라운드로 수행한 뒤 카카오 callbackUrl로 결과를 POST한다."""
    log = logging.getLogger("kakao_callback")

    try:
        log.info(
            "callback 분석 시작 (제한 %ds):\n"
            "  type: %s\n"
            "  source: %s\n"
            "  use_llm: %s",
            state.KAKAO_CALLBACK_TIMEOUT, input_type.value, source[:100], use_llm,
        )
        report_dict = await asyncio.wait_for(
            asyncio.to_thread(_kakao_run_pipeline, source, use_llm),
            timeout=state.KAKAO_CALLBACK_TIMEOUT,
        )
        _, _result_url = issue_result_token(
            result=report_dict,
            user_context=None,
            input_type=input_type,
            user_id=None,
        )
        result = kakao_formatter.format_result(report_dict, input_type, result_url=_result_url)
        log.info(
            "callback 검출 완료:\n"
            "  scam_type: %s\n"
            "  detected_signals: %d\n"
            "  transcript_len: %s자",
            report_dict.get("scam_type", "?"),
            len(report_dict.get("detected_signals") or []),
            len(report_dict.get("transcript_text", "")),
        )
    except asyncio.TimeoutError:
        log.warning("callback 분석 타임아웃 (%ds 초과)", state.KAKAO_CALLBACK_TIMEOUT)
        result = kakao_formatter.format_error(
            kakao_formatter.ErrorCode.TIMEOUT,
            detail=f"분석이 {state.KAKAO_CALLBACK_TIMEOUT}초를 초과했습니다. 더 짧은 영상이나 텍스트로 시도해주세요.",
        )
    except Exception as exc:
        log.error("callback 분석 실패: %s", exc, exc_info=True)
        error_code = _classify_error(exc)
        result = kakao_formatter.format_error(error_code, detail=str(exc))

    import json as _json

    def _post():
        try:
            log.info(
                "callback POST 전송:\n"
                "  url: %s\n"
                "  body: %s",
                callback_url[:80],
                _json.dumps(result, ensure_ascii=False)[:500],
            )
            resp = _requests.post(callback_url, json=result, timeout=10)
            log.info("callback POST 완료: status=%s body=%s", resp.status_code, resp.text[:200])
        except Exception as e:
            log.error("callback POST 실패: %s", e)

    await asyncio.to_thread(_post)


async def _async_maybe_trigger_analyze(user_id: str) -> None:
    """STT 가 끝났으면 1차 분석을 곧바로 백그라운드에서 시작."""
    with state.jobs_lock:
        job = state.pending_jobs.get(user_id)
        if job is None:
            return
        if job.get("status") == "error":
            return
        if not job.get("stt_done"):
            return
        if job.get("analyzing_started"):
            return
        job["analyzing_started"] = True
        source = job["source"]
        input_type = job["input_type"]
        transcript = job["stt_result"]

    await _kakao_analyze_only_task(user_id, source, input_type, transcript, None)


async def _kakao_refine_text_task(
    user_id: str,
    transcript_text: str,
    scam_type: str,
    user_context: dict[str, Any],
) -> None:
    """최종 합본 분석: 1차 분석 결과 + 사용자 채팅 답변을 LLM 에 prior 로 주입해 reasoning 보강."""
    from pipeline import llm_assessor

    log = logging.getLogger("kakao_refine")
    log.info("최종 합본 분석 시작: user=%s scam_type=%s", user_id[:12], scam_type)
    try:
        new_unified = await asyncio.to_thread(
            llm_assessor.analyze_unified,
            transcript_text, scam_type, user_context,
        )
        with state.jobs_lock:
            job = state.pending_jobs.get(user_id)
            if job is None:
                return
            if job.get("result"):
                job["result"]["llm_assessment"] = new_unified.assessment.to_dict()
                if new_unified.scam_type_suggestion is not None:
                    new_type = new_unified.scam_type_suggestion.scam_type
                    if new_type and new_type != job["result"].get("scam_type"):
                        job["result"]["scam_type"] = new_type
                        job["result"]["scam_type_reason"] = new_unified.scam_type_suggestion.reason
            job["refined"] = True
            run_id_for_db = (job.get("result") or {}).get("analysis_run_id")
        log.info("최종 합본 분석 완료: user=%s", user_id[:12])
        if run_id_for_db and repository.persistence_enabled():
            try:
                repository.merge_run_metadata(run_id_for_db, {
                    "refined_llm_assessment": new_unified.assessment.to_dict(),
                })
            except Exception as exc:
                log.warning("refine metadata merge 실패: %s", exc)
    except Exception as exc:
        import traceback
        log.error(
            "최종 합본 실패: user=%s err=%s\n%s",
            user_id[:12], exc, traceback.format_exc(),
        )
        with state.jobs_lock:
            job = state.pending_jobs.get(user_id)
            if job is not None:
                job["refined"] = True


async def _kakao_stt_only_task(user_id: str, source: str) -> None:
    """STT 만 백그라운드에서 수행. 끝나면 trigger 체크."""
    log = logging.getLogger("kakao_stt")
    log.info("STT 시작: user=%s source=%s", user_id[:12], source[:80])
    try:
        transcript = await asyncio.wait_for(
            asyncio.to_thread(_kakao_transcribe_only, source),
            timeout=state.KAKAO_POLL_TIMEOUT,
        )
        with state.jobs_lock:
            job = state.pending_jobs.get(user_id)
            if job is None:
                return
            job["stt_done"] = True
            job["stt_result"] = transcript
        log.info("STT 완료: user=%s len=%s", user_id[:12], len(transcript.text))
    except Exception as exc:
        import traceback
        log.error(
            "STT 실패: user=%s err=%s\n%s",
            user_id[:12], exc, traceback.format_exc(),
        )
        with state.jobs_lock:
            job = state.pending_jobs.get(user_id)
            if job is None:
                return
            job["status"] = "error"
            job["phase"] = "error"
            job["error"] = exc
            job["finished_at"] = time.time()
        return

    await _async_maybe_trigger_analyze(user_id)


async def _kakao_analyze_only_task(
    user_id: str,
    source: str,
    input_type: kakao_formatter.InputType,
    transcript: stt_module.TranscriptResult,
    user_context: dict[str, Any] | None,
) -> None:
    """Phase 2-5 만 백그라운드에서 수행. STT 결과 / user_context 사용."""
    log = logging.getLogger("kakao_analyze")
    log.info(
        "분석 시작: user=%s type=%s ctx_turns=%s",
        user_id[:12], input_type.value,
        (user_context or {}).get("turn_count", 0),
    )
    try:
        report_dict = await asyncio.wait_for(
            asyncio.to_thread(
                _kakao_analyze_with_context,
                source, transcript, user_context,
            ),
            timeout=state.KAKAO_POLL_TIMEOUT,
        )
        with state.jobs_lock:
            job = state.pending_jobs.get(user_id)
            if job is None:
                return
            job["status"] = "done"
            job["result"] = report_dict
            job["finished_at"] = time.time()
        log.info(
            "검출 완료(채팅 계속): user=%s signals=%d",
            user_id[:12],
            len(report_dict.get("detected_signals") or []),
        )
    except Exception as exc:
        import traceback
        log.error(
            "분석 실패: user=%s err=%s\n%s",
            user_id[:12], exc, traceback.format_exc(),
        )
        with state.jobs_lock:
            job = state.pending_jobs.get(user_id)
            if job is None:
                return
            job["status"] = "error"
            job["phase"] = "error"
            job["error"] = exc
            job["finished_at"] = time.time()
