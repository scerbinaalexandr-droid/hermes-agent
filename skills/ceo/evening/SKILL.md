---
name: evening
description: |
  Evening executive review for the CEO of TANDEM Group. Auto-invoked when the
  user types /evening in Telegram (variants: "evening review", "recap",
  "вечерний обзор", "итоги дня"). Reads memory/daily_log.md (today's brief +
  captures), memory/projects.md (priority=high), memory/risks.md. Asks the
  user the blueprint §08 questions (one message per question or all-at-once)
  and appends the structured response to logs/daily/YYYY-MM-DD.md +
  memory/daily_log.md. Updates memory/memory.md::Active Priorities for
  tomorrow.
version: 0.1.0
author: alexandr.scerbina
license: MIT
prerequisites:
  files:
    - memory/soul.md
    - memory/daily_log.md
    - memory/projects.md
    - memory/risks.md
metadata:
  hermes:
    tags: [CEO, Evening, Review, Daily, Telegram]
    commands: [/evening]
    triggers:
      - "/evening"
      - "evening review"
      - "вечерний обзор"
      - "итоги дня"
      - "recap"
---

# Evening Review — CEO of TANDEM Group

**Purpose.** Закрытие дня. Снимает mental residue, готовит фокус на завтра.
Per blueprint §08.

**Trigger.** `/evening` в Telegram or semantic variants.

---

## Persona

Прочитай `memory/soul.md` целиком ПЕРЕД любым ответом. Применяй 5 правил + privacy guard + tone (прямой, экономный, без флаттери).

---

## Step 1 — Load today's context

Используй helper:

```bash
python skills/ceo/evening/scripts/record_evening.py --gather
```

Возвращает JSON с:
- `date`, `weekday`
- `today_log_entries` — что было в `daily_log.md` сегодня (brief + captures)
- `today_per_day_log` — содержимое `logs/daily/YYYY-MM-DD.md` если есть
- `high_priority_projects` — для соотнесения завтрашнего фокуса
- `top_risks` — top 3 active risks

---

## Step 2 — Compact prompt (voice-first)

В Telegram **короткое** приглашение (≤ 400 char), НЕ список из 11 вопросов:

```
🌙 Вечер — {день недели}, {YYYY-MM-DD}

Расскажи как прошёл день голосом (одним voice memo 30-60 сек) или текстом —
свободной формой. Я сам разберу на:

выполнено / не выполнено / почему / перенос / bottleneck / энергия (1-10) /
стресс (1-10) / здоровье / семья / урок дня / фокус на завтра.

Просто говори как другу — порядок и слова неважны.

(или /skip чтобы пропустить evening сегодня)
```

## Step 3 — Parse free-form into 11 fields

User отвечает голосом / текстом — **поток сознания** без структуры. Твоя задача — извлечь 11 полей из этого потока (LLM-side reasoning):

- **Выполнено** — фразы про "сделал / закрыл / завершил / отправил / решил"
- **Не выполнено** — "не успел / отложил / завис / не дошли руки"
- **Почему** — причина невыполнения (если упомянута)
- **Перенос** — что явно переносится на завтра / следующую неделю
- **Bottleneck** — "тормозило / залипал / мешало / energy-killer"
- **Энергия 1-10** — если user не назвал число, оцени по тону (10 = "топ-форма", 5 = "так себе", 2 = "выжатый") и пометь *(оценено по тону)*
- **Стресс 1-10** — аналогично; если упоминает спокойствие / поток / лёгкость — низкий; "горел / давит / нервы" — высокий
- **Здоровье** — спорт, сон, еда (упоминания)
- **Семья** — touchpoints с Супругой / родителями (БЕЗ имён — применяй privacy redaction)
- **Урок дня** — главный вывод / observation
- **Фокус на завтра** — explicit "завтра нужно/буду" фразы

Если поля **нет** в потоке — `(не упомянуто)`, **не выдумывай**.

## Step 4 — Show draft

```
🌙 Распознал твой evening recap:

*Выполнено:* {x}
*Не выполнено:* {x}
*Почему:* {x}
*Перенос:* {x}
*Bottleneck:* {x}
*Энергия:* {N}/10 {(оценено по тону) if applicable}
*Стресс:* {N}/10 {(оценено по тону) if applicable}
*Здоровье:* {x}
*Семья:* {x — после privacy redaction}
*Урок:* {x}
*Завтра:* {x}

Сохранить? «✅ да» / «✏️ поправь: <поле>: <новое значение>»
```

## Step 5 — Save (после approve)

После «да» / «ok» / эмодзи галочки — call helper.

---

## Step 3 — Parse user's response

User отвечает свободным текстом со структурой выше. Распознавай fields по labels
(case-insensitive, дopuсkajut в форматах "1.", "Completed:", "**Completed:**").
Если какое-то поле отсутствует — НЕ ВЫДУМЫВАЙ. Помечай как `(not provided)`.

---

## Step 4 — Save

Передай распарсенные fields в helper:

```bash
python skills/ceo/evening/scripts/record_evening.py --save '<JSON>'
```

JSON shape:
```json
{
  "completed": "...",
  "not_completed": "...",
  "why": "...",
  "carry_over": "...",
  "main_bottleneck": "...",
  "energy_level": "8",
  "stress_level": "4",
  "health_status": "...",
  "family_status": "...",
  "lesson_learned": "...",
  "tomorrow_focus": "..."
}
```

Helper делает:
1. Append full structured review → `logs/daily/YYYY-MM-DD.md::Evening (HH:MM)`
2. Append short summary → `memory/daily_log.md` (2-3 lines)
3. Update `memory/memory.md::Active Priorities (this week)` — заменяет старые active items на `tomorrow_focus` bullets (safe-edit, с current week + carry over)

---

## Step 6 — Acknowledge

≤3 строки + next-steps:

```
✅ Evening сохранён. Энергия {energy_level}/10 · Стресс {stress_level}/10
Завтра: {tomorrow_focus first 60 chars}

Что дальше? · Сон 7+ часов · /brief завтра 07:30 (cron)
```

---

## Edge cases

| Случай | Поведение |
|---|---|
| User отправил только часть полей | Сохрани что есть, пометь missing как `(not provided)`. НЕ переспрашивай — он устал к вечеру. |
| Energy ≤ 4 или Stress ≥ 7 третий день подряд | Добавь в ответ flag: «⚠ Energy/Stress тренд снижается — burnout risk. Завтрашний focus защити recovery block.» |
| User отвечает one-liner типа «всё ок» | Сохрани как `Completed: всё ок`, остальное — `(not provided)`. Не давишь. |
| Reset: user /evening дважды в один день | Replace previous evening entry в `logs/daily/YYYY-MM-DD.md`. Append с timestamp `Evening (HH:MM v2)`. |
| Длинный response > 4096 char | Сохрани полностью (нет лимита на файл), confirm в Telegram укладывается в 4096. |

---

## What NOT to do

- ❌ НЕ выдумывай completed items. Если user не сказал — `(not provided)`.
- ❌ НЕ корректируй priorities/projects через evening review — это для weekly review (`/week`).
- ❌ НЕ давай советы / coaching. Это recap, не therapy. Persona tone: прямой, фактический.
- ❌ НЕ переноси sensitive (имена партнёров, цены) raw в memory — apply pseudonymization из soul.md privacy guard.
