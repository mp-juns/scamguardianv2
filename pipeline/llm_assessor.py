"""
ScamGuardian v2 — Ollama 기반 LLM 보조 판정 모듈

기존 규칙 파이프라인을 대체하지 않고, 추가 엔티티/플래그 후보를 제안한다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import requests

from pipeline.config import (
    LLM_ENTITY_MERGE_THRESHOLD,
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_MAX_ENTITY_COUNT,
    OLLAMA_MAX_TRANSCRIPT_CHARS,
    OLLAMA_MAX_TRIGGERED_FLAG_COUNT,
    OLLAMA_MODEL,
    OLLAMA_NUM_PREDICT,
    OLLAMA_TIMEOUT_SECONDS,
    RAG_MAX_CASES_IN_PROMPT,
    SCORING_RULES,
    get_runtime_scam_taxonomy,
)
from pipeline.extractor import Entity
from pipeline.verifier import VerificationResult


@dataclass
class SuggestedEntity:
    text: str
    label: str
    reason: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "label": self.label,
            "reason": self.reason,
            "confidence": round(self.confidence, 4),
        }


@dataclass
class SuggestedFlag:
    flag: str
    reason: str
    evidence: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "flag": self.flag,
            "reason": self.reason,
            "evidence": self.evidence,
            "confidence": round(self.confidence, 4),
        }


@dataclass
class LLMAssessment:
    model: str
    summary: str = ""
    suggested_entities: list[SuggestedEntity] = field(default_factory=list)
    suggested_flags: list[SuggestedFlag] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "summary": self.summary,
            "suggested_entities": [entity.to_dict() for entity in self.suggested_entities],
            "suggested_flags": [flag.to_dict() for flag in self.suggested_flags],
            "error": self.error,
        }


def default_model_name() -> str:
    return OLLAMA_MODEL


def _clamp_confidence(value: Any, default: float = 0.6) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def _build_prompt(
    transcript: str,
    scam_type: str,
    entities: list[Entity],
    verification_results: list[VerificationResult],
    similar_cases: list[dict[str, Any]] | None = None,
) -> str:
    allowed_labels = get_runtime_scam_taxonomy()["label_sets"].get(scam_type, [])
    allowed_flags = list(SCORING_RULES.keys())

    entity_lines = [
        {
            "text": entity.text,
            "label": entity.label,
            "score": round(entity.score, 4),
            "source": entity.source,
        }
        for entity in entities[:OLLAMA_MAX_ENTITY_COUNT]
    ]
    triggered_flags = [
        {
            "flag": result.flag,
            "description": result.flag_description,
        }
        for result in verification_results[:OLLAMA_MAX_TRIGGERED_FLAG_COUNT]
        if result.triggered
    ]
    rag_cases = (similar_cases or [])[:RAG_MAX_CASES_IN_PROMPT]

    return f"""
역할: 한국어 스캠 탐지 보조 판정기
출력: JSON만

해야 할 일:
1. 기존 추출에서 빠졌을 수 있는 엔티티 최대 2개
2. 기존 검증과 별도로 점수 반영 후보 플래그 최대 2개
3. 짧은 한국어 요약 1문장

규칙:
- missing_entities[].label 은 허용 레이블 중 하나만 사용
- suggested_flags[].flag 는 허용 플래그 중 하나만 사용
- 확신이 낮으면 빈 배열
- confidence 는 0~1 숫자
- JSON 외 텍스트 금지
- text 가 비어 있는 엔티티는 절대 반환하지 마라
- 이미 추출된 엔티티와 동일하면 다시 제안하지 마라

허용 레이블:
{json.dumps(allowed_labels, ensure_ascii=False)}

허용 플래그:
{json.dumps(allowed_flags, ensure_ascii=False)}

이미 추출된 엔티티:
{json.dumps(entity_lines, ensure_ascii=False)}

이미 발동된 플래그:
{json.dumps(triggered_flags, ensure_ascii=False)}

유사 과거 사례(사람이 정답 확정):
{json.dumps(rag_cases, ensure_ascii=False)}

전사 텍스트:
{transcript[:OLLAMA_MAX_TRANSCRIPT_CHARS]}

반환 JSON 스키마:
{{
  "summary": "짧은 한국어 요약",
  "missing_entities": [
    {{
      "text": "문자열",
      "label": "허용 레이블 중 하나",
      "reason": "왜 이 엔티티가 중요하다고 봤는지",
      "confidence": 0.0
    }}
  ],
  "suggested_flags": [
    {{
      "flag": "허용 플래그 중 하나",
      "reason": "왜 이 플래그를 제안하는지",
      "evidence": "전사에서 근거가 되는 짧은 문구",
      "confidence": 0.0
    }}
  ]
}}
""".strip()


def _call_ollama(prompt: str) -> dict[str, Any]:
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "think": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": {
                "temperature": 0,
                "num_predict": OLLAMA_NUM_PREDICT,
            },
        },
        timeout=OLLAMA_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    raw_text = payload.get("response") or payload.get("thinking") or "{}"
    return _parse_ollama_json(raw_text)


def _parse_ollama_json(raw_text: str) -> dict[str, Any]:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        repaired = _repair_truncated_json(raw_text)
        return json.loads(repaired)


def _repair_truncated_json(raw_text: str) -> str:
    text = raw_text.strip()
    if not text:
        return "{}"

    first_brace = text.find("{")
    if first_brace > 0:
        text = text[first_brace:]

    stack: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch == "}" and stack and stack[-1] == "{":
            stack.pop()
        elif ch == "]" and stack and stack[-1] == "[":
            stack.pop()

    if in_string:
        text += '"'

    text = re.sub(r",\s*$", "", text)

    closing_parts: list[str] = []
    for opener in reversed(stack):
        closing_parts.append("}" if opener == "{" else "]")

    repaired = text + "".join(closing_parts)
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    return repaired


def assess(
    transcript: str,
    scam_type: str,
    entities: list[Entity],
    verification_results: list[VerificationResult],
    similar_cases: list[dict[str, Any]] | None = None,
) -> LLMAssessment:
    prompt = _build_prompt(
        transcript,
        scam_type,
        entities,
        verification_results,
        similar_cases=similar_cases,
    )
    raw = _call_ollama(prompt)

    allowed_labels = set(get_runtime_scam_taxonomy()["label_sets"].get(scam_type, []))
    allowed_flags = set(SCORING_RULES.keys())
    existing_entity_pairs = {(entity.label, entity.text) for entity in entities}

    suggested_entities: list[SuggestedEntity] = []
    seen_entity_pairs: set[tuple[str, str]] = set()
    for item in raw.get("missing_entities", [])[:5]:
        label = str(item.get("label", "")).strip()
        text = str(item.get("text", "")).strip()
        if not label or not text or label not in allowed_labels:
            continue
        pair = (label, text)
        if pair in existing_entity_pairs or pair in seen_entity_pairs:
            continue
        seen_entity_pairs.add(pair)
        suggested_entities.append(
            SuggestedEntity(
                text=text,
                label=label,
                reason=str(item.get("reason", "")).strip(),
                confidence=_clamp_confidence(item.get("confidence")),
            )
        )

    suggested_flags: list[SuggestedFlag] = []
    seen_flags: set[str] = set()
    for item in raw.get("suggested_flags", [])[:3]:
        flag = str(item.get("flag", "")).strip()
        if not flag or flag not in allowed_flags or flag in seen_flags:
            continue
        seen_flags.add(flag)
        suggested_flags.append(
            SuggestedFlag(
                flag=flag,
                reason=str(item.get("reason", "")).strip(),
                evidence=str(item.get("evidence", "")).strip(),
                confidence=_clamp_confidence(item.get("confidence")),
            )
        )

    return LLMAssessment(
        model=OLLAMA_MODEL,
        summary=str(raw.get("summary", "")).strip(),
        suggested_entities=suggested_entities,
        suggested_flags=suggested_flags,
    )


def merge_suggested_entities(
    entities: list[Entity],
    assessment: LLMAssessment | None,
) -> list[Entity]:
    if assessment is None or assessment.error:
        return list(entities)

    merged = list(entities)
    seen_pairs = {(entity.label, entity.text) for entity in merged}

    for suggested in assessment.suggested_entities:
        if suggested.confidence < LLM_ENTITY_MERGE_THRESHOLD:
            continue

        pair = (suggested.label, suggested.text)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        merged.append(
            Entity(
                text=suggested.text,
                label=suggested.label,
                score=suggested.confidence,
                start=-1,
                end=-1,
                source="llm",
            )
        )

    merged.sort(key=lambda entity: (entity.start < 0, entity.start, -entity.score))
    return merged
