# Claude Code Instructions for JobOS

You are helping build JobOS, a human-in-the-loop job application agent.

## Core principle

Automate admin, not judgement. Never build blind mass-auto-apply behaviour.

## Safety rules

- Do not add auto-submit without explicit user approval.
- Do not bypass CAPTCHA, login protections or application-site restrictions.
- Do not infer or fill sensitive demographic/legal fields automatically.
- Do not store passwords, cookies, browser state or API keys in GitHub.
- Do not commit `.env`, outputs, CV files, personal documents, or SQLite databases.
- Every generated application answer should be reviewed against approved claims.

## Product direction

Phase 1: truth-and-quality layer.
Phase 2: tracker and dashboard.
Phase 3: form mapping.
Phase 4: safe browser filling.
Phase 5: human-approved submission.

## Coding style

- Keep agents small and specialist.
- Use Pydantic schemas for agent outputs.
- Keep all LLM API calls inside `jobos/llm_client.py`.
- Use simple Python before adding orchestration frameworks.
- Prefer readable, testable code.

## Definition of done for any feature

- It runs locally.
- It does not expose secrets.
- It has a clear human review path for risky outputs.
- It does not make unsupported career claims.
