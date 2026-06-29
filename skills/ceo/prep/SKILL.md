---
name: prep
description: |
  Morning meeting-prep. For every meeting in the CEO's calendar today, build a
  focused checklist of questions to discuss (so he walks in concentrated on what
  matters), store it in the Встречи tab, and send a briefing organized by time
  block. Auto-runs at 07:00 EEST (cron) and on demand. Auto-invoked when the user
  types /prep or says "повестка", "вопросы на встречи", "подготовь встречи",
  "что у меня сегодня по встречам", "подготовь вопросы на встречу", "agenda".
  After the meeting the CEO dictates results → use /notes for the protocol.
version: 0.1.0
author: alexandr.scerbina
license: MIT
prerequisites:
  files:
    - memory/soul.md
    - memory/projects.md
    - memory/risks.md
metadata:
  hermes:
    tags: [CEO, Meetings, Agenda, Prep, Calendar, Telegram]
    commands: [/prep]
    triggers:
      - "/prep"
      - "повестка"
      - "вопросы на встречи"
      - "подготовь встречи"
      - "что у меня сегодня по встречам"
      - "agenda"
---

# Meeting Prep — agenda / questions per meeting

**Purpose.** CEO заходит на каждую встречу с готовым списком обязательных вопросов —
чтобы концентрироваться на важном, ничего не забыть. Утром в 07:00 (cron) — повестки
на ВСЕ встречи дня по блокам; в течение дня — по запросу `/prep`.

**Trigger.** `/prep`, фразы выше, ИЛИ cron 07:00 EEST. Это ПОДГОТОВКА к встрече
(вопросы ДО). Итоги ПОСЛЕ встречи (протокол/решения/задачи) — это `/notes`.

## Step 1 — Gather (deterministic)

```bash
python skills/ceo/prep/scripts/meeting_prep.py --gather
```

Возвращает `{today, tz, events:[{id,summary,start,end,location,description}], projects,
active_priorities, risks}`. `events` — встречи из Google Calendar на сегодня (EEST).

- Если `events` пуст → ответь «📅 На сегодня встреч в календаре нет. Добавить? Скажи
  что и когда.» и НЕ вызывай save.
- Если `events.error` → скажи кратко, что календарь недоступен, предложи повторить.

## Step 2 — Generate agenda per meeting (LLM)

Для КАЖДОЙ встречи составь **3–7 конкретных вопросов**, на которых важно
сфокусироваться. Источники контекста (из gather): название и участники встречи,
`projects` (статус/риски проекта по теме), `active_priorities`, `risks`. Если встреча
связана с проектом/направлением — вопросы должны двигать его (решения, блокеры, цифры,
следующий шаг, сроки). Не вода — каждый вопрос про результат.

**Privacy guard (soul.md):** семейные имена → «Супруга/Мама/Папа», точные суммы →
диапазоны, без банк/паролей/медданных.

`meeting_id` = поле `id` события из gather (стабильно при повторном /prep → перезапишет,
не задвоит).

## Step 3 — Save to Встречи tab (deterministic)

```bash
python skills/ceo/prep/scripts/meeting_prep.py --save '{"meetings":[
  {"meeting_id":"<event id>","date":"YYYY-MM-DD","time":"HH:MM","title":"...",
   "participants":["..."],"agenda":["вопрос 1","вопрос 2"],"status":"planned"}
]}'
```

Upsert в таблицу «Встречи» (CEO видит и может править сам). Returns `{saved,count,results}`.

## Step 4 — Send briefing (по блокам)

```
🗓 *Встречи сегодня — {N}*

*{HH:MM} — {Название}* ({участники})
1. {вопрос}
2. {вопрос}
…

*{HH:MM} — {Название}*
…

📋 Повестки в таблице «Встречи» — можешь дополнить сам. После встречи надиктуй итоги → /notes.
```

Сортируй по времени. Кратко, читабельно за рулём. Это бриф, НЕ черновик — НЕ добавляй
`[[draft_actions]]`.

## Edge cases

| Случай | Поведение |
|---|---|
| Встреча без участников/описания | Сгенерируй вопросы из названия + релевантного проекта |
| Несколько встреч по одному проекту | Разные углы (не дублируй вопросы) |
| Повтор `/prep` за день | save перезапишет повестки (upsert по meeting_id) — норм |
| Календарь пуст | «Встреч нет», предложить добавить, save не звать |

## What NOT to do

- ❌ Не путай с `/notes` (там протокол ПОСЛЕ встречи) и `/capture` (заметки).
- ❌ Не выдумывай встречи, которых нет в календаре.
- ❌ Не больше 7 вопросов на встречу — это фокус, не список ради списка.
