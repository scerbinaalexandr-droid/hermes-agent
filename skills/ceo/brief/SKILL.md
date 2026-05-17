---
name: brief
description: |
  Daily executive briefing for the CEO of TANDEM Group. Auto-invoked when the
  user types /brief in Telegram (or any variant: "daily brief", "morning
  briefing", "что у меня сегодня", "план дня"). Reads /memory/*.md and
  produces a Telegram-fit briefing per blueprint §07 (Date, Main Focus,
  Top 3 Business, Top 3 Personal, Meetings, Deadlines, Health Action,
  Family Touchpoint, Energy Warning, Main Risk Today, One Important Question).
  Appends the briefing to logs/daily/YYYY-MM-DD.md.
version: 0.1.0
author: alexandr.scerbina
license: MIT
prerequisites:
  files:
    - memory/soul.md
    - memory/user.md
    - memory/memory.md
    - memory/areas.md
    - memory/projects.md
    - memory/risks.md
metadata:
  hermes:
    tags: [CEO, Briefing, Daily, Telegram, Memory, Tandem]
    commands: [/brief]
    triggers:
      - "/brief"
      - "daily brief"
      - "morning briefing"
      - "что у меня сегодня"
      - "план дня"
---

# Daily Executive Briefing — CEO of TANDEM Group

**Purpose.** Утренний brief для Alexandr Scerbina (CEO TANDEM Group). Сжатый, focused, помещается в одно Telegram-сообщение (≤4096 символов).

**Trigger.** `/brief` в Telegram, любые семантические варианты ("morning brief", "план дня", "что у меня сегодня").

**Source of truth.** Markdown файлы в `memory/`. Если файл отсутствует или пустой — graceful stub с указанием что заполнить.

---

## Persona (load first)

Перед генерацией briefing **прочитай `memory/soul.md` целиком** и применяй все 5 поведенческих правил + privacy guard + tone rules.

Ключевое:
- Прямой, экономный к словам. НЕ используй «отлично», «прекрасно», «хороший вопрос».
- ZERO false positives — если данных нет, скажи «нет данных», не выдумывай.
- Privacy: ФИО неизвестных — псевдонимы; точные цены — диапазоны.

---

## Memory loads (порядок чтения)

1. `memory/soul.md` — guardrails + tone (для каждого вывода)
2. `memory/user.md` — стабильный профиль CEO (geo, brands, priorities)
3. `memory/memory.md` — active context (week priorities, current issues, strategic themes)
4. `memory/areas.md` — 12 life domains (для Health Action / Family Touchpoint)
5. `memory/projects.md` — active projects (filter priority=high → Top 3 Business)
6. `memory/risks.md` — для Main Risk Today
7. `memory/daily_log.md` last 3 entries — для Energy Warning + carry-over + **morning combo**

## Morning combo — yesterday recap on top (NEW)

Если в `daily_log.md` есть entry за **предыдущий день** (`yesterday = today - 1`)
с секцией `### Evening (HH:MM)` — извлеки:
- Энергия / Стресс scores
- Lesson learned (одна строка)
- Carry-over для сегодня
- Не-выполненное вчера

Показывай это **в самом начале** briefing как «Вчера в 2 строки», чтобы CEO мог
быстро contextualize не лезя в archive.

Используй helper:

```python
from skills.ceo._lib.memory import (
    load_memory, projects_by_priority, last_entries,
    extract_section, today_iso, append_entry,
)

soul  = load_memory(['soul'])['soul']
user  = load_memory(['user'])['user']
mem   = load_memory(['memory'])['memory']
areas = load_memory(['areas'])['areas']
risks = load_memory(['risks'])['risks']
high_projects = projects_by_priority('high')   # list of dicts
recent_days   = last_entries('daily_log', limit=3)
```

---

## Output structure (блюпринт §07) — **ВСЕГДА на русском**

Telegram MarkdownV2, ≤4096 char. Headers и метки — **только русский**. Технические идентификаторы (имена файлов, slash-команды, имена проектов) — без перевода.

```markdown
# Утренний брифинг

*Дата:* {YYYY-MM-DD} ({день недели на русском})

*Вчера:* (только если есть yesterday evening)
Энергия {N}/10 · Стресс {N}/10 · Урок: {lesson short}
Carry-over: {1-2 items от вчера на сегодня}

*Главный фокус:*
{одно предложение — что главное сегодня. Извлекается из memory.md::Active Priorities или manual override}

*Топ-3 бизнес-приоритета:*
1. {из projects.md (priority=high) с next action}
2. {из projects.md (priority=high) с next action}
3. {из projects.md (priority=high) с next action}

*Топ-3 личных приоритета:*
1. {из areas.md (Супруга/Родители/Здоровье/Спорт) и memory.md}
2. {…}
3. {…}

*Встречи:* {если calendar integration есть — list; иначе: «календарь не подключён»}

*Дедлайны:* {projects.md::Deadline в ближайшие 7 дней}

*Действие по здоровью:* {из areas.md::Health Recurring Actions — что сегодня}

*Семейный touchpoint:* {из areas.md::Супруга / Родители — БЕЗ имён, используй "Супруга", "родителям"}

*Предупреждение по энергии:* {из daily_log last evening Energy Level / Stress Level; если последние 3 дня показывают drop → flag}

*Главный риск сегодня:* {top severity*probability риск из risks.md status=active}

*Один важный вопрос:* {LLM генерирует 1 reflective вопрос based на context — что worth pondering today}

Что дальше? · /capture — мысль/задача · /projects high — статусы · /evening вечером
```

**Запрещено:** имена членов семьи в outputе. ВСЕ упоминания супруги → "Супруга". Родители → "родители" / "Мама" / "Папа" (без ФИО).

---

## Logging

После генерации — append в `logs/daily/YYYY-MM-DD.md` (создать если не существует):

```markdown
## Brief (HH:MM)

{полный текст briefing'а который ушёл в Telegram}
```

И в `memory/daily_log.md`:

```python
from skills.ceo._lib.memory import append_entry, today_iso
append_entry('daily_log', today_iso(), '### Brief (HH:MM)\n{short summary 2-3 lines}')
```

---

## Edge cases

| Случай | Поведение |
|---|---|
| `memory/*.md` пустой или missing field | Возврат structured stub: «Раздел X пустой — добавьте в memory/<file>.md» вместо выдумывания |
| `projects.md` нет priority=high | Top 3 Business — fallback на priority=medium с пометкой «no high-priority projects» |
| `daily_log.md` ещё нет evening для last day | Energy Warning: «no evening review for {date}» |
| LLM timeout / rate-limit | Fallback: показать last `logs/daily/YYYY-MM-DD.md::Brief` секцию + извинение |
| Output > 4096 char | Split на 2 message с (1/2)(2/2) markers |
| User зовёт `/brief` дважды за день | Regenerate (свежие данные) + пометить «(refresh #N)» в log |

---

## What NOT to do

- ❌ НЕ генерируй данные которых нет в memory. Если нет meetings — пиши «calendar не подключён», не выдумывай.
- ❌ НЕ предлагай новые проекты / стратегии в briefing — это Phase 3 routine assistant.
- ❌ НЕ инициируй proactive — только on-demand или cron (Stage 6).
- ❌ НЕ raw-копируй sensitive data — псевдонимы / диапазоны (см. soul.md::Privacy guard).
- ❌ НЕ отвечай в style «Доброе утро! Сегодня тебя ждёт замечательный день» — это flattery. Прямой / экономный.

---

## Example output (when memory is populated)

```
# Утренний брифинг

Дата: 2026-05-17 (воскресенье)

Главный фокус:
Sprint Hermes V1 MVP — закрыть Stage 4 (/brief работает end-to-end).

Топ-3 бизнес-приоритета:
1. Tandem Group CEO System — verify /brief в Telegram, подготовить Stage 5 план
2. Tandem Casa 360° — обзор недельного sales pipeline
3. Kitchen by Tandem — lean-kitchen Sprint 10 kickoff prep

Топ-3 личных приоритета:
1. 3x training в неделю — воскресный active recovery 60 мин
2. Семейный ужин с Супругой
3. Воскресный звонок родителям (ритуал)

Встречи: календарь не подключён

Дедлайны:
— Brasov Apartment milestone (см. projects.md::Brasov)
— Pharma RO partner sync (этой неделе)

Действие по здоровью: 60 мин active recovery + 7+ часов сна

Семейный touchpoint: ужин с Супругой 19:00; звонок родителям 18:00

Предупреждение по энергии: вчерашний evening review отсутствует — запусти /evening после briefing

Главный риск сегодня: CEO calendar overload (high prob) — защити 2hr deep-work блок

Один важный вопрос: какой 1 рычаг сегодня сдвинет неделю на 80%?
```

---

## Example output (when memory is empty/stub)

```
# Утренний брифинг

Дата: 2026-05-17 (воскресенье)

⚠ Memory layer пустой — заполни /memory/user.md, /memory/memory.md, /memory/projects.md.

Что сделать в ближайшие 30 мин:
1. Открой memory/user.md — заполни Leadership Style, Communication Style разделы
2. Открой memory/memory.md — добавь Active Priorities (this week)
3. Открой memory/projects.md — заполни 10 initial projects (см. SOP/project_management.md)

После этого /brief вернёт реальный structured briefing.
```
