from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class ParsedJob(BaseModel):
    company: str = Field(description="Company name if available, otherwise 'Unknown'.")
    role_title: str = Field(description="Role title if available, otherwise 'Unknown'.")
    location: str | None = None
    platform: str | None = Field(default=None, description="Application platform if known, e.g. Greenhouse, Lever, Workday, Ashby.")
    responsibilities: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    seniority_level: str = Field(default="unknown")
    target_profile: str = Field(default="unknown")
    red_flags: list[str] = Field(default_factory=list)


class FitScore(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    category: Literal["A", "B", "C", "reject"]
    reason: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    application_strategy: str
    needs_referral: bool


class DraftAnswer(BaseModel):
    question: str
    answer: str
    word_count: int
    claims_used: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    needs_human_review: bool
    review_reason: str | None = None


class ApplicationPack(BaseModel):
    parsed_job: ParsedJob
    fit_score: FitScore
    answers: list[DraftAnswer]
    cv_angle: str
    cover_letter_outline: list[str]
    risks_to_review: list[str] = Field(default_factory=list)


class ClaimCheck(BaseModel):
    claim: str
    status: Literal["approved", "unsupported", "misleading", "needs_review"]
    approved_rewrite: str | None = None
    reason: str


class VerificationResult(BaseModel):
    pass_check: bool
    unsupported_claims: list[str] = Field(default_factory=list)
    exaggerated_claims: list[str] = Field(default_factory=list)
    generic_phrases: list[str] = Field(default_factory=list)
    recommended_edits: list[str] = Field(default_factory=list)
    final_risk_level: Literal["low", "medium", "high"]


class FieldRisk(BaseModel):
    field_label: str
    field_type: str
    risk_level: Literal["green", "amber", "red"]
    suggested_value: str | None = None
    requires_manual_approval: bool
    reason: str


class TrackerRecord(BaseModel):
    company: str
    role_title: str
    job_url: str | None = None
    platform: str | None = None
    fit_score: int
    category: Literal["A", "B", "C", "reject"]
    status: str = "drafted"
    cv_version: str | None = None
    cover_letter_version: str | None = None
    notes: str | None = None
