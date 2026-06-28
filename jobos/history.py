"""Application history — discover and load previous generated application packs."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from jobos.schemas import ApplicationPack


@dataclass
class ApplicationFolder:
    """Metadata about one discovered application output folder."""

    path: Path
    folder_name: str
    modified_time: float
    company: str = ""
    role_title: str = ""
    fit_score: int = 0
    category: str = ""
    has_pack_json: bool = False
    has_pack_md: bool = False
    has_cv_md: bool = False
    has_cl_md: bool = False
    has_answers_md: bool = False
    has_cv_docx: bool = False
    has_cl_docx: bool = False


def scan_applications(applications_dir: Path) -> list[ApplicationFolder]:
    """Scan an applications directory and return ApplicationFolder entries, newest first.

    Each folder is inspected for known file names; metadata is read from
    application_pack.json when present, with a folder-name fallback.
    """
    applications_dir = Path(applications_dir)
    if not applications_dir.exists():
        return []

    entries: list[ApplicationFolder] = []
    for folder in applications_dir.iterdir():
        if not folder.is_dir() or folder.name.startswith("."):
            continue

        try:
            mtime = folder.stat().st_mtime
        except OSError:
            continue

        entry = ApplicationFolder(
            path=folder,
            folder_name=folder.name,
            modified_time=mtime,
            has_pack_json=(folder / "application_pack.json").exists(),
            has_pack_md=(folder / "application_pack.md").exists(),
            has_cv_md=(folder / "tailored_cv.md").exists(),
            has_cl_md=(folder / "cover_letter.md").exists(),
            has_answers_md=(folder / "application_answers.md").exists(),
            has_cv_docx=(folder / "tailored_cv.docx").exists(),
            has_cl_docx=(folder / "cover_letter.docx").exists(),
        )

        # Prefer metadata from the pack JSON
        if entry.has_pack_json:
            try:
                data = json.loads(
                    (folder / "application_pack.json").read_text(encoding="utf-8")
                )
                pj = data.get("parsed_job", {})
                fs = data.get("fit_score", {})
                entry.company = pj.get("company", "")
                entry.role_title = pj.get("role_title", "")
                entry.fit_score = int(fs.get("overall_score", 0))
                entry.category = fs.get("category", "")
            except Exception:
                pass

        # Fallback: parse folder name (YYYYMMDD_HHMMSS_Company_Rest)
        if not entry.company and "_" in folder.name:
            parts = folder.name.split("_", 2)
            if len(parts) >= 3:
                entry.company = parts[2].replace("_", " ")[:60]

        entries.append(entry)

    entries.sort(key=lambda e: e.modified_time, reverse=True)
    return entries


def load_pack_from_folder(folder_path: Path) -> Optional[ApplicationPack]:
    """Load and return an ApplicationPack from a folder's application_pack.json.

    Returns None if the JSON file is absent or cannot be parsed.
    """
    pack_json = Path(folder_path) / "application_pack.json"
    if not pack_json.exists():
        return None
    try:
        data = json.loads(pack_json.read_text(encoding="utf-8"))
        return ApplicationPack.model_validate(data)
    except Exception:
        return None


def read_file_content(path: Path) -> str:
    """Read a file and return its text, or empty string on error."""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""
