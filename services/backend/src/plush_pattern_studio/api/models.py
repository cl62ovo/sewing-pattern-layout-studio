from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateProjectRequest(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=3, max_length=1200)
    heightMm: float = Field(ge=50, le=2000)
    seamAllowanceMm: float = Field(default=7, ge=0, le=50)
    locale: Literal["en", "zh-CN"] = "en"


class CreateModelJobRequest(ApiModel):
    idempotencyKey: str = Field(min_length=8, max_length=100)


class CreatePatternJobRequest(ApiModel):
    idempotencyKey: str = Field(min_length=8, max_length=100)
