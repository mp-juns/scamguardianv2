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

_QUICK_REPLY_NEW = {
    "label": "새로 분석하기",
    "action": "message",
    "messageText": "새로 분석하기",
}

_QUICK_REPLY_HELP = {
    "label": "사용법 보기",
    "action": "message",
    "messageText": "사용법",
}


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
        lines.append(f"• {f.get('flag', '')} ({sign}{delta}점)")
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

    # URL/영상이면 STT 전사 미리보기 포함
    if input_type in (InputType.URL, InputType.VIDEO, InputType.FILE):
        transcript = report.get("transcript_text", "")
        if transcript:
            body_parts.append(
                f"[음성 전사]\n{_truncate(transcript, 150)}"
            )

    body_parts.extend([
        f"[스캠 유형]\n{scam_type} (신뢰도 {confidence_pct})",
        f"[위험 판정]\n{description}",
        f"[발동 플래그]\n{_flag_lines(flags)}",
        f"[추출 엔티티]\n{_entity_lines(entities)}",
    ])

    body = "\n\n".join(body_parts)

    return {
        "basicCard": {
            "title": title,
            "description": body,
        }
    }


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
def format_result(
    report: dict[str, Any],
    input_type: InputType = InputType.TEXT,
) -> dict[str, Any]:
    """분석 결과를 카카오 응답 JSON으로 변환한다."""
    outputs: list[dict[str, Any]] = [_build_result_card(report, input_type)]

    if report.get("is_uncertain"):
        outputs.append(_build_uncertain_text())

    return {
        "version": "2.0",
        "template": {
            "outputs": outputs,
            "quickReplies": [_QUICK_REPLY_NEW],
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
            "quickReplies": [_QUICK_REPLY_NEW, _QUICK_REPLY_HELP],
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


def format_help() -> dict[str, Any]:
    """사용법 안내 메시지."""
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": (
                            "📌 ScamGuardian 사용법\n\n"
                            "아래 중 하나를 입력하세요:\n\n"
                            "1️⃣  의심 문자/음성 내용을 텍스트로 붙여넣기\n"
                            "2️⃣  YouTube / 영상 URL 입력\n"
                            "3️⃣  의심 영상/음성 파일 직접 전송\n\n"
                            "✅ 투자 사기, 건강식품 사기, 기관 사칭 등\n"
                            "다양한 유형을 자동 분류하고\n"
                            "위험도를 점수로 알려드립니다."
                        )
                    }
                }
            ],
            "quickReplies": [_QUICK_REPLY_NEW],
        },
    }
