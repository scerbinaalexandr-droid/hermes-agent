---
name: cost
description: |
  Daily Hermes token-spend monitor. Reads $HERMES_HOME/state.db (Hermes' own
  per-session cost tracking), aggregates today + last 7 days, returns a
  Telegram-ready report. Thresholds (HERMES_TO_96.md, Risk #1):
  🟢 <$7/day · 🟡 $7–10/day · 🔴 ≥$10/day.

  Two run modes:
    1. Manual via Telegram — `/cost`, `/spend`, `/tokens`, "сколько потратил",
       "расходы", "spend report".
    2. Daily cron (no_agent, 0 LLM tokens) at 20:55 UTC ≈ 23:55 EEST — end-of-
       day report. Telegram alert auto-arrives at sleep time when spend > $7.

  Read-only. Does NOT auto-pause the bot — alerts only, decision is human.
version: 1.0.0
author: alexandr.scerbina
license: MIT
metadata:
  hermes:
    tags: [ceo, observability, finops, cost, telemetry]
    commands: [/cost]
    triggers:
      - "/cost"
      - "/spend"
      - "/tokens"
      - "сколько потратил"
      - "сколько токенов"
      - "расходы"
      - "расход токенов"
      - "spend report"
      - "token report"
      - "/cost debug"
      - "cost debug"
      - "почему $0"
      - "debug cost"
---

# /cost — Token spend monitor

Часть HERMES_TO_96 (Risk #1 mitigation). Закрывает critical риск «token bleed
>$200/мес → ты заметишь bill → откатишь импульсивно».

## Как работает

- **Manual** — `/cost` возвращает текущий статус (today + 7d trend + per-model).
- **Daily cron** — `no_agent` job 20:55 UTC = 23:55 EEST. Stdout идёт в Telegram
  напрямую (0 LLM-токенов на сам отчёт).

Скрипт `scripts/cost_monitor.py` (stdlib-only) читает Hermes' SQLite-таблицу
`sessions` (поле `estimated_cost_usd`, `actual_cost_usd`, `input_tokens`,
`output_tokens`, …). Никаких внешних API — данные уже есть у Hermes локально.

## Thresholds

| Зона | Today's spend | Действие |
|---|---|---|
| 🟢 Зелёная | < $7.00 | Просто отчёт |
| 🟡 Жёлтая | $7.00 – $9.99 | Отчёт + рекомендация: «осмотри какой скилл съел» |
| 🔴 Красная | ≥ $10.00 | Отчёт + рекомендация: «рассмотри manual /stop до конца дня» |

Hard cap из плана: $200/мес. При тренде >$200/мес — недельный отчёт даёт ранний
индикатор.

## Output format

```
💰 Hermes Spend Report — 2026-05-29

🟢 Today (UTC): $3.24 (47.2K in / 11.8K out / 0.5K cache)
   → 23 sessions, top: /brief ($1.10), /coach ($0.85), /evening ($0.62)

📊 Last 7 days (UTC):
   May 23 → $5.10  ███████
   May 24 → $4.32  ██████
   May 25 → $2.18  ███
   May 26 → $3.50  █████
   May 27 → $6.20  ████████
   May 28 → $4.90  ██████
   May 29 → $3.24  ████  (today, partial)

   7d total: $29.44 · daily avg: $4.21 · trend: stable

📈 Month-to-date (May 2026): $89.30 / cap $200 (44.6%)
```

## Setup (one-time, после первого deploy)

**Важно:** `/cron` — НЕ slash-команда Telegram-бота. Cron создаётся через
natural language (бот вызовет внутренний `cronjob` tool) ИЛИ через CLI на
Railway. `--script` ожидает путь ОТНОСИТЕЛЬНО `~/.hermes/scripts/`, не
абсолютный.

**Вариант A — через бота (рекомендуется):**

Отправить боту обычным текстом:
> Создай cron-задачу daily_cost_report: запускай cost_monitor.py каждый день
> в 20:55 UTC, режим no-agent, доставка в telegram.

Бот распознает намерение → вызовет cronjob tool → вернёт реальный job_id.
**Verify обязательно** (бот в прошлом выдумывал job IDs — incident 2026-05-24):
> покажи список cron-задач

**Вариант B — через CLI (если есть SSH/railway shell):**
```
/opt/hermes/.venv/bin/hermes cron create "55 20 * * *" \
  --script cost_monitor.py --no-agent \
  --name daily_cost_report --deliver telegram
```

## Debug mode

Если отчёт показывает `$0.00` подозрительно — запусти helper с флагом
`--debug` (или скажи в чат «cost debug» / «почему $0»). Покажет последние
10 sessions с полями `cost_status`, `billing_provider`, `pricing_version`,
`actual/estimated`. Помогает найти root cause:

- `cost_status=disabled` → cost tracking off в config
- `billing_provider=NULL` → провайдер не зарегистрирован после смены config
- `actual=NULL & estimated=NULL` для всех → pricing JSON не обновлён под модель
- `pricing_ver=—` → Hermes не знает pricing для текущей модели

Скрипт: `python3 /opt/data/scripts/cost_monitor.py --debug`

## Где живут данные

- Hermes пишет в `$HERMES_HOME/state.db` (`/opt/data/state.db` на проде).
- Таблица `sessions` имеет столбцы: `started_at`, `model`, `input_tokens`,
  `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `reasoning_tokens`,
  `estimated_cost_usd`, `actual_cost_usd`.
- Скрипт фоллбэкает `actual_cost_usd` → `estimated_cost_usd` если actual NULL.

## What this does NOT do

- ❌ НЕ pause bot автоматически (false alarm = no bot во время важной встречи).
- ❌ НЕ дёргает Anthropic Console API (требует Admin key, лишняя зависимость).
- ❌ НЕ хранит свою копию данных — single source of truth = Hermes state.db.
- ❌ НЕ считает cron-jobs с `--no-agent` (там нет LLM, поэтому Hermes их не
  трекает в sessions).
