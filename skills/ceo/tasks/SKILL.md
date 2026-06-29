---
name: tasks
description: |
  Open-tasks overview. Reads the Задачи tab (tasks from /capture + meeting action
  items via /notes) and surfaces what's still open, bucketed by deadline so nothing
  slips: overdue first, then due this week, then no-deadline. Auto-runs every morning
  (07:15 EEST cron) and on demand. Auto-invoked when the user types /tasks or says
  "задачи", "что висит", "открытые задачи", "мои задачи", "что у меня по задачам",
  "какие задачи". This is the CONTROL end of the loop (meeting → protocol → tasks →
  follow-up); recording tasks is /capture and /notes.
version: 0.1.0
author: alexandr.scerbina
license: MIT
prerequisites:
  files:
    - memory/soul.md
metadata:
  hermes:
    tags: [CEO, Tasks, Followup, Sheets, Telegram]
    commands: [/tasks]
    triggers:
      - "/tasks"
      - "задачи"
      - "что висит"
      - "открытые задачи"
      - "мои задачи"
      - "какие задачи"
---

# Tasks — open-task follow-up

**Purpose.** CEO видит, что висит, и ничего не теряет: задачи из `/capture` и
action items из `/notes` копятся во вкладке «Задачи» — этот скилл показывает
открытые по срокам. Утром в 07:15 (cron, между /prep и /brief) и по запросу.

**Trigger.** `/tasks`, фразы выше, ИЛИ cron 07:15 EEST. Это КОНТРОЛЬ задач (что
открыто) — НЕ создание (то `/capture` и `/notes`).

## Step 1 — Read (deterministic)

```bash
python skills/ceo/tasks/scripts/tasks_list.py --list
```

Возвращает `{ok, today, total_open, overdue[], soon[], later[]}`. Каждая задача:
`{task, area, owner, due, source, overdue_days?}`. Источник — вкладка «Задачи»
(открытые = статус не done/closed/выполнено).

- `ok:false, reason:no-sheet-configured` → «Таблица задач не настроена.»
- `total_open == 0` → «✅ Открытых задач нет — чисто.»

## Step 2 — Format briefing (по срокам)

```
📋 *Открытые задачи — {total_open}*

🔴 *Просрочено:*
• {task} — {owner} · срок {due} (просрочено {overdue_days}д) {area}
…

🟡 *На этой неделе:*
• {task} — {owner} · {due} {area}
…

⚪ *Без срока:*
• {task} — {owner} {area}
…
```

- Пропускай пустые блоки (нет просроченных → не печатай «🔴»).
- `owner` пустой → не показывай «— ». Кратко, читабельно за рулём.
- Если задач много (>15) — покажи 🔴 все + 🟡 все + ⚪ первые 5 и «… ещё N».
- Это бриф, НЕ черновик — без `[[draft_actions]]`.

## Edge cases

| Случай | Поведение |
|---|---|
| Срок свободным текстом («до пятницы») | не парсится как дата → в «⚪ Без срока», показать текст `due` |
| Нет открытых | «✅ Открытых задач нет» |
| Sheet недоступен | «Не смог прочитать задачи, повтори позже» |

## What NOT to do

- ❌ Не создавай и не меняй задачи здесь — только показ. Отметить выполненной —
  пока вручную во вкладке «Задачи» (статус → done).
- ❌ Не путай с `/capture` (создать) и `/notes` (протокол встречи).
- ❌ Не выдумывай задачи вне вкладки «Задачи».
