# Amber Jackson — Career Search Index

This repository is the autonomous backend + GitHub Pages host for Amber's career-search command center.

## What runs automatically

### Weekdays — Career Tracker Monitor
- recomputes Zombie status from `applied_at`
- uses a **10 U.S. business-day** clock
- excludes weekends and U.S. federal holidays
- checks direct links for priority APPLY ASAP / STRETCH / SAFETY NET roles
- only auto-closes a role on a strong signal such as HTTP 404/410 or an explicit closure phrase
- never treats a blocked/403/429 response as proof that a job is closed
- updates `data/jobs.json`, the embedded job data in `index.html`, and `reports/alerts-latest.md`
- opens a GitHub Issue when a new Zombie or closure alert first appears

### Sunday — Weekly Career Search Audit
Validates the source-of-truth math, including:
- 47 confirmed applications
- Zombie is a subset of pending, never an extra application
- 5 interview-request events
- 3 distinct positions actually interviewed
- 4 completed interview meetings
- 0 confirmed offers
- no duplicate tracker ranks
- actionable open roles have status-check timestamps

The interview history in `data/pipeline.json` preserves:
- Oil-Dri: interview requested; role filled before the recruiter screen
- Combined Metals: HR screen + Hiring Manager/Director of IT interview; CFO is only a potential next step
- International Motors — Procurement Digitalization: Hiring Manager interview
- International Motors — Supply Chain Technology & Operations: panel interview

### GitHub Pages
Every push to `main` redeploys `index.html` through GitHub Pages.

## Files

- `index.html` — the pink/purple command center
- `data/jobs.json` — structured 184-role source-of-truth data
- `data/pipeline.json` — application/interview denominator and history
- `data/monitor-config.json` — monitor policy and thresholds
- `scripts/monitor.py` — Zombie + current-role link monitor
- `scripts/audit.py` — consistency and funnel-math audit
- `scripts/scout.py` — optional external new-role discovery hook
- `.github/workflows/monitor.yml` — weekday monitor
- `.github/workflows/weekly-audit.yml` — Sunday audit
- `.github/workflows/pages.yml` — Pages deploy
- `.github/workflows/scout.yml` — optional M/W/F scouting hook

## First-time GitHub setup

1. Create a repository, for example `amber-career-search-index`, and upload/push this folder to its `main` branch.
2. In **Settings → Pages**, select **GitHub Actions** as the Pages source.
3. In **Settings → Actions → General**, make sure workflows are allowed to run and the repository workflow token can write repository contents/issues if GitHub asks for that permission.
4. Run **Career Tracker Monitor** once from the Actions tab to validate the setup.

## Autonomous new-role discovery

The deterministic core does **not** need paid API keys.

Finding brand-new jobs on the internet and robustly scoring the JD against Amber's evidence bank is different: GitHub Actions does not inherit ChatGPT's search/reasoning tools or a ChatGPT Plus subscription. The included scout workflow therefore stays safe by default.

If Amber later wants completely autonomous new-role scouting inside GitHub, configure repository Actions secrets for a web-search provider and a model API. The scaffold currently recognizes:

- `TAVILY_API_KEY`
- `OPENAI_API_KEY`

The scout script is intentionally non-spending until its exact search/scoring prompt is explicitly enabled.

## Status philosophy

The automation is conservative on purpose. A job page returning HTTP 200 is **reachable**, not automatically proven open. A role is auto-closed only on a strong closure signal. That prevents a flaky employer site or bot block from trashing the live tracker.
