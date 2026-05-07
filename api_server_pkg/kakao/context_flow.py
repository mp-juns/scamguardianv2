"""멀티턴 컨텍스트 수집 흐름 — 첫 입력부터 결과 카드 발행까지.

흐름:
- _kakao_start_context_collection: 첫 입력 → STT 백그라운드 시작 + Claude 첫 질문 동기 응답
- _kakao_handle_context_answer: 사용자 답변 → Claude next_turn → 다음 질문 또는 DONE
- _kakao_force_skip_context: '그냥 분석' / 결과확인 → 컨텍스트 강제 종료
- _handle_done_state: status=done 상태에서 결과확인/대화 도착 → refine 트리거 또는 결과 카드
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import BackgroundTasks

from pipeline import context_chat, kakao_formatter, stt as stt_module

from .. import state
from ..result_token import issue_result_token
from .tasks import (
    _async_maybe_trigger_analyze,
    _kakao_refine_text_task,
    _kakao_stt_only_task,
    _new_job_state,
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
            # 이미 with state.jobs_lock 안 — record_poll 호출하면 같은 lock 재획득 시도해
            # threading.Lock(non-reentrant) 특성상 deadlock. lock-free 버전 사용.
            elapsed, poll_count, _ = state._record_poll_unsafe(job)
            return kakao_formatter.format_refining_in_progress(
                elapsed_sec=elapsed, poll_count=poll_count,
            )
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
    from .commands import _classify_error

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
        elapsed, poll_count, stt_done_now = state.record_poll(user_id)
        return kakao_formatter.format_still_running(
            elapsed_sec=elapsed, poll_count=poll_count, stt_done=stt_done_now,
        )

    state.spawn_bg(_async_maybe_trigger_analyze(user_id))
    elapsed, poll_count, _ = state.record_poll(user_id)
    return kakao_formatter.format_context_done_waiting(
        stt_done=stt_done, elapsed_sec=elapsed, poll_count=poll_count,
    )
