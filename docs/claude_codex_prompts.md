# Prompts for Claude Code / Codex

## Prompt 1 — Review the MVP

Read this codebase and explain the current architecture. Do not change files yet. Identify bugs, security issues, and places where the agent could make unsupported job-application claims.

## Prompt 2 — Improve structured outputs

Improve `jobos/llm_client.py` and the agent prompts so every agent returns reliable Pydantic-validated structured output. Keep all LLM calls inside `llm_client.py`. Do not add browser automation yet. Run the sample job through `python apply.py run` and fix any errors.

## Prompt 3 — Add tests

Add pytest tests for:
- offline job parsing
- offline fit scoring
- compliance field classification
- claim verification detecting forbidden claims
Do not call external APIs in tests.

## Prompt 4 — Add tracker table to Streamlit

Update `app.py` so the dashboard shows recent application records from SQLite and lets me update status manually. Do not store sensitive outputs in GitHub.

## Prompt 5 — Add CV tailoring suggestions

Create a new `cv_tailor_agent.py` that suggests CV positioning, bullets to emphasise, bullets to de-emphasise, and risky claims to avoid. Use Pydantic schemas. Do not modify any actual CV files yet.

## Prompt 6 — Add form mapping, no browser filling

Create a form mapping module that accepts a list of field labels and classifies each as green, amber or red using the compliance agent. Output a reviewable field plan. Do not open a browser.

## Prompt 7 — Add Greenhouse filler prototype

Create a prototype Playwright Greenhouse filler that:
- opens a URL
- fills only green fields from an approved field plan
- never clicks submit
- logs fields it could not fill
- stops for manual review
Do not support Workday yet.

## Prompt 8 — Security pass

Review the repository for secrets, sensitive files, unsafe browser state handling and accidental auto-submit behaviour. Update `.gitignore` if needed. Do not remove useful source files.
