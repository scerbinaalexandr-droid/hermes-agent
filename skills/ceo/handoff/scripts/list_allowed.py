#!/usr/bin/env python3
"""List current Telegram allowed users — REDACTED, guard-safe.

Backs `/handoff status`. Reads the UNION of TELEGRAM_ALLOWED_USERS,
TELEGRAM_GROUP_ALLOWED_USERS and GATEWAY_ALLOWED_USERS from the live process
env (mirrors gateway _is_authorized — none is hidden) and emits a redacted
JSON summary. NEVER prints the full numeric IDs — only the last 3 digits as
a "tail" marker so the CEO can recognise an entry without exposing it.

Read-only listing script per CEO OS Skill Convention Contract §3:
no --gather/--save split, always emits JSON to stdout, never writes anything.

Stdlib only. No state.db, no LLM, no network.

Usage:
    python3 skills/ceo/handoff/scripts/list_allowed.py
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))
# Production fallback: _lib/ is baked into image at /opt/hermes, not synced via skill-sync.
if pathlib.Path("/opt/hermes/skills/ceo/_lib/memory.py").exists() and "/opt/hermes" not in sys.path:
    sys.path.insert(0, "/opt/hermes")

# Known canonical IDs from project memory (two-telegram-accounts.md): both
# belong to Alexandr — personal phone and work phone. Used ONLY to label an
# entry as "owner" vs "delegate" in the redacted view; never printed in full.
_OWNER_TAILS = {"595", "170"}  # last-3 of 746810595 (личный) / 385068170 (рабочий)


def _redact(raw_id: str) -> dict[str, str]:
    """Return a redacted descriptor for a single allowlist entry.

    Never exposes the full ID — only a tail (last 3 chars) + length, enough
    for the CEO to recognise but useless for an attacker reading logs.
    """
    val = raw_id.strip()
    tail = val[-3:] if len(val) >= 3 else val
    role = "owner (Alexandr)" if tail in _OWNER_TAILS else "delegate (CoS?)"
    return {
        "tail": tail,
        "length": str(len(val)),
        "masked": ("•" * max(len(val) - 3, 0)) + tail,
        "role_hint": role,
    }


def _parse_env(var: str) -> list[str]:
    raw = os.environ.get(var, "").strip()
    if not raw:
        return []
    return [u.strip() for u in raw.split(",") if u.strip()]


def gather() -> dict:
    # Effective allowlist = UNION of all three vars (mirrors gateway
    # _is_authorized) — NOT a precedence chain. An id granted via ANY var is
    # authorized, so none may be hidden. Track per-id provenance for the view.
    allow_vars = ("TELEGRAM_ALLOWED_USERS", "TELEGRAM_GROUP_ALLOWED_USERS", "GATEWAY_ALLOWED_USERS")
    per_var = {var: _parse_env(var) for var in allow_vars}
    sources_present = [var for var, ids in per_var.items() if ids] or ["(none set)"]

    provenance: dict[str, list[str]] = {}
    for var in allow_vars:
        for uid in per_var[var]:
            provenance.setdefault(uid, [])
            if var not in provenance[uid]:
                provenance[uid].append(var)

    entries = []
    for uid, vars_ in provenance.items():  # dict preserves first-seen order
        e = _redact(uid)
        e["sources"] = [v.replace("_ALLOWED_USERS", "") for v in vars_]
        entries.append(e)
    owners = sum(1 for e in entries if e["role_hint"].startswith("owner"))
    delegates = len(entries) - owners
    return {
        "ok": True,
        "sources_present": sources_present,
        "count": len(entries),
        "owners": owners,
        "delegates": delegates,
        "entries": entries,
        "vars_set": {var: bool(ids) for var, ids in per_var.items()},
        "note": (
            "Allowlist = UNION of TELEGRAM_ALLOWED_USERS, TELEGRAM_GROUP_ALLOWED_USERS, "
            "GATEWAY_ALLOWED_USERS (mirrors gateway _is_authorized). IDs redacted to last "
            "3 digits by design; full IDs live only in Railway env, never in chat/logs."
        ),
    }


def main() -> int:
    argparse.ArgumentParser(
        description="List redacted Telegram allowed users for /handoff status."
    ).parse_args()
    result = gather()
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
