from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from plush_pattern_studio.api.main import create_app
from plush_pattern_studio.infrastructure.database import Database
from plush_pattern_studio.infrastructure.migrate import INITIAL_SCHEMA_VERSION, migrate
from plush_pattern_studio.infrastructure.object_storage import LocalObjectStorage
from plush_pattern_studio.infrastructure.schema import schema_migrations
from plush_pattern_studio.settings import Settings


def test_local_object_storage_round_trip(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path / "objects")

    stored = storage.put_bytes("tests/sample.txt", b"sample")

    assert stored.byte_size == 6
    assert storage.read_bytes(stored.key) == b"sample"
    storage.delete(stored.key)
    assert not (tmp_path / "objects" / "tests" / "sample.txt").exists()


async def test_initial_database_migration(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    try:
        await migrate(database)
        await migrate(database)
        async with database.engine.connect() as connection:
            versions = (await connection.execute(select(schema_migrations.c.version))).all()
        assert versions == [(INITIAL_SCHEMA_VERSION,)]
    finally:
        await database.close()


def test_ready_health_checks_database_and_storage(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'ready.db'}",
        object_storage_path=tmp_path / "objects",
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "objectStorage": "ok"},
    }