"""Alembic migrations, run for real: production Postgres is built only from them,
while every other test uses `create_all`, so drift or a broken downgrade would
otherwise surface only on deploy."""
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.config import get_settings
from app.database import Base

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture()
def alembic_cfg(tmp_path, monkeypatch):
    # env.py reads the URL from the (cached) app settings.
    url = f"sqlite:///{tmp_path / 'migrations.db'}"
    monkeypatch.setattr(get_settings(), "database_url", url)
    # No ini file: env.py would otherwise fileConfig() the logging of the test run.
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return cfg, url


def _tables(url):
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()


def test_upgrade_matches_the_models_and_downgrades_cleanly(alembic_cfg):
    cfg, url = alembic_cfg

    command.upgrade(cfg, "head")
    assert _tables(url) == set(Base.metadata.tables)
    command.check(cfg)  # raises if the models have changes no migration covers

    command.downgrade(cfg, "base")
    assert _tables(url) == set()

    command.upgrade(cfg, "head")
    assert _tables(url) == set(Base.metadata.tables)
