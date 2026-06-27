"""Tests for the Application Bundle Generator."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

_PROFILE = {
    "personal": {
        "name": "Sumedh Brahmadevara",
        "location": "London, UK",
        "email": "test@example.com",
        "linkedin": "linkedin.com/in/test",
    },
    "current_role": {
        "title": "Credit Analyst",
        "employer": "Premier Miton Investors",
        "start_date": "September 2025",
        "sectors": ["Consumer", "Retail", "Travel"],
        "responsibilities": [
            "Conduct deep fundamental research across 60+ issuers.",
            "Build forward-looking financial models.",
        ],
        "skills": ["Fundamental research", "Financial modelling", "Bond valuation"],
    },
    "education": {
        "university": "University of Cambridge",
        "college": "Emmanuel College",
        "degree": "BA Economics",
        "grade": "2.1",
        "dissertation": {
            "title": "Housing Affordability in the Face of Gentrification",
            "prize": "Adam Smith Prize for Best Dissertation",
            "methods": ["Panel data", "Spatial econometrics", "Fixed effects"],
        },
    },
}

_ADJACENT = {
    "python_experience": {
        "note": "Python: frame carefully.",
        "safe_phrases": ["Building Python capability for investment workflow tools."],
    }
}

_FORBIDDEN = {
    "approved_claims": {
        "current_role": {
            "claim": "Credit Analyst at Premier Miton Investors.",
            "contexts": ["all applications"],
        }
    },
    "adjacent_claims": _ADJACENT,
    "forbidden_claims": [
        "Advanced Python developer",
        "Production machine learning engineer",
        "CFA charterholder",
    ],
}


def _make_pack():
    """Build a minimal offline ApplicationPack for testing."""
    from apply import build_pack

    import tempfile, os

    jd = "Company: Test Fund\nRole: Analyst\nFundamental research and financial modelling required."
    qs = "Why are you interested in this role?\nDescribe your analytical process."

    with tempfile.TemporaryDirectory() as tmp:
        job_file = Path(tmp) / "job.txt"
        q_file = Path(tmp) / "q.txt"
        job_file.write_text(jd, encoding="utf-8")
        q_file.write_text(qs, encoding="utf-8")
        return build_pack(job_file, q_file)


# ── Bundle creation ────────────────────────────────────────────────────────────

def test_bundle_creates_output_folder(tmp_path):
    from jobos.application_bundle import generate_bundle

    pack = _make_pack()
    out_dir = tmp_path / "bundle_test"
    result = generate_bundle(pack, out_dir, _PROFILE, _ADJACENT)
    assert out_dir.exists()
    assert result.out_dir == str(out_dir)


def test_bundle_result_schema_valid(tmp_path):
    from jobos.application_bundle import generate_bundle, BundleResult

    pack = _make_pack()
    result = generate_bundle(pack, tmp_path / "bundle", _PROFILE, _ADJACENT)
    assert isinstance(result, BundleResult)
    assert result.tailored_cv_path
    assert result.cover_letter_path
    assert result.answers_path
    assert result.pack_json_path
    assert result.pack_md_path


# ── All five files exist ───────────────────────────────────────────────────────

def test_bundle_tailored_cv_exists(tmp_path):
    from jobos.application_bundle import generate_bundle

    pack = _make_pack()
    result = generate_bundle(pack, tmp_path / "b", _PROFILE, _ADJACENT)
    assert Path(result.tailored_cv_path).exists()


def test_bundle_cover_letter_exists(tmp_path):
    from jobos.application_bundle import generate_bundle

    pack = _make_pack()
    result = generate_bundle(pack, tmp_path / "b", _PROFILE, _ADJACENT)
    assert Path(result.cover_letter_path).exists()


def test_bundle_application_answers_exists(tmp_path):
    from jobos.application_bundle import generate_bundle

    pack = _make_pack()
    result = generate_bundle(pack, tmp_path / "b", _PROFILE, _ADJACENT)
    assert Path(result.answers_path).exists()


def test_bundle_pack_json_exists_and_valid(tmp_path):
    from jobos.application_bundle import generate_bundle

    pack = _make_pack()
    result = generate_bundle(pack, tmp_path / "b", _PROFILE, _ADJACENT)
    json_path = Path(result.pack_json_path)
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert "parsed_job" in data
    assert "fit_score" in data


def test_bundle_pack_md_exists(tmp_path):
    from jobos.application_bundle import generate_bundle

    pack = _make_pack()
    result = generate_bundle(pack, tmp_path / "b", _PROFILE, _ADJACENT)
    assert Path(result.pack_md_path).exists()


# ── Content checks ─────────────────────────────────────────────────────────────

def test_tailored_cv_contains_profile_name(tmp_path):
    from jobos.application_bundle import generate_bundle

    pack = _make_pack()
    result = generate_bundle(pack, tmp_path / "b", _PROFILE, _ADJACENT)
    cv_text = Path(result.tailored_cv_path).read_text(encoding="utf-8")
    assert "Sumedh Brahmadevara" in cv_text


def test_tailored_cv_contains_education_section(tmp_path):
    from jobos.application_bundle import generate_bundle

    pack = _make_pack()
    result = generate_bundle(pack, tmp_path / "b", _PROFILE, _ADJACENT)
    cv_text = Path(result.tailored_cv_path).read_text(encoding="utf-8")
    assert "Cambridge" in cv_text
    assert "Education" in cv_text


def test_cover_letter_contains_role_and_company(tmp_path):
    from jobos.application_bundle import generate_bundle

    pack = _make_pack()
    result = generate_bundle(pack, tmp_path / "b", _PROFILE, _ADJACENT)
    cl_text = Path(result.cover_letter_path).read_text(encoding="utf-8")
    assert "Test Fund" in cl_text
    assert "Analyst" in cl_text


def test_cover_letter_has_full_letter_structure(tmp_path):
    from jobos.application_bundle import generate_bundle

    pack = _make_pack()
    result = generate_bundle(pack, tmp_path / "b", _PROFILE, _ADJACENT)
    cl_text = Path(result.cover_letter_path).read_text(encoding="utf-8")
    assert "Dear Hiring Manager" in cl_text
    assert "Yours sincerely" in cl_text


def test_answers_md_contains_questions(tmp_path):
    from jobos.application_bundle import generate_bundle

    pack = _make_pack()
    result = generate_bundle(pack, tmp_path / "b", _PROFILE, _ADJACENT)
    ans_text = Path(result.answers_path).read_text(encoding="utf-8")
    # At least one question should appear in the document
    assert any(ans.question[:20] in ans_text for ans in pack.answers)


# ── Forbidden claims not in CV body ───────────────────────────────────────────

def test_no_forbidden_claims_in_cv_body(tmp_path):
    from jobos.application_bundle import generate_bundle

    pack = _make_pack()
    result = generate_bundle(pack, tmp_path / "b", _PROFILE, _ADJACENT, approved_claims_full=_FORBIDDEN)
    cv_text = Path(result.tailored_cv_path).read_text(encoding="utf-8")

    # Split off the "Do NOT Include" section — forbidden claims are listed there intentionally
    body_parts = cv_text.split("## Do NOT Include")
    body = body_parts[0].lower()

    for forbidden in _FORBIDDEN["forbidden_claims"]:
        assert forbidden.lower() not in body, (
            f"Forbidden claim '{forbidden}' found in tailored CV body"
        )


# ── High-risk warning appears when CV summary is flagged ──────────────────────

def test_high_risk_warning_in_cv_when_summary_flagged(tmp_path):
    from jobos.application_bundle import generate_bundle, BundleResult
    from jobos.schemas import (
        ApplicationPack, ParsedJob, FitScore, CVTailorSuggestions, VerificationResult
    )

    # Build a pack with a deliberately high-risk CV summary
    risky_verification = VerificationResult(
        pass_check=False,
        unsupported_claims=["expert python developer"],
        exaggerated_claims=[],
        generic_phrases=[],
        adjacent_claims_detected=[],
        recommended_edits=["Remove 'expert' — not supported by profile."],
        final_risk_level="high",
    )
    ct = CVTailorSuggestions(
        positioning_angle="Lead with credit analysis.",
        cv_summary_draft="Expert Python developer and credit analyst.",
        bullets_to_emphasise=["Fundamental research across 60+ issuers."],
        bullets_to_de_emphasise=[],
        reordered_skills=["Financial modelling"],
        risks_and_gaps=[],
        approved_claims_usable=[],
        adjacent_experience=[],
        unsupported_claims=["Do not claim: expert Python"],
        cv_summary_verification=risky_verification,
    )
    job = ParsedJob(company="Test Co", role_title="Analyst")
    fit = FitScore(
        overall_score=70, category="B", reason="ok",
        strengths=[], weaknesses=[], application_strategy="Lead with credit.",
        needs_referral=False,
    )
    pack = ApplicationPack(
        parsed_job=job, fit_score=fit, answers=[],
        cv_angle="", cover_letter_outline=[], cv_tailor=ct, risks_to_review=[],
    )

    result = generate_bundle(pack, tmp_path / "risky", _PROFILE, {})
    assert len(result.high_risk_warnings) > 0
    cv_text = Path(result.tailored_cv_path).read_text(encoding="utf-8")
    assert "CLAIM REVIEW REQUIRED" in cv_text


# ── Full pipeline integration ──────────────────────────────────────────────────

def test_full_pipeline_produces_bundle(tmp_path):
    """End-to-end: build_pack → generate_bundle → all files exist."""
    from apply import build_pack
    from jobos.application_bundle import generate_bundle
    from jobos.io import load_yaml
    from jobos.config import DATA_DIR

    job_file = tmp_path / "job.txt"
    job_file.write_text(
        "Company: Hedge Fund\nRole: Investment Analyst\n"
        "Fundamental credit and financial modelling experience required.",
        encoding="utf-8",
    )
    q_file = tmp_path / "q.txt"
    q_file.write_text("Why are you interested in this role?", encoding="utf-8")

    pack = build_pack(job_file, q_file)
    profile = load_yaml(DATA_DIR / "profile.yaml")
    approved = load_yaml(DATA_DIR / "approved_claims.yaml")
    adjacent = approved.get("adjacent_claims", {})

    out_dir = tmp_path / "full_bundle"
    result = generate_bundle(pack, out_dir, profile, adjacent, approved_claims_full=approved)

    assert Path(result.tailored_cv_path).exists()
    assert Path(result.cover_letter_path).exists()
    assert Path(result.answers_path).exists()
    assert Path(result.pack_json_path).exists()
    assert Path(result.pack_md_path).exists()

    # CV should have the applicant's name from real profile
    cv_text = Path(result.tailored_cv_path).read_text(encoding="utf-8")
    assert "Sumedh" in cv_text
    assert "Cambridge" in cv_text
