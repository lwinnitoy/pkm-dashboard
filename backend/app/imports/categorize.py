"""Assign a category to an imported statement row.

Plaid rows arrive with a `personal_finance_category`; statement exports arrive
with nothing but a description. Two jobs here:

1. **Never leave a category NULL.** Plaid's path falls back to "Uncategorized"
   and the spending queries are written around that, so this path must too.
2. **Recognize transfers.** Importing a credit card *and* the chequing account
   that pays it double-books every payment — once as money-in on the card, once
   as money-out of the chequing account. Categorizing both sides as "Transfers"
   takes them out of spending and income totals (`NON_SPEND_CATEGORIES`).
"""
import re

from sqlalchemy.orm import Session

from app.categorization import rule_category

TRANSFERS = "Transfers"
UNCATEGORIZED = "Uncategorized"

# Descriptions that mean "money moved between accounts you own". Deliberately
# narrow: a false positive silently removes real spending from your totals,
# which is worse than leaving a row uncategorized for you to fix.
_TRANSFER_PATTERNS = (
    r"payment\s*-\s*thank\s*you",        # RBC credit card payment (EN)
    r"pai\s*ement\s*-\s*merci",          # …and the FR half of the same string
    r"\b(mastercard|visa|credit\s*card)\s+(payment|paiement)\b",
    r"\bpayment\s+to\s+(mastercard|visa|credit\s*card)\b",
    r"\b(transfer|tfr|virement)\s+(to|from|au|de)\b",
    r"\bonline\s+banking\s+transfer\b",
    r"\be-?transfer\b",
    r"\binterac\s+e-?transfer\b",
)

_TRANSFER_RE = re.compile("|".join(_TRANSFER_PATTERNS), re.IGNORECASE)


def looks_like_transfer(description: str | None) -> bool:
    return bool(description) and bool(_TRANSFER_RE.search(description))


def resolve_category(db: Session, description: str) -> str:
    """Category for an imported row. A user's own rule always wins, so a
    misfiring transfer pattern can be corrected once and stays corrected."""
    return (
        rule_category(db, None, description)
        or (TRANSFERS if looks_like_transfer(description) else UNCATEGORIZED)
    )
