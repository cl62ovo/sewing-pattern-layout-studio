import argparse
import asyncio

from sqlalchemy import insert, select

from plush_pattern_studio.infrastructure.database import Database
from plush_pattern_studio.infrastructure.schema import metadata, schema_migrations
from plush_pattern_studio.settings import get_settings

INITIAL_SCHEMA_VERSION = "0001_initial"


async def migrate(database: Database) -> None:
    async with database.engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
        existing = await connection.scalar(
            select(schema_migrations.c.version).where(
                schema_migrations.c.version == INITIAL_SCHEMA_VERSION
            )
        )
        if existing is None:
            await connection.execute(
                insert(schema_migrations).values(version=INITIAL_SCHEMA_VERSION)
            )


async def run(database_url: str) -> None:
    database = Database(database_url)
    try:
        await migrate(database)
    finally:
        await database.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply database schema migrations.")
    parser.add_argument("command", choices=["migrate"])
    parser.add_argument("--database-url", default=get_settings().database_url)
    args = parser.parse_args()
    asyncio.run(run(args.database_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
