# JobOS Build Plan

## Phase 1 — Safe MVP

Goal: Generate high-quality application packs from a job description.

Agents:

- Job Parser Agent
- Fit Scoring Agent
- Answer Drafting Agent
- Claim Verification Agent
- Tracker Agent

Done when:

- `python apply.py run` creates an application pack.
- The pack includes fit score, strategy, answers and review risks.
- SQLite tracker stores a drafted application.

## Phase 2 — Dashboard

Goal: Make it easier to paste jobs, review answers and compare roles.

Add:

- Streamlit dashboard
- applications table
- answer editing
- status updates

## Phase 3 — Form Mapping

Goal: Understand application forms before filling them.

Add:

- Field extraction
- Green/amber/red risk classification
- Mapping profile fields to form fields
- Human review screen

## Phase 4 — Browser Filling

Goal: Fill low-risk fields on easy platforms.

Start with:

- Greenhouse
- Lever
- Ashby

Avoid initially:

- Workday
- CAPTCHA
- auto-submit

## Phase 5 — Human-Approved Submission

Goal: The agent can submit only after explicit approval.

Rules:

- Red fields must be manually completed.
- Amber fields require approval.
- Submit button requires explicit final approval.
- Tracker logs exact submitted answers.
