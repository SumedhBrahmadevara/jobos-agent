from __future__ import annotations

import re

from jobos.llm_client import structured_completion, LLMUnavailable
from jobos.schemas import ParsedJob

SYSTEM_PROMPT = """You are the Job Parser Agent for JobOS.
Your job is to convert a messy job description into structured data.
Do not assess the candidate yet. Extract requirements faithfully.
If information is missing, use null or 'unknown'.
Return only the requested structured output.
"""


def _offline_parse(job_description: str) -> ParsedJob:
    company = "Unknown"
    role = "Unknown"
    location = None

    company_match = re.search(r"Company:\s*(.+)", job_description, re.I)
    role_match = re.search(r"Role:\s*(.+)", job_description, re.I)
    location_match = re.search(r"Location:\s*(.+)", job_description, re.I)

    if company_match:
        company = company_match.group(1).strip()
    if role_match:
        role = role_match.group(1).strip()
    if location_match:
        location = location_match.group(1).strip()

    text = job_description.lower()
    responsibilities = []
    for keyword in ["research", "model", "earnings", "management commentary", "investment views", "recommendations"]:
        if keyword in text:
            responsibilities.append(f"Likely involves {keyword}.")

    required_skills = []
    for keyword in ["public markets", "modelling", "written communication", "financial models", "analytical"]:
        if keyword in text:
            required_skills.append(keyword)

    preferred_skills = []
    for keyword in ["python", "data analysis", "credit experience", "equity experience"]:
        if keyword in text:
            preferred_skills.append(keyword)

    red_flags = []
    if "direct equity" in text:
        red_flags.append("May prefer direct equity experience.")
    if "python" in text:
        red_flags.append("Python/data skills may need careful, honest framing.")

    return ParsedJob(
        company=company,
        role_title=role,
        location=location,
        platform=None,
        responsibilities=responsibilities,
        required_skills=required_skills,
        preferred_skills=preferred_skills,
        seniority_level="early-career or unknown",
        target_profile="public markets investment analyst",
        red_flags=red_flags,
    )


def parse_job(job_description: str) -> ParsedJob:
    user_prompt = f"Parse this job description:\n\n{job_description}"
    try:
        return structured_completion(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_model=ParsedJob,
            schema_name="parsed_job",
        )
    except LLMUnavailable:
        return _offline_parse(job_description)
