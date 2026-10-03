"""Holding and account valuation, shared by the investments router and the seam.

Plaid's per-holding `institution_price` / `institution_value` can't be taken on
trust: Wealthsimple sends 0 for both on every holding while quantity and cost
basis are real, so summing them read a ~$21k TFSA as $0. Each holding is instead
priced through a fallback chain, first usable source wins:

1. ``institution`` — the holding's own price/value from Plaid, when > 0.
2. ``close_price`` — the security's last close from Plaid, when > 0.
3. ``transaction`` — the latest buy/sell price for the security in the same account.

Whatever the chain can't price stays unknown (``None``). A stand-in 0 would flow
into totals, gain and allocation as though it were a real price.

A borrowed price (2 or 3) is only used when its currency is compatible with the
holding's: equal, or either side unknown. Plaid labels Wealthsimple's VEE dividend
reinvestment USD (the security resolves to the US listing, VERGF) while the
holding is CAD. Pricing a CAD position off a USD trade is wrong by the exchange
rate in a way nobody would spot, so that holding stays unpriced. Conservative on
purpose.

Account value doesn't need the chain. Plaid's balance for an investment account
is the institution's own total, uninvested cash included, so it's authoritative;
the sum of priced holdings is only the fallback for an account without one.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import Account, Holding, InvestmentTransaction, Security

# Plaid's account type for brokerage and retirement accounts. API versions before
# 2018-05-22 called it "brokerage".
INVESTMENT_ACCOUNT_TYPES = ("investment", "brokerage")

# Where a holding's price came from, in fallback order.
INSTITUTION = "institution"
CLOSE_PRICE = "close_price"
TRANSACTION = "transaction"

# What allocation weights are measured in.
MARKET_VALUE = "market_value"
COST_BASIS = "cost_basis"

# Investment transaction types whose price is a trade in the security itself.
# Dividends ("cash") and fees carry a price of 0, and a transfer's price is
# whatever the institution booked it at rather than a trade.
_TRADE_TYPES = ("buy", "sell")

# (account_id, security_id) -> [(price, currency, date)], newest first.
_TradePrices = dict[tuple[int, int], list[tuple[float, str | None, date]]]


@dataclass
class HoldingValuation:
    holding: Holding
    security: Security
    price: float | None
    value: float | None  # None when no source could price it, never a stand-in 0
    price_source: str | None  # INSTITUTION | CLOSE_PRICE | TRANSACTION
    price_as_of: date | None

    @property
    def cost_basis(self) -> float | None:
        return self.holding.cost_basis

    @property
    def gain(self) -> float | None:
        if self.value is None or self.cost_basis is None:
            return None
        return self.value - self.cost_basis

    @property
    def gain_pct(self) -> float | None:
        gain = self.gain
        if gain is None or not self.cost_basis:
            return None
        return gain / self.cost_basis * 100


@dataclass
class AccountValuation:
    account: Account
    holdings: list[HoldingValuation]

    @property
    def value(self) -> float | None:
        """The institution's balance when there is one, else the sum of whichever
        holdings could be priced; None when there's neither."""
        if self.account.current_balance is not None:
            return self.account.current_balance
        priced = [h.value for h in self.holdings if h.value is not None]
        return sum(priced) if priced else None

    @property
    def complete(self) -> bool:
        """Whether `value` is the account's whole worth, not a partial sum over the
        holdings that happened to be priceable."""
        if self.account.current_balance is not None:
            return True
        return bool(self.holdings) and all(h.value is not None for h in self.holdings)


@dataclass
class PortfolioValuation:
    accounts: list[AccountValuation]

    @property
    def holdings(self) -> list[HoldingValuation]:
        return [h for a in self.accounts for h in a.holdings]

    @property
    def priced_count(self) -> int:
        return sum(1 for h in self.holdings if h.value is not None)

    @property
    def total_value(self) -> float | None:
        """Sum of account values. None only when nothing is linked (no investment
        accounts and no holdings) — the seam's "connect investments" signal."""
        if not self.accounts:
            return None
        return sum(a.value for a in self.accounts if a.value is not None)

    @property
    def cost_basis(self) -> float | None:
        """What the current holdings cost. None unless every holding reports one:
        a partial sum would overstate the gain."""
        bases = [h.cost_basis for h in self.holdings]
        if not bases or any(b is None for b in bases):
            return None
        return sum(bases)

    @property
    def unrealized_gain(self) -> float | None:
        """Value of the accounts holding securities minus what the securities cost.

        Measured against account values because those are the trustworthy number,
        so it includes any cash those accounts hold. Accounts without holdings are
        left out: there's no cost to measure their balance against, and counting it
        all as gain would be absurd.
        """
        cost = self.cost_basis
        invested = [a for a in self.accounts if a.holdings]
        if cost is None or not all(a.complete for a in invested):
            return None
        return sum(a.value for a in invested) - cost

    @property
    def unrealized_gain_pct(self) -> float | None:
        gain, cost = self.unrealized_gain, self.cost_basis
        if gain is None or not cost:
            return None
        return gain / cost * 100

    @property
    def allocation_basis(self) -> str:
        """Market value only when every holding has one. Mixing market values with
        cost bases, or dropping the unpriced holdings, would both skew the weights."""
        if all(h.value is not None for h in self.holdings):
            return MARKET_VALUE
        return COST_BASIS

    def allocation(self) -> list[tuple[Security, float]]:
        """(security, amount) per security across accounts, largest first, measured
        in `allocation_basis`. Holdings with no amount in that basis are left out."""
        by_market = self.allocation_basis == MARKET_VALUE
        totals: dict[int, float] = defaultdict(float)
        securities: dict[int, Security] = {}
        for h in self.holdings:
            amount = h.value if by_market else h.cost_basis
            if amount is None:
                continue
            totals[h.security.id] += amount
            securities[h.security.id] = h.security
        return sorted(
            ((securities[sid], amount) for sid, amount in totals.items()),
            key=lambda slice_: slice_[1],
            reverse=True,
        )


def _positive(x: float | None) -> float | None:
    return x if x is not None and x > 0 else None


def _compatible(a: str | None, b: str | None) -> bool:
    """Same currency, or one side unknown (Plaid leaves some unset)."""
    return a is None or b is None or a.upper() == b.upper()


def _trade_prices(db: Session) -> _TradePrices:
    """Every usable trade price, loaded once instead of queried per holding."""
    rows = (
        db.query(
            InvestmentTransaction.account_id,
            InvestmentTransaction.security_id,
            InvestmentTransaction.price,
            InvestmentTransaction.currency,
            InvestmentTransaction.date,
        )
        .filter(
            InvestmentTransaction.security_id.isnot(None),
            InvestmentTransaction.type.in_(_TRADE_TYPES),
            InvestmentTransaction.price > 0,
        )
        .order_by(InvestmentTransaction.date.desc(), InvestmentTransaction.id.desc())
    )
    out: _TradePrices = defaultdict(list)
    for account_id, security_id, price, currency, when in rows:
        out[(account_id, security_id)].append((price, currency, when))
    return out


def _borrowed_prices(
    holding: Holding, security: Security, trades: _TradePrices
) -> Iterator[tuple[float, str, date | None, str | None]]:
    """(price, source, as_of, currency) from outside the holding, best first: the
    security's last close, then this account's trades in it, newest first."""
    if _positive(security.close_price) is not None:
        yield security.close_price, CLOSE_PRICE, security.close_price_as_of, security.currency
    for price, currency, when in trades.get((holding.account_id, holding.security_id), ()):
        yield price, TRANSACTION, when, currency


def _value_holding(
    holding: Holding, security: Security, trades: _TradePrices
) -> HoldingValuation:
    qty = holding.quantity
    inst_price = _positive(holding.institution_price)
    inst_value = _positive(holding.institution_value)
    if inst_price is not None or inst_value is not None:
        # The institution's value is used as given rather than re-derived as
        # price × quantity: it's the institution's own figure for the position.
        if inst_value is None and qty is not None:
            inst_value = inst_price * qty
        if inst_price is None and qty:
            inst_price = inst_value / qty
        # Institution figures are as fresh as the sync that last wrote them.
        synced = holding.updated_at.date() if holding.updated_at else None
        return HoldingValuation(holding, security, inst_price, inst_value, INSTITUTION, synced)

    for price, source, as_of, currency in _borrowed_prices(holding, security, trades):
        if _compatible(currency, holding.currency):
            value = price * qty if qty is not None else None
            return HoldingValuation(holding, security, price, value, source, as_of)
    return HoldingValuation(holding, security, None, None, None, None)


def value_portfolio(db: Session) -> PortfolioValuation:
    """Value every investment account: those typed as one, plus any other account
    that holds securities. Has no accounts when nothing is linked."""
    trades = _trade_prices(db)
    by_account: dict[int, list[HoldingValuation]] = defaultdict(list)
    for holding, security in (
        db.query(Holding, Security)
        .join(Security, Holding.security_id == Security.id)
        .order_by(Holding.id)
    ):
        by_account[holding.account_id].append(_value_holding(holding, security, trades))

    accounts = (
        db.query(Account)
        .filter(
            or_(
                func.lower(Account.type).in_(INVESTMENT_ACCOUNT_TYPES),
                Account.id.in_(list(by_account)),
            )
        )
        .order_by(Account.id)
        .all()
    )
    return PortfolioValuation([AccountValuation(a, by_account.get(a.id, [])) for a in accounts])
