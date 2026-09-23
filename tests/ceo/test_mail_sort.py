"""mail_sort.py: ordered rules, quarantine, idempotency, dry-run."""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "skills" / "ceo" / "mail" / "scripts" / "mail_sort.py"


class FakeMessages:
    def __init__(self, svc):
        self.svc = svc

    def list(self, userId, q, maxResults, pageToken=None):
        return _Exec({"messages": [{"id": i} for i in self.svc.match(q)]})

    def get(self, userId, id, format, metadataHeaders):
        return _Exec({"payload": {"headers": [{"name": "From", "value": f"{id}@x.io"},
                                              {"name": "Subject", "value": f"тема {id}"}]}})

    def batchModify(self, userId, body):
        self.svc.modified.append(body)
        for mid in body["ids"]:
            self.svc.labels_on.setdefault(mid, set()).update(body.get("addLabelIds", []))
            for rm in body.get("removeLabelIds", []):
                self.svc.labels_on.get(mid, set()).discard(rm)
        return _Exec({})


class FakeLabels:
    def __init__(self, svc):
        self.svc = svc

    def list(self, userId):
        return _Exec({"labels": [{"name": n, "id": i} for n, i in self.svc.store.items()]})

    def create(self, userId, body):
        name = body["name"]
        self.svc.store[name] = f"Label_{len(self.svc.store)}"
        self.svc.created.append(name)
        return _Exec({"id": self.svc.store[name]})


class _Exec:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class FakeService:
    """Gmail stub: `mail` maps message id → the rule queries it matches."""

    def __init__(self, mail: dict[str, list[str]]):
        self.mail = mail
        self.store = {"INBOX": "INBOX"}
        self.created: list[str] = []
        self.modified: list[dict] = []
        self.labels_on: dict[str, set[str]] = {}

    def match(self, q: str) -> list[str]:
        # Drop negated terms before matching: "-category:promotions" must not
        # read as the positive "category:promotions".
        words = q.replace("(", " ").replace(")", " ").split()
        positive = " ".join(w for w in words if not w.startswith("-"))
        negated = {w[1:] for w in words if w.startswith("-")}
        hits = []
        for mid, tags in self.mail.items():
            if not any(t in positive for t in tags):
                continue
            if any(t in negated for t in tags):
                continue
            # honour the "-label:<top>" exclusion the script adds
            excluded = False
            for part in q.split():
                if part.startswith("-label:"):
                    top = part[len("-label:"):]
                    have = {n for n, i in self.store.items() if i in self.labels_on.get(mid, set())}
                    if any(n.split("/")[0] == top for n in have):
                        excluded = True
            if not excluded:
                hits.append(mid)
        return hits

    def users(self):
        return self

    def messages(self):
        return FakeMessages(self)

    def labels(self):
        return FakeLabels(self)


def _load(service):
    fake = types.ModuleType("google_api")
    fake.build_service = lambda *a, **k: service
    fake.GoogleAuthError = type("GoogleAuthError", (Exception,), {})
    fake.google_down_alert = lambda: "⚠️ Google отключён."
    sys.modules["google_api"] = fake
    spec = importlib.util.spec_from_file_location("ceo_mail_sort", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def svc():
    s = FakeService({
        "bank": ["from:revolut.com", "category:promotions"],   # bank rule comes first
        "promo": ["category:promotions"],
        "flight": ["turkishairlines.com"],
        "airline_ad": ["turkishairlines.com", "category:promotions"],
        "security": ["accounts.google.com", "category:promotions"],
    })
    return s


class Args:
    days = 90
    max = 400
    dry_run = False
    rules = False


def test_first_matching_rule_wins_and_quarantine_leaves_inbox(svc):
    mod = _load(svc)
    assert mod._sort(Args()) == 0

    def labels_of(mid):
        return {n for n, i in svc.store.items() if i in svc.labels_on.get(mid, set())}

    assert labels_of("bank") == {"Банки/Revolut"}          # not «Карантин»
    assert labels_of("security") == {"Безопасность"}       # security beats promotions
    assert labels_of("flight") == {"Путешествия/Билеты"}
    assert labels_of("promo") == {"Карантин"}
    # An airline newsletter is marketing, not a ticket.
    assert labels_of("airline_ad") == {"Карантин"}

    # Only quarantined mail loses INBOX.
    quarantine_calls = [m for m in svc.modified if "removeLabelIds" in m]
    assert all(m["removeLabelIds"] == ["INBOX"] for m in quarantine_calls)
    assert {i for m in quarantine_calls for i in m["ids"]} == {"promo", "airline_ad"}
    # Nested folder creates its parent too.
    assert "Банки" in svc.created and "Банки/Revolut" in svc.created


def test_second_run_is_idempotent(svc):
    mod = _load(svc)
    mod._sort(Args())
    before = len(svc.modified)
    mod._sort(Args())
    assert len(svc.modified) == before  # nothing re-labelled


def test_dry_run_changes_nothing(svc):
    mod = _load(svc)
    args = Args()
    args.dry_run = True
    mod._sort(args)
    assert svc.modified == [] and svc.created == []
