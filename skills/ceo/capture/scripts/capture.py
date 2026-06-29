"""Capture helper — routes a single voice memo / thought to the right memory file.

Usage:
  python capture.py --type <meeting|decision|insight|recap|task> \
                    --context "<who / what / project>" \
                    --content "<the actual thought>"

Returns JSON: {file, action, snippet}.

This is a thin wrapper around `route_capture()` in skills/ceo/_lib/memory.py.
The agent is responsible for parsing user input into (type, context, content)
and applying the soul.md privacy guard BEFORE calling this helper.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import subprocess
import sys

_REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))
if pathlib.Path("/opt/hermes/skills/ceo/_lib/memory.py").exists() and "/opt/hermes" not in sys.path:
    sys.path.insert(0, "/opt/hermes")

from skills.ceo._lib.memory import MemoryError, route_capture  # noqa: E402


def _capture_id(memo_type: str) -> str:
    """Stable per-capture id, used for Sheet idempotency (col A)."""
    now = _dt.datetime.now(_dt.timezone.utc)
    return f"cap/{now.strftime('%Y-%m-%d')}/{now.strftime('%H%M%S')}-{memo_type}"


def _sync_to_sheet(memo_type: str, context: str, content: str, capture_id: str) -> dict:
    """Best-effort: mirror a standalone capture into the CEO's master Sheet.

    Runs deterministically (not an LLM step) so every dictated/typed task,
    decision, or insight reaches his tables. Never raises. meeting/recap and a
    missing sheet config are no-ops.
    """
    if memo_type not in ("task", "decision", "insight"):
        return {"synced": False, "reason": "type-not-synced"}
    sheet_id = os.environ.get("HERMES_MEETING_SHEET_ID")
    if not sheet_id:
        return {"synced": False, "reason": "no-sheet-configured"}

    script = os.environ.get("HERMES_SHEETS_SYNC",
                            "/opt/hermes/skills/ceo/_lib/sheets_meeting_sync.py")
    if not os.path.exists(script):
        script = str(pathlib.Path(__file__).resolve().parents[2] / "_lib" / "sheets_meeting_sync.py")
    payload = {"type": memo_type, "context": context, "content": content}
    try:
        cmd = [sys.executable, script, "--capture",
               "--save", json.dumps(payload, ensure_ascii=False),
               "--note-id", capture_id]
        if context:
            cmd += ["--area", context]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if r.returncode == 0:
            try:
                return {"synced": True, **json.loads((r.stdout or "").strip() or "{}")}
            except Exception:
                return {"synced": True, "raw": (r.stdout or "").strip()[:200]}
        return {"synced": False, "reason": ((r.stdout or "") + (r.stderr or "")).strip()[:200]}
    except Exception as exc:
        return {"synced": False, "reason": str(exc)[:200]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--type",
        required=True,
        choices=["meeting", "decision", "insight", "recap", "task"],
        help="Memo type per voice memo template (memory/soul.md).",
    )
    parser.add_argument(
        "--context",
        default="",
        help="Who / what / which project. Optional but recommended.",
    )
    parser.add_argument(
        "--content",
        required=True,
        help="The actual content. Privacy-redacted by the caller.",
    )
    args = parser.parse_args()

    if not args.content.strip():
        print("ERROR: --content cannot be empty.", file=sys.stderr)
        return 2

    try:
        result = route_capture(args.type, args.context, args.content)
    except MemoryError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3

    # Mirror to the CEO's Google Sheet (his visible tables). markdown above stays
    # as the brief's fast-read index; the Sheet is the human-facing home.
    capture_id = _capture_id(args.type)
    result["capture_id"] = capture_id
    result["sheet_sync"] = _sync_to_sheet(args.type, args.context, args.content, capture_id)

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
