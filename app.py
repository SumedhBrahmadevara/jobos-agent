from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st

from apply import build_pack
from jobos.config import DATA_DIR, APPLICATIONS_DIR, ensure_dirs
from jobos.llm_client import llm_is_available
from jobos.io import write_json, write_text, load_yaml
from jobos.schemas import TrackerRecord
from jobos.tracker import save_application, get_applications, update_status
from jobos.agents.claim_verifier_agent import verify_answer
from jobos.agents.compliance_agent import classify_field

_STATUSES = ["drafted", "applied", "screening", "interview", "offer", "rejected", "withdrawn"]

_RISK_BADGE = {"low": "✅ low", "medium": "⚠️ medium", "high": "🚨 high"}
_FIELD_BADGE = {"green": "🟢 green", "amber": "🟡 amber", "red": "🔴 red"}
_CAT_COLOR = {"A": "green", "B": "blue", "C": "orange", "reject": "red"}

st.set_page_config(page_title="JobOS", layout="wide", page_icon="📋")

# ── Session state ─────────────────────────────────────────────────────────────
# Pack and save metadata persist across Streamlit reruns (e.g. sidebar status
# changes) so the user does not lose generated results.
if "pack" not in st.session_state:
    st.session_state["pack"] = None
if "out_dir_name" not in st.session_state:
    st.session_state["out_dir_name"] = None
if "app_id" not in st.session_state:
    st.session_state["app_id"] = None
if "approved_data" not in st.session_state:
    st.session_state["approved_data"] = {}

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

            st.write("")  # breathing room between entries

# ── Main: inputs ──────────────────────────────────────────────────────────────

st.title("JobOS Application Agent")
st.caption("Safe MVP — parse → score fit → draft answers → verify claims. No auto-submit.")

is_llm = llm_is_available()
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

# ── Pipeline ──────────────────────────────────────────────────────────────────

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
    out_dir.mkdir(parents=True, exist_ok=True)

    write_json(out_dir / "application_pack.json", pack.model_dump())

    md = [f"# {pack.parsed_job.company} — {pack.parsed_job.role_title}"]
    md += [f"\nFit: **{pack.fit_score.overall_score}/100 ({pack.fit_score.category})**"]
    md += [f"\n**Strategy:** {pack.fit_score.application_strategy}\n"]
    md += ["\n## Answers"]
    for ans in pack.answers:
        md += [
            f"\n### {ans.question}",
            ans.answer,
            f"\n_Confidence: {ans.confidence} | Review needed: {ans.needs_human_review}_",
        ]
    write_text(out_dir / "application_pack.md", "\n".join(md))

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

    approved_data = (
        load_yaml(DATA_DIR / "approved_claims.yaml")
        if (DATA_DIR / "approved_claims.yaml").exists()
        else {}
    )

    st.session_state["pack"] = pack
    st.session_state["out_dir_name"] = out_dir.name
    st.session_state["app_id"] = app_id
    st.session_state["approved_data"] = approved_data

# ── Results display ───────────────────────────────────────────────────────────

pack = st.session_state["pack"]

if pack is not None:
    st.divider()

    # Header
    st.header(f"{pack.parsed_job.company} — {pack.parsed_job.role_title}")
    if pack.parsed_job.location:
        st.caption(f"Location: {pack.parsed_job.location}")
    if pack.parsed_job.platform:
        st.caption(f"Platform: {pack.parsed_job.platform}")

    # Fit score metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Fit score", f"{pack.fit_score.overall_score} / 100")
    m2.metric("Category", pack.fit_score.category)
    m3.metric("Seniority", pack.parsed_job.seniority_level or "unknown")
    m4.metric("Referral needed", "Yes" if pack.fit_score.needs_referral else "No")

    st.write("**Strategy:**", pack.fit_score.application_strategy)

    # Strengths and review points
    col_str, col_wk = st.columns(2)
    with col_str:
        st.write("**Strengths**")
        for s in pack.fit_score.strengths:
            st.write(f"- {s}")
    with col_wk:
        st.write("**Review points**")
        for w in pack.risks_to_review or pack.fit_score.weaknesses:
            st.write(f"- {w}")

    # Red flags and cover letter in collapsibles
    if pack.parsed_job.red_flags:
        with st.expander(f"Red flags from job description ({len(pack.parsed_job.red_flags)})"):
            for flag in pack.parsed_job.red_flags:
                st.write(f"- {flag}")

    with st.expander("Cover letter outline"):
        for line in pack.cover_letter_outline:
            st.write(f"- {line}")

    # ── CV Tailoring Suggestions ──────────────────────────────────────────────

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
            if vr.final_risk_level == "low":
                st.success(f"Claim check: {badge} — no issues detected in CV summary.")
            else:
                risk_fn = st.error if vr.final_risk_level == "high" else st.warning
                risk_fn(f"Claim check: {badge} — review CV summary before using.")
                if vr.unsupported_claims:
                    st.error("Unsupported: " + ", ".join(f"`{c}`" for c in vr.unsupported_claims))
                if vr.exaggerated_claims:
                    st.error("Forbidden / exaggerated: " + ", ".join(f"`{c}`" for c in vr.exaggerated_claims))
                if vr.generic_phrases:
                    st.warning("Generic phrases: " + ", ".join(f"`{p}`" for p in vr.generic_phrases))
                if vr.recommended_edits:
                    for edit in vr.recommended_edits:
                        st.info(f"Suggested edit: {edit}")

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
        st.caption("Use verbatim.")
        for c in ct.approved_claims_usable:
            st.success(c)
    with col_adj:
        st.write("**🟡 Adjacent experience**")
        st.caption("Frame carefully — do not overstate.")
        for c in ct.adjacent_experience:
            st.warning(c)
    with col_no:
        st.write("**🚨 Do NOT claim**")
        st.caption("Must not appear on CV.")
        for c in ct.unsupported_claims:
            st.error(c)

    if ct.risks_and_gaps:
        with st.expander("Risks and gaps to address"):
            for r in ct.risks_and_gaps:
                st.write(f"- {r}")

    # ── Draft answers ─────────────────────────────────────────────────────────

    st.divider()
    st.subheader("Draft Answers")

    if not pack.answers:
        st.info("No application questions were provided. Add questions above and regenerate.")
    else:
        approved_data: dict = st.session_state["approved_data"]

        for ans in pack.answers:
            # Run claim verification for display (offline: instant; LLM: one extra call)
            verification = verify_answer(
                ans.answer,
                approved_data.get("approved_claims", {}),
                approved_data.get("forbidden_claims", []),
            )
            field_risk = classify_field(ans.question)

            expander_label = (
                f"{ans.question}  "
                f"| claim {_RISK_BADGE[verification.final_risk_level]}  "
                f"| field {_FIELD_BADGE[field_risk.risk_level]}"
            )

            # Expand automatically when review is needed
            with st.expander(expander_label, expanded=ans.needs_human_review):

                # Answer text
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

                # Claim check detail
                st.write("---")
                st.write("**Claim check**")
                has_issues = (
                    verification.unsupported_claims
                    or verification.exaggerated_claims
                    or verification.generic_phrases
                )
                if not has_issues:
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
                    if verification.recommended_edits:
                        for edit in verification.recommended_edits:
                            st.info(f"Suggested edit: {edit}")

                # Compliance note
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

    # ── Save confirmation ─────────────────────────────────────────────────────

    st.divider()
    out_dir_name = st.session_state["out_dir_name"]
    app_id = st.session_state["app_id"]
    if out_dir_name:
        st.success(
            f"Saved to `outputs/applications/{out_dir_name}` · "
            f"Tracker ID: {app_id}"
        )
