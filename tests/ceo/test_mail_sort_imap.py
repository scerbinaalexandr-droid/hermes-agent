"""mail_sort_imap.py: header parsing, rule order over IMAP, moves, dry-run."""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parents[2] / "skills" / "ceo" / "mail" /
          "scripts" / "mail_sort_imap.py")


def _load():
    spec = importlib.util.spec_from_file_location("ceo_mail_sort_imap", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load()


class FakeClient:
    """Stands in for ImapBox: records folders created and messages moved."""

    def __init__(self, messages):
        self.messages = messages           # uid -> headers dict
        self.created: list[str] = []
        self.moved: list[tuple[bytes, str]] = []

    def inbox_uids(self, days):
        return list(self.messages)

    def headers(self, uid):
        return self.messages[uid]

    def ensure_folder(self, folder):
        self.created.append(folder)

    def move(self, uid, folder):
        self.moved.append((uid, folder))

    def close(self):
        pass


def test_parse_headers_handles_folded_lines():
    blob = ("From: Revolut <no-reply@revolut.com>\r\n"
            "Subject: Ваш отчёт\r\n"
            "List-Unsubscribe: <https://x/y>,\r\n"
            " <mailto:u@x>\r\n")
    h = mod.parse_headers(blob)
    assert h["from"] == "Revolut <no-reply@revolut.com>"
    assert h["subject"] == "Ваш отчёт"
    assert h["list-unsubscribe"].endswith("<mailto:u@x>")


def test_decode_mime_encoded_cyrillic_subject():
    assert mod._decode("=?UTF-8?B?0J/RgNC40LLQtdGC?=") == "Привет"


@pytest.mark.parametrize("headers, expected", [
    # A bank keeps its folder even when the sender bulk-mails.
    ({"from": "Revolut <no-reply@revolut.com>", "subject": "Statement",
      "list-unsubscribe": "<mailto:u@x>"}, "Банки/Revolut"),
    # An airline newsletter is marketing, not a ticket.
    ({"from": "Miles&Smiles <news@turkishairlines.com>", "subject": "September deals",
      "list-unsubscribe": "<mailto:u@x>"}, "Карантин"),
    # A real flight confirmation goes to the travel folder.
    ({"from": "Turkish Airlines <info@turkishairlines.com>",
      "subject": "Your ticket"}, "Путешествия/Билеты"),
    # An invoice is filed by subject, whatever the sender.
    ({"from": "Some Vendor <billing@vendor.io>", "subject": "Invoice 42"}, "Документы"),
    # Unknown newsletter → quarantine.
    ({"from": "Shop <hi@shop.io>", "subject": "-50%", "precedence": "bulk"}, "Карантин"),
    # Ordinary personal mail stays in the inbox.
    ({"from": "Мама <mama@mail.ru>", "subject": "Позвони"}, None),
])
def test_pick_folder_order(headers, expected):
    assert mod.pick_folder(headers) == expected


def test_sort_box_moves_and_creates_folders():
    client = FakeClient({
        b"1": {"from": "x@revolut.com", "subject": "Statement"},
        b"2": {"from": "news@turkishairlines.com", "subject": "Deals",
               "list-unsubscribe": "<mailto:u@x>"},
        b"3": {"from": "mama@mail.ru", "subject": "Позвони"},
    })
    counts, samples = mod.sort_box(client, days=90, cap=100, dry_run=False)
    assert counts == {"Банки/Revolut": 1, "Карантин": 1}
    assert dict(client.moved) == {b"1": "Банки/Revolut", b"2": "Карантин"}
    assert client.created == ["Банки/Revolut", "Карантин"]
    assert len(samples) == 2


def test_dry_run_touches_nothing():
    client = FakeClient({b"1": {"from": "x@revolut.com", "subject": "Statement"}})
    counts, _ = mod.sort_box(client, days=90, cap=100, dry_run=True)
    assert counts == {"Банки/Revolut": 1}
    assert client.moved == [] and client.created == []


def test_boxes_from_env_needs_all_three_values(monkeypatch):
    monkeypatch.setenv("MAIL_IMAP_1_HOST", "imap.mail.ru")
    monkeypatch.setenv("MAIL_IMAP_1_USER", "a@mail.ru")
    monkeypatch.delenv("MAIL_IMAP_1_PASS", raising=False)
    assert mod.boxes_from_env() == []
    monkeypatch.setenv("MAIL_IMAP_1_PASS", "secret")
    monkeypatch.setenv("MAIL_IMAP_1_NAME", "mail.ru")
    boxes = mod.boxes_from_env()
    assert [(b.name, b.host, b.port) for b in boxes] == [("mail.ru", "imap.mail.ru", 993)]


def test_password_never_reaches_stdout(monkeypatch, capsys):
    monkeypatch.setenv("MAIL_IMAP_1_HOST", "imap.invalid")
    monkeypatch.setenv("MAIL_IMAP_1_USER", "a@mail.ru")
    monkeypatch.setenv("MAIL_IMAP_1_PASS", "s3cret-value")
    monkeypatch.setattr(sys, "argv", ["mail_sort_imap.py"])

    def boom(box):
        raise OSError(f"connection refused for {box.user} with {box.password}")

    monkeypatch.setattr(mod, "ImapBox", boom)
    assert mod.main() == 0
    out = capsys.readouterr()
    assert "s3cret-value" not in out.out and "s3cret-value" not in out.err
    assert "проверь пароль приложения" in out.out


@pytest.mark.parametrize("sender, expected", [
    # A live person writing from a mail provider is not a subscription.
    ("Сергей <shyrbu@yandex.ru>", None),
    ("Друг <ivan@vk.com>", None),
    # The providers' own service mail still is.
    ("Yandex <noreply@yandex.ru>", "Подписки"),
])
def test_mail_provider_domain_is_not_a_subscription(sender, expected):
    assert mod.pick_folder({"from": sender, "subject": "Привет"}) == expected


class FakeFolderClient(FakeClient):
    """Adds the folder-level operations the report and the purge need."""

    def __init__(self, messages, folders=("Trash",), quota=None):
        super().__init__(messages)
        self.folders = set(folders)
        self._quota = quota

    def uids_in(self, folder, older_than_days=0):
        # every fake message is "old" so the purge test is deterministic
        return list(self.messages)

    def trash_folder(self):
        return "Trash" if "Trash" in self.folders else ""

    def quota(self):
        return self._quota


def test_bulk_report_counts_senders_and_flags_unsubscribe():
    client = FakeFolderClient({
        b"1": {"from": "Shop <news@shop.io>", "list-unsubscribe": "<mailto:u@shop.io>"},
        b"2": {"from": "Shop <news@shop.io>", "list-unsubscribe": "<mailto:u@shop.io>"},
        b"3": {"from": "Разное <info@other.ru>"},
    })
    rows = mod.bulk_report(client, "Карантин", 100)
    assert rows[0] == ("news@shop.io", 2, True)
    assert ("info@other.ru", 1, False) in rows


def test_purge_moves_to_trash_and_dry_run_does_not():
    msgs = {b"1": {"from": "a@b.c"}, b"2": {"from": "d@e.f"}}
    client = FakeFolderClient(dict(msgs))
    moved, trash = mod.purge_folder(client, "Карантин", 30, 100, dry_run=True)
    assert (moved, trash) == (2, "Trash") and client.moved == []

    client = FakeFolderClient(dict(msgs))
    moved, trash = mod.purge_folder(client, "Карантин", 30, 100, dry_run=False)
    assert moved == 2 and {f for _u, f in client.moved} == {"Trash"}


def test_purge_refuses_when_there_is_no_trash():
    client = FakeFolderClient({b"1": {"from": "a@b.c"}}, folders=())
    assert mod.purge_folder(client, "Карантин", 30, 100, dry_run=False) == (0, "")
    assert client.moved == []
