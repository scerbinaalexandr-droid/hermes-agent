#!/usr/bin/env python3
"""Single source of truth for the owner's mail folders.

Both engines read these rules: `mail_sort.py` (Gmail, via the Google API) and
`mail_sort_imap.py` (any IMAP box, e.g. mail.ru). Keeping one list means a
folder added for one mailbox appears in the other, and the owner's mental
model stays the same everywhere.

A rule matches on sender substrings and/or subject substrings. Order matters:
the first matching rule wins, so a bank statement never lands in «Подписки».
`promo_ok=True` marks the folders that accept marketing too (a statement or an
invoice matters whatever tab the provider put it in); everywhere else bulk mail
goes to «Карантин».
"""
from __future__ import annotations

from dataclasses import dataclass, field

QUARANTINE = "Карантин"


@dataclass(frozen=True)
class Rule:
    folder: str
    senders: tuple[str, ...] = ()
    subjects: tuple[str, ...] = ()
    exclude_senders: tuple[str, ...] = ()
    # Gmail-only extras (its own tabs); IMAP has no equivalent and ignores them.
    gmail_query: str = ""
    quarantine: bool = False
    promo_ok: bool = field(default=False)


# A receipt for a subscription and a signed contract are different things and
# belong in different folders: checked on the owner's working mailbox, where
# «Документы» was 124 Apple receipts before this split.
RECEIPT_WORDS = ("invoice", "receipt", "factura", "factură", "счёт", "счет",
                 "квитанция", "чек", "payment", "оплата", "платёж", "bon fiscal")
CONTRACT_WORDS = ("contract", "договор", "акт ", "соглашение", "agreement",
                  "nda", "оферта", "приложение к договору")
INVOICE_WORDS = RECEIPT_WORDS + CONTRACT_WORDS

RULES: tuple[Rule, ...] = (
    # Security first: an alert about the account outranks every other rule.
    Rule("Безопасность", promo_ok=True, senders=(
        "accounts.google.com", "no-reply@accounts.google.com", "appleid.apple.com",
        "security-noreply@", "account-security-noreply@", "noreply@account.mail.ru",
        "security@mail.ru")),
    # Banks and payments.
    Rule("Банки/Revolut", promo_ok=True, senders=("revolut.com",)),
    Rule("Банки/Wise", promo_ok=True, senders=("wise.com",)),
    Rule("Банки/PayPal", promo_ok=True, senders=("paypal.",)),
    Rule("Банки/Stripe", promo_ok=True, senders=("stripe.com",)),
    Rule("Банки/Raiffeisen", promo_ok=True, senders=("raiffeisen",)),
    Rule("Банки/Erste", promo_ok=True, senders=("erstebank", "sparkasse", "georgebank")),
    Rule("Банки/BCR", promo_ok=True, senders=("bcr.ro",)),
    Rule("Банки/BRD", promo_ok=True, senders=("brd.ro",)),
    Rule("Банки/ING", promo_ok=True, senders=("ing.",)),
    Rule("Банки/MAIB", promo_ok=True, senders=("maib.md",)),
    Rule("Банки/Victoriabank", promo_ok=True, senders=("victoriabank.md",)),
    Rule("Банки/OTP", promo_ok=True, senders=("otpbank", "otp-bank")),
    Rule("Банки/UniCredit", promo_ok=True, senders=("unicredit",)),
    Rule("Банки/Transilvania", promo_ok=True, senders=("bancatransilvania", "btrl.ro")),
    Rule("Банки/Fincombank", promo_ok=True, senders=("fincombank",)),
    Rule("Банки/Moldindconbank", promo_ok=True, senders=("micb.md", "moldindconbank")),
    Rule("Банки/Прочие", promo_ok=True, senders=("bank", "banca", "banking"),
         exclude_senders=("revolut", "wise", "paypal")),
    # Travel.
    Rule("Путешествия/Билеты", senders=(
        "turkishairlines.com", "wizzair.com", "ryanair.com", "lufthansa.com",
        "austrian.com", "aegeanair.com", "kiwi.com", "edreams", "skyscanner",
        "omio", "flixbus", "cfrcalatori", "aeroflot", "s7.ru", "utair")),
    Rule("Путешествия/Отели", senders=(
        "booking.com", "airbnb.com", "hotels.com", "expedia", "agoda.com",
        "trivago", "marriott", "hilton", "ostrovok", "sutochno")),
    Rule("Путешествия/Авто", senders=(
        "rentalcars.com", "sixt", "avis", "hertz", "europcar", "carwiz", "autoeurope")),
    # Housing and real estate.
    Rule("Жильё", senders=(
        "immobilienscout24", "willhaben.at", "olx.", "imobiliare.ro", "999.md",
        "remax", "engelvoelkers", "cian.ru", "avito.ru")),
    # Papers worth keeping: contracts and acts.
    Rule("Документы", promo_ok=True, subjects=CONTRACT_WORDS),
    # Money paid: receipts, invoices, utility bills.
    Rule("Чеки", promo_ok=True, subjects=RECEIPT_WORDS),
    # Services and subscriptions — after banks and security, order matters.
    # Only service senders, never a whole mail provider: "yandex" used to put
    # a live person writing from @yandex.ru into «Подписки».
    Rule("Подписки", senders=(
        "evernote.com", "apple.com", "microsoft.com", "openai.com", "anthropic.com",
        "adobe.com", "spotify.com", "netflix.com", "dropbox.com", "notion.so",
        "github.com", "railway.app", "noreply@yandex", "no-reply@yandex",
        "notify@vk.com", "noreply@vk.com")),
    # Noise last, so everything useful is filed before it.
    Rule(QUARANTINE, quarantine=True, promo_ok=True, gmail_query="category:promotions"),
    Rule(QUARANTINE, quarantine=True, promo_ok=True, gmail_query="category:social"),
    Rule(QUARANTINE, quarantine=True, promo_ok=True,
         gmail_query="unsubscribe category:updates -subject:("
                     + " OR ".join(INVOICE_WORDS) + ")"),
)

# The hub: every box forwards new mail to scerbina21@gmail.com, so a label
# says where each letter came from. The marker is the ORIGINAL recipient
# (`to:`): a forwarded letter keeps «To: ascerbina@mail.ru», and Gmail indexes
# that header. `deliveredto:` looked like the natural choice but returns
# nothing for forwarded mail (checked live on 2026-09-24).
# Two contours, by the owner's decision (2026-09-25):
#   важный  — scerbinaalexandr@gmail.com ← alexandr.scerbina@gmail.com
#   прочее  — scerbina21@gmail.com ← остальные ящики (этот список)
# The important contour is a single mailbox the owner works in himself, so it
# needs no source labels; «прочее» is the one Hermes keeps in order.
SOURCES: tuple[tuple[str, str], ...] = (
    ("От/mail.ru", "ascerbina@mail.ru"),
    ("От/Бодар", "bodaro@bk.ru"),
    ("От/Потёмкин", "alex.potiomkin@bk.ru"),
    ("От/Офис", "beldepofarm@gmail.com"),
    ("От/Gmail третий", "alexscerbina@gmail.com"),
)


def source_query(label: str, address: str) -> str:
    """Gmail search for mail forwarded from one box and not yet marked."""
    return f'(to:{address} OR cc:{address}) -label:"{label}"'


# Every folder these rules own; a message already in one of them is left alone.
MANAGED_TOP = sorted({r.folder.split("/")[0] for r in RULES})


def _or_group(field_name: str, values: tuple[str, ...]) -> str:
    return f"{field_name}:({' OR '.join(values)})"


def gmail_query(rule: Rule) -> str:
    """The Gmail search that selects the mail this rule owns."""
    if rule.gmail_query:
        return rule.gmail_query
    parts = []
    if rule.senders:
        parts.append(_or_group("from", rule.senders))
    if rule.subjects:
        parts.append(_or_group("subject", rule.subjects))
    query = " OR ".join(parts)
    if len(parts) > 1:
        query = f"({query})"
    if rule.exclude_senders:
        query += " -" + _or_group("from", rule.exclude_senders)
    return query


def matches(rule: Rule, sender: str, subject: str) -> bool:
    """Local matching for engines without a server-side search (IMAP)."""
    if rule.gmail_query:
        return False  # Gmail's own tabs; the IMAP engine uses bulk_mail() instead
    sender_l = (sender or "").lower()
    subject_l = (subject or "").lower()
    if any(x.lower() in sender_l for x in rule.exclude_senders):
        return False
    if any(x.lower() in sender_l for x in rule.senders):
        return True
    return bool(rule.subjects) and any(x.lower() in subject_l for x in rule.subjects)


def bulk_mail(headers: dict[str, str]) -> bool:
    """Newsletter/marketing, judged from headers (IMAP has no Gmail tabs).

    `List-Unsubscribe` is what every legitimate bulk sender must include, and
    `Precedence: bulk|list` is the old convention for the same thing.
    """
    low = {k.lower(): (v or "") for k, v in headers.items()}
    if low.get("list-unsubscribe") or low.get("list-id"):
        return True
    return low.get("precedence", "").strip().lower() in ("bulk", "list", "junk")


def describe() -> str:
    lines = ["📂 Папки почты и правила", ""]
    for rule in RULES:
        mark = " → в карантин (из входящих)" if rule.quarantine else ""
        what = rule.gmail_query or ", ".join(rule.senders or rule.subjects)
        lines.append(f"• {rule.folder}{mark}\n    {what}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(describe())
