#!/usr/bin/env python3
"""Move heavy mail attachments out of a mailbox into Google Drive.

For every message above `--min-mb` in a folder: download its attachments, put
them on Drive under <корень>/<Документы|Фото|Видео|Прочее>/<год письма>/, and
only THEN move the message to the trash. If a single upload fails, the message
is left where it is — the mailbox is the only copy until Drive has the file.

The Drive root is a folder in the owner's other Google account, shared with the
connected one (`--root-id` from its link, or `--root-name` to look it up among
shared folders).

Usage:
    python3 mail_archive_attachments.py --root-name "Архив почты" --dry-run
    python3 mail_archive_attachments.py --root-id <id> --min-mb 5 --delete-after
"""
from __future__ import annotations

import argparse
import email
import email.utils
import json
import os
import sys
import tempfile
from pathlib import Path

_GWS = "/opt/hermes/skills/productivity/google-workspace/scripts"
for _p in (_GWS, os.path.join(os.path.dirname(__file__), "..", "..", "..",
                              "productivity", "google-workspace", "scripts")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mail_sort_imap as engine  # noqa: E402

try:
    import google_api as gws  # noqa: E402
except Exception as exc:  # pragma: no cover - prod-only path
    sys.stderr.write(f"[archive] no google helper: {exc}\n")
    print("⚠️ Архив вложений недоступен — не удалось подключиться к Google.")
    raise SystemExit(0)

HOME = Path(os.environ.get("HERMES_HOME", "/opt/data"))
LEDGER = HOME / "mail" / "archived.json"
FOLDER_MIME = "application/vnd.google-apps.folder"

CATEGORIES = (
    ("Документы", {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                   ".txt", ".rtf", ".odt", ".ods", ".csv", ".zip", ".rar", ".7z"}),
    ("Фото", {".jpg", ".jpeg", ".png", ".heic", ".gif", ".bmp", ".tif", ".tiff", ".webp"}),
    ("Видео", {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv", ".3gp", ".webm"}),
)


def category_for(filename: str) -> str:
    ext = os.path.splitext(filename.lower())[1]
    for name, exts in CATEGORIES:
        if ext in exts:
            return name
    return "Прочее"


def year_of(msg) -> str:
    try:
        dt = email.utils.parsedate_to_datetime(msg.get("Date", ""))
        return str(dt.year) if dt else "без даты"
    except Exception:
        return "без даты"


def attachments(msg) -> list[tuple[str, bytes]]:
    """(filename, payload) for real attachments, skipping inline signatures."""
    out = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        name = part.get_filename()
        if not name:
            continue
        try:
            name = str(email.header.make_header(email.header.decode_header(name)))
        except Exception:
            pass
        payload = part.get_payload(decode=True)
        if not payload or len(payload) < 8192:   # tiny logos/signatures, not archives
            continue
        out.append((os.path.basename(name), payload))
    return out


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
        sys.stderr.write(f"[archive] ledger not saved: {exc}\n")


class Drive:
    """Just enough Drive: find a shared root, make folders, upload files."""

    def __init__(self, service):
        self.svc = service
        self._folders: dict[tuple[str, str], str] = {}

    def find_root(self, name: str) -> str | None:
        safe = name.replace("'", "\\'")
        res = self.svc.files().list(
            q=f"name = '{safe}' and mimeType = '{FOLDER_MIME}' and trashed = false",
            fields="files(id,name)", pageSize=10,
            includeItemsFromAllDrives=True, supportsAllDrives=True).execute()
        files = res.get("files", [])
        return files[0]["id"] if files else None

    def folder(self, name: str, parent: str) -> str:
        key = (name, parent)
        if key in self._folders:
            return self._folders[key]
        safe = name.replace("'", "\\'")
        res = self.svc.files().list(
            q=(f"name = '{safe}' and mimeType = '{FOLDER_MIME}' and trashed = false "
               f"and '{parent}' in parents"),
            fields="files(id)", pageSize=5,
            includeItemsFromAllDrives=True, supportsAllDrives=True).execute()
        files = res.get("files", [])
        if files:
            self._folders[key] = files[0]["id"]
        else:
            created = self.svc.files().create(
                body={"name": name, "mimeType": FOLDER_MIME, "parents": [parent]},
                fields="id", supportsAllDrives=True).execute()
            self._folders[key] = created["id"]
        return self._folders[key]

    def upload(self, filename: str, payload: bytes, parent: str) -> str:
        from googleapiclient.http import MediaFileUpload
        tmp = Path(tempfile.mkdtemp(prefix="hermes-att-")) / filename
        try:
            tmp.write_bytes(payload)
            media = MediaFileUpload(str(tmp), resumable=False)
            created = self.svc.files().create(
                body={"name": filename, "parents": [parent]},
                media_body=media, fields="id", supportsAllDrives=True).execute()
            return created["id"]
        finally:
            try:
                tmp.unlink()
                tmp.parent.rmdir()
            except OSError:
                pass


def archive_box(client, drive: Drive, root: str, args, ledger: dict) -> dict:
    """Archive one mailbox. Returns counters for the owner-facing summary."""
    stats = {"messages": 0, "files": 0, "bytes": 0, "trashed": 0,
             "failed": 0, "skipped": 0, "by_category": {}}
    min_bytes = int(args.min_mb * 1048576)
    heavy = [(uid, size) for uid, size in client.sizes_in(args.folder)
             if size >= min_bytes]
    heavy.sort(key=lambda x: -x[1])
    trash = client.trash_folder()

    for uid, size in heavy[:args.max]:
        raw = client.raw_message(uid)
        if not raw:
            stats["failed"] += 1
            continue
        msg = email.message_from_bytes(raw)
        key = (msg.get("Message-ID") or f"uid-{uid.decode()}").strip()
        if ledger.get(key):
            stats["skipped"] += 1
            continue
        files = attachments(msg)
        if not files:
            continue
        stats["messages"] += 1
        year = year_of(msg)
        uploaded: list[str] = []
        ok = True
        for name, payload in files:
            category = category_for(name)
            if args.dry_run:
                stats["by_category"][category] = stats["by_category"].get(category, 0) + 1
                stats["files"] += 1
                stats["bytes"] += len(payload)
                continue
            try:
                parent = drive.folder(year, drive.folder(category, root))
                uploaded.append(drive.upload(name, payload, parent))
            except Exception as exc:
                sys.stderr.write(f"[archive] upload failed для {name}: "
                                 f"{type(exc).__name__}: {exc}\n")
                ok = False
                break
            stats["by_category"][category] = stats["by_category"].get(category, 0) + 1
            stats["files"] += 1
            stats["bytes"] += len(payload)
        if args.dry_run:
            continue
        if not ok:
            stats["failed"] += 1
            continue
        ledger[key] = {"files": uploaded, "size": size}
        save_ledger(ledger)      # written before the mail is touched
        if args.delete_after and trash:
            client.move(uid, trash)
            stats["trashed"] += 1
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Archive mail attachments to Drive.")
    ap.add_argument("--folder", default="Отправленные")
    ap.add_argument("--root-id", default="", help="Drive folder id (from its link).")
    ap.add_argument("--root-name", default="", help="Drive folder name to look up.")
    ap.add_argument("--min-mb", type=float, default=5.0)
    ap.add_argument("--max", type=int, default=100, help="Messages per run.")
    ap.add_argument("--delete-after", action="store_true",
                    help="Move the message to the trash once Drive has its files.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    boxes = engine.boxes_from_env()
    if not boxes:
        print("Ящики по IMAP не подключены.")
        return 0

    drive = None
    root = args.root_id
    if not args.dry_run:
        try:
            drive = Drive(gws.build_service("drive", "v3"))
        except Exception as exc:
            sys.stderr.write(f"[archive] drive unavailable: {type(exc).__name__}\n")
            print("⚠️ Диск недоступен — архив не делаю, письма не тронуты.")
            return 0
        if not root and args.root_name:
            root = drive.find_root(args.root_name)
        if not root:
            print(f"⚠️ Не нашёл на Диске папку «{args.root_name or '—'}». "
                  "Создай её и дай доступ подключённому аккаунту — тогда продолжу.")
            return 0

    ledger = load_ledger()
    for box in boxes:
        client = engine._connect(box)
        if not client:
            continue
        try:
            stats = archive_box(client, drive, root, args, ledger)
        finally:
            client.close()
        head = "🗃 *Архив вложений*" + (" — примерка" if args.dry_run else "")
        print(f"{head} — {box.name}, папка «{args.folder}», письма от {args.min_mb:.0f} МБ")
        if not stats["messages"]:
            print("  подходящих писем с вложениями нет\n")
            continue
        print(f"  писем: *{stats['messages']}*, файлов: *{stats['files']}*, "
              f"объём: *{stats['bytes'] / 1048576:.0f} МБ*")
        for category, n in sorted(stats["by_category"].items(), key=lambda x: -x[1]):
            print(f"      {category}: {n}")
        if stats["trashed"]:
            print(f"  в корзину отправлено писем: *{stats['trashed']}*")
        if stats["skipped"]:
            print(f"  уже были в архиве: {stats['skipped']}")
        if stats["failed"]:
            print(f"  ⚠️ не удалось: {stats['failed']} — эти письма остались на месте")
        print()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        sys.stderr.write(f"[archive] failed: {type(exc).__name__}: {exc}\n")
        print("⚠️ Архив вложений не прошёл — нужна проверка.")
        raise SystemExit(0)
