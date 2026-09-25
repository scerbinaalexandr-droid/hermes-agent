#!/usr/bin/env python3
"""Morning mail digest: only what deserves the owner's attention.

Reads the inbox of every box marked MAIL_IMAP_<n>_IMPORTANT and reports UNREAD mail that arrived in
the last `--hours`. Advertising, newsletters and anything the rules would file
as «Карантин» or «Подписки» are counted separately and never listed — that is
the owner's rule: inform about important mail only.

Deterministic, no LLM: safe as a `no_agent` cron, whose stdout goes to Telegram
verbatim. Silent when there is nothing important, so the morning stays quiet.

Usage:
    python3 mail_digest.py                # last 24 hours
    python3 mail_digest.py --hours 72
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mail_rules  # noqa: E402
import mail_sort_imap as engine  # noqa: E402

# Folders whose mail is noise for a digest: it is filed, not reported.
QUIET_FOLDERS = {mail_rules.QUARANTINE, "Подписки"}
MAX_PER_BOX = 12


def important(headers: dict[str, str]) -> bool:
    """Worth the owner's attention: not bulk, not a folder we keep quiet."""
    if mail_rules.bulk_mail(headers):
        return False
    folder = engine.pick_folder(headers)
    return not (folder and folder.split("/")[0] in QUIET_FOLDERS)


def digest_box(client, hours: int) -> tuple[list[str], int]:
    """(lines about important mail, how much noise was skipped)."""
    days = max(1, round(hours / 24))
    uids = client.unseen_uids(days)
    if not uids:
        return [], 0
    bulk = client.headers_all("INBOX")
    lines: list[str] = []
    skipped = 0
    for uid in uids:
        headers = bulk.get(uid) or client.headers(uid)
        if not headers:
            continue
        if not important(headers):
            skipped += 1
            continue
        sender = engine._decode(headers.get("from", "")).split("<")[0].strip(' "')
        subject = engine._decode(headers.get("subject", "")) or "(без темы)"
        lines.append(f"  • {sender[:26] or '?'} — {subject[:52]}")
    return lines, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description="Morning mail digest.")
    ap.add_argument("--hours", type=int, default=24)
    args = ap.parse_args()

    # Only the boxes the owner reads himself: the rest are tidied in silence.
    boxes = [b for b in engine.boxes_from_env() if b.important]
    if not boxes:
        return 0

    blocks: list[str] = []
    total = 0
    noise = 0
    for box in boxes:
        client = engine._connect(box)
        if not client:
            continue
        try:
            lines, skipped = digest_box(client, args.hours)
        except Exception as exc:
            sys.stderr.write(f"[digest] {box.name}: {type(exc).__name__}: {exc}\n")
            continue
        finally:
            client.close()
        noise += skipped
        if not lines:
            continue
        total += len(lines)
        shown = lines[:MAX_PER_BOX]
        if len(lines) > MAX_PER_BOX:
            shown.append(f"      … ещё {len(lines) - MAX_PER_BOX}")
        blocks.append(f"*{box.name}*\n" + "\n".join(shown))

    if not total:
        return 0  # quiet morning: nothing important, nothing to say

    head = f"📬 *Почта* — {total} важных" + (f", шум ({noise}) убран" if noise else "")
    print(head + "\n\n" + "\n\n".join(blocks))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        sys.stderr.write(f"[digest] failed: {type(exc).__name__}: {exc}\n")
        print("⚠️ Сводку по почте собрать не удалось — нужна проверка.")
        raise SystemExit(0)
