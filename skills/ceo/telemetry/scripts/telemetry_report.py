#!/usr/bin/env python3
"""Aggregate UX telemetry from $HERMES_HOME/logs/telemetry/*.jsonl.

Feeds HERMES_TO_96.md Assumption A1: callback (button click) ratio vs
text/command (free text) over last N days. Decision threshold = 30%.

Usage:
    python3 /opt/data/scripts/telemetry_report.py [--days 7]
                                                  [--breakdown commands|users|kinds]

Stdlib only. No state.db, no LLM, safe for no_agent cron.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

TELEMETRY_DIR = (
    pathlib.Path(os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes"))
    / "logs"
    / "telemetry"
)


def _date_range(days: int) -> list[str]:
    today = datetime.now(timezone.utc).date()
    return [
        (today - timedelta(days=i)).isoformat()
        for i in range(days - 1, -1, -1)
    ]


def _load_events(days: int) -> list[dict]:
    out: list[dict] = []
    for d in _date_range(days):
        path = TELEMETRY_DIR / f"{d}.jsonl"
        if not path.exists():
            continue
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue
    return out


def _bar(value: int, total: int, width: int = 30) -> str:
    if total <= 0:
        return ""
    ratio = value / total
    return "█" * int(ratio * width + 0.5)


def _decision_signal(callback_ratio: float, total: int) -> str:
    """HERMES_TO_96 §4 etap #6 matrix."""
    if total < 20:
        return (
            f"⚠ Sample size too small ({total} updates). Подожди ещё дней "
            f"до решения по inline-меню."
        )
    if callback_ratio >= 0.30:
        return (
            f"✅ callback ratio = {callback_ratio*100:.1f}% ≥ 30%\n"
            f"   → BUILD inline-меню (Этап #7). Пользователь активно жмёт кнопки."
        )
    if callback_ratio >= 0.15:
        return (
            f"🟡 callback ratio = {callback_ratio*100:.1f}% — пограничная зона\n"
            f"   → Прогон 14-day window. Если стабильно — build с упрощённой "
            f"архитектурой."
        )
    return (
        f"❌ callback ratio = {callback_ratio*100:.1f}% < 30%\n"
        f"   → SKIP inline-меню. Пользователь предпочитает текст/команды. "
        f"Инвестируй в semantic triggers (расширение фраз) вместо UI."
    )


def render(events: list[dict], days: int, breakdown: str | None) -> str:
    if not events:
        return (
            f"📊 Hermes Usage Telemetry — last {days} days\n\n"
            f"Нет данных. Возможные причины:\n"
            f"  • Telemetry hook ещё не задеплоен (gateway/platforms/telemetry.py).\n"
            f"  • Прошло меньше времени с deploy.\n"
            f"  • Логи в другом HERMES_HOME (текущий: {TELEMETRY_DIR})."
        )

    start = _date_range(days)[0]
    end = _date_range(days)[-1]
    total = len(events)
    by_kind = Counter(e.get("kind", "unknown") for e in events)
    callback_n = by_kind.get("callback", 0)
    callback_ratio = callback_n / total if total else 0

    lines = []
    lines.append(
        f"📊 *Hermes Usage Telemetry* — last {days} days ({start} → {end} UTC)"
    )
    lines.append("")
    lines.append(f"Total updates: *{total}*")
    lines.append("")
    lines.append("*By kind:*")
    for kind, count in sorted(by_kind.items(), key=lambda kv: -kv[1]):
        pct = count / total * 100
        lines.append(f"  {kind:10s}: {count:4d}  ({pct:5.1f}%)  {_bar(count, total)}")
    lines.append("")
    lines.append("🎯 *Decision signal (HERMES_TO_96 A1):*")
    lines.append(_decision_signal(callback_ratio, total))

    if breakdown == "commands":
        cmds = Counter(
            e.get("command") for e in events
            if e.get("kind") == "command" and e.get("command")
        )
        if cmds:
            lines.append("")
            lines.append("*Top commands:*")
            for cmd, count in cmds.most_common(10):
                lines.append(f"  {cmd:15s}: {count}")
    elif breakdown == "users":
        users = Counter(
            e.get("user_id") for e in events if e.get("user_id") is not None
        )
        if users:
            lines.append("")
            lines.append("*By user:*")
            for uid, count in users.most_common(5):
                lines.append(f"  user {uid}: {count}")
    elif breakdown == "kinds":
        # Already shown above; keep flag for symmetry.
        pass

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument(
        "--breakdown",
        choices=["commands", "users", "kinds"],
        default="commands",
        help="What extra slice to show (default: commands)",
    )
    args = ap.parse_args()
    events = _load_events(args.days)
    print(render(events, args.days, args.breakdown))
    return 0


if __name__ == "__main__":
    sys.exit(main())
