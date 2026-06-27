from __future__ import annotations

from jobos.llm_client import structured_completion, LLMUnavailable
from jobos.schemas import ParsedJob, FitScore

SYSTEM_PROMPT = """You are the Fit Scoring Agent for JobOS.
Score whether the user should apply to this role.
Use the user's profile and the parsed job.
Prioritise role quality, fit, truthfulness, and reputation.
Do not encourage mass-applying.
Categories:
A = apply carefully, tailor CV, try referral.
B = apply with moderate tailoring.
C = save/watch, but not a priority.
reject = do not apply.
"""


def _offline_score(parsed_job: ParsedJob, profile: dict) -> FitScore:
    text = " ".join(parsed_job.required_skills + parsed_job.preferred_skills + parsed_job.responsibilities).lower()
    score = 55
    strengths: list[str] = []
    weaknesses: list[str] = []

    if "public markets" in text or "investment" in text:
        score += 10
        strengths.append("Public markets overlap with current credit analyst work.")
    if "financial" in text or "model" in text or "modelling" in text:
        score += 10
        strengths.append("Financial modelling and fundamental analysis overlap.")
    if "consumer" in parsed_job.role_title.lower() or "consumer" in text:
        score += 10
        strengths.append("Consumer sector coverage is directly relevant.")
    if "python" in text or "machine learning" in text:
        weaknesses.append("Python/data requirements need honest positioning.")
        score -= 5
    if "equity" in parsed_job.role_title.lower() or "equity" in text:
        weaknesses.append("May need to explain transition from credit to equity.")

    if score >= 80:
        category = "A"
    elif score >= 65:
        category = "B"
    elif score >= 45:
        category = "C"
    else:
        category = "reject"

    return FitScore(
        overall_score=max(0, min(100, score)),
        category=category,  # type: ignore[arg-type]
        reason="Offline heuristic score based on overlap with public markets, modelling, sector coverage and data requirements.",
        strengths=strengths or ["Some analytical overlap with the user's profile."],
        weaknesses=weaknesses or ["No major weakness identified from heuristic parser."],
        application_strategy="Position as a credit-trained public markets analyst with strong downside-risk, modelling and sector-research discipline.",
        needs_referral=category in {"A", "B"},
    )


def score_fit(parsed_job: ParsedJob, profile: dict) -> FitScore:
    user_prompt = f"""
User profile:
{profile}

Parsed job:
{parsed_job.model_dump_json(indent=2)}
"""
    try:
        return structured_completion(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_model=FitScore,
            schema_name="fit_score",
        )
    except LLMUnavailable:
        return _offline_score(parsed_job, profile)
