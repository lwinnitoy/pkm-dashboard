"""Manual statement import: parsing, overlap dedup, conflicts and gap detection."""
from datetime import date

import pytest

from app.imports import reconcile
from app.imports.parsers import PRESETS, ParseError, parse
from app.imports.reconcile import CONFLICT, DUPLICATE, NEW, DateRange
from app.models import SOURCE_CSV, Account, Transaction
from tests.factories import make_account, make_transaction

RBC = PRESETS["rbc"]

HEADER = (
    '"Account Type","Account Number","Transaction Date","Cheque Number",'
    '"Description 1","Description 2","CAD$","USD$"\n'
)


def rbc_csv(*rows: str) -> bytes:
    return (HEADER + "".join(rows)).encode()


def row(when: str, desc: str, amount: str, desc2: str = "") -> str:
    return f'"Chequing","123-456","{when}","","{desc}","{desc2}","{amount}",""\n'


def manual_account(db) -> Account:
    account = Account(source=SOURCE_CSV, name="RBC Chequing", type="depository", currency="CAD")
    db.add(account)
    db.flush()
    return account


# ---- parsing ----


def test_parses_rbc_export_and_flips_sign_to_plaid_convention(db_session):
    data = rbc_csv(
        row("9/2/2026", "TIM HORTONS", "-4.50"),
        row("9/3/2026", "PAYROLL DEP", "2000.00"),
    )
    rows = parse(data, "rbc.csv", RBC)

    assert [r.date for r in rows] == [date(2026, 9, 2), date(2026, 9, 3)]
    # RBC writes debits negative; Plaid (and the rest of this app) is positive = money out.
    assert rows[0].amount == 4.50
    assert rows[1].amount == -2000.00
    assert rows[0].currency == "CAD"


def test_joins_split_description_columns(db_session):
    rows = parse(rbc_csv(row("9/2/2026", "AMZN MKTP", "-20.00", desc2="ORDER 113")), "r.csv", RBC)
    assert rows[0].description == "AMZN MKTP ORDER 113"


def test_skips_preamble_to_find_the_header_row(db_session):
    data = ("Exported from RBC Online Banking\n\n" + HEADER + row("9/2/2026", "COFFEE", "-3.00")).encode()
    assert len(parse(data, "rbc.csv", RBC)) == 1


def test_rejects_a_file_with_no_recognisable_header(db_session):
    with pytest.raises(ParseError):
        parse(b"totally,unrelated,columns\n1,2,3\n", "nope.csv", RBC)


def test_reads_parenthesised_and_symbol_laden_amounts(db_session):
    rows = parse(rbc_csv(row("9/2/2026", "RENT", "($1,250.00)")), "r.csv", RBC)
    assert rows[0].amount == 1250.00


# ---- overlap / dedup ----


def test_reimporting_an_overlapping_period_finds_only_duplicates(client, db_session):
    account = manual_account(db_session)
    db_session.commit()
    august = rbc_csv(row("8/2/2026", "COFFEE", "-4.50"), row("8/9/2026", "GROCERIES", "-82.10"))

    first = client.post(
        "/api/imports/commit",
        files={"file": ("aug.csv", august, "text/csv")},
        data={"account_id": account.id, "preset": "rbc"},
    )
    assert first.status_code == 200
    assert first.json()["imported"] == 2

    # Next month's export re-sends August and adds September.
    overlapping = rbc_csv(
        row("8/2/2026", "COFFEE", "-4.50"),
        row("8/9/2026", "GROCERIES", "-82.10"),
        row("9/1/2026", "TRANSIT", "-3.35"),
    )
    preview = client.post(
        "/api/imports/preview",
        files={"file": ("sep.csv", overlapping, "text/csv")},
        data={"account_id": account.id, "preset": "rbc"},
    ).json()

    assert (preview["new"], preview["duplicate"]) == (1, 2)

    second = client.post(
        "/api/imports/commit",
        files={"file": ("sep.csv", overlapping, "text/csv")},
        data={"account_id": account.id, "preset": "rbc"},
    ).json()
    assert second["imported"] == 1
    assert db_session.query(Transaction).count() == 3


def test_identical_transactions_on_one_day_are_both_kept(db_session):
    """Two $4.50 coffees on the same day are real, not a duplicated row."""
    account = manual_account(db_session)
    rows = parse(
        rbc_csv(row("9/2/2026", "COFFEE", "-4.50"), row("9/2/2026", "COFFEE", "-4.50")),
        "r.csv",
        RBC,
    )
    classified = reconcile.classify(db_session, account.id, rows)

    assert [c.status for c in classified] == [NEW, NEW]
    assert classified[0].fingerprint != classified[1].fingerprint


def test_a_repeated_pair_still_dedupes_on_reimport(client, db_session):
    account = manual_account(db_session)
    db_session.commit()
    data = rbc_csv(row("9/2/2026", "COFFEE", "-4.50"), row("9/2/2026", "COFFEE", "-4.50"))
    payload = {"account_id": account.id, "preset": "rbc"}

    client.post("/api/imports/commit", files={"file": ("a.csv", data, "text/csv")}, data=payload)
    again = client.post(
        "/api/imports/commit", files={"file": ("a.csv", data, "text/csv")}, data=payload
    ).json()

    assert again["imported"] == 0
    assert again["duplicate"] == 2


def test_description_whitespace_and_case_drift_does_not_defeat_dedup(db_session):
    account = manual_account(db_session)
    first = parse(rbc_csv(row("9/2/2026", "COFFEE SHOP", "-4.50")), "a.csv", RBC)
    stored = reconcile.classify(db_session, account.id, first)[0]
    db_session.add(
        Transaction(
            account_id=account.id,
            import_fingerprint=stored.fingerprint,
            source=SOURCE_CSV,
            date=first[0].date,
            name=first[0].description,
            amount=first[0].amount,
        )
    )
    db_session.flush()

    drifted = parse(rbc_csv(row("9/2/2026", "coffee   shop", "-4.50")), "b.csv", RBC)
    assert reconcile.classify(db_session, account.id, drifted)[0].status == DUPLICATE


# ---- conflicts ----


def test_a_restated_amount_is_flagged_not_silently_added(db_session):
    account = make_account(db_session)
    make_transaction(
        db_session, account=account, amount=20.00, txn_date=date(2026, 9, 2), name="RESTAURANT"
    )

    rows = parse(rbc_csv(row("9/2/2026", "RESTAURANT", "-24.00")), "r.csv", RBC)
    classified = reconcile.classify(db_session, account.id, rows)

    assert classified[0].status == CONFLICT
    assert classified[0].existing_amount == 20.00


def test_ambiguous_same_day_merchant_matches_are_not_called_conflicts(db_session):
    """Two stored rows for one merchant/day: a third can't be a 'restatement'."""
    account = make_account(db_session)
    for amount in (5.00, 7.00):
        make_transaction(
            db_session, account=account, amount=amount, txn_date=date(2026, 9, 2), name="COFFEE"
        )

    rows = parse(rbc_csv(row("9/2/2026", "COFFEE", "-9.00")), "r.csv", RBC)
    assert reconcile.classify(db_session, account.id, rows)[0].status == NEW


def test_conflicts_are_skipped_unless_explicitly_included(client, db_session):
    account = make_account(db_session)
    make_transaction(
        db_session, account=account, amount=20.00, txn_date=date(2026, 9, 2), name="RESTAURANT"
    )
    db_session.commit()
    data = rbc_csv(row("9/2/2026", "RESTAURANT", "-24.00"))

    skipped = client.post(
        "/api/imports/commit",
        files={"file": ("r.csv", data, "text/csv")},
        data={"account_id": account.id, "preset": "rbc"},
    ).json()
    assert skipped["imported"] == 0
    assert skipped["conflict"] == 1

    forced = client.post(
        "/api/imports/commit",
        files={"file": ("r.csv", data, "text/csv")},
        data={"account_id": account.id, "preset": "rbc", "include_conflicts": "true"},
    ).json()
    assert forced["imported"] == 1


# ---- coverage / gaps ----


def test_merges_touching_and_overlapping_periods():
    merged = reconcile.merge_ranges(
        [
            DateRange(date(2026, 6, 1), date(2026, 6, 30)),
            DateRange(date(2026, 7, 1), date(2026, 7, 31)),  # touching
            DateRange(date(2026, 7, 15), date(2026, 8, 10)),  # overlapping
        ]
    )
    assert len(merged) == 1
    assert (merged[0].start, merged[0].end) == (date(2026, 6, 1), date(2026, 8, 10))


def test_reports_the_hole_between_two_statement_periods():
    gaps = reconcile.find_gaps(
        [
            DateRange(date(2026, 6, 1), date(2026, 6, 30)),
            DateRange(date(2026, 8, 1), date(2026, 8, 31)),
        ],
        until=date(2026, 8, 31),
    )
    assert len(gaps) == 1
    assert (gaps[0].start, gaps[0].end) == (date(2026, 7, 1), date(2026, 7, 31))


def test_reports_the_tail_gap_since_the_last_import():
    gaps = reconcile.find_gaps(
        [DateRange(date(2026, 8, 1), date(2026, 8, 31))], until=date(2026, 9, 15)
    )
    assert (gaps[-1].start, gaps[-1].end) == (date(2026, 9, 1), date(2026, 9, 15))


def test_preview_warns_about_the_gap_an_import_would_leave(client, db_session):
    account = manual_account(db_session)
    db_session.commit()
    client.post(
        "/api/imports/commit",
        files={"file": ("jun.csv", rbc_csv(row("6/1/2026", "COFFEE", "-4.50")), "text/csv")},
        data={"account_id": account.id, "preset": "rbc"},
    )

    preview = client.post(
        "/api/imports/preview",
        files={"file": ("aug.csv", rbc_csv(row("8/1/2026", "COFFEE", "-4.50")), "text/csv")},
        data={"account_id": account.id, "preset": "rbc"},
    ).json()

    # June and August are covered; July is the hole the upload would leave behind.
    july = [g for g in preview["gaps_after"] if g["start"] == "2026-06-02"]
    assert july and july[0]["end"] == "2026-07-31"


def test_coverage_endpoint_lists_gaps_per_account(client, db_session):
    account = manual_account(db_session)
    db_session.commit()
    client.post(
        "/api/imports/commit",
        files={"file": ("jun.csv", rbc_csv(row("6/1/2026", "COFFEE", "-4.50")), "text/csv")},
        data={"account_id": account.id, "preset": "rbc"},
    )

    coverage = client.get("/api/imports/coverage").json()
    mine = [c for c in coverage if c["account_id"] == account.id][0]

    assert mine["source"] == SOURCE_CSV
    assert mine["last_imported_period_end"] == "2026-06-01"
    assert mine["gaps"]  # everything since June is uncovered


# ---- wiring ----


def test_creates_an_account_with_no_plaid_identity(client, db_session):
    created = client.post(
        "/api/imports/accounts", json={"name": "RBC Chequing", "current_balance": 1200.0}
    )
    assert created.status_code == 201

    account = db_session.query(Account).filter_by(id=created.json()["id"]).one()
    assert account.source == SOURCE_CSV
    assert account.plaid_item_id is None
    assert account.plaid_account_id is None


def test_imported_rows_pick_up_existing_category_rules(client, db_session):
    account = manual_account(db_session)
    db_session.commit()
    client.patch(
        f"/api/finance/transactions/{make_transaction(db_session, account=account, amount=1.0, name='TIM HORTONS').id}",
        json={"category": "Dining"},
    )
    db_session.commit()

    client.post(
        "/api/imports/commit",
        files={"file": ("r.csv", rbc_csv(row("9/2/2026", "TIM HORTONS", "-4.50")), "text/csv")},
        data={"account_id": account.id, "preset": "rbc"},
    )

    imported = (
        db_session.query(Transaction).filter(Transaction.source == SOURCE_CSV).one()
    )
    assert imported.category == "Dining"


def test_unparseable_upload_is_a_422_not_a_500(client, db_session):
    account = manual_account(db_session)
    db_session.commit()
    response = client.post(
        "/api/imports/preview",
        files={"file": ("junk.csv", b"a,b\n1,2\n", "text/csv")},
        data={"account_id": account.id, "preset": "rbc"},
    )
    assert response.status_code == 422
