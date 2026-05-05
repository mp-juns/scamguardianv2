"""DetectionReport schema contract — 응답 필드 엄격 검증.

Identity Boundary (CLAUDE.md): 점수·등급 필드는 응답 schema 에 절대 포함되면 안 됨.
이 테스트는 회귀 가드 — 누가 실수로 total_score / risk_level 같은 필드를 추가하면 즉시 실패.
"""

from __future__ import annotations

import pytest


def _empty_classification():
    from pipeline.classifier import ClassificationResult
    return ClassificationResult(scam_type="기타", confidence=0.5, all_scores={}, is_uncertain=False)


# ──────────────────────────────────
# 응답 schema — 금지된 필드 회귀 가드
# ──────────────────────────────────


@pytest.mark.parametrize("forbidden_field", [
    "total_score",
    "risk_level",
    "risk_description",
    "is_scam",
    "agent_verdict",
    "agent_reasoning",
    "triggered_flags",
])
def test_to_dict_does_not_expose_score_or_grade_fields(forbidden_field):
    """DetectionReport.to_dict() 응답에 점수·등급·"사기다" 단정 필드 절대 없음."""
    from pipeline import signal_detector
    report = signal_detector.detect(
        verification_results=[],
        classification=_empty_classification(),
        entities=[],
    )
    d = report.to_dict()
    assert forbidden_field not in d, (
        f"Identity Boundary 위반: '{forbidden_field}' 필드가 응답에 노출됨. "
        f"CLAUDE.md Forbidden Actions 참조."
    )


# ──────────────────────────────────
# 응답 schema — 필수 필드 contract
# ──────────────────────────────────


def test_to_dict_required_fields_present():
    """공개 응답 contract: detected_signals + summary + disclaimer + 필수 메타."""
    from pipeline import signal_detector
    report = signal_detector.detect(
        verification_results=[],
        classification=_empty_classification(),
        entities=[],
    )
    d = report.to_dict()
    required = [
        "detected_signals",
        "summary",
        "disclaimer",
        "scam_type",
        "classification_confidence",
        "is_uncertain",
        "entities",
        "verification_count",
    ]
    for k in required:
        assert k in d, f"DetectionReport 응답에 필수 필드 '{k}' 누락"


def test_disclaimer_states_no_judgment():
    """disclaimer 문구가 '판정을 내리지 않습니다' 명시."""
    from pipeline import signal_detector
    report = signal_detector.detect(
        verification_results=[],
        classification=_empty_classification(),
        entities=[],
    )
    assert "판정을 내리지 않습니다" in report.disclaimer
    assert "통합 기업" in report.disclaimer or "자체 판정 logic" in report.disclaimer


# ──────────────────────────────────
# DetectedSignal schema
# ──────────────────────────────────


def test_detected_signal_schema_keys():
    """DetectedSignal.to_dict() 키 contract — 검출 사실 + 학술 근거만."""
    from pipeline import signal_detector
    from pipeline.extractor import Entity
    from pipeline.verifier import VerificationResult

    vr = VerificationResult(
        entity=Entity(text="x", label="회사명 또는 기관명", score=0.5, start=0, end=1, source="test"),
        query="test",
        flag="urgent_transfer_demand",
        flag_description="즉각 송금 요구 검출",
        triggered=True,
        evidence_snippets=["급한 송금"],
    )
    report = signal_detector.detect(
        verification_results=[vr],
        classification=_empty_classification(),
        entities=[],
    )
    sig_dict = report.detected_signals[0].to_dict()
    expected_keys = {
        "flag", "label_ko", "rationale", "source",
        "detection_source", "evidence", "description",
    }
    assert set(sig_dict.keys()) == expected_keys
    # 점수 필드 절대 없음
    assert "score" not in sig_dict
    assert "score_delta" not in sig_dict


# ──────────────────────────────────
# config.py — 폐기된 심볼 회귀 가드
# ──────────────────────────────────


def test_pipeline_config_has_no_deprecated_symbols():
    """pipeline.config 에서 RISK_LEVELS / get_risk_level / SCORING_RULES / LLM_FLAG_SCORE_RATIO
    재도입되지 않았는지 회귀 가드. 누군가 cherry-pick 으로 되돌리면 즉시 실패."""
    from pipeline import config as pcfg
    deprecated = ["RISK_LEVELS", "get_risk_level", "SCORING_RULES", "LLM_FLAG_SCORE_RATIO"]
    for name in deprecated:
        assert not hasattr(pcfg, name), (
            f"deprecated symbol '{name}' 재도입됨. Identity Boundary 위반 — Stage 2 Forbidden Actions."
        )


def test_detected_flags_is_list_not_dict():
    """DETECTED_FLAGS 는 list[str] (점수 mapping 이 아님 — 검출 가능 신호 list 만)."""
    from pipeline import config as pcfg
    assert isinstance(pcfg.DETECTED_FLAGS, list)
    assert all(isinstance(f, str) for f in pcfg.DETECTED_FLAGS)
    # FLAG_LABELS_KO / FLAG_RATIONALE 은 dict 그대로 (한국어 라벨 + 학술 근거)
    assert isinstance(pcfg.FLAG_LABELS_KO, dict)
    assert isinstance(pcfg.FLAG_RATIONALE, dict)


def test_every_detected_flag_has_korean_label_and_rationale():
    """모든 검출 가능 flag 는 한국어 라벨 + 학술 근거 매핑이 있어야 함."""
    from pipeline import config as pcfg
    for flag in pcfg.DETECTED_FLAGS:
        assert flag in pcfg.FLAG_LABELS_KO, f"{flag}: FLAG_LABELS_KO 누락"
        assert flag in pcfg.FLAG_RATIONALE, f"{flag}: FLAG_RATIONALE 누락"
        info = pcfg.FLAG_RATIONALE[flag]
        assert info.get("rationale"), f"{flag}: rationale 비어있음"
        assert info.get("source"), f"{flag}: source 비어있음"
