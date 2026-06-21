#!/usr/bin/env python3
"""Birthday manager for the CEO calendar (connected Google Workspace OAuth).

Two modes, both on the user's PRIMARY calendar (Hermes is owner):
  --add    Create a recurring (yearly) all-day birthday event.
  --check  List birthdays occurring today (or within --days) → Telegram digest.
           Stays SILENT (no output) when there are none, so the daily cron
           never spams.

Source of truth = the calendar itself, so newly-added and imported birthdays
are all covered by the morning reminder. Uses the google-workspace credentials
(no re-auth). All-day + RRULE:FREQ=YEARLY via the raw Calendar API (the bundled
`calendar create` supports neither).

Usage:
  python3 birthday.py --add --name "Маша Иванова" --day 15 --month 3 --year 1990
  python3 birthday.py --add --name "Годовщина свадьбы" --day 5 --month 6 --kind wedding
  python3 birthday.py --check            # today only (for the morning cron)
  python3 birthday.py --check --days 7   # today + next 7 days preview
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys

_GWS = "/opt/hermes/skills/productivity/google-workspace/scripts"
for p in (_GWS, os.path.join(os.path.dirname(__file__), "..", "..", "..", "productivity",
                             "google-workspace", "scripts")):
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

try:
    import google_api as gws
except Exception as exc:  # pragma: no cover - prod-only path
    sys.stderr.write(f"[birthday] cannot import google-workspace helper: {exc}\n")
    raise SystemExit(1)

BDAY_EMOJI = ("🎂", "💍")  # birthday / wedding-anniversary markers


def _svc():
    return gws.build_service("calendar", "v3")


def _today() -> _dt.date:
    # Chisinau (EEST, UTC+3) — the CEO's timezone for "today".
    return (_dt.datetime.utcnow() + _dt.timedelta(hours=3)).date()


def add(args) -> int:
    svc = _svc()
    emoji = "💍" if args.kind == "wedding" else "🎂"
    year = args.year
    base_year = year if year else _today().year
    try:
        start = _dt.date(base_year, args.month, args.day)
    except ValueError:
        print(f"⚠️ Некорректная дата: {args.day}.{args.month}")
        return 1
    title = f"{emoji} {args.name}" + (f" (г.р. {year})" if year and args.kind != "wedding"
                                      else (f" ({year})" if year else ""))
    body = {
        "summary": title,
        "start": {"date": start.isoformat()},
        "end": {"date": (start + _dt.timedelta(days=1)).isoformat()},
        "recurrence": ["RRULE:FREQ=YEARLY"],
        "transparency": "transparent",
        "reminders": {"useDefault": False,
                      "overrides": [{"method": "popup", "minutes": 0}]},
    }
    svc.events().insert(calendarId="primary", body=body).execute()
    when = f"{args.day:02d}.{args.month:02d}" + (f".{year}" if year else "")
    print(f"✅ Добавил в календарь: {title} — каждый год {when}")
    return 0


def _age(summary: str, on: _dt.date) -> str:
    """Extract birth year from a summary and return ' — N лет' if found."""
    import re
    m = re.search(r"\((?:г\.р\.\s*)?(\d{4})\)", summary)
    if not m:
        return ""
    yr = int(m.group(1))
    n = on.year - yr
    if n <= 0:
        return ""
    # Russian plural for "год/года/лет".
    last2, last1 = n % 100, n % 10
    if 11 <= last2 <= 14 or last1 == 0 or last1 >= 5:
        word = "лет"
    elif last1 == 1:
        word = "год"
    else:
        word = "года"
    return f" — {n} {word}"


def _events_on(svc, day: _dt.date):
    lo = _dt.datetime.combine(day, _dt.time.min).isoformat() + "Z"
    hi = _dt.datetime.combine(day + _dt.timedelta(days=1), _dt.time.min).isoformat() + "Z"
    items = svc.events().list(
        calendarId="primary", timeMin=lo, timeMax=hi,
        singleEvents=True, orderBy="startTime", maxResults=50,
    ).execute().get("items", [])
    return [e for e in items if str(e.get("summary", "")).startswith(BDAY_EMOJI)]


def check(args) -> int:
    svc = _svc()
    today = _today()
    todays = _events_on(svc, today)

    upcoming = []
    if args.days and args.days > 0:
        for d in range(1, args.days + 1):
            day = today + _dt.timedelta(days=d)
            for e in _events_on(svc, day):
                upcoming.append((day, e))

    if not todays and not upcoming:
        return 0  # SILENT — nothing today/this window.

    lines = []
    if todays:
        lines.append("🎉 *Сегодня день рождения:*")
        for e in todays:
            s = e.get("summary", "")
            lines.append(f"  • {s}{_age(s, today)}")
        lines.append("")
        lines.append("💡 Не забудь поздравить!")
    if upcoming:
        if todays:
            lines.append("")
        lines.append(f"📅 *Ближайшие ({args.days} дн.):*")
        for day, e in upcoming:
            s = e.get("summary", "")
            lines.append(f"  • {day.strftime('%d.%m')} — {s}{_age(s, day)}")
    print("\n".join(lines))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="CEO birthday manager (add/check).")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--add", action="store_true")
    mode.add_argument("--check", action="store_true")
    ap.add_argument("--name")
    ap.add_argument("--day", type=int)
    ap.add_argument("--month", type=int)
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--kind", choices=["birthday", "wedding"], default="birthday")
    ap.add_argument("--days", type=int, default=0, help="Look-ahead window for --check.")
    args = ap.parse_args()

    if args.add:
        if not (args.name and args.day and args.month):
            ap.error("--add requires --name, --day, --month")
        return add(args)
    return check(args)


if __name__ == "__main__":
    raise SystemExit(main())
