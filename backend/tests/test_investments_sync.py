"""Investments sync: a skipped item must explain itself.

An item with no investment accounts and an item that never consented to the
investments product both end up with zero holdings. Only the second is fixable
(by re-linking), so the reason has to survive the sync.
"""
from types import SimpleNamespace

import pytest
from plaid.exceptions import ApiException

import app.routers.investments as investments_router
from tests.factories import make_account, make_item


def _api_exception(error_code: str, message: str) -> ApiException:
    exc = ApiException(status=400, reason="Bad Request")
    exc.body = f'{{"error_code": "{error_code}", "error_message": "{message}"}}'
    return exc


class FakeInvestmentsClient:
    """Raises per access_token, so items can fail independently."""

    def __init__(self, failures: dict[str, ApiException]):
        self.failures = failures

    def investments_holdings_get(self, request):
        if request.access_token in self.failures:
            raise self.failures[request.access_token]
        return SimpleNamespace(securities=[], holdings=[])

    def investments_transactions_get(self, request):
        return SimpleNamespace(
            total_investment_transactions=0, securities=[], investment_transactions=[]
        )


@pytest.fixture()
def fake_investments(monkeypatch):
    def _install(failures):
        client = FakeInvestmentsClient(failures)
        monkeypatch.setattr(investments_router, "get_plaid_client", lambda: client)
        return client

    return _install


def test_skipped_item_reports_the_plaid_error_code(client, db_session, fake_investments):
    item = make_item(db_session, item_id="ws-1", name="Wealthsimple")
    make_account(db_session, item=item, plaid_account_id="tfsa-1", name="TFSA")
    db_session.commit()

    fake_investments(
        {
            item.access_token: _api_exception(
                "PRODUCTS_NOT_SUPPORTED", "client is not authorized for investments"
            )
        }
    )

    body = client.post("/api/investments/sync").json()

    assert body["items_skipped"] == 1
    assert body["items_synced"] == 0
    skipped = body["skipped_details"][0]
    assert skipped["institution"] == "Wealthsimple"
    assert skipped["error_code"] == "PRODUCTS_NOT_SUPPORTED"
    assert "not authorized" in skipped["message"]


def test_one_failing_item_does_not_stop_the_others(client, db_session, fake_investments):
    broken = make_item(db_session, item_id="ws-1", name="Wealthsimple")
    working = make_item(db_session, item_id="rbc-1", name="Other Bank")
    db_session.commit()

    fake_investments({broken.access_token: _api_exception("ITEM_LOGIN_REQUIRED", "relink")})

    body = client.post("/api/investments/sync").json()

    assert body["items_synced"] == 1
    assert body["items_skipped"] == 1
    assert body["skipped_details"][0]["error_code"] == "ITEM_LOGIN_REQUIRED"
    assert working.institution_name == "Other Bank"


def test_a_clean_sync_reports_no_skips(client, db_session, fake_investments):
    make_item(db_session, item_id="ws-1", name="Wealthsimple")
    db_session.commit()
    fake_investments({})

    body = client.post("/api/investments/sync").json()

    assert body["items_skipped"] == 0
    assert body["skipped_details"] == []


def test_a_malformed_error_body_still_yields_a_reason(client, db_session, fake_investments):
    item = make_item(db_session, item_id="ws-1", name="Wealthsimple")
    db_session.commit()
    exc = ApiException(status=500, reason="Server Error")
    exc.body = "<html>not json</html>"
    fake_investments({item.access_token: exc})

    skipped = client.post("/api/investments/sync").json()["skipped_details"][0]

    assert skipped["error_code"] == "UNKNOWN"
    assert skipped["message"]


def test_holdings_sync_refreshes_the_account_balance_and_todays_snapshot(
    client, db_session, monkeypatch
):
    """The holdings response carries the account's balance, which is the
    portfolio value; keep it current without waiting for a re-link."""
    from datetime import date

    from app.models import Account, BalanceSnapshot

    item = make_item(db_session, item_id="ws-1", name="Wealthsimple")
    tfsa = make_account(
        db_session, item=item, plaid_account_id="tfsa-1", name="TFSA",
        type="investment", current_balance=20000.0,
    )
    db_session.commit()

    class Client(FakeInvestmentsClient):
        def investments_holdings_get(self, request):
            return SimpleNamespace(
                securities=[],
                holdings=[],
                accounts=[SimpleNamespace(account_id="tfsa-1", balances=SimpleNamespace(current=21500.25))],
            )

    monkeypatch.setattr(investments_router, "get_plaid_client", lambda: Client({}))

    assert client.post("/api/investments/sync").status_code == 200

    db_session.expire_all()
    assert db_session.get(Account, tfsa.id).current_balance == 21500.25
    snap = db_session.query(BalanceSnapshot).filter_by(account_id=tfsa.id, date=date.today()).one()
    assert snap.balance == 21500.25
