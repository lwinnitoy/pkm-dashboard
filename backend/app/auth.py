"""Single-user authentication via signed, timestamped bearer tokens.

Auth is disabled when ``APP_PASSWORD`` is unset (local dev convenience). When set,
``/api/auth/login`` verifies the password and issues a token signed with
``signing_secret`` (``AUTH_SECRET`` or, by default, ``SECRET_ENCRYPTION_KEY``);
``require_auth`` validates it on protected routers.

Tokens are bound to the current password: changing ``APP_PASSWORD`` (or rotating
``AUTH_SECRET``) signs every device out. Failed logins are throttled per client.
"""
import hashlib
import secrets
import threading
import time
from collections import deque

from fastapi import Header, HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

_SALT = "pkm-auth"


def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    secret = settings.signing_secret
    if not secret:
        raise RuntimeError(
            "Auth requires a signing secret. Set SECRET_ENCRYPTION_KEY (or AUTH_SECRET)."
        )
    # The password is part of the salt, so a token issued under the old password
    # stops verifying the moment it changes: the way to sign out a lost device.
    password_tag = hashlib.sha256(settings.app_password.encode()).hexdigest()[:16]
    return URLSafeTimedSerializer(secret, salt=f"{_SALT}:{password_tag}")


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


class LoginThrottle:
    """Failed-login limiter per client, in memory.

    In-memory is enough because production runs a single instance
    (`--max-instances 1`); a restart only resets the counters.
    """

    def __init__(self, max_failures: int = 5, window_seconds: float = 15 * 60):
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, client: str, now: float) -> deque[float]:
        times = self._failures.setdefault(client, deque())
        while times and now - times[0] > self.window:
            times.popleft()
        return times

    def retry_after(self, client: str) -> int | None:
        """Seconds until this client may try again, or None if it may now."""
        now = time.monotonic()
        with self._lock:
            times = self._recent(client, now)
            if len(times) < self.max_failures:
                return None
            return max(1, int(self.window - (now - times[0])) + 1)

    def failed(self, client: str) -> None:
        with self._lock:
            self._recent(client, time.monotonic()).append(time.monotonic())

    def succeeded(self, client: str) -> None:
        with self._lock:
            self._failures.pop(client, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


login_throttle = LoginThrottle()
