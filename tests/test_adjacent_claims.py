"""Tests for adjacent/careful claim detection across JobOS."""
from pathlib import Path
import pytest


# ── YAML loading ──────────────────────────────────────────────────────────────

def test_adjacent_claims_present_in_yaml():
    from jobos.io import load_yaml
    from jobos.config import DATA_DIR
    data = load_yaml(DATA_DIR / "approved_claims.yaml")
    assert "adjacent_claims" in data
    adj = data["adjacent_claims"]
    assert isinstance(adj, dict)
    assert len(adj) > 0


def test_adjacent_claims_have_safe_phrases():
    from jobos.io import load_yaml
    from jobos.config import DATA_DIR
    data = load_yaml(DATA_DIR / "approved_claims.yaml")
    adj = data["adjacent_claims"]
    for key, val in adj.items():
        assert isinstance(val, dict), f"{key} should be a dict"
        assert "safe_phrases" in val, f"{key} missing safe_phrases"
        assert len(val["safe_phrases"]) > 0, f"{key} has empty safe_phrases"


# ── Claim verifier: adjacent topics detected ──────────────────────────────────

def test_adjacent_topic_python_detected():
    from jobos.agents.claim_verifier_agent import verify_answer
    answer = "I am building Python capability for investment workflow tools and data analysis."
    result = verify_answer(answer, {}, [])
    assert "Python experience" in result.adjacent_claims_detected


def test_adjacent_topic_quant_detected():
    from jobos.agents.claim_verifier_agent import verify_answer
    answer = "I am interested in quant research and systematic approaches to public markets."
    result = verify_answer(answer, {}, [])
    assert "Quant/systematic methods" in result.adjacent_claims_detected


def test_adjacent_topic_ml_detected():
    from jobos.agents.claim_verifier_agent import verify_answer
    answer = "I have growing interest in machine learning applications to investment research."
    result = verify_answer(answer, {}, [])
    assert "ML/data-science interest" in result.adjacent_claims_detected


# ── Claim verifier: adjacent ≠ forbidden ──────────────────────────────────────

def test_careful_python_framing_is_not_high_risk():
    from jobos.agents.claim_verifier_agent import verify_answer
    answer = "I am actively building Python capability for investment workflow automation."
    result = verify_answer(answer, {}, [])
    assert result.final_risk_level != "high"
    assert result.pass_check


def test_careful_quant_framing_is_not_high_risk():
    from jobos.agents.claim_verifier_agent import verify_answer
    answer = (
        "I have a strong econometric foundation from my Cambridge dissertation "
        "and growing systematic research interest."
    )
    result = verify_answer(answer, {}, [])
    assert result.final_risk_level != "high"
    assert result.pass_check


def test_careful_equity_framing_is_not_high_risk():
    from jobos.agents.claim_verifier_agent import verify_answer
    answer = (
        "I am a credit-trained public markets analyst moving closer to equity risk "
        "and alpha generation."
    )
    result = verify_answer(answer, {}, [])
    assert result.final_risk_level != "high"
    assert result.pass_check


# ── Claim verifier: overstated adjacent → high risk ───────────────────────────

def test_overstated_python_developer_is_high_risk():
    from jobos.agents.claim_verifier_agent import verify_answer
    answer = "I am a strong Python developer with significant data engineering experience."
    result = verify_answer(answer, {}, [])
    assert result.final_risk_level == "high"
    assert not result.pass_check


def test_systematic_trading_experience_claim_is_high_risk():
    from jobos.agents.claim_verifier_agent import verify_answer
    answer = "I have systematic trading experience and have built algorithmic trading strategies."
    result = verify_answer(answer, {}, [])
    assert result.final_risk_level == "high"
    assert not result.pass_check


def test_experienced_equity_analyst_claim_is_high_risk():
    from jobos.agents.claim_verifier_agent import verify_answer
    answer = "As an experienced equity analyst, I bring deep equity research expertise."
    result = verify_answer(answer, {}, [])
    assert result.final_risk_level == "high"
    assert not result.pass_check


# ── Claim verifier: recommended edits for adjacent topics ─────────────────────

def test_adjacent_topic_adds_framing_recommendation():
    from jobos.agents.claim_verifier_agent import verify_answer
    answer = "I am building Python capability and interested in backtesting systematic strategies."
    result = verify_answer(answer, {}, [])
    assert len(result.recommended_edits) > 0
    combined = " ".join(result.recommended_edits).lower()
    assert "python" in combined or "capability" in combined or "systematic" in combined


# ── Pipeline integration ──────────────────────────────────────────────────────

def test_pipeline_surfaces_adjacent_claims(tmp_path):
    from apply import build_pack
    job = tmp_path / "job.txt"
    job.write_text(
        "Company: Quant Fund\nRole: Systematic Analyst\n"
        "Python and quant research required. Equity and systematic strategies.",
        encoding="utf-8",
    )
    qs = tmp_path / "qs.txt"
    qs.write_text("Why are you interested in this role?", encoding="utf-8")
    pack = build_pack(job, qs)
    assert pack.cv_tailor is not None
    # Adjacent experience should be populated for quant/systematic JD
    assert len(pack.cv_tailor.adjacent_experience) > 0


def test_pipeline_adjacent_risks_surfaced_in_risks_to_review(tmp_path):
    from apply import build_pack
    job = tmp_path / "job.txt"
    job.write_text(
        "Company: Quant Fund\nRole: Analyst\n"
        "Python, machine learning and systematic strategies required.",
        encoding="utf-8",
    )
    qs = tmp_path / "qs.txt"
    qs.write_text("What Python experience do you have?", encoding="utf-8")
    pack = build_pack(job, qs)
    # Adjacent claims detected in answers should surface in risks_to_review
    combined = " ".join(pack.risks_to_review).lower()
    assert "adjacent" in combined


# ── CV tailor: adjacent section uses YAML safe_phrases ───────────────────────

def test_cv_tailor_uses_yaml_safe_phrases_for_python_jd():
    from jobos.agents.cv_tailor_agent import tailor_cv
    from jobos.schemas import ParsedJob, FitScore
    from jobos.io import load_yaml
    from jobos.config import DATA_DIR
    approved = load_yaml(DATA_DIR / "approved_claims.yaml")
    job = ParsedJob(company="Test Fund", role_title="Analyst", required_skills=["python", "data analysis"])
    fit = FitScore(overall_score=70, category="B", reason="ok", strengths=[], weaknesses=[],
                   application_strategy="Lead with analytical skills.", needs_referral=False)
    result = tailor_cv(job, fit, {}, approved)
    assert len(result.adjacent_experience) > 0
    # Should use a safe phrase from the YAML, not generic fallback
    combined = " ".join(result.adjacent_experience).lower()
    assert "python" in combined or "capability" in combined or "workflow" in combined
