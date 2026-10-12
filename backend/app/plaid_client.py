"""Plaid SDK client factory + small helpers (env resolution, category normalization,
error decoding)."""
import json
import logging
from functools import lru_cache

import certifi
import plaid
from plaid.api import plaid_api
from plaid.exceptions import ApiException
from plaid.model.item_remove_request import ItemRemoveRequest

from app.config import get_settings

logger = logging.getLogger(__name__)

# Plaid removed the standalone "Development" environment; only Sandbox and Production remain.
_ENV_MAP = {
    "sandbox": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}

# Map Plaid's Personal Finance Category (PFC) onto our normalized buckets. The
# `detailed` value is checked first: some buckets only exist at that level, and
# the primary alone gets them wrong (groceries are FOOD_AND_DRINK_GROCERIES, so a
# primary-only map files them under Dining).
_DETAILED_MAP = {
    "FOOD_AND_DRINK_GROCERIES": "Groceries",
    # The paying side of a card payment. Counted as Loans it was spending, on top
    # of the card purchases it pays for (and income on the card side). The import
    # path already treats these as Transfers; see app/imports/categorize.py.
    "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT": "Transfers",
    "RENT_AND_UTILITIES_RENT": "Housing",
    "GENERAL_SERVICES_EDUCATION": "Education",
}

_PRIMARY_MAP = {
    "FOOD_AND_DRINK": "Dining",
    "GENERAL_MERCHANDISE": "Shopping",
    "HOME_IMPROVEMENT": "Shopping",
    "TRANSPORTATION": "Transport",
    "TRAVEL": "Travel",
    "RENT_AND_UTILITIES": "Bills & Utilities",
    "GENERAL_SERVICES": "Bills & Utilities",
    "ENTERTAINMENT": "Entertainment",
    "PERSONAL_CARE": "Personal Care",
    "MEDICAL": "Health",
    "LOAN_PAYMENTS": "Loans",
    "LOAN_DISBURSEMENTS": "Transfers",  # borrowed money arriving isn't income
    "TRANSFER_IN": "Transfers",
    "TRANSFER_OUT": "Transfers",
    "INCOME": "Income",
    "BANK_FEES": "Fees",
}

DEFAULT_CATEGORIES = [
    "Dining", "Shopping", "Groceries", "Transport", "Travel",
    "Bills & Utilities", "Entertainment", "Personal Care", "Health",
    "Loans", "Transfers", "Income", "Fees", "Uncategorized",
    # A student's two largest costs. Plaid files rent under RENT_AND_UTILITIES and
    # has no tuition bucket, so these are picked by hand (or by a merchant rule).
    "Housing", "Education",
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


def normalize_category(primary: str | None, detailed: str | None = None) -> str:
    if detailed and detailed.upper() in _DETAILED_MAP:
        return _DETAILED_MAP[detailed.upper()]
    if not primary:
        return "Uncategorized"
    return _PRIMARY_MAP.get(primary.upper(), "Uncategorized")


def plaid_error(exc: ApiException) -> tuple[str, str]:
    """(error_code, message) from a Plaid ApiException, which carries a JSON body."""
    try:
        body = json.loads(exc.body or "{}")
    except (ValueError, TypeError):
        body = {}
    return (
        body.get("error_code") or "UNKNOWN",
        body.get("error_message") or str(exc).strip()[:200],
    )



def item_label(item) -> str:
    """How a PlaidItem is named in sync reports and logs."""
    return item.institution_name or f"item {item.item_id[:8]}"


def skipped_item(item, exc: Exception) -> dict[str, str]:
    """A `SkippedItem` entry for an item a sync couldn't complete."""
    if isinstance(exc, ApiException):
        code, message = plaid_error(exc)
    else:
        code, message = "UNKNOWN", str(exc).strip()[:200] or type(exc).__name__
    return {"institution": item_label(item), "error_code": code, "message": message}


def remove_item(client, access_token: str) -> None:
    """Best-effort /item/remove for an Item the app no longer uses.

    An Item stays live at Plaid (and counts toward the plan's Item limit) until it
    is removed there, so dropping our row alone leaves it orphaned. Failure is
    logged, never raised: the local change it follows has already been committed.
    """
    try:
        client.item_remove(ItemRemoveRequest(access_token=access_token))
    except Exception as exc:  # noqa: BLE001 - cleanup only
        logger.warning("could not remove Plaid item: %s", exc)
