#!/usr/bin/env python3
"""Optional autonomous GREEN-role scouting.

Core status/Zombie monitoring needs no paid API. Discovery + robust semantic scoring does.
This script intentionally runs only when both a search provider key and an OpenAI API key
are configured as GitHub Actions secrets.

Supported search secret in this scaffold: TAVILY_API_KEY.
Required model secret: OPENAI_API_KEY.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "scout-latest.md"


def main():
    tavily = os.getenv("TAVILY_API_KEY")
    openai = os.getenv("OPENAI_API_KEY")
    if not tavily or not openai:
        OUT.write_text(
            "# GREEN-role scout\n\n"
            "Autonomous new-role discovery is not active because TAVILY_API_KEY and/or "
            "OPENAI_API_KEY are not configured in repository Actions secrets.\n\n"
            "The core GitHub monitor still handles Zombies, KPI integrity, existing-role link checks, "
            "scheduled auditing, and Pages deployment without these secrets.\n",
            encoding="utf-8",
        )
        print("Scouting skipped: optional secrets are not configured.")
        return

    # Deliberately fail closed until the user opts into external API usage and the scoring prompt is reviewed.
    OUT.write_text(
        "# GREEN-role scout\n\n"
        f"Secrets detected at {datetime.now().astimezone().isoformat(timespec='seconds')}.\n\n"
        "The repository is ready for an external-search + LLM scoring implementation, but it is intentionally "
        "disabled by default so a GitHub Action does not spend API credits or add jobs without Amber approving "
        "the exact scoring prompt and provider behavior.\n",
        encoding="utf-8",
    )
    print("Scouting integration ready but intentionally not spending external API credits.")


if __name__ == "__main__":
    main()
