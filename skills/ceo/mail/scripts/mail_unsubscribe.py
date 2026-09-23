#!/usr/bin/env python3
"""Unsubscribe the owner from newsletters, by the senders' own mechanism.

Reads a folder (default «Карантин»), groups mail by sender and uses the
`List-Unsubscribe` header each bulk sender is obliged to provide:

1. **One-click** (RFC 8058): the sender says `List-Unsubscribe-Post:
   List-Unsubscribe=One-Click`, so a single POST is the intended, safe path.
2. **mailto:** — an unsubscribe letter is sent from the owner's own box over
   SMTP (needs MAIL_IMAP_<n>_SMTP_HOST; without it the sender is only listed).
3. **A plain https link** is NOT opened automatically: those pages often need
   a choice («отписаться от всего / только от этой темы»), and a blind visit
   can confirm the address to a spammer. Such senders are printed for the owner.

Never touched: mail the rules file as banks, security or documents, and
anything in the spam folder (clicking there tells a spammer the box is alive).
Every sender is tried once — the ledger lives on the volume.

Usage:
    python3 mail_unsubscribe.py --dry-run      # who would be unsubscribed
    python3 mail_unsubscribe.py                # do it (one-click + mailto)
    python3 mail_unsubscribe.py --folder INBOX --max 300
"""
from __future__ import annotations

import argparse
import json
import os
import re
import smtplib
import ssl
import sys
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mail_rules  # noqa: E402
import mail_sort_imap as engine  # noqa: E402

HOME = Path(os.environ.get("HERMES_HOME", "/opt/data"))
LEDGER = HOME / "mail" / "unsubscribed.json"
TIMEOUT = 15
PER_RUN_LIMIT = 60  # a polite ceiling: no burst of hundreds of requests
USER_AGENT = "Mozilla/5.0 (compatible; personal-mail-assistant)"


def load_ledger() -> dict:
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_ledger(data: dict) -> None:
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as exc:
        sys.stderr.write(f"[unsubscribe] ledger not saved: {exc}\n")


def parse_targets(header: str) -> tuple[list[str], list[str]]:
    """List-Unsubscribe → (https urls, mailto addresses)."""
    urls, mails = [], []
    for raw in re.findall(r"<([^>]+)>", header or ""):
        value = raw.strip()
        if value.lower().startswith("https://"):
            urls.append(value)
        elif value.lower().startswith("mailto:"):
            mails.append(value[len("mailto:"):])
    return urls, mails


def protected(headers: dict[str, str]) -> bool:
    """True when this mail belongs to a category we never unsubscribe from."""
    folder = engine.pick_folder(headers)
    return bool(folder) and folder.split("/")[0] in engine.PROTECTED_TOPS


def one_click(url: str) -> tuple[bool, str]:
    data = b"List-Unsubscribe=One-Click"
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "User-Agent": USER_AGENT, "Content-Length": str(len(data))})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT,
                                    context=ssl.create_default_context()) as resp:
            return 200 <= resp.status < 400, str(resp.status)
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, type(exc).__name__


def smtp_settings(index: int) -> tuple[str, int] | None:
    host = os.environ.get(f"MAIL_IMAP_{index}_SMTP_HOST", "").strip()
    if not host:
        return None
    return host, int(os.environ.get(f"MAIL_IMAP_{index}_SMTP_PORT", "465") or 465)


def send_unsubscribe(box: engine.Box, smtp: tuple[str, int], to_addr: str,
                     subject: str = "unsubscribe") -> tuple[bool, str]:
    msg = EmailMessage()
    msg["From"] = box.user
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content("unsubscribe")
    host, port = smtp
    try:
        with smtplib.SMTP_SSL(host, port, timeout=TIMEOUT,
                              context=ssl.create_default_context()) as srv:
            srv.login(box.user, box.password)
            srv.send_message(msg)
        return True, "sent"
    except Exception as exc:
        return False, type(exc).__name__


def collect(client, folder: str, cap: int) -> dict[str, dict]:
    """sender → {urls, mails, one_click, count} for bulk mail in `folder`."""
    found: dict[str, dict] = {}
    for uid in client.uids_in(folder)[:cap]:
        headers = client.headers(uid)
        if not headers or not headers.get("list-unsubscribe"):
            continue
        if protected(headers):
            continue
        sender = engine._decode(headers.get("from", "")).strip()
        m = re.search(r"<([^>]+)>", sender)
        addr = (m.group(1) if m else sender).lower()
        urls, mails = parse_targets(headers["list-unsubscribe"])
        entry = found.setdefault(addr, {"urls": [], "mails": [], "one_click": False,
                                        "count": 0})
        entry["count"] += 1
        entry["urls"] = entry["urls"] or urls
        entry["mails"] = entry["mails"] or mails
        post = (headers.get("list-unsubscribe-post") or "").lower()
        if "one-click" in post:
            entry["one_click"] = True
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description="Unsubscribe from newsletters.")
    ap.add_argument("--folder", default=mail_rules.QUARANTINE)
    ap.add_argument("--max", type=int, default=400, help="Messages scanned per box.")
    ap.add_argument("--limit", type=int, default=PER_RUN_LIMIT,
                    help="Max senders acted on in one run.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    boxes = engine.boxes_from_env()
    if not boxes:
        print("Ящики по IMAP не подключены.")
        return 0
    if args.folder.lower() in ("spam", "спам", "junk"):
        print("🛡 В папке «Спам» отписку не делаю: переход по ссылке из спама "
              "подтверждает спамеру, что ящик живой.")
        return 0

    ledger = load_ledger()
    for index, box in enumerate(boxes, start=1):
        client = engine._connect(box)
        if not client:
            continue
        try:
            senders = collect(client, args.folder, args.max)
        finally:
            client.close()
        if not senders:
            print(f"📭 {box.name}: в «{args.folder}» рассылок с кнопкой отписки нет.")
            continue

        smtp = smtp_settings(index)
        done, failed, manual, skipped = [], [], [], 0
        for addr, entry in sorted(senders.items(), key=lambda x: -x[1]["count"]):
            if ledger.get(f"{box.user}|{addr}", {}).get("ok"):
                skipped += 1
                continue
            if len(done) + len(failed) >= args.limit:
                break
            if args.dry_run:
                how = ("в один запрос" if entry["one_click"]
                       else "письмом" if entry["mails"] and smtp
                       else "твоим кликом")
                manual.append(f"  {entry['count']:4}  {addr} — {how}")
                continue
            ok, detail = False, "no method"
            if entry["one_click"] and entry["urls"]:
                ok, detail = one_click(entry["urls"][0])
            if not ok and entry["mails"] and smtp:
                ok, detail = send_unsubscribe(box, smtp, entry["mails"][0])
            if ok:
                done.append(f"  {entry['count']:4}  {addr}")
                ledger[f"{box.user}|{addr}"] = {"ok": True, "how": detail}
                # Written straight away: a dropped connection mid-run must not
                # lose the record and make us poke the same sender again.
                save_ledger(ledger)
            elif entry["urls"]:
                manual.append(f"  {entry['count']:4}  {addr} → {entry['urls'][0]}")
            else:
                failed.append(f"  {entry['count']:4}  {addr} — {detail}")

        head = "📧 *Отписка*" + (" — примерка" if args.dry_run else "")
        print(f"{head} — {box.name}, папка «{args.folder}»")
        if args.dry_run:
            print(f"Нашёл рассылок: *{len(senders)}*"
                  + (f", уже отписаны: {skipped}" if skipped else ""))
            print("\n".join(manual[:30]))
        else:
            if done:
                print(f"✅ Отписал: *{len(done)}*")
                print("\n".join(done[:20]))
            if manual:
                print(f"\n🖐 Нужен твой клик (страница просит выбрать): *{len(manual)}*")
                print("\n".join(manual[:10]))
            if failed:
                print(f"\n⚠️ Не получилось: *{len(failed)}*")
                print("\n".join(failed[:10]))
            if skipped:
                print(f"\nУже были отписаны раньше: {skipped}")
        print()

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        sys.stderr.write(f"[unsubscribe] failed: {type(exc).__name__}: {exc}\n")
        print("⚠️ Отписка не прошла — нужна проверка.")
        raise SystemExit(0)
