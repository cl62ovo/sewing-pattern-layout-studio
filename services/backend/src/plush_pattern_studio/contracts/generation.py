from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GenerationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScopeReason(StrEnum):
    SUPPORTED = "SUPPORTED"
    HAS_COMPLEX_HOLES = "HAS_COMPLEX_HOLES"
    HAS_ARTICULATED_JOINTS = "HAS_ARTICULATED_JOINTS"
    HAS_MANY_DISCONNECTED_PARTS = "HAS_MANY_DISCONNECTED_PARTS"
    HAS_CLOTHING_LAYERS = "HAS_CLOTHING_LAYERS"
    HARD_SURFACE_OBJECT = "HARD_SURFACE_OBJECT"
    REFERENCE_CONFLICT = "REFERENCE_CONFLICT"
    AMBIGUOUS_CORE_SHAPE = "AMBIGUOUS_CORE_SHAPE"
    OTHER_UNSUPPORTED = "OTHER_UNSUPPORTED"


class MainVolume(GenerationModel):
    shape: str = Field(max_length=300)
    proportions: str = Field(max_length=300)
    pose: str = Field(max_length=200)


class Protrusion(GenerationModel):
    kind: str = Field(max_length=60)
    count: int = Field(ge=1, le=4)
    placement: str = Field(max_length=160)
    shape: str = Field(max_length=200)
    mustRemainGeometry: bool


class PlushSpecification(GenerationModel):
    supported: bool
    reasonCodes: list[ScopeReason] = Field(max_length=8)
    summary: str = Field(max_length=500)
    mainVolume: MainVolume
    protrusions: list[Protrusion] = Field(max_length=6)
    symmetry: str = Field(pattern="^(bilateral|mostly_bilateral|asymmetric)$")
    surfaceDetails: list[str] = Field(max_length=12)
    assumptions: list[str] = Field(max_length=10)
    meshyConstraints: list[str] = Field(min_length=4, max_length=12)


class MeshyPrompt(GenerationModel):
    positivePrompt: str = Field(min_length=80, max_length=600)
    generationNotes: list[str] = Field(max_length=8)


class MeshyTaskStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class MeshyTask(GenerationModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    status: MeshyTaskStatus
    progress: int = Field(ge=0, le=100)
    model_urls: dict[str, str] = Field(default_factory=dict)
    thumbnail_url: str | None = None
    task_error: dict[str, object] = Field(default_factory=dict)
    consumed_credits: int | None = None

    @field_validator("task_error", mode="before")
    @classmethod
    def normalize_nullable_task_error(cls, value: object) -> object:
        return {} if value is None else value
