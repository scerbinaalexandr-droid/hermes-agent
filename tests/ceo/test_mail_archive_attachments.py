"""mail_archive_attachments.py: classification, Drive paths, delete-only-after-upload."""
import importlib.util
import sys
import types
from email.message import EmailMessage
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parents[2] / "skills" / "ceo" / "mail" /
          "scripts" / "mail_archive_attachments.py")


def _load(monkeypatch, home: Path):
    monkeypatch.setenv("HERMES_HOME", str(home))
    fake = types.ModuleType("google_api")
    fake.build_service = lambda *a, **k: None
    sys.modules["google_api"] = fake
    spec = importlib.util.spec_from_file_location("ceo_mail_archive", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod(monkeypatch, tmp_path):
    return _load(monkeypatch, tmp_path)


def _message(date="Tue, 18 Jul 2021 15:23:00 +0300", parts=()):
    msg = EmailMessage()
    msg["From"] = "a@mail.ru"
    msg["To"] = "b@mail.ru"
    msg["Subject"] = "Договор"
    msg["Date"] = date
    msg["Message-ID"] = "<id-1@mail.ru>"
    msg.set_content("см. вложение")
    for name, size in parts:
        msg.add_attachment(b"x" * size, maintype="application", subtype="octet-stream",
                           filename=name)
    return msg


class FakeClient:
    def __init__(self, messages, trash="Корзина"):
        self.messages = messages       # uid -> (size, raw bytes)
        self._trash = trash
        self.moved = []

    def sizes_in(self, folder):
        return [(uid, size) for uid, (size, _raw) in self.messages.items()]

    def raw_message(self, uid):
        return self.messages[uid][1]

    def trash_folder(self):
        return self._trash

    def move(self, uid, folder):
        self.moved.append((uid, folder))

    def close(self):
        pass


class FakeDrive:
    def __init__(self, fail_on=None):
        self.folders = {}
        self.uploads = []
        self.fail_on = fail_on

    def folder(self, name, parent):
        key = f"{parent}/{name}"
        self.folders[key] = key
        return key

    def upload(self, filename, payload, parent):
        if filename == self.fail_on:
            raise RuntimeError("drive is down")
        self.uploads.append((parent, filename, len(payload)))
        return f"file-{len(self.uploads)}"


class Args:
    folder = "Отправленные"
    min_mb = 1.0
    max = 50
    delete_after = True
    dry_run = False


@pytest.mark.parametrize("name, expected", [
    ("Договор.pdf", "Документы"), ("скан.DOCX", "Документы"),
    ("ЩЕРБИНА.rar", "Документы"), ("foto.JPG", "Фото"),
    ("clip.mov", "Видео"), ("что-то.xyz", "Прочее"),
])
def test_category_for(mod, name, expected):
    assert mod.category_for(name) == expected


def test_year_and_attachment_filtering(mod):
    msg = _message(parts=[("Договор.pdf", 20000), ("logo.png", 100)])
    assert mod.year_of(msg) == "2021"
    files = mod.attachments(msg)
    # the 100-byte signature logo is not an archive-worthy attachment
    assert [name for name, _p in files] == ["Договор.pdf"]


def test_files_land_in_category_and_year_then_mail_is_trashed(mod):
    raw = _message(parts=[("Договор.pdf", 20000), ("foto.jpg", 30000)]).as_bytes()
    client = FakeClient({b"7": (2 * 1048576, raw)})
    drive = FakeDrive()
    ledger = {}
    stats = mod.archive_box(client, drive, "ROOT", Args(), ledger)

    parents = {parent for parent, _n, _s in drive.uploads}
    assert parents == {"ROOT/Документы/2021", "ROOT/Фото/2021"}
    assert stats["files"] == 2 and stats["messages"] == 1
    assert client.moved == [(b"7", "Корзина")]
    assert ledger["<id-1@mail.ru>"]["files"] == ["file-1", "file-2"]


def test_mail_survives_a_failed_upload(mod):
    raw = _message(parts=[("Договор.pdf", 20000), ("foto.jpg", 30000)]).as_bytes()
    client = FakeClient({b"7": (2 * 1048576, raw)})
    drive = FakeDrive(fail_on="foto.jpg")
    stats = mod.archive_box(client, drive, "ROOT", Args(), {})

    assert client.moved == []          # the mailbox stays the only copy
    assert stats["failed"] == 1


def test_already_archived_message_is_skipped(mod):
    raw = _message(parts=[("Договор.pdf", 20000)]).as_bytes()
    client = FakeClient({b"7": (2 * 1048576, raw)})
    drive = FakeDrive()
    stats = mod.archive_box(client, drive, "ROOT", Args(),
                            {"<id-1@mail.ru>": {"files": ["old"]}})
    assert stats["skipped"] == 1 and drive.uploads == [] and client.moved == []


def test_light_messages_are_left_alone(mod):
    raw = _message(parts=[("Договор.pdf", 20000)]).as_bytes()
    client = FakeClient({b"7": (100 * 1024, raw)})     # 0.1 MB < min_mb
    stats = mod.archive_box(client, FakeDrive(), "ROOT", Args(), {})
    assert stats["messages"] == 0 and client.moved == []


def test_dry_run_uploads_nothing_and_keeps_mail(mod):
    raw = _message(parts=[("Договор.pdf", 20000)]).as_bytes()
    client = FakeClient({b"7": (2 * 1048576, raw)})
    drive = FakeDrive()
    args = Args()
    args.dry_run = True
    stats = mod.archive_box(client, drive, "ROOT", args, {})
    assert drive.uploads == [] and client.moved == []
    assert stats["files"] == 1 and stats["by_category"] == {"Документы": 1}
