"""위반 누적 → 자동 블록."""

from __future__ import annotations


def setup_function():
    from platform_layer import abuse_guard
    abuse_guard.reset_state()


def test_warns_until_threshold_then_blocks():
    from platform_layer import abuse_guard as ag
    user = "kakao_user_X"
    # 1~3회: MIN_LEN 거부지만 BLOCKED 아님
    for i in range(1, ag.VIOLATION_WARN_LIMIT + 1):
        rej = ag.guard("ㅋ", user_id=user)   # MIN_LEN 위반
        assert rej is not None
        assert rej.code == "MIN_LEN"
        assert "경고" in rej.message
        blocked, _ = ag.block_status(user)
        assert blocked is False, f"{i}회째: 아직 블록되면 안 됨"
    # 4회째: BLOCKED
    rej = ag.guard("ㅋ", user_id=user)
    assert rej is not None
    assert rej.code == "BLOCKED"
    blocked, remaining = ag.block_status(user)
    assert blocked is True
    assert 0 < remaining <= ag.BLOCK_DURATION_SEC


def test_blocked_user_subsequent_calls_all_rejected():
    from platform_layer import abuse_guard as ag
    user = "kakao_user_Y"
    # 4회 위반 → 블록
    for _ in range(ag.VIOLATION_WARN_LIMIT + 1):
        ag.guard("ㅋ", user_id=user)
    # 정상 입력도 블록 상태에선 BLOCKED
    rej = ag.guard("정상적인 의심 메시지 보내드려요", user_id=user)
    assert rej is not None and rej.code == "BLOCKED"


def test_unblock_clears_state():
    from platform_layer import abuse_guard as ag
    user = "kakao_user_Z"
    for _ in range(ag.VIOLATION_WARN_LIMIT + 1):
        ag.guard("ㅋ", user_id=user)
    assert ag.block_status(user)[0] is True
    ag.unblock(user)
    blocked, _ = ag.block_status(user)
    assert blocked is False
    # 다음 정상 입력 통과
    assert ag.guard("정상적인 분석 요청입니다", user_id=user) is None


def test_anonymous_no_block_tracking():
    from platform_layer import abuse_guard as ag
    # user_id 없으면 위반 누적 X — 그냥 reject 만
    for _ in range(10):
        rej = ag.guard("ㅋ")
        assert rej is not None and rej.code == "MIN_LEN"
    assert ag.list_blocks() == []
