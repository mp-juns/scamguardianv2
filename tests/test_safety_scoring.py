"""signal_detector 가 SafetyResult 받아 자동 검출 신호 추가하는지 검증.

Stage 3 reframe: 점수·등급 검증 → 검출 신호 list 검증.
점수·등급은 ScamGuardian 의 책임이 아니므로 (통합 기업이 자체 판정), 검출 사실만 확인.
"""

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


def test_malicious_file_triggers_malware_detected_signal():
    from pipeline import signal_detector
    safety = _make_safety(kind="file", level="malicious")
    report = signal_detector.detect(
        verification_results=[],
        classification=_empty_classification(),
        entities=[],
        safety_result=safety,
    )
    flags = [s.flag for s in report.detected_signals]
    assert "malware_detected" in flags
    # 검출된 신호의 학술/법적 근거가 함께 보고되는지
    sig = next(s for s in report.detected_signals if s.flag == "malware_detected")
    assert sig.rationale, "detected signal must carry rationale from FLAG_RATIONALE"
    assert sig.source, "detected signal must carry source from FLAG_RATIONALE"
    assert sig.detection_source == "safety"


def test_malicious_url_triggers_phishing_url_confirmed_signal():
    from pipeline import signal_detector
    safety = _make_safety(kind="url", level="malicious")
    report = signal_detector.detect(
        verification_results=[],
        classification=_empty_classification(),
        entities=[],
        safety_result=safety,
    )
    flags = [s.flag for s in report.detected_signals]
    assert "phishing_url_confirmed" in flags
    sig = next(s for s in report.detected_signals if s.flag == "phishing_url_confirmed")
    assert sig.detection_source == "safety"
    assert sig.rationale


def test_suspicious_file_triggers_low_confidence_signal():
    from pipeline import signal_detector
    safety = _make_safety(kind="file", level="suspicious")
    report = signal_detector.detect(
        verification_results=[],
        classification=_empty_classification(),
        entities=[],
        safety_result=safety,
    )
    flags = [s.flag for s in report.detected_signals]
    assert "suspicious_file_signal" in flags


def test_safe_file_produces_no_safety_signal():
    from pipeline import signal_detector
    safety = _make_safety(kind="file", level="safe", dets=0)
    report = signal_detector.detect(
        verification_results=[],
        classification=_empty_classification(),
        entities=[],
        safety_result=safety,
    )
    flags = [s.flag for s in report.detected_signals]
    assert "malware_detected" not in flags
    assert "suspicious_file_signal" not in flags
