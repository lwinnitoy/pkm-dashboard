"""EncryptedString column type: transparent round-trip, ciphertext at rest."""
from sqlalchemy import inspect, text

from app.crypto import decrypt, encrypt
from app.models import PlaidItem


def test_encrypt_decrypt_round_trips():
    token = "access-sandbox-super-secret"
    assert decrypt(encrypt(token)) == token
    # Ciphertext is non-deterministic and never equals the plaintext.
    assert encrypt(token) != token


def test_encrypted_string_column_round_trips_via_orm(db_session):
    """Reading a PlaidItem back yields the original plaintext access_token."""
    item = PlaidItem(item_id="item-1", access_token="plain-token-123")
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    fetched = db_session.query(PlaidItem).filter_by(item_id="item-1").first()
    assert fetched.access_token == "plain-token-123"


def test_raw_stored_value_is_ciphertext(db_session):
    """The value physically stored in the column must not be the plaintext."""
    db_session.add(PlaidItem(item_id="item-2", access_token="plain-token-456"))
    db_session.commit()

    # Read the raw column bypassing the TypeDecorator.
    table = inspect(PlaidItem).local_table.name
    raw = db_session.execute(
        text(f"SELECT access_token FROM {table} WHERE item_id = :iid"),
        {"iid": "item-2"},
    ).scalar_one()

    assert raw != "plain-token-456"
    # ...but it decrypts back to the original.
    assert decrypt(raw) == "plain-token-456"
