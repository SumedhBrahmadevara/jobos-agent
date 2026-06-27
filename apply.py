from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from jobos.config import DATA_DIR, APPLICATIONS_DIR, ensure_dirs
from jobos.llm_client import llm_is_available
from jobos.io import load_yaml, read_text, write_json, write_text
from jobos.schemas import ApplicationPack, TrackerRecord
from jobos.tracker import save_application
from jobos.agents.job_parser_agent import parse_job
from jobos.agents.fit_scorer_agent import score_fit
from jobos.agents.answer_drafter_agent import draft_answer
from jobos.agents.claim_verifier_agent import verify_answer
from jobos.agents.cv_tailor_agent import tailor_cv

app = typer.Typer(help="JobOS Application Agent MVP")
console = Console()


def build_pack(job_file: Path, questions_file: Path | None) -> ApplicationPack:
    ensure_dirs()
    profile = load_yaml(DATA_DIR / "profile.yaml")
    approved = load_yaml(DATA_DIR / "approved_claims.yaml")
    answer_bank = load_yaml(DATA_DIR / "answer_bank.yaml")
    job_description = read_text(job_file)
    questions = []
    if questions_file and questions_file.exists():
        questions = [q.strip() for q in read_text(questions_file).splitlines() if q.strip()]

    parsed = parse_job(job_description)
    fit = score_fit(parsed, profile)
    cv_tailor = tailor_cv(parsed, fit, profile, approved)

    answers = []
    risks = list(parsed.red_flags)
    for question in questions:
        draft = draft_answer(
            question=question,
            parsed_job=parsed,
            fit_score=fit,
            profile=profile,
            approved_claims=approved,
            answer_bank=answer_bank,
        )
        verification = verify_answer(draft.answer, approved, approved)
        if verification.final_risk_level != "low":
            draft.needs_human_review = True
            draft.review_reason = draft.review_reason or "Claim verifier flagged this answer."
            risks.extend(verification.unsupported_claims)
            risks.extend(verification.exaggerated_claims)
            risks.extend(verification.generic_phrases)
        answers.append(draft)

    cv_angle = fit.application_strategy
    cover_letter_outline = [
        "Open with public-markets/investment motivation, not generic enthusiasm.",
        "Bridge credit experience to the specific role requirements.",
        "Use one data/econometrics proof point if relevant.",
        "Close with a direct statement of fit and learning velocity.",
    ]

    return ApplicationPack(
        parsed_job=parsed,
        fit_score=fit,
        answers=answers,
        cv_angle=cv_angle,
        cover_letter_outline=cover_letter_outline,
        cv_tailor=cv_tailor,
        risks_to_review=sorted(set(risks)),
    )


@app.command()
def run(
    job_file: Path = typer.Option(DATA_DIR / "sample_job.txt", help="Path to job description text file."),
    questions_file: Path = typer.Option(DATA_DIR / "sample_questions.txt", help="Path to application questions text file."),
    save_tracker: bool = typer.Option(True, help="Save a tracker record to SQLite."),
):
    """Generate a safe application pack from a job description."""
    mode = "LLM mode" if llm_is_available() else "offline demo mode"
    console.print(Panel(f"Running JobOS in [bold]{mode}[/bold]."))

    pack = build_pack(job_file, questions_file)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = f"{pack.parsed_job.company}_{pack.parsed_job.role_title}".replace(" ", "_").replace("/", "-")
    out_dir = APPLICATIONS_DIR / f"{timestamp}_{slug}"
    out_dir.mkdir(parents=True, exist_ok=True)

    write_json(out_dir / "application_pack.json", pack.model_dump())

    ct = pack.cv_tailor
    md = [
        f"# Application Pack: {pack.parsed_job.company} — {pack.parsed_job.role_title}",
        "",
        f"Fit: **{pack.fit_score.overall_score}/100 ({pack.fit_score.category})**",
        "",
        "## Strategy",
        pack.fit_score.application_strategy,
        "",
        "## CV Tailoring Suggestions",
        f"**Positioning:** {ct.positioning_angle}",
        "",
        "### CV Summary Draft",
        "> " + ct.cv_summary_draft,
        "",
        "### Bullets to Emphasise",
        *[f"- {x}" for x in ct.bullets_to_emphasise],
        "",
        "### Bullets to De-emphasise",
        *[f"- {x}" for x in ct.bullets_to_de_emphasise],
        "",
        "### Suggested Skill Order",
        *[f"- {x}" for x in ct.reordered_skills],
        "",
        "### Approved Claims (use verbatim)",
        *[f"- {x}" for x in ct.approved_claims_usable],
        "",
        "### Adjacent Experience (frame carefully)",
        *[f"- {x}" for x in ct.adjacent_experience],
        "",
        "### Do NOT Claim",
        *[f"- {x}" for x in ct.unsupported_claims],
        "",
        "## Strengths",
        *[f"- {x}" for x in pack.fit_score.strengths],
        "",
        "## Weaknesses / Review Points",
        *[f"- {x}" for x in (pack.risks_to_review or pack.fit_score.weaknesses)],
        "",
        "## Answers",
    ]
    for ans in pack.answers:
        md.extend([
            "",
            f"### {ans.question}",
            ans.answer,
            "",
            f"Confidence: {ans.confidence}; Human review: {ans.needs_human_review}; Reason: {ans.review_reason or 'n/a'}",
        ])
    write_text(out_dir / "application_pack.md", "\n".join(md))

    app_id = None
    if save_tracker:
        record = TrackerRecord(
            company=pack.parsed_job.company,
            role_title=pack.parsed_job.role_title,
            platform=pack.parsed_job.platform,
            fit_score=pack.fit_score.overall_score,
            category=pack.fit_score.category,
            status="drafted",
            notes=pack.fit_score.reason,
        )
        app_id = save_application(record)

    console.print(Panel.fit(
        f"Created application pack:\n{out_dir}\n\nTracker ID: {app_id or 'not saved'}",
        title="Done",
    ))
    console.print(f"Fit: [bold]{pack.fit_score.overall_score}/100[/bold] ({pack.fit_score.category})")
    console.print(f"Strategy: {pack.fit_score.application_strategy}")


if __name__ == "__main__":
    app()
