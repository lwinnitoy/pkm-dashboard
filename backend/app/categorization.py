"""Merchant-based category rules.

A user recategorization creates a durable rule keyed by a normalized match key
(lowercased ``merchant_name``, falling back to ``name``). Rules are consulted on
every Plaid sync so overrides are never clobbered, and applied retroactively to
existing transactions when created.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import CategoryRule, Transaction


def match_key(merchant_name: str | None, name: str | None) -> str | None:
    """Normalized key a rule matches on. None when there's nothing to match."""
    value = merchant_name or name
    value = (value or "").strip().lower()
    return value or None


def rule_category(db: Session, merchant_name: str | None, name: str | None) -> str | None:
    """The user-defined category for this merchant, if a rule exists."""
    key = match_key(merchant_name, name)
    if key is None:
        return None
    rule = db.query(CategoryRule).filter_by(match_key=key).first()
    return rule.category if rule else None


# SQL expression for a transaction's match key, so rules can be applied in bulk.
_TXN_MATCH_KEY = func.lower(
    func.trim(func.coalesce(Transaction.merchant_name, Transaction.name, ""))
)


def upsert_rule_and_apply(db: Session, key: str, category: str) -> int:
    """Create/replace the rule for ``key`` and retroactively recategorize every
    existing transaction that matches it. Returns the number updated. Caller commits."""
    rule = db.query(CategoryRule).filter_by(match_key=key).first()
    if rule is None:
        db.add(CategoryRule(match_key=key, category=category))
    else:
        rule.category = category

    return (
        db.query(Transaction)
        .filter(_TXN_MATCH_KEY == key)
        .update({Transaction.category: category}, synchronize_session=False)
    )
