import json

import httpx
import pytest

from plush_pattern_studio.contracts.generation import MeshyTaskStatus
from plush_pattern_studio.providers.meshy import MeshyClient
from plush_pattern_studio.providers.openrouter import OpenRouterClient


SPECIFICATION = {
    "supported": True,
    "reasonCodes": ["SUPPORTED"],
    "summary": "A rounded cloud rabbit.",
    "mainVolume": {"shape": "rounded cloud", "proportions": "compact", "pose": "upright"},
    "protrusions": [{
        "kind": "ear",
        "count": 2,
        "placement": "top",
        "shape": "long and rounded",
        "mustRemainGeometry": True,
    }],
    "symmetry": "bilateral",
    "surfaceDetails": ["embroidered eyes"],
    "assumptions": [],
    "meshyConstraints": ["closed", "watertight", "manifold", "no internal geometry"],
}


async def test_openrouter_requests_strict_structured_output() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.headers["authorization"] == "Bearer test-key"
        assert body["provider"] == {"require_parameters": True}
        assert body["response_format"]["type"] == "json_schema"
        assert body["response_format"]["json_schema"]["strict"] is True
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(SPECIFICATION)}}]},
        )

    client = OpenRouterClient(
        "test-key",
        "test/model",
        base_url="https://openrouter.test",
        transport=httpx.MockTransport(handler),
    )

    result = await client.normalize_specification("cloud rabbit", 240, "en")

    assert result.supported is True
    assert result.protrusions[0].count == 2


async def test_meshy_uses_current_preview_contract() -> None:
    requests: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={"result": "task-1"})
        return httpx.Response(
            200,
            json={
                "id": "task-1",
                "type": "text-to-3d-preview",
                "status": "SUCCEEDED",
                "progress": 100,
                "prompt": "A closed watertight rounded plush volume",
                "created_at": 1785641537242,
                "finished_at": 1785641609520,
                "model_urls": {"glb": "https://assets.test/model.glb"},
                "thumbnail_url": "https://assets.test/preview.png",
                "task_error": None,
                "consumed_credits": 20,
            },
        )

    client = MeshyClient(
        "test-key",
        base_url="https://meshy.test/openapi",
        transport=httpx.MockTransport(handler),
    )

    task_id = await client.create_preview("A closed watertight rounded plush volume")
    task = await client.get_task(task_id)

    assert requests == [{
        "mode": "preview",
        "prompt": "A closed watertight rounded plush volume",
        "ai_model": "latest",
        "model_type": "standard",
        "should_remesh": True,
        "topology": "triangle",
        "target_polycount": 20000,
        "target_formats": ["glb"],
        "moderation": True,
    }]
    assert task.status == MeshyTaskStatus.SUCCEEDED
    assert task.task_error == {}
    assert task.model_urls["glb"].endswith("model.glb")


async def test_meshy_maps_payment_error_without_leaking_body() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"message": "account detail"})

    client = MeshyClient(
        "test-key",
        base_url="https://meshy.test/openapi",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(Exception, match="Meshy request failed") as error:
        await client.create_preview("A closed plush")

    assert "account detail" not in str(error.value)