import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh


def rounded_body() -> trimesh.Trimesh:
    mesh = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
    mesh.vertices *= np.array([0.82, 1.0, 0.68])
    return mesh


def long_ears() -> trimesh.Trimesh:
    mesh = trimesh.creation.icosphere(subdivisions=4, radius=1.0)
    vertices = mesh.vertices
    top_weight = np.clip((vertices[:, 1] - 0.05) / 0.95, 0.0, 1.0) ** 2
    ear_centers = np.exp(-((np.abs(vertices[:, 0]) - 0.48) ** 2) / 0.035)
    vertices[:, 1] += 1.25 * top_weight * ear_centers
    vertices[:, 0] *= 0.88
    vertices[:, 2] *= 0.7
    return mesh


def simple_tail() -> trimesh.Trimesh:
    mesh = trimesh.creation.icosphere(subdivisions=4, radius=1.0)
    vertices = mesh.vertices
    back_weight = np.clip((-vertices[:, 2] - 0.18) / 0.82, 0.0, 1.0) ** 2
    mid_height = np.exp(-((vertices[:, 1] + 0.05) ** 2) / 0.22)
    vertices[:, 2] -= 0.95 * back_weight * mid_height
    vertices *= np.array([0.78, 1.0, 0.72])
    return mesh


def main() -> None:
    backend_root = Path(__file__).resolve().parent.parent
    output_dir = backend_root / "tests" / "fixtures" / "glb"
    output_dir.mkdir(parents=True, exist_ok=True)
    fixtures = {
        "rounded-body.glb": rounded_body(),
        "long-ears.glb": long_ears(),
        "simple-tail.glb": simple_tail(),
    }
    manifest: dict[str, dict[str, int | str]] = {}
    for name, mesh in fixtures.items():
        path = output_dir / name
        mesh.export(path, file_type="glb")
        manifest[name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "vertexCount": len(mesh.vertices),
            "faceCount": len(mesh.faces),
        }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
