from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, insert, select, update

from plush_pattern_studio.contracts.generation import MeshyPrompt, PlushSpecification
from plush_pattern_studio.infrastructure.database import Database
from plush_pattern_studio.infrastructure.object_storage import LocalObjectStorage
from plush_pattern_studio.infrastructure.schema import (
    assets,
    jobs,
    pattern_runs,
    project_versions,
    projects,
    users,
)

LOCAL_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def utc_now() -> datetime:
    return datetime.now(UTC)


class ProjectRepository:
    def __init__(self, database: Database, storage: LocalObjectStorage) -> None:
        self.database = database
        self.storage = storage

    async def ensure_local_user(self) -> None:
        async with self.database.engine.begin() as connection:
            existing = await connection.scalar(
                select(users.c.id).where(users.c.id == LOCAL_USER_ID)
            )
            if existing is None:
                await connection.execute(
                    insert(users).values(
                        id=LOCAL_USER_ID,
                        google_subject="local-development-user",
                        email="local@plush-pattern.invalid",
                        display_name="Local Studio",
                    )
                )

    async def create_project(
        self,
        *,
        name: str,
        description: str,
        height_mm: float,
        seam_allowance_mm: float,
        locale: str,
        specification: PlushSpecification,
        meshy_prompt: MeshyPrompt | None,
    ) -> UUID:
        await self.ensure_local_user()
        project_id = uuid4()
        version_id = uuid4()
        now = utc_now()
        status = "draft" if specification.supported and meshy_prompt else "failed"
        async with self.database.engine.begin() as connection:
            await connection.execute(
                insert(projects).values(
                    id=project_id,
                    owner_id=LOCAL_USER_ID,
                    name=name,
                    locale=locale,
                    created_at=now,
                    updated_at=now,
                )
            )
            await connection.execute(
                insert(project_versions).values(
                    id=version_id,
                    project_id=project_id,
                    version_number=1,
                    status=status,
                    prompt_text=description,
                    height_mm=Decimal(str(height_mm)),
                    seam_allowance_mm=Decimal(str(seam_allowance_mm)),
                    material_preset="low_stretch_short_plush",
                    algorithm_version="normalize-v3",
                    prompt_version="p01-v1+p02-v1",
                    created_at=now,
                    updated_at=now,
                )
            )

        await self.add_json_asset(version_id, "validated_spec", specification.model_dump())
        if meshy_prompt is not None:
            await self.add_json_asset(version_id, "meshy_prompt", meshy_prompt.model_dump())
        return project_id

    async def add_json_asset(
        self,
        version_id: UUID,
        kind: str,
        payload: dict[str, Any],
    ) -> UUID:
        return await self.add_asset(
            version_id,
            kind,
            f"versions/{version_id}/{kind}.json",
            "application/json",
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        )

    async def add_asset(
        self,
        version_id: UUID,
        kind: str,
        storage_key: str,
        content_type: str,
        payload: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> UUID:
        stored = self.storage.put_bytes(storage_key, payload)
        async with self.database.engine.begin() as connection:
            existing_id = await connection.scalar(
                select(assets.c.id).where(assets.c.storage_key == stored.key)
            )
            if existing_id is not None:
                await connection.execute(
                    update(assets)
                    .where(assets.c.id == existing_id)
                    .values(
                        content_type=content_type,
                        byte_size=stored.byte_size,
                        sha256=stored.sha256,
                        asset_metadata=metadata or {},
                    )
                )
                return existing_id
            asset_id = uuid4()
            await connection.execute(
                insert(assets).values(
                    id=asset_id,
                    version_id=version_id,
                    kind=kind,
                    storage_key=stored.key,
                    content_type=content_type,
                    byte_size=stored.byte_size,
                    sha256=stored.sha256,
                    asset_metadata=metadata or {},
                )
            )
        return asset_id

    async def list_projects(self) -> list[dict[str, Any]]:
        query = (
            select(
                projects.c.id,
                projects.c.name,
                projects.c.locale,
                projects.c.updated_at,
                project_versions.c.id.label("version_id"),
                project_versions.c.status,
                project_versions.c.height_mm,
            )
            .join(project_versions, project_versions.c.project_id == projects.c.id)
            .where(project_versions.c.version_number == 1)
            .order_by(projects.c.updated_at.desc())
        )
        async with self.database.engine.connect() as connection:
            rows = (await connection.execute(query)).mappings().all()
        return [
            {
                "id": str(row["id"]),
                "name": row["name"],
                "locale": row["locale"],
                "updatedAt": row["updated_at"],
                "versionId": str(row["version_id"]),
                "status": row["status"],
                "heightMm": float(row["height_mm"]),
            }
            for row in rows
        ]

    async def get_project(self, project_id: UUID) -> dict[str, Any] | None:
        query = (
            select(projects, project_versions)
            .join(project_versions, project_versions.c.project_id == projects.c.id)
            .where(
                and_(
                    projects.c.id == project_id,
                    project_versions.c.version_number == 1,
                )
            )
        )
        async with self.database.engine.connect() as connection:
            row = (await connection.execute(query)).mappings().first()
        if row is None:
            return None

        version_id = row[project_versions.c.id]
        version_assets = await self.get_assets(version_id)
        latest_job = await self.get_latest_job(version_id)
        return {
            "id": str(row[projects.c.id]),
            "name": row[projects.c.name],
            "locale": row[projects.c.locale],
            "createdAt": row[projects.c.created_at],
            "version": {
                "id": str(version_id),
                "status": row[project_versions.c.status],
                "description": row[project_versions.c.prompt_text],
                "heightMm": float(row[project_versions.c.height_mm]),
                "seamAllowanceMm": float(row[project_versions.c.seam_allowance_mm]),
                "specification": self._read_json_kind(version_assets, "validated_spec"),
                "meshyPrompt": self._read_json_kind(version_assets, "meshy_prompt"),
                "assets": [self._public_asset(asset) for asset in version_assets],
                "latestJob": self._public_job(latest_job) if latest_job else None,
            },
        }

    async def get_project_for_version(self, version_id: UUID) -> dict[str, Any]:
        async with self.database.engine.connect() as connection:
            row = (
                await connection.execute(
                    select(
                        project_versions.c.project_id,
                        project_versions.c.height_mm,
                        project_versions.c.seam_allowance_mm,
                    ).where(project_versions.c.id == version_id)
                )
            ).mappings().first()
        if row is None:
            raise LookupError("version")
        return {
            "projectId": str(row["project_id"]),
            "heightMm": float(row["height_mm"]),
            "seamAllowanceMm": float(row["seam_allowance_mm"]),
        }

    async def get_assets(self, version_id: UUID) -> list[dict[str, Any]]:
        async with self.database.engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(assets).where(assets.c.version_id == version_id)
                )
            ).mappings().all()
        return [dict(row) for row in rows]

    def _read_json_kind(
        self,
        version_assets: list[dict[str, Any]],
        kind: str,
    ) -> dict[str, Any] | None:
        asset = next((item for item in version_assets if item["kind"] == kind), None)
        if asset is None:
            return None
        return json.loads(self.storage.read_bytes(asset["storage_key"]))

    @staticmethod
    def _public_asset(asset: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(asset["id"]),
            "kind": asset["kind"],
            "contentType": asset["content_type"],
            "byteSize": asset["byte_size"],
            "sha256": asset["sha256"],
            "url": f"/api/assets/{asset['id']}",
            "metadata": asset["asset_metadata"],
        }

    async def get_asset(self, asset_id: UUID) -> dict[str, Any] | None:
        async with self.database.engine.connect() as connection:
            row = (
                await connection.execute(select(assets).where(assets.c.id == asset_id))
            ).mappings().first()
        return dict(row) if row else None

    async def create_model_job(
        self,
        version_id: UUID,
        idempotency_key: str,
    ) -> dict[str, Any]:
        async with self.database.engine.begin() as connection:
            version_exists = await connection.scalar(
                select(project_versions.c.id).where(project_versions.c.id == version_id)
            )
            if version_exists is None:
                raise LookupError("version")
            existing = (
                await connection.execute(
                    select(jobs).where(
                        and_(
                            jobs.c.version_id == version_id,
                            jobs.c.kind == "generate_model",
                            jobs.c.idempotency_key == idempotency_key,
                        )
                    )
                )
            ).mappings().first()
            if existing:
                return self._public_job(dict(existing))
            job_id = uuid4()
            await connection.execute(
                insert(jobs).values(
                    id=job_id,
                    version_id=version_id,
                    kind="generate_model",
                    state="queued",
                    stage="queued",
                    idempotency_key=idempotency_key,
                    attempt=1,
                    progress_message_key="model.queued",
                    error_details={"progress": 0},
                )
            )
            await connection.execute(
                update(project_versions)
                .where(project_versions.c.id == version_id)
                .values(status="generating_model", updated_at=utc_now())
            )
        return await self.get_job(job_id) or {}

    async def create_pattern_job(
        self,
        version_id: UUID,
        idempotency_key: str,
    ) -> dict[str, Any]:
        async with self.database.engine.begin() as connection:
            version = (
                await connection.execute(
                    select(project_versions.c.status).where(
                        project_versions.c.id == version_id
                    )
                )
            ).mappings().first()
            if version is None:
                raise LookupError("version")
            existing = (
                await connection.execute(
                    select(jobs).where(
                        and_(
                            jobs.c.version_id == version_id,
                            jobs.c.kind == "build_pattern",
                            jobs.c.idempotency_key == idempotency_key,
                        )
                    )
                )
            ).mappings().first()
            if existing:
                return self._public_job(dict(existing))
            normalized_exists = await connection.scalar(
                select(assets.c.id).where(
                    and_(
                        assets.c.version_id == version_id,
                        assets.c.kind == "normalized_glb",
                    )
                )
            )
            if normalized_exists is None or version["status"] not in {
                "model_review",
                "pattern_review",
                "ready",
            }:
                raise ValueError("model is not ready")
            job_id = uuid4()
            await connection.execute(
                insert(jobs).values(
                    id=job_id,
                    version_id=version_id,
                    kind="build_pattern",
                    state="queued",
                    stage="segmenting",
                    idempotency_key=idempotency_key,
                    attempt=1,
                    started_at=utc_now(),
                    progress_message_key="pattern.queued",
                    error_details={"progress": 0},
                )
            )
            await connection.execute(
                update(project_versions)
                .where(project_versions.c.id == version_id)
                .values(status="segmenting", updated_at=utc_now())
            )
        return await self.get_job(job_id) or {}

    async def get_job(self, job_id: UUID) -> dict[str, Any] | None:
        async with self.database.engine.connect() as connection:
            row = (
                await connection.execute(select(jobs).where(jobs.c.id == job_id))
            ).mappings().first()
        return self._public_job(dict(row)) if row else None

    async def get_latest_model_job(self, version_id: UUID) -> dict[str, Any] | None:
        async with self.database.engine.connect() as connection:
            row = (
                await connection.execute(
                    select(jobs)
                    .where(
                        and_(
                            jobs.c.version_id == version_id,
                            jobs.c.kind == "generate_model",
                        )
                    )
                    .order_by(jobs.c.started_at.desc())
                    .limit(1)
                )
            ).mappings().first()
        return dict(row) if row else None

    async def get_latest_job(self, version_id: UUID) -> dict[str, Any] | None:
        async with self.database.engine.connect() as connection:
            row = (
                await connection.execute(
                    select(jobs)
                    .where(jobs.c.version_id == version_id)
                    .order_by(jobs.c.started_at.desc(), jobs.c.id.desc())
                    .limit(1)
                )
            ).mappings().first()
        return dict(row) if row else None

    @staticmethod
    def _public_job(job: dict[str, Any]) -> dict[str, Any]:
        details = job.get("error_details") or {}
        return {
            "id": str(job["id"]),
            "versionId": str(job["version_id"]),
            "kind": job["kind"],
            "state": job["state"],
            "stage": job["stage"],
            "progress": details.get("progress", 0),
            "thumbnailUrl": details.get("thumbnailUrl"),
            "consumedCredits": details.get("consumedCredits"),
            "errorCode": job.get("error_code"),
            "errorMessage": details.get("errorMessage"),
            "providerStatus": details.get("providerStatus"),
            "patternPassed": details.get("patternPassed"),
        }

    async def resume_model_job(self, job_id: UUID) -> dict[str, Any]:
        async with self.database.engine.begin() as connection:
            row = (
                await connection.execute(select(jobs).where(jobs.c.id == job_id))
            ).mappings().first()
            if row is None:
                raise LookupError("job")
            if row["state"] != "failed" or not row["external_job_id"]:
                raise ValueError("job is not recoverable")
            await connection.execute(
                update(jobs)
                .where(jobs.c.id == job_id)
                .values(
                    state="running",
                    stage="provider_generation",
                    error_code=None,
                    error_details={
                        "progress": 0,
                        "providerStatus": "RECOVERING",
                        "terminalObservations": 0,
                    },
                    finished_at=None,
                    heartbeat_at=utc_now(),
                    progress_message_key="model.generating",
                )
            )
            await connection.execute(
                update(project_versions)
                .where(project_versions.c.id == row["version_id"])
                .values(status="generating_model", updated_at=utc_now())
            )
        resumed = await self.get_job(job_id)
        if resumed is None:
            raise LookupError("job")
        return resumed

    async def next_model_job(self) -> dict[str, Any] | None:
        query = (
            select(jobs)
            .where(
                and_(
                    jobs.c.kind == "generate_model",
                    jobs.c.state.in_(["queued", "running"]),
                )
            )
            .order_by(jobs.c.started_at.asc())
            .limit(1)
        )
        async with self.database.engine.connect() as connection:
            row = (await connection.execute(query)).mappings().first()
        return dict(row) if row else None

    async def next_pattern_job(self) -> dict[str, Any] | None:
        query = (
            select(jobs)
            .where(
                and_(
                    jobs.c.kind == "build_pattern",
                    jobs.c.state.in_(["queued", "running"]),
                )
            )
            .order_by(jobs.c.started_at.asc(), jobs.c.id.asc())
            .limit(1)
        )
        async with self.database.engine.connect() as connection:
            row = (await connection.execute(query)).mappings().first()
        return dict(row) if row else None

    async def mark_pattern_job_started(self, job_id: UUID) -> None:
        async with self.database.engine.begin() as connection:
            await connection.execute(
                update(jobs)
                .where(jobs.c.id == job_id)
                .values(
                    state="running",
                    stage="segmenting",
                    started_at=utc_now(),
                    heartbeat_at=utc_now(),
                    progress_message_key="pattern.segmenting",
                    error_details={"progress": 20},
                )
            )

    async def save_pattern_run(
        self,
        version_id: UUID,
        quality: dict[str, Any],
    ) -> None:
        async with self.database.engine.begin() as connection:
            attempt = int(
                await connection.scalar(
                    select(pattern_runs.c.attempt)
                    .where(pattern_runs.c.version_id == version_id)
                    .order_by(pattern_runs.c.attempt.desc())
                    .limit(1)
                )
                or 0
            ) + 1
            await connection.execute(
                insert(pattern_runs).values(
                    id=uuid4(),
                    version_id=version_id,
                    attempt=attempt,
                    piece_count=quality["pieceCount"],
                    mean_distortion=Decimal(str(quality["meanDistortion"])),
                    max_distortion=Decimal(str(quality["maxDistortion"])),
                    max_seam_mismatch=Decimal(str(quality["maxSeamMismatch"])),
                    flipped_triangle_count=quality["flippedTriangleCount"],
                    passed=quality["passed"],
                    failure_reasons=quality["failureReasons"],
                    metrics=quality,
                )
            )

    async def finish_pattern_job(
        self,
        job_id: UUID,
        version_id: UUID,
        *,
        computed: bool,
        pattern_passed: bool = False,
        error_code: str | None = None,
    ) -> None:
        now = utc_now()
        async with self.database.engine.begin() as connection:
            await connection.execute(
                update(jobs)
                .where(jobs.c.id == job_id)
                .values(
                    state="succeeded" if computed else "failed",
                    stage="ready" if pattern_passed else ("pattern_review" if computed else "failed"),
                    error_code=error_code,
                    error_details={
                        "progress": 100 if computed else 0,
                        "patternPassed": pattern_passed,
                    },
                    finished_at=now,
                    heartbeat_at=now,
                    progress_message_key="pattern.ready" if pattern_passed else "pattern.review",
                )
            )
            await connection.execute(
                update(project_versions)
                .where(project_versions.c.id == version_id)
                .values(
                    status="ready" if pattern_passed else ("pattern_review" if computed else "failed"),
                    algorithm_version="pattern-v3" if computed else project_versions.c.algorithm_version,
                    updated_at=now,
                )
            )

    async def get_meshy_prompt(self, version_id: UUID) -> MeshyPrompt:
        prompt_asset = next(
            item for item in await self.get_assets(version_id) if item["kind"] == "meshy_prompt"
        )
        payload = json.loads(self.storage.read_bytes(prompt_asset["storage_key"]))
        return MeshyPrompt.model_validate(payload)

    async def mark_job_started(self, job_id: UUID, external_job_id: str) -> None:
        async with self.database.engine.begin() as connection:
            await connection.execute(
                update(jobs)
                .where(jobs.c.id == job_id)
                .values(
                    state="running",
                    stage="provider_generation",
                    external_job_id=external_job_id,
                    started_at=utc_now(),
                    heartbeat_at=utc_now(),
                    progress_message_key="model.generating",
                    error_details={"progress": 0},
                )
            )

    async def update_running_job(
        self,
        job_id: UUID,
        *,
        progress: int,
        thumbnail_url: str | None,
        consumed_credits: int | None,
        provider_status: str,
        terminal_observations: int = 0,
    ) -> None:
        async with self.database.engine.begin() as connection:
            await connection.execute(
                update(jobs)
                .where(jobs.c.id == job_id)
                .values(
                    heartbeat_at=utc_now(),
                    error_details={
                        "progress": progress,
                        "thumbnailUrl": thumbnail_url,
                        "consumedCredits": consumed_credits,
                        "providerStatus": provider_status,
                        "terminalObservations": terminal_observations,
                    },
                )
            )

    async def finish_job(
        self,
        job_id: UUID,
        version_id: UUID,
        *,
        succeeded: bool,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        async with self.database.engine.begin() as connection:
            await connection.execute(
                update(jobs)
                .where(jobs.c.id == job_id)
                .values(
                    state="succeeded" if succeeded else "failed",
                    stage="model_review" if succeeded else "failed",
                    error_code=error_code,
                    error_details=details or {"progress": 100 if succeeded else 0},
                    finished_at=utc_now(),
                    heartbeat_at=utc_now(),
                    progress_message_key="model.ready" if succeeded else "model.failed",
                )
            )
            await connection.execute(
                update(project_versions)
                .where(project_versions.c.id == version_id)
                .values(
                    status="model_review" if succeeded else "failed",
                    updated_at=utc_now(),
                )
            )