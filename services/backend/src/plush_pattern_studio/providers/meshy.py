from urllib.parse import urlparse

import httpx

from plush_pattern_studio.contracts.generation import MeshyTask
from plush_pattern_studio.providers.errors import ProviderError


class MeshyClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.meshy.ai/openapi",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.transport = transport

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def create_preview(self, prompt: str) -> str:
        request = {
            "mode": "preview",
            "prompt": prompt,
            "ai_model": "latest",
            "model_type": "standard",
            "should_remesh": True,
            "topology": "triangle",
            "target_polycount": 20000,
            "target_formats": ["glb"],
            "moderation": True,
        }
        payload = await self._request("POST", "/v2/text-to-3d", json=request)
        task_id = payload.get("result")
        if not isinstance(task_id, str) or not task_id:
            raise ProviderError(
                "PROVIDER_GENERATION_FAILED",
                "Meshy did not return a task identifier.",
            )
        return task_id

    async def get_task(self, task_id: str) -> MeshyTask:
        payload = await self._request("GET", f"/v2/text-to-3d/{task_id}")
        try:
            return MeshyTask.model_validate(payload)
        except ValueError as error:
            raise ProviderError(
                "PROVIDER_GENERATION_FAILED",
                "Meshy returned an invalid task response.",
            ) from error

    async def delete_task(self, task_id: str) -> None:
        await self._request("DELETE", f"/v2/text-to-3d/{task_id}")

    async def balance(self) -> int:
        payload = await self._request("GET", "/v1/balance")
        balance = payload.get("balance")
        if not isinstance(balance, int):
            raise ProviderError("PROVIDER_GENERATION_FAILED", "Invalid balance response.")
        return balance

    async def download_bytes(self, url: str, max_bytes: int = 100 * 1024 * 1024) -> bytes:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if parsed.scheme != "https" or not (
            hostname == "assets.meshy.ai" or hostname.endswith(".meshy.ai")
        ):
            raise ProviderError("PROVIDER_ASSET_INVALID", "Meshy asset URL is not trusted.")
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=60.0,
                follow_redirects=False,
            ) as client:
                async with client.stream("GET", url, headers=self.headers) as response:
                    response.raise_for_status()
                    chunks: list[bytes] = []
                    byte_size = 0
                    async for chunk in response.aiter_bytes():
                        byte_size += len(chunk)
                        if byte_size > max_bytes:
                            raise ProviderError(
                                "PROVIDER_ASSET_INVALID",
                                "Meshy asset exceeds the size limit.",
                            )
                        chunks.append(chunk)
            return b"".join(chunks)
        except httpx.HTTPError as error:
            raise ProviderError("PROVIDER_ASSET_INVALID", "Meshy asset download failed.") from error

    async def _request(self, method: str, path: str, **kwargs: object) -> dict[str, object]:
        headers = {**self.headers, "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=30.0,
            ) as client:
                response = await client.request(
                    method,
                    f"{self.base_url}{path}",
                    headers=headers,
                    **kwargs,
                )
                response.raise_for_status()
                if not response.content:
                    return {}
                payload = response.json()
                if not isinstance(payload, dict):
                    raise TypeError("Provider response is not an object.")
                return payload
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            if status == 429:
                code = "PROVIDER_RATE_LIMITED"
            elif status in {400, 402}:
                code = "PROVIDER_GENERATION_FAILED"
            else:
                code = "PROVIDER_ASSET_INVALID"
            raise ProviderError(code, "Meshy request failed.", status) from error
        except (httpx.HTTPError, TypeError, ValueError) as error:
            raise ProviderError("PROVIDER_GENERATION_FAILED", "Meshy request failed.") from error
