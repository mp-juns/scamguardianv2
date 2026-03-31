"""
ScamGuardian v2 — 스코어링 모듈
교차 검증 결과를 바탕으로 규칙 기반 스캠 점수를 산출한다.
LLM 판단 없이, 우리가 설계한 알고리즘이 최종 판정을 내린다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pipeline.config import LLM_FLAG_SCORE_RATIO, LLM_FLAG_SCORE_THRESHOLD, SCORING_RULES, get_risk_level
from pipeline.classifier import ClassificationResult
from pipeline.extractor import Entity
from pipeline.llm_assessor import LLMAssessment
from pipeline.verifier import VerificationResult


@dataclass
class FlagDetail:
    flag: str
    description: str
    score_delta: int
    evidence: list[str] = field(default_factory=list)
    source: str = "rule"


@dataclass
class ScamReport:
    # 입력 정보
    source: str = ""
    transcript_preview: str = ""

    # 분류 결과
    scam_type: str = ""
    classification_confidence: float = 0.0
    is_uncertain: bool = False

    # 추출 결과
    entities: list[dict[str, Any]] = field(default_factory=list)

    # 스코어링 결과
    total_score: int = 0
    risk_level: str = ""
    risk_description: str = ""
    triggered_flags: list[FlagDetail] = field(default_factory=list)

    # 검증 상세 (디버깅/감사용)
    all_verifications: list[dict[str, Any]] = field(default_factory=list)
    llm_assessment: dict[str, Any] | None = None
    rag_context: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "transcript_preview": self.transcript_preview,
            "scam_type": self.scam_type,
            "classification_confidence": round(self.classification_confidence, 4),
            "is_uncertain": self.is_uncertain,
            "entities": self.entities,
            "total_score": self.total_score,
            "risk_level": self.risk_level,
            "risk_description": self.risk_description,
            "triggered_flags": [
                {
                    "flag": f.flag,
                    "description": f.description,
                    "score_delta": f.score_delta,
                    "evidence": f.evidence,
                    "source": f.source,
                }
                for f in self.triggered_flags
            ],
            "verification_count": len(self.all_verifications),
            "llm_assessment": self.llm_assessment,
            "rag_context": self.rag_context,
        }

    def summary(self) -> str:
        """사람이 읽기 쉬운 한국어 요약을 반환한다."""
        lines = [
            "=" * 60,
            "  ScamGuardian v2 — 분석 결과",
            "=" * 60,
            "",
            f"  스캠 유형: {self.scam_type} (신뢰도: {self.classification_confidence:.1%})",
        ]
        if self.is_uncertain:
            lines.append("  ⚠ 분류 신뢰도가 낮아 결과가 부정확할 수 있습니다.")
        lines.append("")

        lines.append(f"  추출된 엔티티 ({len(self.entities)}개):")
        for e in self.entities:
            lines.append(f"    - [{e['label']}] {e['text']} (신뢰도: {e['score']:.2f})")
        lines.append("")

        lines.append(f"  총 위험 점수: {self.total_score}점")
        lines.append(f"  위험도 레벨: {self.risk_level}")
        lines.append(f"  판정: {self.risk_description}")
        lines.append("")

        if self.triggered_flags:
            lines.append(f"  발동된 플래그 ({len(self.triggered_flags)}개):")
            for f in self.triggered_flags:
                source_prefix = "[LLM] " if f.source == "llm" else ""
                lines.append(f"    {source_prefix}[{f.flag}] +{f.score_delta}점 — {f.description}")
                for ev in f.evidence[:2]:
                    lines.append(f"      근거: {ev[:100]}")
        else:
            lines.append("  발동된 플래그 없음")

        if self.llm_assessment:
            lines.append("")
            lines.append("  LLM 보조 판정:")
            if self.llm_assessment.get("error"):
                lines.append(f"    실패: {self.llm_assessment['error']}")
            else:
                if self.llm_assessment.get("summary"):
                    lines.append(f"    요약: {self.llm_assessment['summary']}")
                lines.append(
                    f"    추가 엔티티 제안: {len(self.llm_assessment.get('suggested_entities', []))}개"
                )
                lines.append(
                    f"    추가 플래그 제안: {len(self.llm_assessment.get('suggested_flags', []))}개"
                )

        if self.rag_context and self.rag_context.get("enabled"):
            lines.append("")
            lines.append(
                f"  RAG 참고 사례: {len(self.rag_context.get('similar_cases', []))}개"
            )

        lines.extend(["", "=" * 60])
        return "\n".join(lines)


def _scale_llm_flag_delta(delta: int) -> int:
    scaled = int(round(delta * LLM_FLAG_SCORE_RATIO))
    if delta != 0 and scaled == 0:
        return 1 if delta > 0 else -1
    return scaled


def score(
    verification_results: list[VerificationResult],
    classification: ClassificationResult,
    entities: list[Entity],
    source: str = "",
    transcript: str = "",
    llm_assessment: LLMAssessment | None = None,
    rag_context: dict[str, Any] | None = None,
) -> ScamReport:
    """
    검증 결과를 종합하여 최종 스캠 리포트를 생성한다.

    Args:
        verification_results: 교차 검증 결과 리스트
        classification: 스캠 유형 분류 결과
        entities: 추출된 엔티티 리스트
        source: 원본 입력 소스
        transcript: STT 텍스트

    Returns:
        ScamReport 객체
    """
    total = 0
    triggered: list[FlagDetail] = []

    # 중복 플래그 방지: 같은 flag는 한 번만 가산
    seen_flags: set[str] = set()

    for vr in verification_results:
        if not vr.triggered:
            continue
        if vr.flag in seen_flags:
            continue
        seen_flags.add(vr.flag)

        delta = SCORING_RULES.get(vr.flag, 0)
        total += delta

        triggered.append(FlagDetail(
            flag=vr.flag,
            description=vr.flag_description,
            score_delta=delta,
            evidence=vr.evidence_snippets,
            source="rule",
        ))

    if llm_assessment is not None and not llm_assessment.error:
        for suggested in llm_assessment.suggested_flags:
            if suggested.confidence < LLM_FLAG_SCORE_THRESHOLD:
                continue
            if suggested.flag in seen_flags:
                continue
            seen_flags.add(suggested.flag)

            base_delta = SCORING_RULES.get(suggested.flag, 0)
            delta = _scale_llm_flag_delta(base_delta)
            total += delta
            triggered.append(FlagDetail(
                flag=suggested.flag,
                description=f"[LLM 보조] {suggested.reason}",
                score_delta=delta,
                evidence=[suggested.evidence] if suggested.evidence else [],
                source="llm",
            ))

    risk_level, risk_description = get_risk_level(total)

    return ScamReport(
        source=source,
        transcript_preview=transcript[:200] + ("..." if len(transcript) > 200 else ""),
        scam_type=classification.scam_type,
        classification_confidence=classification.confidence,
        is_uncertain=classification.is_uncertain,
        entities=[e.to_dict() for e in entities],
        total_score=total,
        risk_level=risk_level,
        risk_description=risk_description,
        triggered_flags=triggered,
        all_verifications=[vr.to_dict() for vr in verification_results],
        llm_assessment=llm_assessment.to_dict() if llm_assessment is not None else None,
        rag_context=rag_context,
    )
