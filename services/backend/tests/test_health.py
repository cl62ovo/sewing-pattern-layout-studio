from fastapi.testclient import TestClient

from plush_pattern_studio.api.main import app


def test_live_health_check() -> None:
    response = TestClient(app).get("/api/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "api",
        "version": "0.1.0",
    }