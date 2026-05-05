"""카카오 챗봇 webhook + 멀티턴 컨텍스트 수집 흐름.

흐름 요약:
- /webhook/kakao 진입 → 어뷰즈 가드 → 특수 명령(welcome/help/reset/결과확인/스킵)
- 신규 입력 → callback 모드 OR 컨텍스트 수집 모드
- 컨텍스트 수집: STT 백그라운드 + Claude 다음 질문 동기 응답
- 1차 분석은 채팅 도중 자동 시작 → 사용자가 결과확인 누르면 refine + 토큰 발급

테스트 호환을 위해 `_kakao_detect_input`, `_is_system_command`, `_wrap_with_soft_warning`
이름은 underscore prefix 유지.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid as _uuid
from pathlib import Path
from typing import Any

import requests as _requests
from fastapi import APIRouter, BackgroundTasks, Request

from db import repository
from pipeline import context_chat, kakao_formatter, stt as stt_module
from pipeline.runner import ScamGuardianPipeline

from . import state
from .common import persist_run
from .models import AnalyzeRequest
from .result_token import issue_result_token

router = APIRouter()


# ──────────────────────────────────
# URL 분류 + 카카오 입력 감지
# ──────────────────────────────────

_URL_RE = re.compile(r"https?://\S+")
_YOUTUBE_RE = re.compile(r"https?://(www\.)?(youtube\.com|youtu\.be)/")
_IMAGE_URL_RE = re.compile(r"\.(jpg|jpeg|png|webp|gif|bmp)(\?|$)", re.IGNORECASE)
_PDF_URL_RE = re.compile(r"\.pdf(\?|$)", re.IGNORECASE)
# 사기범이 링크로 자주 뿌리는 악성 실행파일 확장자 — 다운로드 후 VT 파일 스캔 강제 라우팅
_EXECUTABLE_URL_RE = re.compile(
    r"\.(apk|exe|dmg|msi|jar|bat|cmd|scr|app|ipa|deb|rpm)(\?|$)", re.IGNORECASE
)


def _classify_url_input(url: str) -> kakao_formatter.InputType:
    """URL 확장자 보고 IMAGE/PDF/FILE/URL 구분."""
    InputType = kakao_formatter.InputType
    if _IMAGE_URL_RE.search(url):
        return InputType.IMAGE
    if _PDF_URL_RE.search(url):
        return InputType.PDF
    # APK/EXE/DMG 등 실행 파일 — VT 파일 스캔이 필수. 일반 웹페이지(URL) 스캔이 아니라 다운로드 후 검사로 강제.
    if _EXECUTABLE_URL_RE.search(url):
        return InputType.FILE
    return InputType.URL


def _kakao_detect_input(
    utterance: str, action_params: dict
) -> tuple[str, kakao_formatter.InputType]:
    """카카오 페이로드에서 분석 대상 소스와 입력 유형을 감지한다.

    Returns: (source, InputType)
    """
    InputType = kakao_formatter.InputType

    # 1) 정해진 키로 들어온 파일/영상/이미지/PDF URL — 카카오 표준 블록 파라미터.
    for key in (
        "image", "picture", "photo",  # 이미지
        "pdf", "document",            # PDF/문서
        "video", "video_url",         # 영상
        "file", "attachment",         # 일반 파일 (확장자 보고 재분류)
    ):
        val = action_params.get(key)
        url = ""
        if isinstance(val, str) and val.startswith("http"):
            url = val
        elif isinstance(val, dict):
            v = val.get("url", "")
            if isinstance(v, str) and v.startswith("http"):
                url = v
        if not url:
            continue
        if key in ("image", "picture", "photo"):
            return url, InputType.IMAGE
        if key in ("pdf", "document"):
            return url, InputType.PDF
        if key in ("video", "video_url"):
            return url, InputType.VIDEO
        # file/attachment — URL 확장자 보고 분기
        kind = _classify_url_input(url)
        if kind in (InputType.IMAGE, InputType.PDF):
            return url, kind
        return url, InputType.FILE

    # 2) 표준 키에 매칭 안 된 경우 — action.params 의 *모든* 값을 훑어서 URL 인 것 중 확장자로 분기.
    for _key, val in action_params.items():
        url = ""
        if isinstance(val, str) and val.startswith("http"):
            url = val
        elif isinstance(val, dict):
            v = val.get("url", "")
            if isinstance(v, str) and v.startswith("http"):
                url = v
        if not url:
            continue
        kind = _classify_url_input(url)
        if kind in (InputType.IMAGE, InputType.PDF):
            return url, kind
        if re.search(r"\.(mp4|mov|webm|mkv|avi)(\?|$)", url, re.IGNORECASE):
            return url, InputType.VIDEO
        return url, InputType.FILE

    # 3) utterance 전체 또는 일부가 URL — 둘 다 첫 매칭 URL 만 사용
    url_match = _URL_RE.search(utterance)
    if url_match:
        url = url_match.group(0)
        return url, _classify_url_input(url)

    # 4) 순수 텍스트
    return utterance, InputType.TEXT


def _kakao_materialize_url(url: str, suffix_hint: str = "") -> str:
    """카카오 CDN 등의 HTTP URL 을 로컬 파일로 다운로드하고 경로 반환."""
    log = logging.getLogger("kakao_dl")

    suffix = suffix_hint
    if not suffix:
        path = url.split("?", 1)[0]
        idx = path.rfind(".")
        if idx > 0 and len(path) - idx <= 6:
            suffix = path[idx:]
    if not suffix:
        suffix = ".bin"

    target_dir = Path(".scamguardian") / "uploads" / "kakao"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{_uuid.uuid4().hex}{suffix}"

    resp = _requests.get(url, stream=True, timeout=30)
    resp.raise_for_status()
    with target.open("wb") as fp:
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            if chunk:
                fp.write(chunk)
    log.info("카카오 미디어 다운로드 완료: %s → %s (%d bytes)",
             url[:80], target.name, target.stat().st_size)
    return str(target)


# ──────────────────────────────────
# 시스템 명령 / 결과확인 / 어뷰즈 안내
# ──────────────────────────────────

# 사용자 발화 중 "그냥 분석 결과만 보내줘" 류로 컨텍스트 수집을 강제 종료할 신호
_KAKAO_SKIP_PHRASES = {
    "그냥 분석결과 보내줘",
    "그냥 분석",
    "그만 묻고 분석",
    "건너뛰기",
    "스킵",
    "skip",
}

_RESULT_REQUEST_EXACT = {
    "결과확인", "결과 확인", "결과", "확인",
}
_RESULT_REQUEST_SUBSTRINGS = (
    "결과확인", "결과 확인",
    "결과 알려", "결과알려", "결과 좀", "결과좀",
    "결과 보여", "결과보여", "결과 받", "결과받",
    "결과 봐", "결과봐", "결과 줘", "결과줘",
    "분석 다됐", "분석다됐", "분석 됐어", "분석됐어",
    "분석 끝", "분석끝", "분석 결과", "분석결과",
    "다 됐어", "다됐어", "다 끝났",
)


def _is_result_request(text: str) -> bool:
    """사용자 발화가 결과 요청인지 판별. '결과확인' 외에 자연 표현도 폭넓게 인식."""
    s = (text or "").strip()
    if not s:
        return False
    if s in _RESULT_REQUEST_EXACT:
        return True
    return any(p in s for p in _RESULT_REQUEST_SUBSTRINGS)


# 시스템 명령어 — 짧지만 분석 의도가 분명하므로 어뷰즈 소프트 트래커에서 제외해야 한다.
# (결과확인 4자, 사용법 3자 등이 SOFT_LEN_THRESHOLD=10 미만이라 위반으로 잘못 카운트되던 버그 방지)
_SYSTEM_COMMAND_EXACT = {
    "사용법", "도움말", "help", "?",
    "분석 초기화", "초기화", "리셋", "reset",
}


def _is_system_command(text: str) -> bool:
    """결과확인/사용법/초기화/스킵 같은 시스템 명령어인지 — 어뷰즈 트래커 우회용."""
    s = (text or "").strip()
    if not s:
        return False
    if s in _SYSTEM_COMMAND_EXACT:
        return True
    if s in _KAKAO_SKIP_PHRASES:
        return True
    return _is_result_request(s)


def _wrap_with_soft_warning(response: dict, info: dict | None) -> dict:
    """짧은 메시지 누적 위반 시 응답 최상단에 경고 simpleText 부착.

    첫 번째(count=1) 는 무시 — 정상 인사로 통과시킴.
    두 번째(count>=2) 부터 경고 prepend.
    """
    if not info or info.get("count", 0) < 2 or info.get("blocked"):
        return response
    from platform_layer import abuse_guard as _ag
    count = info["count"]
    limit = _ag.VIOLATION_WARN_LIMIT
    warn = {
        "simpleText": {
            "text": (
                f"⚠️ 짧은 메시지가 반복되고 있어요 ({count}/{limit}).\n"
                "분석할 의심 메시지·URL·문서를 보내주세요. 누적 시 일시 차단됩니다."
            )
        }
    }
    response.setdefault("template", {}).setdefault("outputs", []).insert(0, warn)
    return response


def _classify_error(exc: Exception) -> kakao_formatter.ErrorCode:
    """예외 종류에 따라 적절한 ErrorCode를 반환한다."""
    EC = kakao_formatter.ErrorCode
    msg = str(exc).lower()
    if "api" in msg and ("credit" in msg or "quota" in msg or "limit" in msg):
        return EC.API_CREDIT
    if "connection" in msg or "connect" in msg or "unreachable" in msg:
        return EC.SERVER_DOWN
    if "stt" in msg or "whisper" in msg or "audio" in msg or "transcri" in msg:
        return EC.STT_FAIL
    if "timeout" in msg or "timed out" in msg:
        return EC.TIMEOUT
    if "memory" in msg or "ollama" in msg:
        return EC.LLM_UNAVAILABLE
    if "empty" in msg or "비어" in msg:
        return EC.EMPTY_INPUT
    return EC.UNKNOWN


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
    input_type: kakao_formatter.InputType,
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
# 백그라운드 task: STT + 1차 분석 + refine
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
            "callback 분석 완료:\n"
            "  scam_type: %s\n"
            "  risk: %s/100 (%s)\n"
            "  transcript_len: %s자",
            report_dict.get("scam_type", "?"),
            report_dict.get("total_score", "?"),
            report_dict.get("risk_level", "?"),
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
                source, transcript, user_context, input_type,
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
            "분석 완료(채팅 계속): user=%s risk=%s/100 (%s)",
            user_id[:12],
            report_dict.get("total_score", "?"),
            report_dict.get("risk_level", "?"),
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


# ──────────────────────────────────
# 컨텍스트 수집 흐름
# ──────────────────────────────────


async def _kakao_start_context_collection(
    user_id: str,
    source: str,
    input_type: kakao_formatter.InputType,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """첫 입력 (TEXT/URL/VIDEO/FILE) 수신 → STT 시작 + 컨텍스트 첫 질문 응답."""
    log = logging.getLogger("kakao_ctx")

    with state.jobs_lock:
        state.pending_jobs[user_id] = _new_job_state(source=source, input_type=input_type)

    if input_type == kakao_formatter.InputType.TEXT:
        try:
            transcript = stt_module.transcribe(source)
            with state.jobs_lock:
                job = state.pending_jobs.get(user_id)
                if job is not None:
                    job["stt_done"] = True
                    job["stt_result"] = transcript
            state.spawn_bg(_async_maybe_trigger_analyze(user_id))
        except Exception as exc:
            log.error("TEXT passthrough 실패: %s", exc)
            with state.jobs_lock:
                job = state.pending_jobs.get(user_id)
                if job is not None:
                    job["status"] = "error"
                    job["phase"] = "error"
                    job["error"] = exc
    else:
        background_tasks.add_task(_kakao_stt_only_task, user_id, source)

    with state.jobs_lock:
        job = state.pending_jobs.get(user_id)
        first_transcript_text: str | None = None
        if job is not None and job.get("stt_result") is not None:
            first_transcript_text = job["stt_result"].text
    try:
        first_turn = await asyncio.to_thread(
            context_chat.next_turn, input_type.value, [], first_transcript_text,
        )
    except Exception as exc:
        log.error("첫 질문 생성 실패: %s", exc, exc_info=True)
        with state.jobs_lock:
            job = state.pending_jobs.get(user_id)
            if job is not None:
                job["context_done"] = True
                job["user_context"] = None
        state.spawn_bg(_async_maybe_trigger_analyze(user_id))
        return kakao_formatter.format_context_done_waiting(stt_done=False)

    with state.jobs_lock:
        job = state.pending_jobs.get(user_id)
        if job is None:
            return kakao_formatter.format_error(
                kakao_formatter.ErrorCode.UNKNOWN, "세션이 사라졌습니다.",
            )
        job["chat_history"].append(
            context_chat.ContextTurn(role="bot", message=first_turn.message)
        )
        if first_turn.is_done:
            job["context_done"] = True
            job["user_context"] = context_chat.summarize_for_pipeline(job["chat_history"])
            stt_done = job["stt_done"]
        else:
            stt_done = None

    if first_turn.is_done:
        state.spawn_bg(_async_maybe_trigger_analyze(user_id))
        return kakao_formatter.format_context_done_waiting(stt_done=bool(stt_done))

    return kakao_formatter.format_question(
        first_turn.message, is_first_turn=True, input_type=input_type,
    )


async def _kakao_handle_context_answer(
    user_id: str,
    utterance: str,
) -> dict[str, Any]:
    """수집 중 사용자 답변 도착 → Claude 다음 액션 결정 → 응답."""
    log = logging.getLogger("kakao_ctx")

    with state.jobs_lock:
        job = state.pending_jobs.get(user_id)
        if job is None:
            return kakao_formatter.format_no_job()
        input_type = job["input_type"]
        user_turn = context_chat.ContextTurn(
            role="user",
            message=utterance[: context_chat.USER_ANSWER_MAX_CHARS],
        )
        job["chat_history"].append(user_turn)
        history = list(job["chat_history"])
        transcript_text = (
            job["stt_result"].text if job.get("stt_result") is not None else None
        )

    try:
        next_action = await asyncio.to_thread(
            context_chat.next_turn, input_type.value, history, transcript_text,
        )
    except Exception as exc:
        log.error("Claude next_turn 실패 → DONE 폴백: %s", exc, exc_info=True)
        next_action = context_chat.NextAction(
            action="DONE",
            message="알려주신 내용 잘 받았어요. 분석 결과 곧 알려드릴게요.",
            reasoning=f"claude_error: {exc}",
        )

    notify_done = False
    with state.jobs_lock:
        job = state.pending_jobs.get(user_id)
        if job is None:
            return kakao_formatter.format_no_job()
        if (
            job.get("status") == "done"
            and not job.get("done_notice_sent")
            and not next_action.is_done
        ):
            notify_done = True
            job["done_notice_sent"] = True
            next_action = context_chat.NextAction(
                action="ASK",
                message=(
                    next_action.message
                    + "\n\n💡 참고로 분석은 끝났어요. "
                    + "더 알려주실 게 있으면 답해주시고, "
                    + "결과를 보시려면 '결과확인'을 누르거나 '결과 알려줘'라고 해주세요."
                ),
                reasoning=next_action.reasoning,
            )
        job["chat_history"].append(
            context_chat.ContextTurn(role="bot", message=next_action.message)
        )
        if next_action.is_done:
            job["context_done"] = True
            job["user_context"] = context_chat.summarize_for_pipeline(job["chat_history"])
            stt_done = job["stt_done"]
        else:
            stt_done = None

    if next_action.is_done:
        state.spawn_bg(_async_maybe_trigger_analyze(user_id))
        return kakao_formatter.format_context_done_waiting(stt_done=bool(stt_done))

    if notify_done:
        log.info("→ 분석 완료 안내 동봉: user=%s", user_id[:12])

    return kakao_formatter.format_question(
        next_action.message, is_first_turn=False, input_type=input_type,
    )


def _user_ctx_for_display(job: dict[str, Any]) -> dict[str, Any] | None:
    """결과 카드에 보여줄 user_context — 우선 저장된 값, 없으면 chat_history 에서 즉석 요약."""
    ctx = job.get("user_context")
    if ctx is not None:
        return ctx
    history = job.get("chat_history") or []
    if not history:
        return None
    return context_chat.summarize_for_pipeline(history)


async def _handle_done_state(
    user_id: str,
    background_tasks: BackgroundTasks,
    utterance: str | None = None,
) -> dict[str, Any]:
    """status=done 상태에서 사용자 메시지/결과확인 도착 시 처리."""
    log = logging.getLogger("kakao_done")

    with state.jobs_lock:
        job = state.pending_jobs.get(user_id)
        if job is None:
            return kakao_formatter.format_no_job()

        if (
            utterance
            and not job.get("result_ready_announced", False)
        ):
            job["chat_history"].append(
                context_chat.ContextTurn(
                    role="user",
                    message=utterance[: context_chat.USER_ANSWER_MAX_CHARS],
                )
            )

        announced = job.get("result_ready_announced", False)
        refine_started = job.get("refine_started", False)
        refined = job.get("refined", False)
        has_answers = any(
            getattr(t, "role", None) == "user"
            for t in job.get("chat_history", [])
        )

        if not announced:
            job["result_ready_announced"] = True
            job["phase"] = "result_requested"
            if has_answers and not refine_started:
                job["refine_started"] = True
                transcript_text = (
                    job["stt_result"].text
                    if job.get("stt_result") is not None
                    else job.get("source", "")
                )
                user_ctx = _user_ctx_for_display(job) or {}
                scam_type = job["result"].get("scam_type", "")
                trigger_refine = True
            else:
                _, url = issue_result_token(
                    result=job["result"],
                    user_context=_user_ctx_for_display(job),
                    input_type=job["input_type"],
                    user_id=user_id,
                    chat_history=job.get("chat_history") or [],
                )
                result = kakao_formatter.format_result(
                    job["result"], job["input_type"],
                    user_context=_user_ctx_for_display(job),
                    result_url=url,
                )
                state.pending_jobs.pop(user_id, None)
                return result
        elif refine_started and not refined:
            return kakao_formatter.format_refining_in_progress()
        elif refined:
            _, url = issue_result_token(
                result=job["result"],
                user_context=_user_ctx_for_display(job),
                input_type=job["input_type"],
                user_id=user_id,
                chat_history=job.get("chat_history") or [],
            )
            result = kakao_formatter.format_result(
                job["result"], job["input_type"],
                user_context=_user_ctx_for_display(job),
                result_url=url,
            )
            state.pending_jobs.pop(user_id, None)
            return result
        else:
            _, url = issue_result_token(
                result=job["result"],
                user_context=_user_ctx_for_display(job),
                input_type=job["input_type"],
                user_id=user_id,
                chat_history=job.get("chat_history") or [],
            )
            result = kakao_formatter.format_result(
                job["result"], job["input_type"],
                user_context=_user_ctx_for_display(job),
                result_url=url,
            )
            state.pending_jobs.pop(user_id, None)
            return result

    log.info("→ 결과 준비 완료 → announce + refine 트리거: user=%s", user_id[:12])
    background_tasks.add_task(
        _kakao_refine_text_task,
        user_id, transcript_text, scam_type, user_ctx,
    )
    return kakao_formatter.format_result_ready_announce(has_refine=True)


async def _kakao_force_skip_context(user_id: str) -> dict[str, Any]:
    """사용자가 '그냥 분석결과 보내줘' 같은 신호 → 컨텍스트 강제 종료."""
    with state.jobs_lock:
        job = state.pending_jobs.get(user_id)
        if job is None:
            return kakao_formatter.format_no_job()
        if job.get("status") == "error":
            del state.pending_jobs[user_id]
            error_code = _classify_error(job.get("error") or Exception())
            return kakao_formatter.format_error(error_code)
        if job.get("status") == "done":
            _, url = issue_result_token(
                result=job["result"],
                user_context=_user_ctx_for_display(job),
                input_type=job["input_type"],
                user_id=user_id,
                chat_history=job.get("chat_history") or [],
            )
            result = kakao_formatter.format_result(
                job["result"], job["input_type"],
                user_context=_user_ctx_for_display(job),
                result_url=url,
            )
            del state.pending_jobs[user_id]
            return result
        already_analyzing = job.get("analyzing_started", False)
        if job.get("phase") == "collecting_context":
            job["context_done"] = True
            if job.get("user_context") is None:
                job["user_context"] = context_chat.summarize_for_pipeline(
                    job["chat_history"]
                )
            stt_done = job["stt_done"]
        else:
            stt_done = job["stt_done"]

    if already_analyzing:
        return kakao_formatter.format_still_running()

    state.spawn_bg(_async_maybe_trigger_analyze(user_id))
    return kakao_formatter.format_context_done_waiting(stt_done=stt_done)


# ──────────────────────────────────
# /webhook/kakao 엔드포인트
# ──────────────────────────────────


@router.post("/webhook/kakao")
async def kakao_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    """카카오 오픈빌더 Skill Webhook 엔드포인트.

    분기 흐름:
    - 도움말 / 결과확인 / 스킵 같은 특수 명령 우선 처리
    - 진행 중 job 이 있으면 답변 또는 busy 처리 (멀티턴 컨텍스트 수집)
    - 신규 입력:
      - callbackUrl 있음 → 단발 callback 모드 (컨텍스트 수집 없음)
      - URL/영상 + callback 없음 → 컨텍스트 수집 + 병렬 STT 시작
      - 텍스트 → 즉시 동기 분석
    """
    log = logging.getLogger("kakao_webhook")
    EC = kakao_formatter.ErrorCode
    InputType = kakao_formatter.InputType

    try:
        body = await request.json()
    except Exception:
        return kakao_formatter.format_error(EC.PARSE_ERROR)

    log.info(
        "kakao webhook 수신:\n"
        "  utterance: %s\n"
        "  callbackUrl: %s\n"
        "  action.params: %s",
        (body.get("userRequest", {}).get("utterance") or "")[:100],
        (body.get("userRequest", {}).get("callbackUrl") or "")[:80],
        str(body.get("action", {}).get("params", {}))[:200],
    )

    user_request = body.get("userRequest", {})
    utterance: str = (user_request.get("utterance") or "").strip()
    callback_url: str = (user_request.get("callbackUrl") or "").strip()
    action_params: dict = body.get("action", {}).get("params", {})
    user_id: str = (user_request.get("user", {}).get("id") or "").strip()

    # ── 어뷰즈 누적 차단 우선 검사 ──
    soft_warn_info: dict | None = None
    if user_id:
        from platform_layer import abuse_guard as _ag
        blocked, remaining = _ag.block_status(user_id)
        if blocked:
            log.warning("→ blocked user %s (남은 %ds)", user_id[:12], remaining)
            with state.jobs_lock:
                state.pending_jobs.pop(user_id, None)
            return kakao_formatter.format_abuse_blocked(remaining)
        has_attachment = any(
            action_params.get(k)
            for k in ("image", "picture", "photo", "pdf", "document", "video", "video_url", "file", "attachment")
        )
        if utterance and not has_attachment and not _is_system_command(utterance):
            soft_warn_info = _ag.track_short_message(user_id, utterance)
            if soft_warn_info and soft_warn_info.get("blocked"):
                log.warning("→ soft block triggered user %s", user_id[:12])
                with state.jobs_lock:
                    state.pending_jobs.pop(user_id, None)
                return kakao_formatter.format_abuse_blocked(
                    soft_warn_info.get("block_remaining_sec") or _ag.BLOCK_DURATION_SEC
                )

    # ── 특수 명령: 빈 메시지 = welcome (즉답) ──
    if not utterance:
        log.info("→ welcome 응답 반환 (빈 메시지)")
        return kakao_formatter.format_welcome()
    if utterance in ("사용법", "도움말", "help", "?"):
        log.info("→ 사용법 응답 반환 (특수 명령)")
        return kakao_formatter.format_help()

    if utterance in ("분석 초기화", "초기화", "리셋", "reset"):
        had_job = False
        if user_id:
            with state.jobs_lock:
                had_job = user_id in state.pending_jobs
                state.pending_jobs.pop(user_id, None)
        log.info(
            "→ 분석 초기화: user=%s had_job=%s",
            user_id[:12] if user_id else "?", had_job,
        )
        return kakao_formatter.format_reset(had_active_job=had_job)

    if _is_result_request(utterance):
        _cleanup_expired_jobs()
        with state.jobs_lock:
            job = state.pending_jobs.get(user_id)
        log.info(
            "→ 결과확인 요청: user=%s status=%s phase=%s",
            user_id[:12] if user_id else "?",
            job and job.get("status"),
            job and job.get("phase"),
        )
        if job is None:
            return kakao_formatter.format_no_job()
        if job.get("status") == "error":
            with state.jobs_lock:
                state.pending_jobs.pop(user_id, None)
            error_code = _classify_error(job.get("error") or Exception())
            return kakao_formatter.format_error(error_code)
        if job.get("status") == "done":
            return await _handle_done_state(user_id, background_tasks)
        if job.get("phase") == "collecting_context":
            log.info("→ 결과확인 = 컨텍스트 강제 종료 신호로 해석")
            return await _kakao_force_skip_context(user_id)
        return kakao_formatter.format_still_running()

    if utterance in _KAKAO_SKIP_PHRASES and user_id:
        log.info("→ 스킵 신호 수신: user=%s", user_id[:12])
        with state.jobs_lock:
            has_job = user_id in state.pending_jobs
        if has_job:
            return await _kakao_force_skip_context(user_id)
        return kakao_formatter.format_no_job()

    source, input_type = _kakao_detect_input(utterance, action_params)
    is_heavy = input_type in (
        InputType.URL, InputType.VIDEO, InputType.FILE, InputType.IMAGE, InputType.PDF,
    )
    log.info(
        "입력 감지: type=%s, heavy=%s, source=%s",
        input_type.value, is_heavy, source[:80],
    )

    # ── v3 Phase 1: 이미지/PDF/실행파일 → 로컬 다운로드 ──
    if input_type in (InputType.IMAGE, InputType.PDF, InputType.FILE) and source.startswith("http"):
        try:
            if input_type == InputType.PDF:
                suffix_hint = ".pdf"
            elif input_type == InputType.FILE:
                m = _EXECUTABLE_URL_RE.search(source)
                suffix_hint = f".{m.group(1).lower()}" if m else ""
            else:
                suffix_hint = ""
            local_path = await asyncio.to_thread(
                _kakao_materialize_url, source, suffix_hint,
            )
            log.info(
                "→ 카카오 미디어 로컬 저장: %s → %s",
                input_type.value, Path(local_path).name,
            )
            source = local_path
        except Exception as exc:
            log.error("카카오 미디어 다운로드 실패: %s", exc, exc_info=True)
            return kakao_formatter.format_error(
                kakao_formatter.ErrorCode.UNKNOWN,
                f"파일 다운로드 실패: {exc}",
            )

    # ── 진행 중 job 처리 ──
    if user_id and not callback_url:
        with state.jobs_lock:
            job = state.pending_jobs.get(user_id)
        if job is not None:
            phase = job.get("phase")
            status = job.get("status")
            if status == "error":
                with state.jobs_lock:
                    state.pending_jobs.pop(user_id, None)
                error_code = _classify_error(job.get("error") or Exception())
                return kakao_formatter.format_error(error_code)
            if status == "done":
                if phase == "collecting_context":
                    log.info(
                        "→ 분석 완료 후에도 채팅 계속: user=%s (사용자가 결과확인 안 함)",
                        user_id[:12],
                    )
                    return await _kakao_handle_context_answer(user_id, utterance)
                return await _handle_done_state(user_id, background_tasks, utterance=utterance)
            if is_heavy:
                log.info("→ busy: 진행 중 job 있음, 새 영상 거절")
                return kakao_formatter.format_busy()
            if phase == "collecting_context":
                log.info("→ 컨텍스트 답변 처리: user=%s", user_id[:12])
                return await _kakao_handle_context_answer(user_id, utterance)
            return kakao_formatter.format_still_running()

    # ── callbackUrl 있으면: 단발 callback 모드 ──
    if callback_url:
        log.info(
            "→ callback 모드: 백그라운드 분석 시작, callbackUrl=%s",
            callback_url[:80],
        )
        msg = kakao_formatter.format_analyzing(input_type)
        background_tasks.add_task(
            _kakao_callback_task, source, callback_url, input_type, True,
        )
        resp = {
            "version": "2.0",
            "useCallback": True,
            "data": {"text": msg},
        }
        log.info("→ 즉시 응답: %s", str(resp)[:200])
        return resp

    # ── callbackUrl 없음, 무거운 입력 → 컨텍스트 수집 시작 ──
    if is_heavy:
        if not user_id:
            log.warning("→ user_id 없음, 컨텍스트 수집 불가 → CALLBACK_REQUIRED")
            return kakao_formatter.format_error(EC.CALLBACK_REQUIRED)
        log.info(
            "→ 컨텍스트 수집 모드 시작: user=%s type=%s",
            user_id[:12], input_type.value,
        )
        return await _kakao_start_context_collection(
            user_id, source, input_type, background_tasks,
        )

    # ── 어뷰즈 가드 (TEXT) ──
    if user_id:
        from platform_layer import abuse_guard as _ag
        rej = _ag.guard(source, user_id=user_id)
        if rej is not None:
            log.warning(
                "→ abuse guard reject user=%s code=%s (%s)",
                user_id[:12], rej.code, rej.detail,
            )
            if rej.code == "BLOCKED":
                with state.jobs_lock:
                    state.pending_jobs.pop(user_id, None)
                remaining = 3600
                try:
                    remaining = int(rej.detail.split("=")[-1].split("s")[0])
                except Exception:
                    pass
                return kakao_formatter.format_abuse_blocked(remaining)
            warns_left = _ag.VIOLATION_WARN_LIMIT - _ag.violation_count(user_id)
            return kakao_formatter.format_abuse_warning(rej.message, max(0, warns_left))

    # ── 텍스트: 의도 분류 ──
    if soft_warn_info and soft_warn_info.get("count", 0) >= 2:
        log.info(
            "→ Haiku skip (soft warn count=%d) → welcome 직접 반환",
            soft_warn_info["count"],
        )
        return _wrap_with_soft_warning(kakao_formatter.format_welcome(), soft_warn_info)

    intent = await asyncio.to_thread(context_chat.classify_intent, source)
    log.info("→ TEXT intent: %s", intent)

    if intent == context_chat.INTENT_GREETING:
        return _wrap_with_soft_warning(kakao_formatter.format_welcome(), soft_warn_info)
    if intent == context_chat.INTENT_HELP:
        return _wrap_with_soft_warning(kakao_formatter.format_help(), soft_warn_info)
    if intent == context_chat.INTENT_ANALYZE_NO_CONTENT:
        return _wrap_with_soft_warning(
            kakao_formatter.format_ask_for_content(reason="analyze"), soft_warn_info,
        )
    if intent == context_chat.INTENT_CHAT:
        return _wrap_with_soft_warning(
            kakao_formatter.format_ask_for_content(reason="chat"), soft_warn_info,
        )

    # CONTENT (default) — 본문 들어왔다 → 컨텍스트 수집 모드 시작
    if not user_id:
        log.warning("→ TEXT user_id 없음, 컨텍스트 수집 불가 → CALLBACK_REQUIRED")
        return kakao_formatter.format_error(EC.CALLBACK_REQUIRED)
    log.info(
        "→ TEXT 컨텍스트 수집 모드 시작: user=%s len=%s",
        user_id[:12], len(source),
    )
    return await _kakao_start_context_collection(
        user_id, source, input_type, background_tasks,
    )
