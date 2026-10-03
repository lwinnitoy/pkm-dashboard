"""Insight cards for a page: read them, or publish one by key.

The write side exists for whatever generates content later — a scheduled AI job,
a pipeline running elsewhere — so it can replace its own cards each run without
a deploy. Seed cards are owned by app/insights/content/*.yaml instead.
"""
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.insights import store
from app.models import ORIGIN_SEED, Insight
from app.schemas import SLUG, InsightOut, InsightWrite

router = APIRouter(prefix="/api/insights", tags=["insights"])

# "<page>.<slug>" — the page prefix keeps one writer's keys from colliding with
# another page's.
KEY = r"^[a-z0-9]+(?:-[a-z0-9]+)*\.[a-z0-9]+(?:-[a-z0-9]+)*$"


@router.get("", response_model=list[InsightOut])
def list_page_insights(page: str = Query(..., pattern=SLUG), db: Session = Depends(get_db)):
    return store.list_insights(db, page)


@router.put("/{key}", response_model=InsightOut)
def put_insight(
    payload: InsightWrite,
    key: str = Path(..., pattern=KEY),
    db: Session = Depends(get_db),
):
    """Create or replace a card. Writing to a seed card's key takes it over: the
    boot-time seed sync leaves non-seed rows alone from then on."""
    if not key.startswith(f"{payload.page}."):
        raise HTTPException(status_code=422, detail=f"key must start with '{payload.page}.'")
    row = store.upsert_insight(
        db, key, payload.page, payload, origin=payload.origin, model=payload.model
    )
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{key}", status_code=204)
def delete_insight(key: str = Path(..., pattern=KEY), db: Session = Depends(get_db)):
    row = db.query(Insight).filter_by(key=key).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Insight not found")
    if row.origin == ORIGIN_SEED:
        # It would be re-created from the YAML on the next boot.
        page = key.split(".", 1)[0]
        raise HTTPException(
            status_code=409,
            detail=f"Seed card — remove it from app/insights/content/{page}.yaml instead",
        )
    db.delete(row)
    db.commit()
