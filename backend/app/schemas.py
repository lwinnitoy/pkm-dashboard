"""Pydantic request/response models for the API."""
from datetime import date

from pydantic import BaseModel, ConfigDict


class LinkTokenResponse(BaseModel):
    link_token: str


class ExchangeTokenRequest(BaseModel):
    public_token: str
    institution_name: str | None = None


class SyncResponse(BaseModel):
    added: int
    modified: int
    removed: int


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    official_name: str | None
    type: str | None
    subtype: str | None
    current_balance: float | None
    currency: str | None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: date
    name: str | None
    merchant_name: str | None
    amount: float
    currency: str | None
    category: str | None
    pending: bool


class CategorySpend(BaseModel):
    category: str
    total: float
    count: int


class SummaryResponse(BaseModel):
    period_days: int
    total_spent: float
    transaction_count: int
    by_category: list[CategorySpend]


# ---- Investments ----


class InvestmentsSyncResponse(BaseModel):
    securities: int
    holdings: int
    investment_transactions: int
    items_synced: int
    items_skipped: int


class HoldingOut(BaseModel):
    account_id: int
    account_name: str | None
    ticker: str | None
    security_name: str | None
    quantity: float | None
    price: float | None
    value: float | None
    cost_basis: float | None
    currency: str | None


class InvestmentTransactionOut(BaseModel):
    id: int
    date: date
    name: str | None
    ticker: str | None
    type: str | None
    subtype: str | None
    quantity: float | None
    price: float | None
    amount: float | None
    fees: float | None
    currency: str | None


class AccountValue(BaseModel):
    account_id: int
    account_name: str | None
    value: float


class PortfolioHolding(BaseModel):
    ticker: str | None
    security_name: str | None
    value: float


class PortfolioSummary(BaseModel):
    total_value: float
    holdings_count: int
    by_account: list[AccountValue]
    top_holdings: list[PortfolioHolding]


class TrendPoint(BaseModel):
    period_start: date
    spent: float
    income: float


class MerchantSpend(BaseModel):
    merchant: str
    total: float
    count: int


class CategoryComparison(BaseModel):
    category: str
    current: float
    previous: float
    pct_change: float | None  # None when previous was 0 (no baseline)


class NetWorthPoint(BaseModel):
    date: date
    assets: float
    liabilities: float
    net_worth: float


class GoalCreate(BaseModel):
    name: str
    target_amount: float
    target_date: date
    expected_annual_return: float = 0.06
    monthly_contribution: float = 0.0


class GoalUpdate(BaseModel):
    name: str | None = None
    target_amount: float | None = None
    target_date: date | None = None
    expected_annual_return: float | None = None
    monthly_contribution: float | None = None


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    target_amount: float
    target_date: date
    expected_annual_return: float
    monthly_contribution: float
    # Computed projection fields (populated in routers/finance.py; default None so
    # the model validates directly from the ORM row before projection is applied).
    current_value: float | None = None            # from investments seam; None if unlinked
    projected_value: float | None = None          # value at target_date given assumptions
    gap: float | None = None                      # projected_value - target_amount
    on_track: bool | None = None                  # projected_value >= target_amount
    required_monthly_contribution: float | None = None  # PMT to exactly hit target
