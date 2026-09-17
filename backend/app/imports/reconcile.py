"""Reconcile parsed statement rows against what's already stored.

Two problems, both caused by importing by hand what Plaid would otherwise stream:

**Overlap.** Statement exports are requested by date range, so re-importing
"last 90 days" every month re-sends rows already stored. Each row gets a
deterministic `fingerprint` over (account, date, amount, description, ordinal).
The ordinal counts identical rows *within their own (date, amount, description)
group*, which is what makes this safe: two genuinely separate $4.50 coffees on
the same day get ordinals 0 and 1 and both survive, while the same two rows in
next month's overlapping export reproduce those same ordinals and dedupe. The
fingerprint is also a UNIQUE column, so a double-submit can't slip through.

**Gaps.** Coverage is tracked as statement *periods* (`ImportBatch`), not row
dates — an imported month with no spending is covered, not missing. Gaps are the
holes in the union of those periods, plus the tail between the newest period and
today.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.imports.parsers import ParsedRow
from app.models import ImportBatch, Transaction

NEW = "new"
DUPLICATE = "duplicate"
CONFLICT = "conflict"


def normalize_description(text: str | None) -> str:
    """Collapse case/whitespace so trivial formatting drift doesn't defeat dedup."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def fingerprint(account_id: int, row: ParsedRow, ordinal: int) -> str:
    parts = (
        str(account_id),
        row.date.isoformat(),
        f"{row.amount:.2f}",
        normalize_description(row.description),
        str(ordinal),
    )
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


@dataclass
class ClassifiedRow:
    row: ParsedRow
    fingerprint: str
    status: str
    existing_amount: float | None = None  # set when status == CONFLICT


@dataclass
class DateRange:
    start: date
    end: date


@dataclass
class Reconciliation:
    rows: list[ClassifiedRow]
    period: DateRange
    gaps_before: list[DateRange]
    gaps_after: list[DateRange]

    @property
    def new_rows(self) -> list[ClassifiedRow]:
        return [r for r in self.rows if r.status == NEW]

    @property
    def conflicting_rows(self) -> list[ClassifiedRow]:
        return [r for r in self.rows if r.status == CONFLICT]

    def count(self, status: str) -> int:
        return sum(1 for r in self.rows if r.status == status)


def _assign_ordinals(account_id: int, rows: list[ParsedRow]) -> list[tuple[ParsedRow, str]]:
    seen: dict[tuple, int] = defaultdict(int)
    out = []
    for row in rows:
        key = (row.date, round(row.amount, 2), normalize_description(row.description))
        ordinal = seen[key]
        seen[key] += 1
        out.append((row, fingerprint(account_id, row, ordinal)))
    return out


def _conflict_amount(
    index: dict[tuple[date, str], list[float]], row: ParsedRow
) -> float | None:
    """The stored amount for an unambiguous (date, description) match that differs.

    Deliberately conservative: only when exactly one stored row shares the date and
    description. With several, there's no way to tell a restated amount from a
    second, genuinely different purchase at the same merchant on the same day.
    """
    matches = index.get((row.date, normalize_description(row.description)), [])
    if len(matches) != 1:
        return None
    return matches[0] if abs(matches[0] - row.amount) >= 0.01 else None


def classify(db: Session, account_id: int, rows: list[ParsedRow]) -> list[ClassifiedRow]:
    """Mark every row new/duplicate/conflict.

    Both lookups are loaded once over the file's date span rather than per row: a
    duplicate must share its date with the row that spawned it (the date is inside
    the fingerprint), so the span is sufficient. Per-row queries would mean one
    network round trip each against a remote Postgres — minutes, for a file like a
    year of credit-card activity.
    """
    fingerprinted = _assign_ordinals(account_id, rows)
    start, end = min(r.date for r in rows), max(r.date for r in rows)
    in_span = (
        Transaction.account_id == account_id,
        Transaction.date >= start,
        Transaction.date <= end,
    )

    known = {
        fp
        for (fp,) in db.query(Transaction.import_fingerprint).filter(
            *in_span, Transaction.import_fingerprint.isnot(None)
        )
    }
    by_key: dict[tuple[date, str], list[float]] = defaultdict(list)
    for when, merchant, name, amount in db.query(
        Transaction.date, Transaction.merchant_name, Transaction.name, Transaction.amount
    ).filter(*in_span):
        by_key[(when, normalize_description(merchant or name))].append(amount)

    classified = []
    for row, fp in fingerprinted:
        if fp in known:
            classified.append(ClassifiedRow(row=row, fingerprint=fp, status=DUPLICATE))
            continue
        existing = _conflict_amount(by_key, row)
        if existing is not None:
            classified.append(
                ClassifiedRow(
                    row=row, fingerprint=fp, status=CONFLICT, existing_amount=existing
                )
            )
        else:
            classified.append(ClassifiedRow(row=row, fingerprint=fp, status=NEW))
    return classified


def merge_ranges(ranges: list[DateRange]) -> list[DateRange]:
    """Union of periods. Touching periods (Jun 30 / Jul 1) merge into one."""
    if not ranges:
        return []
    ordered = sorted(ranges, key=lambda r: (r.start, r.end))
    merged = [DateRange(ordered[0].start, ordered[0].end)]
    for current in ordered[1:]:
        last = merged[-1]
        if current.start <= last.end + timedelta(days=1):
            last.end = max(last.end, current.end)
        else:
            merged.append(DateRange(current.start, current.end))
    return merged


def covered_ranges(db: Session, account_id: int) -> list[DateRange]:
    """Periods this account has data for: imported statement spans, plus the span
    Plaid has been syncing (first to last synced transaction) when it's linked."""
    ranges = [
        DateRange(batch.period_start, batch.period_end)
        for batch in db.query(ImportBatch).filter(ImportBatch.account_id == account_id)
    ]
    plaid_span = (
        db.query(func.min(Transaction.date), func.max(Transaction.date))
        .filter(
            Transaction.account_id == account_id,
            Transaction.import_fingerprint.is_(None),
        )
        .one()
    )
    if plaid_span[0] is not None:
        ranges.append(DateRange(plaid_span[0], plaid_span[1]))
    return merge_ranges(ranges)


def find_gaps(ranges: list[DateRange], until: date | None = None) -> list[DateRange]:
    """Uncovered spans between periods, plus the tail from the newest period to
    `until` (default today) — the "you haven't imported since August" case."""
    until = until or date.today()
    merged = merge_ranges(ranges)
    if not merged:
        return []

    gaps = [
        DateRange(merged[i].end + timedelta(days=1), merged[i + 1].start - timedelta(days=1))
        for i in range(len(merged) - 1)
    ]
    newest = merged[-1].end
    if newest < until:
        gaps.append(DateRange(newest + timedelta(days=1), until))
    return gaps


def reconcile(db: Session, account_id: int, rows: list[ParsedRow]) -> Reconciliation:
    """Classify every row and report the coverage picture before and after import."""
    classified = classify(db, account_id, rows)
    period = DateRange(min(r.date for r in rows), max(r.date for r in rows))

    existing = covered_ranges(db, account_id)
    return Reconciliation(
        rows=classified,
        period=period,
        gaps_before=find_gaps(existing),
        gaps_after=find_gaps([*existing, period]),
    )
