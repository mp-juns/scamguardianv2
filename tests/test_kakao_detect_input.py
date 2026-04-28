"""카카오 webhook input 분류 — text/url/video/image/pdf/file 정확한 라우팅."""

from __future__ import annotations


def _detect(utterance, params):
    from api_server import _kakao_detect_input
    return _kakao_detect_input(utterance, params)


def test_pure_text_routes_to_text():
    src, kind = _detect("안녕 투자 9배 보장", {})
    assert kind.value == "text"
    assert "투자" in src


def test_youtube_url_in_action_param_routes_to_video():
    src, kind = _detect("", {"video_url": "https://youtube.com/watch?v=abc"})
    assert kind.value == "video"


def test_image_action_param_routes_to_image():
    src, kind = _detect("", {"image": "https://k.kakaocdn.net/abc.jpg"})
    assert kind.value == "image"
    assert src.endswith(".jpg")


def test_picture_dict_with_url_routes_to_image():
    src, kind = _detect("", {"picture": {"url": "https://x.example/y.png"}})
    assert kind.value == "image"


def test_pdf_routes_to_pdf():
    src, kind = _detect("", {"pdf": "https://example.com/x.pdf"})
    assert kind.value == "pdf"


def test_file_with_image_extension_routes_to_image():
    src, kind = _detect("", {"file": "https://cdn.example/poster.jpeg"})
    assert kind.value == "image"


def test_file_with_video_extension_falls_back_to_file():
    src, kind = _detect("", {"file": "https://cdn.example/x.mp4"})
    assert kind.value == "file"


def test_url_in_utterance_extracts_only_url():
    src, kind = _detect("이거 봐줘 https://example.com/scam.jpg 부탁해", {})
    assert kind.value == "image"
    assert src == "https://example.com/scam.jpg"


def test_pure_url_pdf_in_utterance_routes_to_pdf():
    src, kind = _detect("https://example.com/x.pdf", {})
    assert kind.value == "pdf"
