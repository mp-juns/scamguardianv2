"""scorer 가 SafetyResult 받아 자동 플래그 발동 + 점수 가산하는지 검증."""

from __future__ import annotations


def _make_safety(*, kind: str, level: str, dets: int = 5):
    from pipeline.safety import SafetyResult, ThreatLevel
    return SafetyResult(
        target_kind=kind,
        target="test",
        threat_level=ThreatLevel(level),
        detections=dets,
        total_engines=70,
        threat_categories=["malware"],
    )


def _empty_classification():
    from pipeline.classifier import ClassificationResult
    return ClassificationResult(scam_type="메신저 피싱", confidence=0.0, all_scores={}, is_uncertain=True)


def test_malicious_file_triggers_malware_detected_80():
    from pipeline import scorer
    safety = _make_safety(kind="file", level="malicious")
    report = scorer.score(
        verification_results=[],
        classification=_empty_classification(),
        entities=[],
        safety_result=safety,
    )
    flags = [f.flag for f in report.triggered_flags]
    assert "malware_detected" in flags
    assert report.total_score >= 80
    assert report.risk_level == "매우 위험"


def test_malicious_url_triggers_phishing_url_confirmed_75():
    from pipeline import scorer
    safety = _make_safety(kind="url", level="malicious")
    report = scorer.score(
        verification_results=[],
        classification=_empty_classification(),
        entities=[],
        safety_result=safety,
    )
    flags = [f.flag for f in report.triggered_flags]
    assert "phishing_url_confirmed" in flags
    assert report.total_score >= 75
    assert report.risk_level == "매우 위험"


def test_suspicious_file_triggers_low_score_signal():
    from pipeline import scorer
    safety = _make_safety(kind="file", level="suspicious")
    report = scorer.score(
        verification_results=[],
        classification=_empty_classification(),
        entities=[],
        safety_result=safety,
    )
    flags = [f.flag for f in report.triggered_flags]
    assert "suspicious_file_signal" in flags
    assert report.total_score >= 25


def test_safe_file_no_safety_flag():
    from pipeline import scorer
    safety = _make_safety(kind="file", level="safe", dets=0)
    report = scorer.score(
        verification_results=[],
        classification=_empty_classification(),
        entities=[],
        safety_result=safety,
    )
    flags = [f.flag for f in report.triggered_flags]
    assert "malware_detected" not in flags
    assert "suspicious_file_signal" not in flags
