"""Offline tests for the CV Tailoring Agent."""
import pytest
from jobos.schemas import ParsedJob, FitScore, CVTailorSuggestions


def _job(**kwargs) -> ParsedJob:
    defaults = dict(
        company="Test Fund",
        role_title="Equity Analyst",
        required_skills=[],
        preferred_skills=[],
        responsibilities=[],
        red_flags=[],
    )
    defaults.update(kwargs)
    return ParsedJob(**defaults)


def _fit(**kwargs) -> FitScore:
    defaults = dict(
        overall_score=75,
        category="A",
        reason="Good fit",
        strengths=["Public markets overlap"],
        weaknesses=["Python/data skills may need careful framing"],
        application_strategy="Position as a credit-trained public markets analyst.",
        needs_referral=True,
    )
    defaults.update(kwargs)
    return FitScore(**defaults)


_APPROVED = {
    "approved_claims": {
        "deep_coverage": {
            "claim": "Conduct deep fundamental research across 60+ consumer-sector issuers.",
            "contexts": ["credit analyst applications", "public markets analyst applications"],
        },
        "modelling": {
            "claim": "Build forward-looking financial models covering revenue, FCF and leverage.",
            "contexts": ["equity research", "hedge fund analyst roles"],
        },
    },
    "forbidden_claims": [
        "Advanced Python developer",
        "Production machine learning engineer",
    ],
}


# ── Schema ────────────────────────────────────────────────────────────────────

def test_cv_tailor_returns_correct_type():
    from jobos.agents.cv_tailor_agent import tailor_cv
    result = tailor_cv(_job(), _fit(), {}, {})
    assert isinstance(result, CVTailorSuggestions)


def test_cv_tailor_all_fields_populated():
    from jobos.agents.cv_tailor_agent import tailor_cv
    result = tailor_cv(_job(), _fit(), {}, {})
    assert result.positioning_angle
    assert result.cv_summary_draft
    assert isinstance(result.bullets_to_emphasise, list)
    assert len(result.bullets_to_emphasise) > 0
    assert isinstance(result.bullets_to_de_emphasise, list)
    assert len(result.bullets_to_de_emphasise) > 0
    assert isinstance(result.reordered_skills, list)
    assert isinstance(result.risks_and_gaps, list)
    assert isinstance(result.approved_claims_usable, list)
    assert isinstance(result.adjacent_experience, list)
    assert isinstance(result.unsupported_claims, list)


# ── Positioning ───────────────────────────────────────────────────────────────

def test_positioning_angle_derived_from_fit_strategy():
    from jobos.agents.cv_tailor_agent import tailor_cv
    fit = _fit(application_strategy="Lead with credit discipline and public-markets transferability.")
    result = tailor_cv(_job(), fit, {}, {})
    assert "credit" in result.positioning_angle.lower() or "public" in result.positioning_angle.lower()


# ── Bullets to emphasise ──────────────────────────────────────────────────────

def test_public_markets_role_emphasises_research_bullet():
    from jobos.agents.cv_tailor_agent import tailor_cv
    job = _job(required_skills=["public markets", "financial modelling"])
    result = tailor_cv(job, _fit(), {}, {})
    combined = " ".join(result.bullets_to_emphasise).lower()
    assert "research" in combined or "modelling" in combined


def test_earnings_role_emphasises_earnings_bullet():
    from jobos.agents.cv_tailor_agent import tailor_cv
    job = _job(required_skills=["earnings analysis", "investment views"])
    result = tailor_cv(job, _fit(), {}, {})
    combined = " ".join(result.bullets_to_emphasise).lower()
    assert "earnings" in combined or "investment" in combined


def test_unmatched_jd_returns_fallback_emphasis():
    from jobos.agents.cv_tailor_agent import tailor_cv
    job = _job(required_skills=["operations management"])
    result = tailor_cv(job, _fit(), {}, {})
    assert len(result.bullets_to_emphasise) > 0


# ── Bullets to de-emphasise ───────────────────────────────────────────────────

def test_python_role_de_emphasises_expert_framing():
    from jobos.agents.cv_tailor_agent import tailor_cv
    job = _job(required_skills=["python", "machine learning"])
    result = tailor_cv(job, _fit(), {}, {})
    combined = " ".join(result.bullets_to_de_emphasise).lower()
    assert "python" in combined or "expert" in combined or "production" in combined


def test_equity_role_de_emphasises_credit_leads():
    from jobos.agents.cv_tailor_agent import tailor_cv
    job = _job(role_title="Equity Analyst", required_skills=["equity research"])
    result = tailor_cv(job, _fit(), {}, {})
    combined = " ".join(result.bullets_to_de_emphasise).lower()
    assert "credit" in combined or "bond" in combined or "fixed income" in combined


# ── Adjacent experience ───────────────────────────────────────────────────────

def test_python_role_flags_python_as_adjacent():
    from jobos.agents.cv_tailor_agent import tailor_cv
    job = _job(required_skills=["python", "data analysis"])
    result = tailor_cv(job, _fit(), {}, {})
    assert len(result.adjacent_experience) > 0
    combined = " ".join(result.adjacent_experience).lower()
    assert "python" in combined or "capability" in combined


def test_equity_role_flags_credit_transition_as_adjacent():
    from jobos.agents.cv_tailor_agent import tailor_cv
    job = _job(role_title="Equity Analyst", required_skills=["equity valuation"])
    result = tailor_cv(job, _fit(), {}, {})
    combined = " ".join(result.adjacent_experience).lower()
    assert "equity" in combined or "credit" in combined


def test_quant_role_flags_systematic_as_adjacent():
    from jobos.agents.cv_tailor_agent import tailor_cv
    job = _job(required_skills=["systematic strategies", "quant research"])
    result = tailor_cv(job, _fit(), {}, {})
    combined = " ".join(result.adjacent_experience).lower()
    assert "quant" in combined or "systematic" in combined or "dissertation" in combined


# ── Unsupported claims ────────────────────────────────────────────────────────

def test_unsupported_claims_populated_from_forbidden_list():
    from jobos.agents.cv_tailor_agent import tailor_cv
    result = tailor_cv(_job(), _fit(), {}, _APPROVED)
    assert len(result.unsupported_claims) > 0
    combined = " ".join(result.unsupported_claims).lower()
    assert "python" in combined or "machine learning" in combined


def test_unsupported_claims_not_in_approved_tier():
    from jobos.agents.cv_tailor_agent import tailor_cv
    result = tailor_cv(_job(), _fit(), {}, _APPROVED)
    approved_text = " ".join(result.approved_claims_usable).lower()
    for claim in result.unsupported_claims:
        # No unsupported claim should appear verbatim in the approved tier
        assert claim.lower() not in approved_text


# ── Approved claims ───────────────────────────────────────────────────────────

def test_approved_claims_filtered_for_investment_role():
    from jobos.agents.cv_tailor_agent import tailor_cv
    job = _job(required_skills=["public markets", "investment research"])
    result = tailor_cv(job, _fit(), {}, _APPROVED)
    assert len(result.approved_claims_usable) > 0
    # At least one approved claim should reference relevant content
    combined = " ".join(result.approved_claims_usable).lower()
    assert "research" in combined or "modelling" in combined or "financial" in combined


def test_approved_claims_empty_dict_returns_fallback():
    from jobos.agents.cv_tailor_agent import tailor_cv
    result = tailor_cv(_job(), _fit(), {}, {})
    assert len(result.approved_claims_usable) > 0


# ── CV summary draft ──────────────────────────────────────────────────────────

def test_cv_summary_draft_non_empty():
    from jobos.agents.cv_tailor_agent import tailor_cv
    result = tailor_cv(_job(), _fit(), {}, {})
    assert len(result.cv_summary_draft) > 20


def test_cv_summary_includes_role_and_company():
    from jobos.agents.cv_tailor_agent import tailor_cv
    job = _job(company="Apex Capital", role_title="Portfolio Analyst")
    result = tailor_cv(job, _fit(), {}, {})
    assert "Apex Capital" in result.cv_summary_draft
    assert "Portfolio Analyst" in result.cv_summary_draft


def test_cv_summary_uses_profile_employer_when_available():
    from jobos.agents.cv_tailor_agent import tailor_cv
    profile = {"current_role": {"title": "Credit Analyst", "employer": "Premier Miton Investors"}}
    result = tailor_cv(_job(), _fit(), profile, {})
    assert "Premier Miton" in result.cv_summary_draft


def test_cv_summary_safe_with_empty_profile():
    from jobos.agents.cv_tailor_agent import tailor_cv
    result = tailor_cv(_job(), _fit(), {}, {})
    # Must not crash and must return non-empty text
    assert result.cv_summary_draft


# ── Risks and gaps ────────────────────────────────────────────────────────────

def test_risks_include_fit_score_weaknesses():
    from jobos.agents.cv_tailor_agent import tailor_cv
    fit = _fit(weaknesses=["Limited direct equity experience", "Python needs framing"])
    result = tailor_cv(_job(), fit, {}, {})
    combined = " ".join(result.risks_and_gaps).lower()
    assert "equity" in combined or "python" in combined


def test_risks_include_job_red_flags():
    from jobos.agents.cv_tailor_agent import tailor_cv
    job = _job(red_flags=["May prefer direct equity experience"])
    result = tailor_cv(job, _fit(weaknesses=[]), {}, {})
    combined = " ".join(result.risks_and_gaps).lower()
    assert "equity" in combined


# ── Reordered skills ──────────────────────────────────────────────────────────

def test_reordered_skills_populated():
    from jobos.agents.cv_tailor_agent import tailor_cv
    job = _job(required_skills=["financial modelling", "earnings analysis"])
    result = tailor_cv(job, _fit(), {}, {})
    assert len(result.reordered_skills) > 0


def test_reordered_skills_uses_profile_skills_as_fallback():
    from jobos.agents.cv_tailor_agent import tailor_cv
    profile = {"current_role": {"skills": ["Skill A", "Skill B", "Skill C"]}}
    job = _job(required_skills=["operations"])  # no keyword matches
    result = tailor_cv(job, _fit(), profile, {})
    assert len(result.reordered_skills) > 0
