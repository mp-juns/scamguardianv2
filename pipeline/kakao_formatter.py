"""
ScamGuardian v2 — 카카오 오픈빌더 응답 포맷터

ScamReport.to_dict() 결과를 카카오 챗봇 응답 JSON으로 변환한다.
https://i.kakao.com/docs/skill-response-format
"""

from __future__ import annotations

from typing import Any


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


def _build_result_card(report: dict[str, Any]) -> dict[str, Any]:
    """분석 결과를 BasicCard 하나로 만든다."""
    level = report.get("risk_level", "알 수 없음")
    score = report.get("total_score", 0)
    scam_type = report.get("scam_type", "미분류")
    confidence = report.get("classification_confidence", 0)
    entities = report.get("entities", [])
    flags = report.get("triggered_flags", [])
    description = report.get("risk_description", "")

    icon = _risk_icon(level)
    confidence_pct = f"{confidence * 100:.0f}%"

    title = f"{icon} {level}  |  {score}점"
    body = (
        f"[스캠 유형]\n{scam_type} (신뢰도 {confidence_pct})\n\n"
        f"[위험 판정]\n{description}\n\n"
        f"[발동 플래그]\n{_flag_lines(flags)}\n\n"
        f"[추출 엔티티]\n{_entity_lines(entities)}"
    )

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


def format_result(report: dict[str, Any]) -> dict[str, Any]:
    """
    ScamReport.to_dict() 결과를 카카오 오픈빌더 응답 JSON으로 변환한다.

    Returns:
        카카오 skill response JSON (version 2.0)
    """
    outputs: list[dict[str, Any]] = [_build_result_card(report)]

    if report.get("is_uncertain"):
        outputs.append(_build_uncertain_text())

    return {
        "version": "2.0",
        "template": {
            "outputs": outputs,
            "quickReplies": [_QUICK_REPLY_NEW],
        },
    }


def format_error(message: str = "분석 중 오류가 발생했습니다.") -> dict[str, Any]:
    """오류 발생 시 반환할 카카오 응답."""
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": f"❌ {message}\n잠시 후 다시 시도해 주세요."
                    }
                }
            ],
            "quickReplies": [_QUICK_REPLY_NEW],
        },
    }


def format_waiting() -> dict[str, Any]:
    """분석 시작 안내 메시지 (즉시 반환용)."""
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": (
                            "🔍 분석을 시작합니다.\n\n"
                            "텍스트나 YouTube URL을 입력하면\n"
                            "스캠 여부를 판별해 드립니다."
                        )
                    }
                }
            ],
            "quickReplies": [_QUICK_REPLY_NEW],
        },
    }


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
                            "2️⃣  YouTube URL 입력\n\n"
                            "투자 사기, 건강식품 사기, 기관 사칭 등\n"
                            "5가지 유형을 자동으로 분류하고\n"
                            "위험도를 점수로 알려드립니다."
                        )
                    }
                }
            ],
            "quickReplies": [_QUICK_REPLY_NEW],
        },
    }
