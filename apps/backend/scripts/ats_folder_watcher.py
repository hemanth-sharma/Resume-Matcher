#!/usr/bin/env python3
"""ATS folder watcher — auto-upload resume PDFs for standalone ATS checks.

Monitors a folder and, whenever a PDF whose filename contains a keyword
(default: "resume") lands there, uploads it to the Resume Matcher standalone
ATS check endpoint. The score is computed by the backend, stored in the
``ats_checks`` table, and immediately visible on the frontend ATS Check page
(``/ats-check``). After a successful upload the original file is moved to a
``processed`` subfolder; files rejected by the backend (e.g. scanned/image
PDFs) move to a ``failed`` subfolder so they are never re-uploaded in a loop.

The backend archives every checked PDF as ``{ATS_USER_NAME}_Resume_{id}.pdf``
in the configured archive folder — the watcher itself only handles uploads.

Configuration (all via environment variables or the backend ``.env`` file):

========================  ==============================================  =========================
Variable                  Meaning                                         Default
========================  ==============================================  =========================
ATS_WATCH_FOLDER          Folder to monitor (required)                    —
ATS_FILE_KEYWORD          Filename keyword filter (case-insensitive)      resume
ATS_BACKEND_URL           Resume Matcher backend base URL                 http://127.0.0.1:8000
ATS_POLL_INTERVAL         Seconds between folder scans                    10
ATS_PROCESSED_SUBDIR      Subfolder for successfully uploaded files       processed
ATS_FAILED_SUBDIR         Subfolder for rejected files                    failed
ATS_WATCHER_LOG_LEVEL     Python log level                                INFO
========================  ==============================================  =========================

Usage (from ``apps/backend``)::

    uv run python scripts/ats_folder_watcher.py

    # or plain python if dependencies are installed system-wide:
    python scripts/ats_folder_watcher.py

Stop with Ctrl+C.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    print(
        "The 'requests' package is required. Install it with:\n"
        "  uv add requests   (or)   pip install requests",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover

    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:  # type: ignore[misc]
        return False


logger = logging.getLogger("ats_folder_watcher")

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent

UPLOAD_ENDPOINT = "/api/v1/ats-check/upload"


def load_configuration() -> dict[str, Any]:
    """Resolve configuration from env vars, the backend .env, and defaults."""
    # .env resolution order: backend dir first (this script ships with the
    # backend), then the current working directory.
    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv()  # cwd .env — does not override already-set variables

    watch_folder = os.environ.get("ATS_WATCH_FOLDER", "").strip()
    return {
        "watch_folder": Path(watch_folder).expanduser() if watch_folder else None,
        "keyword": os.environ.get("ATS_FILE_KEYWORD", "resume").strip().lower(),
        "backend_url": os.environ.get("ATS_BACKEND_URL", "http://127.0.0.1:8000")
        .strip()
        .rstrip("/"),
        "poll_interval": max(2.0, float(os.environ.get("ATS_POLL_INTERVAL", "10") or 10)),
        "processed_subdir": os.environ.get("ATS_PROCESSED_SUBDIR", "processed").strip()
        or "processed",
        "failed_subdir": os.environ.get("ATS_FAILED_SUBDIR", "failed").strip()
        or "failed",
    }


def configure_logging() -> None:
    level_name = os.environ.get("ATS_WATCHER_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )


def is_candidate_pdf(path: Path, keyword: str) -> bool:
    """True when ``path`` is a PDF whose filename contains the keyword."""
    if not path.is_file():
        return False
    if path.suffix.lower() != ".pdf":
        return False
    if not keyword:  # empty keyword matches every PDF
        return True
    return keyword in path.name.lower()


def upload_pdf(backend_url: str, path: Path, source: str = "folder_watch") -> dict[str, Any] | None:
    """POST the PDF to the backend; returns the JSON record or None.

    A dict with the ``__rejected__`` marker means the backend definitively
    rejected the file (bad PDF, too large, image-only…) — the caller should
    park it instead of retrying.
    """
    url = f"{backend_url}{UPLOAD_ENDPOINT}"
    try:
        with open(path, "rb") as fh:
            response = requests.post(
                url,
                files={"file": (path.name, fh, "application/pdf")},
                data={"source": source},
                timeout=60,
            )
    except requests.RequestException as exc:
        logger.warning("Upload request failed for %s: %s", path.name, exc)
        return None

    if response.status_code != 200:
        try:
            detail = response.json().get("detail", "")
        except ValueError:
            detail = response.text[:200]
        logger.warning(
            "Backend rejected %s (HTTP %s): %s", path.name, response.status_code, detail
        )
        return {"__rejected__": True, "status_code": response.status_code}

    try:
        return response.json()
    except ValueError:
        logger.warning("Backend returned non-JSON response for %s", path.name)
        return {"__rejected__": True, "status_code": response.status_code}


def print_score_summary(record: dict[str, Any]) -> None:
    """Pretty-print the score the backend returned for one upload."""
    overall = record.get("overall_score")
    if overall is None:
        logger.info("Check #%s created but not scored yet.", record.get("id"))
        return
    line = "-" * 62
    print(f"\n{line}")
    print(f"  ATS SCORE: {overall} / 100   ({record.get('file_name', '?')})")
    sub_scores = record.get("sub_scores") or {}
    if sub_scores:
        labels = {
            "contact_info": "Contact info          ",
            "section_completeness": "Sections              ",
            "formatting_quality": "Formatting            ",
            "impact_quality": "Impact                ",
            "keyword_optimization": "Keyword optimization  ",
            "readability_structure": "Readability           ",
        }
        for key, label in labels.items():
            value = sub_scores.get(key)
            if value is not None:
                print(f"    {label} {float(value):6.1f}")
    recommendations = (record.get("score_data") or {}).get("recommendations") or []
    if recommendations:
        print(f"  Top tip: {recommendations[0]}")
    print(f"  View the full report on the frontend: /ats-check/{record.get('id')}")
    print(f"{line}\n")


def move_file(path: Path, target_dir: Path) -> None:
    """Move ``path`` into ``target_dir`` (created on demand), never clobbering."""
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / path.name
        counter = 1
        while target.exists():
            target = target_dir / f"{path.stem}_{counter}{path.suffix}"
            counter += 1
        shutil.move(str(path), str(target))
        logger.info("Moved %s -> %s", path.name, target)
    except OSError as exc:
        logger.error("Could not move %s: %s", path.name, exc)


def poll_once(config: dict[str, Any], sizes: dict[Path, int]) -> None:
    """One folder scan: upload stable candidate PDFs, then relocate them."""
    watch_folder: Path = config["watch_folder"]
    keyword: str = config["keyword"]

    candidates = [p for p in watch_folder.iterdir() if is_candidate_pdf(p, keyword)]

    for path in candidates:
        try:
            current_size = path.stat().st_size
        except OSError:
            continue
        previous_size = sizes.get(path)
        sizes[path] = current_size
        if previous_size != current_size:
            # File changed since the last scan — probably still being written.
            logger.debug("Waiting for %s to stabilize (size changed).", path.name)
            continue
        if current_size == 0:
            continue

        logger.info("Found resume PDF: %s (%.1f KB)", path.name, current_size / 1024)
        result = upload_pdf(config["backend_url"], path)
        if result is None:
            # Network/backend error — leave the file for the next poll.
            continue
        if result.get("__rejected__"):
            # Definitive backend rejection — park it so it is not retried forever.
            move_file(path, watch_folder / config["failed_subdir"])
            continue
        print_score_summary(result)
        move_file(path, watch_folder / config["processed_subdir"])
        sizes.pop(path, None)


def main() -> int:
    configure_logging()
    config = load_configuration()

    watch_folder: Path | None = config["watch_folder"]
    if watch_folder is None:
        print(
            "ERROR: ATS_WATCH_FOLDER is not set.\n"
            "Set it in apps/backend/.env (or your environment), e.g.:\n"
            "  ATS_WATCH_FOLDER=/Users/you/Downloads/resumes_to_check",
            file=sys.stderr,
        )
        return 2

    if not watch_folder.exists():
        print(f"ERROR: Watch folder does not exist: {watch_folder}", file=sys.stderr)
        return 2

    logger.info("ATS folder watcher started")
    logger.info("  Watching   : %s", watch_folder)
    logger.info("  Keyword    : '%s' (in filename, case-insensitive)", config["keyword"])
    logger.info("  Backend    : %s", config["backend_url"])
    logger.info("  Poll every : %ss", config["poll_interval"])
    logger.info("Stop with Ctrl+C.")

    # Verify the backend is reachable once up-front so misconfiguration is
    # obvious immediately (the watcher still keeps retrying afterwards).
    try:
        requests.get(f"{config['backend_url']}/health", timeout=5)
    except requests.RequestException:
        logger.warning(
            "Backend not reachable right now at %s — will keep retrying.",
            config["backend_url"],
        )

    sizes: dict[Path, int] = {}
    try:
        while True:
            try:
                poll_once(config, sizes)
            except Exception:
                logger.exception("Unexpected error during folder scan; continuing.")
            time.sleep(config["poll_interval"])
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
