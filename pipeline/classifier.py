"""
ScamGuardian v2 — 스캠 유형 분류 모듈
mDeBERTa zero-shot classification + 키워드 부스팅으로 스캠 유형을 판별한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    pipeline as hf_pipeline,
)

from pipeline.config import (
    CLASSIFICATION_THRESHOLD,
    KEYWORD_BOOST,
    KEYWORD_BOOST_WEIGHT,
    KEYWORD_NO_MATCH_PENALTY,
    MODELS,
    get_runtime_scam_taxonomy,
)

_classifier = None


def _resolve_local_hf_snapshot(model_id: str) -> str | None:
    cache_root = Path.home() / ".cache" / "huggingface" / "hub"
    model_dir = cache_root / f"models--{model_id.replace('/', '--')}"
    refs_main = model_dir / "refs" / "main"
    if not refs_main.exists():
        return None

    revision = refs_main.read_text().strip()
    snapshot_dir = model_dir / "snapshots" / revision
    return str(snapshot_dir) if snapshot_dir.exists() else None


@dataclass
class ClassificationResult:
    scam_type: str
    confidence: float
    all_scores: dict[str, float] = field(default_factory=dict)
    is_uncertain: bool = False


def _get_classifier():
    global _classifier
    if _classifier is None:
        model_source = _resolve_local_hf_snapshot(MODELS["classifier"]) or MODELS["classifier"]
        tokenizer = AutoTokenizer.from_pretrained(model_source, local_files_only=model_source != MODELS["classifier"])
        model = AutoModelForSequenceClassification.from_pretrained(
            model_source,
            local_files_only=model_source != MODELS["classifier"],
        )
        _classifier = hf_pipeline(
            "zero-shot-classification",
            model=model,
            tokenizer=tokenizer,
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
    taxonomy = get_runtime_scam_taxonomy()

    truncated = text[:2000]
    descriptive_labels = list(taxonomy["descriptions"].keys())

    result = clf(
        truncated,
        descriptive_labels,
        hypothesis_template="이 내용은 {}하는 것이다.",
        multi_label=False,
    )

    # NLI 스코어를 짧은 이름으로 매핑
    nli_scores: dict[str, float] = {}
    for label, score in zip(result["labels"], result["scores"]):
        short_name = taxonomy["descriptions"][label]
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
