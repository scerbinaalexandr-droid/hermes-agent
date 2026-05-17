---
name: week
description: |
  Weekly CEO review for the CEO of TANDEM Group. Auto-invoked when the user
  types /week in Telegram (variants: "weekly review", "ceo review",
  "обзор недели", "итоги недели"). Reads memory/projects.md, memory/risks.md,
  memory/daily_log.md (last 7 entries), memory/weekly_review.md (last entry,
  for comparison). Asks blueprint §09 questions, saves to
  logs/weekly/YYYY-Www.md, memory/weekly_review.md, and updates
  memory/projects.md (status + last_update) for projects the user mentioned.
version: 0.1.0
author: alexandr.scerbina
license: MIT
prerequisites:
  files:
    - memory/soul.md
    - memory/projects.md
    - memory/risks.md
    - memory/daily_log.md
    - memory/weekly_review.md
metadata:
  hermes:
    tags: [CEO, Weekly, Review, Sunday, Telegram]
    commands: [/week]
    triggers:
      - "/week"
      - "weekly review"
      - "ceo review"
      - "обзор недели"
      - "итоги недели"
---

# Weekly CEO Review — TANDEM Group

**Purpose.** Sunday consolidation: что двигалось / стагнирует, риски, фокус
следующей недели. Per blueprint §09.

**Trigger.** `/week` в Telegram (Sun 18:00 cron в Stage 6, manual до тех пор).

---

## Persona

Load `memory/soul.md` first. Apply 5 guardrails + privacy guard + concise tone.

---

## Step 1 — Gather context

```bash
python skills/ceo/week/scripts/record_week.py --gather
```

Returns JSON with:
- `iso_week` (e.g. `2026-W20`)
- `week_start`, `week_end`
- `daily_log_entries_this_week` — все daily_log entries за последние 7 дней
- `all_projects` — список с status/priority/deadline/next_actions для апдейта
- `top_risks` — sorted by severity × probability
- `last_weekly_review` — последний weekly review block (для сравнения week-over-week)

---

## Step 2 — Compact prompt (voice-first)

В Telegram короткое приглашение, **не** 14-question list:

```
📅 Weekly Review {iso_week} (неделя завершается {week_end})

Прошлая неделя по daily_log:
{1-2 строки top events}

Топ рисков: {top 3 names с severity}

Расскажи неделю голосом (1-3 voice memo, 30-60 сек каждый) или текстом —
свободно. Я разберу на 14 секций сам:

бизнес / cashflow / продажи / производство / маркетинг / команда /
проекты (status) / здоровье / семья / recovery / обучение /
изменения рисков / ключевые решения / фокус следующей недели

(или /skip чтобы пропустить этой неделей)
```

## Step 3 — Parse free-form into 14 fields

User говорит потоком о неделе. Извлеки 14 полей (LLM reasoning):

- **Бизнес** — общая картина бизнеса этой недели (revenue/momentum/feel)
- **Cashflow** — упоминания денег / runway / concerns
- **Продажи** — упоминания TC360, sales pipeline, conversion
- **Производство** — Kitchen by Tandem, lean, OEE, defects
- **Маркетинг** — TikTok, brand, content
- **Команда** — key people movements, hiring, conflicts, mentions of names → roles
- **Проекты** — extract pairs `<имя проекта>: <новый статус / progress note>`. Если user сказал "Tandem Casa активный +12%" → {name: "Tandem Casa 360°", status: "active", note: "+12%"}
- **Здоровье** — спорт sessions, sleep, labs, energy trend
- **Семья** — touchpoints (БЕЗ имён, redact в "Супруга" / "родители")
- **Recovery** — пришёл ли с энергией / выгорел
- **Обучение** — что прочитал / book / podcast / insight
- **Изменения по рискам** — new risks, escalations, closures (mentioned by user)
- **Ключевые решения** — explicit "решил / договорились / decision" фразы
- **Фокус следующей недели** — "на следующей неделе нужно / буду / приоритет"

Поле не упомянуто → `(не упомянуто)`. Не выдумывай.

## Step 4 — Show draft

```
📅 Распознал weekly review {iso_week}:

*Бизнес:* {x}
*Cashflow:* {x}
*Продажи:* {x}
...
*Проекты обновлены:*
  - Tandem Casa 360°: active — pipeline +12%
  - Brasov Apartment: blocked — contractor delay
*Семья:* {x — после redaction}
*Фокус следующей недели:* {x}

Сохранить? «✅ да» / «✏️ поправь: <поле>: <новое>»
```

## Step 5 — Save (после approve)

---

## Step 3 — Parse + save

Parse user's response (label-based, case-insensitive). Missing fields → `(not provided)`.

For section **7. Projects** — каждая строка ожидается формата `<Project Name>: <new status>`. Распознай как список tuples → передай в helper для апдейта `projects.md`.

```bash
python skills/ceo/week/scripts/record_week.py --save '<JSON>'
```

JSON shape:
```json
{
  "business": "...",
  "cashflow": "...",
  "sales": "...",
  "production": "...",
  "marketing": "...",
  "team": "...",
  "projects": [
    {"name": "Tandem Casa 360°", "status": "active", "note": "pipeline +12%"},
    {"name": "Brasov Apartment Renovation", "status": "blocked", "note": "contractor delay"}
  ],
  "health": "...",
  "family": "...",
  "recovery": "...",
  "learning": "...",
  "key_risks_changed": "...",
  "key_decisions": "...",
  "next_week_focus": "..."
}
```

Helper writes:
1. Full text → `logs/weekly/YYYY-Www.md`
2. Short summary → `memory/weekly_review.md` (append-only)
3. For each project в `projects` array: `update_project_field(name, 'Status', status)` + `update_project_field(name, 'Last Update', today)`. Logs unmatched project names to confirmation message.

---

## Step 6 — Acknowledge

≤4 строки + next-steps:

```
✅ Weekly {iso_week} сохранён.
Проектов обновлено: {N matched} | не найдено: [{names if any}]
Фокус: {next_week_focus first 70 chars}

Что дальше? · /brief завтра 07:30 · /capture decision <следующий шаг>
```

---

## Edge cases

| Случай | Поведение |
|---|---|
| User вызывает `/week` среди недели (не Sunday) | Allow, but include в confirmation note: «Week not closed yet — partial review.» |
| User присылает только некоторые fields | Save partial. Не переспрашивай — выходные. |
| Project в section 7 не найден в projects.md | НЕ создавай новый — log в confirm message: «Unknown project: 'X'. Add via /capture if real, or fix spelling.» |
| Длинный response > 4096 char | Save целиком в file. Confirm укладывается в 4096. |

---

## What NOT to do

- ❌ НЕ создавай новые проекты в projects.md через /week — это для /capture skill (Stage 5b).
- ❌ НЕ меняй risks.md из /week автоматически — пометь в key_risks_changed и предложи через /risks (Stage 5c).
- ❌ НЕ генерируй "advice" / "coaching" — это recap + decisions, не therapy.
