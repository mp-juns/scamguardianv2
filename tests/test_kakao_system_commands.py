"""시스템 명령어("결과확인", "사용법", "초기화" 등)는 어뷰즈 소프트 트래커에서 제외돼야 한다.

배경: 결과확인(4자), 사용법(3자) 모두 SOFT_LEN_THRESHOLD(10) 미만이라
track_short_message 가 위반으로 잘못 카운트하던 버그가 있었다. 팀원이 결과확인을
3~4회 누르자 자동 차단된 케이스 발생 → _is_system_command 화이트리스트 도입.
"""

from __future__ import annotations


def test_result_confirm_recognized_as_system_command():
    from api_server import _is_system_command
    # 정확 매칭
    assert _is_system_command("결과확인")
    assert _is_system_command("결과 확인")
    # 부분 매칭 (자연 표현)
    assert _is_system_command("결과 알려줘")
    assert _is_system_command("분석 다됐어?")
    assert _is_system_command("결과 보여줘")


def test_help_and_reset_recognized():
    from api_server import _is_system_command
    assert _is_system_command("사용법")
    assert _is_system_command("도움말")
    assert _is_system_command("help")
    assert _is_system_command("?")
    assert _is_system_command("분석 초기화")
    assert _is_system_command("초기화")
    assert _is_system_command("리셋")
    assert _is_system_command("reset")


def test_skip_phrases_recognized():
    from api_server import _is_system_command
    assert _is_system_command("스킵")
    assert _is_system_command("skip")
    assert _is_system_command("그냥 분석")


def test_normal_input_not_system_command():
    from api_server import _is_system_command
    assert not _is_system_command("안녕")
    assert not _is_system_command("ㅋㅋㅋ")
    assert not _is_system_command("이거 사기인가요")
    assert not _is_system_command("https://example.com 의심돼요")
    assert not _is_system_command("")
    assert not _is_system_command("   ")
