import pytest

from app.config import settings
from app.database import get_connection, init_db


@pytest.fixture
def db(tmp_path):
    """Fresh temp-file SQLite database with an open connection, isolated per test."""
    db_path = tmp_path / "test.db"
    original = settings.database_url
    settings.database_url = f"sqlite:///{db_path.as_posix()}"
    init_db()
    conn = get_connection()
    yield conn
    conn.close()
    settings.database_url = original