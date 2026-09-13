"""Single-user authentication via signed, timestamped bearer tokens.

Auth is disabled when ``APP_PASSWORD`` is unset (local dev convenience). When set,
``/api/auth/login`` verifies the password and issues a token signed with
``signing_secret`` (``AUTH_SECRET`` or, by default, ``SECRET_ENCRYPTION_KEY``);
``require_auth`` validates it on protected routers.
"""
import secrets

from fastapi import Header, HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

_SALT = "pkm-auth"


def _serializer() -> URLSafeTimedSerializer:
    secret = get_settings().signing_secret
    if not secret:
        raise RuntimeError(
            "Auth requires a signing secret. Set SECRET_ENCRYPTION_KEY (or AUTH_SECRET)."
        )
    return URLSafeTimedSerializer(secret, salt=_SALT)


def create_token() -> str:
    return _serializer().dumps({"sub": "user"})


def verify_token(token: str) -> bool:
    ttl_seconds = get_settings().auth_token_ttl_hours * 3600
    try:
        _serializer().loads(token, max_age=ttl_seconds)
        return True
    except (BadSignature, SignatureExpired):
        return False


def check_password(password: str) -> bool:
    return secrets.compare_digest(password, get_settings().app_password)


def require_auth(authorization: str | None = Header(default=None)) -> None:
    """Guard dependency for protected routers. No-op when auth is disabled."""
    if not get_settings().auth_enabled:
        return
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1].strip()
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
