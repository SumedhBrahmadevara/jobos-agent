"""Tests for jobos/history.py — application history discovery and loading."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_pack():
    import tempfile
    from apply import build_pack

    jd = (
        "Company: HistoryTest Fund\n"
        "Role: Credit Analyst\n"
        "Fundamental research and financial modelling required."
    )
    with tempfile.TemporaryDirectory() as tmp:
        job_file = Path(tmp) / "job.txt"
        q_file = Path(tmp) / "q.txt"
        job_file.write_text(jd, encoding="utf-8")
        q_file.write_text("", encoding="utf-8")
        return build_pack(job_file, q_file)


def _write_pack_json(folder: Path, pack=None) -> None:
    """Write a minimal application_pack.json to a folder."""
    if pack is not None:
        data = pack.model_dump()
    else:
        data = {
            "parsed_job": {
                "company": "Acme Capital",
                "role_title": "Research Analyst",
                "location": None,
                "platform": None,
                "responsibilities": [],
                "required_skills": [],
                "preferred_skills": [],
                "seniority_level": "junior",
                "target_profile": "analyst",
                "red_flags": [],
            },
            "fit_score": {
                "overall_score": 72,
                "category": "B",
                "reason": "Good match",
                "strengths": [],
                "weaknesses": [],
                "application_strategy": "Apply",
                "needs_referral": False,
            },
            "cv_angle": "Credit analyst applying to public markets research role.",
            "cv_tailor": {
                "positioning_angle": "Credit analyst background",
                "cv_summary_draft": "Summary text.",
                "cv_summary_verification": None,
                "bullets_to_emphasise": [],
                "bullets_to_de_emphasise": [],
                "reordered_skills": [],
                "approved_claims_usable": [],
                "adjacent_experience": [],
                "unsupported_claims": [],
                "risks_and_gaps": [],
            },
            "cover_letter_outline": [],
            "answers": [],
            "risks_to_review": [],
        }
    (folder / "application_pack.json").write_text(
        json.dumps(data), encoding="utf-8"
    )


# ── scan_applications ──────────────────────────────────────────────────────────


def test_scan_applications_empty_for_nonexistent_dir(tmp_path):
    from jobos.history import scan_applications

    result = scan_applications(tmp_path / "does_not_exist")
    assert result == []


def test_scan_applications_empty_for_empty_dir(tmp_path):
    from jobos.history import scan_applications

    result = scan_applications(tmp_path)
    assert result == []


def test_scan_applications_ignores_files_at_root(tmp_path):
    from jobos.history import scan_applications

    (tmp_path / "stray_file.txt").write_text("hello")
    result = scan_applications(tmp_path)
    assert result == []


def test_scan_applications_finds_single_folder(tmp_path):
    from jobos.history import scan_applications

    folder = tmp_path / "20240101_120000_TestCo_Analyst"
    folder.mkdir()
    result = scan_applications(tmp_path)
    assert len(result) == 1
    assert result[0].folder_name == "20240101_120000_TestCo_Analyst"


def test_scan_applications_reads_metadata_from_json(tmp_path):
    from jobos.history import scan_applications

    folder = tmp_path / "20240101_120000_App1"
    folder.mkdir()
    _write_pack_json(folder)

    result = scan_applications(tmp_path)
    assert len(result) == 1
    assert result[0].company == "Acme Capital"
    assert result[0].role_title == "Research Analyst"
    assert result[0].fit_score == 72
    assert result[0].category == "B"


def test_scan_applications_fallback_company_from_folder_name(tmp_path):
    from jobos.history import scan_applications

    folder = tmp_path / "20240101_120000_BlueFund_Analyst"
    folder.mkdir()
    # No pack JSON — should fall back to folder name parsing
    result = scan_applications(tmp_path)
    assert len(result) == 1
    assert "BlueFund" in result[0].company


def test_scan_applications_detects_present_files(tmp_path):
    from jobos.history import scan_applications

    folder = tmp_path / "app_folder"
    folder.mkdir()
    _write_pack_json(folder)
    (folder / "tailored_cv.md").write_text("cv content")
    (folder / "cover_letter.md").write_text("cl content")

    result = scan_applications(tmp_path)
    entry = result[0]
    assert entry.has_pack_json is True
    assert entry.has_cv_md is True
    assert entry.has_cl_md is True
    assert entry.has_answers_md is False
    assert entry.has_cv_docx is False
    assert entry.has_cl_docx is False


def test_scan_applications_detects_docx_files(tmp_path):
    from jobos.history import scan_applications

    folder = tmp_path / "app_with_docx"
    folder.mkdir()
    (folder / "tailored_cv.docx").write_bytes(b"fake docx")
    (folder / "cover_letter.docx").write_bytes(b"fake docx")

    result = scan_applications(tmp_path)
    assert result[0].has_cv_docx is True
    assert result[0].has_cl_docx is True


def test_scan_applications_sorts_newest_first(tmp_path):
    from jobos.history import scan_applications

    older = tmp_path / "old_app"
    older.mkdir()
    _write_pack_json(older)

    time.sleep(0.05)  # ensure different mtime

    newer = tmp_path / "new_app"
    newer.mkdir()
    _write_pack_json(newer)

    result = scan_applications(tmp_path)
    assert len(result) == 2
    assert result[0].folder_name == "new_app"
    assert result[1].folder_name == "old_app"


def test_scan_applications_ignores_hidden_folders(tmp_path):
    from jobos.history import scan_applications

    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "application_pack.json").write_text("{}")

    result = scan_applications(tmp_path)
    assert result == []


def test_scan_applications_multiple_folders(tmp_path):
    from jobos.history import scan_applications

    for name in ["app_a", "app_b", "app_c"]:
        folder = tmp_path / name
        folder.mkdir()
        _write_pack_json(folder)

    result = scan_applications(tmp_path)
    assert len(result) == 3


# ── load_pack_from_folder ──────────────────────────────────────────────────────


def test_load_pack_returns_none_for_missing_json(tmp_path):
    from jobos.history import load_pack_from_folder

    result = load_pack_from_folder(tmp_path)
    assert result is None


def test_load_pack_returns_none_for_invalid_json(tmp_path):
    from jobos.history import load_pack_from_folder

    (tmp_path / "application_pack.json").write_text("not valid json", encoding="utf-8")
    result = load_pack_from_folder(tmp_path)
    assert result is None


def test_load_pack_returns_none_for_invalid_schema(tmp_path):
    from jobos.history import load_pack_from_folder

    (tmp_path / "application_pack.json").write_text('{"bad": "schema"}', encoding="utf-8")
    result = load_pack_from_folder(tmp_path)
    assert result is None


def test_load_pack_returns_valid_pack(tmp_path):
    from jobos.history import load_pack_from_folder
    from jobos.schemas import ApplicationPack

    _write_pack_json(tmp_path)
    result = load_pack_from_folder(tmp_path)
    assert isinstance(result, ApplicationPack)
    assert result.parsed_job.company == "Acme Capital"
    assert result.parsed_job.role_title == "Research Analyst"
    assert result.fit_score.overall_score == 72


def test_load_pack_round_trips_real_pack(tmp_path):
    from jobos.history import load_pack_from_folder
    from jobos.schemas import ApplicationPack

    pack = _make_pack()
    (tmp_path / "application_pack.json").write_text(
        pack.model_dump_json(), encoding="utf-8"
    )
    loaded = load_pack_from_folder(tmp_path)
    assert isinstance(loaded, ApplicationPack)
    assert loaded.parsed_job.company == pack.parsed_job.company
    assert loaded.parsed_job.role_title == pack.parsed_job.role_title
    assert loaded.fit_score.overall_score == pack.fit_score.overall_score


def test_load_pack_accepts_path_object(tmp_path):
    from jobos.history import load_pack_from_folder

    _write_pack_json(tmp_path)
    result = load_pack_from_folder(Path(tmp_path))
    assert result is not None


# ── read_file_content ──────────────────────────────────────────────────────────


def test_read_file_content_returns_text(tmp_path):
    from jobos.history import read_file_content

    f = tmp_path / "test.md"
    f.write_text("# Hello\n\nWorld.", encoding="utf-8")
    assert read_file_content(f) == "# Hello\n\nWorld."


def test_read_file_content_returns_empty_for_missing(tmp_path):
    from jobos.history import read_file_content

    result = read_file_content(tmp_path / "missing.md")
    assert result == ""


# ── ApplicationFolder dataclass ────────────────────────────────────────────────


def test_application_folder_has_expected_fields(tmp_path):
    from jobos.history import ApplicationFolder

    folder = tmp_path / "some_app"
    folder.mkdir()
    entry = ApplicationFolder(
        path=folder,
        folder_name="some_app",
        modified_time=1234567890.0,
        company="Test Co",
        role_title="Analyst",
    )
    assert entry.company == "Test Co"
    assert entry.has_pack_json is False
    assert entry.has_cv_docx is False
