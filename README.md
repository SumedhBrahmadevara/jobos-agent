# JobOS Application Agent

A safe, human-in-the-loop job application operating system.

This MVP does **not** auto-submit applications. It builds the truth-and-quality layer first:

1. Parse a job description
2. Score fit
3. Draft tailored answers
4. Verify risky claims
5. Save an application pack
6. Save a tracker entry

Browser automation comes later, after the application-quality layer works.

## Why this architecture

The main risk in job automation is not form filling; it is sending generic, misleading, inconsistent or reputation-damaging applications. So JobOS starts with a controlled workflow:

```text
Job description
  -> Job Parser Agent
  -> Fit Scoring Agent
  -> Answer Drafting Agent
  -> Claim Verification Agent
  -> Tracker
  -> Human review
```

## Setup on Windows PowerShell

```powershell
cd $HOME
mkdir jobos-agent
cd jobos-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Then open `.env` and add your API key:

```text
OPENAI_API_KEY=your_key_here
JOBOS_MODEL=gpt-5.5
JOBOS_OFFLINE_MODE=false
```

If you do not add an API key, the app runs in offline demo mode.

## Run the command-line version

```powershell
python apply.py
```

Outputs are saved to:

```text
outputs/applications/
```

## Run the dashboard

```powershell
streamlit run app.py
```

Then open the local URL Streamlit gives you.

## GitHub setup

Create a **private** GitHub repo, then:

```powershell
git init
git add .
git commit -m "Initial JobOS agent MVP"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/jobos-agent.git
git push -u origin main
```

Do not commit `.env`, outputs, browser state, CV PDFs, cookies or personal documents.

## What to build next

1. Improve answer quality using real applications
2. Add tests with saved sample jobs
3. Add CV tailoring suggestions
4. Add compliance field mapping
5. Add Greenhouse/Lever browser filling
6. Add Workday later
7. Add final human approval workflow

## Claude Code / Codex usage

Use Claude Code or Codex for implementation, but keep tasks small. Ask for one feature at a time, then run the app and test.

See `docs/claude_codex_prompts.md` for ready-to-use prompts.
