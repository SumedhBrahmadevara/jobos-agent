"""DOCX template renderer for JobOS.

Loads a user-supplied .docx template, validates required {{ token }} placeholders,
fills them with approved content, and writes the result to a new file.
Never modifies the original template file.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn as _ns_qn

from jobos.schemas import ApplicationPack
from jobos.document_generator import jd_to_tags, select_bullets, select_skills

# ── Required placeholders ──────────────────────────────────────────────────────

CV_PLACEHOLDERS: list[str] = [
    "name",
    "contact_line",
    "profile_summary",
    "skills",
    "experience_role",
    "experience_company",
    "experience_dates",
    "experience_bullets",
    "education_section",
    "adjacent_claims_note",
    "do_not_include_note",
]

CL_PLACEHOLDERS: list[str] = [
    "name",
    "contact_line",
    "date",
    "company",
    "role",
    "greeting",
    "opening_paragraph",
    "body_paragraph_1",
    "body_paragraph_2",
    "motivation_paragraph",
    "closing_paragraph",
    "signoff",
]

# ── Exceptions ─────────────────────────────────────────────────────────────────


class DocxGeneratorError(Exception):
    """Base error for DOCX generation failures."""


class TemplateNotFoundError(DocxGeneratorError):
    """Template file does not exist."""


class MissingPlaceholdersError(DocxGeneratorError):
    """Template is missing one or more required {{ token }} placeholders."""


# ── Template scanning helpers ──────────────────────────────────────────────────


def _iter_paragraphs(doc: Document):
    """Yield every paragraph in body, tables, and section headers/footers."""
    yield from doc.paragraphs
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs
    for section in doc.sections:
        yield from section.header.paragraphs
        yield from section.footer.paragraphs


def validate_template(
    path: Path,
    required_placeholders: list[str],
) -> tuple[bool, list[str]]:
    """Check that all required {{ token }} placeholders appear in the template.

    Returns (is_valid, list_of_missing_names).
    """
    path = Path(path)
    doc = Document(str(path))
    all_text = "\n".join(
        "".join(run.text for run in para.runs)
        for para in _iter_paragraphs(doc)
    )
    missing = [p for p in required_placeholders if f"{{{{ {p} }}}}" not in all_text]
    return len(missing) == 0, missing


# ── Paragraph-level replacement ────────────────────────────────────────────────


def _overwrite_paragraph(para, new_text: str) -> None:
    """Replace a paragraph's run content with new_text.

    Paragraph style and spacing are preserved (w:pPr untouched).
    Newlines in new_text become soft line-breaks within the same paragraph.
    """
    p = para._p
    for child in list(p):
        if child.tag in (
            _ns_qn("w:r"),
            _ns_qn("w:hyperlink"),
            _ns_qn("w:ins"),
            _ns_qn("w:del"),
        ):
            p.remove(child)

    lines = new_text.split("\n")
    for i, line in enumerate(lines):
        if i > 0:
            br_run = para.add_run()
            br_run.add_break()
        para.add_run(line)


def _replace_in_paragraph(para, context: dict[str, str]) -> bool:
    """Replace {{ token }} placeholders in one paragraph.

    Word sometimes splits a placeholder across multiple runs; joining all run
    texts before replacement handles that correctly.

    Returns True if any replacement was made.
    """
    full_text = "".join(run.text for run in para.runs)
    if "{{" not in full_text:
        return False

    new_text = full_text
    for token, value in context.items():
        new_text = new_text.replace(f"{{{{ {token} }}}}", value)
        new_text = new_text.replace(f"{{{{{token}}}}}", value)  # no-space variant

    if new_text == full_text:
        return False

    _overwrite_paragraph(para, new_text)
    return True


def _replace_in_doc(doc: Document, context: dict[str, str]) -> None:
    """Apply context replacements to every paragraph in the document."""
    for para in _iter_paragraphs(doc):
        _replace_in_paragraph(para, context)


# ── Context builders ───────────────────────────────────────────────────────────


def _build_cv_context(
    pack: ApplicationPack,
    profile: dict,
    cv_master: dict,
) -> dict[str, str]:
    meta = cv_master.get("meta", {})
    personal = profile.get("personal", {})

    name = meta.get("name") or personal.get("name", "Sumedh Brahmadevara")
    location = meta.get("location") or personal.get("location", "London, UK")
    email = meta.get("email") or personal.get("email", "[ADD EMAIL]")
    linkedin = meta.get("linkedin") or personal.get("linkedin", "[ADD LINKEDIN]")

    ct = pack.cv_tailor
    jd_tags = jd_to_tags(pack.parsed_job)

    roles = cv_master.get("experience", [])
    all_bullets: list[dict] = [b for role in roles for b in role.get("bullets", [])]
    selected_bullets = select_bullets(all_bullets, jd_tags)
    main_skills, adjacent_skills = select_skills(cv_master.get("skills", []), jd_tags)

    # Primary role (first entry)
    role_data = roles[0] if roles else {}
    exp_role = role_data.get("title", "")
    exp_company = role_data.get("employer", "")
    start = role_data.get("start", "")
    end = role_data.get("end", "Present")
    exp_dates = f"{start} – {end}"

    # Only bullets belonging to the first role
    first_role_bullet_ids = {b["id"] for b in role_data.get("bullets", [])}
    first_role_bullets = [b for b in selected_bullets if b["id"] in first_role_bullet_ids]
    exp_bullets = "\n".join(f"• {b['text']}" for b in first_role_bullets)

    # Education block
    edu_lines: list[str] = []
    for edu in cv_master.get("education", []):
        diss = edu.get("dissertation", {})
        institution = edu.get("institution", "")
        college = edu.get("college", "")
        heading = institution + (f", {college}" if college else "")
        edu_lines.append(
            f"{edu.get('degree', '')} ({edu.get('grade', '')}) — {heading} | {edu.get('years', '')}"
        )
        if diss.get("title"):
            prize = diss.get("prize", "")
            edu_lines.append(
                "Dissertation: " + diss["title"] + (f" — {prize}" if prize else "")
            )
        if diss.get("methods"):
            edu_lines.append("Methods: " + ", ".join(diss["methods"]))
    education_section = "\n".join(edu_lines)

    # Adjacent claims note
    adj_items: list[str] = list(ct.adjacent_experience)
    for s in adjacent_skills:
        note = s.get("adjacent_note", "")
        if note:
            adj_items.append(f"{s['text']} — {note}")
    adjacent_note = (
        "\n".join(f"• {item}" for item in adj_items)
        if adj_items
        else "No adjacent experience notes for this role."
    )

    # Do-not-include note
    do_not = (
        "\n".join(f"• {c}" for c in ct.unsupported_claims)
        if ct.unsupported_claims
        else "No specific exclusions for this role."
    )

    return {
        "name": name,
        "contact_line": f"{location} │ {email} │ {linkedin}",
        "profile_summary": ct.cv_summary_draft,
        "skills": "\n".join(f"• {s}" for s in main_skills),
        "experience_role": exp_role,
        "experience_company": exp_company,
        "experience_dates": exp_dates,
        "experience_bullets": exp_bullets,
        "education_section": education_section,
        "adjacent_claims_note": adjacent_note,
        "do_not_include_note": do_not,
    }


def _build_cl_context(
    pack: ApplicationPack,
    profile: dict,
    cv_master: dict,
) -> dict[str, str]:
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

    def _select(key: str) -> str:
        options = cl_paragraphs.get(key, [])
        if not options:
            return f"[{key} — add paragraphs to cv_master.yaml]"

        def _score(p: dict) -> int:
            tags = set(p.get("tags", []))
            non_general = tags - {"general"}
            return len(non_general & jd_tags) if non_general else 0

        best = max(options, key=lambda p: (_score(p), p.get("id", "")))
        text = best["text"]
        text = text.replace("{role_title}", job.role_title)
        text = text.replace("{company}", job.company)
        text = text.replace("{application_strategy}", fit.application_strategy)
        return text

    opening = _select("opening") + " " + ct.positioning_angle

    return {
        "name": name,
        "contact_line": f"{location} │ {email}",
        "date": datetime.now().strftime("%d %B %Y"),
        "company": job.company,
        "role": job.role_title,
        "greeting": "Dear Hiring Manager,",
        "opening_paragraph": opening,
        "body_paragraph_1": _select("body_credit"),
        "body_paragraph_2": _select("body_cambridge"),
        "motivation_paragraph": _select("body_motivation"),
        "closing_paragraph": _select("closing"),
        "signoff": f"Yours sincerely,\n\n{name}",
    }


# ── Render functions ───────────────────────────────────────────────────────────


def render_cv_docx(
    template_path: Path,
    pack: ApplicationPack,
    profile: dict,
    cv_master: dict,
    out_path: Path,
) -> Path:
    """Render a tailored CV .docx from a user-supplied template.

    Raises TemplateNotFoundError if the template does not exist.
    Raises MissingPlaceholdersError if required placeholders are absent.
    The original template is never modified.
    """
    template_path = Path(template_path)
    if not template_path.exists():
        raise TemplateNotFoundError(f"CV template not found: {template_path}")

    valid, missing = validate_template(template_path, CV_PLACEHOLDERS)
    if not valid:
        raise MissingPlaceholdersError(
            f"CV template missing required placeholders: {', '.join(missing)}"
        )

    doc = Document(str(template_path))
    context = _build_cv_context(pack, profile, cv_master)
    _replace_in_doc(doc, context)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path


def render_cover_letter_docx(
    template_path: Path,
    pack: ApplicationPack,
    profile: dict,
    cv_master: dict,
    out_path: Path,
) -> Path:
    """Render a cover letter .docx from a user-supplied template.

    Raises TemplateNotFoundError if the template does not exist.
    Raises MissingPlaceholdersError if required placeholders are absent.
    The original template is never modified.
    """
    template_path = Path(template_path)
    if not template_path.exists():
        raise TemplateNotFoundError(f"Cover letter template not found: {template_path}")

    valid, missing = validate_template(template_path, CL_PLACEHOLDERS)
    if not valid:
        raise MissingPlaceholdersError(
            f"Cover letter template missing required placeholders: {', '.join(missing)}"
        )

    doc = Document(str(template_path))
    context = _build_cl_context(pack, profile, cv_master)
    _replace_in_doc(doc, context)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path
