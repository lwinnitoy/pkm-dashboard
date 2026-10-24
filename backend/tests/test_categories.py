"""Plaid personal-finance category → our buckets."""
import pytest

from app.plaid_client import normalize_category


@pytest.mark.parametrize(
    ("primary", "detailed", "expected"),
    [
        # The detailed value wins where it carries the meaning.
        ("FOOD_AND_DRINK", "FOOD_AND_DRINK_GROCERIES", "Groceries"),
        ("FOOD_AND_DRINK", "FOOD_AND_DRINK_RESTAURANT", "Dining"),
        ("LOAN_PAYMENTS", "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT", "Transfers"),
        ("LOAN_PAYMENTS", "LOAN_PAYMENTS_STUDENT_LOAN_PAYMENT", "Loans"),
        ("RENT_AND_UTILITIES", "RENT_AND_UTILITIES_RENT", "Housing"),
        ("RENT_AND_UTILITIES", "RENT_AND_UTILITIES_GAS_AND_ELECTRICITY", "Bills & Utilities"),
        ("GENERAL_SERVICES", "GENERAL_SERVICES_EDUCATION", "Education"),
        # Primaries the old map missed.
        ("HOME_IMPROVEMENT", None, "Shopping"),
        ("GENERAL_SERVICES", None, "Bills & Utilities"),
        ("LOAN_DISBURSEMENTS", None, "Transfers"),
        # Unknown or absent.
        ("GOVERNMENT_AND_NON_PROFIT", None, "Uncategorized"),
        (None, None, "Uncategorized"),
        ("food_and_drink", None, "Dining"),
    ],
)
def test_normalize_category(primary, detailed, expected):
    assert normalize_category(primary, detailed) == expected
