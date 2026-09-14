"""DATABASE_URL normalization (hosts hand out bare postgres:// URLs)."""
from app.config import Settings


def test_sqlalchemy_url_selects_psycopg_driver():
    assert (
        Settings(database_url="postgres://u:p@h:5432/db").sqlalchemy_url
        == "postgresql+psycopg://u:p@h:5432/db"
    )
    assert (
        Settings(database_url="postgresql://u:p@h/db").sqlalchemy_url
        == "postgresql+psycopg://u:p@h/db"
    )


def test_sqlalchemy_url_leaves_sqlite_and_explicit_driver_untouched():
    assert Settings(database_url="sqlite:///./pkm.db").sqlalchemy_url == "sqlite:///./pkm.db"
    explicit = "postgresql+psycopg://u:p@h/db"
    assert Settings(database_url=explicit).sqlalchemy_url == explicit
