"""Morning ritual helper (personal) — meditation cue + the CEO's focus to affirm.

Личное «Утро»: пауза-медитация, напоминание на чём фокусироваться, проговорить вслух.

  --gather : JSON {meditation, focus[], count} — a rotating meditation cue + the
             CEO's saved focus items (from the Фокус tab) for him to affirm.
  --save   : JSON {"text": "..."} → append a focus item to the Фокус tab.

Best-effort: never raises hard.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))
if pathlib.Path("/opt/hermes/skills/ceo/_lib/memory.py").exists() and "/opt/hermes" not in sys.path:
    sys.path.insert(0, "/opt/hermes")

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Europe/Chisinau")
except Exception:  # pragma: no cover
    _TZ = _dt.timezone(_dt.timedelta(hours=3))

# Short, universal meditation/presence cues. Rotated by day (deterministic — no
# randomness so it's testable and reproducible). The CEO's FOCUS items are his own.
_MEDITATIONS = [
    "Сделай 5 медленных вдохов. Только дыхание — больше ничего.",
    "Минута тишины. Отпусти вчера. Ты здесь, сейчас.",
    "Закрой глаза. Три вдоха. На выдохе отпускай напряжение.",
    "Почувствуй опору — стопы, дыхание. Спокойствие приходит само.",
    "Один глубокий вдох. Спроси себя: каким я хочу быть сегодня?",
    "Тишина 60 секунд. Ничего не решай — просто будь.",
    "Вдох на 4 счёта, выдох на 6. Повтори трижды. Ум проясняется.",
]


def _today() -> _dt.date:
    return _dt.datetime.now(_TZ).date()


def _meditation_for(day: _dt.date) -> str:
    return _MEDITATIONS[day.toordinal() % len(_MEDITATIONS)]


def _google_api() -> str:
    p = os.environ.get("HERMES_GOOGLE_API",
                       "/opt/hermes/skills/productivity/google-workspace/scripts/google_api.py")
    if not os.path.exists(p):
        p = str(_REPO / "skills" / "productivity" / "google-workspace" / "scripts" / "google_api.py")
    return p


def cmd_gather() -> dict:
    day = _today()
    out: dict = {"meditation": _meditation_for(day), "focus": [], "count": 0}
    sheet_id = os.environ.get("HERMES_MEETING_SHEET_ID")
    if not sheet_id:
        out["reason"] = "no-sheet-configured"
        return out
    try:
        from skills.ceo._lib.sheets_meeting_sync import GoogleApiGW, FOCUS_TAB
        gw = GoogleApiGW(_google_api())
        # First-ever run: the Фокус tab won't exist yet, and reading a missing
        # tab makes Sheets return HTTP 400 ("Unable to parse range") — which
        # surfaced as a scary "google_api failed" instead of a clean "no focus
        # set yet". Self-create the tab (parity with sync_focus on the save side).
        gw.ensure_tab(sheet_id, FOCUS_TAB)
        rows = gw.get(sheet_id, f"{FOCUS_TAB}!A:D")
        focus = [r[2].strip() for r in rows[1:] if len(r) > 2 and r[2].strip()]
        out["focus"] = focus
        out["count"] = len(focus)
    except Exception as exc:
        out["reason"] = f"read:{str(exc)[:200]}"
    return out


def cmd_save(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {"saved": False, "reason": "payload-not-dict"}
    text = str(payload.get("text", "")).strip()
    if not text:
        return {"saved": False, "reason": "empty"}
    sheet_id = os.environ.get("HERMES_MEETING_SHEET_ID")
    if not sheet_id:
        return {"saved": False, "reason": "no-sheet-configured"}
    try:
        from skills.ceo._lib.sheets_meeting_sync import sync_focus, GoogleApiGW, _now_iso
    except Exception as exc:
        return {"saved": False, "reason": f"import:{exc}"}
    now = _now_iso()
    fid = f"focus/{now[:10]}/{now[11:19].replace(':', '')}"
    try:
        res = sync_focus({"text": text}, sheet_id, GoogleApiGW(_google_api()), now, focus_id=fid)
        return {"saved": bool(res.get("focus_written")), "focus_id": fid, **res}
    except Exception as exc:
        return {"saved": False, "reason": str(exc)[:200]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--gather", action="store_true")
    g.add_argument("--save", metavar="JSON", help='JSON {"text": "focus item"}')
    args = ap.parse_args()

    if args.gather:
        result = cmd_gather()
    else:
        try:
            payload = json.loads(args.save)
        except json.JSONDecodeError as exc:
            print(f"ERROR: --save expects JSON ({exc})", file=sys.stderr)
            return 2
        result = cmd_save(payload)

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
