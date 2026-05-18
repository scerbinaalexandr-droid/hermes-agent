"""Risks listing helper for /risks skill.

Returns JSON with active risks (skipping placeholders, status=closed),
sorted by severity * probability. Optional --min-severity floor.
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

from skills.ceo._lib.memory import risks_by_severity, _normalize_rank_token  # noqa: E402


def _shorten(text: str, limit: int = 100) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def gather(min_severity: str = "low") -> dict[str, object]:
    raw = risks_by_severity(min_severity)
    out: list[dict[str, str]] = []
    for r in raw:
        if _normalize_rank_token(r.get("status", "")) == "closed":
            continue
        out.append({
            "title": r.get("title", ""),
            "category": r.get("category", "—"),
            "severity": _normalize_rank_token(r.get("severity", "")) or "—",
            "probability": _normalize_rank_token(r.get("probability", "")) or "—",
            "status": _normalize_rank_token(r.get("status", "")) or "—",
            "mitigation_short": _shorten(r.get("mitigation", ""), 100),
            "owner": r.get("owner", "—"),
        })
    return {
        "filter": min_severity,
        "total": len(out),
        "risks": out,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--min-severity",
        choices=["critical", "high", "medium", "low"],
        default="low",
        help="Lowest severity to include (default: low = all).",
    )
    args = parser.parse_args()
    json.dump(gather(args.min_severity), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
