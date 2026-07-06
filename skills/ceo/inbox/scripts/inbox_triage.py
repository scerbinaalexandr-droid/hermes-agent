#!/usr/bin/env python3
"""Auto-triage the CEO inbox via the connected Google Workspace OAuth.

Deterministic, no LLM — safe to run as a `no_agent` cron. Moves Gmail's own
NOISE categories (Promotions, Social) OUT of the inbox (archive = remove the
INBOX label; fully reversible, mail stays in All Mail) and tags them with a
"Hermes/Авто-архив" label so the CEO can see/undo what was touched. Important
mail (Primary) is never touched. Prints a Telegram-ready Russian digest; stays
SILENT (no output) when there was nothing to do, so the daily cron never spams.

Uses gmail.modify scope (already granted) — NO re-auth needed. Never deletes.

Usage:
    python3 inbox_triage.py            # triage + digest
    python3 inbox_triage.py --max 100  # cap messages processed per category
    python3 inbox_triage.py --dry-run  # report what WOULD be archived, change nothing
"""
from __future__ import annotations

import argparse
import os
import sys

# Reuse the google-workspace skill's auth/service helpers.
_GWS = "/opt/hermes/skills/productivity/google-workspace/scripts"
for p in (_GWS, os.path.join(os.path.dirname(__file__), "..", "..", "..", "productivity",
                             "google-workspace", "scripts")):
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

try:
    import google_api as gws  # provides build_service(), get_credentials()
except Exception as exc:  # pragma: no cover - prod-only path
    sys.stderr.write(f"[inbox] cannot import google-workspace helper: {exc}\n")
    # no_agent cron delivers stdout verbatim: a bare SystemExit(1) would deliver
    # nothing (or a technical error doc) and the CEO would never learn triage
    # silently stopped. Deliver one clean human line instead.
    print("⚠️ Разбор входящих сейчас недоступен — не удалось подключиться к Google.")
    raise SystemExit(0)

ARCHIVE_LABEL = "Hermes/Авто-архив"
# Gmail's own noise tabs. Conservative: only Promotions + Social. Updates
# (receipts/confirmations) and Forums stay in the inbox by design.
NOISE_QUERIES = [
    ("промо", "in:inbox category:promotions"),
    ("соцсети", "in:inbox category:social"),
]


def _svc():
    return gws.build_service("gmail", "v1")


def _ensure_label(svc) -> str:
    """Return the id of ARCHIVE_LABEL, creating it once if missing."""
    existing = svc.users().labels().list(userId="me").execute().get("labels", [])
    for lab in existing:
        if lab.get("name") == ARCHIVE_LABEL:
            return lab["id"]
    created = svc.users().labels().create(
        userId="me",
        body={"name": ARCHIVE_LABEL,
              "labelListVisibility": "labelShow",
              "messageListVisibility": "show"},
    ).execute()
    return created["id"]


def _ids_for(svc, query: str, cap: int) -> list[str]:
    ids: list[str] = []
    page = None
    while len(ids) < cap:
        resp = svc.users().messages().list(
            userId="me", q=query, maxResults=min(100, cap - len(ids)), pageToken=page,
        ).execute()
        ids += [m["id"] for m in resp.get("messages", [])]
        page = resp.get("nextPageToken")
        if not page:
            break
    return ids[:cap]


def _subjects(svc, ids: list[str], n: int = 3) -> list[str]:
    out = []
    for mid in ids[:n]:
        msg = svc.users().messages().get(
            userId="me", id=mid, format="metadata", metadataHeaders=["Subject", "From"],
        ).execute()
        hdrs = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        out.append(f"{hdrs.get('From', '?')[:28]} — {hdrs.get('Subject', '(без темы)')[:40]}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Auto-triage CEO inbox (archive noise).")
    ap.add_argument("--max", type=int, default=200, help="Max messages per category.")
    ap.add_argument("--dry-run", action="store_true", help="Report only, change nothing.")
    args = ap.parse_args()
    try:
        return _triage(args)
    except gws.GoogleAuthError:
        # Google disconnected (token expired/revoked). Don't crash the no_agent
        # cron with a raw traceback — emit one throttled clean alert (shared
        # across all Google jobs) or stay silent if already alerted.
        msg = gws.google_down_alert()
        if msg:
            print(msg)
        return 0
    except Exception as exc:
        # no_agent cron must never crash — an auth 401 surfaced at .execute(), a
        # transient API 5xx or a network blip logs to stderr and stays silent
        # rather than delivering a generic scheduler error.
        sys.stderr.write(f"[inbox] triage failed: {type(exc).__name__}: {exc}\n")
        return 0


def _triage(args) -> int:
    svc = _svc()
    label_id = None if args.dry_run else _ensure_label(svc)

    lines: list[str] = []
    total_archived = 0
    for human, query in NOISE_QUERIES:
        ids = _ids_for(svc, query, args.max)
        if not ids:
            continue
        sample = _subjects(svc, ids)
        if not args.dry_run:
            # batchModify handles up to 1000 ids per call.
            for i in range(0, len(ids), 1000):
                svc.users().messages().batchModify(
                    userId="me",
                    body={"ids": ids[i:i + 1000],
                          "removeLabelIds": ["INBOX"],
                          "addLabelIds": [label_id]},
                ).execute()
        total_archived += len(ids)
        verb = "нашлось" if args.dry_run else "в архив"
        lines.append(f"  • {human}: {len(ids)} {verb}")
        lines += [f"      — {s}" for s in sample]

    # Count what's left in Primary (the mail that matters).
    primary_unread = len(_ids_for(svc, "in:inbox category:primary is:unread", 200))

    if total_archived == 0 and primary_unread == 0:
        return 0  # SILENT — nothing to report, cron stays quiet.

    head = "🧹 *Авто-разбор почты*" + (" (dry-run)" if args.dry_run else "")
    body = [head, ""]
    if total_archived:
        body.append(f"📥 {'Будет заархивировано' if args.dry_run else 'Заархивировано'} *{total_archived}* (шум — промо/соцсети, обратимо, ярлык «{ARCHIVE_LABEL}»):")
        body += lines
        body.append("")
    body.append(f"⭐️ В Primary непрочитанных: *{primary_unread}*"
                + ("" if primary_unread else " — инбокс чист 🎉"))
    print("\n".join(body))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
