import argparse
import asyncio
import json
import tempfile
from pathlib import Path
from uuid import UUID

from plush_pattern_studio.contracts.generation import MeshyTaskStatus
from plush_pattern_studio.contracts.pipeline import ErrorCode
from plush_pattern_studio.geometry.normalize import normalize_glb
from plush_pattern_studio.geometry.pattern import PatternBuildError, build_pattern
from plush_pattern_studio.infrastructure.database import Database
from plush_pattern_studio.infrastructure.migrate import migrate
from plush_pattern_studio.infrastructure.object_storage import LocalObjectStorage
from plush_pattern_studio.infrastructure.repository import ProjectRepository
from plush_pattern_studio.providers.errors import ProviderError
from plush_pattern_studio.providers.meshy import MeshyClient
from plush_pattern_studio.settings import Settings, get_settings

AMBIGUOUS_TERMINAL_POLL_LIMIT = 24


async def _process_pattern_job(
    repository: ProjectRepository,
    job: dict[str, object],
) -> bool:
    job_id = UUID(str(job["id"]))
    version_id = UUID(str(job["version_id"]))
    if job["state"] == "queued":
        await repository.mark_pattern_job_started(job_id)
        return True
    try:
        version = await repository.get_project_for_version(version_id)
        normalized_asset = next(
            asset
            for asset in await repository.get_assets(version_id)
            if asset["kind"] == "normalized_glb"
        )
        normalized_path = repository.storage.path_for(normalized_asset["storage_key"])
        with tempfile.TemporaryDirectory(prefix="plush-pattern-build-") as temporary:
            output_directory = Path(temporary)
            report = build_pattern(
                normalized_path,
                target_height_mm=version["heightMm"],
                seam_allowance_mm=version["seamAllowanceMm"],
                output_directory=output_directory,
            )
            payload = report.model_dump(mode="json", by_alias=True)
            await repository.add_json_asset(version_id, "pattern_report", payload)
            await repository.add_asset(
                version_id,
                "pattern_svg",
                f"versions/{version_id}/pattern.svg",
                "image/svg+xml",
                (output_directory / "pattern.svg").read_bytes(),
                {"experimental": True, "passed": report.quality.passed},
            )
            if report.pdf_file_name is not None:
                await repository.add_asset(
                    version_id,
                    "pattern_pdf",
                    f"versions/{version_id}/pattern.pdf",
                    "application/pdf",
                    (output_directory / report.pdf_file_name).read_bytes(),
                    {"experimental": True, "passed": True, "scale": "1:1"},
                )
            await repository.save_pattern_run(version_id, payload["quality"])
        await repository.finish_pattern_job(
            job_id,
            version_id,
            computed=True,
            pattern_passed=report.quality.passed,
            error_code=(
                None
                if report.quality.passed
                else str(report.quality.failure_reasons[0])
            ),
        )
    except (PatternBuildError, LookupError, StopIteration, ValueError) as error:
        code = error.code if isinstance(error, PatternBuildError) else ErrorCode.PROVIDER_ASSET_INVALID
        await repository.finish_pattern_job(
            job_id,
            version_id,
            computed=False,
            error_code=str(code),
        )
    return True


async def process_once(settings: Settings, meshy: MeshyClient | None = None) -> bool:
    database = Database(settings.database_url)
    storage = LocalObjectStorage(settings.object_storage_path)
    repository = ProjectRepository(database, storage)
    try:
        await migrate(database)
        pattern_job = await repository.next_pattern_job()
        if pattern_job is not None:
            return await _process_pattern_job(repository, pattern_job)
        job = await repository.next_model_job()
        if job is None:
            return False
        job_id = UUID(str(job["id"]))
        version_id = UUID(str(job["version_id"]))
        if meshy is None:
            if settings.meshy_api_key is None:
                await repository.finish_job(
                    job_id,
                    version_id,
                    succeeded=False,
                    error_code="MESHY_NOT_CONFIGURED",
                )
                return True
            meshy = MeshyClient(settings.meshy_api_key.get_secret_value())

        try:
            if job["state"] == "queued":
                prompt = await repository.get_meshy_prompt(version_id)
                external_id = await meshy.create_preview(prompt.positivePrompt)
                await repository.mark_job_started(job_id, external_id)
                return True

            task = await meshy.get_task(str(job["external_job_id"]))
            previous_details = job.get("error_details") or {}
            terminal_observations = 0
            if task.status in {MeshyTaskStatus.FAILED, MeshyTaskStatus.CANCELED}:
                terminal_observations = int(previous_details.get("terminalObservations", 0)) + 1
            await repository.update_running_job(
                job_id,
                progress=task.progress,
                thumbnail_url=task.thumbnail_url,
                consumed_credits=task.consumed_credits,
                provider_status=task.status.value,
                terminal_observations=terminal_observations,
            )
            if task.status in {MeshyTaskStatus.PENDING, MeshyTaskStatus.IN_PROGRESS}:
                return True
            provider_message = task.task_error.get("message")
            error_message = (
                provider_message.strip()[:500]
                if isinstance(provider_message, str) and provider_message.strip()
                else None
            )
            if (
                task.status in {MeshyTaskStatus.FAILED, MeshyTaskStatus.CANCELED}
                and error_message is None
                and terminal_observations < AMBIGUOUS_TERMINAL_POLL_LIMIT
            ):
                return True
            if task.status != MeshyTaskStatus.SUCCEEDED:
                await repository.finish_job(
                    job_id,
                    version_id,
                    succeeded=False,
                    error_code="PROVIDER_GENERATION_FAILED",
                    details={
                        "progress": task.progress,
                        "providerStatus": task.status.value,
                        "errorMessage": error_message,
                    },
                )
                return True
            if "glb" not in task.model_urls:
                await repository.finish_job(
                    job_id,
                    version_id,
                    succeeded=False,
                    error_code="PROVIDER_ASSET_INVALID",
                    details={
                        "progress": task.progress,
                        "providerStatus": task.status.value,
                        "errorMessage": "Meshy completed without a GLB asset.",
                    },
                )
                return True

            source_glb = await meshy.download_bytes(task.model_urls["glb"])
            with tempfile.TemporaryDirectory(prefix="plush-pattern-") as temporary:
                source_path = Path(temporary) / "source.glb"
                normalized_path = Path(temporary) / "normalized.glb"
                source_path.write_bytes(source_glb)
                project = await repository.get_project_for_version(version_id)
                report = normalize_glb(
                    source_path,
                    target_height_mm=project["heightMm"],
                    output_glb=normalized_path,
                )
                await repository.add_asset(
                    version_id,
                    "source_glb",
                    f"versions/{version_id}/source.glb",
                    "model/gltf-binary",
                    source_glb,
                )
                await repository.add_json_asset(
                    version_id,
                    "normalization_report",
                    report.model_dump(mode="json", by_alias=True),
                )
                succeeded = report.stages[0].status == "completed"
                if succeeded:
                    await repository.add_asset(
                        version_id,
                        "normalized_glb",
                        f"versions/{version_id}/normalized.glb",
                        "model/gltf-binary",
                        normalized_path.read_bytes(),
                    )
            await repository.finish_job(
                job_id,
                version_id,
                succeeded=succeeded,
                error_code=None if succeeded else str(report.stages[0].error_code),
                details={
                    "progress": 100,
                    "thumbnailUrl": task.thumbnail_url,
                    "consumedCredits": task.consumed_credits,
                },
            )
            return True
        except (ProviderError, LookupError, ValueError) as error:
            code = error.code if isinstance(error, ProviderError) else "PROVIDER_GENERATION_FAILED"
            await repository.finish_job(
                job_id,
                version_id,
                succeeded=False,
                error_code=code,
            )
            return True
    finally:
        await database.close()


async def run_worker(settings: Settings, once: bool, interval: float) -> None:
    while True:
        processed = await process_once(settings)
        print(
            json.dumps({"service": "worker", "status": "processed" if processed else "idle"}),
            flush=True,
        )
        if once:
            return
        await asyncio.sleep(max(interval, 1.0))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Plush Pattern Studio worker.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()
    asyncio.run(run_worker(get_settings(), args.once, args.interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
