"""Single-user auth: disabled by default, enforced when APP_PASSWORD is set."""
import pytest

from app.config import get_settings

PASSWORD = "correct horse"


@pytest.fixture()
def auth_on():
    """Enable auth for the duration of a test by setting the (cached) password."""
    settings = get_settings()
    settings.app_password = PASSWORD
    try:
        yield
    finally:
        settings.app_password = ""


def test_auth_disabled_by_default(client):
    assert client.get("/api/auth/status").json()["auth_required"] is False
    # Protected routes are open when no password is configured.
    assert client.get("/api/finance/accounts").status_code == 200


def test_status_reports_required_when_enabled(client, auth_on):
    assert client.get("/api/auth/status").json()["auth_required"] is True


def test_protected_route_requires_token(client, auth_on):
    assert client.get("/api/finance/accounts").status_code == 401


def test_wrong_password_rejected(client, auth_on):
    assert client.post("/api/auth/login", json={"password": "nope"}).status_code == 401


def test_login_then_access_with_token(client, auth_on):
    token = client.post("/api/auth/login", json={"password": PASSWORD}).json()["token"]
    resp = client.get("/api/finance/accounts", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_tampered_token_rejected(client, auth_on):
    assert (
        client.get("/api/finance/accounts", headers={"Authorization": "Bearer garbage"}).status_code
        == 401
    )


def test_health_stays_open_when_auth_enabled(client, auth_on):
    assert client.get("/health").status_code == 200


def test_repeated_wrong_passwords_are_throttled(client, auth_on):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"password": "nope"}).status_code == 401

    blocked = client.post("/api/auth/login", json={"password": PASSWORD})

    assert blocked.status_code == 429  # even the right password, until the window passes
    assert int(blocked.headers["Retry-After"]) > 0


def test_throttle_is_per_client(client, auth_on):
    for _ in range(5):
        client.post("/api/auth/login", json={"password": "nope"}, headers={"X-Forwarded-For": "1.1.1.1"})

    other = client.post(
        "/api/auth/login", json={"password": PASSWORD}, headers={"X-Forwarded-For": "2.2.2.2"}
    )
    assert other.status_code == 200


def test_changing_the_password_signs_old_tokens_out(client, auth_on):
    token = client.post("/api/auth/login", json={"password": PASSWORD}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/finance/accounts", headers=headers).status_code == 200

    get_settings().app_password = "a new passphrase"

    assert client.get("/api/finance/accounts", headers=headers).status_code == 401


def test_api_docs_are_hidden_when_auth_is_on(client, auth_on):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_api_docs_are_served_without_auth(client):
    assert client.get("/openapi.json").status_code == 200


def test_health_reports_an_unreachable_database(client, monkeypatch):
    import app.main as app_main

    class DownEngine:
        def connect(self):
            raise ConnectionError("db down")

    monkeypatch.setattr(app_main, "engine", DownEngine())

    resp = client.get("/health")

    assert resp.status_code == 503
    assert resp.json() == {"status": "unavailable"}
