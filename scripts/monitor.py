#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from calendar import monthcalendar, MONDAY, THURSDAY
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    requests = None

ROOT = Path(__file__).resolve().parents[1]
JOBS_PATH = ROOT / "data" / "jobs.json"
PIPELINE_PATH = ROOT / "data" / "pipeline.json"
CONFIG_PATH = ROOT / "data" / "monitor-config.json"
INDEX_PATH = ROOT / "index.html"
ALERTS_PATH = ROOT / "reports" / "alerts-latest.md"
STATUS_PATH = ROOT / "data" / "monitor-status.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    weeks = monthcalendar(year, month)
    days = [week[weekday] for week in weeks if week[weekday] != 0]
    return date(year, month, days[n - 1])


def last_weekday(year: int, month: int, weekday: int) -> date:
    weeks = monthcalendar(year, month)
    days = [week[weekday] for week in weeks if week[weekday] != 0]
    return date(year, month, days[-1])


def observed(d: date) -> date:
    if d.weekday() == 5:  # Saturday -> Friday
        return d - timedelta(days=1)
    if d.weekday() == 6:  # Sunday -> Monday
        return d + timedelta(days=1)
    return d


def us_federal_holidays(year: int) -> set[date]:
    return {
        observed(date(year, 1, 1)),
        nth_weekday(year, 1, MONDAY, 3),
        nth_weekday(year, 2, MONDAY, 3),
        last_weekday(year, 5, MONDAY),
        observed(date(year, 6, 19)),
        observed(date(year, 7, 4)),
        nth_weekday(year, 9, MONDAY, 1),
        nth_weekday(year, 10, MONDAY, 2),
        observed(date(year, 11, 11)),
        nth_weekday(year, 11, THURSDAY, 4),
        observed(date(year, 12, 25)),
    }


def business_days_elapsed(start: date, end: date) -> int:
    if end <= start:
        return 0
    holidays = set()
    for y in range(start.year, end.year + 1):
        holidays |= us_federal_holidays(y)
    count = 0
    d = start + timedelta(days=1)
    while d <= end:
        if d.weekday() < 5 and d not in holidays:
            count += 1
        d += timedelta(days=1)
    return count


def chicago_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Chicago"))
    except Exception:
        return datetime.now(timezone.utc)


def iso_now() -> str:
    return chicago_now().isoformat(timespec="seconds")


def is_priority_open_job(job: dict) -> bool:
    return (
        job.get("status_class") == "status-queue"
        and job.get("strategy_bucket") in {"APPLY ASAP", "STRETCH", "SAFETY NET"}
        and not job.get("duplicate_of")
    )


def strong_closed_signal(status_code: int | None, body: str, closure_phrases: list[str]) -> str | None:
    if status_code in {404, 410}:
        return f"HTTP {status_code}"
    low = re.sub(r"\s+", " ", body.lower())[:700000]
    for phrase in closure_phrases:
        if phrase.lower() in low:
            return phrase
    return None


def check_url(url: str, timeout: int, closure_phrases: list[str]) -> dict:
    if not requests:
        return {"result": "CHECK_SKIPPED", "reason": "requests not installed"}
    if not url or not url.startswith(("http://", "https://")):
        return {"result": "CHECK_SKIPPED", "reason": "no direct URL"}
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AmberCareerTracker/1.0; +https://github.com/)"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        text = resp.text if "text" in resp.headers.get("content-type", "") or resp.text else ""
        closed = strong_closed_signal(resp.status_code, text, closure_phrases)
        if closed:
            return {
                "result": "CLOSED_SIGNAL",
                "reason": closed,
                "status_code": resp.status_code,
                "final_url": resp.url,
            }
        if resp.status_code == 200:
            return {
                "result": "REACHABLE",
                "reason": "HTTP 200; no strong closure phrase detected",
                "status_code": 200,
                "final_url": resp.url,
            }
        if resp.status_code in {401, 403, 429}:
            return {
                "result": "CHECK_BLOCKED",
                "reason": f"HTTP {resp.status_code}",
                "status_code": resp.status_code,
                "final_url": resp.url,
            }
        return {
            "result": "CHECK_INCONCLUSIVE",
            "reason": f"HTTP {resp.status_code}",
            "status_code": resp.status_code,
            "final_url": resp.url,
        }
    except Exception as exc:
        return {"result": "CHECK_FAILED", "reason": str(exc)[:300]}


def alert_key(kind: str, job: dict, detail: str) -> str:
    raw = f'{kind}|{job.get("company")}|{job.get("title")}|{detail}'
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def apply_zombie_logic(jobs: list[dict], threshold: int, today: date, alerts: list[dict]):
    for job in jobs:
        job["zombie"] = False
        job["zombie_business_days"] = None
        if job.get("status_class") != "status-pending":
            continue
        if job.get("completed_interview_count", 0) > 0:
            continue
        applied = job.get("applied_at")
        if not applied:
            continue
        try:
            applied_date = date.fromisoformat(applied[:10])
        except Exception:
            continue
        days = business_days_elapsed(applied_date, today)
        job["zombie_business_days"] = days
        if days >= threshold:
            job["zombie"] = True
            detail = f"{days} U.S. business days pending"
            key = alert_key("zombie", job, detail)
            if job.get("last_zombie_alert_key") != key:
                alerts.append({
                    "type": "ZOMBIE",
                    "company": job.get("company"),
                    "title": job.get("title"),
                    "detail": detail,
                    "key": key,
                })
                job["last_zombie_alert_key"] = key


def apply_open_role_checks(jobs: list[dict], config: dict, alerts: list[dict]):
    check_cfg = config.get("open_role_check", {})
    if not check_cfg.get("enabled", True):
        return 0
    max_links = int(check_cfg.get("max_links_per_run", 40))
    timeout = int(check_cfg.get("timeout_seconds", 20))
    phrases = check_cfg.get("closure_phrases", [])
    candidates = [j for j in jobs if is_priority_open_job(j) and j.get("link")]
    candidates.sort(key=lambda j: (0 if j.get("strategy_bucket") == "APPLY ASAP" else 1, -(j.get("screen") or 0)))
    checked = 0
    for job in candidates[:max_links]:
        result = check_url(job.get("link", ""), timeout, phrases)
        checked += 1
        job["status_checked_at"] = iso_now()
        job["status_check_source"] = "GitHub Actions HTTP monitor"
        job["last_link_check"] = result
        if result["result"] == "CLOSED_SIGNAL":
            prior = job.get("posting_status")
            detail = result.get("reason", "closed signal")
            job["posting_status"] = "CLOSED_OR_INACTIVE"
            job["live_status"] = f"LIKELY CLOSED — {detail}"
            key = alert_key("closed", job, detail)
            if job.get("last_closed_alert_key") != key and prior != "CLOSED_OR_INACTIVE":
                alerts.append({
                    "type": "ROLE CLOSED",
                    "company": job.get("company"),
                    "title": job.get("title"),
                    "detail": detail,
                    "key": key,
                })
                job["last_closed_alert_key"] = key
        elif result["result"] == "REACHABLE":
            # Do not overclaim. Reachability is not the same as a verified-live requisition.
            if job.get("posting_status") not in {"OPEN_VERIFIED", "CLOSED_OR_INACTIVE"}:
                job["posting_status"] = "OPEN_AT_LAST_CHECK"
    return checked


def patch_embedded_jobs(index_text: str, jobs: list[dict]) -> str:
    payload = json.dumps(jobs, ensure_ascii=False, separators=(",", ":"))
    pattern = re.compile(r"const jobs\s*=\s*\[.*?\];\s*function", re.S)
    match = pattern.search(index_text)
    if not match:
        raise RuntimeError("Could not find embedded jobs payload in index.html")
    replacement = f"const jobs={payload};\nfunction"
    return index_text[:match.start()] + replacement + index_text[match.end():]


def write_alerts(alerts: list[dict], checked: int):
    lines = [
        "# Career tracker automated monitor",
        "",
        f"Run: {iso_now()}",
        f"Priority job links checked: {checked}",
        "",
    ]
    if not alerts:
        lines.append("No new alerts.")
    else:
        for a in alerts:
            lines.append(f'## {a["type"]}: {a["company"]} — {a["title"]}')
            lines.append(a["detail"])
            lines.append("")
    ALERTS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-http", action="store_true", help="Only recompute deterministic state such as Zombies")
    args = parser.parse_args()

    jobs = load_json(JOBS_PATH)
    pipeline = load_json(PIPELINE_PATH)
    config = load_json(CONFIG_PATH)
    alerts: list[dict] = []
    now = chicago_now()

    apply_zombie_logic(jobs, int(config.get("zombie_business_days", 10)), now.date(), alerts)
    checked = 0 if args.skip_http else apply_open_role_checks(jobs, config, alerts)

    for job in jobs:
        job["scheduler_last_run_at"] = iso_now()

    save_json(JOBS_PATH, jobs)
    index_text = INDEX_PATH.read_text(encoding="utf-8")
    INDEX_PATH.write_text(patch_embedded_jobs(index_text, jobs), encoding="utf-8")
    write_alerts(alerts, checked)
    save_json(STATUS_PATH, {
        "last_run_at": iso_now(),
        "priority_links_checked": checked,
        "new_alerts": len(alerts),
        "zombies": sum(1 for j in jobs if j.get("zombie")),
        "open_priority_records": sum(1 for j in jobs if is_priority_open_job(j)),
    })

    print(json.dumps({"checked": checked, "alerts": alerts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
