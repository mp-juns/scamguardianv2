"""VirusTotal 응답 분류 + path traversal 방어."""

from __future__ import annotations


def test_classify_stats_malicious_threshold():
    from pipeline.safety import _classify_stats, ThreatLevel
    assert _classify_stats({"malicious": 0, "suspicious": 0}) == ThreatLevel.SAFE
    assert _classify_stats({"malicious": 1}) == ThreatLevel.SUSPICIOUS
    assert _classify_stats({"malicious": 0, "suspicious": 2}) == ThreatLevel.SUSPICIOUS
    assert _classify_stats({"malicious": 3}) == ThreatLevel.MALICIOUS
    assert _classify_stats({"malicious": 50}) == ThreatLevel.MALICIOUS


def test_url_id_is_base64_urlsafe_no_padding():
    from pipeline.safety import _vt_url_id
    out = _vt_url_id("https://example.com/test")
    assert "=" not in out
    assert "/" not in out
    assert "+" not in out


def test_admin_media_path_blocks_traversal():
    import api_server
    import pytest
    from fastapi import HTTPException

    for bad in [
        "/etc/passwd",
        ".scamguardian/uploads/../../etc/passwd",
        "/tmp/somewhere",
    ]:
        with pytest.raises(HTTPException) as exc:
            api_server._resolve_admin_media_path(bad)
        assert exc.value.status_code in (400, 404)
