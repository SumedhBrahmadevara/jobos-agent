from __future__ import annotations

from pathlib import Path

import streamlit as st

from apply import build_pack
from jobos.config import DATA_DIR, APPLICATIONS_DIR, ensure_dirs
from jobos.llm_client import llm_is_available
from jobos.io import write_json, write_text

st.set_page_config(page_title="JobOS Agent", layout="wide")
st.title("JobOS Application Agent")
st.caption("Safe MVP: parse role, score fit, draft answers, flag risks. Browser automation comes later.")

mode = "LLM mode" if llm_is_available() else "offline demo mode"
st.info(f"Running in {mode}.")

job_text = st.text_area("Paste job description", value=(DATA_DIR / "sample_job.txt").read_text(encoding="utf-8"), height=300)
questions_text = st.text_area("Application questions, one per line", value=(DATA_DIR / "sample_questions.txt").read_text(encoding="utf-8"), height=140)

if st.button("Generate application pack"):
    ensure_dirs()
    temp_job = DATA_DIR / "_temp_job.txt"
    temp_questions = DATA_DIR / "_temp_questions.txt"
    temp_job.write_text(job_text, encoding="utf-8")
    temp_questions.write_text(questions_text, encoding="utf-8")

    pack = build_pack(temp_job, temp_questions)
    st.subheader(f"{pack.parsed_job.company} — {pack.parsed_job.role_title}")
    st.metric("Fit score", f"{pack.fit_score.overall_score}/100", pack.fit_score.category)
    st.write("**Strategy:**", pack.fit_score.application_strategy)

    col1, col2 = st.columns(2)
    with col1:
        st.write("### Strengths")
        for x in pack.fit_score.strengths:
            st.write("-", x)
    with col2:
        st.write("### Review points")
        for x in pack.risks_to_review or pack.fit_score.weaknesses:
            st.write("-", x)

    st.write("## Draft answers")
    for ans in pack.answers:
        with st.expander(ans.question, expanded=True):
            st.write(ans.answer)
            st.caption(f"Confidence: {ans.confidence}; review needed: {ans.needs_human_review}; {ans.review_reason or ''}")

    out_dir = APPLICATIONS_DIR / "streamlit_latest"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "application_pack.json", pack.model_dump())
    write_text(out_dir / "application_pack.md", "\n\n".join([a.answer for a in pack.answers]))
    st.success(f"Saved latest output to {out_dir}")
