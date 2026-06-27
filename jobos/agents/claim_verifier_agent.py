from __future__ import annotations

from jobos.llm_client import structured_completion, LLMUnavailable
from jobos.schemas import VerificationResult

SYSTEM_PROMPT = """You are the Claim Verification Agent for JobOS.
Your job is to protect the user's reputation.
Check application answers against approved claims and forbidden claims.
Flag unsupported, exaggerated, misleading, overly generic or sensitive content.
Do not rewrite the whole answer unless needed; return verification metadata.
"""

GENERIC_PHRASES = [
    "dynamic culture",
    "fast-paced environment",
    "commitment to excellence",
    "passionate about finance",
    "unique opportunity",
]


def _offline_verify(answer: str, approved_claims: dict, forbidden_claims: dict) -> VerificationResult:
    lower = answer.lower()
    unsupported: list[str] = []
    exaggerated: list[str] = []
    generic = [phrase for phrase in GENERIC_PHRASES if phrase in lower]

    for claim in forbidden_claims.get("forbidden_claims", []):
        if claim.lower() in lower:
            exaggerated.append(claim)

    risky_terms = ["expert", "advanced python", "machine learning engineer", "production"]
    for term in risky_terms:
        if term in lower:
            unsupported.append(term)

    risk = "low"
    if unsupported or exaggerated:
        risk = "high"
    elif generic:
        risk = "medium"

    return VerificationResult(
        pass_check=risk != "high",
        unsupported_claims=unsupported,
        exaggerated_claims=exaggerated,
        generic_phrases=generic,
        recommended_edits=["Add firm-specific detail."] if generic else [],
        final_risk_level=risk,  # type: ignore[arg-type]
    )


def verify_answer(answer: str, approved_claims: dict, forbidden_claims: dict) -> VerificationResult:
    user_prompt = f"""
Answer to verify:
{answer}

Approved claims:
{approved_claims}

Forbidden claims:
{forbidden_claims}
"""
    try:
        return structured_completion(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_model=VerificationResult,
            schema_name="verification_result",
        )
    except LLMUnavailable:
        return _offline_verify(answer, approved_claims, forbidden_claims)
