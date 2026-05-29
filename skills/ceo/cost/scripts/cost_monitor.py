#!/usr/bin/env python3
"""Hermes token-spend monitor — reads state.db, returns Telegram report.

Designed for two modes (HERMES_TO_96.md, Risk #1):

  1. Daily no_agent cron — 0 LLM tokens, stdout → Telegram:
       hermes cron create "55 20 * * *" \
           --script /opt/data/scripts/cost_monitor.py --no-agent \
           --name daily_cost_report --deliver telegram

  2. Manual via /cost — same script, same output (skill calls it).

Thresholds: 🟢 <$7/day · 🟡 $7-10/day · 🔴 ≥$10/day. Read-only — no pause.

Env:
    HERMES_HOME            /opt/data on prod (defaults to ~/.hermes locally)
    HERMES_COST_BUDGET     monthly cap in USD (default 200.0)
    HERMES_COST_WARN       daily warn threshold (default 7.0)
    HERMES_COST_CRIT       daily critical threshold (default 10.0)

Stdlib only.
"""
from __future__ import annotations

import calendar
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes"))
STATE_DB = HERMES_HOME / "state.db"

BUDGET = float(os.environ.get("HERMES_COST_BUDGET", "200.0"))
WARN = float(os.environ.get("HERMES_COST_WARN", "7.0"))
CRIT = float(os.environ.get("HERMES_COST_CRIT", "10.0"))

# Display tz: EEST (UTC+3). Aggregation is done in UTC for stability;
# only the header date label is shown in EEST.
_DISPLAY_TZ_OFFSET = timedelta(hours=3)

BAR_CHARS = "▁▂▃▄▅▆▇█"


def _today_utc_start() -> float:
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    return start.timestamp()


def _days_ago_start(days: int) -> float:
    return _today_utc_start() - days * 86400


def _month_start_utc() -> float:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc).timestamp()


def _coalesce_cost(row: tuple) -> float:
    """sessions table stores cost twice; prefer actual, fallback estimated."""
    actual, estimated = row
    if actual is not None and actual >= 0:
        return float(actual)
    if estimated is not None and estimated >= 0:
        return float(estimated)
    return 0.0


def _connect() -> sqlite3.Connection:
    if not STATE_DB.exists():
        print(f"ℹ Hermes state.db не найден: {STATE_DB}")
        print("Это нормально для свежего deploy без активности. После первой")
        print("сессии Hermes создаст БД и /cost начнёт работать.")
        sys.exit(0)
    return sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)


def _bar(value: float, max_value: float, width: int = 10) -> str:
    if max_value <= 0:
        return "▁" * width
    ratio = max(0.0, min(1.0, value / max_value))
    filled = int(ratio * width + 0.5)
    return "█" * filled + "▁" * (width - filled)


def today_cost(conn: sqlite3.Connection) -> tuple[float, dict]:
    """Return (total_cost, details dict)."""
    start = _today_utc_start()
    cur = conn.execute(
        """
        SELECT actual_cost_usd, estimated_cost_usd,
               COALESCE(input_tokens, 0), COALESCE(output_tokens, 0),
               COALESCE(cache_read_tokens, 0), COALESCE(cache_write_tokens, 0),
               COALESCE(reasoning_tokens, 0),
               title, model
        FROM sessions
        WHERE started_at >= ?
        """,
        (start,),
    )
    total = 0.0
    sessions = 0
    in_tok = out_tok = cache_r = cache_w = reason_tok = 0
    per_title: dict[str, float] = {}
    for actual, estim, i_t, o_t, c_r, c_w, r_t, title, _model in cur:
        cost = _coalesce_cost((actual, estim))
        total += cost
        sessions += 1
        in_tok += i_t
        out_tok += o_t
        cache_r += c_r
        cache_w += c_w
        reason_tok += r_t
        if title:
            per_title[title] = per_title.get(title, 0.0) + cost
    top = sorted(per_title.items(), key=lambda kv: -kv[1])[:3]
    return total, {
        "sessions": sessions,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cache_read": cache_r,
        "cache_write": cache_w,
        "reasoning": reason_tok,
        "top_titles": top,
    }


def daily_totals(conn: sqlite3.Connection, days: int = 7) -> list[tuple[str, float]]:
    """Last N days (UTC), oldest first. (date_label, cost)."""
    out = []
    for i in range(days - 1, -1, -1):
        start = _days_ago_start(i)
        end = start + 86400
        cur = conn.execute(
            """
            SELECT actual_cost_usd, estimated_cost_usd
            FROM sessions
            WHERE started_at >= ? AND started_at < ?
            """,
            (start, end),
        )
        cost = sum(_coalesce_cost(row) for row in cur)
        label = datetime.fromtimestamp(start, tz=timezone.utc).strftime("%b %d")
        out.append((label, cost))
    return out


def mtd_total(conn: sqlite3.Connection) -> float:
    cur = conn.execute(
        """
        SELECT actual_cost_usd, estimated_cost_usd
        FROM sessions
        WHERE started_at >= ?
        """,
        (_month_start_utc(),),
    )
    return sum(_coalesce_cost(row) for row in cur)


def trend_label(seven_days: list[tuple[str, float]]) -> str:
    """First 3 days vs last 3 days."""
    if len(seven_days) < 6:
        return "—"
    first = sum(c for _, c in seven_days[:3]) / 3
    last = sum(c for _, c in seven_days[3:6]) / 3  # exclude today (partial)
    if first == 0 and last == 0:
        return "no spend"
    if last > first * 1.3:
        return f"⬆ rising ({first:.2f} → {last:.2f})"
    if last < first * 0.7:
        return f"⬇ falling ({first:.2f} → {last:.2f})"
    return "stable"


def status_emoji(today: float) -> tuple[str, str]:
    if today >= CRIT:
        return "🔴", f"Critical (≥${CRIT:.0f}). Рассмотри manual `/stop` до конца дня."
    if today >= WARN:
        return "🟡", f"Warning (≥${WARN:.0f}). Осмотри какой скилл съел — `/cost` детально."
    return "🟢", "OK"


def days_in_current_month() -> int:
    now = datetime.now(timezone.utc)
    return calendar.monthrange(now.year, now.month)[1]


def render(conn: sqlite3.Connection) -> str:
    today, details = today_cost(conn)
    week = daily_totals(conn, 7)
    mtd = mtd_total(conn)
    status, note = status_emoji(today)
    trend = trend_label(week)
    dim = days_in_current_month()
    pct = (mtd / BUDGET * 100) if BUDGET else 0.0
    proj_eom = (mtd / max(datetime.now(timezone.utc).day, 1)) * dim

    # Header date in EEST
    today_eest = (datetime.now(timezone.utc) + _DISPLAY_TZ_OFFSET).date().isoformat()
    month_label = datetime.now(timezone.utc).strftime("%B %Y")

    lines = []
    lines.append(f"💰 *Hermes Spend Report — {today_eest}*")
    lines.append("")
    lines.append(
        f"{status} *Today (UTC):* ${today:.2f} "
        f"({details['input_tokens']/1000:.1f}K in / "
        f"{details['output_tokens']/1000:.1f}K out / "
        f"{details['cache_read']/1000:.1f}K cache_r)"
    )
    lines.append(f"   → {details['sessions']} sessions")
    if details["top_titles"]:
        top_str = ", ".join(f"{t} (${c:.2f})" for t, c in details["top_titles"])
        lines.append(f"   → top: {top_str}")
    lines.append(f"   → {note}")
    lines.append("")

    max_day = max(c for _, c in week) if week else 0.0
    lines.append("📊 *Last 7 days (UTC):*")
    for i, (label, cost) in enumerate(week):
        suffix = "  ← today (partial)" if i == len(week) - 1 else ""
        lines.append(f"   {label} → ${cost:5.2f}  {_bar(cost, max_day)}{suffix}")
    total_7 = sum(c for _, c in week)
    avg_7 = total_7 / 7
    lines.append("")
    lines.append(f"   7d total: ${total_7:.2f} · daily avg: ${avg_7:.2f} · trend: {trend}")
    lines.append("")

    lines.append(
        f"📈 *Month-to-date ({month_label}):* ${mtd:.2f} / "
        f"cap ${BUDGET:.0f} ({pct:.1f}%)"
    )
    if mtd > 0:
        lines.append(f"   Projection EOM at current pace: ${proj_eom:.2f}")
        if proj_eom > BUDGET:
            lines.append(f"   ⚠ Projection exceeds cap by ${proj_eom - BUDGET:.2f}")

    return "\n".join(lines)


def main() -> int:
    try:
        conn = _connect()
    except sqlite3.OperationalError as e:
        print(f"❌ Не могу открыть state.db: {e}")
        return 1
    try:
        out = render(conn)
    finally:
        conn.close()
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
