"""
ScamGuardian v2 — Claude API 기반 라벨링 초안 생성기

어드민 라벨링 작업에서 사람 검수자의 부담을 줄이기 위해
Claude가 scam_type, 엔티티, 플래그 초안을 자동으로 생성한다.
검수자는 틀린 것만 수정하면 된다.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from pipeline.config import DETECTED_FLAGS, get_runtime_scam_taxonomy

_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _build_prompt(
    transcript: str,
    predicted_scam_type: str,
    predicted_entities: list[dict[str, Any]],
    predicted_flags: list[dict[str, Any]],
) -> str:
    taxonomy = get_runtime_scam_taxonomy()
    scam_types = taxonomy["scam_types"]
    label_sets = taxonomy["label_sets"]
    allowed_flags = list(DETECTED_FLAGS)

    return f"""당신은 한국어 전화/영상 사기 탐지 전문 라벨러입니다.
아래 전사 텍스트를 분석하고 정확한 라벨링 초안을 JSON으로만 반환하세요.

## 허용 스캠 유형
{json.dumps(scam_types, ensure_ascii=False)}

## 스캠 유형별 허용 엔티티 라벨
{json.dumps(label_sets, ensure_ascii=False)}

## 허용 플래그
{json.dumps(allowed_flags, ensure_ascii=False)}

## 파이프라인 예측 결과 (참고만 할 것, 맹신 금지)
- 예측 스캠 유형: {predicted_scam_type}
- 예측 엔티티: {json.dumps(predicted_entities, ensure_ascii=False)}
- 예측 플래그: {json.dumps(predicted_flags, ensure_ascii=False)}

## 전사 텍스트
{transcript[:3000]}

## 지시사항
1. scam_type: 허용 목록에서 가장 적합한 것을 선택
2. entities: 텍스트에서 실제로 언급된 것만 추출. label은 선택한 scam_type의 허용 라벨 중 하나
3. flags: 텍스트에 명확한 근거가 있을 때만 포함. evidence는 텍스트에서 직접 인용 (각 evidence 최대 80자, 길면 줄임)
4. reasoning: 판단 근거를 2~3문장으로 간결하게 요약 (최대 200자)
5. JSON 외 텍스트 절대 금지. 모든 문자열 안의 큰따옴표는 \" 로 이스케이프

반환 JSON 스키마:
{{
  "scam_type": "허용 스캠 유형 중 하나",
  "entities": [
    {{"text": "텍스트에서 그대로 추출", "label": "허용 라벨 중 하나"}}
  ],
  "flags": [
    {{"flag": "허용 플래그 중 하나", "description": "한국어 설명", "evidence": "텍스트 직접 인용"}}
  ],
  "reasoning": "판단 근거 요약"
}}""".strip()


def _parse_response(raw: str) -> dict[str, Any]:
    """Claude 응답에서 JSON을 추출한다.

    응답이 max_tokens 등으로 잘려 JSON 끝이 깨졌을 수 있으므로,
    파싱 실패 시 마지막 닫힌 객체까지만 잘라 재시도한다.
    """
    # 마크다운 코드블록 제거
    text = re.sub(r"```(?:json)?\s*", "", raw).strip()
    text = text.rstrip("` \n\r\t")
    match = re.search(r"\{[\s\S]*\}", text)
    candidate = match.group(0) if match else text

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # 잘린 JSON 복구 시도 — 괄호 균형 맞추는 위치까지만 사용
    repaired = _truncate_to_balanced(candidate)
    if repaired is not None:
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

    raise ValueError(
        "Claude 응답을 JSON으로 파싱하지 못했습니다. "
        "max_tokens 부족으로 응답이 잘렸을 수 있습니다. "
        f"raw 응답 미리보기: {raw[:200]!r}"
    )


def _truncate_to_balanced(text: str) -> str | None:
    """문자열을 앞에서부터 읽어 괄호/문자열이 균형 잡힌 가장 긴 prefix 를 반환.

    잘린 JSON 응답에서 마지막으로 완전히 닫힌 객체/배열까지를 잘라낸다.
    리스트 끝이 trailing comma 로 깨진 경우도 보정한다.
    """
    if not text or text[0] != "{":
        return None

    in_string = False
    escape = False
    stack: list[str] = []
    last_safe = -1  # 가장 마지막으로 균형 잡힌 위치 (직전까지 유효)

    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if not stack:
                break
            stack.pop()
            if not stack:
                last_safe = i  # 최상위 객체가 닫힌 위치
                break
        elif ch == "," and len(stack) == 1:
            # 최상위 객체 안에서 완전한 key:value 페어가 끝난 시점
            last_safe = i - 1

    if last_safe < 0:
        return None

    truncated = text[: last_safe + 1].rstrip().rstrip(",")
    # 남은 열린 괄호를 닫아 본다
    closers = []
    in_string = False
    escape = False
    stack = []
    for ch in truncated:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()
    for opener in reversed(stack):
        closers.append("}" if opener == "{" else "]")
    return truncated + "".join(closers)


def _sanitize(
    result: dict[str, Any],
    predicted_scam_type: str,
) -> dict[str, Any]:
    """허용 목록 외 값을 필터링하고 구조를 정규화한다."""
    taxonomy = get_runtime_scam_taxonomy()
    valid_scam_types = set(taxonomy["scam_types"])
    label_sets = taxonomy["label_sets"]
    valid_flags = set(DETECTED_FLAGS)

    scam_type = str(result.get("scam_type", predicted_scam_type)).strip()
    if scam_type not in valid_scam_types:
        scam_type = predicted_scam_type

    valid_labels = set(label_sets.get(scam_type, []))

    entities: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for item in result.get("entities", []):
        text = str(item.get("text", "")).strip()
        label = str(item.get("label", "")).strip()
        if not text or not label or label not in valid_labels:
            continue
        pair = (label, text)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        entities.append({"text": text, "label": label})

    flags: list[dict[str, str]] = []
    seen_flags: set[str] = set()
    for item in result.get("flags", []):
        flag = str(item.get("flag", "")).strip()
        if not flag or flag not in valid_flags or flag in seen_flags:
            continue
        seen_flags.add(flag)
        flags.append(
            {
                "flag": flag,
                "description": str(item.get("description", "")).strip(),
                "evidence": str(item.get("evidence", "")).strip(),
            }
        )

    return {
        "scam_type": scam_type,
        "entities": entities,
        "flags": flags,
        "reasoning": str(result.get("reasoning", "")).strip(),
    }


def generate_draft(
    transcript: str,
    predicted_scam_type: str,
    predicted_entities: list[dict[str, Any]],
    predicted_flags: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Claude API로 라벨링 초안을 생성한다.

    Returns:
        {
            "scam_type": str,
            "entities": [{"text": str, "label": str}],
            "flags": [{"flag": str, "description": str, "evidence": str}],
            "reasoning": str,
        }
    """
    prompt = _build_prompt(
        transcript,
        predicted_scam_type,
        predicted_entities,
        predicted_flags,
    )

    client = _get_client()
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system="당신은 한국어 사기 탐지 라벨러입니다. JSON만 반환하세요.",
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        from platform_layer import cost as _cost
        _cost.record_claude(
            model,
            int(getattr(message.usage, "input_tokens", 0) or 0),
            int(getattr(message.usage, "output_tokens", 0) or 0),
            action="claude_labeler.generate_draft",
        )
    except Exception:
        pass

    # 첫 text 블록을 찾는다 (extended thinking 등 비-텍스트 블록 대비)
    raw = ""
    for block in message.content:
        text = getattr(block, "text", None)
        if text:
            raw = text
            break
    if not raw:
        raise ValueError(f"Claude 응답에 텍스트가 없습니다. stop_reason={message.stop_reason}")

    result = _parse_response(raw)
    return _sanitize(result, predicted_scam_type)
