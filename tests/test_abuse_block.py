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


def test_track_short_message_passes_but_counts():
    """'안녕' 같은 짧은 인사는 통과하지만 user_id 별로 누적된다.

    1번째: count=1 (경고 X — 1번째는 정상 인사)
    2번째~3번째: count=2,3 (경고 prepend — 호출자 책임)
    4번째: count=4 → blocked=True
    """
    from platform_layer import abuse_guard as ag
    user = "kakao_user_short"
    # 1~3회: count 증가, blocked=False
    for i in range(1, ag.VIOLATION_WARN_LIMIT + 1):
        info = ag.track_short_message(user, "안녕")
        assert info is not None
        assert info["count"] == i
        assert info["blocked"] is False, f"{i}회째 아직 블록 X"
    # 4회째: blocked
    info = ag.track_short_message(user, "안녕")
    assert info["blocked"] is True
    assert ag.block_status(user)[0] is True


def test_wrap_with_soft_warning_skips_first():
    """첫 호출(count=1)에는 wrap 안 함 — 정상 인사로 보이게."""
    from api_server import _wrap_with_soft_warning
    from pipeline import kakao_formatter

    base = kakao_formatter.format_welcome()
    base_outputs = len(base["template"]["outputs"])

    # count=1 → wrap 안 됨
    out = _wrap_with_soft_warning(base, {"count": 1, "blocked": False})
    assert len(out["template"]["outputs"]) == base_outputs

    # count=2 → 경고 prepend
    base2 = kakao_formatter.format_welcome()
    out = _wrap_with_soft_warning(base2, {"count": 2, "blocked": False})
    assert len(out["template"]["outputs"]) == base_outputs + 1
    assert "2/3" in out["template"]["outputs"][0]["simpleText"]["text"]


def test_track_short_message_skips_long_text():
    from platform_layer import abuse_guard as ag
    info = ag.track_short_message("u1", "이것은 충분히 긴 메시지로 분석 의도를 보입니다 박상철 본부장")
    assert info is None  # 임계 이상이면 트래킹 skip


def test_track_short_message_skips_no_user():
    from platform_layer import abuse_guard as ag
    info = ag.track_short_message("", "안녕")
    assert info is None
