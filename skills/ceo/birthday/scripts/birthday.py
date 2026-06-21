#!/usr/bin/env python3
"""Birthday manager for the CEO calendar (connected Google Workspace OAuth).

Writes to a DEDICATED, Hermes-owned calendar "🎂 Дни рождения" (created once on
first use) — Google's native "Дни рождения" calendar is a read-only virtual
calendar built from Contacts and cannot be written via the API. Keeping a
separate calendar lets the CEO toggle birthdays on/off and gives Hermes full
read/write control.

Modes (all on the dedicated birthday calendar):
  --add      Create a recurring (yearly) all-day birthday event.
  --check    List birthdays today (or within --days) → Telegram digest. SILENT
             (no output) when none, so the daily cron never spams.
  --migrate  One-time: move 🎂/💍 events already sitting in the PRIMARY calendar
             (e.g. from an .ics import) into the dedicated birthday calendar.

Uses the google-workspace credentials (no re-auth). All-day + RRULE:FREQ=YEARLY
via the raw Calendar API.

Usage:
  python3 birthday.py --add --name "Маша Иванова" --day 15 --month 3 --year 1990
  python3 birthday.py --add --name "Годовщина свадьбы" --day 5 --month 6 --kind wedding
  python3 birthday.py --check --days 7
  python3 birthday.py --migrate
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

BDAY_EMOJI = ("🎂", "💍")
BDAY_CAL_NAME = "🎂 Дни рождения"
BDAY_CAL_COLOR = "10"  # Google calendar colorId 10 = green (Basil)


def _svc():
    return gws.build_service("calendar", "v3")


def _today() -> _dt.date:
    # Chisinau (EEST, UTC+3) — the CEO's timezone for "today".
    return (_dt.datetime.utcnow() + _dt.timedelta(hours=3)).date()


def _bday_cal_id(svc) -> str:
    """Find (or create once) the dedicated Hermes-owned birthday calendar."""
    for c in svc.calendarList().list(showHidden=True).execute().get("items", []):
        if c.get("summary") == BDAY_CAL_NAME:
            return c["id"]
    created = svc.calendars().insert(
        body={"summary": BDAY_CAL_NAME, "timeZone": "Europe/Chisinau"}
    ).execute()
    cid = created["id"]
    try:  # colour it green in the sidebar; non-fatal if it fails
        svc.calendarList().patch(calendarId=cid, body={"colorId": BDAY_CAL_COLOR}).execute()
    except Exception:
        pass
    return cid


def add(args) -> int:
    svc = _svc()
    cal = _bday_cal_id(svc)
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
    svc.events().insert(calendarId=cal, body=body).execute()
    when = f"{args.day:02d}.{args.month:02d}" + (f".{year}" if year else "")
    print(f"✅ Добавил в «{BDAY_CAL_NAME}»: {title} — каждый год {when}")
    return 0


def _age(summary: str, on: _dt.date) -> str:
    import re
    m = re.search(r"\((?:г\.р\.\s*)?(\d{4})\)", summary)
    if not m:
        return ""
    n = on.year - int(m.group(1))
    if n <= 0:
        return ""
    last2, last1 = n % 100, n % 10
    if 11 <= last2 <= 14 or last1 == 0 or last1 >= 5:
        word = "лет"
    elif last1 == 1:
        word = "год"
    else:
        word = "года"
    return f" — {n} {word}"


def _events_on(svc, cal, day: _dt.date):
    lo = _dt.datetime.combine(day, _dt.time.min).isoformat() + "Z"
    hi = _dt.datetime.combine(day + _dt.timedelta(days=1), _dt.time.min).isoformat() + "Z"
    items = svc.events().list(
        calendarId=cal, timeMin=lo, timeMax=hi,
        singleEvents=True, orderBy="startTime", maxResults=50,
    ).execute().get("items", [])
    return [e for e in items if str(e.get("summary", "")).startswith(BDAY_EMOJI)]


def check(args) -> int:
    svc = _svc()
    cal = _bday_cal_id(svc)
    today = _today()
    todays = _events_on(svc, cal, today)

    upcoming = []
    if args.days and args.days > 0:
        for d in range(1, args.days + 1):
            day = today + _dt.timedelta(days=d)
            for e in _events_on(svc, cal, day):
                upcoming.append((day, e))

    if not todays and not upcoming:
        return 0  # SILENT

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


def migrate(args) -> int:
    """Move 🎂/💍 recurring events from PRIMARY into the dedicated calendar."""
    svc = _svc()
    cal = _bday_cal_id(svc)
    moved = 0
    page = None
    while True:
        resp = svc.events().list(
            calendarId="primary", singleEvents=False, maxResults=2500, pageToken=page,
        ).execute()
        for e in resp.get("items", []):
            if str(e.get("summary", "")).startswith(BDAY_EMOJI):
                try:
                    svc.events().move(
                        calendarId="primary", eventId=e["id"], destination=cal
                    ).execute()
                    moved += 1
                except Exception as exc:
                    sys.stderr.write(f"[birthday] move failed for {e.get('id')}: {exc}\n")
        page = resp.get("nextPageToken")
        if not page:
            break
    print(f"✅ Перенесено в «{BDAY_CAL_NAME}»: {moved} событий (из основного календаря).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="CEO birthday manager.")
    # No mode flag → --check (today). Lets the no_agent cron run the bare script.
    mode = ap.add_mutually_exclusive_group(required=False)
    mode.add_argument("--add", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--migrate", action="store_true")
    ap.add_argument("--name")
    ap.add_argument("--day", type=int)
    ap.add_argument("--month", type=int)
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--kind", choices=["birthday", "wedding"], default="birthday")
    ap.add_argument("--days", type=int, default=0)
    args = ap.parse_args()

    if args.add:
        if not (args.name and args.day and args.month):
            ap.error("--add requires --name, --day, --month")
        return add(args)
    if args.migrate:
        return migrate(args)
    return check(args)


if __name__ == "__main__":
    raise SystemExit(main())
