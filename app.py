from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st

from apply import build_pack
from jobos.config import DATA_DIR, APPLICATIONS_DIR, ensure_dirs
from jobos.llm_client import llm_is_available
from jobos.io import load_yaml
from jobos.schemas import TrackerRecord
from jobos.tracker import save_application, get_applications, update_status
from jobos.agents.claim_verifier_agent import verify_answer
from jobos.agents.compliance_agent import classify_field
from jobos.profile_manager import save_yaml_safe
from jobos.application_bundle import generate_bundle
from jobos.docx_generator import (
    CV_PLACEHOLDERS, CL_PLACEHOLDERS,
    validate_template, diagnose_template, render_cv_docx, render_cover_letter_docx,
    TemplateNotFoundError, MissingPlaceholdersError,
)
from jobos.document_generator import load_cv_master
from jobos.history import scan_applications, load_pack_from_folder, read_file_content

_BACKUPS_DIR = DATA_DIR / "backups"

_STATUSES = ["drafted", "applied", "screening", "interview", "offer", "rejected", "withdrawn"]

_RISK_BADGE = {"low": "✅ low", "medium": "⚠️ medium", "high": "🚨 high"}
_FIELD_BADGE = {"green": "🟢 green", "amber": "🟡 amber", "red": "🔴 red"}
_CAT_COLOR = {"A": "green", "B": "blue", "C": "orange", "reject": "red"}

st.set_page_config(page_title="JobOS", layout="wide", page_icon="📋")

# ── Session state ─────────────────────────────────────────────────────────────
if "pack" not in st.session_state:
    st.session_state["pack"] = None
if "out_dir_name" not in st.session_state:
    st.session_state["out_dir_name"] = None
if "app_id" not in st.session_state:
    st.session_state["app_id"] = None
if "approved_data" not in st.session_state:
    st.session_state["approved_data"] = {}
if "bundle" not in st.session_state:
    st.session_state["bundle"] = None
if "docx_cv_path" not in st.session_state:
    st.session_state["docx_cv_path"] = None
if "docx_cl_path" not in st.session_state:
    st.session_state["docx_cl_path"] = None

_LOCAL_TEMPLATES_DIR = DATA_DIR / "local_templates"
_LOCAL_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

# ── Sidebar: recent applications ──────────────────────────────────────────────

with st.sidebar:
    st.title("JobOS")
    st.caption("Human-in-the-loop job application agent")
    st.divider()

    st.subheader("Recent Applications")
    recent = get_applications(limit=20)

    if not recent:
        st.caption("No applications yet. Generate a pack to start tracking.")
    else:
        for row in recent:
            cat = row["category"]
            color = _CAT_COLOR.get(cat, "gray")
            st.markdown(f"**{row['company']}** · :{color}[{cat}] · {row['fit_score']}/100")
            st.caption(f"{row['role_title']} · {row['created_at'][:10]}")

            current_idx = _STATUSES.index(row["status"]) if row["status"] in _STATUSES else 0
            new_status = st.selectbox(
                "Status",
                options=_STATUSES,
                index=current_idx,
                key=f"status_{row['id']}",
                label_visibility="collapsed",
            )
            if new_status != row["status"]:
                update_status(row["id"], new_status)
                st.rerun()

            st.write("")

# ── Main tabs ─────────────────────────────────────────────────────────────────

is_llm = llm_is_available()
tab_apply, tab_profile, tab_history, tab_exports = st.tabs(
    ["🚀 Apply", "📋 Profile & Claims", "📂 History", "📄 Templates & Exports"]
)

# ══════════════════════════════════════════════════════════════════════════════
# Tab 1: Apply
# ══════════════════════════════════════════════════════════════════════════════

with tab_apply:
    st.title("JobOS Application Agent")
    st.caption("Safe MVP — parse → score fit → draft answers → verify claims. No auto-submit.")

    if is_llm:
        st.info("Running in **LLM mode**.")
    else:
        st.info(
            "Running in **offline demo mode**. "
            "Add `OPENAI_API_KEY` to `.env` to enable the LLM."
        )

    _sample_job = DATA_DIR / "sample_job.txt"
    _sample_q = DATA_DIR / "sample_questions.txt"

    col_jd, col_qs = st.columns([3, 2])

    with col_jd:
        st.subheader("Job description")
        job_text = st.text_area(
            "job_desc",
            value=_sample_job.read_text(encoding="utf-8") if _sample_job.exists() else "",
            height=280,
            placeholder="Paste the job description here…",
            label_visibility="collapsed",
        )

    with col_qs:
        st.subheader("Application questions")
        st.caption("One question per line. Leave blank if there are none.")
        questions_text = st.text_area(
            "questions",
            value=_sample_q.read_text(encoding="utf-8") if _sample_q.exists() else "",
            height=250,
            placeholder="Why are you applying for this role?\nDescribe a time you used data…",
            label_visibility="collapsed",
        )

    generate_clicked = st.button("Generate Application Pack", type="primary", use_container_width=True)

    # ── Pipeline ───────────────────────────────────────────────────────────────

    if generate_clicked:
        if not job_text.strip():
            st.error("Please paste a job description first.")
            st.stop()

        ensure_dirs()
        temp_job = DATA_DIR / "_temp_job.txt"
        temp_q = DATA_DIR / "_temp_questions.txt"

        try:
            temp_job.write_text(job_text, encoding="utf-8")
            temp_q.write_text(questions_text, encoding="utf-8")
            with st.spinner("Running agents…"):
                pack = build_pack(temp_job, temp_q)
        finally:
            temp_job.unlink(missing_ok=True)
            temp_q.unlink(missing_ok=True)

        # Save outputs
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = (
            f"{pack.parsed_job.company}_{pack.parsed_job.role_title}"
            .replace(" ", "_")
            .replace("/", "-")
        )
        out_dir = APPLICATIONS_DIR / f"{timestamp}_{slug}"

        approved_data = (
            load_yaml(DATA_DIR / "approved_claims.yaml")
            if (DATA_DIR / "approved_claims.yaml").exists()
            else {}
        )
        profile_data = (
            load_yaml(DATA_DIR / "profile.yaml")
            if (DATA_DIR / "profile.yaml").exists()
            else {}
        )
        adjacent_claims_data = approved_data.get("adjacent_claims", {})

        bundle = generate_bundle(
            pack, out_dir, profile_data, adjacent_claims_data, approved_claims_full=approved_data
        )

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

        st.session_state["pack"] = pack
        st.session_state["out_dir_name"] = out_dir.name
        st.session_state["app_id"] = app_id
        st.session_state["approved_data"] = approved_data
        st.session_state["bundle"] = bundle

    # ── Results display ────────────────────────────────────────────────────────

    pack = st.session_state["pack"]

    if pack is not None:
        st.divider()

        st.header(f"{pack.parsed_job.company} — {pack.parsed_job.role_title}")
        if pack.parsed_job.location:
            st.caption(f"Location: {pack.parsed_job.location}")
        if pack.parsed_job.platform:
            st.caption(f"Platform: {pack.parsed_job.platform}")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Fit score", f"{pack.fit_score.overall_score} / 100")
        m2.metric("Category", pack.fit_score.category)
        m3.metric("Seniority", pack.parsed_job.seniority_level or "unknown")
        m4.metric("Referral needed", "Yes" if pack.fit_score.needs_referral else "No")

        st.write("**Strategy:**", pack.fit_score.application_strategy)

        col_str, col_wk = st.columns(2)
        with col_str:
            st.write("**Strengths**")
            for s in pack.fit_score.strengths:
                st.write(f"- {s}")
        with col_wk:
            st.write("**Review points**")
            for w in pack.risks_to_review or pack.fit_score.weaknesses:
                st.write(f"- {w}")

        if pack.parsed_job.red_flags:
            with st.expander(f"Red flags from job description ({len(pack.parsed_job.red_flags)})"):
                for flag in pack.parsed_job.red_flags:
                    st.write(f"- {flag}")

        with st.expander("Cover letter outline"):
            for line in pack.cover_letter_outline:
                st.write(f"- {line}")

        # ── CV Tailoring Suggestions ──────────────────────────────────────────

        st.divider()
        st.subheader("CV Tailoring Suggestions")
        st.caption(
            "Suggestions only — no CV files have been modified. "
            "Review all draft language before using."
        )

        ct = pack.cv_tailor

        st.write("**Positioning angle:**", ct.positioning_angle)

        with st.expander("CV summary / profile draft", expanded=True):
            st.info(ct.cv_summary_draft)
            st.caption("Draft only — verify every claim against approved_claims.yaml before using.")
            if ct.cv_summary_verification is not None:
                vr = ct.cv_summary_verification
                badge = _RISK_BADGE[vr.final_risk_level]
                if vr.final_risk_level == "low" and not vr.adjacent_claims_detected:
                    st.success(f"Claim check: {badge} — no issues detected in CV summary.")
                else:
                    risk_fn = st.error if vr.final_risk_level == "high" else st.warning
                    if vr.final_risk_level != "low":
                        risk_fn(f"Claim check: {badge} — review CV summary before using.")
                    if vr.unsupported_claims:
                        st.error("Unsupported: " + ", ".join(f"`{c}`" for c in vr.unsupported_claims))
                    if vr.exaggerated_claims:
                        st.error("Forbidden / exaggerated: " + ", ".join(f"`{c}`" for c in vr.exaggerated_claims))
                    if vr.generic_phrases:
                        st.warning("Generic phrases: " + ", ".join(f"`{p}`" for p in vr.generic_phrases))
                    if vr.adjacent_claims_detected:
                        st.warning(
                            "🟡 Adjacent topics in summary — review framing: "
                            + ", ".join(f"`{t}`" for t in vr.adjacent_claims_detected)
                        )
                    if vr.recommended_edits:
                        with st.expander("Framing recommendations", expanded=False):
                            for edit in vr.recommended_edits:
                                st.info(edit)

        col_em, col_de = st.columns(2)
        with col_em:
            st.write("**Emphasise**")
            for b in ct.bullets_to_emphasise:
                st.write(f"- {b}")
        with col_de:
            st.write("**De-emphasise / reframe**")
            for b in ct.bullets_to_de_emphasise:
                st.write(f"- {b}")

        if ct.reordered_skills:
            with st.expander("Suggested skill order for this role"):
                for i, skill in enumerate(ct.reordered_skills, 1):
                    st.write(f"{i}. {skill}")

        col_ap, col_adj, col_no = st.columns(3)
        with col_ap:
            st.write("**✅ Approved claims**")
            st.caption("Use verbatim — these are confirmed facts.")
            for c in ct.approved_claims_usable:
                st.success(c)
        with col_adj:
            st.write("**🟡 Adjacent / Careful Claims**")
            st.caption(
                "True but require careful framing. "
                "Use only the exact wording shown — do not upgrade to expertise claims."
            )
            for c in ct.adjacent_experience:
                st.warning(c)
        with col_no:
            st.write("**🚨 Do NOT claim**")
            st.caption("Must not appear on CV or any application.")
            for c in ct.unsupported_claims:
                st.error(c)

        if ct.risks_and_gaps:
            with st.expander("Risks and gaps to address"):
                for r in ct.risks_and_gaps:
                    st.write(f"- {r}")

        # ── Draft answers ─────────────────────────────────────────────────────

        st.divider()
        st.subheader("Draft Answers")

        if not pack.answers:
            st.info("No application questions were provided. Add questions above and regenerate.")
        else:
            approved_data: dict = st.session_state["approved_data"]
            adjacent_claims_data = approved_data.get("adjacent_claims", {})

            for ans in pack.answers:
                verification = verify_answer(
                    ans.answer,
                    approved_data.get("approved_claims", {}),
                    approved_data.get("forbidden_claims", []),
                    adjacent_claims=adjacent_claims_data,
                )
                field_risk = classify_field(ans.question)

                expander_label = (
                    f"{ans.question}  "
                    f"| claim {_RISK_BADGE[verification.final_risk_level]}  "
                    f"| field {_FIELD_BADGE[field_risk.risk_level]}"
                )

                with st.expander(expander_label, expanded=ans.needs_human_review):

                    st.write(ans.answer)
                    st.caption(
                        f"Confidence: **{ans.confidence}** · "
                        f"Words: {ans.word_count} · "
                        f"Human review: {'**yes**' if ans.needs_human_review else 'no'}"
                    )

                    if ans.needs_human_review:
                        st.warning(
                            f"Review needed: {ans.review_reason or 'Flagged by claim verifier.'}"
                        )

                    st.write("---")
                    st.write("**Claim check**")
                    has_hard_issues = (
                        verification.unsupported_claims
                        or verification.exaggerated_claims
                        or verification.generic_phrases
                    )
                    if not has_hard_issues and not verification.adjacent_claims_detected:
                        st.success("No claim issues detected.")
                    else:
                        if verification.unsupported_claims:
                            st.error(
                                "Unsupported claims: "
                                + ", ".join(f"`{c}`" for c in verification.unsupported_claims)
                            )
                        if verification.exaggerated_claims:
                            st.error(
                                "Forbidden / exaggerated: "
                                + ", ".join(f"`{c}`" for c in verification.exaggerated_claims)
                            )
                        if verification.generic_phrases:
                            st.warning(
                                "Generic phrases to remove: "
                                + ", ".join(f"`{p}`" for p in verification.generic_phrases)
                            )
                        if verification.adjacent_claims_detected:
                            st.warning(
                                "🟡 Adjacent experience detected — review framing: "
                                + ", ".join(f"`{t}`" for t in verification.adjacent_claims_detected)
                            )
                        # Show recommended edits, but de-duplicate adjacent framing notes
                        # that are already visible via adjacent_claims_detected display
                        edits_to_show = verification.recommended_edits
                        if edits_to_show:
                            with st.expander("Framing recommendations", expanded=False):
                                for edit in edits_to_show:
                                    st.info(edit)

                    st.write("**Compliance note**")
                    _compliance_fn = {
                        "green": st.success,
                        "amber": st.warning,
                        "red": st.error,
                    }[field_risk.risk_level]
                    _compliance_fn(
                        f"{_FIELD_BADGE[field_risk.risk_level]} {field_risk.reason}"
                        + (" — manual review required." if field_risk.requires_manual_approval else "")
                    )

        # ── Generated Bundle ───────────────────────────────────────────────────

        st.divider()
        out_dir_name = st.session_state["out_dir_name"]
        app_id = st.session_state["app_id"]
        bundle_result = st.session_state.get("bundle")

        if out_dir_name:
            st.subheader("Generated Bundle")
            st.success(
                f"Saved to `outputs/applications/{out_dir_name}` · "
                f"Tracker ID: {app_id}"
            )

            if bundle_result:
                if bundle_result.high_risk_warnings:
                    st.error("⚠️ High-risk claim warnings — review before submitting:")
                    for w in bundle_result.high_risk_warnings:
                        st.error(f"- {w}")

                if bundle_result.adjacent_claims_flagged:
                    with st.expander("🟡 Adjacent claims flagged in this application"):
                        for item in bundle_result.adjacent_claims_flagged:
                            st.warning(item)

                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    st.write("**Documents created:**")
                    for label, path_str in [
                        ("📄 Tailored CV", bundle_result.tailored_cv_path),
                        ("✉️ Cover Letter", bundle_result.cover_letter_path),
                        ("📝 Application Answers", bundle_result.answers_path),
                    ]:
                        p = Path(path_str)
                        rel = p.relative_to(Path(bundle_result.out_dir).parent.parent) if p.exists() else p.name
                        st.write(f"{label}: `{rel}`")
                with col_b2:
                    st.write("**Data files:**")
                    for label, path_str in [
                        ("📦 Pack JSON", bundle_result.pack_json_path),
                        ("📋 Pack Summary", bundle_result.pack_md_path),
                    ]:
                        p = Path(path_str)
                        rel = p.relative_to(Path(bundle_result.out_dir).parent.parent) if p.exists() else p.name
                        st.write(f"{label}: `{rel}`")

                st.caption(
                    "All files are local only and excluded from Git. "
                    "Review tailored_cv.md and cover_letter.md carefully before submitting."
                )

# ══════════════════════════════════════════════════════════════════════════════
# Tab 2: Profile & Claims
# ══════════════════════════════════════════════════════════════════════════════

with tab_profile:
    st.title("Profile & Claims Manager")
    st.caption(
        "View and edit your source-of-truth files. "
        "YAML is validated before saving and a timestamped backup is created automatically."
    )
    st.warning(
        "Changes here update the live files used by the Apply tab. "
        "Review every edit carefully — the claim verifier enforces these limits on every answer and CV summary."
    )

    ptab_profile, ptab_claims, ptab_answers = st.tabs(
        ["👤 Profile", "✅ Approved Claims", "📝 Answer Bank"]
    )

    # ── Profile ───────────────────────────────────────────────────────────────

    with ptab_profile:
        profile_path = DATA_DIR / "profile.yaml"

        if profile_path.exists():
            profile_data = load_yaml(profile_path)
            personal = profile_data.get("personal", {})
            role = profile_data.get("current_role", {})
            edu = profile_data.get("education", {})

            col_p1, col_p2 = st.columns(2)
            with col_p1:
                st.subheader("Personal")
                st.write(f"**Name:** {personal.get('name', '—')}")
                st.write(f"**Location:** {personal.get('location', '—')}")
                st.write(f"**Email:** {personal.get('email', '—')}")

                st.subheader("Current Role")
                st.write(f"**Title:** {role.get('title', '—')}")
                st.write(f"**Employer:** {role.get('employer', '—')}")
                st.write(f"**Since:** {role.get('start_date', '—')}")
                if role.get("sectors"):
                    st.write("**Sectors:** " + ", ".join(role["sectors"]))

            with col_p2:
                st.subheader("Education")
                st.write(f"**University:** {edu.get('university', '—')}")
                st.write(f"**Degree:** {edu.get('degree', '—')} ({edu.get('grade', '—')})")
                diss = edu.get("dissertation", {})
                if diss.get("prize"):
                    st.write(f"**Prize:** {diss['prize']}")

                st.subheader("Skills")
                for skill in role.get("skills", []):
                    st.write(f"- {skill}")

            targets = profile_data.get("target_roles", [])
            if targets:
                with st.expander("Target roles"):
                    for t in targets:
                        st.write(f"- {t}")
        else:
            st.info("profile.yaml not found. Create it using the editor below.")

        st.divider()
        st.subheader("Edit profile.yaml")
        raw_profile = profile_path.read_text(encoding="utf-8") if profile_path.exists() else ""
        edited_profile = st.text_area(
            "profile_yaml_editor",
            value=raw_profile,
            height=400,
            label_visibility="collapsed",
        )
        if st.button("Save Profile", key="save_profile"):
            try:
                _, backup = save_yaml_safe(profile_path, edited_profile, _BACKUPS_DIR)
                msg = "Profile saved."
                if backup:
                    msg += f" Backup: `data/backups/{backup.name}`"
                st.success(msg)
                st.rerun()
            except ValueError as exc:
                st.error(f"Invalid YAML — file not saved. Error: {exc}")

    # ── Approved Claims ────────────────────────────────────────────────────────

    with ptab_claims:
        claims_path = DATA_DIR / "approved_claims.yaml"

        if claims_path.exists():
            claims_data = load_yaml(claims_path)
            approved = claims_data.get("approved_claims", {})
            forbidden = claims_data.get("forbidden_claims", [])

            st.subheader("Approved claims")
            st.caption("These can be used verbatim on applications and CVs.")
            if isinstance(approved, dict):
                for key, val in approved.items():
                    if isinstance(val, dict):
                        with st.expander(f"**{key}**"):
                            st.success(val.get("claim", ""))
                            contexts = val.get("contexts", [])
                            if contexts:
                                st.caption("Use in: " + " · ".join(contexts))
                    else:
                        st.success(str(val))

            st.divider()
            st.subheader("Forbidden claims")
            st.caption("Must NOT appear on any CV or application — enforced by the claim verifier.")
            for f_claim in (forbidden or []):
                st.error(f"🚫 {f_claim}")
        else:
            st.info("approved_claims.yaml not found.")

        st.divider()
        st.subheader("Edit approved_claims.yaml")
        raw_claims = claims_path.read_text(encoding="utf-8") if claims_path.exists() else ""
        edited_claims = st.text_area(
            "claims_yaml_editor",
            value=raw_claims,
            height=400,
            label_visibility="collapsed",
        )
        if st.button("Save Claims", key="save_claims"):
            try:
                _, backup = save_yaml_safe(claims_path, edited_claims, _BACKUPS_DIR)
                msg = "Claims file saved."
                if backup:
                    msg += f" Backup: `data/backups/{backup.name}`"
                st.success(msg)
                st.rerun()
            except ValueError as exc:
                st.error(f"Invalid YAML — file not saved. Error: {exc}")

    # ── Answer Bank ────────────────────────────────────────────────────────────

    with ptab_answers:
        answers_path = DATA_DIR / "answer_bank.yaml"

        if answers_path.exists():
            answers_data = load_yaml(answers_path)
            st.subheader("Answer angles")
            st.caption("Pre-approved angles used by the answer drafter. One per question type.")
            for key, val in answers_data.items():
                label = key.replace("_", " ").title()
                if isinstance(val, dict) and "angle" in val:
                    with st.expander(label):
                        st.info(val["angle"])
                else:
                    with st.expander(label):
                        st.write(str(val))
        else:
            st.info("answer_bank.yaml not found.")

        st.divider()
        st.subheader("Edit answer_bank.yaml")
        raw_answers = answers_path.read_text(encoding="utf-8") if answers_path.exists() else ""
        edited_answers = st.text_area(
            "answers_yaml_editor",
            value=raw_answers,
            height=400,
            label_visibility="collapsed",
        )
        if st.button("Save Answer Bank", key="save_answers"):
            try:
                _, backup = save_yaml_safe(answers_path, edited_answers, _BACKUPS_DIR)
                msg = "Answer bank saved."
                if backup:
                    msg += f" Backup: `data/backups/{backup.name}`"
                st.success(msg)
                st.rerun()
            except ValueError as exc:
                st.error(f"Invalid YAML — file not saved. Error: {exc}")

# ══════════════════════════════════════════════════════════════════════════════
# Tab 3: History
# ══════════════════════════════════════════════════════════════════════════════

with tab_history:
    st.title("Application History")
    st.caption(
        "Browse and review all previously generated application packs. "
        "Nothing is regenerated unless you return to the Apply tab."
    )

    from jobos.config import ensure_dirs
    ensure_dirs()
    history_entries = scan_applications(APPLICATIONS_DIR)

    if not history_entries:
        st.info(
            "No application history found yet. "
            "Generate an application pack in the Apply tab first."
        )
    else:
        # ── Selection ──────────────────────────────────────────────────────────
        def _entry_label(e):
            score_str = f"{e.fit_score}/100" if e.fit_score else "—"
            cat_str = f"[{e.category}]" if e.category else ""
            company_role = f"{e.company} — {e.role_title}" if e.role_title else e.company or e.folder_name
            return f"{company_role} · {score_str} {cat_str} · {e.folder_name[:15]}"

        selected_idx = st.selectbox(
            "Select application to review",
            range(len(history_entries)),
            format_func=lambda i: _entry_label(history_entries[i]),
            key="history_selection",
        )
        entry = history_entries[selected_idx]

        st.caption(f"Folder: `{entry.folder_name}`")

        # ── Metadata overview ──────────────────────────────────────────────────
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Fit Score", f"{entry.fit_score}/100" if entry.fit_score else "—")
        m2.metric("Category", entry.category or "—")
        m3.metric("Company", entry.company[:20] if entry.company else "—")
        m4.metric("Role", entry.role_title[:20] if entry.role_title else "—")

        # ── Available files ────────────────────────────────────────────────────
        st.subheader("Available Files")
        file_cols = st.columns(4)
        file_info = [
            ("📋 Pack JSON", entry.has_pack_json),
            ("📄 CV (md)", entry.has_cv_md),
            ("✉️ Cover Letter (md)", entry.has_cl_md),
            ("📝 Answers (md)", entry.has_answers_md),
            ("📄 CV (docx)", entry.has_cv_docx),
            ("✉️ CL (docx)", entry.has_cl_docx),
            ("📦 Pack summary (md)", entry.has_pack_md),
        ]
        for col_i, (label, exists) in enumerate(file_info):
            file_cols[col_i % 4].write("✅ " + label if exists else "⬜ " + label)

        # ── Status from tracker ────────────────────────────────────────────────
        if entry.company and entry.role_title:
            tracker_records = get_applications(limit=200)
            matching = [
                r for r in tracker_records
                if r["company"] == entry.company and r["role_title"] == entry.role_title
            ]
            if matching:
                record = matching[0]
                st.divider()
                current_status = record["status"]
                current_idx = _STATUSES.index(current_status) if current_status in _STATUSES else 0
                new_status = st.selectbox(
                    "Application status",
                    options=_STATUSES,
                    index=current_idx,
                    key=f"hist_status_{record['id']}_{selected_idx}",
                )
                if new_status != current_status:
                    update_status(record["id"], new_status)
                    st.success(f"Status updated to: **{new_status}**")
                    st.rerun()

        # ── Full pack review ───────────────────────────────────────────────────
        if entry.has_pack_json:
            hist_pack = load_pack_from_folder(entry.path)
            if hist_pack is not None:
                st.divider()
                st.subheader("Application Pack Review")

                hist_job = hist_pack.parsed_job
                hist_fit = hist_pack.fit_score
                hist_ct = hist_pack.cv_tailor

                if hist_job.location:
                    st.caption(f"Location: {hist_job.location}")
                if hist_job.platform:
                    st.caption(f"Platform: {hist_job.platform}")

                st.write("**Strategy:**", hist_fit.application_strategy)

                col_str, col_wk = st.columns(2)
                with col_str:
                    st.write("**Strengths**")
                    for s in hist_fit.strengths:
                        st.write(f"- {s}")
                with col_wk:
                    st.write("**Review points**")
                    for w in hist_pack.risks_to_review or hist_fit.weaknesses:
                        st.write(f"- {w}")

                if hist_job.red_flags:
                    with st.expander(f"Red flags ({len(hist_job.red_flags)})"):
                        for flag in hist_job.red_flags:
                            st.write(f"- {flag}")

                # CV tailoring
                with st.expander("CV tailoring suggestions", expanded=False):
                    st.write("**Positioning:**", hist_ct.positioning_angle)
                    st.write("**CV summary draft:**")
                    st.info(hist_ct.cv_summary_draft)
                    if hist_ct.approved_claims_usable:
                        st.write("**✅ Approved claims:**")
                        for c in hist_ct.approved_claims_usable:
                            st.success(c)
                    if hist_ct.adjacent_experience:
                        st.write("**🟡 Adjacent / careful claims:**")
                        for c in hist_ct.adjacent_experience:
                            st.warning(c)
                    if hist_ct.unsupported_claims:
                        st.write("**🚨 Do NOT claim:**")
                        for c in hist_ct.unsupported_claims:
                            st.error(c)

                # Draft answers
                if hist_pack.answers:
                    hist_approved = load_yaml(DATA_DIR / "approved_claims.yaml") if (DATA_DIR / "approved_claims.yaml").exists() else {}
                    hist_adjacent = hist_approved.get("adjacent_claims", {})
                    with st.expander(f"Draft answers ({len(hist_pack.answers)})"):
                        for ans in hist_pack.answers:
                            vr = verify_answer(
                                ans.answer,
                                hist_approved.get("approved_claims", {}),
                                hist_approved.get("forbidden_claims", []),
                                adjacent_claims=hist_adjacent,
                            )
                            badge = _RISK_BADGE[vr.final_risk_level]
                            st.write(f"**Q: {ans.question}**")
                            st.write(ans.answer)
                            st.caption(f"Claim check: {badge} · Confidence: {ans.confidence}")
                            st.write("---")
            else:
                st.warning("Could not parse application_pack.json for this entry.")

        # ── Markdown file previews ─────────────────────────────────────────────
        st.divider()
        st.subheader("Document Previews")

        if entry.has_cv_md:
            with st.expander("📄 Tailored CV (markdown)", expanded=False):
                st.markdown(read_file_content(entry.path / "tailored_cv.md"))

        if entry.has_cl_md:
            with st.expander("✉️ Cover Letter (markdown)", expanded=False):
                st.markdown(read_file_content(entry.path / "cover_letter.md"))

        if entry.has_answers_md:
            with st.expander("📝 Application Answers (markdown)", expanded=False):
                st.markdown(read_file_content(entry.path / "application_answers.md"))

        if entry.has_pack_md:
            with st.expander("📦 Application Pack Summary", expanded=False):
                st.markdown(read_file_content(entry.path / "application_pack.md"))

        if not any([entry.has_cv_md, entry.has_cl_md, entry.has_answers_md, entry.has_pack_md]):
            st.caption("No markdown files found in this application folder.")


# ══════════════════════════════════════════════════════════════════════════════
# Tab 4: Templates & Exports
# ══════════════════════════════════════════════════════════════════════════════

with tab_exports:
    st.title("Templates & Exports")
    st.caption(
        "Upload your own .docx CV and cover letter templates with {{ token }} placeholders. "
        "JobOS will fill them with approved content and write DOCX files alongside the markdown bundle."
    )
    st.info(
        "Templates are saved locally to `data/local_templates/` and are excluded from Git. "
        "Generated DOCX files are written into the same `outputs/applications/` folder as the markdown bundle."
    )

    col_cv_up, col_cl_up = st.columns(2)

    _cv_template_path = _LOCAL_TEMPLATES_DIR / "cv_template.docx"
    _cl_template_path = _LOCAL_TEMPLATES_DIR / "cover_letter_template.docx"

    # ── CV template upload ─────────────────────────────────────────────────────

    with col_cv_up:
        st.subheader("CV Template")
        st.caption(
            "Must contain these placeholders:\n"
            + "  ".join(f"`{{{{ {p} }}}}`" for p in CV_PLACEHOLDERS)
        )

        uploaded_cv = st.file_uploader(
            "Upload CV .docx template",
            type=["docx"],
            key="cv_template_upload",
        )
        if uploaded_cv is not None:
            _cv_template_path.write_bytes(uploaded_cv.read())
            st.success(f"Saved to `data/local_templates/cv_template.docx`")

        if _cv_template_path.exists():
            cv_diag = diagnose_template(_cv_template_path, CV_PLACEHOLDERS)
            if cv_diag["is_valid"]:
                st.success("CV template: all required placeholders found.")
            else:
                st.error(
                    "CV template missing placeholders: "
                    + ", ".join(f"`{{{{ {p} }}}}`" for p in cv_diag["missing"])
                )
            with st.expander("Template diagnostics", expanded=not cv_diag["is_valid"]):
                if cv_diag["found_body"]:
                    st.write("**Found in body paragraphs:**")
                    st.write(", ".join(f"`{{{{ {p} }}}}`" for p in cv_diag["found_body"]))
                if cv_diag["found_table"]:
                    st.write("**Found in table cells:**")
                    st.write(", ".join(f"`{{{{ {p} }}}}`" for p in cv_diag["found_table"]))
                if cv_diag["missing"]:
                    st.error("**Missing (required):** " + ", ".join(f"`{{{{ {p} }}}}`" for p in cv_diag["missing"]))
                st.caption(
                    "For exact formatting, place placeholders inside your desired formatted Word "
                    "template. The renderer replaces placeholders while preserving template style."
                )
        else:
            st.caption("No CV template uploaded yet.")

    # ── Cover letter template upload ───────────────────────────────────────────

    with col_cl_up:
        st.subheader("Cover Letter Template")
        st.caption(
            "Must contain these placeholders:\n"
            + "  ".join(f"`{{{{ {p} }}}}`" for p in CL_PLACEHOLDERS)
        )

        uploaded_cl = st.file_uploader(
            "Upload cover letter .docx template",
            type=["docx"],
            key="cl_template_upload",
        )
        if uploaded_cl is not None:
            _cl_template_path.write_bytes(uploaded_cl.read())
            st.success(f"Saved to `data/local_templates/cover_letter_template.docx`")

        if _cl_template_path.exists():
            cl_diag = diagnose_template(_cl_template_path, CL_PLACEHOLDERS)
            if cl_diag["is_valid"]:
                st.success("Cover letter template: all required placeholders found.")
            else:
                st.error(
                    "Cover letter template missing placeholders: "
                    + ", ".join(f"`{{{{ {p} }}}}`" for p in cl_diag["missing"])
                )
            with st.expander("Template diagnostics", expanded=not cl_diag["is_valid"]):
                if cl_diag["found_body"]:
                    st.write("**Found in body paragraphs:**")
                    st.write(", ".join(f"`{{{{ {p} }}}}`" for p in cl_diag["found_body"]))
                if cl_diag["found_table"]:
                    st.write("**Found in table cells:**")
                    st.write(", ".join(f"`{{{{ {p} }}}}`" for p in cl_diag["found_table"]))
                if cl_diag["missing"]:
                    st.error("**Missing (required):** " + ", ".join(f"`{{{{ {p} }}}}`" for p in cl_diag["missing"]))
                st.caption(
                    "For exact formatting, place placeholders inside your desired formatted Word "
                    "template. The renderer replaces placeholders while preserving template style."
                )
        else:
            st.caption("No cover letter template uploaded yet.")

    st.divider()

    # ── Generate DOCX outputs ──────────────────────────────────────────────────

    st.subheader("Generate DOCX Outputs")

    bundle_result = st.session_state.get("bundle")
    pack_for_docx = st.session_state.get("pack")

    templates_ready = _cv_template_path.exists() and _cl_template_path.exists()
    pack_ready = pack_for_docx is not None and bundle_result is not None

    if not pack_ready:
        st.info("Generate an application pack in the Apply tab first, then come back here to export DOCX.")
    elif not templates_ready:
        st.warning("Upload both templates above before generating DOCX outputs.")
    else:
        cv_ok, _ = validate_template(_cv_template_path, CV_PLACEHOLDERS)  # noqa: F841
        cl_ok, _ = validate_template(_cl_template_path, CL_PLACEHOLDERS)  # noqa: F841

        if not cv_ok or not cl_ok:
            st.error("Fix placeholder errors in the templates above before generating.")
        else:
            if st.button("Generate DOCX Outputs", type="primary"):
                try:
                    cv_master_data = load_cv_master()
                    approved_data_for_docx = st.session_state.get("approved_data", {})
                    profile_data_for_docx = (
                        load_yaml(DATA_DIR / "profile.yaml")
                        if (DATA_DIR / "profile.yaml").exists()
                        else {}
                    )

                    bundle_out_dir = Path(bundle_result.out_dir)
                    cv_docx_out = bundle_out_dir / "tailored_cv.docx"
                    cl_docx_out = bundle_out_dir / "cover_letter.docx"

                    with st.spinner("Rendering DOCX files…"):
                        render_cv_docx(
                            _cv_template_path,
                            pack_for_docx,
                            profile_data_for_docx,
                            cv_master_data,
                            cv_docx_out,
                        )
                        render_cover_letter_docx(
                            _cl_template_path,
                            pack_for_docx,
                            profile_data_for_docx,
                            cv_master_data,
                            cl_docx_out,
                        )

                    st.session_state["docx_cv_path"] = str(cv_docx_out)
                    st.session_state["docx_cl_path"] = str(cl_docx_out)
                    st.success("DOCX files generated.")
                except (TemplateNotFoundError, MissingPlaceholdersError) as exc:
                    st.error(f"Template error: {exc}")
                except Exception as exc:
                    st.error(f"Generation failed: {exc}")

    docx_cv_path = st.session_state.get("docx_cv_path")
    docx_cl_path = st.session_state.get("docx_cl_path")

    if docx_cv_path or docx_cl_path:
        st.divider()
        st.subheader("Generated DOCX Files")
        st.caption(
            "These files are local only and excluded from Git. "
            "Review every claim before using in a real application."
        )
        if docx_cv_path and Path(docx_cv_path).exists():
            st.write(f"📄 **Tailored CV:** `{docx_cv_path}`")
        if docx_cl_path and Path(docx_cl_path).exists():
            st.write(f"✉️ **Cover Letter:** `{docx_cl_path}`")
