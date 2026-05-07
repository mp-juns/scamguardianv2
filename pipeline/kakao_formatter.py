"""
ScamGuardian — 카카오 오픈빌더 응답 포맷터

DetectionReport.to_dict() 결과를 카카오 챗봇 응답 JSON 으로 변환.
Identity (CLAUDE.md): 점수·등급 표시 안 함 — 검출 신호 list + 학술/법적 근거만.

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
    IMAGE = "image"   # v3 — 사진·캡쳐
    PDF = "pdf"       # v3 — PDF 문서


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
# 검출 신호 개수별 아이콘 (점수·등급 X — Identity Boundary)
# 단순히 "신호 있음/없음" 만 시각화. 판정은 통합 기업 몫.
# ──────────────────────────────────


def _detection_icon(signal_count: int) -> str:
    """검출 신호 개수에 따른 표시 아이콘. 점수·등급 매기기 X."""
    if signal_count <= 0:
        return "✅"
    if signal_count <= 2:
        return "⚠️"
    return "🚨"


_DISCLAIMER_TEXT = (
    "ⓘ ScamGuardian 은 사기 판정을 내리지 않습니다. "
    "위 검출 신호와 근거를 참고하여 신중히 판단해주세요."
)

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


def _entity_lines(entities: list[dict[str, Any]], max_count: int = 6) -> str:
    if not entities:
        return "없음"
    lines = []
    for e in entities[:max_count]:
        lines.append(f"• {e.get('label', '')}: {e.get('text', '')}")
    if len(entities) > max_count:
        lines.append(f"… 외 {len(entities) - max_count}개")
    return "\n".join(lines)


def _signal_lines(signals: list[dict[str, Any]], max_count: int = 4) -> str:
    """검출 신호를 한국어 라벨 + (요약된) 학술/법적 근거로 표시. 점수 표기 없음."""
    if not signals:
        return "검출된 위험 신호 없음"
    lines = []
    for s in signals[:max_count]:
        flag_key = s.get("flag", "")
        label = s.get("label_ko") or (flag_label_ko(flag_key) if flag_key else "(이름 없음)")
        rationale = (s.get("rationale") or "").strip()
        # 카드 본문이 너무 길어지지 않도록 근거는 1문장 또는 80자까지만 노출
        if rationale:
            short = rationale.split(".", 1)[0].strip()
            short = (short[:80] + "…") if len(short) > 80 else short
            lines.append(f"• {label}\n   └ 근거: {short}")
        else:
            lines.append(f"• {label}")
    if len(signals) > max_count:
        lines.append(f"… 외 {len(signals) - max_count}개")
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
    """검출 결과 카드 — 점수·등급 X, 검출 신호 list 만 표시."""
    scam_type = report.get("scam_type", "미분류")
    confidence = report.get("classification_confidence", 0)
    entities = report.get("entities", [])
    signals = report.get("detected_signals", [])
    signal_count = len(signals)

    icon = _detection_icon(signal_count)
    confidence_pct = f"{confidence * 100:.0f}%"

    # 입력 유형 표시
    type_labels = {
        InputType.TEXT: "💬 텍스트 검출",
        InputType.URL: "🔗 링크 검출",
        InputType.VIDEO: "🎬 영상 검출",
        InputType.FILE: "📎 파일 검출",
        InputType.IMAGE: "🖼 이미지 검출",
        InputType.PDF: "📄 PDF 검출",
    }
    type_label = type_labels.get(input_type, "검출")

    if signal_count == 0:
        title = f"{icon} 검출된 위험 신호 없음"
    else:
        title = f"{icon} 위험 신호 {signal_count}개 검출"

    body_parts = [f"[검출 방식] {type_label}"]

    # 입력 본문/전사 미리보기 — TEXT 도 포함하여 일관 표시
    transcript = report.get("transcript_text", "")
    if transcript:
        # VIDEO/FILE 만 음성 전사. URL 은 링크 자체 또는 페이지 텍스트라 "입력 본문" 으로 통일.
        label = "음성 전사" if input_type in (InputType.VIDEO, InputType.FILE) else "입력 본문"
        body_parts.append(f"[{label}]\n{_truncate(transcript, 150)}")

    # LLM 한 줄 요약이 있으면 우선 노출 — 사용자가 핵심 빠르게 파악 가능
    llm = report.get("llm_assessment") or {}
    summary = str(llm.get("summary", "")).strip()
    if summary:
        body_parts.append(f"[AI 요약]\n{_truncate(summary, 200)}")

    body_parts.extend([
        f"[추정 유형]\n{scam_type} (분류 신뢰도 {confidence_pct})",
        f"[검출된 위험 신호 — {signal_count}개]\n{_signal_lines(signals)}",
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


def _build_safety_warning_block(report: dict[str, Any]) -> dict[str, Any] | None:
    """v3 Phase 0 안전성 결과 — malicious/suspicious 일 때만 최상단 경고 블록 생성."""
    safety = report.get("safety_check") or {}
    level = (safety.get("threat_level") or "").lower()
    if level not in ("malicious", "suspicious"):
        return None
    detections = int(safety.get("detections") or 0)
    total = int(safety.get("total_engines") or 0)
    cats = safety.get("threat_categories") or []
    target_kind = safety.get("target_kind", "")
    kind_label = "URL" if target_kind == "url" else "파일"
    icon = "🚨" if level == "malicious" else "⚠️"
    if level == "malicious":
        head = f"{icon} 위험! 이 {kind_label}은 악성으로 확인됐어요."
    else:
        head = f"{icon} 주의: 이 {kind_label}에 일부 의심 신호가 있어요."
    lines = [head]
    if total:
        lines.append(f"VirusTotal {detections}/{total} 엔진 탐지")
    if cats:
        lines.append("탐지 카테고리: " + ", ".join(map(str, cats[:3])))
    lines.append("절대 클릭·실행하지 마시고 발신자에게 답하지 마세요.")
    return {"simpleText": {"text": "\n".join(lines)}}


def format_result(
    report: dict[str, Any],
    input_type: InputType = InputType.TEXT,
    user_context: dict[str, Any] | None = None,
    result_url: str | None = None,
) -> dict[str, Any]:
    """검출 결과를 카카오 응답 JSON 으로 변환.

    Identity (CLAUDE.md): 점수·등급 X, 검출 신호 list 만. 끝에 disclaimer 부착.
    result_url 이 주어지면 카드에 '자세한 결과 보기' webLink 버튼 + 안내 텍스트 추가.
    """
    outputs: list[dict[str, Any]] = []

    safety_block = _build_safety_warning_block(report)
    if safety_block:
        # VT 다중 엔진 합의 신호는 카드보다 먼저 — 사용자 눈에 가장 먼저 들어오도록
        outputs.append(safety_block)

    outputs.append(_build_result_card(report, input_type, result_url=result_url))

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

    # Identity Boundary disclaimer — 모든 결과 카드 마지막에
    outputs.append({"simpleText": {"text": _DISCLAIMER_TEXT}})

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
        InputType.URL: "🔗 링크 안전성 검사 중입니다...\nVirusTotal 조회 후 페이지 내용을 분석합니다.",
        InputType.VIDEO: "🎬 영상을 분석 중입니다...\n음성 인식(STT) 후 사기 여부를 판별합니다.",
        InputType.FILE: "📎 파일을 분석 중입니다...",
        InputType.IMAGE: "🖼 이미지를 분석 중입니다...\nOCR + 시각 단서를 같이 봅니다.",
        InputType.PDF: "📄 PDF를 분석 중입니다...\n페이지별로 OCR + 시각 단서를 추출합니다.",
    }
    return msgs.get(input_type, msgs[InputType.TEXT])


def format_queued(input_type: InputType = InputType.URL) -> dict[str, Any]:
    """폴링 모드: 분석 시작 안내 (콜백 없을 때 즉시 응답)."""
    msgs = {
        InputType.URL: "🔗 링크 분석을 시작했습니다.\nVirusTotal 검사 + 페이지 내용 분석.\n완료되면 '결과확인'을 입력해 주세요.",
        InputType.VIDEO: "🎬 영상 분석을 시작했습니다.\n완료되면 '결과확인'을 입력해 주세요.",
        InputType.FILE: "📎 파일 분석을 시작했습니다.\n완료되면 '결과확인'을 입력해 주세요.",
        InputType.TEXT: "🔍 분석을 시작했습니다.\n완료되면 '결과확인'을 입력해 주세요.",
        InputType.IMAGE: "🖼 이미지 분석을 시작했습니다.\nOCR 후 사기 여부를 판별합니다.\n완료되면 '결과확인'을 입력해 주세요.",
        InputType.PDF: "📄 PDF 분석을 시작했습니다.\n페이지 OCR 후 사기 여부를 판별합니다.\n완료되면 '결과확인'을 입력해 주세요.",
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


def _humanize_duration(sec: int) -> str:
    """경과 초 → 사용자에게 보여줄 한국어 표현."""
    if sec < 10:
        return "방금 시작"
    if sec < 60:
        return f"{sec}초째"
    minutes = sec // 60
    rem = sec % 60
    if rem < 10:
        return f"{minutes}분째"
    return f"{minutes}분 {rem}초째"


def _polling_progress_lines(stage: str, elapsed_sec: int, poll_count: int) -> str:
    """polling 진행 상황을 사용자가 헷갈리지 않게 단계별 텍스트로 변환.

    stage:
        "stt"        — 음성 인식 중
        "analyzing"  — 분석 중 (STT 끝났고 본 분석 진행)
        "refining"   — 사용자 답변 반영 최종 정리 중
    """
    elapsed_label = _humanize_duration(elapsed_sec)
    if stage == "stt":
        head = "⏳ 음성 인식 진행 중이에요"
        if poll_count <= 1:
            tail = "유튜브 영상은 보통 1~3분 걸려요. 끝나면 결과를 정리해드릴게요."
        else:
            tail = (
                f"({elapsed_label}) — 유튜브는 다운로드 + 받아쓰기까지 1~3분 걸려요.\n"
                "곧 끝납니다, 30초만 더 기다려주세요."
            )
    elif stage == "refining":
        head = "📊 알려주신 정보 반영해서 마지막 정리 중이에요"
        if poll_count <= 1:
            tail = "5~10초 정도면 끝나요. 잠시 후 다시 '결과확인' 눌러주세요."
        else:
            tail = (
                f"({elapsed_label}) — 거의 다 됐어요. 한 번만 더 기다려주세요."
            )
    else:  # "analyzing"
        head = "🔍 받아쓰기는 끝났고 본 분석을 마무리하는 중이에요"
        if poll_count <= 1:
            tail = "보통 10~20초 걸려요. 끝나면 결과 카드 보여드릴게요."
        else:
            tail = (
                f"({elapsed_label}) — 곧 끝나요. 30초만 더 기다려주세요."
            )
    return f"{head}\n{tail}"


def format_still_running(
    elapsed_sec: int = 0,
    poll_count: int = 1,
    stt_done: bool = True,
) -> dict[str, Any]:
    """폴링 모드: 아직 분석 중일 때 응답. 매 호출마다 경과 시간 다르게 표시."""
    stage = "analyzing" if stt_done else "stt"
    text = _polling_progress_lines(stage, elapsed_sec, poll_count)
    return {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": text}}],
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
        if input_type in (InputType.URL, InputType.VIDEO, InputType.FILE, InputType.IMAGE, InputType.PDF):
            # 영상/URL/이미지/PDF: vision/STT + 1차 분석이 백그라운드로 돌고 있고, 채팅으로 정보 수집
            kind = {
                InputType.URL: "🔗 링크",
                InputType.VIDEO: "🎬 영상",
                InputType.FILE: "📎 파일",
                InputType.IMAGE: "🖼 이미지",
                InputType.PDF: "📄 PDF",
            }.get(input_type, "콘텐츠")
            # 이미지/PDF/URL 은 다운로드/OCR/VT 만 — 더 빠름
            duration = (
                "10초 정도"
                if input_type in (InputType.IMAGE, InputType.PDF, InputType.URL)
                else "1~3분"
            )
            intro = (
                f"{kind} 받았어요! 🔍 분석을 시작했어요 ({duration} 걸려요).\n"
                "그 동안 분석 정확도를 높일 정보 몇 가지 여쭤볼게요.\n"
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


def format_context_done_waiting(
    stt_done: bool,
    elapsed_sec: int = 0,
    poll_count: int = 1,
) -> dict[str, Any]:
    """컨텍스트 수집이 끝났고 분석을 기다리는 중일 때 안내.

    poll_count 가 2 이상이면 ack 인사 빼고 진행 단계만 표시 — 같은 메시지 도배 방지.
    """
    stage = "analyzing" if stt_done else "stt"
    progress = _polling_progress_lines(stage, elapsed_sec, poll_count)
    if poll_count <= 1:
        text = f"📝 알려주신 내용 잘 받았어요.\n\n{progress}"
    else:
        text = progress
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


def format_refining_in_progress(
    elapsed_sec: int = 0,
    poll_count: int = 1,
) -> dict[str, Any]:
    """최종 합본 분석 진행 중 폴링 응답."""
    text = _polling_progress_lines("refining", elapsed_sec, poll_count)
    return {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": text}}],
            "quickReplies": quick_replies("polling"),
        },
    }


def format_abuse_warning(message: str, warns_left: int) -> dict[str, Any]:
    """어뷰즈 가드 경고 — 짧은/도배/gibberish 등. warns_left 표시."""
    return {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": f"⚠️ {message}"}}],
            "quickReplies": quick_replies("idle"),
        },
    }


def format_abuse_blocked(remaining_sec: int) -> dict[str, Any]:
    """반복 어뷰즈로 일시 차단됐을 때. 채팅 종료."""
    minutes = max(1, remaining_sec // 60)
    text = (
        "🚫 반복적인 어뷰즈로 일시 차단되었어요.\n"
        f"약 {minutes}분 후 다시 시도해 주세요.\n"
        "정상적인 사기 의심 메시지는 길고 구체적일수록 분석 정확도가 높아져요."
    )
    return {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": text}}],
            "quickReplies": [],   # 차단 상태에선 quick reply 도 제거
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
