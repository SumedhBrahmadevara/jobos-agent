from __future__ import annotations

from jobos.llm_client import structured_completion, LLMUnavailable
from jobos.schemas import ParsedJob, FitScore, CVTailorSuggestions

SYSTEM_PROMPT = """You are the CV Tailoring Agent for JobOS.
Generate safe, truthful, role-specific CV tailoring suggestions.

Rules:
- Use only claims from the user's approved claims list. Label everything else explicitly.
- Never invent experience. Never upgrade exposure into expertise.
- Distinguish three tiers clearly:
  (1) approved_claims_usable: claims the user can include verbatim.
  (2) adjacent_experience: real experience that needs careful framing — not overstated.
  (3) unsupported_claims: statements the user must NOT make on this CV.
- The cv_summary_draft must be factually accurate. Do not add claims not in the profile.
- All suggestions must be actionable and specific to the role.
- Do not reference or modify actual CV files — output text suggestions only.
"""

# Keyword → emphasis bullet mapping used by the offline fallback.
_EMPHASIS_MAP: list[tuple[str, str]] = [
    ("public markets", "Fundamental research across 60+ consumer-sector issuers (equity-style modelling depth)."),
    ("financial modelling", "Forward-looking financial models: revenue, FCF, leverage and maturity profiles."),
    ("investment", "Investment views and trade recommendations supported by deep fundamental analysis."),
    ("earnings", "Systematic earnings analysis and management commentary tracking across 300+ monitored issuers."),
    ("consumer", "Deep consumer-sector coverage: retail, F&B, leisure, travel and business services."),
    ("credit", "Credit risk analysis: downside scenarios, covenant review, liquidity and refinancing risk."),
    ("research", "Company research: business model analysis, competitive positioning and sector dynamics."),
    ("modelling", "Financial modelling covering revenue drivers, margins, cash flow and capital structure."),
    ("communication", "Clear written communication: investment notes, trade ideas and research summaries."),
    ("data", "Quantitative analysis: panel data, spatial econometrics and data harmonisation (Cambridge dissertation)."),
    ("analytical", "Rigorous analytical approach applied to complex multi-factor investment situations."),
]

_SKILL_PRIORITY: list[tuple[str, str]] = [
    ("public markets", "Fundamental credit/equity research"),
    ("modelling", "Financial modelling"),
    ("earnings", "Earnings analysis"),
    ("investment", "Relative value and investment views"),
    ("bond", "Bond valuation and new-issue pricing"),
    ("cash", "Cash-flow and balance-sheet analysis"),
    ("downside", "Downside risk analysis"),
    ("communication", "Written communication and research presentation"),
    ("data", "Quantitative methods and data analysis"),
    ("python", "Python (building capability — frame carefully)"),
]


def _offline_tailor(
    parsed_job: ParsedJob,
    fit_score: FitScore,
    profile: dict,
    approved_claims: dict,
) -> CVTailorSuggestions:
    all_jd = " ".join([
        parsed_job.role_title,
        *parsed_job.required_skills,
        *parsed_job.preferred_skills,
        *parsed_job.responsibilities,
    ]).lower()
    role_lower = parsed_job.role_title.lower()

    # ── Positioning angle ────────────────────────────────────────────────────
    positioning_angle = fit_score.application_strategy or (
        f"Position as a fundamentals-driven analyst suited to {parsed_job.role_title}."
    )

    # ── Bullets to emphasise ─────────────────────────────────────────────────
    bullets_to_emphasise = [b for kw, b in _EMPHASIS_MAP if kw in all_jd]
    if not bullets_to_emphasise:
        bullets_to_emphasise = ["Lead with financial modelling and fundamental analysis experience."]

    # ── Bullets to de-emphasise ──────────────────────────────────────────────
    bullets_to_de_emphasise: list[str] = []
    if any(kw in all_jd for kw in ["python", "data science", "machine learning", "quant"]):
        bullets_to_de_emphasise.append(
            "Avoid leading with Python/data-science framing — use 'building capability' "
            "language, never 'expert' or 'production'."
        )
    if "equity" in role_lower or "equity" in all_jd:
        bullets_to_de_emphasise.append(
            "Reframe credit-specific language: avoid 'bond' and 'fixed income' as leads; "
            "emphasise public-markets investment-discipline transferability instead."
        )
    if not bullets_to_de_emphasise:
        bullets_to_de_emphasise = ["Keep the CV focused on skills directly relevant to this role."]

    # ── Reordered skills ─────────────────────────────────────────────────────
    reordered_skills = [skill for kw, skill in _SKILL_PRIORITY if kw in all_jd]
    if not reordered_skills:
        current_skills: list[str] = profile.get("current_role", {}).get("skills", [])
        reordered_skills = current_skills[:6] if current_skills else [
            "Fundamental research", "Financial modelling", "Analytical communication",
        ]

    # ── CV summary draft ─────────────────────────────────────────────────────
    current_role = profile.get("current_role", {})
    employer = current_role.get("employer", "current employer")
    title = current_role.get("title", "analyst")
    edu = profile.get("education", {})
    university = edu.get("university", "")
    prize = edu.get("dissertation", {}).get("prize", "")

    edu_line = ""
    if university and prize:
        edu_line = f" {university} graduate ({prize})."
    elif university:
        edu_line = f" {university} graduate."

    cv_summary_draft = (
        f"{title.capitalize()} at {employer} with deep fundamental research and financial "
        f"modelling experience across public-markets credit and consumer-sector issuers.{edu_line} "
        f"Applying for {parsed_job.role_title} at {parsed_job.company}: {positioning_angle}"
    )

    # ── Approved claims usable for this role ─────────────────────────────────
    claims_section = approved_claims.get("approved_claims", {}) if approved_claims else {}
    role_keywords = {
        "public markets", "credit", "equity", "investment",
        "hedge fund", "quant", "fixed income", "systematic",
    }
    approved_claims_usable: list[str] = []
    if isinstance(claims_section, dict):
        for val in claims_section.values():
            if not isinstance(val, dict):
                continue
            claim_text: str = val.get("claim", "")
            contexts: str = " ".join(val.get("contexts", [])).lower()
            if not claim_text:
                continue
            if any(kw in all_jd or kw in contexts for kw in role_keywords):
                approved_claims_usable.append(claim_text)
    if not approved_claims_usable:
        approved_claims_usable = ["Use only claims explicitly listed in approved_claims.yaml without modification."]

    # ── Adjacent experience — must be framed carefully ───────────────────────
    adjacent_experience: list[str] = []
    if "python" in all_jd or "data" in all_jd:
        adjacent_experience.append(
            "Python/data: frame as 'actively building capability for investment workflows' — "
            "reference Cambridge econometrics dissertation, not production engineering."
        )
    if "equity" in role_lower or "equity" in all_jd:
        adjacent_experience.append(
            "Credit-to-equity: frame bond analysis as training in equity risk (downside, "
            "capital allocation, market-implied expectations) — not a separate track."
        )
    if "systematic" in all_jd or "quant" in all_jd:
        adjacent_experience.append(
            "Quant/systematic: reference dissertation panel data and econometrics as evidence "
            "of quantitative aptitude — do not claim professional systematic trading experience."
        )
    if not adjacent_experience:
        adjacent_experience = [
            "Frame all cross-disciplinary experience as additive context, not a primary qualification."
        ]

    # ── Unsupported claims — must NOT appear on CV ───────────────────────────
    forbidden: list = approved_claims.get("forbidden_claims", []) if approved_claims else []
    if isinstance(forbidden, list) and forbidden:
        unsupported_claims = [f"Do not claim: \"{c}\"" for c in forbidden]
    else:
        unsupported_claims = [
            "Do not claim Python production engineering experience.",
            "Do not claim direct equity analyst experience unless evidenced.",
            "Do not claim institutional-grade systematic trading model experience.",
        ]

    # ── Risks and gaps ───────────────────────────────────────────────────────
    risks_and_gaps: list[str] = list(fit_score.weaknesses) + list(parsed_job.red_flags)
    if not risks_and_gaps:
        risks_and_gaps = ["No major skill gaps detected from offline analysis — review manually."]

    return CVTailorSuggestions(
        positioning_angle=positioning_angle,
        cv_summary_draft=cv_summary_draft,
        bullets_to_emphasise=bullets_to_emphasise,
        bullets_to_de_emphasise=bullets_to_de_emphasise,
        reordered_skills=reordered_skills,
        risks_and_gaps=risks_and_gaps,
        approved_claims_usable=approved_claims_usable,
        adjacent_experience=adjacent_experience,
        unsupported_claims=unsupported_claims,
    )


def tailor_cv(
    parsed_job: ParsedJob,
    fit_score: FitScore,
    profile: dict,
    approved_claims: dict,
) -> CVTailorSuggestions:
    user_prompt = f"""
Parsed job:
{parsed_job.model_dump_json(indent=2)}

Fit score and strategy:
{fit_score.model_dump_json(indent=2)}

User profile:
{profile}

Approved and forbidden claims:
{approved_claims}
"""
    try:
        return structured_completion(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_model=CVTailorSuggestions,
            schema_name="cv_tailor_suggestions",
        )
    except LLMUnavailable:
        return _offline_tailor(parsed_job, fit_score, profile, approved_claims)
