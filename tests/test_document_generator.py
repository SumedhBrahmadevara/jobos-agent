"""Tests for template-locked document generator."""
from __future__ import annotations

from pathlib import Path

import pytest


# ── cv_master.yaml schema ──────────────────────────────────────────────────────

def test_cv_master_loads():
    from jobos.document_generator import load_cv_master
    master = load_cv_master()
    assert isinstance(master, dict)
    assert "experience" in master
    assert "education" in master
    assert "skills" in master
    assert "cover_letter_paragraphs" in master


def test_cv_master_has_meta():
    from jobos.document_generator import load_cv_master
    master = load_cv_master()
    meta = master.get("meta", {})
    assert meta.get("name"), "cv_master.yaml meta.name is empty"
    assert meta.get("location"), "cv_master.yaml meta.location is empty"


def test_all_experience_bullets_have_required_fields():
    from jobos.document_generator import load_cv_master
    master = load_cv_master()
    for role in master.get("experience", []):
        for bullet in role.get("bullets", []):
            assert "id" in bullet, f"Bullet missing id: {bullet}"
            assert "text" in bullet, f"Bullet missing text: {bullet}"
            assert "tags" in bullet, f"Bullet missing tags: {bullet}"
            assert isinstance(bullet["tags"], list), f"Bullet tags must be a list: {bullet}"
            assert len(bullet["tags"]) > 0, f"Bullet tags must not be empty: {bullet}"
            assert len(bullet["text"]) > 10, f"Bullet text too short: {bullet}"


def test_all_skills_have_required_fields():
    from jobos.document_generator import load_cv_master
    master = load_cv_master()
    for skill in master.get("skills", []):
        assert "id" in skill, f"Skill missing id: {skill}"
        assert "text" in skill, f"Skill missing text: {skill}"
        assert "tags" in skill, f"Skill missing tags: {skill}"
        assert isinstance(skill["tags"], list), f"Skill tags must be a list: {skill}"


def test_bullet_ids_are_unique():
    from jobos.document_generator import load_cv_master
    master = load_cv_master()
    ids: list[str] = []
    for role in master.get("experience", []):
        for b in role.get("bullets", []):
            ids.append(b["id"])
    assert len(ids) == len(set(ids)), f"Duplicate bullet IDs found: {ids}"


def test_skill_ids_are_unique():
    from jobos.document_generator import load_cv_master
    master = load_cv_master()
    ids = [s["id"] for s in master.get("skills", [])]
    assert len(ids) == len(set(ids)), f"Duplicate skill IDs found: {ids}"


def test_cover_letter_paragraphs_present():
    from jobos.document_generator import load_cv_master
    master = load_cv_master()
    cl = master.get("cover_letter_paragraphs", {})
    for key in ("opening", "body_credit", "body_cambridge", "body_motivation", "closing"):
        assert key in cl, f"Missing cover_letter_paragraphs.{key}"
        assert len(cl[key]) > 0, f"cover_letter_paragraphs.{key} is empty"


# ── Tag extraction ─────────────────────────────────────────────────────────────

def test_jd_to_tags_basic():
    from jobos.document_generator import jd_to_tags
    from jobos.schemas import ParsedJob
    job = ParsedJob(
        company="Test", role_title="Investment Analyst",
        required_skills=["financial modelling", "credit research"],
        preferred_skills=[], responsibilities=[],
    )
    tags = jd_to_tags(job)
    assert "financial_modelling" in tags
    assert "credit" in tags
    assert "investment" in tags


def test_jd_to_tags_python():
    from jobos.document_generator import jd_to_tags
    from jobos.schemas import ParsedJob
    job = ParsedJob(company="T", role_title="Analyst", required_skills=["python"], preferred_skills=[], responsibilities=[])
    tags = jd_to_tags(job)
    assert "python_careful" in tags


def test_jd_to_tags_empty_job():
    from jobos.document_generator import jd_to_tags
    from jobos.schemas import ParsedJob
    job = ParsedJob(company="T", role_title="Analyst")
    tags = jd_to_tags(job)
    assert isinstance(tags, set)


# ── Bullet selection ───────────────────────────────────────────────────────────

def test_select_bullets_always_include():
    from jobos.document_generator import select_bullets
    bullets = [
        {"id": "B001", "text": "Always bullet", "tags": ["research"], "always_include": True},
        {"id": "B002", "text": "No match bullet", "tags": ["unrelated"]},
        {"id": "B003", "text": "Match bullet", "tags": ["investment"]},
    ]
    result = select_bullets(bullets, {"investment"})
    ids = [b["id"] for b in result]
    assert "B001" in ids, "always_include bullet must be selected"
    assert "B003" in ids, "matching bullet must be selected"
    assert "B002" not in ids, "non-matching bullet must not be selected"


def test_select_bullets_respects_max_count():
    from jobos.document_generator import select_bullets
    bullets = [
        {"id": f"B{i:03d}", "text": f"Bullet {i}", "tags": ["investment"]}
        for i in range(10)
    ]
    result = select_bullets(bullets, {"investment"}, max_count=3)
    assert len(result) == 3


def test_select_bullets_preserves_yaml_order():
    from jobos.document_generator import select_bullets
    bullets = [
        {"id": "B001", "text": "First", "tags": ["investment"], "always_include": True},
        {"id": "B002", "text": "Second", "tags": ["investment"]},
        {"id": "B003", "text": "Third", "tags": ["investment"]},
    ]
    result = select_bullets(bullets, {"investment"})
    assert [b["id"] for b in result] == ["B001", "B002", "B003"]


def test_real_cv_master_always_include_selected():
    from jobos.document_generator import load_cv_master, select_bullets, jd_to_tags
    from jobos.schemas import ParsedJob
    master = load_cv_master()
    all_bullets = []
    for role in master.get("experience", []):
        all_bullets.extend(role.get("bullets", []))
    job = ParsedJob(company="T", role_title="Analyst", required_skills=[])
    tags = jd_to_tags(job)
    selected = select_bullets(all_bullets, tags)
    always = [b for b in all_bullets if b.get("always_include")]
    for b in always:
        assert b in selected, f"always_include bullet {b['id']} not in selected"


# ── Skill selection ────────────────────────────────────────────────────────────

def test_select_skills_splits_adjacent():
    from jobos.document_generator import select_skills
    skills = [
        {"id": "SK001", "text": "Credit research", "tags": ["credit"]},
        {"id": "SK002", "text": "Python building", "tags": ["python_careful"], "adjacent": True},
        {"id": "SK003", "text": "Financial modelling", "tags": ["financial_modelling"]},
    ]
    main, adjacent = select_skills(skills, {"credit", "python_careful"})
    assert "Credit research" in main
    assert "Python building" not in main
    assert any(s["id"] == "SK002" for s in adjacent)


def test_select_skills_adjacent_excluded_when_not_relevant():
    from jobos.document_generator import select_skills
    skills = [
        {"id": "SK001", "text": "Credit research", "tags": ["credit"]},
        {"id": "SK002", "text": "Python building", "tags": ["python_careful"], "adjacent": True},
    ]
    main, adjacent = select_skills(skills, {"credit"})
    assert "Python building" not in main
    assert len(adjacent) == 0, "Python skill should not appear when JD doesn't mention python"


def test_select_skills_orders_by_relevance():
    from jobos.document_generator import select_skills
    skills = [
        {"id": "SK001", "text": "Unrelated skill", "tags": ["unrelated"]},
        {"id": "SK002", "text": "Highly relevant", "tags": ["credit", "investment", "modelling"]},
        {"id": "SK003", "text": "Somewhat relevant", "tags": ["credit"]},
    ]
    main, _ = select_skills(skills, {"credit", "investment", "modelling"})
    assert main[0] == "Highly relevant"


# ── CV rendering ───────────────────────────────────────────────────────────────

_CV_HEADINGS_IN_ORDER = [
    "## Profile",
    "## Core Competencies",
    "## Experience",
    "## Education",
]


def _make_test_pack():
    """Build a minimal offline ApplicationPack for rendering tests."""
    import tempfile
    from apply import build_pack
    jd = "Company: Test Fund\nRole: Investment Analyst\nFundamental research and financial modelling required."
    qs = "Why are you interested in this role?"
    with tempfile.TemporaryDirectory() as tmp:
        jf = Path(tmp) / "j.txt"
        qf = Path(tmp) / "q.txt"
        jf.write_text(jd, encoding="utf-8")
        qf.write_text(qs, encoding="utf-8")
        return build_pack(jf, qf)


def test_generated_cv_has_all_locked_headings():
    from jobos.document_generator import generate_documents
    from jobos.io import load_yaml
    from jobos.config import DATA_DIR
    pack = _make_test_pack()
    profile = load_yaml(DATA_DIR / "profile.yaml")
    approved = load_yaml(DATA_DIR / "approved_claims.yaml")
    cv_content, _, _ = generate_documents(pack, profile, approved.get("adjacent_claims", {}), approved_claims_full=approved)
    for heading in _CV_HEADINGS_IN_ORDER:
        assert heading in cv_content, f"Missing heading: {heading}"


def test_cv_headings_appear_in_correct_order():
    from jobos.document_generator import generate_documents
    from jobos.io import load_yaml
    from jobos.config import DATA_DIR
    pack = _make_test_pack()
    profile = load_yaml(DATA_DIR / "profile.yaml")
    approved = load_yaml(DATA_DIR / "approved_claims.yaml")
    cv_content, _, _ = generate_documents(pack, profile, {}, approved_claims_full=approved)
    positions = [cv_content.index(h) for h in _CV_HEADINGS_IN_ORDER]
    assert positions == sorted(positions), "CV headings are not in the required order"


def test_cv_no_unreplaced_tokens():
    from jobos.document_generator import generate_documents
    from jobos.io import load_yaml
    from jobos.config import DATA_DIR
    import re
    pack = _make_test_pack()
    profile = load_yaml(DATA_DIR / "profile.yaml")
    approved = load_yaml(DATA_DIR / "approved_claims.yaml")
    cv_content, _, cl_content = generate_documents(pack, profile, {}, approved_claims_full=approved)
    unreplaced_cv = re.findall(r"\{\{[A-Z_]+\}\}", cv_content)
    unreplaced_cl = re.findall(r"\{\{[A-Z_]+\}\}", cl_content)
    assert unreplaced_cv == [], f"Unreplaced CV tokens: {unreplaced_cv}"
    assert unreplaced_cl == [], f"Unreplaced CL tokens: {unreplaced_cl}"


def test_cv_contains_profile_name():
    from jobos.document_generator import generate_documents
    from jobos.io import load_yaml
    from jobos.config import DATA_DIR
    pack = _make_test_pack()
    profile = load_yaml(DATA_DIR / "profile.yaml")
    cv_content, _, _ = generate_documents(pack, profile, {})
    assert "Sumedh Brahmadevara" in cv_content


def test_cv_education_section_contains_cambridge():
    from jobos.document_generator import generate_documents
    from jobos.io import load_yaml
    from jobos.config import DATA_DIR
    pack = _make_test_pack()
    profile = load_yaml(DATA_DIR / "profile.yaml")
    cv_content, _, _ = generate_documents(pack, profile, {})
    assert "Cambridge" in cv_content
    assert "Adam Smith Prize" in cv_content


def test_cv_forbidden_claims_not_in_body():
    from jobos.document_generator import generate_documents
    from jobos.io import load_yaml
    from jobos.config import DATA_DIR
    pack = _make_test_pack()
    profile = load_yaml(DATA_DIR / "profile.yaml")
    approved = load_yaml(DATA_DIR / "approved_claims.yaml")
    forbidden = approved.get("forbidden_claims", [])
    cv_content, _, _ = generate_documents(pack, profile, {}, approved_claims_full=approved)

    # Check body only (before the "Do NOT Include" section which lists them intentionally)
    body = cv_content.split("## Do NOT Include")[0].lower()
    for fc in forbidden:
        assert fc.lower() not in body, f"Forbidden claim '{fc}' found in CV body"


def test_cv_adjacent_skill_only_in_framing_section_when_relevant():
    from jobos.document_generator import generate_documents, load_cv_master
    from jobos.io import load_yaml
    from jobos.config import DATA_DIR
    from jobos.schemas import ParsedJob, FitScore, CVTailorSuggestions, VerificationResult, ApplicationPack, DraftAnswer

    master = load_cv_master()
    profile = load_yaml(DATA_DIR / "profile.yaml")
    approved = load_yaml(DATA_DIR / "approved_claims.yaml")

    # JD that explicitly mentions Python
    ct = CVTailorSuggestions(
        positioning_angle="Lead with analytical skills.",
        cv_summary_draft="Credit analyst with strong analytical foundations.",
        bullets_to_emphasise=[],
        bullets_to_de_emphasise=[],
        reordered_skills=[],
        risks_and_gaps=[],
        approved_claims_usable=[],
        adjacent_experience=["Building Python capability for investment workflow tools."],
        unsupported_claims=[],
        cv_summary_verification=VerificationResult(
            pass_check=True, unsupported_claims=[], exaggerated_claims=[],
            generic_phrases=[], adjacent_claims_detected=[], recommended_edits=[], final_risk_level="low",
        ),
    )
    job = ParsedJob(company="Quant Fund", role_title="Analyst", required_skills=["python", "data"])
    fit = FitScore(overall_score=70, category="B", reason="ok", strengths=[], weaknesses=[],
                   application_strategy="Lead with credit.", needs_referral=False)
    pack = ApplicationPack(
        parsed_job=job, fit_score=fit, answers=[], cv_angle="",
        cover_letter_outline=[], cv_tailor=ct, risks_to_review=[],
    )
    cv_content, _, _ = generate_documents(pack, profile, {}, approved_claims_full=approved, cv_master=master)

    # Python should appear in the framing guide section, not in skills list
    framing_section = ""
    if "## Adjacent Experience" in cv_content:
        framing_section = cv_content.split("## Adjacent Experience")[1]

    # The Python building capability statement should be in the framing section
    assert "Python" in framing_section or "python" in framing_section.lower()

    # The main skills list (before adjacent section) should not contain "Python building"
    main_body = cv_content.split("## Adjacent Experience")[0] if "## Adjacent Experience" in cv_content else cv_content
    # "Python — building workflow automation capability" is the adjacent skill text from cv_master
    assert "Python — building workflow automation" not in main_body.split("## Core Competencies")[1].split("## Experience")[0] if "## Core Competencies" in main_body and "## Experience" in main_body else True


def test_cv_high_risk_warning_banner_present():
    from jobos.document_generator import generate_documents
    from jobos.schemas import (
        ApplicationPack, ParsedJob, FitScore, CVTailorSuggestions, VerificationResult
    )
    from jobos.io import load_yaml
    from jobos.config import DATA_DIR
    profile = load_yaml(DATA_DIR / "profile.yaml")

    risky_vr = VerificationResult(
        pass_check=False, unsupported_claims=["expert python developer"],
        exaggerated_claims=[], generic_phrases=[], adjacent_claims_detected=[],
        recommended_edits=["Remove 'expert'."], final_risk_level="high",
    )
    ct = CVTailorSuggestions(
        positioning_angle="Lead with credit.", cv_summary_draft="Expert Python developer.",
        bullets_to_emphasise=[], bullets_to_de_emphasise=[], reordered_skills=[],
        risks_and_gaps=[], approved_claims_usable=[], adjacent_experience=[],
        unsupported_claims=[], cv_summary_verification=risky_vr,
    )
    job = ParsedJob(company="Co", role_title="Analyst")
    fit = FitScore(overall_score=70, category="B", reason="ok", strengths=[], weaknesses=[],
                   application_strategy="Lead with credit.", needs_referral=False)
    pack = ApplicationPack(
        parsed_job=job, fit_score=fit, answers=[], cv_angle="",
        cover_letter_outline=[], cv_tailor=ct, risks_to_review=[],
    )
    cv_content, warnings, _ = generate_documents(pack, profile, {})
    assert "CLAIM REVIEW REQUIRED" in cv_content
    assert len(warnings) > 0


# ── Cover letter rendering ─────────────────────────────────────────────────────

_CL_REQUIRED_SECTIONS = [
    "Dear Hiring Manager",
    "Yours sincerely",
    "Cover Letter Guidance",
]


def test_cover_letter_has_required_sections():
    from jobos.document_generator import generate_documents
    from jobos.io import load_yaml
    from jobos.config import DATA_DIR
    pack = _make_test_pack()
    profile = load_yaml(DATA_DIR / "profile.yaml")
    _, _, cl_content = generate_documents(pack, profile, {})
    for section in _CL_REQUIRED_SECTIONS:
        assert section in cl_content, f"Missing CL section: {section}"


def test_cover_letter_contains_company_and_role():
    from jobos.document_generator import generate_documents
    from jobos.io import load_yaml
    from jobos.config import DATA_DIR
    pack = _make_test_pack()
    profile = load_yaml(DATA_DIR / "profile.yaml")
    _, _, cl_content = generate_documents(pack, profile, {})
    assert "Test Fund" in cl_content
    assert "Investment Analyst" in cl_content


def test_cover_letter_paragraph_structure():
    """Cover letter must have all four body sections in order."""
    from jobos.document_generator import generate_documents
    from jobos.io import load_yaml
    from jobos.config import DATA_DIR
    pack = _make_test_pack()
    profile = load_yaml(DATA_DIR / "profile.yaml")
    _, _, cl_content = generate_documents(pack, profile, {})

    # All four paragraph content markers should appear in the right order
    markers = [
        "Dear Hiring Manager",   # salutation
        "Premier Miton",         # body_credit paragraph always references current employer
        "Cambridge",             # body_cambridge always references Cambridge
        "ADD FIRM-SPECIFIC",     # motivation paragraph placeholder
        "Yours sincerely",       # sign-off
    ]
    positions = [cl_content.find(m) for m in markers]
    assert all(p != -1 for p in positions), f"Missing marker: {[m for m, p in zip(markers, positions) if p == -1]}"
    assert positions == sorted(positions), "Cover letter paragraphs are not in the required order"


def test_cover_letter_firm_specific_placeholder_present():
    from jobos.document_generator import generate_documents
    from jobos.io import load_yaml
    from jobos.config import DATA_DIR
    pack = _make_test_pack()
    profile = load_yaml(DATA_DIR / "profile.yaml")
    _, _, cl_content = generate_documents(pack, profile, {})
    assert "ADD FIRM-SPECIFIC MOTIVATION" in cl_content


# ── Full bundle integration ────────────────────────────────────────────────────

def test_full_bundle_creates_all_five_files(tmp_path):
    from apply import build_pack
    from jobos.application_bundle import generate_bundle
    from jobos.io import load_yaml
    from jobos.config import DATA_DIR

    jd = "Company: Hedge Fund\nRole: Analyst\nCredit and investment research."
    qs = "Why are you interested in this role?"
    jf = tmp_path / "j.txt"
    qf = tmp_path / "q.txt"
    jf.write_text(jd, encoding="utf-8")
    qf.write_text(qs, encoding="utf-8")

    pack = build_pack(jf, qf)
    profile = load_yaml(DATA_DIR / "profile.yaml")
    approved = load_yaml(DATA_DIR / "approved_claims.yaml")
    adjacent = approved.get("adjacent_claims", {})

    result = generate_bundle(pack, tmp_path / "bundle", profile, adjacent, approved_claims_full=approved)

    from pathlib import Path as P
    assert P(result.tailored_cv_path).exists()
    assert P(result.cover_letter_path).exists()
    assert P(result.answers_path).exists()
    assert P(result.pack_json_path).exists()
    assert P(result.pack_md_path).exists()


def test_bundle_cv_follows_locked_headings(tmp_path):
    from apply import build_pack
    from jobos.application_bundle import generate_bundle
    from jobos.io import load_yaml
    from jobos.config import DATA_DIR
    from pathlib import Path as P

    jf = tmp_path / "j.txt"
    qf = tmp_path / "q.txt"
    jf.write_text("Company: Fund\nRole: Analyst\nFundamental research required.", encoding="utf-8")
    qf.write_text("", encoding="utf-8")

    pack = build_pack(jf, qf)
    profile = load_yaml(DATA_DIR / "profile.yaml")
    approved = load_yaml(DATA_DIR / "approved_claims.yaml")
    result = generate_bundle(pack, tmp_path / "bundle", profile, {}, approved_claims_full=approved)

    cv_text = P(result.tailored_cv_path).read_text(encoding="utf-8")
    for heading in _CV_HEADINGS_IN_ORDER:
        assert heading in cv_text, f"Bundle CV missing locked heading: {heading}"
