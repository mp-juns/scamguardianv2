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

from pipeline.config import SCORING_RULES, get_runtime_scam_taxonomy

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
    allowed_flags = list(SCORING_RULES.keys())

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
3. flags: 텍스트에 명확한 근거가 있을 때만 포함. evidence는 텍스트에서 직접 인용
4. reasoning: 판단 근거를 2~3문장으로 간결하게 요약
5. JSON 외 텍스트 절대 금지

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
    """Claude 응답에서 JSON을 추출한다."""
    # 마크다운 코드블록 제거
    text = re.sub(r"```(?:json)?\s*", "", raw).strip()
    # 첫 번째 { ... } 블록 추출
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return json.loads(match.group(0))
    return json.loads(text)


def _sanitize(
    result: dict[str, Any],
    predicted_scam_type: str,
) -> dict[str, Any]:
    """허용 목록 외 값을 필터링하고 구조를 정규화한다."""
    taxonomy = get_runtime_scam_taxonomy()
    valid_scam_types = set(taxonomy["scam_types"])
    label_sets = taxonomy["label_sets"]
    valid_flags = set(SCORING_RULES.keys())

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
        max_tokens=1024,
        system="당신은 한국어 사기 탐지 라벨러입니다. JSON만 반환하세요.",
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text
    result = _parse_response(raw)
    return _sanitize(result, predicted_scam_type)
