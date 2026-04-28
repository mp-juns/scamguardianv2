"""가격표 + 비용 기록·집계 검증."""

from __future__ import annotations


def test_claude_sonnet_pricing():
    from platform_layer import pricing
    cost = pricing.claude_cost("claude-sonnet-4-6", 1_000_000, 0)
    assert cost == 3.0
    cost = pricing.claude_cost("claude-sonnet-4-6", 0, 1_000_000)
    assert cost == 15.0


def test_whisper_pricing_per_minute():
    from platform_layer import pricing
    assert pricing.whisper_cost(60.0) == 0.006
    assert abs(pricing.whisper_cost(30.0) - 0.003) < 1e-9


def test_unknown_claude_model_falls_back_to_sonnet():
    from platform_layer import pricing
    cost = pricing.claude_cost("unknown-model", 1_000_000, 0)
    assert cost == 3.0


def test_cost_record_and_aggregate(sqlite_init):
    from platform_layer import api_keys, cost
    from db import repository

    rec = api_keys.issue(label="costtest")
    cost.set_context(request_id="r1", api_key_id=rec["id"])
    cost.record_claude("claude-sonnet-4-6", 1000, 200)
    cost.record_serper(2)
    cost.record_virustotal(1)
    cost.clear_context()

    agg = repository.aggregate_costs(days=1)
    providers = {p["provider"]: p for p in agg["by_provider"]}
    assert "claude" in providers
    assert "serper" in providers
    assert providers["claude"]["usd"] > 0
    assert agg["total"]["calls"] == 3
