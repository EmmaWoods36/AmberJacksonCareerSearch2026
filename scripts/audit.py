#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOBS = ROOT / "data" / "jobs.json"
PIPELINE = ROOT / "data" / "pipeline.json"
REPORT = ROOT / "reports" / "weekly-audit.md"
AUDIT_JSON = ROOT / "data" / "audit-latest.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    jobs = load(JOBS)
    pipe = load(PIPELINE)
    errors = []
    warnings = []

    ranks = [j.get("rank") for j in jobs]
    dup_ranks = [r for r,c in Counter(ranks).items() if c > 1]
    if dup_ranks:
        errors.append(f"Duplicate tracker ranks: {dup_ranks}")

    total_apps = int(pipe["applications_total"])
    pending = int(pipe["active_pending"])
    rej = int(pipe["confirmed_rejections"])
    if pending > total_apps:
        errors.append(f"Pending applications ({pending}) exceed total applications ({total_apps}).")
    if rej > total_apps:
        errors.append(f"Confirmed rejections ({rej}) exceed total applications ({total_apps}).")

    zombies = [j for j in jobs if j.get("zombie")]
    bad_zombies = [j for j in zombies if j.get("status_class") != "status-pending"]
    if bad_zombies:
        errors.append("Zombie records exist outside status-pending.")
    if len(zombies) > pending:
        errors.append(f"Zombie count ({len(zombies)}) exceeds pending applications ({pending}).")

    req_events = sum(int(x.get("request_events", 0)) for x in pipe.get("interview_history", []))
    meetings = sum(int(x.get("completed_meetings", 0)) for x in pipe.get("interview_history", []))
    distinct_interviewed = sum(1 for x in pipe.get("interview_history", []) if int(x.get("completed_meetings", 0)) > 0)
    if req_events != int(pipe["interview_request_events"]):
        errors.append(f"Interview request detail sums to {req_events}, expected {pipe['interview_request_events']}.")
    if meetings != int(pipe["completed_interview_meetings"]):
        errors.append(f"Interview meeting detail sums to {meetings}, expected {pipe['completed_interview_meetings']}.")
    if distinct_interviewed != int(pipe["distinct_positions_interviewed"]):
        errors.append(f"Distinct interviewed positions detail sums to {distinct_interviewed}, expected {pipe['distinct_positions_interviewed']}.")

    # Status freshness warning for actionable queue records.
    for j in jobs:
        if j.get("status_class") == "status-queue" and j.get("strategy_bucket") in {"APPLY ASAP", "STRETCH", "SAFETY NET"}:
            if not j.get("status_checked_at"):
                warnings.append(f'Missing status check timestamp: {j.get("company")} — {j.get("title")}')

    now = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        "# Weekly career search integrity audit",
        "",
        f"Generated: {now}",
        f"Role records: {len(jobs)}",
        f"Confirmed applications: {total_apps}",
        f"Pending applications: {pending}",
        f"Zombies (subset of pending): {len(zombies)}",
        f"Interview request events: {req_events}",
        f"Distinct positions interviewed: {distinct_interviewed}",
        f"Completed interview meetings: {meetings}",
        f"Offers: {pipe['offers_extended']}",
        "",
        "## Errors",
    ]
    lines.extend([f"- {e}" for e in errors] or ["- None"])
    lines += ["", "## Warnings"]
    lines.extend([f"- {w}" for w in warnings[:100]] or ["- None"])
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    AUDIT_JSON.write_text(json.dumps({
        "generated_at": now,
        "errors": errors,
        "warnings": warnings,
        "role_records": len(jobs),
        "applications_total": total_apps,
        "pending": pending,
        "zombies": len(zombies),
        "interview_request_events": req_events,
        "distinct_positions_interviewed": distinct_interviewed,
        "completed_interview_meetings": meetings,
        "offers": pipe["offers_extended"],
    }, indent=2) + "\n", encoding="utf-8")

    print(f"errors={len(errors)} warnings={len(warnings)}")
    if errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
