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

    def headers_all(self, folder):
        self.bulk_calls = getattr(self, "bulk_calls", 0) + 1
        return dict(self.messages)

    def headers(self, uid):
        self.single_calls = getattr(self, "single_calls", 0) + 1
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
    ({"from": "Some Vendor <billing@vendor.io>", "subject": "Invoice 42"}, "Чеки"),
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


@pytest.mark.parametrize("name, encoded", [
    ("Карантин", "&BBoEMARABDAEPQRCBDgEPQ-"),
    ("Банки", "&BBEEMAQ9BDoEOA-"),
    ("Корзина", "&BBoEPgRABDcEOAQ9BDA-"),
    ("Documents", "Documents"),
    ("R&D", "R&-D"),
])
def test_mutf7_encode_known_values(name, encoded):
    # A wrong encoding here means the server silently never creates the folder.
    assert mod.mutf7_encode(name) == encoded
    assert mod.mutf7_decode(encoded) == name


def test_mutf7_roundtrip_with_nested_path():
    name = "Банки/Прочие"
    assert mod.mutf7_decode(mod.mutf7_encode(name)) == name


class SizeClient(FakeFolderClient):
    def __init__(self, per_folder):
        super().__init__({})
        self.per_folder = per_folder          # folder -> [(uid, size)]
        self.headers_by_uid = {}

    def sizes_in(self, folder):
        return self.per_folder.get(folder, [])

    def headers_all(self, folder):
        return dict(self.headers_by_uid)

    def headers(self, uid):
        return self.headers_by_uid.get(uid, {"from": "x@y.z", "subject": "s"})


def test_folder_sizes_sorted_by_weight_and_skips_empty():
    client = SizeClient({
        "INBOX": [(b"1", 1000), (b"2", 2000)],
        "Отправленные": [(b"3", 9000)],
        "Пусто": [],
    })
    rows = folder_rows = mod.folder_sizes(client, ["INBOX", "Отправленные", "Пусто"])
    assert rows[0] == ("Отправленные", 1, 9000)
    assert ("Пусто", 0, 0) not in folder_rows
    assert rows[1] == ("INBOX", 2, 3000)


def test_heaviest_returns_biggest_first_with_headers():
    client = SizeClient({"INBOX": [(b"small", 10), (b"big", 5_000_000)]})
    client.headers_by_uid = {
        b"big": {"from": "=?UTF-8?B?0J/QtdGC0Y8=?= <p@x.io>", "subject": "Договор"},
        b"small": {"from": "a@b.c", "subject": "hi"},
    }
    rows = mod.heaviest(client, "INBOX", 1)
    assert rows[0][0] == 5_000_000
    assert "Петя" in rows[0][1] and rows[0][2] == "Договор"


def test_sizes_parser_reads_uid_and_size_in_any_order():
    class Conn:
        def __init__(self, rows): self.rows = rows
        def select(self, folder): return "OK", [b"2"]
        def uid(self, *a): return "OK", self.rows

    client = object.__new__(mod.ImapBox)
    client.conn = Conn([b"1 (UID 11 RFC822.SIZE 2048)", b"2 (RFC822.SIZE 4096 UID 22)"])
    client.delimiter = "/"
    client._folders = {"INBOX"}
    assert client.sizes_in("INBOX") == [(b"11", 2048), (b"22", 4096)]


def test_duplicates_keeps_one_copy_per_group():
    client = SizeClient({"Отправленные": [(b"1", 100), (b"2", 100), (b"3", 100),
                                          (b"4", 200)]})
    same = {"to": "client@x.io", "subject": "КП по кухне"}
    client.headers_by_uid = {
        b"1": same, b"2": same, b"3": same,
        b"4": {"to": "other@x.io", "subject": "КП по кухне"},   # other recipient
    }
    groups = mod.duplicates(client, "Отправленные", 100)
    assert len(groups) == 1
    label, extra = groups[0]
    assert extra == [b"2", b"3"]          # the first copy is kept
    assert "КП по кухне" in label and "client@x.io" in label


def test_duplicates_ignores_same_subject_with_different_size():
    client = SizeClient({"Отправленные": [(b"1", 100), (b"2", 900)]})
    client.headers_by_uid = {
        b"1": {"to": "a@x.io", "subject": "Договор"},
        b"2": {"to": "a@x.io", "subject": "Договор"},   # edited version, not a dupe
    }
    assert mod.duplicates(client, "Отправленные", 100) == []


def test_sort_reads_headers_in_one_batch_not_per_message():
    """A big folder must cost one FETCH, not one per message."""
    client = FakeClient({
        b"1": {"from": "x@revolut.com", "subject": "Statement"},
        b"2": {"from": "news@turkishairlines.com", "subject": "Deals",
               "list-unsubscribe": "<mailto:u@x>"},
        b"3": {"from": "mama@mail.ru", "subject": "Позвони"},
    })
    mod.sort_box(client, days=90, cap=100, dry_run=True)
    assert client.bulk_calls == 1
    assert getattr(client, "single_calls", 0) == 0


def test_headers_all_parses_a_real_fetch_response():
    class Conn:
        def select(self, folder):
            return "OK", [b"2"]

        def uid(self, cmd, *a):
            return "OK", [
                (b"1 (UID 11 BODY[HEADER.FIELDS (FROM SUBJECT)] {42}",
                 b"From: a@b.c\r\nSubject: One\r\n\r\n"), b")",
                (b"2 (UID 22 BODY[HEADER.FIELDS (FROM SUBJECT)] {42}",
                 b"From: d@e.f\r\nSubject: Two\r\n\r\n"), b")"]

    client = object.__new__(mod.ImapBox)
    client.conn = Conn()
    client.delimiter = "/"
    client._folders = {"INBOX"}
    got = client.headers_all("INBOX")
    assert got[b"11"]["from"] == "a@b.c" and got[b"22"]["subject"] == "Two"


@pytest.mark.parametrize("sender, subject, expected", [
    # A subscription receipt is not a document — checked on the real mailbox,
    # where «Документы» had turned into 124 Apple receipts.
    ("Apple <no_reply@email.apple.com>", "Your receipt from Apple", "Чеки"),
    ("Orange <notif@notifications.orange.ro>", "Factura ta Orange", "Чеки"),
    # A contract from a human stays a document.
    ("Elena <elena@partner.md>", "Договор аренды на подпись", "Документы"),
    ("Tudor <tudor@bpro.md>", "Contract de prestari servicii", "Документы"),
    # Named banks get their own folder instead of «Прочие».
    ("OTP <noreply@otpbank.md>", "Extras de cont", "Банки/OTP"),
    ("UniCredit <info@unicredit.ro>", "Notificare", "Банки/UniCredit"),
    ("BT <info@bancatransilvania.ro>", "Extras", "Банки/Transilvania"),
])
def test_bank_and_paper_split(sender, subject, expected):
    assert mod.pick_folder({"from": sender, "subject": subject}) == expected
