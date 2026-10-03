"""Insight cards: the shipped seed content, the seed sync, and the read/write API."""
from datetime import datetime, timedelta

import pytest

from app.insights import store
from app.insights.store import SeedError
from app.models import ORIGIN_AI, ORIGIN_SEED, Insight
from app.schemas import InsightContent


def _card(title: str = "Title", **fields) -> InsightContent:
    return InsightContent(title=title, body="Body.", **fields)


# --- The shipped content ---------------------------------------------------------


def test_shipped_seed_content_is_valid():
    """A bad edit to a content file should fail here, not silently at boot (where
    the sync is best-effort and only logs)."""
    cards = store.load_seed()
    pages = {page for page, _ in cards.values()}
    assert {"goals", "budgets"} <= pages
    for key, (page, content) in cards.items():
        assert content.body.strip(), key
        assert content.summary, key
        for source in content.sources:
            assert source.url.startswith("https://"), (key, source.url)


@pytest.mark.parametrize(
    "yaml_text, message",
    [
        ("- key: budgets.wrong-page\n  title: T\n", "must start with 'goals.'"),
        ("- key: goals.a\n  title: T\n- key: goals.a\n  title: U\n", "duplicate key"),
        ("- key: goals.a\n", "goals.a"),  # title is required
        ("key: goals.a\n", "expected a list"),
    ],
)
def test_load_seed_rejects_malformed_files(tmp_path, yaml_text, message):
    (tmp_path / "goals.yaml").write_text(yaml_text)
    with pytest.raises(SeedError, match=message):
        store.load_seed(tmp_path)


# --- Seed sync --------------------------------------------------------------------


def test_sync_seed_adds_updates_and_removes_seed_cards(db_session):
    store.sync_seed(db_session, {"goals.a": ("goals", _card("A")), "goals.b": ("goals", _card("B"))})
    db_session.commit()

    store.sync_seed(db_session, {"goals.a": ("goals", _card("A, revised"))})
    db_session.commit()

    rows = {r.key: r for r in db_session.query(Insight).all()}
    assert set(rows) == {"goals.a"}  # b was removed from the file
    assert rows["goals.a"].title == "A, revised"
    assert rows["goals.a"].origin == ORIGIN_SEED


def test_sync_seed_leaves_other_writers_alone(db_session):
    """An AI job that took over a seed key, and its own cards, survive a re-sync."""
    store.upsert_insight(db_session, "goals.a", "goals", _card("AI's newer take"), origin=ORIGIN_AI)
    store.upsert_insight(db_session, "goals.news-1", "goals", _card("News"), origin=ORIGIN_AI)
    db_session.commit()

    store.sync_seed(db_session, {"goals.a": ("goals", _card("Seed text"))})
    db_session.commit()

    rows = {r.key: r for r in db_session.query(Insight).all()}
    assert rows["goals.a"].title == "AI's newer take"
    assert "goals.news-1" in rows


def test_resync_of_unchanged_card_keeps_its_date(db_session):
    """updated_at is shown as the card's date, so a boot must not refresh it."""
    cards = {"goals.a": ("goals", _card("A", sources=[{"title": "CRA", "url": "https://x"}]))}
    store.sync_seed(db_session, cards)
    db_session.commit()
    stamp = datetime(2026, 1, 1)
    db_session.query(Insight).update({"updated_at": stamp})
    db_session.commit()

    store.sync_seed(db_session, cards)
    db_session.commit()

    assert db_session.query(Insight).one().updated_at == stamp


# --- API --------------------------------------------------------------------------


def test_list_orders_by_position_and_hides_expired(client, db_session):
    store.upsert_insight(db_session, "goals.second", "goals", _card("2", position=20), origin=ORIGIN_SEED)
    store.upsert_insight(db_session, "goals.first", "goals", _card("1", position=10), origin=ORIGIN_SEED)
    store.upsert_insight(
        db_session, "goals.stale", "goals",
        _card("old news", expires_at=datetime.now() - timedelta(days=1)),
        origin=ORIGIN_AI,
    )
    store.upsert_insight(db_session, "budgets.x", "budgets", _card("other page"), origin=ORIGIN_SEED)
    db_session.commit()

    res = client.get("/api/insights", params={"page": "goals"})

    assert res.status_code == 200
    assert [c["key"] for c in res.json()] == ["goals.first", "goals.second"]


def test_put_creates_then_replaces_a_card(client):
    body = {
        "page": "goals",
        "kind": "progress",
        "title": "You're 12% of the way there",
        "body": "**Nice.**",
        "sources": [{"title": "FP Canada", "url": "https://fpcanada.ca"}],
        "origin": "ai",
        "model": "claude-sonnet-5-5",
        "expires_at": "2026-12-31T00:00:00Z",
    }
    first = client.put("/api/insights/goals.progress", json=body)
    assert first.status_code == 200
    assert first.json()["origin"] == "ai"

    second = client.put("/api/insights/goals.progress", json={**body, "title": "13% now"})

    assert second.status_code == 200
    cards = client.get("/api/insights", params={"page": "goals"}).json()
    assert [(c["key"], c["title"]) for c in cards] == [("goals.progress", "13% now")]


@pytest.mark.parametrize(
    "key, overrides",
    [
        ("budgets.x", {}),               # key namespaced to another page
        ("goals", {}),                   # no slug after the page
        ("goals.Has Spaces", {}),
        ("goals.x", {"origin": "seed"}),  # seed is reserved for the YAML sync
        ("goals.x", {"page": "Goals"}),
    ],
)
def test_put_rejects_bad_keys_and_reserved_origin(client, key, overrides):
    body = {"page": "goals", "title": "T", **overrides}
    assert client.put(f"/api/insights/{key}", json=body).status_code == 422


def test_delete_refuses_seed_cards_but_removes_others(client, db_session):
    store.upsert_insight(db_session, "goals.seeded", "goals", _card(), origin=ORIGIN_SEED)
    store.upsert_insight(db_session, "goals.news", "goals", _card(), origin=ORIGIN_AI)
    db_session.commit()

    assert client.delete("/api/insights/goals.seeded").status_code == 409
    assert client.delete("/api/insights/goals.news").status_code == 204
    assert client.delete("/api/insights/goals.news").status_code == 404
