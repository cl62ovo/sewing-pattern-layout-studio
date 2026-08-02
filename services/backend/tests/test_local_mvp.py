from pathlib import Path

import trimesh
from fastapi.testclient import TestClient

from plush_pattern_studio.api.main import create_app
from plush_pattern_studio.contracts.generation import (
    MainVolume,
    MeshyPrompt,
    MeshyTask,
    MeshyTaskStatus,
    PlushSpecification,
    Protrusion,
    ScopeReason,
)
from plush_pattern_studio.settings import Settings
from plush_pattern_studio.worker.main import process_once


class FakeOpenRouter:
    async def normalize_specification(
        self,
        description: str,
        height_mm: float,
        locale: str,
    ) -> PlushSpecification:
        assert description
        assert height_mm == 240
        assert locale == "en"
        return PlushSpecification(
            supported=True,
            reasonCodes=[ScopeReason.SUPPORTED],
            summary="A rounded cloud rabbit.",
            mainVolume=MainVolume(
                shape="rounded cloud",
                proportions="compact",
                pose="neutral upright",
            ),
            protrusions=[
                Protrusion(
                    kind="ear",
                    count=2,
                    placement="top",
                    shape="long and rounded",
                    mustRemainGeometry=True,
                )
            ],
            symmetry="bilateral",
            surfaceDetails=["embroidered eyes"],
            assumptions=[],
            meshyConstraints=[
                "single closed volume",
                "watertight",
                "manifold",
                "no internal geometry",
            ],
        )

    async def create_meshy_prompt(self, _: PlushSpecification) -> MeshyPrompt:
        return MeshyPrompt(
            positivePrompt=(
                "A single closed watertight manifold rounded cloud rabbit plush volume, "
                "neutral upright and bilaterally symmetric, with two long ears connected "
                "through broad sturdy bases, clean topology and no internal geometry."
            ),
            generationNotes=["Keep ear bases broad."],
        )


class FakeMeshy:
    def __init__(self) -> None:
        self.created_prompts: list[str] = []
        self.poll_count = 0
        self.glb = trimesh.creation.box(extents=[2, 4, 3]).export(file_type="glb")

    async def balance(self) -> int:
        return 100

    async def create_preview(self, prompt: str) -> str:
        self.created_prompts.append(prompt)
        return "task-1"

    async def get_task(self, task_id: str) -> MeshyTask:
        assert task_id == "task-1"
        self.poll_count += 1
        if self.poll_count == 1:
            return MeshyTask(
                id=task_id,
                status=MeshyTaskStatus.FAILED,
                progress=0,
                task_error={},
            )
        if self.poll_count == 2:
            return MeshyTask(
                id=task_id,
                status=MeshyTaskStatus.FAILED,
                progress=0,
                task_error={"message": "temporary provider failure"},
            )
        return MeshyTask(
            id=task_id,
            status=MeshyTaskStatus.SUCCEEDED,
            progress=100,
            model_urls={"glb": "https://assets.meshy.ai/test/model.glb"},
            thumbnail_url="https://assets.meshy.ai/test/preview.png",
            task_error={},
            consumed_credits=20,
        )

    async def download_bytes(self, _: str) -> bytes:
        return self.glb


def test_local_project_to_normalized_model(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'mvp.db'}",
        object_storage_path=tmp_path / "objects",
    )
    openrouter = FakeOpenRouter()
    meshy = FakeMeshy()

    with TestClient(
        create_app(
            settings,
            openrouter_client=openrouter,
            meshy_client=meshy,
        )
    ) as client:
        capability_response = client.get("/api/capabilities")
        assert capability_response.json()["meshyBalance"] == 100

        create_response = client.post(
            "/api/projects",
            json={
                "name": "Cloud Rabbit",
                "description": "A rounded cloud rabbit with two long ears",
                "heightMm": 240,
                "seamAllowanceMm": 7,
                "locale": "en",
            },
        )
        assert create_response.status_code == 201
        project = create_response.json()
        assert project["version"]["status"] == "draft"
        assert project["version"]["specification"]["supported"] is True

        endpoint = f"/api/versions/{project['version']['id']}/model-jobs"
        first_job = client.post(endpoint, json={"idempotencyKey": "same-request-123"})
        second_job = client.post(endpoint, json={"idempotencyKey": "same-request-123"})
        assert first_job.status_code == 202
        assert first_job.json()["id"] == second_job.json()["id"]

        import asyncio

        assert asyncio.run(process_once(settings, meshy)) is True
        running = client.get(f"/api/jobs/{first_job.json()['id']}").json()
        assert running["state"] == "running"
        assert asyncio.run(process_once(settings, meshy)) is True
        ambiguous = client.get(f"/api/jobs/{first_job.json()['id']}").json()
        assert ambiguous["state"] == "running"
        assert asyncio.run(process_once(settings, meshy)) is True
        failed = client.get(f"/api/jobs/{first_job.json()['id']}").json()
        assert failed["state"] == "failed"
        assert failed["providerStatus"] == "FAILED"
        assert failed["errorMessage"] == "temporary provider failure"

        resumed = client.post(f"/api/jobs/{first_job.json()['id']}/resume")
        assert resumed.status_code == 202
        assert resumed.json()["state"] == "running"
        assert asyncio.run(process_once(settings, meshy)) is True

        completed = client.get(f"/api/jobs/{first_job.json()['id']}").json()
        assert completed["state"] == "succeeded"
        assert completed["consumedCredits"] == 20

        refreshed = client.get(f"/api/projects/{project['id']}").json()
        assert refreshed["version"]["status"] == "model_review"
        asset_kinds = {asset["kind"] for asset in refreshed["version"]["assets"]}
        assert {"source_glb", "normalized_glb", "normalization_report"} <= asset_kinds

        normalized = next(
            asset
            for asset in refreshed["version"]["assets"]
            if asset["kind"] == "normalized_glb"
        )
        asset_response = client.get(normalized["url"])
        assert asset_response.status_code == 200
        assert asset_response.content[:4] == b"glTF"

    assert len(meshy.created_prompts) == 1