---
name: remind
description: |
  One-shot reminders через Hermes cron. Используй ВСЕГДА когда user говорит:
  "напомни через 3 часа", "/remind завтра в 10:00 проверить email", "пингани
  меня в 15:00 про встречу", "remind me in 2 hours". Создаёт one-shot cron
  job (Hermes cron) с delivery в Telegram + удалением после первого срабатывания.
version: 0.1.0
author: alexandr.scerbina
license: MIT
metadata:
  hermes:
    tags: [CEO, Reminder, Cron, Time, Telegram]
    commands: [/remind]
    triggers:
      - "/remind"
      - "напомни"
      - "пингани"
      - "напоминалка"
      - "напомнить"
      - "remind me"
---

# Remind — One-Shot Reminder

**Purpose.** Snap-create one-shot напоминание из natural language без
запоминания cron syntax.

**Trigger.** `/remind <когда> <что>`, "напомни через X / завтра в HH:MM /
в N часов".

## Step 1 — Parse time expression (natural language)

Поддерживаемые форматы:

| Пример | Result |
|---|---|
| "через 30 минут" | now + 30 min |
| "через 2 часа" | now + 2h |
| "сегодня в 17:30" | today HH:MM EEST |
| "завтра в 10:00" | tomorrow HH:MM EEST |
| "в пятницу в 14:00" | next Friday 14:00 EEST |
| "через 3 дня" | now + 3d (at current HH:MM) |
| "30m" / "2h" / "3d" — short form | duration syntax (Hermes понимает напрямую) |

Если не распарсил — спроси: «Не понял время. "через N минут", "завтра в HH:MM",
"в пятницу в HH:MM" — что ближе?»

## Step 2 — Extract reminder text

Всё что после time expression и предлогов "что/о/чтобы":
- "напомни через 2 часа проверить почту" → text = "проверить почту"
- "/remind завтра в 10:00 встреча с Живко" → text = "встреча с Живко"

Если text пустой — спроси: «Что именно напомнить?»

## Step 3 — Confirm before creating

```
⏰ Напомнить:
*Когда:* {parsed_time} ({EEST or duration})
*Текст:* {reminder_text}

Сохранить? «✅ да» / «✏️ поправь»
```

## Step 4 — Create cron job (one-shot)

После «да» — call Hermes cron tool create with `--repeat 1`:

```
hermes cron create --name "Reminder: {first 20 chars of text}" \
  --repeat 1 \
  --deliver telegram:746810595 \
  "{schedule expression — duration or cron}" \
  "Напомни: {reminder_text}"
```

Для duration ("через 2 часа") → schedule = `2h` (Hermes понимает).
Для cron (today 17:30 EEST = 14:30 UTC сегодня) → calculate exact cron expression.

## Step 5 — Acknowledge

```
✅ Сохранено напоминание на {when}: «{text}»
Job ID: {cron_id}

Отменить — `/remind list` → cancel <id>
```

## Subcommands

- `/remind list` — показать все active one-shot reminders (filter by `--repeat 1` + `--name "Reminder:"`)
- `/remind cancel <id>` — удалить cron job

## Edge cases

| Случай | Поведение |
|---|---|
| Время в прошлом ("вчера в 10:00") | Reject: «Это уже прошло. Хочешь установить на завтра?» |
| Слишком далёкое будущее (>30 days) | Спроси confirmation: «Это через {N} дней — точно? Может проще в календаре?» |
| Слишком частое (>10 reminders / day) | Подскажи: «Это много — может стоит /capture task вместо?» |
| Duplicate reminder (тот же text + время) | Спроси: «Похоже уже есть. Создать вторую или отменить?» |

## What NOT to do

- ❌ Не создавай **recurring** reminders через `/remind` (это для `/cron` или daily/weekly skills)
- ❌ Не предлагай рекуррентные авто-напоминания — это namespace других skills
- ❌ Не сохраняй reminder text с sensitive data (passwords, banking) raw — спроси переформулировать
