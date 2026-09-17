#!/usr/bin/env python3
"""Append a dated entry to an append-only memory file without inline `python -c`.

Usage (from $HERMES_HOME):
    python3 skills/ceo/_lib/append_log.py daily_log "### Brief (07:30)" "<body text>"

Inline `python3 -c "..."` is a script-execution pattern that needs approval
(and is denied for cron jobs), so skills call this file instead.
"""
import os
import sys
from pathlib import Path

# On prod the live memory lives under $HERMES_HOME (/opt/data), while this
# script may run from the image copy (/opt/hermes). Pin the root explicitly.
if os.environ.get("HERMES_HOME") and not os.environ.get("HERMES_CEO_MEMORY_ROOT"):
    os.environ["HERMES_CEO_MEMORY_ROOT"] = str(Path(os.environ["HERMES_HOME"]) / "memory")
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from skills.ceo._lib.memory import append_entry, today_iso  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: append_log.py <file-name> <entry-title> <body>", file=sys.stderr)
        return 2
    name, title, body = argv
    append_entry(name, today_iso(), f"{title}\n{body}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
