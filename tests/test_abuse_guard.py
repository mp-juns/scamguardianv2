"""abuse_guard — 길이 cap·반복·gibberish·duplicate 차단."""

from __future__ import annotations


def setup_function():
    from platform_layer import abuse_guard
    abuse_guard.reset_state()


def test_normal_korean_passes():
    from platform_layer import abuse_guard
    text = "안녕하세요 박상철 본부장입니다. 솔라텍 바이오 상장 예정으로 연 30% 수익 보장입니다."
    assert abuse_guard.check(text) is None


def test_too_short_rejected():
    from platform_layer import abuse_guard
    rej = abuse_guard.check("짧음")
    assert rej is not None and rej.code == "MIN_LEN"


def test_too_long_rejected(monkeypatch):
    from platform_layer import abuse_guard
    text = "투자 사기 의심" * 1000
    rej = abuse_guard.check(text)
    assert rej is not None and rej.code == "MAX_LEN"


def test_repetitive_rejected():
    from platform_layer import abuse_guard
    rej = abuse_guard.check("ㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋ")
    assert rej is not None and rej.code == "REPETITIVE"


def test_unique_chars_too_few():
    from platform_layer import abuse_guard
    rej = abuse_guard.check("ababababababababab")
    assert rej is not None and rej.code == "REPETITIVE"


def test_only_emojis_rejected():
    from platform_layer import abuse_guard
    rej = abuse_guard.check("🌟🌟🌟🌟🌟🌟🌟🌟🌟🌟🌟🌟🌟🌟")
    assert rej is not None and rej.code in ("GIBBERISH", "REPETITIVE")


def test_duplicate_throttle_after_5_in_window(sqlite_init):
    from platform_layer import abuse_guard
    text = "투자해서 9배 수익 보장이라는데 의심돼요. 이거 사기인가요?"
    for _ in range(5):
        assert abuse_guard.check(text, key_id="anon") is None
    rej = abuse_guard.check(text, key_id="anon")
    assert rej is not None and rej.code == "DUPLICATE"


def test_duplicate_throttle_isolated_per_key(sqlite_init):
    from platform_layer import abuse_guard
    text = "투자해서 9배 수익 보장이라는데 의심돼요. 이거 사기인가요?"
    for _ in range(5):
        assert abuse_guard.check(text, key_id="key_A") is None
    # 같은 텍스트 다른 키 — 통과해야 함
    assert abuse_guard.check(text, key_id="key_B") is None
