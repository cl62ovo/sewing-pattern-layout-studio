from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import numpy as np
import trimesh

from plush_pattern_studio.contracts.pipeline import (
    Bounds3D,
    ErrorCode,
    GeometryPipelineReport,
    MeshDiagnostics,
    PipelineStage,
    StageReport,
    StageStatus,
)

MAX_GLB_BYTES = 100 * 1024 * 1024
VOXEL_REPAIR_RESOLUTION = 192
MAX_REPAIR_BOUNDARY_EDGES = 64
MAX_REPAIR_NON_MANIFOLD_EDGES = 64
MAX_REPAIR_COMPONENTS = 8


class GeometryInputError(ValueError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


def _validate_glb(path: Path) -> int:
    if path.suffix.lower() != ".glb":
        raise GeometryInputError(
            ErrorCode.PROVIDER_ASSET_INVALID,
            "Input must use the .glb extension.",
        )
    if not path.is_file():
        raise GeometryInputError(
            ErrorCode.PROVIDER_ASSET_INVALID,
            "Input GLB does not exist or is not a file.",
        )

    byte_size = path.stat().st_size
    if byte_size < 12 or byte_size > MAX_GLB_BYTES:
        raise GeometryInputError(
            ErrorCode.PROVIDER_ASSET_INVALID,
            "Input GLB size is outside the supported range.",
        )

    with path.open("rb") as source:
        magic, version, declared_size = struct.unpack("<4sII", source.read(12))
    if magic != b"glTF" or version != 2 or declared_size != byte_size:
        raise GeometryInputError(
            ErrorCode.PROVIDER_ASSET_INVALID,
            "Input is not a valid GLB 2.0 container.",
        )
    return byte_size


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _diagnose(mesh: trimesh.Trimesh) -> MeshDiagnostics:
    edge_counts = np.bincount(mesh.edges_unique_inverse)
    bounds = mesh.bounds
    area_epsilon = max(float(mesh.area), 1.0) * 1e-12

    return MeshDiagnostics(
        vertex_count=len(mesh.vertices),
        face_count=len(mesh.faces),
        connected_component_count=len(mesh.split(only_watertight=False)),
        boundary_edge_count=int(np.count_nonzero(edge_counts == 1)),
        non_manifold_edge_count=int(np.count_nonzero(edge_counts > 2)),
        degenerate_face_count=int(np.count_nonzero(mesh.area_faces <= area_epsilon)),
        is_watertight=bool(mesh.is_watertight),
        is_winding_consistent=bool(mesh.is_winding_consistent),
        bounds_mm=Bounds3D(
            minimum=tuple(float(value) for value in bounds[0]),
            maximum=tuple(float(value) for value in bounds[1]),
        ),
    )


def _load_mesh(path: Path) -> trimesh.Trimesh:
    try:
        scene = trimesh.load_scene(path, file_type="glb")
        mesh = scene.to_mesh()
    except Exception as error:
        raise GeometryInputError(
            ErrorCode.PROVIDER_ASSET_INVALID,
            "GLB geometry could not be decoded.",
        ) from error

    if mesh.is_empty or len(mesh.faces) == 0:
        raise GeometryInputError(
            ErrorCode.PROVIDER_ASSET_INVALID,
            "GLB contains no triangular mesh geometry.",
        )
    mesh.remove_unreferenced_vertices()
    return mesh


def _place_and_scale(mesh: trimesh.Trimesh, target_height_mm: float) -> None:
    bounds = mesh.bounds.copy()
    height = float(mesh.extents[1])
    if height <= 1e-12:
        raise GeometryInputError(
            ErrorCode.PROVIDER_ASSET_INVALID,
            "Mesh has zero extent on the Y height axis.",
        )
    mesh.apply_translation(
        [
            -float((bounds[0, 0] + bounds[1, 0]) / 2),
            -float(bounds[0, 1]),
            -float((bounds[0, 2] + bounds[1, 2]) / 2),
        ]
    )
    mesh.apply_scale(target_height_mm / height)


def _is_usable(diagnostics: MeshDiagnostics) -> bool:
    return (
        diagnostics.connected_component_count == 1
        and diagnostics.boundary_edge_count == 0
        and diagnostics.non_manifold_edge_count == 0
        and diagnostics.degenerate_face_count == 0
        and diagnostics.is_watertight
        and diagnostics.is_winding_consistent
    )


def _can_voxel_repair(mesh: trimesh.Trimesh, diagnostics: MeshDiagnostics) -> bool:
    components = mesh.split(only_watertight=False)
    largest_component_share = max(len(component.faces) for component in components) / len(
        mesh.faces
    )
    return (
        (
            diagnostics.connected_component_count <= MAX_REPAIR_COMPONENTS
            or largest_component_share >= 0.98
        )
        and diagnostics.boundary_edge_count <= MAX_REPAIR_BOUNDARY_EDGES
        and diagnostics.non_manifold_edge_count <= MAX_REPAIR_NON_MANIFOLD_EDGES
    )


def _voxel_repair(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    pitch = float(max(mesh.extents)) / VOXEL_REPAIR_RESOLUTION
    try:
        voxels = mesh.voxelized(pitch).fill()
        repaired = voxels.marching_cubes
        repaired.apply_transform(voxels.transform)
        repaired.process(validate=True)
        return repaired
    except Exception as error:
        raise GeometryInputError(
            ErrorCode.MESH_REPAIR_FAILED,
            "Mesh could not be reconstructed as a closed manifold.",
        ) from error


def normalize_glb(
    input_path: Path,
    target_height_mm: float,
    output_glb: Path | None = None,
) -> GeometryPipelineReport:
    if not np.isfinite(target_height_mm) or target_height_mm <= 0:
        raise GeometryInputError(
            ErrorCode.PROVIDER_ASSET_INVALID,
            "Target height must be a finite positive number of millimeters.",
        )

    path = input_path.resolve()
    byte_size = _validate_glb(path)
    source_sha256 = _sha256(path)
    mesh = _load_mesh(path)

    source_height = float(mesh.extents[1])
    _place_and_scale(mesh, target_height_mm)
    scale_factor = target_height_mm / source_height
    input_diagnostics = _diagnose(mesh)

    mesh.process(validate=True)
    diagnostics = _diagnose(mesh)
    repair_method = "none"
    voxel_resolution = None
    if not _is_usable(diagnostics) and _can_voxel_repair(mesh, diagnostics):
        mesh = _voxel_repair(mesh)
        _place_and_scale(mesh, target_height_mm)
        diagnostics = _diagnose(mesh)
        repair_method = "voxel_reconstruction"
        voxel_resolution = VOXEL_REPAIR_RESOLUTION
    elif _is_usable(diagnostics) and not _is_usable(input_diagnostics):
        repair_method = "topology_cleanup"

    if diagnostics.non_manifold_edge_count > 0:
        status = StageStatus.FAILED
        error_code = ErrorCode.MESH_NON_MANIFOLD
    elif not diagnostics.is_watertight:
        status = StageStatus.FAILED
        error_code = ErrorCode.MESH_NOT_CLOSED
    elif (
        diagnostics.connected_component_count != 1
        or not diagnostics.is_winding_consistent
        or diagnostics.degenerate_face_count > 0
    ):
        status = StageStatus.FAILED
        error_code = ErrorCode.MESH_REPAIR_FAILED
    else:
        status = StageStatus.COMPLETED
        error_code = None
        if output_glb is not None:
            output_glb.parent.mkdir(parents=True, exist_ok=True)
            mesh.export(output_glb, file_type="glb")

    stages = [
        StageReport(stage=PipelineStage.NORMALIZE, status=status, error_code=error_code)
    ]
    stages.extend(
        StageReport(
            stage=stage,
            status=StageStatus.NOT_IMPLEMENTED,
            error_code=ErrorCode.NOT_IMPLEMENTED,
        )
        for stage in (
            PipelineStage.SEGMENT,
            PipelineStage.FLATTEN,
            PipelineStage.SCORE,
            PipelineStage.PDF,
        )
    )

    return GeometryPipelineReport(
        source_file_name=path.name,
        source_sha256=source_sha256,
        source_byte_size=byte_size,
        target_height_mm=target_height_mm,
        scale_factor=scale_factor,
        input_diagnostics=input_diagnostics,
        diagnostics=diagnostics,
        repair_method=repair_method,
        voxel_resolution=voxel_resolution,
        stages=stages,
    )
