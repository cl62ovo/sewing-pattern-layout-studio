import hashlib
from pathlib import Path

import pytest
import trimesh

from plush_pattern_studio.contracts.pipeline import ErrorCode, StageStatus
from plush_pattern_studio.geometry.normalize import normalize_glb


def export_glb(mesh: trimesh.Trimesh, path: Path) -> Path:
    mesh.export(path, file_type="glb")
    return path


def test_normalize_closed_glb_to_requested_y_height(tmp_path: Path) -> None:
    source = export_glb(
        trimesh.creation.box(extents=[2.0, 4.0, 3.0]),
        tmp_path / "rounded-body.glb",
    )
    normalized = tmp_path / "normalized.glb"

    report = normalize_glb(source, target_height_mm=240, output_glb=normalized)

    assert report.source_sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert report.scale_factor == pytest.approx(60.0)
    assert report.diagnostics.bounds_mm.minimum[1] == pytest.approx(0.0)
    assert report.diagnostics.bounds_mm.maximum[1] == pytest.approx(240.0)
    assert report.diagnostics.is_watertight is True
    assert report.repair_method == "none"
    assert report.stages[0].status == StageStatus.COMPLETED
    assert all(
        stage.status == StageStatus.NOT_IMPLEMENTED for stage in report.stages[1:]
    )
    assert normalized.is_file()


def test_non_closed_glb_is_reconstructed_as_closed_manifold(tmp_path: Path) -> None:
    mesh = trimesh.creation.box()
    mesh.update_faces([False, *([True] * (len(mesh.faces) - 1))])
    source = export_glb(mesh, tmp_path / "open-body.glb")

    normalized = tmp_path / "repaired.glb"
    report = normalize_glb(source, target_height_mm=100, output_glb=normalized)

    assert report.input_diagnostics.boundary_edge_count > 0
    assert report.diagnostics.boundary_edge_count == 0
    assert report.diagnostics.non_manifold_edge_count == 0
    assert report.diagnostics.is_watertight is True
    assert report.repair_method == "voxel_reconstruction"
    assert report.voxel_resolution == 64
    assert report.stages[0].status == StageStatus.COMPLETED
    assert normalized.is_file()


def test_inconsistent_face_winding_uses_topology_cleanup(tmp_path: Path) -> None:
    mesh = trimesh.creation.box()
    mesh.faces[0] = mesh.faces[0][::-1]
    source = export_glb(mesh, tmp_path / "inconsistent-winding.glb")

    report = normalize_glb(source, target_height_mm=100)

    assert report.input_diagnostics.is_winding_consistent is False
    assert report.diagnostics.is_watertight is True
    assert report.diagnostics.is_winding_consistent is True
    assert report.repair_method == "topology_cleanup"
    assert report.stages[0].status == StageStatus.COMPLETED


def test_many_disconnected_components_are_not_reconstructed(tmp_path: Path) -> None:
    meshes = []
    for index in range(10):
        mesh = trimesh.creation.box()
        mesh.apply_translation([index * 2.0, 0, 0])
        meshes.append(mesh)
    source = export_glb(trimesh.util.concatenate(meshes), tmp_path / "many-parts.glb")

    report = normalize_glb(source, target_height_mm=100)

    assert report.diagnostics.connected_component_count == 10
    assert report.repair_method == "none"
    assert report.stages[0].status == StageStatus.FAILED
    assert report.stages[0].error_code == ErrorCode.MESH_REPAIR_FAILED