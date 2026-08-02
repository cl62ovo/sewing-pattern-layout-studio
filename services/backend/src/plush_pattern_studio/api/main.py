from contextlib import asynccontextmanager

from fastapi import FastAPI

from plush_pattern_studio import __version__
from plush_pattern_studio.api.projects import create_projects_router
from plush_pattern_studio.infrastructure.database import Database
from plush_pattern_studio.infrastructure.migrate import migrate
from plush_pattern_studio.infrastructure.object_storage import LocalObjectStorage
from plush_pattern_studio.infrastructure.repository import ProjectRepository
from plush_pattern_studio.providers.meshy import MeshyClient
from plush_pattern_studio.providers.openrouter import OpenRouterClient
from plush_pattern_studio.settings import Settings, get_settings


def create_app(
    settings: Settings | None = None,
    *,
    openrouter_client: OpenRouterClient | None = None,
    meshy_client: MeshyClient | None = None,
) -> FastAPI:
    runtime_settings = settings or get_settings()
    database = Database(runtime_settings.database_url)
    storage = LocalObjectStorage(runtime_settings.object_storage_path)
    repository = ProjectRepository(database, storage)
    if openrouter_client is None and runtime_settings.openrouter_api_key is not None:
        openrouter_client = OpenRouterClient(
            runtime_settings.openrouter_api_key.get_secret_value(),
            runtime_settings.openrouter_model,
        )
    if meshy_client is None and runtime_settings.meshy_api_key is not None:
        meshy_client = MeshyClient(runtime_settings.meshy_api_key.get_secret_value())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await migrate(database)
        yield
        await database.close()

    app = FastAPI(
        title="Plush Pattern Studio API",
        version=__version__,
        lifespan=lifespan,
    )
    app.include_router(
        create_projects_router(
            runtime_settings,
            repository,
            openrouter_client,
            meshy_client,
        )
    )

    @app.get("/api/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "api",
            "version": __version__,
        }

    @app.get("/api/health/ready", tags=["health"])
    async def ready() -> dict[str, object]:
        checks: dict[str, str] = {}
        try:
            await database.ping()
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "failed"
        try:
            storage.health_check()
            checks["objectStorage"] = "ok"
        except Exception:
            checks["objectStorage"] = "failed"
        return {
            "status": "ok" if all(value == "ok" for value in checks.values()) else "degraded",
            "checks": checks,
        }

    return app


app = create_app()
