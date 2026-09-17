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


_MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
               "августа", "сентября", "октября", "ноября", "декабря"]
_MONTHS_NOM = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
               "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]


def trend_note(seven_days: list[tuple[str, float]]) -> str:
    """First 3 days vs last 3 full days (today is partial and excluded)."""
    if len(seven_days) < 6:
        return ""
    first = sum(c for _, c in seven_days[:3]) / 3
    last = sum(c for _, c in seven_days[3:6]) / 3
    if last > first * 1.3 and last > 0.5:
        return "Расход растёт по сравнению с началом недели."
    if last < first * 0.7 and first > 0.5:
        return "Расход снижается по сравнению с началом недели."
    return ""


def status(today: float) -> tuple[str, str]:
    """(emoji for the today line, warning line or empty)."""
    if today >= CRIT:
        return "🔴", "Расход за сегодня критический — лучше остановить бота до конца дня."
    if today >= WARN:
        return "🟡", "Расход за сегодня выше обычного — стоит взглянуть, что так много работало."
    return "🟢", ""


def days_in_current_month() -> int:
    now = datetime.now(timezone.utc)
    return calendar.monthrange(now.year, now.month)[1]


def render(conn: sqlite3.Connection) -> str:
    """Owner-facing summary: money only, in Russian, no tokens/sessions/bars."""
    today, _details = today_cost(conn)
    week = daily_totals(conn, 7)
    mtd = mtd_total(conn)
    dim = days_in_current_month()
    pct = (mtd / BUDGET * 100) if BUDGET else 0.0
    now_utc = datetime.now(timezone.utc)
    proj_eom = (mtd / max(now_utc.day, 1)) * dim

    local = (now_utc + _DISPLAY_TZ_OFFSET).date()
    total_7 = sum(c for _, c in week)

    emoji, warning = status(today)
    lines = [
        f"💰 *Расходы на ассистента — {local.day} {_MONTHS_GEN[local.month - 1]}*",
        "",
        f"Сегодня: ${today:.2f} {emoji}",
        f"За 7 дней: ${total_7:.2f} (в среднем ${total_7 / 7:.2f} в день)",
        f"{_MONTHS_NOM[now_utc.month - 1]}: ${mtd:.2f} из ${BUDGET:.0f} ({pct:.0f}%)",
    ]
    if mtd > 0:
        lines.append(f"При таком темпе к концу месяца: около ${proj_eom:.2f}")
        if proj_eom > BUDGET:
            lines.append(f"⚠️ Это больше лимита на ${proj_eom - BUDGET:.2f}.")
    trend = trend_note(week)
    if warning or trend:
        lines.append("")
        lines += [ln for ln in (warning, trend) if ln]
    return "\n".join(lines)


def render_debug(conn: sqlite3.Connection) -> str:
    """Diagnostic dump — last 10 sessions with cost-tracking metadata."""
    cur = conn.execute(
        """
        SELECT datetime(started_at, 'unixepoch') AS started,
               model,
               COALESCE(billing_provider, '—') AS provider,
               COALESCE(billing_mode, '—') AS mode,
               COALESCE(cost_status, '—') AS status,
               COALESCE(cost_source, '—') AS source,
               COALESCE(pricing_version, '—') AS pv,
               actual_cost_usd, estimated_cost_usd,
               input_tokens, output_tokens, cache_read_tokens
        FROM sessions
        ORDER BY started_at DESC
        LIMIT 10
        """
    )
    rows = list(cur)
    if not rows:
        return "🔍 *Debug:* state.db пуст — sessions не создавались."

    lines = ["🔍 *Cost tracking debug — last 10 sessions:*", ""]
    for r in rows:
        (started, model, provider, mode, status, source, pv,
         actual, estim, i_t, o_t, c_r) = r
        cost_str = f"a=${actual}" if actual is not None else "a=NULL"
        cost_str += f" e=${estim}" if estim is not None else " e=NULL"
        lines.append(
            f"• {started} UTC — model=`{model or 'NULL'}` "
            f"provider=`{provider}` mode=`{mode}`"
        )
        lines.append(
            f"   status=`{status}` source=`{source}` pricing_ver=`{pv}` "
            f"tokens=(i={i_t} o={o_t} c_r={c_r}) cost=({cost_str})"
        )

    # Diagnostic interpretation
    lines.append("")
    lines.append("📋 *Что искать:*")
    lines.append(
        "• `cost_status=disabled` или `no_pricing` → cost tracking off / "
        "модель не в pricing table"
    )
    lines.append(
        "• `billing_provider=NULL` → провайдер не зарегистрирован в session "
        "(чаще всего после смены provider в config)"
    )
    lines.append(
        "• `actual=NULL e=NULL` для всех → нужен update pricing JSON или "
        "включить `cost_tracking: true` в config.yaml"
    )
    lines.append(
        "• `pricing_ver=—` → Hermes не знает pricing для текущей модели"
    )
    return "\n".join(lines)


def main() -> int:
    debug = "--debug" in sys.argv[1:] or "debug" in sys.argv[1:]
    try:
        conn = _connect()
    except sqlite3.OperationalError as e:
        sys.stderr.write(f"[cost] cannot open state.db: {e}\n")
        print("⚠️ Отчёт по расходам сейчас недоступен.")
        return 0
    try:
        out = render_debug(conn) if debug else render(conn)
    except Exception as e:
        # A schema mismatch (e.g. missing cost column after a rollback) must not
        # abort the no_agent delivery with a raw traceback — degrade cleanly.
        sys.stderr.write(f"[cost] render failed: {e}\n")
        print("⚠️ Отчёт по расходам сегодня недоступен.")
        return 0
    finally:
        conn.close()
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
