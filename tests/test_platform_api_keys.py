"""API key 발급·조회·revoke + 월별 quota·RPM rate limit."""

from __future__ import annotations

import time

import pytest


def test_issue_and_lookup(sqlite_init):
    from platform_layer import api_keys

    rec = api_keys.issue(label="dev", monthly_quota=100, rpm_limit=5)
    assert rec["plaintext"].startswith("sg_")
    assert rec["status"] == "active"

    found = api_keys.lookup(rec["plaintext"])
    assert found is not None
    assert found["label"] == "dev"
    assert found["status"] == "active"


def test_lookup_unknown_key_returns_none(sqlite_init):
    from platform_layer import api_keys

    assert api_keys.lookup("sg_doesnotexist") is None
    assert api_keys.lookup("not-prefixed") is None
    assert api_keys.lookup("") is None


def test_revoke_marks_status(sqlite_init):
    from platform_layer import api_keys

    rec = api_keys.issue(label="to_revoke")
    assert api_keys.revoke(rec["id"]) is True

    after = api_keys.lookup(rec["plaintext"])
    assert after["status"] == "revoked"


def test_rpm_rate_limit_triggers_429(sqlite_init):
    from platform_layer import api_keys, rate_limit

    rec = api_keys.issue(label="rl", rpm_limit=2)
    rate_limit.check_and_consume(rec["id"], 2)
    rate_limit.check_and_consume(rec["id"], 2)
    with pytest.raises(rate_limit.RateLimitExceeded) as exc:
        rate_limit.check_and_consume(rec["id"], 2)
    assert exc.value.scope == "rpm"
    assert exc.value.retry_after >= 1


def test_monthly_quota_decrements(sqlite_init):
    from platform_layer import api_keys, rate_limit

    rec = api_keys.issue(label="quota", monthly_quota=3)
    info = rate_limit.consume_monthly_quota(rec["id"])
    assert info["remaining_month"] == 2
    info = rate_limit.consume_monthly_quota(rec["id"])
    assert info["remaining_month"] == 1
