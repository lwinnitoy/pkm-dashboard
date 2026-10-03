"""Transaction list filters, pagination, and the matching count endpoint.

The Transactions page pages through full history with these, and shows
"Showing N of M" from the count — so every filter must narrow the list and the
count identically.
"""
from datetime import date, timedelta

from tests.factories import make_account, make_transaction


def _txn(db, account, *, days_ago: int = 0, amount: float = 10.0, **fields):
    return make_transaction(
        db,
        account=account,
        amount=amount,
        txn_date=date.today() - timedelta(days=days_ago),
        **fields,
    )


def _list(client, **params) -> list[int]:
    resp = client.get("/api/finance/transactions", params={"limit": 500, **params})
    assert resp.status_code == 200, resp.text
    return [row["id"] for row in resp.json()]


def _count(client, **params) -> int:
    resp = client.get("/api/finance/transactions/count", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["total"]


# --------------------------------------------------------------------------- #
# filters                                                                      #
# --------------------------------------------------------------------------- #
def test_period_is_a_look_back_window_and_omitting_it_means_all_time(client, db_session):
    acct = make_account(db_session)
    today = _txn(db_session, acct, days_ago=0)
    boundary = _txn(db_session, acct, days_ago=30)  # inclusive, like /summary
    older = _txn(db_session, acct, days_ago=31)
    last_year = _txn(db_session, acct, days_ago=400)
    db_session.commit()

    assert _list(client, period=30) == [today.id, boundary.id]
    assert _count(client, period=30) == 2

    assert _list(client) == [today.id, boundary.id, older.id, last_year.id]
    assert _count(client) == 4


def test_search_matches_name_or_merchant_case_insensitively(client, db_session):
    acct = make_account(db_session)
    tims = _txn(db_session, acct, name="TIM HORTONS #1234", merchant_name=None)
    coffee = _txn(db_session, acct, name="POS PURCHASE 0042", merchant_name="Starbucks")
    groceries = _txn(db_session, acct, name="Grocery run", merchant_name="Loblaws")
    db_session.commit()

    assert _list(client, q="tim hortons") == [tims.id]
    assert _list(client, q="STARB") == [coffee.id]  # merchant only
    assert _list(client, q="purchase") == [coffee.id]  # name, though a merchant is set
    assert _list(client, q="  loblaws ") == [groceries.id]  # padding from the search box
    assert _count(client, q="starb") == 1
    # A blank search is no filter, not "match the empty string somewhere".
    assert _count(client, q="   ") == 3


def test_search_treats_like_wildcards_as_text(client, db_session):
    acct = make_account(db_session)
    sale = _txn(db_session, acct, name="50% OFF SALE")
    _txn(db_session, acct, name="Coffee")
    db_session.commit()

    assert _list(client, q="%") == [sale.id]
    assert _list(client, q="_") == []


def test_uncategorized_matches_null_and_the_literal_string(client, db_session):
    acct = make_account(db_session)
    from_plaid = _txn(db_session, acct, category=None, days_ago=1)
    from_import = _txn(db_session, acct, category="Uncategorized", days_ago=2)
    dining = _txn(db_session, acct, category="Dining", days_ago=3)
    db_session.commit()

    assert _list(client, category="Uncategorized") == [from_plaid.id, from_import.id]
    assert _count(client, category="Uncategorized") == 2
    # Any other category is still an exact match, as before.
    assert _list(client, category="Dining") == [dining.id]
    assert _count(client, category="Dining") == 1


def test_account_filter(client, db_session):
    chequing = make_account(db_session, plaid_account_id="a-chq", name="Chequing")
    card = make_account(db_session, plaid_account_id="a-card", name="Visa", type="credit")
    on_chequing = _txn(db_session, chequing, days_ago=1)
    on_card = [_txn(db_session, card, days_ago=2), _txn(db_session, card, days_ago=3)]
    db_session.commit()

    assert _list(client, account_id=chequing.id) == [on_chequing.id]
    assert _list(client, account_id=card.id) == [t.id for t in on_card]
    assert _count(client, account_id=card.id) == 2
    assert _list(client, account_id=9999) == []
    assert _count(client, account_id=9999) == 0


def test_filters_combine(client, db_session):
    chequing = make_account(db_session, plaid_account_id="a-chq")
    card = make_account(db_session, plaid_account_id="a-card", type="credit")
    # Two rows match everything (one NULL, one literal "Uncategorized")...
    hit_null = _txn(db_session, chequing, days_ago=1, category=None, name="Tim Hortons")
    hit_literal = _txn(
        db_session, chequing, days_ago=2, category="Uncategorized", name="TIM HORTONS #9"
    )
    # ...and each decoy misses exactly one filter, so a dropped or mis-grouped
    # clause (e.g. the Uncategorized OR leaking past the AND) lets one through.
    _txn(db_session, card, days_ago=1, category=None, name="Tim Hortons")
    _txn(db_session, chequing, days_ago=1, category="Dining", name="Tim Hortons")
    _txn(db_session, chequing, days_ago=1, category=None, name="Starbucks")
    _txn(db_session, chequing, days_ago=90, category="Uncategorized", name="Tim Hortons")
    db_session.commit()

    params = {"period": 30, "q": "tim", "category": "Uncategorized", "account_id": chequing.id}
    assert _list(client, **params) == [hit_null.id, hit_literal.id]
    assert _count(client, **params) == 2


# --------------------------------------------------------------------------- #
# pagination + count                                                           #
# --------------------------------------------------------------------------- #
def test_pages_cover_every_row_once_newest_first(client, db_session):
    acct = make_account(db_session)
    # Several rows share a date, so the id tiebreak is what keeps pages stable.
    rows = [_txn(db_session, acct, days_ago=d) for d in (5, 0, 1, 0, 5, 1, 0)]
    db_session.commit()
    expected = [t.id for t in sorted(rows, key=lambda t: (t.date, t.id), reverse=True)]

    pages = [_list(client, limit=3, offset=offset) for offset in (0, 3, 6, 9)]
    assert [len(p) for p in pages] == [3, 3, 1, 0]
    assert [i for page in pages for i in page] == expected
    assert _count(client) == 7


def test_pages_of_a_filtered_list_only_contain_matches(client, db_session):
    acct = make_account(db_session)
    matches = [_txn(db_session, acct, days_ago=d, category=None) for d in range(5)]
    for d in range(5):
        _txn(db_session, acct, days_ago=d, category="Dining")
    db_session.commit()

    first = _list(client, category="Uncategorized", limit=3, offset=0)
    rest = _list(client, category="Uncategorized", limit=3, offset=3)
    assert first + rest == [t.id for t in matches]
    assert _count(client, category="Uncategorized") == 5


def test_count_is_routed_and_counts_nothing_when_empty(client):
    # Not swallowed by the /transactions/{txn_id} route, which would 405 or 422.
    resp = client.get("/api/finance/transactions/count")
    assert resp.status_code == 200
    assert resp.json() == {"total": 0}
