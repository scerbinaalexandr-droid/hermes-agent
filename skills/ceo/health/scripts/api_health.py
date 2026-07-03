#!/usr/bin/env python3
"""Hermes LLM-provider health monitor — never let the bot die silently again.

Runs as a no_agent cron (0 LLM-agent tokens; just one 1-token probe call).
On a healthy probe it prints NOTHING → the scheduler treats empty stdout as a
silent run (no delivery). On a credit/auth failure it prints ONE clean,
human Telegram alert → delivered to the CEO's phones so he can top up before
(or the moment) the bot goes down.

Deploy (created once; the entrypoint stages this script into $HERMES_HOME/scripts):

    hermes cron create "*/30 * * * *" \
        --script /opt/data/scripts/api_health.py --no-agent \
        --name "API Health Monitor" \
        --deliver telegram:746810595,telegram:385068170

Why failure-based (not balance-prediction): Anthropic exposes no remaining-balance
API for a normal key, so we probe and react. A state file throttles a sustained
outage to one alert per THROTTLE_H hours (no spam); recovery resets it silently.

Env:
    HERMES_HOME            /opt/data on prod (defaults to ~/.hermes locally)
    ANTHROPIC_API_KEY      the bot's key (inherited from the gateway process)
    HERMES_MODEL           probe model (default = dated Sonnet snapshot)

Stdlib only. Always exits 0 — the alert must be delivered as normal content,
not wrapped as a cron error (which would add technical noise).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes"))
STATE_PATH = HERMES_HOME / "cron" / "api_health_state.json"
MODEL = os.environ.get("HERMES_MODEL") or "claude-sonnet-4-5-20250929"
THROTTLE_H = 6  # during a sustained outage, re-alert at most once every 6h

BILLING_URL = "https://console.anthropic.com/settings/billing"


def _probe() -> str:
    """Return one of: ok | credit | auth | no_key. Transient errors → ok
    (we never cry wolf over a rate-limit / network blip)."""
    key = os.environ.get("ANTHROPIC_API_KEY") or ""
    if not key:
        return "no_key"
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(
            {"model": MODEL, "max_tokens": 1,
             "messages": [{"role": "user", "content": "ping"}]}
        ).encode(),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=30)
        return "ok"
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode().lower()
        except Exception:
            body = ""
        if exc.code in (400, 402) and any(
            w in body for w in ("credit", "balance", "insufficient")
        ):
            return "credit"
        if exc.code in (401, 403):
            return "auth"
        return "ok"  # 429/529/5xx — transient, not our alarm
    except Exception:
        return "ok"  # network blip


def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def _save_state(status: str, ts: int) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps({"status": status, "ts": ts}))
    except OSError:
        pass  # best-effort — a monitor must never crash the tick


def _alert(status: str) -> str:
    if status == "credit":
        return (
            "⚠️ Баланс API почти на нуле — бот скоро остановится.\n\n"
            "Пополни, чтобы всё работало без перебоев:\n"
            f"{BILLING_URL}\n\n"
            "И включи там «Auto reload» — тогда это больше не повторится."
        )
    if status == "auth":
        return (
            "⚠️ Бот не может отвечать — проблема с ключом API (авторизация).\n"
            "Нужно проверить ключ в настройках."
        )
    return (
        "⚠️ Бот не может отвечать — не найден ключ API.\n"
        "Нужно проверить настройки."
    )


def main() -> None:
    status = _probe()
    state = _load_state()
    now = int(time.time())

    if status == "ok":
        if state.get("status") != "ok":
            _save_state("ok", now)  # recovered — reset so next outage alerts at once
        return  # healthy → silent

    same = state.get("status") == status
    fresh_enough = (now - int(state.get("ts", 0))) < THROTTLE_H * 3600
    if same and fresh_enough:
        return  # already alerted recently for this outage → stay quiet

    _save_state(status, now)
    print(_alert(status))


if __name__ == "__main__":
    main()
