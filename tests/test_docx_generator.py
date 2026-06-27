"""Tests for jobos/docx_generator.py — DOCX template rendering."""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from docx import Document


# ── Shared fixtures ────────────────────────────────────────────────────────────

_PROFILE = {
    "personal": {
        "name": "Sumedh Brahmadevara",
        "location": "London, UK",
        "email": "test@example.com",
        "linkedin": "linkedin.com/in/test",
    },
}

_ADJACENT = {
    "python_experience": {
        "note": "Python: frame carefully.",
        "safe_phrases": ["Building Python capability for investment workflow tools."],
    }
}


def _make_pack():
    """Build a minimal offline ApplicationPack using the full pipeline."""
    import tempfile
    from apply import build_pack

    jd = (
        "Company: Alpha Fund\n"
        "Role: Research Analyst\n"
        "Fundamental credit research and financial modelling required."
    )
    qs = ""
    with tempfile.TemporaryDirectory() as tmp:
        job_file = Path(tmp) / "job.txt"
        q_file = Path(tmp) / "q.txt"
        job_file.write_text(jd, encoding="utf-8")
        q_file.write_text(qs, encoding="utf-8")
        return build_pack(job_file, q_file)


def _make_cv_docx(tmp_path: Path) -> Path:
    """Create a synthetic CV .docx containing all required CV placeholders."""
    from jobos.docx_generator import CV_PLACEHOLDERS

    doc = Document()
    for placeholder in CV_PLACEHOLDERS:
        doc.add_paragraph(f"{{{{ {placeholder} }}}}")
    path = tmp_path / "cv_template.docx"
    doc.save(str(path))
    return path


def _make_cl_docx(tmp_path: Path) -> Path:
    """Create a synthetic cover letter .docx containing all required CL placeholders."""
    from jobos.docx_generator import CL_PLACEHOLDERS

    doc = Document()
    for placeholder in CL_PLACEHOLDERS:
        doc.add_paragraph(f"{{{{ {placeholder} }}}}")
    path = tmp_path / "cl_template.docx"
    doc.save(str(path))
    return path


# ── Exception class tests ──────────────────────────────────────────────────────

def test_exception_hierarchy():
    from jobos.docx_generator import (
        DocxGeneratorError, TemplateNotFoundError, MissingPlaceholdersError,
    )

    assert issubclass(TemplateNotFoundError, DocxGeneratorError)
    assert issubclass(MissingPlaceholdersError, DocxGeneratorError)


# ── Template not found ─────────────────────────────────────────────────────────

def test_render_cv_docx_raises_template_not_found(tmp_path):
    from jobos.docx_generator import render_cv_docx, TemplateNotFoundError

    missing = tmp_path / "does_not_exist.docx"
    pack = _make_pack()
    cv_master = {}
    with pytest.raises(TemplateNotFoundError):
        render_cv_docx(missing, pack, _PROFILE, cv_master, tmp_path / "out.docx")


def test_render_cl_docx_raises_template_not_found(tmp_path):
    from jobos.docx_generator import render_cover_letter_docx, TemplateNotFoundError

    missing = tmp_path / "does_not_exist.docx"
    pack = _make_pack()
    cv_master = {}
    with pytest.raises(TemplateNotFoundError):
        render_cover_letter_docx(missing, pack, _PROFILE, cv_master, tmp_path / "out.docx")


# ── validate_template ──────────────────────────────────────────────────────────

def test_validate_template_passes_complete_cv(tmp_path):
    from jobos.docx_generator import validate_template, CV_PLACEHOLDERS

    path = _make_cv_docx(tmp_path)
    valid, missing = validate_template(path, CV_PLACEHOLDERS)
    assert valid is True
    assert missing == []


def test_validate_template_passes_complete_cl(tmp_path):
    from jobos.docx_generator import validate_template, CL_PLACEHOLDERS

    path = _make_cl_docx(tmp_path)
    valid, missing = validate_template(path, CL_PLACEHOLDERS)
    assert valid is True
    assert missing == []


def test_validate_template_reports_missing_placeholder(tmp_path):
    from jobos.docx_generator import validate_template

    doc = Document()
    doc.add_paragraph("{{ name }}")
    doc.add_paragraph("{{ contact_line }}")
    path = tmp_path / "partial.docx"
    doc.save(str(path))

    valid, missing = validate_template(path, ["name", "contact_line", "profile_summary"])
    assert valid is False
    assert "profile_summary" in missing


def test_validate_template_reports_all_missing(tmp_path):
    from jobos.docx_generator import validate_template, CV_PLACEHOLDERS

    doc = Document()
    doc.add_paragraph("This template has no placeholders.")
    path = tmp_path / "empty.docx"
    doc.save(str(path))

    valid, missing = validate_template(path, CV_PLACEHOLDERS)
    assert valid is False
    assert len(missing) == len(CV_PLACEHOLDERS)


# ── Missing placeholder error from render functions ────────────────────────────

def test_render_cv_raises_missing_placeholders(tmp_path):
    from jobos.docx_generator import render_cv_docx, MissingPlaceholdersError
    from jobos.document_generator import load_cv_master

    doc = Document()
    doc.add_paragraph("{{ name }} only")
    template = tmp_path / "partial_cv.docx"
    doc.save(str(template))

    cv_master = load_cv_master()
    pack = _make_pack()
    with pytest.raises(MissingPlaceholdersError):
        render_cv_docx(template, pack, _PROFILE, cv_master, tmp_path / "out.docx")


def test_render_cl_raises_missing_placeholders(tmp_path):
    from jobos.docx_generator import render_cover_letter_docx, MissingPlaceholdersError
    from jobos.document_generator import load_cv_master

    doc = Document()
    doc.add_paragraph("{{ name }} only")
    template = tmp_path / "partial_cl.docx"
    doc.save(str(template))

    cv_master = load_cv_master()
    pack = _make_pack()
    with pytest.raises(MissingPlaceholdersError):
        render_cover_letter_docx(template, pack, _PROFILE, cv_master, tmp_path / "out.docx")


# ── CV DOCX rendering ──────────────────────────────────────────────────────────

def test_render_cv_docx_produces_output_file(tmp_path):
    from jobos.docx_generator import render_cv_docx
    from jobos.document_generator import load_cv_master

    template = _make_cv_docx(tmp_path)
    cv_master = load_cv_master()
    pack = _make_pack()
    out = tmp_path / "cv_out.docx"
    result = render_cv_docx(template, pack, _PROFILE, cv_master, out)
    assert result == out
    assert out.exists()


def test_render_cv_docx_output_is_valid_docx(tmp_path):
    from jobos.docx_generator import render_cv_docx
    from jobos.document_generator import load_cv_master

    template = _make_cv_docx(tmp_path)
    cv_master = load_cv_master()
    pack = _make_pack()
    out = tmp_path / "cv_out.docx"
    render_cv_docx(template, pack, _PROFILE, cv_master, out)
    # If python-docx can open it, it's a valid DOCX
    doc = Document(str(out))
    assert len(doc.paragraphs) > 0


def test_render_cv_docx_contains_name(tmp_path):
    from jobos.docx_generator import render_cv_docx
    from jobos.document_generator import load_cv_master

    template = _make_cv_docx(tmp_path)
    cv_master = load_cv_master()
    pack = _make_pack()
    out = tmp_path / "cv_out.docx"
    render_cv_docx(template, pack, _PROFILE, cv_master, out)

    doc = Document(str(out))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Sumedh" in full_text


def test_render_cv_docx_name_from_cv_master(tmp_path):
    """cv_master.meta.name takes priority over profile.personal.name."""
    from jobos.docx_generator import render_cv_docx
    from jobos.document_generator import load_cv_master

    template = _make_cv_docx(tmp_path)
    cv_master = load_cv_master()
    pack = _make_pack()
    out = tmp_path / "cv_out.docx"
    render_cv_docx(template, pack, _PROFILE, cv_master, out)

    doc = Document(str(out))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    # cv_master.yaml defines the name
    assert cv_master["meta"]["name"] in full_text


def test_render_cv_docx_no_unfilled_placeholders(tmp_path):
    from jobos.docx_generator import render_cv_docx, CV_PLACEHOLDERS
    from jobos.document_generator import load_cv_master

    template = _make_cv_docx(tmp_path)
    cv_master = load_cv_master()
    pack = _make_pack()
    out = tmp_path / "cv_out.docx"
    render_cv_docx(template, pack, _PROFILE, cv_master, out)

    doc = Document(str(out))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    for placeholder in CV_PLACEHOLDERS:
        assert f"{{{{ {placeholder} }}}}" not in full_text, (
            f"Placeholder '{{{{ {placeholder} }}}}' was not replaced"
        )


def test_render_cv_docx_profile_summary_not_a_forbidden_claim(tmp_path):
    """The profile_summary and skills context must not contain forbidden claim text.

    Forbidden claims legitimately appear in the do_not_include_note advisory section
    (which tells the reviewer what NOT to claim), so we check the specific fields
    that populate positive CV content, not the full document text.
    """
    from jobos.docx_generator import _build_cv_context
    from jobos.document_generator import load_cv_master

    cv_master = load_cv_master()
    pack = _make_pack()
    context = _build_cv_context(pack, _PROFILE, cv_master)

    # These must never appear as positive claims in the CV content fields
    assert "CFA charterholder" not in context["profile_summary"]
    assert "CFA charterholder" not in context["skills"]
    assert "CFA charterholder" not in context["experience_bullets"]
    assert "Production machine learning engineer" not in context["profile_summary"]


def test_render_cv_docx_does_not_modify_template(tmp_path):
    from jobos.docx_generator import render_cv_docx
    from jobos.document_generator import load_cv_master

    template = _make_cv_docx(tmp_path)
    original_bytes = template.read_bytes()

    cv_master = load_cv_master()
    pack = _make_pack()
    out = tmp_path / "cv_out.docx"
    render_cv_docx(template, pack, _PROFILE, cv_master, out)

    assert template.read_bytes() == original_bytes, "Template file was modified"


def test_render_cv_docx_creates_parent_directory(tmp_path):
    from jobos.docx_generator import render_cv_docx
    from jobos.document_generator import load_cv_master

    template = _make_cv_docx(tmp_path)
    cv_master = load_cv_master()
    pack = _make_pack()
    nested_out = tmp_path / "deep" / "nested" / "cv.docx"
    render_cv_docx(template, pack, _PROFILE, cv_master, nested_out)
    assert nested_out.exists()


# ── Cover letter DOCX rendering ────────────────────────────────────────────────

def test_render_cl_docx_produces_output_file(tmp_path):
    from jobos.docx_generator import render_cover_letter_docx
    from jobos.document_generator import load_cv_master

    template = _make_cl_docx(tmp_path)
    cv_master = load_cv_master()
    pack = _make_pack()
    out = tmp_path / "cl_out.docx"
    result = render_cover_letter_docx(template, pack, _PROFILE, cv_master, out)
    assert result == out
    assert out.exists()


def test_render_cl_docx_contains_company_name(tmp_path):
    from jobos.docx_generator import render_cover_letter_docx
    from jobos.document_generator import load_cv_master

    template = _make_cl_docx(tmp_path)
    cv_master = load_cv_master()
    pack = _make_pack()
    out = tmp_path / "cl_out.docx"
    render_cover_letter_docx(template, pack, _PROFILE, cv_master, out)

    doc = Document(str(out))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert pack.parsed_job.company in full_text


def test_render_cl_docx_no_unfilled_placeholders(tmp_path):
    from jobos.docx_generator import render_cover_letter_docx, CL_PLACEHOLDERS
    from jobos.document_generator import load_cv_master

    template = _make_cl_docx(tmp_path)
    cv_master = load_cv_master()
    pack = _make_pack()
    out = tmp_path / "cl_out.docx"
    render_cover_letter_docx(template, pack, _PROFILE, cv_master, out)

    doc = Document(str(out))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    for placeholder in CL_PLACEHOLDERS:
        assert f"{{{{ {placeholder} }}}}" not in full_text, (
            f"Placeholder '{{{{ {placeholder} }}}}' was not replaced"
        )


def test_render_cl_docx_does_not_modify_template(tmp_path):
    from jobos.docx_generator import render_cover_letter_docx
    from jobos.document_generator import load_cv_master

    template = _make_cl_docx(tmp_path)
    original_bytes = template.read_bytes()

    cv_master = load_cv_master()
    pack = _make_pack()
    out = tmp_path / "cl_out.docx"
    render_cover_letter_docx(template, pack, _PROFILE, cv_master, out)

    assert template.read_bytes() == original_bytes, "Template file was modified"


def test_render_cl_docx_contains_greeting(tmp_path):
    from jobos.docx_generator import render_cover_letter_docx
    from jobos.document_generator import load_cv_master

    template = _make_cl_docx(tmp_path)
    cv_master = load_cv_master()
    pack = _make_pack()
    out = tmp_path / "cl_out.docx"
    render_cover_letter_docx(template, pack, _PROFILE, cv_master, out)

    doc = Document(str(out))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Dear Hiring Manager" in full_text


# ── _overwrite_paragraph internals ────────────────────────────────────────────

def test_overwrite_paragraph_replaces_text():
    from jobos.docx_generator import _overwrite_paragraph

    doc = Document()
    para = doc.add_paragraph("{{ name }}")
    _overwrite_paragraph(para, "Alice Smith")
    assert para.text == "Alice Smith"


def test_overwrite_paragraph_handles_newlines():
    from jobos.docx_generator import _overwrite_paragraph

    doc = Document()
    para = doc.add_paragraph("placeholder")
    _overwrite_paragraph(para, "Line one\nLine two")
    # After overwrite the paragraph text joins lines without the soft break
    # (soft breaks are <w:br/> elements, not \n in para.text)
    combined = para.text
    assert "Line one" in combined
    assert "Line two" in combined


# ── Split-run handling ─────────────────────────────────────────────────────────

def test_replace_handles_split_run():
    """_replace_in_paragraph must handle a placeholder split across two runs."""
    from jobos.docx_generator import _replace_in_paragraph

    doc = Document()
    para = doc.add_paragraph()
    # Simulate Word splitting '{{ name }}' into two runs
    para.add_run("{{ na")
    para.add_run("me }}")

    changed = _replace_in_paragraph(para, {"name": "Bob Jones"})
    assert changed is True
    assert "Bob Jones" in para.text


def test_replace_returns_false_when_no_placeholder():
    from jobos.docx_generator import _replace_in_paragraph

    doc = Document()
    para = doc.add_paragraph("No placeholders here.")
    changed = _replace_in_paragraph(para, {"name": "Alice"})
    assert changed is False
