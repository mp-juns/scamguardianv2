"""Phase 0.5 샌드박스 디토네이션 파서/스코어링 단위 테스트.

실제 Docker/Playwright 호출은 안 함 — JSON output 파싱과 scorer 통합만 검증.
"""

from __future__ import annotations

import json
from pathlib import Path


def _parse(json_str: str, target: str = "https://example.com/evil"):
    from pipeline.sandbox import _parse_detonate_output
    return _parse_detonate_output(json_str, target)


def test_password_form_parsed():
    raw = json.dumps({
        "status": "completed",
        "final_url": "https://example.com/evil",
        "redirect_chain": [],
        "title": "Login",
        "screenshot_path": "/tmp/x.png",
        "has_login_form": True,
        "has_password_field": True,
        "sensitive_form_fields": ["password"],
        "download_attempts": [],
        "duration_ms": 1234,
    })
    r = _parse(raw)
    assert r.has_password_field is True
    assert r.is_dangerous is True
    assert r.cloaking_detected is False
    assert r.excessive_redirects is False
    assert r.duration_ms == 1234


def test_cloaking_detected_when_final_domain_differs():
    raw = json.dumps({
        "status": "completed",
        "final_url": "https://different.evil/landing",
        "redirect_chain": ["https://example.com/r1", "https://example.com/r2"],
        "has_login_form": False,
        "has_password_field": False,
        "download_attempts": [],
    })
    r = _parse(raw, target="https://example.com/evil")
    assert r.cloaking_detected is True
    assert r.is_dangerous is True


def test_excessive_redirects_threshold():
    raw = json.dumps({
        "status": "completed",
        "final_url": "https://example.com/final",
        "redirect_chain": [
            "https://example.com/1",
            "https://example.com/2",
            "https://example.com/3",
            "https://example.com/4",
        ],
        "has_login_form": False,
        "has_password_field": False,
        "download_attempts": [],
    })
    r = _parse(raw)
    assert r.excessive_redirects is True


def test_three_redirects_not_excessive():
    raw = json.dumps({
        "status": "completed",
        "final_url": "https://example.com/final",
        "redirect_chain": [
            "https://example.com/1",
            "https://example.com/2",
            "https://example.com/3",
        ],
        "has_login_form": False,
        "has_password_field": False,
        "download_attempts": [],
    })
    r = _parse(raw)
    assert r.excessive_redirects is False


def test_invalid_json_returns_error_status():
    r = _parse("not-json{")
    assert r.status.value == "error"
    assert r.error and "JSON parse" in r.error


def test_sensitive_field_detector():
    """input 속성 리스트 → 민감 라벨 추출 (스크립트 내부 함수)."""
    from pipeline.sandbox_detonate import _detect_sensitive_fields
    fields = [
        {"type": "password"},
        {"type": "text", "name": "ssn", "id": "x"},
        {"type": "text", "placeholder": "OTP 코드"},
        {"type": "email"},
    ]
    sensitive = _detect_sensitive_fields(fields)
    assert "password" in sensitive
    assert "주민번호" in sensitive
    assert "OTP" in sensitive


def test_signal_detector_password_form_signal():
    """샌드박스가 비밀번호폼 발견 → sandbox_password_form_detected 신호 검출 (점수 X)."""
    from pipeline import signal_detector
    from pipeline.classifier import ClassificationResult
    from pipeline.sandbox import SandboxResult, SandboxStatus

    sb = SandboxResult(
        target_url="https://evil.example/login",
        status=SandboxStatus.COMPLETED,
        has_login_form=True,
        has_password_field=True,
        sensitive_form_fields=["password"],
    )
    cls = ClassificationResult(scam_type="피싱", confidence=0.7, all_scores={}, is_uncertain=False)
    report = signal_detector.detect(
        verification_results=[],
        classification=cls,
        entities=[],
        source="https://evil.example/login",
        transcript="",
        sandbox_result=sb,
    )
    flag_names = [s.flag for s in report.detected_signals]
    assert "sandbox_password_form_detected" in flag_names
    pwd_signal = next(s for s in report.detected_signals if s.flag == "sandbox_password_form_detected")
    assert pwd_signal.detection_source == "sandbox"
    assert pwd_signal.rationale, "must carry rationale (학술 근거)"
    assert pwd_signal.source, "must carry source (출처 기관)"
    # ✅ 점수 필드 자체가 응답 schema 에 없음을 확인 — Identity Boundary
    assert not hasattr(pwd_signal, "score_delta")


def test_signal_detector_drive_by_download_signal():
    from pipeline import signal_detector
    from pipeline.classifier import ClassificationResult
    from pipeline.sandbox import SandboxResult, SandboxStatus

    sb = SandboxResult(
        target_url="https://evil.example/file.apk",
        status=SandboxStatus.COMPLETED,
        download_attempts=[{"suggested_filename": "court.apk", "url": "https://evil.example/file.apk"}],
    )
    cls = ClassificationResult(scam_type="피싱", confidence=0.5, all_scores={}, is_uncertain=False)
    report = signal_detector.detect(
        verification_results=[], classification=cls, entities=[],
        source="https://evil.example/file.apk", transcript="",
        sandbox_result=sb,
    )
    flag_names = [s.flag for s in report.detected_signals]
    assert "sandbox_auto_download_attempt" in flag_names


def test_signal_detector_skips_when_sandbox_status_not_completed():
    """status=error 면 어떤 신호도 검출되면 안 됨."""
    from pipeline import signal_detector
    from pipeline.classifier import ClassificationResult
    from pipeline.sandbox import SandboxResult, SandboxStatus

    sb = SandboxResult(
        target_url="https://x.example",
        status=SandboxStatus.ERROR,
        has_password_field=True,
        download_attempts=[{"suggested_filename": "x.apk"}],
    )
    cls = ClassificationResult(scam_type="기타", confidence=0.3, all_scores={}, is_uncertain=False)
    report = signal_detector.detect(
        verification_results=[], classification=cls, entities=[],
        source="https://x.example", transcript="",
        sandbox_result=sb,
    )
    sandbox_signals = [s for s in report.detected_signals if s.detection_source == "sandbox"]
    assert sandbox_signals == []


def test_backend_resolves_to_local_when_no_remote_env(monkeypatch):
    """REMOTE_URL/TOKEN 미설정이면 _resolved_backend == local."""
    monkeypatch.delenv("SANDBOX_REMOTE_URL", raising=False)
    monkeypatch.delenv("SANDBOX_REMOTE_TOKEN", raising=False)
    # 모듈 상수가 import 시 캐시되므로 직접 재할당
    from pipeline import sandbox as sb
    monkeypatch.setattr(sb, "SANDBOX_BACKEND", "auto")
    monkeypatch.setattr(sb, "SANDBOX_REMOTE_URL", "")
    monkeypatch.setattr(sb, "SANDBOX_REMOTE_TOKEN", "")
    assert sb._resolved_backend() == "local"


def test_backend_resolves_to_remote_when_url_and_token_set(monkeypatch):
    from pipeline import sandbox as sb
    monkeypatch.setattr(sb, "SANDBOX_BACKEND", "auto")
    monkeypatch.setattr(sb, "SANDBOX_REMOTE_URL", "https://sandbox.example.com")
    monkeypatch.setattr(sb, "SANDBOX_REMOTE_TOKEN", "secret")
    assert sb._resolved_backend() == "remote"


def test_backend_explicit_local_overrides_env(monkeypatch):
    """SANDBOX_BACKEND=local 이면 REMOTE 설정 있어도 local."""
    from pipeline import sandbox as sb
    monkeypatch.setattr(sb, "SANDBOX_BACKEND", "local")
    monkeypatch.setattr(sb, "SANDBOX_REMOTE_URL", "https://sandbox.example.com")
    monkeypatch.setattr(sb, "SANDBOX_REMOTE_TOKEN", "secret")
    assert sb._resolved_backend() == "local"


def test_screenshot_base64_decoded_to_local_file(tmp_path, monkeypatch):
    """원격에서 base64 로 받은 스크린샷이 호스트 파일시스템에 저장돼야 한다."""
    import base64
    from pipeline import sandbox as sb
    monkeypatch.setattr(sb, "SANDBOX_OUTPUT_DIR", tmp_path)

    fake_png = b"\x89PNG\r\n\x1a\nfakepng_payload"
    raw = json.dumps({
        "status": "completed",
        "final_url": "https://x.example",
        "redirect_chain": [],
        "has_login_form": False,
        "has_password_field": False,
        "download_attempts": [],
        "screenshot_path": "/sandbox/out/screenshot.png",  # 호스트엔 없음
        "screenshot_base64": base64.b64encode(fake_png).decode(),
    })
    result = sb._parse_detonate_output(raw, "https://x.example")
    assert result.screenshot_path is not None
    saved = Path(result.screenshot_path)
    assert saved.exists()
    assert saved.read_bytes() == fake_png


def test_invalid_url_returns_error_without_calling_backend(monkeypatch):
    """detonate_url 가 http(s) 아닌 입력 받으면 백엔드 호출 0회 + ERROR."""
    from pipeline import sandbox as sb
    called = {"local": False, "remote": False}
    monkeypatch.setattr(sb, "_detonate_local",
                        lambda u: (called.__setitem__("local", True) or sb.SandboxResult(target_url=u)))
    monkeypatch.setattr(sb, "_detonate_remote",
                        lambda u: (called.__setitem__("remote", True) or sb.SandboxResult(target_url=u)))
    result = sb.detonate_url("ftp://x.example")
    assert result.status.value == "error"
    assert result.error == "invalid url"
    assert called == {"local": False, "remote": False}


def test_sandbox_result_in_report_dict():
    """DetectionReport.to_dict() 에 sandbox_check 필드 포함."""
    from pipeline import signal_detector
    from pipeline.classifier import ClassificationResult
    from pipeline.sandbox import SandboxResult, SandboxStatus

    sb = SandboxResult(
        target_url="https://x.example",
        status=SandboxStatus.COMPLETED,
        final_url="https://x.example/landing",
        title="Test",
    )
    cls = ClassificationResult(scam_type="기타", confidence=0.5, all_scores={}, is_uncertain=False)
    report = signal_detector.detect(
        verification_results=[], classification=cls, entities=[],
        source="https://x.example", transcript="",
        sandbox_result=sb,
    )
    d = report.to_dict()
    assert "sandbox_check" in d
    assert d["sandbox_check"]["target_url"] == "https://x.example"
    assert d["sandbox_check"]["status"] == "completed"
    # Identity Boundary — 응답 schema 에서 점수·등급 필드 절대 없음
    assert "total_score" not in d
    assert "risk_level" not in d
    assert "is_scam" not in d
    assert "agent_verdict" not in d
    assert "detected_signals" in d
