"""ORM models. Finance tables stand alone for v1 but leave room for future modules."""
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.crypto import EncryptedString
from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PlaidItem(Base):
    """One linked institution login (an "Item" in Plaid terms)."""

    __tablename__ = "plaid_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    access_token: Mapped[str] = mapped_column(EncryptedString)  # encrypted at rest (Fernet)
    institution_name: Mapped[str | None] = mapped_column(String, nullable=True)
    transactions_cursor: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    accounts: Mapped[list["Account"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    plaid_item_id: Mapped[int] = mapped_column(ForeignKey("plaid_items.id"))
    plaid_account_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    official_name: Mapped[str | None] = mapped_column(String, nullable=True)
    type: Mapped[str | None] = mapped_column(String, nullable=True)
    subtype: Mapped[str | None] = mapped_column(String, nullable=True)
    current_balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String, nullable=True)

    item: Mapped["PlaidItem"] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    holdings: Mapped[list["Holding"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    investment_transactions: Mapped[list["InvestmentTransaction"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    plaid_transaction_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    merchant_name: Mapped[str | None] = mapped_column(String, nullable=True)
    amount: Mapped[float] = mapped_column(Float)  # Plaid: positive = money out
    currency: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str | None] = mapped_column(String, index=True)  # normalized
    plaid_category: Mapped[str | None] = mapped_column(String, nullable=True)  # raw
    pending: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    account: Mapped["Account"] = relationship(back_populates="transactions")


class Category(Base):
    """Seed lookup of normalized spending categories for clean dashboard grouping."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)


class CategoryRule(Base):
    """User recategorization as a durable merchant rule. Keyed by a normalized
    match key (lowercased merchant_name, falling back to name) so it survives
    Plaid syncs and auto-applies to past and future transactions."""

    __tablename__ = "category_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    category: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Budget(Base):
    """A monthly spending limit for one category (resets each calendar month)."""

    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String, unique=True)
    monthly_limit: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ---- Investments (holdings + investment transactions, e.g. Wealthsimple) ----


class Security(Base):
    """A tradable instrument (stock, ETF, etc.) referenced by holdings/txns."""

    __tablename__ = "securities"

    id: Mapped[int] = mapped_column(primary_key=True)
    plaid_security_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    ticker_symbol: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    type: Mapped[str | None] = mapped_column(String, nullable=True)
    close_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    close_price_as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str | None] = mapped_column(String, nullable=True)


class Holding(Base):
    """Current position of a security within an investment account (point-in-time)."""

    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("account_id", "security_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"))
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    institution_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    institution_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_basis: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    account: Mapped["Account"] = relationship(back_populates="holdings")
    security: Mapped["Security"] = relationship()


class InvestmentTransaction(Base):
    """A buy/sell/dividend/fee/transfer within an investment account."""

    __tablename__ = "investment_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    security_id: Mapped[int | None] = mapped_column(
        ForeignKey("securities.id"), nullable=True
    )
    plaid_investment_transaction_id: Mapped[str] = mapped_column(
        String, unique=True, index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    fees: Mapped[float | None] = mapped_column(Float, nullable=True)
    type: Mapped[str | None] = mapped_column(String, index=True)
    subtype: Mapped[str | None] = mapped_column(String, nullable=True)
    currency: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    account: Mapped["Account"] = relationship(back_populates="investment_transactions")
    security: Mapped["Security"] = relationship()


class BalanceSnapshot(Base):
    """Daily point-in-time balance per account, so net worth can be charted over
    time. Plaid only exposes *current* balance, so history accrues going forward."""

    __tablename__ = "balance_snapshots"
    __table_args__ = (
        UniqueConstraint("account_id", "date", name="uq_snapshot_account_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    balance: Mapped[float | None] = mapped_column(Float, nullable=True)

    account: Mapped["Account"] = relationship()


class Goal(Base):
    """A retirement/portfolio target: reach `target_amount` by `target_date`.

    Current value is read live from the investments seam (get_portfolio_value),
    not stored here — only the target and the projection assumptions live on the row.
    """

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    target_amount: Mapped[float] = mapped_column(Float)
    target_date: Mapped[date] = mapped_column(Date)
    # Assumptions driving the compound-growth projection.
    expected_annual_return: Mapped[float] = mapped_column(Float, default=0.06)  # 0.06 = 6%/yr
    monthly_contribution: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
