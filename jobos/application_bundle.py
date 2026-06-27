"""Application Bundle Generator — produces upload-ready documents from an ApplicationPack."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from jobos.io import write_json, write_text
from jobos.schemas import ApplicationPack
from jobos.agents.claim_verifier_agent import verify_answer
from jobos.document_generator import generate_documents


class BundleResult(BaseModel):
    out_dir: str
    tailored_cv_path: str
    cover_letter_path: str
    answers_path: str
    pack_json_path: str
    pack_md_path: str
    high_risk_warnings: list[str] = Field(default_factory=list)
    adjacent_claims_flagged: list[str] = Field(default_factory=list)


def _risk_emoji(risk: str) -> str:
    return {"low": "✅", "medium": "⚠️", "high": "🚨"}.get(risk, "❓")


def _build_application_answers_md(
    pack: ApplicationPack,
    approved_claims: dict,
    forbidden_claims: list[str],
    adjacent_claims: dict,
    date_str: str,
) -> str:
    """Generate Q&A document with per-answer claim-check status."""
    job = pack.parsed_job
    lines = [
        f"# Application Answers — {job.company}: {job.role_title}",
        "",
        f"**Generated:** {date_str}",
        f"**Fit score:** {pack.fit_score.overall_score}/100 ({pack.fit_score.category})",
        "",
        "> All answers require human review before submission.",
        "> Answers marked ⚠️ or 🚨 must be edited to resolve claim issues.",
        "",
        "---",
        "",
    ]

    if not pack.answers:
        lines += [
            "No application questions were provided.",
            "",
            "*Add questions and regenerate to see answers here.*",
        ]
        return "\n".join(lines)

    for i, ans in enumerate(pack.answers, 1):
        vr = verify_answer(ans.answer, approved_claims, forbidden_claims, adjacent_claims=adjacent_claims)
        risk_emoji = _risk_emoji(vr.final_risk_level)
        review_flag = "⚠️ **HUMAN REVIEW REQUIRED**" if ans.needs_human_review else "✅ Draft ready for review"

        lines += [
            f"## Q{i}: {ans.question}",
            "",
            ans.answer,
            "",
            f"**Claim check:** {risk_emoji} {vr.final_risk_level} risk "
            f"| **Confidence:** {ans.confidence} | {review_flag}",
            "",
        ]

        if ans.review_reason:
            lines += [f"> {ans.review_reason}", ""]

        issues: list[str] = []
        if vr.unsupported_claims:
            issues.append("🚨 **Unsupported:** " + ", ".join(f"`{c}`" for c in vr.unsupported_claims))
        if vr.exaggerated_claims:
            issues.append("🚨 **Forbidden / exaggerated:** " + ", ".join(f"`{c}`" for c in vr.exaggerated_claims))
        if vr.generic_phrases:
            issues.append("⚠️ **Generic phrases:** " + ", ".join(f"`{p}`" for p in vr.generic_phrases))
        if vr.adjacent_claims_detected:
            issues.append(
                "🟡 **Adjacent — review framing:** "
                + ", ".join(f"`{t}`" for t in vr.adjacent_claims_detected)
            )
        if issues:
            lines += issues + [""]

        if vr.recommended_edits:
            lines += ["**Framing guidance:**"]
            for edit in vr.recommended_edits:
                lines.append(f"- {edit}")
            lines.append("")

        lines += ["---", ""]

    return "\n".join(lines)


def _build_pack_md(pack: ApplicationPack, date_str: str) -> str:
    """Generate full application_pack.md summary."""
    ct = pack.cv_tailor
    job = pack.parsed_job
    fit = pack.fit_score

    lines = [
        f"# Application Pack: {job.company} — {job.role_title}",
        "",
        f"**Generated:** {date_str}",
        f"**Fit:** {fit.overall_score}/100 ({fit.category})",
        "",
        "## Strategy",
        fit.application_strategy,
        "",
        "## CV Tailoring Suggestions",
        f"**Positioning:** {ct.positioning_angle}",
        "",
        "### CV Summary Draft",
        "> " + ct.cv_summary_draft,
        "",
        *(
            [
                f"⚠️ **CV Summary Claim Warning ({ct.cv_summary_verification.final_risk_level} risk)** — review before using.",
                *([f"- Unsupported: {', '.join(ct.cv_summary_verification.unsupported_claims)}"] if ct.cv_summary_verification.unsupported_claims else []),
                *([f"- Exaggerated: {', '.join(ct.cv_summary_verification.exaggerated_claims)}"] if ct.cv_summary_verification.exaggerated_claims else []),
                "",
            ]
            if ct.cv_summary_verification and ct.cv_summary_verification.final_risk_level != "low"
            else []
        ),
        "### Bullets to Emphasise",
        *[f"- {x}" for x in ct.bullets_to_emphasise],
        "",
        "### Bullets to De-emphasise",
        *[f"- {x}" for x in ct.bullets_to_de_emphasise],
        "",
        "### Suggested Skill Order",
        *[f"- {x}" for x in ct.reordered_skills],
        "",
        "### Approved Claims — Use Verbatim",
        *[f"- {x}" for x in ct.approved_claims_usable],
        "",
        "### Adjacent / Careful Claims — Use Only With This Wording",
        "> These are true but require careful framing. Use the exact phrasing below.",
        *[f"- {x}" for x in ct.adjacent_experience],
        "",
        "### Do NOT Claim",
        *[f"- {x}" for x in ct.unsupported_claims],
        "",
        "## Strengths",
        *[f"- {x}" for x in fit.strengths],
        "",
        "## Weaknesses / Review Points",
        *[f"- {x}" for x in (pack.risks_to_review or fit.weaknesses)],
        "",
        "## Answers",
    ]
    for ans in pack.answers:
        lines.extend([
            "",
            f"### {ans.question}",
            ans.answer,
            "",
            f"Confidence: {ans.confidence}; Human review: {ans.needs_human_review}; Reason: {ans.review_reason or 'n/a'}",
        ])

    return "\n".join(lines)


def generate_bundle(
    pack: ApplicationPack,
    out_dir: Path,
    profile: dict,
    adjacent_claims: dict,
    approved_claims_full: dict | None = None,
) -> BundleResult:
    """Write all bundle files to out_dir and return paths and warnings.

    tailored_cv.md and cover_letter.md are rendered by the template-locked
    document_generator.  The remaining files (answers, json, md summary) are
    built here from the ApplicationPack directly.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%d %B %Y")

    approved_dict: dict = {}
    forbidden_list: list[str] = []
    if approved_claims_full:
        approved_dict = approved_claims_full.get("approved_claims", {})
        raw_forbidden = approved_claims_full.get("forbidden_claims", [])
        forbidden_list = raw_forbidden if isinstance(raw_forbidden, list) else []

    # ── tailored_cv.md + cover_letter.md (template-locked) ───────────────────
    cv_content, high_risk_warnings, cl_content = generate_documents(
        pack, profile, adjacent_claims,
        approved_claims_full=approved_claims_full,
        date_str=date_str,
    )
    cv_path = out_dir / "tailored_cv.md"
    write_text(cv_path, cv_content)

    cl_path = out_dir / "cover_letter.md"
    write_text(cl_path, cl_content)

    # ── application_answers.md ────────────────────────────────────────────────
    ans_content = _build_application_answers_md(
        pack, approved_dict, forbidden_list, adjacent_claims, date_str
    )
    ans_path = out_dir / "application_answers.md"
    write_text(ans_path, ans_content)

    # ── application_pack.json ─────────────────────────────────────────────────
    json_path = out_dir / "application_pack.json"
    write_json(json_path, pack.model_dump())

    # ── application_pack.md ───────────────────────────────────────────────────
    md_path = out_dir / "application_pack.md"
    write_text(md_path, _build_pack_md(pack, date_str))

    adjacent_flagged = [r for r in pack.risks_to_review if r.startswith("Adjacent claim detected:")]

    return BundleResult(
        out_dir=str(out_dir),
        tailored_cv_path=str(cv_path),
        cover_letter_path=str(cl_path),
        answers_path=str(ans_path),
        pack_json_path=str(json_path),
        pack_md_path=str(md_path),
        high_risk_warnings=high_risk_warnings,
        adjacent_claims_flagged=adjacent_flagged,
    )
