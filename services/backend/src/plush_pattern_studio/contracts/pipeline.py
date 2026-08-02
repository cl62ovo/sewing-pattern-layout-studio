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
    algorithm_version: Literal["normalize-v2"] = "normalize-v2"
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
