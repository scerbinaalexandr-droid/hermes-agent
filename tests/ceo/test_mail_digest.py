"""mail_digest.py: reports important mail only, stays silent otherwise."""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parents[2] / "skills" / "ceo" / "mail" /
          "scripts" / "mail_digest.py")


def _load():
    spec = importlib.util.spec_from_file_location("ceo_mail_digest", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load()


class FakeClient:
    def __init__(self, messages, unseen=None):
        self.messages = messages
        self._unseen = unseen if unseen is not None else list(messages)

    def unseen_uids(self, days):
        return list(self._unseen)

    def headers_all(self, folder):
        return dict(self.messages)

    def headers(self, uid):
        return self.messages[uid]

    def close(self):
        pass


PERSON = {"from": "Elena Seremet <elena@partner.md>", "subject": "Договор аренды"}
ADVERT = {"from": "Shop <news@shop.io>", "subject": "-50%",
          "list-unsubscribe": "<mailto:u@shop.io>"}
SERVICE = {"from": "Netflix <info@netflix.com>", "subject": "Новинки"}
BANK = {"from": "OTP <noreply@otpbank.md>", "subject": "Extras de cont"}


def test_advertising_and_subscriptions_never_appear():
    assert mod.important(PERSON) is True
    assert mod.important(BANK) is True        # a bank statement matters
    assert mod.important(ADVERT) is False     # bulk mail
    assert mod.important(SERVICE) is False    # «Подписки»


def test_digest_lists_people_and_counts_noise():
    client = FakeClient({b"1": PERSON, b"2": ADVERT, b"3": SERVICE, b"4": BANK})
    lines, skipped = mod.digest_box(client, hours=24)
    assert skipped == 2
    assert any("Elena Seremet" in l and "Договор аренды" in l for l in lines)
    assert not any("shop.io" in l or "Netflix" in l for l in lines)


def test_read_mail_is_not_reported():
    client = FakeClient({b"1": PERSON}, unseen=[])
    assert mod.digest_box(client, hours=24) == ([], 0)


def test_quiet_when_nothing_important(monkeypatch, capsys):
    monkeypatch.setenv("MAIL_IMAP_1_HOST", "imap.mail.ru")
    monkeypatch.setenv("MAIL_IMAP_1_USER", "a@mail.ru")
    monkeypatch.setenv("MAIL_IMAP_1_PASS", "x")
    monkeypatch.setenv("MAIL_IMAP_1_IMPORTANT", "1")
    monkeypatch.setattr(mod.engine, "_connect",
                        lambda box: FakeClient({b"1": ADVERT}))
    monkeypatch.setattr(sys, "argv", ["mail_digest.py"])
    assert mod.main() == 0
    assert capsys.readouterr().out == ""     # a quiet morning says nothing


def test_digest_prints_one_block_per_box(monkeypatch, capsys):
    monkeypatch.setenv("MAIL_IMAP_1_HOST", "imap.mail.ru")
    monkeypatch.setenv("MAIL_IMAP_1_USER", "a@mail.ru")
    monkeypatch.setenv("MAIL_IMAP_1_PASS", "x")
    monkeypatch.setenv("MAIL_IMAP_1_NAME", "mail.ru")
    monkeypatch.setenv("MAIL_IMAP_1_IMPORTANT", "1")
    monkeypatch.setattr(mod.engine, "_connect",
                        lambda box: FakeClient({b"1": PERSON, b"2": ADVERT}))
    monkeypatch.setattr(sys, "argv", ["mail_digest.py"])
    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "📬 *Почта* — 1 важных" in out and "шум (1) убран" in out
    assert "*mail.ru*" in out and "Elena Seremet" in out


def test_boxes_without_the_important_flag_are_not_reported(monkeypatch, capsys):
    """Tidy-only boxes never reach the digest, however much unread they hold."""
    monkeypatch.setenv("MAIL_IMAP_1_HOST", "imap.mail.ru")
    monkeypatch.setenv("MAIL_IMAP_1_USER", "a@mail.ru")
    monkeypatch.setenv("MAIL_IMAP_1_PASS", "x")
    monkeypatch.delenv("MAIL_IMAP_1_IMPORTANT", raising=False)
    monkeypatch.setattr(mod.engine, "_connect",
                        lambda box: FakeClient({b"1": PERSON}))
    monkeypatch.setattr(sys, "argv", ["mail_digest.py"])
    assert mod.main() == 0
    assert capsys.readouterr().out == ""
