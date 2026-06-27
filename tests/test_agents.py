"""Offline tests for the four core agents and the compliance classifier."""
from jobos.schemas import ParsedJob, FitScore

# ── Helpers ───────────────────────────────────────────────────────────────────

def _minimal_parsed_job(**kwargs) -> ParsedJob:
    defaults = dict(
        company="Acme",
        role_title="Analyst",
        required_skills=[],
        preferred_skills=[],
        responsibilities=[],
        red_flags=[],
    )
    defaults.update(kwargs)
    return ParsedJob(**defaults)


def _minimal_fit_score(**kwargs) -> FitScore:
    defaults = dict(
        overall_score=70,
        category="B",
        reason="Good fit",
        strengths=["Financial modelling"],
        weaknesses=[],
        application_strategy="Position as analyst",
        needs_referral=False,
    )
    defaults.update(kwargs)
    return FitScore(**defaults)


# ── Job Parser Agent ──────────────────────────────────────────────────────────

def test_job_parser_extracts_company_role_location():
    from jobos.agents.job_parser_agent import parse_job
    result = parse_job(
        "Company: Acme Capital\nRole: Credit Analyst\nLocation: London\n"
        "We need public markets and financial modelling experience."
    )
    assert result.company == "Acme Capital"
    assert result.role_title == "Credit Analyst"
    assert result.location == "London"


def test_job_parser_returns_lists():
    from jobos.agents.job_parser_agent import parse_job
    result = parse_job("Company: Firm\nRole: Analyst\nWe need modelling and research skills.")
    assert isinstance(result.required_skills, list)
    assert isinstance(result.responsibilities, list)
    assert isinstance(result.red_flags, list)


def test_job_parser_flags_python_as_red_flag():
    from jobos.agents.job_parser_agent import parse_job
    result = parse_job("Company: Quant Fund\nRole: Researcher\nPython skills required.")
    assert any("python" in flag.lower() for flag in result.red_flags)


def test_job_parser_unknown_fields_default_gracefully():
    from jobos.agents.job_parser_agent import parse_job
    result = parse_job("No structured data here at all.")
    assert result.company == "Unknown"
    assert result.role_title == "Unknown"


# ── Fit Scorer Agent ──────────────────────────────────────────────────────────

def test_fit_scorer_returns_valid_score_and_category():
    from jobos.agents.fit_scorer_agent import score_fit
    parsed = _minimal_parsed_job(
        required_skills=["public markets", "financial modelling"],
    )
    result = score_fit(parsed, {})
    assert 0 <= result.overall_score <= 100
    assert result.category in {"A", "B", "C", "reject"}


def test_fit_scorer_returns_non_empty_strategy_and_strengths():
    from jobos.agents.fit_scorer_agent import score_fit
    parsed = _minimal_parsed_job(required_skills=["public markets"])
    result = score_fit(parsed, {})
    assert result.application_strategy
    assert len(result.strengths) > 0


def test_fit_scorer_public_markets_overlap_boosts_score():
    from jobos.agents.fit_scorer_agent import score_fit
    with_overlap = score_fit(
        _minimal_parsed_job(required_skills=["public markets", "investment"]), {}
    ).overall_score
    without_overlap = score_fit(
        _minimal_parsed_job(required_skills=["operations"]), {}
    ).overall_score
    assert with_overlap > without_overlap


def test_fit_scorer_penalises_python_requirement():
    from jobos.agents.fit_scorer_agent import score_fit
    with_python = score_fit(
        _minimal_parsed_job(required_skills=["python", "machine learning"]), {}
    ).overall_score
    without_python = score_fit(
        _minimal_parsed_job(required_skills=["public markets"]), {}
    ).overall_score
    assert with_python < without_python


# ── Answer Drafter Agent ──────────────────────────────────────────────────────

def test_answer_drafter_returns_non_empty_answer():
    from jobos.agents.answer_drafter_agent import draft_answer
    result = draft_answer(
        question="Why are you interested in this role?",
        parsed_job=_minimal_parsed_job(),
        fit_score=_minimal_fit_score(),
        profile={},
        approved_claims={},
        answer_bank={},
    )
    assert result.answer
    assert result.word_count > 0


def test_answer_drafter_marks_offline_drafts_for_review():
    from jobos.agents.answer_drafter_agent import draft_answer
    result = draft_answer(
        question="What makes you a strong fit?",
        parsed_job=_minimal_parsed_job(),
        fit_score=_minimal_fit_score(),
        profile={},
        approved_claims={},
        answer_bank={},
    )
    assert result.needs_human_review
    assert result.review_reason


def test_answer_drafter_confidence_is_valid():
    from jobos.agents.answer_drafter_agent import draft_answer
    result = draft_answer(
        question="Describe a time you used data to make a decision.",
        parsed_job=_minimal_parsed_job(),
        fit_score=_minimal_fit_score(),
        profile={},
        approved_claims={},
        answer_bank={},
    )
    assert result.confidence in {"high", "medium", "low"}


def test_answer_drafter_data_question_mentions_data():
    from jobos.agents.answer_drafter_agent import draft_answer
    result = draft_answer(
        question="Describe a time you used data to make a decision.",
        parsed_job=_minimal_parsed_job(),
        fit_score=_minimal_fit_score(),
        profile={},
        approved_claims={},
        answer_bank={},
    )
    assert "data" in result.answer.lower()


# ── Claim Verifier Agent ──────────────────────────────────────────────────────

def test_claim_verifier_passes_clean_answer():
    from jobos.agents.claim_verifier_agent import verify_answer
    result = verify_answer(
        "I bring strong credit research skills and financial modelling experience.",
        approved_claims={},
        forbidden_claims=[],
    )
    assert result.final_risk_level == "low"
    assert result.pass_check


def test_claim_verifier_flags_forbidden_claims_as_high_risk():
    from jobos.agents.claim_verifier_agent import verify_answer
    result = verify_answer(
        "I am a production machine learning engineer.",
        approved_claims={},
        forbidden_claims=["Production machine learning engineer"],
    )
    assert result.final_risk_level == "high"
    assert not result.pass_check
    assert len(result.exaggerated_claims) > 0


def test_claim_verifier_flags_risky_terms_as_unsupported():
    from jobos.agents.claim_verifier_agent import verify_answer
    result = verify_answer(
        "I am an expert with advanced python production skills.",
        approved_claims={},
        forbidden_claims=[],
    )
    assert result.final_risk_level == "high"
    assert "expert" in result.unsupported_claims


def test_claim_verifier_flags_generic_phrases_as_medium_risk():
    from jobos.agents.claim_verifier_agent import verify_answer
    result = verify_answer(
        "I thrive in a dynamic culture with a commitment to excellence.",
        approved_claims={},
        forbidden_claims=[],
    )
    assert result.final_risk_level == "medium"
    assert len(result.generic_phrases) > 0


def test_claim_verifier_accepts_list_or_dict_for_forbidden_claims():
    from jobos.agents.claim_verifier_agent import verify_answer
    answer = "I am a credit analyst."
    # list form (current preferred call-site)
    r1 = verify_answer(answer, {}, [])
    # legacy dict form (old call-site in apply.py)
    r2 = verify_answer(answer, {}, {"forbidden_claims": []})
    assert r1.final_risk_level == r2.final_risk_level


# ── Compliance Agent ──────────────────────────────────────────────────────────

def test_compliance_agent_classifies_red_fields():
    from jobos.agents.compliance_agent import classify_field
    for label in ["Right to work", "Visa sponsorship required", "Criminal conviction"]:
        result = classify_field(label)
        assert result.risk_level == "red", f"Expected red for: {label}"
        assert result.requires_manual_approval


def test_compliance_agent_classifies_green_fields():
    from jobos.agents.compliance_agent import classify_field
    for label in ["Email address", "Phone number", "LinkedIn URL"]:
        result = classify_field(label)
        assert result.risk_level == "green", f"Expected green for: {label}"
        assert not result.requires_manual_approval


def test_compliance_agent_classifies_amber_fields():
    from jobos.agents.compliance_agent import classify_field
    for label in ["Salary expectations", "Why are you applying?"]:
        result = classify_field(label)
        assert result.risk_level == "amber", f"Expected amber for: {label}"
        assert result.requires_manual_approval


def test_compliance_agent_defaults_unknown_fields_to_amber():
    from jobos.agents.compliance_agent import classify_field
    result = classify_field("Proprietary field XYZ-9923")
    assert result.risk_level == "amber"
    assert result.requires_manual_approval
