"""
ScamGuardian v2 — 스캠 유형 분류 모듈
mDeBERTa zero-shot classification + 키워드 부스팅으로 스캠 유형을 판별한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from transformers import pipeline as hf_pipeline

from pipeline.config import (
    CLASSIFICATION_THRESHOLD,
    KEYWORD_BOOST,
    KEYWORD_BOOST_WEIGHT,
    KEYWORD_NO_MATCH_PENALTY,
    MODELS,
    SCAM_TYPE_DESCRIPTIONS,
)

_classifier = None


@dataclass
class ClassificationResult:
    scam_type: str
    confidence: float
    all_scores: dict[str, float] = field(default_factory=dict)
    is_uncertain: bool = False


def _get_classifier():
    global _classifier
    if _classifier is None:
        _classifier = hf_pipeline(
            "zero-shot-classification",
            model=MODELS["classifier"],
            device="cpu",
        )
    return _classifier


def _compute_keyword_boost(text: str) -> dict[str, float]:
    """텍스트 내 키워드 매칭 비율로 각 스캠 유형의 부스트/감점을 계산한다."""
    text_lower = text.lower()
    boosts: dict[str, float] = {}
    for scam_type, keywords in KEYWORD_BOOST.items():
        matched = sum(1 for kw in keywords if kw in text_lower)
        if matched == 0:
            boosts[scam_type] = -KEYWORD_NO_MATCH_PENALTY
        else:
            ratio = matched / len(keywords) if keywords else 0
            boosts[scam_type] = min(ratio * KEYWORD_BOOST_WEIGHT * 3, KEYWORD_BOOST_WEIGHT)
    return boosts


def classify(text: str) -> ClassificationResult:
    """
    STT 텍스트를 입력받아 스캠 유형을 분류한다.
    NLI 스코어 + 키워드 부스팅을 결합하여 최종 판정한다.
    """
    clf = _get_classifier()

    truncated = text[:2000]
    descriptive_labels = list(SCAM_TYPE_DESCRIPTIONS.keys())

    result = clf(
        truncated,
        descriptive_labels,
        hypothesis_template="이 내용은 {}하는 것이다.",
        multi_label=False,
    )

    # NLI 스코어를 짧은 이름으로 매핑
    nli_scores: dict[str, float] = {}
    for label, score in zip(result["labels"], result["scores"]):
        short_name = SCAM_TYPE_DESCRIPTIONS[label]
        nli_scores[short_name] = score

    # 키워드 부스팅 적용
    boosts = _compute_keyword_boost(truncated)
    combined: dict[str, float] = {}
    for scam_type in nli_scores:
        combined[scam_type] = nli_scores[scam_type] + boosts.get(scam_type, 0)

    # 결합 점수 기준 재정렬
    sorted_types = sorted(combined.items(), key=lambda x: -x[1])
    top_type = sorted_types[0][0]
    top_score = sorted_types[0][1]

    # 항상 확률처럼 해석 가능한 [0, 1] 점수로 정규화한다.
    # total이 0 이하가 될 수 있으므로 min-shift 후 합으로 나눈다.
    min_score = min(combined.values())
    shifted = {k: v - min_score for k, v in combined.items()}
    shifted_total = sum(shifted.values())
    if shifted_total == 0:
        # 모든 점수가 동일하면 균등 분포로 처리
        uniform = 1.0 / len(shifted) if shifted else 0.0
        all_scores = {k: uniform for k in shifted}
    else:
        all_scores = {k: v / shifted_total for k, v in shifted.items()}

    return ClassificationResult(
        scam_type=top_type,
        confidence=all_scores[top_type],
        all_scores=all_scores,
        is_uncertain=all_scores[top_type] < CLASSIFICATION_THRESHOLD,
    )
