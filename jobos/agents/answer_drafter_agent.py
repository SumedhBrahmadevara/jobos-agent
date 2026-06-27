from __future__ import annotations

from jobos.llm_client import structured_completion, LLMUnavailable
from jobos.schemas import ParsedJob, FitScore, DraftAnswer

SYSTEM_PROMPT = """You are the Answer Drafting Agent for JobOS.
Write concise, credible, finance/HF-quality application answers.
Rules:
- Use only approved claims or clearly label adjacent experience.
- Never invent experience.
- Never upgrade exposure into expertise.
- Avoid generic phrases like 'dynamic culture' unless backed by specifics.
- If a question asks for sensitive/legal information, mark it for human review.
- Keep answers sharp, direct and truthful.
- For adjacent/careful claims: use the safe_phrases provided — never upgrade them into expertise claims.
  Examples of correct framing:
    Python: 'building Python capability for workflow/data analysis' (NOT 'strong Python developer')
    Quant:  'econometric foundation and growing systematic research interest' (NOT 'professional quant researcher')
    Equity: 'credit-trained analyst moving closer to equity risk' (NOT 'experienced equity analyst')
    Systematic: 'growing interest and university-level exposure to backtesting' (NOT 'systematic trading experience')
"""


def _offline_answer(question: str, parsed_job: ParsedJob, fit_score: FitScore, approved_claims: dict) -> DraftAnswer:
    q = question.lower()
    if "why" in q and "role" in q:
        answer = (
            f"I am interested in this role because it sits at the intersection of fundamental company research, "
            f"financial modelling and public-markets judgement. My credit analyst background has trained me to analyse "
            f"cash-flow durability, downside risk, balance-sheet resilience and market pricing. For a role like {parsed_job.role_title}, "
            f"I would position that discipline closer to equity risk, alpha generation and differentiated investment debate."
        )
    elif "data" in q:
        answer = (
            "A good example is my Cambridge economics dissertation, where I used panel data, spatial econometrics and extensive "
            "data harmonisation to study housing affordability and gentrification. The project required turning messy geographic "
            "and economic data into a testable empirical framework, then interpreting the results carefully rather than treating "
            "the model output mechanically."
        )
    elif "python" in q or "coding" in q or "technical" in q:
        answer = (
            "I am actively building Python capability for investment workflow tools and data analysis. "
            "My Cambridge econometrics dissertation required working with MSOA-level geographic and economic data, "
            "and I have since been applying similar data-handling skills to automate research workflows. "
            "I frame this honestly as capability-building, not production engineering expertise."
        )
    elif "fit" in q or "strength" in q:
        answer = (
            "I bring a credit-trained investment lens: fundamental research, financial modelling, earnings analysis, management "
            "commentary analysis and a strong focus on downside risk. That gives me a differentiated way to assess public companies, "
            "especially where balance-sheet strength, cash-flow durability and market-implied expectations matter."
        )
    else:
        answer = (
            "My background combines public-markets credit analysis, financial modelling, consumer-sector research and econometric training. "
            "I would aim to bring rigorous fundamental judgement, clear communication and intellectual curiosity to this application."
        )

    return DraftAnswer(
        question=question,
        answer=answer,
        word_count=len(answer.split()),
        claims_used=["credit analyst background", "financial modelling", "Cambridge econometrics dissertation"],
        confidence="medium",
        needs_human_review=True,
        review_reason="Offline draft: review tone, firm-specific detail and any factual claims before use.",
    )


def draft_answer(
    *,
    question: str,
    parsed_job: ParsedJob,
    fit_score: FitScore,
    profile: dict,
    approved_claims: dict,
    answer_bank: dict,
    adjacent_claims: dict | None = None,
    word_limit: int | None = None,
) -> DraftAnswer:
    adjacent_section = ""
    if adjacent_claims:
        adjacent_section = f"\nAdjacent/careful claims (use safe_phrases only — never upgrade to expertise):\n{adjacent_claims}"

    user_prompt = f"""
Question:
{question}

Word limit:
{word_limit or 'No explicit limit'}

Parsed job:
{parsed_job.model_dump_json(indent=2)}

Fit score and strategy:
{fit_score.model_dump_json(indent=2)}

Profile:
{profile}

Approved claims:
{approved_claims}

Answer bank:
{answer_bank}
{adjacent_section}
"""
    try:
        return structured_completion(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_model=DraftAnswer,
            schema_name="draft_answer",
        )
    except LLMUnavailable:
        return _offline_answer(question, parsed_job, fit_score, approved_claims)
