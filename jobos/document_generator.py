"""Template-locked CV and cover letter generator for JobOS.

Loads cv_master.yaml as the sole approved-content source, selects bullets and
skills by JD-tag relevance, and renders output by filling tokens in the locked
markdown templates.  The AI does not freestyle structure or invent content.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from jobos.config import DATA_DIR
from jobos.io import load_yaml, read_text
from jobos.schemas import ApplicationPack, ParsedJob

# ── Default paths ──────────────────────────────────────────────────────────────
CV_MASTER_PATH = DATA_DIR / "cv_master.yaml"
CV_TEMPLATE_PATH = DATA_DIR / "templates" / "cv_template.md"
CL_TEMPLATE_PATH = DATA_DIR / "templates" / "cover_letter_template.md"

# ── JD keyword → bullet/skill tag mapping ─────────────────────────────────────
_JD_KEYWORD_TAGS: list[tuple[str, list[str]]] = [
    ("fundamental research", ["fundamental_research", "research"]),
    ("fundamental analysis", ["fundamental_research", "research"]),
    ("public markets", ["public_markets", "investment"]),
    ("financial modelling", ["financial_modelling", "modelling"]),
    ("financial model", ["financial_modelling", "modelling"]),
    ("investment", ["investment", "public_markets"]),
    ("earnings", ["earnings", "monitoring"]),
    ("consumer", ["consumer", "sector_research"]),
    ("retail", ["consumer", "sector_research"]),
    ("credit", ["credit", "investment"]),
    ("fixed income", ["bond", "credit", "investment"]),
    ("research", ["research", "fundamental_research"]),
    ("modelling", ["financial_modelling", "modelling"]),
    ("communication", ["communication", "writing"]),
    ("data", ["data", "analytical"]),
    ("analytical", ["analytical"]),
    ("analysis", ["analytical", "research"]),
    ("python", ["python_careful"]),
    ("coding", ["python_careful"]),
    ("programming", ["python_careful"]),
    ("workflow", ["workflow", "python_careful"]),
    ("bond", ["bond", "primary_market"]),
    ("primary", ["primary_market", "bond"]),
    ("new issue", ["primary_market", "bond"]),
    ("hedge fund", ["investment", "public_markets"]),
    ("equity", ["public_markets"]),
    ("systematic", ["quant_adjacent"]),
    ("quant", ["quant_adjacent"]),
    ("econometric", ["econometrics", "quant_adjacent"]),
    ("cash flow", ["financial_modelling"]),
    ("balance sheet", ["financial_modelling", "analytical"]),
    ("leverage", ["financial_modelling", "credit"]),
    ("sector", ["consumer", "sector_research"]),
    ("relative value", ["investment", "analytical"]),
    ("monitoring", ["monitoring", "earnings"]),
    ("risk", ["credit", "analytical"]),
    ("spread", ["credit", "bond"]),
    ("covenant", ["credit", "analytical"]),
]


# ── Loaders ────────────────────────────────────────────────────────────────────

def load_cv_master(path: Path | None = None) -> dict:
    """Load cv_master.yaml. Raises FileNotFoundError if missing."""
    return load_yaml(path or CV_MASTER_PATH)


def _load_template(path: Path) -> str:
    """Load a markdown template file."""
    return read_text(path)


# ── Tag extraction ─────────────────────────────────────────────────────────────

def jd_to_tags(parsed_job: ParsedJob) -> set[str]:
    """Convert a ParsedJob into a set of bullet/skill tags for relevance scoring."""
    jd_text = " ".join([
        parsed_job.role_title,
        *parsed_job.required_skills,
        *parsed_job.preferred_skills,
        *parsed_job.responsibilities,
    ]).lower()

    tags: set[str] = set()
    for keyword, keyword_tags in _JD_KEYWORD_TAGS:
        if keyword in jd_text:
            tags.update(keyword_tags)
    return tags


# ── Bullet and skill selection ─────────────────────────────────────────────────

def select_bullets(
    bullets: list[dict],
    jd_tags: set[str],
    max_count: int = 7,
) -> list[dict]:
    """Select bullets in original YAML order.

    always_include bullets are always selected.
    Other bullets are selected if they share at least one tag with jd_tags.
    """
    selected = [
        b for b in bullets
        if b.get("always_include") or bool(set(b.get("tags", [])) & jd_tags)
    ]
    return selected[:max_count]


def select_skills(
    skills: list[dict],
    jd_tags: set[str],
    max_count: int = 12,
) -> tuple[list[str], list[dict]]:
    """Return (main_skill_texts, adjacent_skill_dicts).

    Adjacent skills (adjacent: true) are excluded from the main list and
    returned separately so callers can place them in the framing guide.
    Main skills are sorted by descending JD-tag overlap.
    """
    non_adjacent = [s for s in skills if not s.get("adjacent")]
    adjacent = [s for s in skills if s.get("adjacent")]

    def score(s: dict) -> int:
        return len(set(s.get("tags", [])) & jd_tags)

    sorted_main = sorted(non_adjacent, key=lambda s: -score(s))
    main_texts = [s["text"] for s in sorted_main[:max_count]]

    relevant_adjacent = [s for s in adjacent if score(s) > 0]
    return main_texts, relevant_adjacent


# ── Section renderers ──────────────────────────────────────────────────────────

def _render_experience_section(roles: list[dict], selected_bullets: list[dict]) -> str:
    """Render the full experience block for all roles."""
    selected_ids = {b["id"] for b in selected_bullets}
    role_blocks: list[str] = []

    for role in roles:
        title = role["title"]
        employer = role["employer"]
        start = role["start"]
        end = role.get("end", "Present")
        sectors: list[str] = role.get("sectors", [])
        role_bullet_ids = {rb["id"] for rb in role.get("bullets", [])}
        role_bullets = [b for b in selected_bullets if b["id"] in role_bullet_ids]

        lines = [f"### {title} — {employer} | {start} – {end}", ""]
        if sectors:
            lines += [f"**Sectors:** {', '.join(sectors)}", ""]
        for b in role_bullets:
            lines.append(f"- {b['text']}")

        role_blocks.append("\n".join(lines))

    return "\n\n".join(role_blocks)


def _render_education_section(educations: list[dict]) -> str:
    """Render the full education block for all entries."""
    blocks: list[str] = []
    for edu in educations:
        institution = edu["institution"]
        college = edu.get("college", "")
        degree = edu["degree"]
        grade = edu["grade"]
        years = edu.get("years", "")
        diss = edu.get("dissertation", {})

        heading = f"### {institution}"
        if college:
            heading += f" | {college}"
        if years:
            heading += f" | {years}"

        lines = [heading, "", f"**{degree}** ({grade})"]

        if diss:
            title = diss.get("title", "")
            prize = diss.get("prize", "")
            methods: list[str] = diss.get("methods", [])
            if title:
                diss_line = f"**Dissertation:** *{title}*"
                if prize:
                    diss_line += f" — *{prize}*"
                lines += ["", diss_line]
            if methods:
                lines += ["", "**Methods:** " + ", ".join(methods)]

        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def _render_optional_adjacent(
    ct_adjacent_experience: list[str],
    adjacent_skills: list[dict],
) -> str:
    """Render the adjacent framing guide section, or empty string if nothing to show."""
    items: list[str] = list(ct_adjacent_experience)
    for skill in adjacent_skills:
        note = skill.get("adjacent_note", "")
        if note:
            items.append(f"{skill['text']} — {note}")

    if not items:
        return ""

    lines = [
        "---",
        "",
        "## Adjacent Experience — Framing Guide",
        "",
        "> ⚠️ These claims are true but require careful framing.",
        "> Use only the exact wording shown — do not upgrade to expertise claims.",
        "",
    ]
    for item in items:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def _render_optional_review(unsupported_claims: list[str]) -> str:
    """Render the Do NOT Include section, or empty string if nothing to show."""
    if not unsupported_claims:
        return ""
    lines = [
        "---",
        "",
        "## Do NOT Include on This CV",
        "",
        "> 🚫 The following claims must NOT appear on any CV, cover letter or application for this role.",
        "",
    ]
    for claim in unsupported_claims:
        lines.append(f"- {claim}")
    lines.append("")
    return "\n".join(lines)


def _clean_whitespace(text: str) -> str:
    """Collapse three or more consecutive newlines into two."""
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def _replace_tokens(template: str, tokens: dict[str, str]) -> str:
    """Replace all {{TOKEN}} placeholders in template."""
    result = template
    for key, value in tokens.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


# ── CV renderer ────────────────────────────────────────────────────────────────

def render_cv(
    template: str,
    pack: ApplicationPack,
    cv_master: dict,
    profile: dict,
    forbidden_claims: list[str],
    date_str: str,
) -> tuple[str, list[str]]:
    """Render tailored_cv.md from the locked template.

    Returns (markdown_content, high_risk_warnings).
    """
    meta = cv_master.get("meta", {})
    personal = profile.get("personal", {})

    name = meta.get("name") or personal.get("name", "Sumedh Brahmadevara")
    location = meta.get("location") or personal.get("location", "London, UK")
    email = meta.get("email") or personal.get("email", "[ADD EMAIL]")
    linkedin = meta.get("linkedin") or personal.get("linkedin", "[ADD LINKEDIN]")

    ct = pack.cv_tailor
    jd_tags = jd_to_tags(pack.parsed_job)

    # ── Bullet selection ───────────────────────────────────────────────────────
    roles = cv_master.get("experience", [])
    all_bullets: list[dict] = []
    for role in roles:
        all_bullets.extend(role.get("bullets", []))
    selected_bullets = select_bullets(all_bullets, jd_tags)

    # ── Skill selection ────────────────────────────────────────────────────────
    all_skills = cv_master.get("skills", [])
    main_skills, adjacent_skills = select_skills(all_skills, jd_tags)

    # ── CV summary ─────────────────────────────────────────────────────────────
    profile_summary = ct.cv_summary_draft
    summary_annotation = ""
    high_risk_warnings: list[str] = []

    vr = ct.cv_summary_verification
    if vr and vr.final_risk_level != "low":
        w = f"CV summary is {vr.final_risk_level} risk — review before submitting."
        high_risk_warnings.append(w)
        notes: list[str] = []
        if vr.unsupported_claims:
            notes.append("> ⚠️ **Unsupported claims:** " + ", ".join(vr.unsupported_claims))
        if vr.exaggerated_claims:
            notes.append("> 🚨 **Forbidden / exaggerated:** " + ", ".join(vr.exaggerated_claims))
        if notes:
            summary_annotation = "\n\n" + "\n".join(notes)
    elif vr and vr.adjacent_claims_detected:
        summary_annotation = (
            "\n\n> 🟡 **Adjacent topics in summary** — review framing: "
            + ", ".join(vr.adjacent_claims_detected)
        )

    # ── Safety scan: forbidden claims in body text ─────────────────────────────
    body_text = " ".join(b["text"] for b in selected_bullets) + " " + profile_summary
    for fc in forbidden_claims:
        if fc.lower() in body_text.lower():
            high_risk_warnings.append(
                f"⚠️ Forbidden claim found in CV draft: '{fc}' — remove before submitting."
            )

    # ── Render sections ────────────────────────────────────────────────────────
    skills_list = "\n".join(f"- {s}" for s in main_skills)
    experience_block = _render_experience_section(roles, selected_bullets)
    education_block = _render_education_section(cv_master.get("education", []))
    optional_adjacent = _render_optional_adjacent(ct.adjacent_experience, adjacent_skills)
    optional_review = _render_optional_review(ct.unsupported_claims)

    footer = (
        f"Draft generated by JobOS on {date_str}. "
        "All claims require human review before submission. "
        "Do not submit without verifying every claim against approved_claims.yaml."
    )

    tokens = {
        "NAME": name,
        "LOCATION": location,
        "EMAIL": email,
        "LINKEDIN": linkedin,
        "PROFILE_SUMMARY": profile_summary + summary_annotation,
        "SKILLS_LIST": skills_list,
        "EXPERIENCE_SECTION": experience_block,
        "EDUCATION_SECTION": education_block,
        "OPTIONAL_ADJACENT_SECTION": optional_adjacent,
        "OPTIONAL_REVIEW_SECTION": optional_review,
        "FOOTER": footer,
    }

    result = _replace_tokens(template, tokens)

    # Prepend high-risk banner if needed
    if high_risk_warnings:
        banner_lines = [
            "> ## ⚠️ CLAIM REVIEW REQUIRED",
            ">",
            *[f"> {w}" for w in high_risk_warnings],
            ">",
            "> **Resolve all warnings above before submitting this CV.**",
            "",
        ]
        result = "\n".join(banner_lines) + "\n" + result

    return _clean_whitespace(result), high_risk_warnings


# ── Cover letter renderer ──────────────────────────────────────────────────────

def render_cover_letter(
    template: str,
    pack: ApplicationPack,
    cv_master: dict,
    profile: dict,
    date_str: str,
) -> str:
    """Render cover_letter.md from the locked template."""
    meta = cv_master.get("meta", {})
    personal = profile.get("personal", {})
    cl_paragraphs = cv_master.get("cover_letter_paragraphs", {})

    name = meta.get("name") or personal.get("name", "Sumedh Brahmadevara")
    location = meta.get("location") or personal.get("location", "London, UK")
    email = meta.get("email") or personal.get("email", "[ADD EMAIL]")

    job = pack.parsed_job
    fit = pack.fit_score
    ct = pack.cv_tailor
    jd_tags = jd_to_tags(job)

    def _select_paragraph(key: str) -> str:
        options = cl_paragraphs.get(key, [])
        if not options:
            return f"[{key} paragraph — add to cv_master.yaml]"

        def score(p: dict) -> int:
            tags = set(p.get("tags", []))
            non_general = tags - {"general"}
            return len(non_general & jd_tags) if non_general else 0

        best = max(options, key=lambda p: (score(p), p.get("id", "")))
        text = best["text"]
        text = text.replace("{role_title}", job.role_title)
        text = text.replace("{company}", job.company)
        text = text.replace("{application_strategy}", fit.application_strategy)
        return text

    opening_base = _select_paragraph("opening")
    opening_para = opening_base + " " + ct.positioning_angle

    outline_block = "\n".join(f"> - {p}" for p in pack.cover_letter_outline)
    sign_off = f"Yours sincerely,\n\n{name}"
    footer = (
        f"Draft generated by JobOS on {date_str}. Human review required before sending. "
        "Replace [ADD FIRM-SPECIFIC MOTIVATION] with firm-specific detail before submitting."
    )

    tokens = {
        "COMPANY": job.company,
        "ROLE_TITLE": job.role_title,
        "NAME": name,
        "LOCATION": location,
        "EMAIL": email,
        "DATE": date_str,
        "SALUTATION": "Hiring Manager",
        "OPENING_PARAGRAPH": opening_para,
        "BODY_PARAGRAPH_1": _select_paragraph("body_credit"),
        "BODY_PARAGRAPH_2": _select_paragraph("body_cambridge"),
        "MOTIVATION_PARAGRAPH": _select_paragraph("body_motivation"),
        "CLOSING_PARAGRAPH": _select_paragraph("closing"),
        "SIGN_OFF": sign_off,
        "OUTLINE_GUIDANCE": outline_block,
        "FOOTER": footer,
    }

    result = _replace_tokens(template, tokens)
    return _clean_whitespace(result)


# ── Public entry point ─────────────────────────────────────────────────────────

def generate_documents(
    pack: ApplicationPack,
    profile: dict,
    adjacent_claims: dict,
    approved_claims_full: dict | None = None,
    cv_master: dict | None = None,
    cv_template: str | None = None,
    cover_letter_template: str | None = None,
    date_str: str | None = None,
) -> tuple[str, list[str], str]:
    """Generate CV and cover letter from locked templates.

    Returns (cv_content, high_risk_warnings, cover_letter_content).
    """
    if date_str is None:
        date_str = datetime.now().strftime("%d %B %Y")

    if cv_master is None:
        cv_master = load_cv_master()

    if cv_template is None:
        cv_template = _load_template(CV_TEMPLATE_PATH)

    if cover_letter_template is None:
        cover_letter_template = _load_template(CL_TEMPLATE_PATH)

    forbidden_claims: list[str] = []
    if approved_claims_full:
        raw = approved_claims_full.get("forbidden_claims", [])
        forbidden_claims = raw if isinstance(raw, list) else []

    cv_content, warnings = render_cv(
        cv_template, pack, cv_master, profile, forbidden_claims, date_str
    )
    cl_content = render_cover_letter(
        cover_letter_template, pack, cv_master, profile, date_str
    )
    return cv_content, warnings, cl_content
