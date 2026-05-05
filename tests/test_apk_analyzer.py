"""APK 정적 분석 (Lv 1 + Lv 2) 테스트.

⚠️ 진짜 악성 APK 는 절대 commit 하지 말 것.
이 테스트는 합성 minimal APK 또는 helper 함수 단위 검증만 사용.

진짜 악성 샘플 검증은 KISA 공개 분석 자료를 받아서 별도 fixture 디렉토리에
*수동으로만* 배치 (gitignore). 이 파일에서는 단위 + 합성 contract 만.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from pipeline.apk_analyzer import (
    APKBytecodeReport,
    APKStaticReport,
    _is_suspicious_impersonation,
    is_apk_file,
)


# ──────────────────────────────────
# is_apk_file — 입력 감지
# ──────────────────────────────────


def test_is_apk_file_recognizes_apk_extension(tmp_path):
    p = tmp_path / "sample.apk"
    p.write_bytes(b"PK\x03\x04dummy")
    assert is_apk_file(p) is True


def test_is_apk_file_recognizes_zip_magic_no_extension(tmp_path):
    """확장자 없어도 ZIP magic bytes 만 맞으면 APK 로 인식."""
    p = tmp_path / "noext"
    p.write_bytes(b"PK\x03\x04rest")
    assert is_apk_file(p) is True


def test_is_apk_file_rejects_text_file(tmp_path):
    p = tmp_path / "plain.txt"
    p.write_text("hello")
    assert is_apk_file(p) is False


def test_is_apk_file_rejects_missing(tmp_path):
    assert is_apk_file(tmp_path / "missing.apk") is False


def test_is_apk_file_rejects_directory(tmp_path):
    assert is_apk_file(tmp_path) is False


# ──────────────────────────────────
# _is_suspicious_impersonation — 패키지명 위장 휴리스틱
# ──────────────────────────────────


@pytest.mark.parametrize("pkg", [
    "com.kakao.talk.fake",                 # typo prefix + suffix
    "com.kakao.talk.v2",
    "com.nhn.android.search.official",
    "kr.co.shinhan.fake",                  # 은행 사칭
    "com.kbstar.kbbank.test",
    "com.example.banking_v2",              # 의심 suffix
    "com.example.app_official",
])
def test_suspicious_impersonation_detected(pkg):
    assert _is_suspicious_impersonation(pkg) is True


@pytest.mark.parametrize("pkg", [
    "com.kakao.talk",                      # 정확 일치 — 정상 (legitimate)
    "com.nhn.android.search",
    "com.totally.unrelated.app",           # 정상 앱과 무관
    "com.example.helloworld",
    "",                                    # 빈 문자열 — False
])
def test_suspicious_impersonation_clean(pkg):
    assert _is_suspicious_impersonation(pkg) is False


# ──────────────────────────────────
# 합성 minimal APK fixture — analyze_apk_static contract
# ──────────────────────────────────


def _make_minimal_apk(
    tmp_path: Path,
    *,
    package: str = "com.example.benign",
    permissions: list[str] | None = None,
) -> Path:
    """androguard 가 parse 가능한 최소 APK (ZIP) 합성.

    실제 androguard 가 manifest binary XML 디코드를 요구해서
    *정확한 manifest 분석 검증* 은 안 되지만, parse 실패 시 보수적
    error 응답이 정상으로 떨어지는지 contract 검증 가능.
    """
    apk_path = tmp_path / "synthetic.apk"
    with zipfile.ZipFile(apk_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 빈 manifest — androguard 가 parse 시도하다 실패할 가능성 큼
        zf.writestr("AndroidManifest.xml", b"")
        zf.writestr("classes.dex", b"")
    return apk_path


def test_analyze_apk_static_returns_structured_report_on_invalid_apk(tmp_path):
    """invalid manifest 라도 분석은 죽지 않고 report 반환 — error 필드만 채워짐."""
    from pipeline.apk_analyzer import analyze_apk_static

    apk = _make_minimal_apk(tmp_path)
    report = analyze_apk_static(apk)
    assert isinstance(report, APKStaticReport)
    # 이 합성 APK 는 권한이 없으므로 위험 권한 조합 검출 X
    assert "apk_dangerous_permissions_combo" not in report.detected_flags


def test_analyze_apk_bytecode_returns_structured_report_on_invalid_apk(tmp_path):
    """AnalyzeAPK 실패해도 빈 detected_flags 로 graceful return."""
    from pipeline.apk_analyzer import analyze_apk_bytecode

    apk = _make_minimal_apk(tmp_path)
    report = analyze_apk_bytecode(apk)
    assert isinstance(report, APKBytecodeReport)
    # parse 실패 시 빈 list (보수적)
    assert isinstance(report.detected_flags, list)


# ──────────────────────────────────
# Schema contract
# ──────────────────────────────────


def test_apk_static_report_to_dict_keys():
    rep = APKStaticReport(
        detected_flags=["apk_self_signed"],
        package_name="com.foo.bar",
        permissions=["android.permission.INTERNET"],
        is_self_signed=True,
    )
    d = rep.to_dict()
    assert set(d.keys()) == {"detected_flags", "package_name", "permissions", "is_self_signed", "error"}
    # 점수·등급 절대 없음 (Identity Boundary)
    assert "score" not in d
    assert "risk_level" not in d


def test_apk_bytecode_report_to_dict_keys():
    rep = APKBytecodeReport(detected_flags=["apk_sms_auto_send_code"])
    d = rep.to_dict()
    assert set(d.keys()) == {"detected_flags", "error"}


# ──────────────────────────────────
# signal_detector 통합 — APK report → DetectedSignal
# ──────────────────────────────────


def _empty_classification():
    from pipeline.classifier import ClassificationResult
    return ClassificationResult(scam_type="메신저 피싱", confidence=0.5, all_scores={}, is_uncertain=False)


def test_signal_detector_consumes_apk_static_result():
    """apk_static_result 의 flag 가 detected_signals 로 변환 + detection_source='static_lv1'."""
    from pipeline import signal_detector

    apk_rep = APKStaticReport(
        detected_flags=["apk_dangerous_permissions_combo", "apk_self_signed"],
        package_name="com.evil.fake",
        permissions=[],
        is_self_signed=True,
    )
    report = signal_detector.detect(
        verification_results=[],
        classification=_empty_classification(),
        entities=[],
        apk_static_result=apk_rep,
    )
    flags = [s.flag for s in report.detected_signals]
    assert "apk_dangerous_permissions_combo" in flags
    assert "apk_self_signed" in flags
    sig = next(s for s in report.detected_signals if s.flag == "apk_self_signed")
    assert sig.detection_source == "static_lv1"
    assert sig.rationale, "FLAG_RATIONALE 학술 근거 동반 필수"
    assert sig.source, "출처 기관 동반 필수"


def test_signal_detector_consumes_apk_bytecode_result():
    """apk_bytecode_result → detection_source='static_lv2'."""
    from pipeline import signal_detector

    bc_rep = APKBytecodeReport(
        detected_flags=["apk_sms_auto_send_code", "apk_impersonation_keywords"],
    )
    report = signal_detector.detect(
        verification_results=[],
        classification=_empty_classification(),
        entities=[],
        apk_bytecode_result=bc_rep,
    )
    flags = [s.flag for s in report.detected_signals]
    assert "apk_sms_auto_send_code" in flags
    assert "apk_impersonation_keywords" in flags
    sig = next(s for s in report.detected_signals if s.flag == "apk_sms_auto_send_code")
    assert sig.detection_source == "static_lv2"
    assert sig.rationale
    assert sig.source


def test_signal_detector_dedupes_same_flag_from_static_and_bytecode():
    """같은 flag 가 Lv1/Lv2 양쪽에서 들어와도 1번만."""
    from pipeline import signal_detector
    apk_rep = APKStaticReport(detected_flags=["apk_self_signed"])
    bc_rep = APKBytecodeReport(detected_flags=["apk_self_signed"])  # 비현실이지만 contract 검증
    report = signal_detector.detect(
        verification_results=[],
        classification=_empty_classification(),
        entities=[],
        apk_static_result=apk_rep,
        apk_bytecode_result=bc_rep,
    )
    flags = [s.flag for s in report.detected_signals]
    assert flags.count("apk_self_signed") == 1


def test_signal_detector_ignores_unknown_apk_flag():
    """알 수 없는 flag (DETECTED_FLAGS 외) 는 무시 — 환각 방지."""
    from pipeline import signal_detector
    bc_rep = APKBytecodeReport(detected_flags=["apk_completely_made_up_flag"])
    report = signal_detector.detect(
        verification_results=[],
        classification=_empty_classification(),
        entities=[],
        apk_bytecode_result=bc_rep,
    )
    flags = [s.flag for s in report.detected_signals]
    assert "apk_completely_made_up_flag" not in flags


# ──────────────────────────────────
# DETECTED_FLAGS / FLAG_LABELS_KO / FLAG_RATIONALE 매핑 검증
# ──────────────────────────────────


_APK_FLAGS = (
    "apk_dangerous_permissions_combo",
    "apk_self_signed",
    "apk_suspicious_package_name",
    "apk_sms_auto_send_code",
    "apk_call_state_listener",
    "apk_accessibility_abuse",
    "apk_impersonation_keywords",
    "apk_hardcoded_c2_url",
    "apk_string_obfuscation",
    "apk_device_admin_lock",
)


@pytest.mark.parametrize("flag", _APK_FLAGS)
def test_apk_flag_in_detected_flags(flag):
    from pipeline.config import DETECTED_FLAGS
    assert flag in DETECTED_FLAGS


@pytest.mark.parametrize("flag", _APK_FLAGS)
def test_apk_flag_has_korean_label(flag):
    from pipeline.config import FLAG_LABELS_KO
    assert flag in FLAG_LABELS_KO
    assert FLAG_LABELS_KO[flag], f"{flag}: 빈 라벨"


@pytest.mark.parametrize("flag", _APK_FLAGS)
def test_apk_flag_has_rationale_and_source(flag):
    """모든 APK flag 는 학술/법적 근거 + 출처 기관 동반 필수."""
    from pipeline.config import FLAG_RATIONALE
    info = FLAG_RATIONALE.get(flag, {})
    assert info.get("rationale"), f"{flag}: rationale 비어있음"
    assert info.get("source"), f"{flag}: source 비어있음"


# ──────────────────────────────────
# Lv 3 동적 분석 — 안전 정책 검증
# ──────────────────────────────────


_LV3_FLAGS = (
    "apk_runtime_c2_network_call",
    "apk_runtime_sms_intercepted",
    "apk_runtime_overlay_attack",
    "apk_runtime_credential_exfiltration",
    "apk_runtime_persistence_install",
)


@pytest.mark.parametrize("flag", _LV3_FLAGS)
def test_lv3_flag_in_detected_flags(flag):
    from pipeline.config import DETECTED_FLAGS, FLAG_LABELS_KO, FLAG_RATIONALE
    assert flag in DETECTED_FLAGS
    assert flag in FLAG_LABELS_KO
    assert FLAG_RATIONALE[flag]["rationale"]
    assert FLAG_RATIONALE[flag]["source"]


def test_dynamic_disabled_by_default(tmp_path, monkeypatch):
    """APK_DYNAMIC_ENABLED=0 (기본) 면 즉시 DISABLED 반환 — 호스트 절대 안 건드림."""
    monkeypatch.delenv("APK_DYNAMIC_ENABLED", raising=False)
    # 모듈 상수가 import 시 캐시 — monkeypatch 로 직접 재할당
    from pipeline import apk_analyzer
    monkeypatch.setattr(apk_analyzer, "APK_DYNAMIC_ENABLED", False)

    apk = tmp_path / "x.apk"
    apk.write_bytes(b"PK\x03\x04dummy")
    report = apk_analyzer.analyze_apk_dynamic(apk)
    assert report.status == apk_analyzer.APKDynamicStatus.DISABLED
    assert report.detected_flags == []
    assert "기본 비활성" in report.error


def test_dynamic_local_backend_hard_blocked(tmp_path, monkeypatch):
    """ENABLED=1 + backend=local 이어도 *항상* HARD BLOCK — 호스트 위험."""
    from pipeline import apk_analyzer
    monkeypatch.setattr(apk_analyzer, "APK_DYNAMIC_ENABLED", True)
    monkeypatch.setattr(apk_analyzer, "APK_DYNAMIC_BACKEND", "local")
    monkeypatch.setattr(apk_analyzer, "APK_DYNAMIC_REMOTE_URL", "")
    monkeypatch.setattr(apk_analyzer, "APK_DYNAMIC_REMOTE_TOKEN", "")

    apk = tmp_path / "x.apk"
    apk.write_bytes(b"PK\x03\x04dummy")
    report = apk_analyzer.analyze_apk_dynamic(apk)
    assert report.status == apk_analyzer.APKDynamicStatus.BLOCKED_LOCAL
    assert report.detected_flags == []
    assert "local execution forbidden" in report.error


def test_dynamic_auto_resolves_to_local_when_remote_env_missing(monkeypatch):
    """auto + REMOTE_URL/TOKEN 없음 → backend=local → HARD BLOCK."""
    from pipeline import apk_analyzer
    monkeypatch.setattr(apk_analyzer, "APK_DYNAMIC_BACKEND", "auto")
    monkeypatch.setattr(apk_analyzer, "APK_DYNAMIC_REMOTE_URL", "")
    monkeypatch.setattr(apk_analyzer, "APK_DYNAMIC_REMOTE_TOKEN", "")
    assert apk_analyzer._resolved_dynamic_backend() == "local"


def test_dynamic_auto_resolves_to_remote_when_url_and_token_set(monkeypatch):
    """auto + REMOTE_URL+TOKEN 둘 다 → remote."""
    from pipeline import apk_analyzer
    monkeypatch.setattr(apk_analyzer, "APK_DYNAMIC_BACKEND", "auto")
    monkeypatch.setattr(apk_analyzer, "APK_DYNAMIC_REMOTE_URL", "https://sandbox.example.com")
    monkeypatch.setattr(apk_analyzer, "APK_DYNAMIC_REMOTE_TOKEN", "secret")
    assert apk_analyzer._resolved_dynamic_backend() == "remote"


def test_dynamic_remote_not_configured_when_only_partial(tmp_path, monkeypatch):
    """ENABLED=1 + backend=remote 인데 URL/TOKEN 한쪽만 있으면 NOT_CONFIGURED."""
    from pipeline import apk_analyzer
    monkeypatch.setattr(apk_analyzer, "APK_DYNAMIC_ENABLED", True)
    monkeypatch.setattr(apk_analyzer, "APK_DYNAMIC_BACKEND", "remote")
    monkeypatch.setattr(apk_analyzer, "APK_DYNAMIC_REMOTE_URL", "https://sandbox.example.com")
    monkeypatch.setattr(apk_analyzer, "APK_DYNAMIC_REMOTE_TOKEN", "")  # 토큰 없음

    apk = tmp_path / "x.apk"
    apk.write_bytes(b"PK\x03\x04dummy")
    report = apk_analyzer.analyze_apk_dynamic(apk)
    assert report.status == apk_analyzer.APKDynamicStatus.NOT_CONFIGURED


def test_dynamic_remote_call_validates_unknown_flag(tmp_path, monkeypatch):
    """remote VM 가 알 수 없는 flag 보내도 무시 (DETECTED_FLAGS 외 차단)."""
    from pipeline import apk_analyzer

    monkeypatch.setattr(apk_analyzer, "APK_DYNAMIC_ENABLED", True)
    monkeypatch.setattr(apk_analyzer, "APK_DYNAMIC_BACKEND", "remote")
    monkeypatch.setattr(apk_analyzer, "APK_DYNAMIC_REMOTE_URL", "https://sandbox.example.com")
    monkeypatch.setattr(apk_analyzer, "APK_DYNAMIC_REMOTE_TOKEN", "secret")

    class _FakeResp:
        status_code = 200
        def json(self):
            return {
                "detected_flags": [
                    "apk_runtime_sms_intercepted",       # 유효
                    "apk_completely_made_up_flag",       # 환각 — 차단되어야
                    "apk_runtime_overlay_attack",        # 유효
                ],
                "observations": {"foo": "bar"},
            }

    def _fake_post(url, headers=None, files=None, timeout=None):
        return _FakeResp()

    import requests as _requests
    monkeypatch.setattr(_requests, "post", _fake_post)

    apk = tmp_path / "x.apk"
    apk.write_bytes(b"PK\x03\x04dummy")
    report = apk_analyzer.analyze_apk_dynamic(apk)
    assert report.status == apk_analyzer.APKDynamicStatus.COMPLETED
    assert "apk_runtime_sms_intercepted" in report.detected_flags
    assert "apk_runtime_overlay_attack" in report.detected_flags
    assert "apk_completely_made_up_flag" not in report.detected_flags


def test_dynamic_report_to_dict_keys():
    from pipeline.apk_analyzer import APKDynamicReport, APKDynamicStatus
    rep = APKDynamicReport(
        status=APKDynamicStatus.COMPLETED,
        detected_flags=["apk_runtime_sms_intercepted"],
        backend="remote",
        duration_ms=15000,
    )
    d = rep.to_dict()
    assert set(d.keys()) == {"status", "detected_flags", "backend", "duration_ms", "error", "raw_observations"}
    # 점수·등급 절대 없음 (Identity Boundary)
    assert "score" not in d
    assert "risk_level" not in d


def test_signal_detector_consumes_apk_dynamic_completed():
    """status=completed 일 때만 detected_flags 신호화 + detection_source='dynamic_lv3'."""
    from pipeline import signal_detector
    from pipeline.apk_analyzer import APKDynamicReport, APKDynamicStatus

    rep = APKDynamicReport(
        status=APKDynamicStatus.COMPLETED,
        detected_flags=["apk_runtime_sms_intercepted", "apk_runtime_overlay_attack"],
        backend="remote",
    )
    report = signal_detector.detect(
        verification_results=[],
        classification=_empty_classification(),
        entities=[],
        apk_dynamic_result=rep,
    )
    flags = [s.flag for s in report.detected_signals]
    assert "apk_runtime_sms_intercepted" in flags
    assert "apk_runtime_overlay_attack" in flags
    sig = next(s for s in report.detected_signals if s.flag == "apk_runtime_sms_intercepted")
    assert sig.detection_source == "dynamic_lv3"
    assert sig.rationale
    assert sig.source


def test_signal_detector_skips_apk_dynamic_disabled():
    """status=disabled 면 어떤 신호도 만들지 않음."""
    from pipeline import signal_detector
    from pipeline.apk_analyzer import APKDynamicReport, APKDynamicStatus

    rep = APKDynamicReport(status=APKDynamicStatus.DISABLED)
    report = signal_detector.detect(
        verification_results=[],
        classification=_empty_classification(),
        entities=[],
        apk_dynamic_result=rep,
    )
    runtime_flags = [s.flag for s in report.detected_signals if s.flag.startswith("apk_runtime_")]
    assert runtime_flags == []


def test_signal_detector_skips_apk_dynamic_blocked_local():
    """status=blocked_local 면 어떤 신호도 만들지 않음 — 호스트 위험 정책."""
    from pipeline import signal_detector
    from pipeline.apk_analyzer import APKDynamicReport, APKDynamicStatus

    rep = APKDynamicReport(
        status=APKDynamicStatus.BLOCKED_LOCAL,
        backend="local",
        error="local execution forbidden",
    )
    report = signal_detector.detect(
        verification_results=[],
        classification=_empty_classification(),
        entities=[],
        apk_dynamic_result=rep,
    )
    runtime_flags = [s.flag for s in report.detected_signals if s.flag.startswith("apk_runtime_")]
    assert runtime_flags == []
