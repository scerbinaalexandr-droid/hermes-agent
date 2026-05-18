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
import json
import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))
if pathlib.Path("/opt/hermes/skills/ceo/_lib/memory.py").exists() and "/opt/hermes" not in sys.path:
    sys.path.insert(0, "/opt/hermes")

from skills.ceo._lib.memory import MemoryError, route_capture  # noqa: E402


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

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
