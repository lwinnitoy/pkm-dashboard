"""Application settings loaded from environment / .env via pydantic-settings."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Plaid
    plaid_client_id: str = ""
    plaid_secret: str = ""
    plaid_env: str = "sandbox"  # sandbox | production
    plaid_country_codes: str = "US,CA"
    plaid_products: str = "transactions"
    # Consent-only products captured at Link time if the institution supports them,
    # without filtering the institution list. Enables investment-heavy institutions
    # like Wealthsimple to link and consent to investments data.
    plaid_additional_consented_products: str = "investments"

    # Database
    database_url: str = "sqlite:///./pkm.db"

    # Fernet key for encrypting secrets at rest (Plaid access_tokens).
    secret_encryption_key: str = ""

    # CORS
    frontend_origin: str = "http://localhost:5173"

    @property
    def country_code_list(self) -> list[str]:
        return [c.strip() for c in self.plaid_country_codes.split(",") if c.strip()]

    @property
    def product_list(self) -> list[str]:
        return [p.strip() for p in self.plaid_products.split(",") if p.strip()]

    @property
    def additional_consented_product_list(self) -> list[str]:
        return [
            p.strip()
            for p in self.plaid_additional_consented_products.split(",")
            if p.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
