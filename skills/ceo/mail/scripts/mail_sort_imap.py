#!/usr/bin/env python3
"""Sort any IMAP mailbox (mail.ru, corporate boxes) into the owner's folders.

Same folder tree and same order as Gmail — the rules live in `mail_rules.py`.
Difference: IMAP has folders, not labels, so filing MOVES the message out of
the inbox into its folder. Nothing is deleted, and a move back is one drag in
any mail client.

Boxes are configured through Railway Variables, numbered from 1 to 10:

    MAIL_IMAP_1_HOST=imap.mail.ru        # SMTP is not needed here
    MAIL_IMAP_1_USER=<адрес>
    MAIL_IMAP_1_PASS=<пароль приложения> # never printed, never logged
    MAIL_IMAP_1_NAME=mail.ru             # optional label for the digest

Usage:
    python3 mail_sort_imap.py --dry-run     # report what would move
    python3 mail_sort_imap.py               # sort
    python3 mail_sort_imap.py --boxes       # which boxes are configured
"""
from __future__ import annotations

import argparse
import email.header
import imaplib
import os
import re
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mail_rules  # noqa: E402
from mail_rules import MANAGED_TOP, QUARANTINE, RULES  # noqa: E402

MAX_BOXES = 10
FETCH_HEADERS = "(FROM SUBJECT LIST-UNSUBSCRIBE LIST-ID PRECEDENCE)"
FAIL_MSG = "⚠️ Раскладка почты сегодня не прошла — нужна проверка."


@dataclass
class Box:
    name: str
    host: str
    user: str
    password: str
    port: int = 993


def boxes_from_env() -> list[Box]:
    out = []
    for i in range(1, MAX_BOXES + 1):
        host = os.environ.get(f"MAIL_IMAP_{i}_HOST", "").strip()
        user = os.environ.get(f"MAIL_IMAP_{i}_USER", "").strip()
        pwd = os.environ.get(f"MAIL_IMAP_{i}_PASS", "")
        if not (host and user and pwd):
            continue
        out.append(Box(
            name=os.environ.get(f"MAIL_IMAP_{i}_NAME", "").strip() or user,
            host=host, user=user, password=pwd,
            port=int(os.environ.get(f"MAIL_IMAP_{i}_PORT", "993") or 993),
        ))
    return out


def _decode(raw: str) -> str:
    """MIME-encoded header → plain text (mail.ru sends Base64 Cyrillic)."""
    try:
        parts = email.header.decode_header(raw or "")
    except Exception:
        return raw or ""
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            try:
                out.append(text.decode(enc or "utf-8", errors="replace"))
            except LookupError:
                out.append(text.decode("utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def parse_headers(blob: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    current = None
    for line in (blob or "").splitlines():
        if line[:1] in (" ", "\t") and current:
            headers[current] += " " + line.strip()
            continue
        if ":" in line:
            name, _, value = line.partition(":")
            current = name.strip().lower()
            headers[current] = value.strip()
    return headers


class ImapBox:
    """Thin wrapper over imaplib: only the operations the sorter needs."""

    def __init__(self, box: Box):
        self.box = box
        self.conn = imaplib.IMAP4_SSL(box.host, box.port)
        self.conn.login(box.user, box.password)
        self.delimiter = "/"
        self._folders: set[str] = set()
        self._read_folders()

    def _read_folders(self) -> None:
        code, rows = self.conn.list()
        if code != "OK":
            return
        for row in rows or []:
            text = row.decode(errors="replace") if isinstance(row, bytes) else str(row)
            m = re.match(r'\(.*?\)\s+"?([^" ]+)"?\s+"?(.*?)"?$', text)
            if not m:
                continue
            self.delimiter = m.group(1) if m.group(1) != "NIL" else "/"
            self._folders.add(m.group(2))

    def native(self, folder: str) -> str:
        return folder.replace("/", self.delimiter)

    def ensure_folder(self, folder: str) -> None:
        parts = folder.split("/")
        for i in range(1, len(parts) + 1):
            path = self.native("/".join(parts[:i]))
            if path in self._folders:
                continue
            self.conn.create(f'"{path}"')
            self._folders.add(path)

    def inbox_uids(self, days: int) -> list[bytes]:
        """UIDs in the inbox; days<=0 means the whole inbox, however old."""
        self.conn.select("INBOX")
        criteria = "ALL" if days <= 0 else f"(SINCE {_since(days)})"
        code, data = self.conn.uid("SEARCH", None, criteria)
        if code != "OK" or not data or not data[0]:
            return []
        return data[0].split()

    def headers(self, uid: bytes) -> dict[str, str]:
        code, data = self.conn.uid(
            "FETCH", uid, f"(BODY.PEEK[HEADER.FIELDS {FETCH_HEADERS}])")
        if code != "OK":
            return {}
        for part in data or []:
            if isinstance(part, tuple) and len(part) > 1:
                blob = part[1]
                text = blob.decode(errors="replace") if isinstance(blob, bytes) else str(blob)
                return parse_headers(text)
        return {}

    def quota(self) -> tuple[int, int] | None:
        """(used_kb, limit_kb) when the server reports a quota, else None."""
        try:
            code, data = self.conn.getquotaroot("INBOX")
        except Exception:
            return None
        if code != "OK":
            return None
        for row in data or []:
            for item in (row if isinstance(row, list) else [row]):
                text = item.decode(errors="replace") if isinstance(item, bytes) else str(item)
                m = re.search(r"STORAGE\s+(\d+)\s+(\d+)", text)
                if m:
                    return int(m.group(1)), int(m.group(2))
        return None

    def select_folder(self, folder: str) -> int:
        code, data = self.conn.select(f'"{self.native(folder)}"')
        if code != "OK":
            return 0
        try:
            return int(data[0])
        except Exception:
            return 0

    def uids_in(self, folder: str, older_than_days: int = 0) -> list[bytes]:
        if self.select_folder(folder) == 0:
            return []
        criteria = "ALL" if older_than_days <= 0 else f"(BEFORE {_since(older_than_days)})"
        code, data = self.conn.uid("SEARCH", None, criteria)
        if code != "OK" or not data or not data[0]:
            return []
        return data[0].split()

    def trash_folder(self) -> str:
        """The server's own trash folder — never invent one."""
        for name in ("Trash", "Корзина", "INBOX/Trash", "[Gmail]/Корзина",
                     "[Gmail]/Trash", "Deleted Items"):
            native = self.native(name)
            if native in self._folders:
                return name
        return ""

    def move(self, uid: bytes, folder: str) -> None:
        """MOVE when the server supports it, else copy + mark deleted."""
        target = f'"{self.native(folder)}"'
        code, _ = self.conn.uid("MOVE", uid, target)
        if code == "OK":
            return
        code, _ = self.conn.uid("COPY", uid, target)
        if code != "OK":
            raise RuntimeError("copy failed")
        self.conn.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
        self.conn.expunge()

    def close(self) -> None:
        try:
            self.conn.logout()
        except Exception:
            pass


def _since(days: int) -> str:
    from datetime import date, timedelta
    return (date.today() - timedelta(days=max(1, days))).strftime("%d-%b-%Y")


def pick_folder(headers: dict[str, str]) -> str | None:
    """The folder this message belongs to, or None to leave it in the inbox."""
    sender = _decode(headers.get("from", ""))
    subject = _decode(headers.get("subject", ""))
    bulk = mail_rules.bulk_mail(headers)
    for rule in RULES:
        if not mail_rules.matches(rule, sender, subject):
            continue
        # Marketing never lands in a working folder — same order as in Gmail.
        if bulk and not rule.promo_ok:
            return QUARANTINE
        return rule.folder
    return QUARANTINE if bulk else None


def sort_box(client: ImapBox, days: int, cap: int, dry_run: bool) -> tuple[dict[str, int], list[str]]:
    counts: dict[str, int] = {}
    samples: list[str] = []
    for uid in client.inbox_uids(days)[:cap]:
        headers = client.headers(uid)
        if not headers:
            continue
        folder = pick_folder(headers)
        if not folder:
            continue
        if not dry_run:
            client.ensure_folder(folder)
            client.move(uid, folder)
        counts[folder] = counts.get(folder, 0) + 1
        if len(samples) < 6:
            samples.append(
                f"      — {_decode(headers.get('from', '?'))[:26]} → {folder}")
    return counts, samples


def bulk_report(client: ImapBox, folder: str, cap: int) -> list[tuple[str, int, bool]]:
    """Who floods this folder: (sender, count, offers unsubscribe), busiest first."""
    counts: dict[str, int] = {}
    unsub: dict[str, bool] = {}
    for uid in client.uids_in(folder)[:cap]:
        headers = client.headers(uid)
        if not headers:
            continue
        sender = _decode(headers.get("from", "")).strip()
        m = re.search(r"<([^>]+)>", sender)
        addr = (m.group(1) if m else sender).lower()
        counts[addr] = counts.get(addr, 0) + 1
        if headers.get("list-unsubscribe"):
            unsub[addr] = True
    return sorted(((a, n, unsub.get(a, False)) for a, n in counts.items()),
                  key=lambda x: -x[1])


def purge_folder(client: ImapBox, folder: str, older_than_days: int,
                 cap: int, dry_run: bool) -> tuple[int, str]:
    """Move old mail from `folder` to the server's trash. Reversible ~30 days."""
    trash = client.trash_folder()
    if not trash:
        return 0, ""
    uids = client.uids_in(folder, older_than_days)[:cap]
    if not dry_run:
        for uid in uids:
            client.move(uid, trash)
    return len(uids), trash


def main() -> int:
    ap = argparse.ArgumentParser(description="Sort IMAP mailboxes into folders.")
    ap.add_argument("--days", type=int, default=90,
                    help="How far back to look; 0 = the whole inbox.")
    ap.add_argument("--all", action="store_true",
                    help="Sort the whole inbox regardless of age (same as --days 0).")
    ap.add_argument("--max", type=int, default=500, help="Max messages per box.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--boxes", action="store_true", help="List configured boxes.")
    ap.add_argument("--report", metavar="FOLDER", nargs="?", const=QUARANTINE,
                    help="Who floods a folder (default «Карантин») — for unsubscribing.")
    ap.add_argument("--purge", metavar="FOLDER", nargs="?", const=QUARANTINE,
                    help="Move that folder's old mail to the trash (default «Карантин»).")
    ap.add_argument("--older-than", type=int, default=30,
                    help="With --purge: only mail older than N days (default 30).")
    args = ap.parse_args()

    if args.all:
        args.days = 0
    boxes = boxes_from_env()
    if args.boxes:
        if not boxes:
            print("Ящики по IMAP не подключены.")
        for b in boxes:
            print(f"• {b.name} — {b.host}")
        return 0
    if not boxes:
        return 0  # nothing configured yet: the cron stays silent

    if args.report:
        return run_report(boxes, args)
    if args.purge:
        return run_purge(boxes, args)

    out: list[str] = []
    total = 0
    quarantined = 0
    for box in boxes:
        try:
            client = ImapBox(box)
        except Exception as exc:
            # Never print the password or the raw server text.
            sys.stderr.write(f"[mail_sort_imap] {box.name}: {type(exc).__name__}\n")
            out.append(f"  • {box.name}: не удалось войти — проверь пароль приложения.")
            continue
        try:
            counts, samples = sort_box(client, args.days, args.max, args.dry_run)
        except Exception as exc:
            sys.stderr.write(f"[mail_sort_imap] {box.name}: {type(exc).__name__}: {exc}\n")
            out.append(f"  • {box.name}: раскладка прервалась — нужна проверка.")
            continue
        finally:
            client.close()
        moved = sum(counts.values())
        total += moved
        quarantined += counts.get(QUARANTINE, 0)
        if not moved:
            continue
        out.append(f"  *{box.name}* — {moved}")
        out += [f"      {folder}: {n}" for folder, n in sorted(counts.items())]
        out += samples[:2]

    if not out:
        if args.dry_run:
            print("📭 Раскладывать нечего — всё уже по папкам.")
        return 0
    head = "🗂 *Раскладка почты*" + (" — примерка, ничего не тронуто" if args.dry_run else "")
    body = [head, "", f"{'Разложилось бы' if args.dry_run else 'Разложено'}: *{total}*"] + out
    if quarantined:
        body += ["", f"🚦 В «{QUARANTINE}»: *{quarantined}* — письма целы, лежат в папке."]
    print("\n".join(body))
    return 0


def _connect(box: Box) -> ImapBox | None:
    try:
        return ImapBox(box)
    except Exception as exc:
        sys.stderr.write(f"[mail_sort_imap] {box.name}: {type(exc).__name__}\n")
        print(f"  • {box.name}: не удалось войти — проверь пароль приложения.")
        return None


def run_report(boxes: list[Box], args) -> int:
    for box in boxes:
        client = _connect(box)
        if not client:
            continue
        try:
            rows = bulk_report(client, args.report, args.max)
            quota = client.quota()
        finally:
            client.close()
        print(f"📊 *{box.name}* — папка «{args.report}»")
        if quota:
            used, limit = quota
            pct = round(used * 100 / limit) if limit else 0
            print(f"Занято: {used // 1024} МБ из {limit // 1024} МБ ({pct}%)")
        if not rows:
            print("  пусто\n")
            continue
        print(f"Кто пишет чаще всего (всего разных адресов: {len(rows)}):")
        for addr, n, unsub in rows[:25]:
            mark = " — можно отписаться" if unsub else ""
            print(f"  {n:4}  {addr}{mark}")
        print()
    return 0


def run_purge(boxes: list[Box], args) -> int:
    for box in boxes:
        client = _connect(box)
        if not client:
            continue
        try:
            moved, trash = purge_folder(client, args.purge, args.older_than,
                                        args.max, args.dry_run)
        finally:
            client.close()
        if not trash:
            print(f"⚠️ {box.name}: не нашёл корзину — чистку не делаю.")
            continue
        verb = "уехало бы" if args.dry_run else "переехало"
        print(f"🧺 *{box.name}*: из «{args.purge}» в корзину {verb} *{moved}* "
              f"(старше {args.older_than} дн.). Из корзины письма восстановимы ~30 дней.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # a cron job must never crash with a traceback
        sys.stderr.write(f"[mail_sort_imap] failed: {type(exc).__name__}: {exc}\n")
        print(FAIL_MSG)
        raise SystemExit(0)
