"""
ScamGuardian v2 — 카카오 오픈빌더 응답 포맷터

ScamReport.to_dict() 결과를 카카오 챗봇 응답 JSON으로 변환한다.
입력 유형(텍스트/URL/영상)에 따라 다른 카드 레이아웃을 제공하고,
에러 상황별로 구체적인 안내 메시지를 출력한다.
https://i.kakao.com/docs/skill-response-format
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pipeline.config import flag_label_ko


# ──────────────────────────────────
# 입력 유형
# ──────────────────────────────────
class InputType(str, Enum):
    TEXT = "text"
    URL = "url"
    VIDEO = "video"
    FILE = "file"


# ──────────────────────────────────
# 에러 코드 → 사용자 친화적 메시지
# ──────────────────────────────────
class ErrorCode(str, Enum):
    UNKNOWN = "unknown"
    API_CREDIT = "api_credit"
    SERVER_DOWN = "server_down"
    STT_FAIL = "stt_fail"
    TIMEOUT = "timeout"
    EMPTY_INPUT = "empty_input"
    INVALID_URL = "invalid_url"
    FILE_TOO_LARGE = "file_too_large"
    LLM_UNAVAILABLE = "llm_unavailable"
    CALLBACK_REQUIRED = "callback_required"
    PARSE_ERROR = "parse_error"


_ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.UNKNOWN: "알 수 없는 오류가 발생했습니다.",
    ErrorCode.API_CREDIT: (
        "🔑 서버의 API 크레딧이 부족합니다!\n"
        "챗봇 관리자에게 알려주세요."
    ),
    ErrorCode.SERVER_DOWN: (
        "🔧 분석 서버에 연결할 수 없습니다.\n"
        "서버가 점검 중이거나 일시적 장애입니다.\n"
        "관리자에게 문의해 주세요."
    ),
    ErrorCode.STT_FAIL: (
        "🎤 음성 인식(STT)에 실패했습니다.\n"
        "영상/음성 파일이 손상되었거나\n"
        "오디오가 포함되지 않은 파일일 수 있습니다."
    ),
    ErrorCode.TIMEOUT: (
        "⏱️ 처리 시간이 초과되었습니다.\n"
        "다시 시도해 주세요."
    ),
    ErrorCode.EMPTY_INPUT: (
        "📝 분석할 내용이 비어 있습니다.\n"
        "의심되는 텍스트, URL, 또는 영상을 보내주세요."
    ),
    ErrorCode.INVALID_URL: (
        "🔗 유효하지 않은 URL입니다.\n"
        "YouTube 링크 또는 영상 URL을 확인해 주세요."
    ),
    ErrorCode.FILE_TOO_LARGE: (
        "📦 파일 크기가 너무 큽니다.\n"
        "100MB 이하의 파일을 보내주세요."
    ),
    ErrorCode.LLM_UNAVAILABLE: (
        "🤖 AI 보조 분석 서비스를 사용할 수 없습니다.\n"
        "기본 분석으로 진행합니다."
    ),
    ErrorCode.CALLBACK_REQUIRED: (
        "⏳ 영상/URL 분석은 시간이 걸립니다.\n"
        "챗봇 관리자가 '콜백 사용' 설정을 켜야 합니다."
    ),
    ErrorCode.PARSE_ERROR: "요청을 파싱할 수 없습니다.",
}


# ──────────────────────────────────
# 위험도별 이모지/텍스트 표현
# ──────────────────────────────────
_RISK_ICON: dict[str, str] = {
    "매우 위험": "🚨",
    "위험": "⚠️",
    "주의": "🔶",
    "안전": "✅",
}

_QUICK_REPLY_HELP = {
    "label": "사용법",
    "action": "message",
    "messageText": "사용법",
}

_QUICK_REPLY_RESET = {
    "label": "분석 초기화",
    "action": "message",
    "messageText": "분석 초기화",
}

_QUICK_REPLY_RESULT_CHECK = {
    "label": "결과확인",
    "action": "message",
    "messageText": "결과확인",
}

# 결과확인 버튼이 우선 노출돼야 하는 phase — 사용자가 결과를 기다리는 상황
_PHASES_WITH_RESULT_CHECK = frozenset({
    "polling",
    "analyzing",
    "busy",
    "collecting_context",
})


def quick_replies(phase: str = "default") -> list[dict[str, str]]:
    """phase 별 퀵 리플라이 반환.

    분석 결과를 기다리는 phase(폴링/refining/대기 등)에서는 결과확인 버튼을 우선 노출한다.
    그 외 phase 에서는 [사용법, 분석 초기화] 두 개만 반환한다.
    """
    if phase in _PHASES_WITH_RESULT_CHECK:
        return [_QUICK_REPLY_RESULT_CHECK, _QUICK_REPLY_HELP, _QUICK_REPLY_RESET]
    return [_QUICK_REPLY_HELP, _QUICK_REPLY_RESET]


def _risk_icon(level: str) -> str:
    return _RISK_ICON.get(level, "❓")


def _entity_lines(entities: list[dict[str, Any]], max_count: int = 6) -> str:
    if not entities:
        return "없음"
    lines = []
    for e in entities[:max_count]:
        lines.append(f"• {e.get('label', '')}: {e.get('text', '')}")
    if len(entities) > max_count:
        lines.append(f"… 외 {len(entities) - max_count}개")
    return "\n".join(lines)


def _flag_lines(flags: list[dict[str, Any]], max_count: int = 4) -> str:
    if not flags:
        return "없음"
    lines = []
    for f in flags[:max_count]:
        delta = f.get("score_delta", 0)
        sign = "+" if delta >= 0 else ""
        flag_key = f.get("flag", "")
        label = flag_label_ko(flag_key) if flag_key else "(이름 없음)"
        lines.append(f"• {label} ({sign}{delta}점)")
    if len(flags) > max_count:
        lines.append(f"… 외 {len(flags) - max_count}개")
    return "\n".join(lines)


def _truncate(text: str, max_len: int = 200) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


# ──────────────────────────────────
# 결과 카드 빌더 (입력 유형별)
# ──────────────────────────────────
def _build_result_card(
    report: dict[str, Any],
    input_type: InputType = InputType.TEXT,
    result_url: str | None = None,
) -> dict[str, Any]:
    level = report.get("risk_level", "알 수 없음")
    score = report.get("total_score", 0)
    scam_type = report.get("scam_type", "미분류")
    confidence = report.get("classification_confidence", 0)
    entities = report.get("entities", [])
    flags = report.get("triggered_flags", [])
    description = report.get("risk_description", "")

    icon = _risk_icon(level)
    confidence_pct = f"{confidence * 100:.0f}%"

    # 입력 유형 표시
    type_labels = {
        InputType.TEXT: "💬 텍스트 분석",
        InputType.URL: "🔗 URL/영상 분석",
        InputType.VIDEO: "🎬 업로드 영상 분석",
        InputType.FILE: "📎 파일 분석",
    }
    type_label = type_labels.get(input_type, "분석")

    title = f"{icon} {level}  |  {score}점"

    body_parts = [f"[분석 방식] {type_label}"]

    # 입력 본문/전사 미리보기 — TEXT 도 포함하여 일관 표시
    transcript = report.get("transcript_text", "")
    if transcript:
        label = "음성 전사" if input_type in (InputType.URL, InputType.VIDEO, InputType.FILE) else "입력 본문"
        body_parts.append(f"[{label}]\n{_truncate(transcript, 150)}")

    # LLM 한 줄 요약이 있으면 우선 노출 — 사용자가 핵심 빠르게 파악 가능
    llm = report.get("llm_assessment") or {}
    summary = str(llm.get("summary", "")).strip()
    if summary:
        body_parts.append(f"[AI 요약]\n{_truncate(summary, 200)}")

    body_parts.extend([
        f"[스캠 유형]\n{scam_type} (신뢰도 {confidence_pct})",
        f"[위험 판정]\n{description}",
        f"[발동 플래그]\n{_flag_lines(flags)}",
        f"[추출 엔티티]\n{_entity_lines(entities)}",
    ])

    body = "\n\n".join(body_parts)

    card: dict[str, Any] = {
        "basicCard": {
            "title": title,
            "description": body,
        }
    }
    if result_url:
        card["basicCard"]["buttons"] = [
            {
                "label": "자세한 결과 보기",
                "action": "webLink",
                "webLinkUrl": result_url,
            }
        ]
    return card


def _build_uncertain_text() -> dict[str, Any]:
    return {
        "simpleText": {
            "text": (
                "⚠️ 분류 신뢰도가 낮아 정확도가 떨어질 수 있습니다.\n"
                "더 자세한 내용을 포함한 텍스트를 다시 입력해 주세요."
            )
        }
    }


# ──────────────────────────────────
# 공개 API
# ──────────────────────────────────
def _build_user_context_block(user_context: dict[str, Any] | None) -> dict[str, Any] | None:
    """결과 카드 뒤에 붙는 '사용자 제공 정보' 블록 — 컨텍스트 있을 때만."""
    if not user_context:
        return None
    qa_pairs = user_context.get("qa_pairs") or []
    if not qa_pairs:
        return None
    lines = ["📝 사용자 제공 정보"]
    for qa in qa_pairs[:4]:
        a = str(qa.get("answer", "")).strip()
        if not a:
            continue
        q = str(qa.get("question", "")).strip()
        if q:
            lines.append(f"• Q: {_truncate(q, 60)}")
            lines.append(f"  A: {_truncate(a, 100)}")
        else:
            lines.append(f"• {_truncate(a, 100)}")
    return {"simpleText": {"text": "\n".join(lines)}}


def format_result(
    report: dict[str, Any],
    input_type: InputType = InputType.TEXT,
    user_context: dict[str, Any] | None = None,
    result_url: str | None = None,
) -> dict[str, Any]:
    """분석 결과를 카카오 응답 JSON으로 변환한다.

    result_url 이 주어지면 카드에 '자세한 결과 보기' webLink 버튼 + 안내 텍스트 추가.
    """
    outputs: list[dict[str, Any]] = [
        _build_result_card(report, input_type, result_url=result_url)
    ]

    user_block = _build_user_context_block(user_context)
    if user_block:
        outputs.append(user_block)

    if result_url:
        outputs.append({
            "simpleText": {
                "text": f"📊 자세한 결과는 1시간 동안 다음 링크에서 보실 수 있어요.\n{result_url}"
            }
        })

    if report.get("is_uncertain"):
        outputs.append(_build_uncertain_text())

    return {
        "version": "2.0",
        "template": {
            "outputs": outputs,
            "quickReplies": quick_replies("result"),
        },
    }


def format_error(
    code: ErrorCode = ErrorCode.UNKNOWN,
    detail: str | None = None,
) -> dict[str, Any]:
    """에러 상황별 카카오 응답을 반환한다."""
    message = _ERROR_MESSAGES.get(code, _ERROR_MESSAGES[ErrorCode.UNKNOWN])
    if detail:
        message += f"\n\n상세: {_truncate(detail, 100)}"

    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {"simpleText": {"text": f"❌ {message}"}}
            ],
            "quickReplies": quick_replies("error"),
        },
    }


def format_analyzing(input_type: InputType = InputType.TEXT) -> dict[str, Any]:
    """분석 시작 안내 (callback 초기 응답 텍스트)."""
    msgs = {
        InputType.TEXT: "🔍 텍스트를 분석 중입니다...",
        InputType.URL: "🔍 영상 다운로드 및 분석 중입니다...\n음성 인식(STT) 후 사기 여부를 판별합니다.",
        InputType.VIDEO: "🎬 업로드된 영상을 분석 중입니다...\n음성 인식(STT) 후 사기 여부를 판별합니다.",
        InputType.FILE: "📎 파일을 분석 중입니다...",
    }
    return msgs.get(input_type, msgs[InputType.TEXT])


def format_queued(input_type: InputType = InputType.URL) -> dict[str, Any]:
    """폴링 모드: 분석 시작 안내 (콜백 없을 때 즉시 응답)."""
    msgs = {
        InputType.URL: "🔍 영상 분석을 시작했습니다.\n음성 인식(STT) 후 사기 여부를 판별합니다.\n\n완료되면 '결과확인'을 입력해 주세요.",
        InputType.VIDEO: "🎬 영상 분석을 시작했습니다.\n완료되면 '결과확인'을 입력해 주세요.",
        InputType.FILE: "📎 파일 분석을 시작했습니다.\n완료되면 '결과확인'을 입력해 주세요.",
        InputType.TEXT: "🔍 분석을 시작했습니다.\n완료되면 '결과확인'을 입력해 주세요.",
    }
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {"simpleText": {"text": msgs.get(input_type, msgs[InputType.TEXT])}}
            ],
            "quickReplies": quick_replies("polling"),
        },
    }


def format_still_running() -> dict[str, Any]:
    """폴링 모드: 아직 분석 중일 때 응답."""
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": "⏳ 아직 분석 중입니다.\n잠시 후 다시 '결과확인'을 입력해 주세요."
                    }
                }
            ],
            "quickReplies": quick_replies("polling"),
        },
    }


def format_no_job() -> dict[str, Any]:
    """폴링 모드: 진행 중인 분석이 없을 때 응답."""
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": "📭 현재 진행 중인 분석이 없습니다.\n의심 텍스트, URL, 또는 영상을 보내주세요."
                    }
                }
            ],
            "quickReplies": quick_replies("idle"),
        },
    }


def format_ask_for_content(reason: str = "analyze") -> dict[str, Any]:
    """사용자가 분석 요청만 했거나 상황만 묘사했을 때 — 본문을 보여달라 부탁."""
    if reason == "chat":
        text = (
            "어떤 일이 있으셨어요? 함께 살펴볼게요. 🙂\n"
            "받으신 메시지·캡처·영상·URL 그대로 보내주시면 바로 분석할게요.\n"
            "(텍스트라면 통째로 붙여넣어 주세요)"
        )
    else:  # analyze
        text = (
            "그럼요! 분석할 내용을 보여주세요. 🔍\n"
            "받으신 메시지·캡처·영상·URL 그대로 보내주시면 됩니다.\n"
            "(텍스트라면 통째로 붙여넣어 주세요)"
        )
    return {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": text}}],
            "quickReplies": quick_replies("idle"),
        },
    }


def format_reset(had_active_job: bool = False) -> dict[str, Any]:
    """진행 중 분석 잡 정리 후 안내 — '분석 초기화' 버튼 응답."""
    if had_active_job:
        text = (
            "🔄 진행 중이던 분석을 초기화했어요.\n"
            "새 의심 메시지/영상/URL을 보내주시면 처음부터 시작할게요."
        )
    else:
        text = (
            "🔄 초기화 완료. 진행 중인 분석은 없었어요.\n"
            "의심되는 메시지/영상/URL을 보내주시면 분석 시작할게요."
        )
    return {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": text}}],
            "quickReplies": quick_replies(),
        },
    }


def format_welcome() -> dict[str, Any]:
    """첫 인사 / 새 세션 진입용 — 대화체 오프닝."""
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": (
                            "안녕하세요! 저는 ScamGuardian이에요. 🛡️\n"
                            "어떤 일로 오셨어요?\n\n"
                            "의심되는 메시지·영상·URL이 있으면 그대로 보내주세요.\n"
                            "받자마자 함께 살펴보고 위험도를 알려드릴게요.\n\n"
                            "(자세한 사용법은 '사용법'을 입력하세요)"
                        )
                    }
                }
            ],
            "quickReplies": quick_replies("idle"),
        },
    }


def format_help() -> dict[str, Any]:
    """명시적 사용법 요청 시 — 무엇을 보낼 수 있고 어떻게 동작하는지 안내."""
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": (
                            "📌 ScamGuardian 사용법\n\n"
                            "이렇게 보내주시면 돼요:\n\n"
                            "1️⃣  의심 문자/통화 내용을 텍스트로 붙여넣기\n"
                            "2️⃣  YouTube · 영상 URL 보내기\n"
                            "3️⃣  의심 영상·음성 파일 직접 전송\n\n"
                            "💬 받자마자 분석 정확도를 높일 정보를 몇 가지\n"
                            "    여쭤볼게요 (어디서 받으셨는지, 어떤 게 의심됐는지 등).\n"
                            "    답변하기 어려우시면 언제든 '결과확인'을 눌러주세요.\n\n"
                            "✅ 투자·건강식품·기관 사칭·로맨스·스미싱 등\n"
                            "    다양한 유형을 자동 분류하고 위험도를 점수로 알려드려요."
                        )
                    }
                }
            ],
            "quickReplies": quick_replies("help"),
        },
    }


# ──────────────────────────────────
# 컨텍스트 대화 / 멀티턴 응답
# ──────────────────────────────────
def format_question(
    question_text: str,
    *,
    is_first_turn: bool = False,
    input_type: InputType = InputType.URL,
) -> dict[str, Any]:
    """챗봇이 사용자에게 컨텍스트 질문을 던질 때 사용.

    is_first_turn 이면 영상 접수 안내 + 첫 질문을 함께 보낸다.
    """
    outputs: list[dict[str, Any]] = []
    if is_first_turn:
        if input_type in (InputType.URL, InputType.VIDEO, InputType.FILE):
            # 영상/URL: STT + 1차 분석이 백그라운드로 돌고 있고, 채팅으로 정보 수집
            kind = {
                InputType.URL: "🔗 영상",
                InputType.VIDEO: "🎬 영상",
                InputType.FILE: "📎 파일",
            }.get(input_type, "영상")
            intro = (
                f"{kind} 받았어요! 🔍 분석을 시작했어요 (1~3분 걸려요).\n"
                "그 동안 분석 정확도를 높일 정보 몇 가지 여쭤볼게요.\n"
                "⏱ 의심 구간(예: \"1분 30초쯤\")을 알려주시면 더 정확해요.\n"
                "분석이 끝나면 다음 메시지에서 '🎉 완료' 알림과 함께 정리해드릴게요."
            )
        else:
            # TEXT: 분석도 백그라운드로 돌고 있음 (1분 정도)
            intro = (
                "📩 받았어요! 🔍 분석을 시작했어요 (약 1분 걸려요).\n"
                "그 동안 분석 정확도를 높일 정보 몇 가지 여쭤볼게요.\n"
                "분석이 끝나면 다음 메시지에서 '🎉 완료' 알림과 함께 정리해드릴게요."
            )
        outputs.append({"simpleText": {"text": intro}})
    outputs.append({"simpleText": {"text": f"💬 {question_text}"}})

    return {
        "version": "2.0",
        "template": {
            "outputs": outputs,
            "quickReplies": quick_replies("collecting_context"),
        },
    }


def format_context_done_waiting(stt_done: bool) -> dict[str, Any]:
    """컨텍스트 수집이 끝났고 분석을 기다리는 중일 때 안내."""
    if stt_done:
        text = (
            "📝 알려주신 내용 잘 받았어요.\n"
            "분석을 마무리하는 중입니다. 잠시 후 '결과확인'을 눌러주세요."
        )
    else:
        text = (
            "📝 알려주신 내용 잘 받았어요.\n"
            "음성 인식이 끝나는 대로 분석을 마무리할게요. 잠시 후 '결과확인'을 눌러주세요."
        )
    return {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": text}}],
            "quickReplies": quick_replies("analyzing"),
        },
    }


def format_result_ready_announce(has_refine: bool) -> dict[str, Any]:
    """1차 분석 완료를 사용자에게 처음 알릴 때 — 결과 준비됐다는 announce.

    has_refine=True 면 "최종 정리 중" 안내, False 면 결과 받기 안내.
    """
    if has_refine:
        text = (
            "🎉 분석이 완료됐어요!\n"
            "알려주신 정보를 더해 최종 결과를 정리 중이에요. (5~10초)\n"
            "잠시 후 '결과확인'을 눌러주시면 최종 결과를 보여드릴게요."
        )
    else:
        text = (
            "🎉 분석이 완료됐어요!\n"
            "'결과확인'을 눌러 결과를 받아보세요."
        )
    return {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": text}}],
            "quickReplies": quick_replies("polling"),
        },
    }


def format_refining_in_progress() -> dict[str, Any]:
    """최종 합본 분석 진행 중 폴링 응답."""
    return {
        "version": "2.0",
        "template": {
            "outputs": [{
                "simpleText": {
                    "text": "📊 알려주신 정보 반영해서 최종 결과 정리 중이에요.\n잠시 후 다시 '결과확인'을 입력해 주세요."
                }
            }],
            "quickReplies": quick_replies("polling"),
        },
    }


def format_busy() -> dict[str, Any]:
    """이전 분석이 아직 진행 중인데 사용자가 새 영상/URL 을 보냈을 때."""
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": (
                            "⏳ 이전 분석이 아직 진행 중이에요.\n"
                            "끝나면 '결과확인'으로 결과를 받으신 뒤 다시 보내주세요."
                        )
                    }
                }
            ],
            "quickReplies": quick_replies("busy"),
        },
    }
