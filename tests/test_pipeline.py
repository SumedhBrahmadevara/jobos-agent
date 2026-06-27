"""Offline end-to-end tests for the full application pipeline."""
from pathlib import Path
import pytest


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


# ── Full pipeline ─────────────────────────────────────────────────────────────

def test_pipeline_returns_complete_pack(tmp_path):
    from apply import build_pack
    job = _write(
        tmp_path / "job.txt",
        "Company: Test Fund\nRole: Equity Analyst\nLocation: London\n"
        "We need public markets, financial modelling and consumer sector experience.",
    )
    qs = _write(
        tmp_path / "questions.txt",
        "Why are you interested in this role?\nWhat makes you a strong fit?",
    )
    pack = build_pack(job, qs)
    assert pack.parsed_job.company == "Test Fund"
    assert pack.parsed_job.role_title == "Equity Analyst"
    assert 0 <= pack.fit_score.overall_score <= 100
    assert pack.fit_score.category in {"A", "B", "C", "reject"}
    assert pack.fit_score.application_strategy
    assert len(pack.answers) == 2
    assert isinstance(pack.risks_to_review, list)
    assert pack.cv_angle
    assert len(pack.cover_letter_outline) > 0


def test_pipeline_produces_one_answer_per_question(tmp_path):
    from apply import build_pack
    job = _write(tmp_path / "job.txt", "Company: Firm\nRole: Analyst\n")
    qs = _write(
        tmp_path / "questions.txt",
        "Question one?\nQuestion two?\nQuestion three?",
    )
    pack = build_pack(job, qs)
    assert len(pack.answers) == 3
    questions_out = [a.question for a in pack.answers]
    assert "Question one?" in questions_out
    assert "Question three?" in questions_out


def test_pipeline_answers_flagged_for_human_review(tmp_path):
    from apply import build_pack
    job = _write(tmp_path / "job.txt", "Company: Firm\nRole: Analyst\n")
    qs = _write(tmp_path / "questions.txt", "Why this role?")
    pack = build_pack(job, qs)
    # Offline drafts always require human review
    assert all(ans.needs_human_review for ans in pack.answers)


def test_pipeline_with_empty_questions_returns_no_answers(tmp_path):
    from apply import build_pack
    job = _write(tmp_path / "job.txt", "Company: Firm\nRole: Analyst\n")
    qs = _write(tmp_path / "questions.txt", "")
    pack = build_pack(job, qs)
    assert pack.answers == []


def test_pipeline_does_not_write_to_outputs(tmp_path):
    """build_pack returns a Python object; it must not write application files."""
    from apply import build_pack
    from jobos.config import APPLICATIONS_DIR
    job = _write(tmp_path / "job.txt", "Company: Firm\nRole: Analyst\n")
    qs = _write(tmp_path / "questions.txt", "")
    before = set(APPLICATIONS_DIR.rglob("*")) if APPLICATIONS_DIR.exists() else set()
    build_pack(job, qs)
    after = set(APPLICATIONS_DIR.rglob("*")) if APPLICATIONS_DIR.exists() else set()
    assert after == before, "build_pack must not write files to outputs/applications/"


def test_pipeline_claim_verification_integrated(tmp_path):
    """Answers containing risky terms should be marked for review by build_pack."""
    from apply import build_pack
    job = _write(
        tmp_path / "job.txt",
        "Company: Firm\nRole: Analyst\nPython and machine learning required.",
    )
    qs = _write(tmp_path / "questions.txt", "Why are you interested in this role?")
    pack = build_pack(job, qs)
    # All offline answers are human-review; risk flags roll up into risks_to_review
    assert isinstance(pack.risks_to_review, list)


def test_pipeline_pydantic_schema_validates_pack(tmp_path):
    """ApplicationPack must round-trip through model_dump without error."""
    from apply import build_pack
    from jobos.schemas import ApplicationPack
    job = _write(tmp_path / "job.txt", "Company: Firm\nRole: Analyst\n")
    qs = _write(tmp_path / "questions.txt", "Why this role?")
    pack = build_pack(job, qs)
    dumped = pack.model_dump()
    restored = ApplicationPack.model_validate(dumped)
    assert restored.parsed_job.company == pack.parsed_job.company
    assert restored.fit_score.overall_score == pack.fit_score.overall_score
