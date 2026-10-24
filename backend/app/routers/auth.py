"""Auth endpoints: report whether auth is required, and exchange a password for a token."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.auth import check_password, create_token, login_throttle
from app.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


class TokenResponse(BaseModel):
    token: str


class AuthStatus(BaseModel):
    auth_required: bool


@router.get("/status", response_model=AuthStatus)
def auth_status():
    """Unprotected: lets the frontend decide whether to show a login screen."""
    return AuthStatus(auth_required=get_settings().auth_enabled)


def _client_id(request: Request) -> str:
    """Who is logging in, for throttling. Behind Cloud Run's front end the peer is
    a Google proxy, so the first X-Forwarded-For hop is the real client."""
    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip()
    return first or (request.client.host if request.client else "unknown")


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request):
    settings = get_settings()
    # When auth is disabled we still issue a token so the client flow is uniform.
    if not settings.auth_enabled:
        return TokenResponse(token=create_token())

    client = _client_id(request)
    wait = login_throttle.retry_after(client)
    if wait is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many wrong passwords. Try again later.",
            headers={"Retry-After": str(wait)},
        )
    if not check_password(payload.password):
        login_throttle.failed(client)
        raise HTTPException(status_code=401, detail="Incorrect password")
    login_throttle.succeeded(client)
    return TokenResponse(token=create_token())
