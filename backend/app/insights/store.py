"""Read and write insight cards, and keep the shipped seed cards in step with
their YAML files."""
from datetime import datetime, timezone
from pathlib import Path

import yaml
from pydantic import ValidationError
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import ORIGIN_SEED, Insight
from app.schemas import InsightContent

CONTENT_DIR = Path(__file__).resolve().parent / "content"


class SeedError(ValueError):
    """A seed YAML file that doesn't describe valid cards."""


def _naive_utc(value: datetime | None) -> datetime | None:
    """DateTime columns are naive UTC (as everywhere else in the schema), so an
    aware timestamp from the API is converted rather than silently re-zoned."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def upsert_insight(
    db: Session,
    key: str,
    page: str,
    content: InsightContent,
    *,
    origin: str,
    model: str | None = None,
) -> Insight:
    """Create or replace the card at `key`. The caller commits.

    Only fields that actually differ are assigned, so re-syncing an unchanged
    seed card on boot doesn't bump `updated_at` (shown to the reader as the
    card's date).
    """
    values = {
        "page": page,
        "kind": content.kind,
        "title": content.title,
        "summary": content.summary,
        "body": content.body,
        "sources": [s.model_dump() for s in content.sources],
        "position": content.position,
        "expires_at": _naive_utc(content.expires_at),
        "origin": origin,
        "model": model,
    }
    row = db.query(Insight).filter_by(key=key).first()
    if row is None:
        row = Insight(key=key, **values)
        db.add(row)
        return row
    for field, value in values.items():
        if getattr(row, field) != value:
            setattr(row, field, value)
    return row


def list_insights(db: Session, page: str, now: datetime | None = None) -> list[Insight]:
    """A page's live cards: expired ones are hidden, not deleted."""
    now = _naive_utc(now) or datetime.now(timezone.utc).replace(tzinfo=None)
    return (
        db.query(Insight)
        .filter(
            Insight.page == page,
            or_(Insight.expires_at.is_(None), Insight.expires_at > now),
        )
        .order_by(Insight.position, Insight.updated_at.desc(), Insight.id)
        .all()
    )


def load_seed(content_dir: Path = CONTENT_DIR) -> dict[str, tuple[str, InsightContent]]:
    """Parse every `<page>.yaml` into {key: (page, content)}.

    The file name is the page, and each key must be namespaced by it
    ("goals.savings-rate"), so a card can't land on the wrong page by a typo in
    one field while the other says something else.
    """
    cards: dict[str, tuple[str, InsightContent]] = {}
    for path in sorted(content_dir.glob("*.yaml")):
        page = path.stem
        entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        if not isinstance(entries, list):
            raise SeedError(f"{path.name}: expected a list of cards")
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise SeedError(f"{path.name} card {i}: expected a mapping")
            entry = dict(entry)
            key = entry.pop("key", None)
            if not isinstance(key, str) or not key.startswith(f"{page}."):
                raise SeedError(f"{path.name} card {i}: key must start with '{page}.'")
            if key in cards:
                raise SeedError(f"{path.name}: duplicate key {key!r}")
            try:
                cards[key] = (page, InsightContent.model_validate(entry))
            except ValidationError as exc:
                raise SeedError(f"{path.name} {key}: {exc}") from exc
    return cards


def sync_seed(db: Session, cards: dict[str, tuple[str, InsightContent]]) -> None:
    """Make the seed rows match the YAML: add new cards, rewrite changed ones,
    and drop cards that were removed from the files. The caller commits.

    Rows written by anyone else are left alone — including one that has taken
    over a seed card's key (an AI job refreshing a card with newer figures);
    after that the job owns the key, not the file.
    """
    existing = {row.key: row for row in db.query(Insight).all()}
    for key, (page, content) in cards.items():
        row = existing.get(key)
        if row is not None and row.origin != ORIGIN_SEED:
            continue
        upsert_insight(db, key, page, content, origin=ORIGIN_SEED)
    for key, row in existing.items():
        if row.origin == ORIGIN_SEED and key not in cards:
            db.delete(row)
