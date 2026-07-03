"""Append-only changelog for all PCO write operations.

Usage in any script:
    from pco_log import log
    log("ASSIGN", "2026-05-17  John Doe → Sound  [plan:12345]")
    log("PATCH",  "song:12345678  title: '01 Foo' → 'Foo'")
    log("HIDE",   "song:12345678  hidden: False → True")

Log file: changelog.log next to this script
Format:   2026-05-13T14:32:10  ACTION   detail
"""
import os
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).parent / "changelog.log"


def log(action: str, detail: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts}  {action:<10} {detail}\n"
    with open(LOG_PATH, "a") as f:
        f.write(line)
