import hashlib
import json
from pathlib import Path

from plush_pattern_studio.contracts.pipeline import StageStatus
from plush_pattern_studio.geometry.normalize import normalize_glb

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "glb"


def test_fixed_glb_fixtures_are_closed_and_match_manifest() -> None:
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert set(manifest) == {"rounded-body.glb", "long-ears.glb", "simple-tail.glb"}
    for file_name, expected in manifest.items():
        path = FIXTURE_DIR / file_name
        report = normalize_glb(path, target_height_mm=240)

        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected["sha256"]
        assert report.source_sha256 == expected["sha256"]
        assert report.diagnostics.vertex_count == expected["vertexCount"]
        assert report.diagnostics.face_count == expected["faceCount"]
        assert report.diagnostics.connected_component_count == 1
        assert report.diagnostics.is_watertight is True
        assert report.stages[0].status == StageStatus.COMPLETED
