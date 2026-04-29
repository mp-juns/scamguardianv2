"""어드민 토큰 게이팅 — middleware + login endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, sqlite_init):
    monkeypatch.setenv("SCAMGUARDIAN_ADMIN_TOKEN", "test-admin-secret")
    # api_server 모듈 import 가 dotenv.load_dotenv() 를 호출하므로
    # 환경변수 set 이후에 import.
    import importlib

    import api_server  # noqa: F401

    importlib.reload(api_server)
    # .env 의 ADMIN_AUTH_DISABLED 가 reload 시 다시 로드되므로 reload 후 unset.
    monkeypatch.delenv("ADMIN_AUTH_DISABLED", raising=False)
    return TestClient(api_server.app)


@pytest.fixture
def client_no_token(monkeypatch, sqlite_init):
    # api_server 가 import 시 load_dotenv() 를 호출해서 .env 의 토큰을 다시 끌어오므로
    # reload 후에 한 번 더 delenv 해야 한다 (middleware 는 request 시점에 os.getenv 호출).
    import importlib

    import api_server  # noqa: F401

    importlib.reload(api_server)
    monkeypatch.delenv("SCAMGUARDIAN_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("ADMIN_AUTH_DISABLED", raising=False)
    return TestClient(api_server.app)


def test_admin_route_blocks_without_token(client):
    res = client.get("/api/admin/stats")
    assert res.status_code == 401
    assert res.json()["code"] == "admin_unauthorized"


def test_admin_route_blocks_with_wrong_token(client):
    res = client.get("/api/admin/stats", headers={"X-Admin-Token": "wrong"})
    assert res.status_code == 401


def test_admin_route_accepts_correct_header(client):
    res = client.get(
        "/api/admin/stats", headers={"X-Admin-Token": "test-admin-secret"}
    )
    assert res.status_code == 200


def test_admin_route_accepts_bearer_admin(client):
    res = client.get(
        "/api/admin/stats",
        headers={"Authorization": "Bearer admin-test-admin-secret"},
    )
    assert res.status_code == 200


def test_admin_login_endpoint_validates(client):
    # 로그인 자체는 인증 면제 — 토큰 없이도 접근, 400/401 응답
    res = client.post("/api/admin/login", json={"token": "wrong"})
    assert res.status_code == 401

    res = client.post("/api/admin/login", json={"token": "test-admin-secret"})
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_admin_blocked_when_env_unset(client_no_token):
    res = client_no_token.get("/api/admin/stats")
    assert res.status_code == 401
    detail = res.json()["detail"]
    assert "SCAMGUARDIAN_ADMIN_TOKEN" in detail


def test_admin_login_503_when_env_unset(client_no_token):
    res = client_no_token.post("/api/admin/login", json={"token": "anything"})
    assert res.status_code == 503


def test_non_admin_route_unaffected(client):
    # 헬스/웹훅 같은 경로는 admin token 없어도 접근
    res = client.get("/health")
    # /health 가 없으면 404, 있으면 200 — 어느 쪽이든 401 이 아니어야 함
    assert res.status_code != 401


@pytest.fixture
def client_disabled(monkeypatch, sqlite_init):
    """ADMIN_AUTH_DISABLED=true 시 인증 우회."""
    monkeypatch.setenv("ADMIN_AUTH_DISABLED", "true")
    monkeypatch.setenv("SCAMGUARDIAN_ADMIN_TOKEN", "test-admin-secret")
    import importlib

    import api_server  # noqa: F401

    importlib.reload(api_server)
    monkeypatch.setenv("ADMIN_AUTH_DISABLED", "true")
    return TestClient(api_server.app)


def test_admin_disabled_flag_bypasses_token_check(client_disabled):
    # 토큰 없이도 200
    res = client_disabled.get("/api/admin/stats")
    assert res.status_code == 200


def test_admin_disabled_flag_bypasses_wrong_token(client_disabled):
    # 잘못된 토큰이어도 200
    res = client_disabled.get("/api/admin/stats", headers={"X-Admin-Token": "wrong"})
    assert res.status_code == 200
