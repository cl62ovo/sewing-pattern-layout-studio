from typing import Protocol
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from plush_pattern_studio.api.models import (
    CreateModelJobRequest,
    CreatePatternJobRequest,
    CreateProjectRequest,
)
from plush_pattern_studio.contracts.generation import MeshyPrompt, PlushSpecification
from plush_pattern_studio.infrastructure.repository import ProjectRepository
from plush_pattern_studio.providers.errors import ProviderError
from plush_pattern_studio.settings import Settings


class SpecificationProvider(Protocol):
    async def normalize_specification(
        self, description: str, height_mm: float, locale: str
    ) -> PlushSpecification: ...

    async def create_meshy_prompt(self, specification: PlushSpecification) -> MeshyPrompt: ...


class BalanceProvider(Protocol):
    async def balance(self) -> int: ...


def create_projects_router(
    settings: Settings,
    repository: ProjectRepository,
    openrouter: SpecificationProvider | None,
    meshy: BalanceProvider | None,
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/capabilities")
    async def capabilities() -> dict[str, object]:
        balance: int | None = None
        if meshy is not None:
            try:
                balance = await meshy.balance()
            except ProviderError:
                balance = None
        return {
            "mode": "local",
            "openRouter": openrouter is not None,
            "meshy": meshy is not None,
            "meshyBalance": balance,
            "authentication": False,
            "queue": "sqlite-worker",
            "objectStorage": settings.object_storage_mode,
        }

    @router.get("/projects")
    async def list_projects() -> list[dict[str, object]]:
        return await repository.list_projects()

    @router.post("/projects", status_code=201)
    async def create_project(request: CreateProjectRequest) -> dict[str, object]:
        if openrouter is None:
            raise HTTPException(503, detail={"code": "OPENROUTER_NOT_CONFIGURED"})
        try:
            specification = await openrouter.normalize_specification(
                request.description,
                request.heightMm,
                request.locale,
            )
            prompt = (
                await openrouter.create_meshy_prompt(specification)
                if specification.supported
                else None
            )
        except ProviderError as error:
            raise HTTPException(
                error.status_code or 502,
                detail={"code": error.code, "message": str(error)},
            ) from error
        project_id = await repository.create_project(
            name=request.name,
            description=request.description,
            height_mm=request.heightMm,
            seam_allowance_mm=request.seamAllowanceMm,
            locale=request.locale,
            specification=specification,
            meshy_prompt=prompt,
        )
        project = await repository.get_project(project_id)
        if project is None:
            raise HTTPException(500, detail={"code": "PROJECT_PERSIST_FAILED"})
        return project

    @router.get("/projects/{project_id}")
    async def get_project(project_id: UUID) -> dict[str, object]:
        project = await repository.get_project(project_id)
        if project is None:
            raise HTTPException(404, detail={"code": "PROJECT_NOT_FOUND"})
        return project

    @router.post("/versions/{version_id}/model-jobs", status_code=202)
    async def create_model_job(
        version_id: UUID,
        request: CreateModelJobRequest,
    ) -> dict[str, object]:
        if meshy is None:
            raise HTTPException(503, detail={"code": "MESHY_NOT_CONFIGURED"})
        try:
            return await repository.create_model_job(version_id, request.idempotencyKey)
        except LookupError as error:
            raise HTTPException(404, detail={"code": "VERSION_NOT_FOUND"}) from error

    async def enqueue_pattern_job(
        version_id: UUID,
        request: CreatePatternJobRequest,
    ) -> dict[str, object]:
        try:
            return await repository.create_pattern_job(version_id, request.idempotencyKey)
        except LookupError as error:
            raise HTTPException(404, detail={"code": "VERSION_NOT_FOUND"}) from error
        except ValueError as error:
            raise HTTPException(409, detail={"code": "MODEL_NOT_READY"}) from error

    router.add_api_route(
        "/versions/{version_id}/accept-model",
        enqueue_pattern_job,
        methods=["POST"],
        status_code=202,
    )
    router.add_api_route(
        "/versions/{version_id}/pattern-jobs",
        enqueue_pattern_job,
        methods=["POST"],
        status_code=202,
    )

    @router.get("/versions/{version_id}/pattern")
    async def get_pattern(version_id: UUID) -> dict[str, object]:
        payload = repository._read_json_kind(
            await repository.get_assets(version_id), "pattern_report"
        )
        if payload is None:
            raise HTTPException(404, detail={"code": "PATTERN_NOT_FOUND"})
        return payload

    @router.get("/versions/{version_id}/quality-report")
    async def get_quality_report(version_id: UUID) -> dict[str, object]:
        payload = repository._read_json_kind(
            await repository.get_assets(version_id), "pattern_report"
        )
        if payload is None:
            raise HTTPException(404, detail={"code": "PATTERN_NOT_FOUND"})
        return payload["quality"]

    @router.get("/jobs/{job_id}")
    async def get_job(job_id: UUID) -> dict[str, object]:
        job = await repository.get_job(job_id)
        if job is None:
            raise HTTPException(404, detail={"code": "JOB_NOT_FOUND"})
        return job

    @router.post("/jobs/{job_id}/resume", status_code=202)
    async def resume_job(job_id: UUID) -> dict[str, object]:
        try:
            return await repository.resume_model_job(job_id)
        except LookupError as error:
            raise HTTPException(404, detail={"code": "JOB_NOT_FOUND"}) from error
        except ValueError as error:
            raise HTTPException(409, detail={"code": "JOB_NOT_RECOVERABLE"}) from error

    @router.get("/assets/{asset_id}")
    async def download_asset(asset_id: UUID) -> FileResponse:
        asset = await repository.get_asset(asset_id)
        if asset is None:
            raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND"})
        try:
            path = repository.storage.path_for(asset["storage_key"])
        except FileNotFoundError as error:
            raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND"}) from error
        return FileResponse(path, media_type=asset["content_type"], filename=path.name)

    return router