#!/usr/bin/env python3
"""Sort the owner's Gmail into a fixed folder tree + «Карантин».

Deterministic, no LLM — safe as a `no_agent` cron (stdout is delivered to
Telegram verbatim, so every line here is owner-facing Russian).

Rules are ordered: the first matching rule wins, so a bank receipt never ends
up in «Подписки». Nothing is ever deleted: quarantine = label + remove INBOX
(mail stays in «Вся почта», one filter undoes it). Folders are Gmail labels,
so they show up in Gmail, on the phone and in Hermex.

Usage:
    python3 mail_sort.py --dry-run          # show what would move, change nothing
    python3 mail_sort.py                    # sort the last 90 days
    python3 mail_sort.py --days 365         # first big pass over the archive
    python3 mail_sort.py --rules            # print the folder tree and its rules
"""
from __future__ import annotations

import argparse
import os
import sys

_GWS = "/opt/hermes/skills/productivity/google-workspace/scripts"
for _p in (_GWS, os.path.join(os.path.dirname(__file__), "..", "..", "..",
                              "productivity", "google-workspace", "scripts")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import google_api as gws
except Exception as exc:  # pragma: no cover - prod-only path
    sys.stderr.write(f"[mail_sort] cannot import google-workspace helper: {exc}\n")
    print("⚠️ Раскладка почты сейчас недоступна — не удалось подключиться к Google.")
    raise SystemExit(0)

QUARANTINE = "Карантин"

# (folder, gmail query) — ORDER MATTERS, first match wins.
# `quarantine=True` also takes the mail out of the inbox.
RULES: list[tuple[str, str, bool]] = [
    # --- Безопасность: всегда мимо карантина, даже если Google зовёт это «промо»
    ("Безопасность", "from:(accounts.google.com OR no-reply@accounts.google.com OR "
                     "appleid.apple.com OR security-noreply@ OR account-security-noreply@)", False),
    # --- Банки и платежи
    ("Банки/Revolut", "from:revolut.com", False),
    ("Банки/Wise", "from:wise.com", False),
    ("Банки/PayPal", "from:paypal.", False),
    ("Банки/Stripe", "from:stripe.com", False),
    ("Банки/Raiffeisen", "from:raiffeisen", False),
    ("Банки/Erste", "from:(erstebank OR sparkasse OR georgebank)", False),
    ("Банки/BCR", "from:bcr.ro", False),
    ("Банки/BRD", "from:brd.ro", False),
    ("Банки/ING", "from:ing.", False),
    ("Банки/MAIB", "from:maib.md", False),
    ("Банки/Victoriabank", "from:victoriabank.md", False),
    ("Банки/Прочие", "from:(bank OR banca OR banking) -from:(revolut OR wise OR paypal)", False),
    # --- Путешествия
    ("Путешествия/Билеты", "from:(turkishairlines.com OR wizzair.com OR ryanair.com OR "
                           "lufthansa.com OR austrian.com OR aegeanair.com OR kiwi.com OR "
                           "edreams OR skyscanner OR omio OR flixbus OR cfrcalatori)", False),
    ("Путешествия/Отели", "from:(booking.com OR airbnb.com OR hotels.com OR expedia OR "
                          "agoda.com OR trivago OR marriott OR hilton)", False),
    ("Путешествия/Авто", "from:(rentalcars.com OR sixt OR avis OR hertz OR europcar OR "
                         "carwiz OR autoeurope)", False),
    # --- Жильё и недвижимость
    ("Жильё", "from:(immobilienscout24 OR willhaben.at OR olx. OR imobiliare.ro OR "
              "999.md OR remax OR engelvoelkers)", False),
    # --- Документы: счета, инвойсы, договоры
    ("Документы", "subject:(invoice OR receipt OR factura OR factură OR счёт OR счет OR "
                  "квитанция OR contract OR договор) -category:promotions", False),
    # --- Подписки и сервисы (после банков и безопасности — порядок важен)
    ("Подписки", "from:(evernote.com OR apple.com OR microsoft.com OR openai.com OR "
                 "anthropic.com OR adobe.com OR spotify.com OR netflix.com OR "
                 "dropbox.com OR notion.so OR github.com OR railway.app)", False),
    # --- Карантин: шум. Последним, чтобы всё полезное успело разобраться выше
    (QUARANTINE, "category:promotions", True),
    (QUARANTINE, "category:social", True),
    (QUARANTINE, "unsubscribe category:updates -subject:(invoice OR receipt OR factura OR "
                 "счёт OR счет OR contract OR договор)", True),
]


# Every folder this script owns. A message that already carries one of them is
# skipped by ALL rules: that is what makes repeat runs idempotent and keeps the
# first-match order stable between runs (a bank receipt labelled today must not
# be pulled into «Карантин» tomorrow by the promotions rule).
MANAGED_TOP = sorted({folder.split("/")[0] for folder, _q, _quar in RULES})

# Folders that accept mail even when Google tags it as promotions/social:
# a security alert, a bank statement or an invoice matters whatever tab it
# landed in. Everywhere else marketing belongs in «Карантин», not in the
# working folder (an airline newsletter is not a ticket).
PROMO_ALLOWED = {"Безопасность", "Банки", "Документы", QUARANTINE}


def _svc():
    return gws.build_service("gmail", "v1")


def _labels(svc) -> dict[str, str]:
    return {l["name"]: l["id"] for l in
            svc.users().labels().list(userId="me").execute().get("labels", [])}


def _ensure_label(svc, name: str, cache: dict[str, str]) -> str:
    """Label id for `name`, creating it (and its parents) when missing."""
    parts = name.split("/")
    for i in range(1, len(parts) + 1):
        path = "/".join(parts[:i])
        if path in cache:
            continue
        created = svc.users().labels().create(
            userId="me",
            body={"name": path, "labelListVisibility": "labelShow",
                  "messageListVisibility": "show"},
        ).execute()
        cache[path] = created["id"]
    return cache[name]


def _ids_for(svc, query: str, cap: int) -> list[str]:
    ids: list[str] = []
    page = None
    while len(ids) < cap:
        resp = svc.users().messages().list(
            userId="me", q=query, maxResults=min(100, cap - len(ids)), pageToken=page,
        ).execute()
        ids += [m["id"] for m in resp.get("messages", [])]
        page = resp.get("nextPageToken")
        if not page:
            break
    return ids[:cap]


def _sample(svc, ids: list[str], n: int = 2) -> list[str]:
    out = []
    for mid in ids[:n]:
        msg = svc.users().messages().get(
            userId="me", id=mid, format="metadata",
            metadataHeaders=["Subject", "From"]).execute()
        h = {x["name"]: x["value"] for x in msg.get("payload", {}).get("headers", [])}
        out.append(f"{h.get('From', '?')[:26]} — {h.get('Subject', '(без темы)')[:38]}")
    return out


def _print_rules() -> int:
    print("📂 Папки почты и правила\n")
    for folder, query, quar in RULES:
        mark = " → в карантин (из входящих)" if quar else ""
        print(f"• {folder}{mark}\n    {query}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Sort Gmail into folders + quarantine.")
    ap.add_argument("--days", type=int, default=90, help="How far back to look.")
    ap.add_argument("--max", type=int, default=400, help="Max messages per rule.")
    ap.add_argument("--dry-run", action="store_true", help="Report only, change nothing.")
    ap.add_argument("--rules", action="store_true", help="Print the folder tree and exit.")
    args = ap.parse_args()
    if args.rules:
        return _print_rules()
    try:
        return _sort(args)
    except gws.GoogleAuthError:
        msg = gws.google_down_alert()
        if msg:
            print(msg)
        return 0
    except Exception as exc:
        sys.stderr.write(f"[mail_sort] failed: {type(exc).__name__}: {exc}\n")
        print("⚠️ Раскладка почты сегодня не прошла — нужна проверка.")
        return 0


def _sort(args) -> int:
    svc = _svc()
    cache = _labels(svc)
    window = f"newer_than:{args.days}d -in:spam -in:trash"

    seen: set[str] = set()
    lines: list[str] = []
    moved_total = 0
    quarantined = 0

    skip_sorted = " ".join(f"-label:{top}" for top in MANAGED_TOP)
    for folder, query, quar in RULES:
        # Already-sorted mail is skipped entirely, so re-runs are cheap and the
        # owner's own filing is never overwritten.
        full = f"{window} ({query}) {skip_sorted}"
        if folder.split("/")[0] not in PROMO_ALLOWED:
            full += " -category:promotions -category:social"
        ids = [i for i in _ids_for(svc, full, args.max) if i not in seen]
        if not ids:
            continue
        seen.update(ids)
        sample = _sample(svc, ids)
        if not args.dry_run:
            label_id = _ensure_label(svc, folder, cache)
            body = {"ids": [], "addLabelIds": [label_id]}
            if quar:
                body["removeLabelIds"] = ["INBOX"]
            for i in range(0, len(ids), 1000):
                svc.users().messages().batchModify(
                    userId="me", body={**body, "ids": ids[i:i + 1000]}).execute()
        moved_total += len(ids)
        if quar:
            quarantined += len(ids)
        lines.append(f"  • {folder}: {len(ids)}")
        lines += [f"      — {s}" for s in sample]

    if moved_total == 0:
        if args.dry_run:
            print("📭 Раскладывать нечего — всё уже по папкам.")
        return 0

    head = "🗂 *Раскладка почты*" + (" — примерка, ничего не тронуто" if args.dry_run else "")
    out = [head, "", f"{'Разложилось бы' if args.dry_run else 'Разложено'}: *{moved_total}* писем"]
    out += lines
    if quarantined:
        out += ["", f"🚦 В «{QUARANTINE}»: *{quarantined}* — из входящих убраны, письма целы."]
    inbox_left = len(_ids_for(svc, "in:inbox is:unread", 300))
    out += ["", f"⭐️ Непрочитанных во входящих: *{inbox_left}*"]
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
