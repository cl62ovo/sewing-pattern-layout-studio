from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
    )


class PipelineStage(StrEnum):
    NORMALIZE = "normalize"
    SEGMENT = "segment"
    FLATTEN = "flatten"
    SCORE = "score"
    PDF = "pdf"


class StageStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    NOT_IMPLEMENTED = "not_implemented"


class ErrorCode(StrEnum):
    PROVIDER_ASSET_INVALID = "PROVIDER_ASSET_INVALID"
    MESH_NOT_CLOSED = "MESH_NOT_CLOSED"
    MESH_NON_MANIFOLD = "MESH_NON_MANIFOLD"
    MESH_REPAIR_FAILED = "MESH_REPAIR_FAILED"
    SEGMENTATION_NO_VALID_CUT = "SEGMENTATION_NO_VALID_CUT"
    FLATTENING_FLIPPED_TRIANGLES = "FLATTENING_FLIPPED_TRIANGLES"
    FLATTENING_DISTORTION_TOO_HIGH = "FLATTENING_DISTORTION_TOO_HIGH"
    SEAM_LENGTH_MISMATCH = "SEAM_LENGTH_MISMATCH"
    SEAM_ALLOWANCE_OFFSET_FAILED = "SEAM_ALLOWANCE_OFFSET_FAILED"
    PDF_VALIDATION_FAILED = "PDF_VALIDATION_FAILED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


class Bounds3D(ContractModel):
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]


class MeshDiagnostics(ContractModel):
    vertex_count: int = Field(ge=0)
    face_count: int = Field(ge=0)
    connected_component_count: int = Field(ge=0)
    boundary_edge_count: int = Field(ge=0)
    non_manifold_edge_count: int = Field(ge=0)
    degenerate_face_count: int = Field(ge=0)
    is_watertight: bool
    is_winding_consistent: bool
    bounds_mm: Bounds3D


class StageReport(ContractModel):
    stage: PipelineStage
    status: StageStatus
    error_code: ErrorCode | None = None


class GeometryPipelineReport(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["normalize-v3"] = "normalize-v3"
    units: Literal["mm"] = "mm"
    source_file_name: str
    source_sha256: str
    source_byte_size: int = Field(ge=0)
    target_height_mm: float = Field(gt=0)
    scale_factor: float = Field(gt=0)
    input_diagnostics: MeshDiagnostics
    diagnostics: MeshDiagnostics
    repair_method: Literal["none", "topology_cleanup", "voxel_reconstruction"]
    voxel_resolution: int | None = Field(default=None, ge=32)
    stages: list[StageReport]


class SeamEdge(ContractModel):
    id: str
    pair_id: str
    source_vertices: tuple[int, int]
    length_3d_mm: float = Field(ge=0)
    length_2d_mm: float = Field(ge=0)


class PatternPiece(ContractModel):
    id: str
    name: str
    quantity: int = Field(default=1, ge=1)
    mirror_of: str | None = None
    grain_direction: tuple[float, float] = (0.0, 1.0)
    source_vertex_ids: list[int]
    faces: list[tuple[int, int, int]]
    vertices_2d_mm: list[tuple[float, float]]
    seam_path_mm: list[tuple[float, float]]
    cut_path_mm: list[tuple[float, float]]
    seam_edges: list[SeamEdge]


class PatternQuality(ContractModel):
    piece_count: int = Field(ge=0)
    mean_distortion: float = Field(ge=0)
    max_distortion: float = Field(ge=0)
    max_seam_mismatch: float = Field(ge=0)
    flipped_triangle_count: int = Field(ge=0)
    boundary_self_intersection_count: int = Field(ge=0)
    unpaired_seam_count: int = Field(ge=0)
    passed: bool
    failure_reasons: list[ErrorCode]


class PatternPipelineReport(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["pattern-v3"] = "pattern-v3"
    units: Literal["mm"] = "mm"
    source_sha256: str
    target_height_mm: float = Field(gt=0)
    seam_allowance_mm: float = Field(ge=0)
    pieces: list[PatternPiece]
    quality: PatternQuality
    stages: list[StageReport]
    svg_file_name: str | None = None
    pdf_file_name: str | None = None
