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
