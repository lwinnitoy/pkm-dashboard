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


class TransactionUpdate(BaseModel):
    category: str


class CategorySpend(BaseModel):
    category: str
    total: float
    count: int


# ---- Budgets ----


class BudgetCreate(BaseModel):
    category: str
    monthly_limit: float


class BudgetUpdate(BaseModel):
    category: str | None = None
    monthly_limit: float | None = None


class BudgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    monthly_limit: float


class BudgetStatusItem(BaseModel):
    budget_id: int | None  # None = spending in a category with no budget set
    category: str
    limit: float | None
    spent: float
    remaining: float | None
    pct: float | None


class BudgetStatus(BaseModel):
    month: str  # "YYYY-MM"
    total_limit: float
    total_spent: float
    items: list[BudgetStatusItem]


class SummaryResponse(BaseModel):
    period_days: int
    total_spent: float
    transaction_count: int
    by_category: list[CategorySpend]


# ---- Investments ----


class SkippedItem(BaseModel):
    institution: str
    error_code: str  # Plaid's code, e.g. PRODUCTS_NOT_SUPPORTED / ITEM_LOGIN_REQUIRED
    message: str


class InvestmentsSyncResponse(BaseModel):
    securities: int
    holdings: int
    investment_transactions: int
    items_synced: int
    items_skipped: int
    skipped_details: list[SkippedItem] = []


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


# ---- Manual statement imports (CSV/Excel) ----


class ImportPresetOut(BaseModel):
    key: str
    label: str


class DateRangeOut(BaseModel):
    start: date
    end: date


class ImportRowOut(BaseModel):
    date: date
    description: str
    amount: float
    currency: str | None
    status: str  # new | duplicate | conflict
    existing_amount: float | None = None  # stored value when status == conflict
    category: str  # what it would be written with, incl. auto-detected Transfers


class ImportPreviewOut(BaseModel):
    account_id: int
    filename: str
    preset: str
    period: DateRangeOut
    parsed: int
    new: int
    duplicate: int
    conflict: int
    transfers: int  # rows auto-categorized as Transfers, excluded from spend/income
    gaps_before: list[DateRangeOut]  # uncovered spans as things stand
    gaps_after: list[DateRangeOut]   # what would still be uncovered post-import
    conflicts: list[ImportRowOut]    # every conflict, so none are decided blind
    sample: list[ImportRowOut]       # first rows, to eyeball the parse


class ImportCommitOut(BaseModel):
    batch_id: int
    imported: int
    duplicate: int
    conflict: int
    period: DateRangeOut
    gaps: list[DateRangeOut]


class ManualAccountCreate(BaseModel):
    name: str
    # Drives asset/liability classification in net worth (LIABILITY_TYPES), so a
    # credit card imported as "depository" would add to net worth instead of
    # subtracting from it.
    type: str = "depository"
    subtype: str | None = None
    currency: str | None = "CAD"
    current_balance: float | None = None


class ManualAccountUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    subtype: str | None = None
    current_balance: float | None = None


class ImportBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    filename: str
    preset: str
    period_start: date
    period_end: date
    rows_parsed: int
    rows_imported: int
    rows_duplicate: int
    rows_conflicting: int


class AccountCoverageOut(BaseModel):
    account_id: int
    account_name: str | None
    account_type: str | None
    source: str
    covered: list[DateRangeOut]
    gaps: list[DateRangeOut]
    last_imported_period_end: date | None


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
