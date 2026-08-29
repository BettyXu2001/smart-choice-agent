from __future__ import annotations

import pytest

from choice_agent.config import Settings
from choice_agent.database import Database
from choice_agent.domains.diet.seed import seed_legacy_data


@pytest.fixture
def database(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")
    database = Database(settings)
    database.create_all()
    with database.session_factory() as db:
        seed_legacy_data(db)
    return database


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")

