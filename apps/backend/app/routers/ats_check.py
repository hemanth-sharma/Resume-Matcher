"""Standalone ATS check endpoints.

A deliberately isolated feature: upload a resume PDF, get its ATS score.
Nothing here touches the resumes/jobs/improvements pipeline or the
application tracker — records live in the dedicated ``ats_checks`` table and
archived (renamed) copies go to the configured archive folder.
"""

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import settings
from app.database import db
from app.schemas.ats_check import (
    AtsCheckDeleteResponse,
    AtsCheckListResponse,
    AtsCheckResponse,
)
from app.services.ats_standalone import compute_standalone_ats_score
from app.services.parser import parse_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ats-check", tags=["ATS Check"])

# Standalone checks accept PDF resumes only — the feature is scoped to the
# single most common ATS submission format (keeps validation unambiguous).
ALLOWED_TYPES = {"application/pdf"}
MAX_FILE_SIZE = 4 * 1024 * 1024  # 4MB (same cap as the resume pipeline)

VALID_SOURCES = {"manual", "folder_watch"}


def _sanitize_filename(filename: str | None) -> str:
    """Strip path components from an uploaded filename."""
    if not filename:
        return "resume.pdf"
    name = Path(filename).name.strip()
    return name or "resume.pdf"


def _archive_pdf(check_id: int, content: bytes) -> Path | None:
    """Save a renamed copy ``{user}_Resume_{id}.pdf`` in the archive folder.

    Archiving is best-effort: a failure logs a warning and leaves
    ``stored_path`` unset instead of failing the whole check.
    """
    try:
        archive_dir = settings.ats_archive_path
        archive_dir.mkdir(parents=True, exist_ok=True)
        safe_user = settings.ats_user_name or "User"
        target = archive_dir / f"{safe_user}_Resume_{check_id}.pdf"
        with open(target, "wb") as fh:
            fh.write(content)
        return target
    except OSError as e:
        logger.warning("Could not archive ATS check %s: %s", check_id, e)
        return None


@router.post("/upload", response_model=AtsCheckResponse)
async def upload_ats_check(
    file: UploadFile = File(...),
    source: str = Form("manual"),
) -> AtsCheckResponse:
    """Upload a resume PDF and score it (standalone, no job description).

    The score is computed by the deterministic standalone engine (no LLM), so
    the response is immediate. A renamed copy of the uploaded PDF is archived
    as ``{ATS_USER_NAME}_Resume_{id}.pdf``.
    """
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail=f"Invalid source: {source}")

    filename = _sanitize_filename(file.filename)
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {content_type or 'unknown'}. Only PDF files are supported.",
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )
    # Real PDFs start with the %PDF magic bytes; catches mislabeled uploads.
    if not content.startswith(b"%PDF"):
        raise HTTPException(
            status_code=422,
            detail="This file is not a valid PDF document.",
        )

    # Extract text (markdown) from the PDF. Scanned/image-only PDFs yield an
    # empty extraction and are rejected with a clear message.
    try:
        markdown_content = await parse_document(content, filename)
    except Exception as e:
        logger.error("ATS check document parsing failed: %s", e)
        raise HTTPException(
            status_code=422,
            detail="Failed to parse the PDF. Please ensure it is a valid, text-based PDF file.",
        ) from e

    if not markdown_content or not markdown_content.strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not extract text from the PDF. It may be image-based or scanned — "
                "upload a text-based PDF (or run OCR first)."
            ),
        )

    # Create the record first so the autoincrement id drives the archive name.
    record = await db.create_ats_check(
        file_name=filename,
        source=source,
        content_markdown=markdown_content,
        status="processing",
    )
    check_id = int(record["id"])

    # Score (deterministic, local, near-instant — no LLM configured needed).
    try:
        score_payload = compute_standalone_ats_score(markdown_content)
    except Exception as e:  # engine already guards; extra safety net
        logger.error("Standalone ATS scoring failed for check %s: %s", check_id, e)
        score_payload = None

    if score_payload is None:
        updated = await db.update_ats_check(
            check_id,
            {"status": "failed", "error": "Scoring failed — please re-upload."},
        )
        assert updated is not None
        return AtsCheckResponse(**updated)

    stored_path = _archive_pdf(check_id, content)

    updated = await db.update_ats_check(
        check_id,
        {
            "status": "ready",
            "overall_score": float(score_payload["overall_score"]),
            "sub_scores": score_payload["sub_scores"],
            "score_data": score_payload,
            "stored_path": str(stored_path) if stored_path else None,
        },
    )
    assert updated is not None
    logger.info(
        "ATS check %s scored %s (%s) from %s",
        check_id,
        updated["overall_score"],
        score_payload["interpretation"],
        source,
    )
    return AtsCheckResponse(**updated)


@router.get("/checks", response_model=AtsCheckListResponse)
async def list_ats_checks() -> AtsCheckListResponse:
    """List all standalone ATS checks, newest first."""
    checks = await db.list_ats_checks()
    return AtsCheckListResponse(checks=[AtsCheckResponse(**c) for c in checks])


@router.get("/checks/{check_id}", response_model=AtsCheckResponse)
async def get_ats_check(check_id: int) -> AtsCheckResponse:
    """Get one ATS check with its full score payload."""
    record = await db.get_ats_check(check_id)
    if record is None:
        raise HTTPException(status_code=404, detail="ATS check not found")
    return AtsCheckResponse(**record)


@router.delete("/checks/{check_id}", response_model=AtsCheckDeleteResponse)
async def delete_ats_check(check_id: int) -> AtsCheckDeleteResponse:
    """Delete an ATS check record and its archived PDF copy."""
    record = await db.delete_ats_check(check_id)
    if record is None:
        raise HTTPException(status_code=404, detail="ATS check not found")

    stored_path = record.get("stored_path")
    if stored_path:
        try:
            Path(stored_path).unlink(missing_ok=True)
        except OSError as e:
            logger.warning(
                "Could not remove archived file for check %s: %s", check_id, e
            )
    return AtsCheckDeleteResponse(
        message=f"ATS check {check_id} deleted", deleted_id=check_id
    )
