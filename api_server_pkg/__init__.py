"""api_server_pkg — api_server.py 분기 라우터 모음.

외부 진입은 항상 `api_server.py` (얇은 wrapper) 를 통한다:
- `import api_server; api_server.app`
- `from api_server import _kakao_detect_input` (테스트 호환)

이 패키지 자체는 라이브러리 사용을 가정하지 않는다.
"""
