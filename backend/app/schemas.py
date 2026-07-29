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
