---
name: dashboard
description: |
  Forward-looking CEO Executive Cockpit — взгляд ВПЕРЁД (что на столе сейчас и
  что впереди), в отличие от /report (ретроспектива за период). Генерирует
  self-contained HTML из REAL памяти и отправляет в Telegram как документ.
  Секции: Top-of-mind сегодня (memory.md::Active Priorities), Backlog
  надиктованного (/capture task: за 30 дней), Weekly Plan (Next Week Focus),
  активные проекты с прогрессом, риски под наблюдением, тренд энергии/стресса
  (если есть evening reviews), журнал недавних решений, quick-capture
  напоминание. NO fake stats, NO external news, NO fabricated identifiers.
  Args: /dashboard (без аргументов — всегда текущий снимок памяти).
version: 0.1.0
author: alexandr.scerbina
license: MIT
prerequisites:
  files:
    - memory/soul.md
    - memory/memory.md
    - memory/projects.md
    - memory/risks.md
    - memory/decisions.md
    - memory/weekly_review.md
    - memory/daily_log.md
metadata:
  hermes:
    tags: [CEO, Dashboard, HTML, Cockpit, Telegram]
    commands: [/dashboard]
    triggers:
      - "/dashboard"
      - "кокпит"
      - "executive cockpit"
      - "что на столе"
      - "взгляд вперёд"
      - "панель"
---

# Dashboard — Executive Cockpit (взгляд вперёд)

**Purpose.** Forward-looking HTML-кокпит для CEO: что на столе **сейчас** и что
**впереди**. В отличие от `/report` (что произошло за период), `/dashboard`
смотрит вперёд — открытые приоритеты, надиктованный backlog, план недели,
прогресс проектов, риски под наблюдением. Тот же premium dark TANDEM-стиль
(gold `#c4a747`), что у `/report`. Single artefact: bot генерирует HTML →
отправляет как Telegram document → одинаковый вид на Mac (Chrome) и iPhone.

**Trigger.** `/dashboard` (без аргументов — всегда текущий снимок памяти).

## КРИТИЧНО — NO fake data (soul.md §4a/§4c)

Применяй жёстко:
- НЕ выдумывай stats / threat levels / sentiment scores / KPI / проценты
- НЕ упоминай конкурентов или sources, которых **в памяти нет**
- НЕ выдумывай cron job ID / file paths / deadlines / имена людей без записи в памяти
- Если секция пустая — helper сам рендерит «(нет данных)» с подсказкой как заполнить. НЕ дополняй выдумкой.

---

## Persona

Загрузи `memory/soul.md` целиком. Применяй privacy guard (семейные имена →
«Супруга»/«Мама»/«Папа»; незнакомые партнёры → «партнёр X»; точные цены →
диапазоны) + tone (прямой, экономный, без «отлично»/«прекрасно») + §9 Response
Design + §10 self-eval перед любым текстом в Telegram.

---

## Step 1 — Generate HTML

Запусти helper (только чтение памяти + запись HTML-артефакта в reports dir):

```bash
python3 skills/ceo/dashboard/scripts/generate_dashboard.py --output /opt/data/reports/
```

Helper делает:
1. Читает `memory/memory.md`, `projects.md`, `risks.md`, `decisions.md`,
   `weekly_review.md`, `logs/daily/*.md` — фильтрует по forward-looking логике.
2. Собирает 8 секций (top-of-mind, backlog, weekly plan, проекты с прогрессом,
   риски, health trend, решения, quick-capture).
3. Рендерит self-contained HTML (dark TANDEM theme, Chart.js CDN для тренда).
4. Сохраняет `/opt/data/reports/<uuid>.html` (+ friendly симлинк
   `tandem-dashboard-<YYYY-MM-DD>.html`).
5. Строит `public_url` из `HERMES_PUBLIC_HOST` (если задан в Railway Variables).
6. Возвращает JSON: `{html_path, public_url, telegram_caption, stats, filled, empty}`.

Если все секции пустые — см. Edge cases (не отправляй файл, дай fail-loud текст).

---

## Step 2 — Send as Telegram document + public URL

**КРИТИЧНО.** Helper возвращает поле `telegram_caption` — это **готовая строка**.
Используй её **БЕЗ ИЗМЕНЕНИЙ**:

- ❌ НЕ переписывай caption своими словами
- ❌ НЕ сокращай (там уже всё нужное в правильном формате)
- ❌ НЕ убирай URL (критичный элемент для multi-device доступа)
- ❌ НЕ переводи русские/английские части
- ✅ Возьми `result["telegram_caption"]` как есть для **первого** attachment

Алгоритм:
1. `telegram_send_document(result["html_path"], caption=result["telegram_caption"])`
2. **НЕ** дублируй содержимое кокпита текстом в чат — caption + HTML = single source of truth.

---

## Step 3 — Acknowledge (короткое)

После attachment — **одна** строка подтверждения (НЕ повторяй URL — он в caption):

```
✅ Готово · Что дальше? · /capture task: новые задачи · /report week — ретроспектива
```

---

## Секции в кокпите (HTML)

| Section | Source | Если пусто |
|---|---|---|
| 🎯 **Top-of-mind сегодня** | `memory.md::Active Priorities` (открытые) | «Запиши через `/capture task:`» |
| 🎤 **Backlog надиктованного** | `logs/daily/*.md` capture-task за 30 дней | «Нет надиктованных задач за 30 дней» |
| 📅 **Weekly Plan** | последний `weekly_review.md::Next Week Focus` | «Запусти `/week` в воскресенье» |
| 📂 **Активные проекты** | `projects.md` (non-done, sorted by priority) + прогресс по чекбоксам | «Нет active проектов» |
| ⚠ **Риски под наблюдением** | `risks.md` (severity × probability) | «Заполни `memory/risks.md`» |
| 💗 **Тренд энергии/стресса** | `logs/daily/*.md::Evening` за 14 дней (line chart) | «Запусти `/evening` несколько дней» |
| 📝 **Журнал решений** | `decisions.md` последние записи | «Фиксируй через `/capture decision:`» |
| 🎤 **Quick-capture** | статичное напоминание | (всегда показывается) |

## Edge cases

| Случай | Поведение |
|---|---|
| **Все секции empty** | НЕ отправляй HTML. Reply text: «⚠ Памяти для кокпита мало. Запусти `/capture task:`, `/evening`, `/week` несколько дней — потом `/dashboard`.» |
| `HERMES_PUBLIC_HOST` не задан | Caption сам объясняет как включить Public Networking — отправь как есть, не переписывай. |
| Только template-заглушки в memory.md | Helper отбрасывает строки `<...>` — секция корректно пустая, не выдумывай. |
| User просит «добавь конкурентов / рынок» | Reply: «Конкурентный анализ — Phase 4, в памяти данных нет, не выдумываю. Зафиксировать в TODO?» |
| User просит email/КП по проекту из кокпита | Reply: «Генерация писем/КП — Phase 3, сейчас фокус Memory Hub. Логнуть в TODO?» |

## What NOT to do

- ❌ НЕ пиши в `memory/*.md` — этот skill только читает память + пишет HTML в reports dir (guard.py блокирует запись в memory).
- ❌ НЕ генерируй числа/проценты/KPI/threat levels/sources, которых нет в памяти (soul.md §4a).
- ❌ НЕ упоминай cron job ID / file paths / deadlines / имена людей без записи в памяти (soul.md §4c).
- ❌ НЕ переписывай и не сокращай `telegram_caption` — используй verbatim, не убирай URL.
- ❌ НЕ дублируй HTML контент текстом в чат — это shareable артефакт, single source of truth.
- ❌ НЕ оборачивай short response в HTML — кокпит это **document**.
- ❌ НЕ предлагай новые проекты/стратегии (Phase 3) и не делай sparring (Phase 2) в этом skill.
