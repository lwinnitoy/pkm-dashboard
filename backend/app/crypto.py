"""Symmetric encryption for secrets at rest.

Provides an ``EncryptedString`` SQLAlchemy type so sensitive columns (e.g. Plaid
``access_token``) are transparently encrypted on write and decrypted on read — the
rest of the code keeps treating them as plain strings.
"""
from functools import lru_cache

from cryptography.fernet import Fernet
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().secret_encryption_key
    if not key:
        raise RuntimeError(
            "SECRET_ENCRYPTION_KEY is not set. Generate one with:\n"
            "  python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"\n"
            "and add it to backend/.env."
        )
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


class EncryptedString(TypeDecorator):
    """A String column whose value is Fernet-encrypted in the database."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        return None if value is None else encrypt(value)

    def process_result_value(self, value: str | None, dialect) -> str | None:
        return None if value is None else decrypt(value)
