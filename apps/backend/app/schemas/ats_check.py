"""Pydantic schemas for the standalone ATS check API."""

from typing import Any

from pydantic import BaseModel, Field


class AtsCheckResponse(BaseModel):
    """One standalone ATS check record."""

    id: int
    file_name: str
    stored_path: str | None = None
    status: str = "processing"
    overall_score: float | None = None
    sub_scores: dict[str, float] | None = None
    score_data: dict[str, Any] | None = None
    source: str = "manual"
    error: str | None = None
    created_at: str
    updated_at: str


class AtsCheckListResponse(BaseModel):
    """Response for GET /ats-check/checks (newest first)."""

    checks: list[AtsCheckResponse] = Field(default_factory=list)


class AtsCheckDeleteResponse(BaseModel):
    """Response for DELETE /ats-check/checks/{check_id}."""

    message: str
    deleted_id: int
