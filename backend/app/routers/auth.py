"""Auth endpoints: report whether auth is required, and exchange a password for a token."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.auth import check_password, create_token
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


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest):
    settings = get_settings()
    # When auth is disabled we still issue a token so the client flow is uniform.
    if settings.auth_enabled and not check_password(payload.password):
        raise HTTPException(status_code=401, detail="Incorrect password")
    return TokenResponse(token=create_token())
