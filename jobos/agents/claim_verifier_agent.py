from __future__ import annotations

from jobos.llm_client import structured_completion, LLMUnavailable
from jobos.schemas import VerificationResult

SYSTEM_PROMPT = """You are the Claim Verification Agent for JobOS.
Your job is to protect the user's reputation.
Check application answers against approved claims, adjacent/careful claims, and forbidden claims.

Classify each issue found:
- FORBIDDEN / EXAGGERATED: claims on the explicit forbidden list, or claims that overstate experience into
  expertise the user does not have (e.g. "advanced Python developer", "professional quant researcher").
- ADJACENT OVERSTATEMENT: converts adjacent/careful experience into claimed expertise
  (e.g. "strong Python developer", "systematic trading experience") — flag as high risk.
- ADJACENT DETECTED: adjacent topics mentioned but framed carefully — note for review, do not fail.
- UNSUPPORTED: risky terms that imply expertise not in the profile (e.g. "expert", "production").
- GENERIC: empty filler phrases that weaken the answer.

Do not rewrite the whole answer unless needed; return verification metadata.
"""

GENERIC_PHRASES = [
    "dynamic culture",
    "fast-paced environment",
    "commitment to excellence",
    "passionate about finance",
    "unique opportunity",
]

# Phrases that convert adjacent experience into claimed expertise → high risk.
# These are distinct from the explicit forbidden_claims list and catch soft exaggeration.
_ADJACENT_OVERSTATEMENT_HIGH: list[tuple[str, str]] = [
    ("strong python developer", "Do not claim 'strong Python developer' — frame as 'building Python capability'."),
    ("proficient python developer", "Do not claim 'proficient Python developer' — frame as 'building Python capability'."),
    ("experienced python developer", "Do not claim 'experienced Python developer' — frame as 'building Python capability'."),
    ("skilled python developer", "Do not claim 'skilled Python developer' — frame as 'building Python capability'."),
    ("systematic trading experience", "Do not claim systematic trading experience — frame as 'growing interest and university-level exposure'."),
    ("algorithmic trading experience", "Do not claim algorithmic trading experience — frame as 'growing systematic research interest'."),
    ("quant trading experience", "Do not claim quant trading experience — frame as 'econometric foundation and growing systematic interest'."),
    ("experienced equity analyst", "Do not claim 'experienced equity analyst' — frame as 'credit-trained analyst moving toward equity risk'."),
    ("equity analyst background", "Do not claim equity analyst background — frame as 'credit-trained public markets analyst'."),
]

# Adjacent topics: detected when present, flagged for careful framing (no risk increase on their own).
_ADJACENT_TOPIC_RULES: list[tuple[str, list[str], str]] = [
    (
        "Python experience",
        ["python"],
        "Python mentioned — ensure framing uses 'building capability for workflow/data analysis', not established expertise.",
    ),
    (
        "ML/data-science interest",
        ["machine learning", "deep learning"],
        "ML mentioned — ensure framing uses 'interest in data-driven methods', not 'professional ML engineer'.",
    ),
    (
        "Quant/systematic methods",
        ["quant research", "systematic strategy", "quantitative research", "backtesting"],
        "Quant/systematic methods mentioned — frame as 'econometric foundation and growing interest', not production experience.",
    ),
    (
        "Equity investing",
        ["equity analyst", "equity research role", "equity investing"],
        "Equity analyst framing detected — frame as 'credit-trained moving toward equity risk', not direct analyst experience.",
    ),
]


def _offline_verify(
    answer: str,
    approved_claims: dict,
    forbidden_claims: dict | list,
    adjacent_claims: dict | None = None,
) -> VerificationResult:
    lower = answer.lower()
    unsupported: list[str] = []
    exaggerated: list[str] = []
    adjacent_detected: list[str] = []
    generic = [phrase for phrase in GENERIC_PHRASES if phrase in lower]
    recommended: list[str] = []

    # ── Forbidden / exaggerated claims ────────────────────────────────────────
    # Accept either the raw list or the full YAML dict (legacy call-site).
    _forbidden_list: list = (
        forbidden_claims if isinstance(forbidden_claims, list)
        else forbidden_claims.get("forbidden_claims", [])
    )
    for claim in _forbidden_list:
        if claim.lower() in lower:
            exaggerated.append(claim)

    # ── Risky terms (unsupported expertise language) ──────────────────────────
    risky_terms = ["expert", "advanced python", "machine learning engineer", "production"]
    for term in risky_terms:
        if term in lower:
            unsupported.append(term)

    # ── Adjacent overstatement: converts adjacent experience into claimed expertise ──
    for phrase, note in _ADJACENT_OVERSTATEMENT_HIGH:
        if phrase in lower:
            exaggerated.append(f"Adjacent overstatement: '{phrase}'")
            if note not in recommended:
                recommended.append(note)

    # ── Adjacent topic detection: present but not necessarily overstated ──────
    for topic_label, triggers, framing_note in _ADJACENT_TOPIC_RULES:
        if any(kw in lower for kw in triggers):
            adjacent_detected.append(topic_label)
            if framing_note not in recommended:
                recommended.append(framing_note)

    # ── Generic phrases ───────────────────────────────────────────────────────
    if generic:
        recommended.append("Add firm-specific detail instead of generic filler.")

    # ── Final risk ────────────────────────────────────────────────────────────
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
        adjacent_claims_detected=adjacent_detected,
        recommended_edits=recommended,
        final_risk_level=risk,  # type: ignore[arg-type]
    )


def verify_answer(
    answer: str,
    approved_claims: dict,
    forbidden_claims: dict | list,
    adjacent_claims: dict | None = None,
) -> VerificationResult:
    adjacent_section = ""
    if adjacent_claims:
        adjacent_section = f"\nAdjacent/careful claims (use only with careful framing):\n{adjacent_claims}"

    user_prompt = f"""
Answer to verify:
{answer}

Approved claims:
{approved_claims}

Forbidden claims:
{forbidden_claims}
{adjacent_section}
"""
    try:
        return structured_completion(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_model=VerificationResult,
            schema_name="verification_result",
        )
    except LLMUnavailable:
        return _offline_verify(answer, approved_claims, forbidden_claims, adjacent_claims)
