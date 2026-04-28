"""월별 USD cap circuit breaker."""

from __future__ import annotations

import pytest


def test_usd_cap_below_quota_passes(sqlite_init):
    from platform_layer import api_keys, cost, rate_limit
    rec = api_keys.issue(label="usd-test", monthly_usd_quota=10.0)
    cost.set_context(request_id="r1", api_key_id=rec["id"])
    cost.record_claude("claude-sonnet-4-6", 1000, 200)  # ~$0.0063
    cost.clear_context()
    rate_limit.check_monthly_usd_cap(rec["id"], 10.0)  # 통과


def test_usd_cap_blocks_when_over(sqlite_init):
    from platform_layer import api_keys, cost, rate_limit
    rec = api_keys.issue(label="usd-block", monthly_usd_quota=0.001)
    cost.set_context(request_id="r2", api_key_id=rec["id"])
    cost.record_claude("claude-sonnet-4-6", 1000, 200)  # ~$0.0063 > 0.001
    cost.clear_context()
    with pytest.raises(rate_limit.RateLimitExceeded) as exc:
        rate_limit.check_monthly_usd_cap(rec["id"], 0.001)
    assert exc.value.scope == "usd"


def test_zero_quota_means_unlimited(sqlite_init):
    from platform_layer import api_keys, cost, rate_limit
    rec = api_keys.issue(label="unlim", monthly_usd_quota=0.0)
    cost.set_context(request_id="r3", api_key_id=rec["id"])
    for _ in range(5):
        cost.record_claude("claude-sonnet-4-6", 10000, 5000)
    cost.clear_context()
    rate_limit.check_monthly_usd_cap(rec["id"], 0.0)  # 무제한 — 통과
