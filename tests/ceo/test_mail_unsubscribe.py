"""mail_unsubscribe.py: what it acts on, what it refuses, what it remembers."""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parents[2] / "skills" / "ceo" / "mail" /
          "scripts" / "mail_unsubscribe.py")


def _load(monkeypatch, home: Path):
    monkeypatch.setenv("HERMES_HOME", str(home))
    spec = importlib.util.spec_from_file_location("ceo_mail_unsub", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod(monkeypatch, tmp_path):
    return _load(monkeypatch, tmp_path)


class FakeClient:
    def __init__(self, messages):
        self.messages = messages

    def uids_in(self, folder, older_than_days=0):
        return list(self.messages)

    def headers(self, uid):
        return self.messages[uid]

    def close(self):
        pass


def test_parse_targets_splits_urls_and_mailto(mod):
    urls, mails = mod.parse_targets("<https://x.io/u?id=1>, <mailto:stop@x.io>")
    assert urls == ["https://x.io/u?id=1"] and mails == ["stop@x.io"]


def test_http_only_link_is_not_followed(mod):
    urls, mails = mod.parse_targets("<http://insecure.io/u>")
    assert urls == [] and mails == []


def test_bank_and_security_mail_is_protected(mod):
    bank = {"from": "Revolut <no-reply@revolut.com>", "subject": "Statement",
            "list-unsubscribe": "<mailto:stop@revolut.com>"}
    google = {"from": "Google <no-reply@accounts.google.com>", "subject": "Вход",
              "list-unsubscribe": "<mailto:stop@google.com>"}
    shop = {"from": "Shop <news@shop.io>", "subject": "-50%",
            "list-unsubscribe": "<mailto:stop@shop.io>"}
    assert mod.protected(bank) and mod.protected(google)
    assert not mod.protected(shop)


def test_collect_groups_senders_and_skips_protected(mod):
    client = FakeClient({
        b"1": {"from": "Shop <news@shop.io>", "list-unsubscribe": "<https://shop.io/u>",
               "list-unsubscribe-post": "List-Unsubscribe=One-Click"},
        b"2": {"from": "Shop <news@shop.io>", "list-unsubscribe": "<https://shop.io/u>"},
        b"3": {"from": "Revolut <no-reply@revolut.com>", "subject": "Statement",
               "list-unsubscribe": "<mailto:stop@revolut.com>"},
        b"4": {"from": "Мама <mama@mail.ru>", "subject": "Позвони"},  # no header
    })
    found = mod.collect(client, "Карантин", 100)
    assert set(found) == {"news@shop.io"}
    assert found["news@shop.io"]["count"] == 2
    assert found["news@shop.io"]["one_click"] is True


def test_spam_folder_is_refused(mod, monkeypatch, capsys):
    monkeypatch.setenv("MAIL_IMAP_1_HOST", "imap.mail.ru")
    monkeypatch.setenv("MAIL_IMAP_1_USER", "a@mail.ru")
    monkeypatch.setenv("MAIL_IMAP_1_PASS", "x")
    monkeypatch.setattr(sys, "argv", ["mail_unsubscribe.py", "--folder", "Спам"])
    assert mod.main() == 0
    assert "подтверждает спамеру" in capsys.readouterr().out


def test_ledger_roundtrip_and_skip_of_known_sender(mod, monkeypatch, capsys):
    mod.save_ledger({"a@mail.ru|news@shop.io": {"ok": True, "how": "200"}})
    assert mod.load_ledger()["a@mail.ru|news@shop.io"]["ok"] is True

    monkeypatch.setenv("MAIL_IMAP_1_HOST", "imap.mail.ru")
    monkeypatch.setenv("MAIL_IMAP_1_USER", "a@mail.ru")
    monkeypatch.setenv("MAIL_IMAP_1_PASS", "x")
    client = FakeClient({b"1": {"from": "Shop <news@shop.io>",
                                "list-unsubscribe": "<https://shop.io/u>",
                                "list-unsubscribe-post": "List-Unsubscribe=One-Click"}})
    monkeypatch.setattr(mod.engine, "_connect", lambda box: client)
    called = []
    monkeypatch.setattr(mod, "one_click", lambda url: called.append(url) or (True, "200"))
    monkeypatch.setattr(sys, "argv", ["mail_unsubscribe.py"])

    assert mod.main() == 0
    assert called == []  # already unsubscribed once — never poked again
    assert "Уже были отписаны раньше: 1" in capsys.readouterr().out


def test_one_click_sender_is_posted_once(mod, monkeypatch, capsys):
    monkeypatch.setenv("MAIL_IMAP_1_HOST", "imap.mail.ru")
    monkeypatch.setenv("MAIL_IMAP_1_USER", "a@mail.ru")
    monkeypatch.setenv("MAIL_IMAP_1_PASS", "x")
    client = FakeClient({b"1": {"from": "Shop <news@shop.io>",
                                "list-unsubscribe": "<https://shop.io/u>",
                                "list-unsubscribe-post": "List-Unsubscribe=One-Click"}})
    monkeypatch.setattr(mod.engine, "_connect", lambda box: client)
    posted = []
    monkeypatch.setattr(mod, "one_click", lambda url: (posted.append(url), (True, "200"))[1])
    monkeypatch.setattr(sys, "argv", ["mail_unsubscribe.py"])

    assert mod.main() == 0
    assert posted == ["https://shop.io/u"]
    assert "Отписал" in capsys.readouterr().out
    assert mod.load_ledger()["a@mail.ru|news@shop.io"]["ok"] is True


def test_ledger_is_written_immediately_after_each_success(mod, monkeypatch, tmp_path):
    monkeypatch.setenv("MAIL_IMAP_1_HOST", "imap.mail.ru")
    monkeypatch.setenv("MAIL_IMAP_1_USER", "a@mail.ru")
    monkeypatch.setenv("MAIL_IMAP_1_PASS", "x")
    client = FakeClient({
        b"1": {"from": "A <a@shop.io>", "list-unsubscribe": "<https://shop.io/a>",
               "list-unsubscribe-post": "List-Unsubscribe=One-Click"},
        b"2": {"from": "B <b@shop.io>", "list-unsubscribe": "<https://shop.io/b>",
               "list-unsubscribe-post": "List-Unsubscribe=One-Click"},
    })
    monkeypatch.setattr(mod.engine, "_connect", lambda box: client)
    seen = []

    def flaky(url):
        seen.append(url)
        if len(seen) == 2:
            raise KeyboardInterrupt  # the run dies right after the first success
        return True, "200"

    monkeypatch.setattr(mod, "one_click", flaky)
    monkeypatch.setattr(sys, "argv", ["mail_unsubscribe.py"])
    with pytest.raises(KeyboardInterrupt):
        mod.main()
    # The first sender is already on disk although the run never finished.
    assert len(mod.load_ledger()) == 1


def test_dry_run_sends_nothing(mod, monkeypatch, capsys):
    monkeypatch.setenv("MAIL_IMAP_1_HOST", "imap.mail.ru")
    monkeypatch.setenv("MAIL_IMAP_1_USER", "a@mail.ru")
    monkeypatch.setenv("MAIL_IMAP_1_PASS", "x")
    client = FakeClient({b"1": {"from": "Shop <news@shop.io>",
                                "list-unsubscribe": "<https://shop.io/u>",
                                "list-unsubscribe-post": "List-Unsubscribe=One-Click"}})
    monkeypatch.setattr(mod.engine, "_connect", lambda box: client)
    monkeypatch.setattr(mod, "one_click", lambda url: pytest.fail("dry run must not post"))
    monkeypatch.setattr(sys, "argv", ["mail_unsubscribe.py", "--dry-run"])

    assert mod.main() == 0
    assert "примерка" in capsys.readouterr().out
    assert mod.load_ledger() == {}
