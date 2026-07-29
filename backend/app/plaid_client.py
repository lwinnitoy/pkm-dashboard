"""Plaid SDK client factory + small helpers (env resolution, category normalization)."""
from functools import lru_cache

import certifi
import plaid
from plaid.api import plaid_api

from app.config import get_settings

# Plaid removed the standalone "Development" environment; only Sandbox and Production remain.
_ENV_MAP = {
    "sandbox": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}

# Map Plaid's Personal Finance Category "primary" values to our normalized buckets.
_CATEGORY_MAP = {
    "FOOD_AND_DRINK": "Dining",
    "GENERAL_MERCHANDISE": "Shopping",
    "GROCERIES": "Groceries",
    "TRANSPORTATION": "Transport",
    "TRAVEL": "Travel",
    "RENT_AND_UTILITIES": "Bills & Utilities",
    "ENTERTAINMENT": "Entertainment",
    "PERSONAL_CARE": "Personal Care",
    "MEDICAL": "Health",
    "LOAN_PAYMENTS": "Loans",
    "TRANSFER_IN": "Transfers",
    "TRANSFER_OUT": "Transfers",
    "INCOME": "Income",
    "BANK_FEES": "Fees",
}

DEFAULT_CATEGORIES = [
    "Dining", "Shopping", "Groceries", "Transport", "Travel",
    "Bills & Utilities", "Entertainment", "Personal Care", "Health",
    "Loans", "Transfers", "Income", "Fees", "Uncategorized",
]


@lru_cache
def get_plaid_client() -> plaid_api.PlaidApi:
    settings = get_settings()
    host = _ENV_MAP.get(settings.plaid_env.lower(), plaid.Environment.Sandbox)
    configuration = plaid.Configuration(
        host=host,
        api_key={
            "clientId": settings.plaid_client_id,
            "secret": settings.plaid_secret,
        },
    )
    # The python.org framework build ships no CA bundle, so point the SDK's urllib3
    # layer at certifi's bundle to fix "CERTIFICATE_VERIFY_FAILED" on macOS.
    configuration.ssl_ca_cert = certifi.where()
    return plaid_api.PlaidApi(plaid.ApiClient(configuration))


def normalize_category(primary: str | None) -> str:
    if not primary:
        return "Uncategorized"
    return _CATEGORY_MAP.get(primary.upper(), "Uncategorized")
