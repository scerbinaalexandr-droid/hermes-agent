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

## Step 2 — Ask the user the 11 questions

Отправь в Telegram ОДНО сообщение со всем шаблоном (≤4096 char). НЕ дроби на 11 отдельных сообщений — это раздражает на ходу.

Шаблон вопроса (ВСЕ headers на русском):

```
🌙 Вечерний обзор — {YYYY-MM-DD} ({день недели})

Сегодня по daily_log:
{today_log_entries highlight — 3-4 строки максимум}

Ответь одним сообщением (можно blocks):

1. *Выполнено:* (что сделал из brief priorities)
2. *Не выполнено:* (что осталось)
3. *Почему:* (если осталось — причина)
4. *Перенос:* (что переносится на завтра)
5. *Главный bottleneck:* (что больше всего тормозило)
6. *Энергия:* 1-10
7. *Стресс:* 1-10
8. *Здоровье:* (спорт/сон/еда коротко)
9. *Семья:* (touchpoint с Супругой / родителями сделан?)
10. *Урок дня:* (одно предложение)
11. *Фокус на завтра:* (1-3 главных приоритета)
```

**КРИТИЧНО:** имена членов семьи в output → "Супруга", "родители". Без ФИО.

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

## Step 5 — Confirm to user

Короткое подтверждение на русском:

```
✅ Вечерний обзор сохранён.
   Энергия: {energy_level}/10 | Стресс: {stress_level}/10
   Фокус на завтра: {tomorrow_focus — first 80 chars}

Цель сна: 7+ часов.
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
