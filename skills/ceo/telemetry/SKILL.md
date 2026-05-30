---
name: telemetry
description: |
  UX telemetry report — counts inbound updates per type (text / command /
  voice / photo / callback) over the last N days. Feeds HERMES_TO_96.md
  Assumption A1 ("inline-меню удобнее свободного текста") with data, not
  intuition.

  Manual triggers: `/telemetry`, `/usage`, "как я пользуюсь ботом",
  "статистика использования", "telemetry report".

  Read-only. No state.db touching. Reads $HERMES_HOME/logs/telemetry/*.jsonl
  (written by gateway/platforms/telemetry.py).
version: 1.0.0
author: alexandr.scerbina
license: MIT
metadata:
  hermes:
    tags: [ceo, observability, telemetry, ux, menu]
    commands: [/telemetry]
    triggers:
      - "/telemetry"
      - "/usage"
      - "как я пользуюсь"
      - "как я пользуюсь ботом"
      - "статистика использования"
      - "статистика бота"
      - "telemetry report"
      - "usage report"
---

# /telemetry — UX usage report

Часть HERMES_TO_96 Этап #2. Тест допущения A1: «иерархическое inline-меню
удобнее свободного текста». Без данных строить inline keyboard — гадание;
со счётчиком за 7 дней решение становится фактом.

## Как работает

- Gateway модуль `gateway/platforms/telemetry.py` пишет каждый incoming
  update в `$HERMES_HOME/logs/telemetry/YYYY-MM-DD.jsonl` (append-only).
- Лог содержит: `kind` (text / command / voice / photo / callback / …),
  `command` (для commands — первый токен), `user_id`, `chat_id`, `text_len`.
- **Не пишется**: тело free-text сообщений (PII boundary), media bytes.
- Этот скилл (`/telemetry`) читает лог и агрегирует.

## Run modes

```bash
# Default — last 7 days
python3 /opt/data/scripts/telemetry_report.py

# Custom window
python3 /opt/data/scripts/telemetry_report.py --days 14

# Per-command breakdown
python3 /opt/data/scripts/telemetry_report.py --breakdown commands
```

## Output (typical)

```
📊 Hermes Usage Telemetry — last 7 days (2026-05-24 → 2026-05-30 UTC)

Total updates: 87

By kind:
  command   : 52  (59.8%)  ██████████████████████████████
  text      : 24  (27.6%)  ██████████████
  callback  :  4  ( 4.6%)  ██
  voice     :  5  ( 5.7%)  ███
  photo     :  2  ( 2.3%)  █

🎯 Decision signal (HERMES_TO_96 A1):
  callback ratio = 4.6%
  → < 30% threshold → НЕ строим inline-меню; user predominantly types
    commands and free text. Invest в semantic triggers instead.

Top 5 commands:
  /brief    : 14
  /coach    :  8
  /cost     :  7
  /evening  :  6
  /whoami   :  4
```

## Decision matrix (HERMES_TO_96 §4 etap #6)

| callback ratio after 7 days | Action |
|---|---|
| ≥ 30% | Build inline-меню — Этап #7. Telemetry continues. |
| 15–30% | Re-run на 14-day window. Если стабильно — build с упрощённой архитектурой. |
| < 15% | Skip inline-меню. Direct → Этап #9 (morning RO digest). |

## Setup

Никакой setup не нужен — gateway автоматически логирует с момента deploy
с telemetry hook'ом. /telemetry просто читает что уже накопилось.

## What this does NOT do

- ❌ Не пишет в state.db (отдельный observability стрим).
- ❌ Не логирует тело free-text сообщений (privacy).
- ❌ Не блокирует bot — telemetry crashes silenced (см. modul'ный design).
