---
name: report
description: |
  Generate professional HTML dashboard report from REAL memory data
  (captures, decisions, weekly_reviews, projects, risks, daily_log). NO fake
  stats, NO external news, NO fabricated threat levels — only real content
  the CEO captured. Single artefact: bot generates HTML → sends as Telegram
  document (.html attached) → identical view on Mac (Chrome) and iPhone
  (Safari/Telegram preview).
  Args: /report week (default — last 7 days), /report month (last 30),
  /report quarter (last 90), /report all (full memory dump).
version: 0.1.0
author: alexandr.scerbina
license: MIT
prerequisites:
  files:
    - memory/decisions.md
    - memory/daily_log.md
    - memory/weekly_review.md
    - memory/projects.md
    - memory/risks.md
metadata:
  hermes:
    tags: [CEO, Report, HTML, Dashboard, Telegram]
    commands: [/report]
    triggers:
      - "/report"
      - "отчёт"
      - "weekly report"
      - "monthly report"
---

# Report — Real-data HTML Dashboard

**Purpose.** Профессиональный shareable отчёт для CEO команды на базе **реальных** данных из памяти. Замена для предыдущих fake-data «competitive intel reports».

**Trigger.** `/report [period]` где period = `week` (default) | `month` | `quarter` | `all`.

## КРИТИЧНО — NO fake data

Применяй `soul.md::4a NO FAKE DATA` правило **жёстко**:
- НЕ выдумывай stats / threat levels / sentiment scores / cited articles
- НЕ упоминай конкурентов (Rovere, Mobexpert, IKEA, KUXA, JYSK) если **в твоей памяти их нет**
- НЕ изобретай sources (ZF.ro, Profit.ro, HotNews) — там данных у тебя НЕТ
- Если section пустой — пиши «(нет данных за период — добавь через `/capture`)»

## Step 1 — Resolve period

```python
period = parse_arg(user_input)  # "week" | "month" | "quarter" | "all"
days = {"week": 7, "month": 30, "quarter": 90, "all": 9999}[period]
```

## Step 2 — Generate (HTML + PDF + Google Doc)

Запусти helper **с флагами `--pdf --gdoc`**:

```bash
python skills/ceo/report/scripts/generate_report.py --period <week|month|quarter|all> --pdf --gdoc --output /opt/data/reports/
```

`--gdoc` создаёт **редактируемую копию отчёта как Google Doc** в Drive Hermes
(конвертация HTML→Doc нативно, без новых зависимостей). Ссылка попадает в
`telegram_caption` автоматически. Doc экспортируется в PDF/Word в один клик
(File → Download). Best-effort: если Doc не создался — отчёт всё равно уходит
HTML+PDF, в caption будет строка `⚠ Google Doc не создан`.

Helper делает:
1. Читает `memory/*.md` + `logs/daily/*.md` + `logs/weekly/*.md`
2. Фильтрует entries по дате в окне period
3. Аггрегирует: captures by type, decisions, weekly summaries, project status, risks, energy/stress trend (если есть evening reviews)
4. Рендерит HTML через inline template + Chart.js CDN
5. Если `--pdf` — рендерит **PDF через headless Chromium** (`/opt/hermes/.playwright/chromium*/chrome-linux/headless_shell --print-to-pdf`). Chart.js charts реально выполняются и появляются в PDF.
6. Сохраняет `/opt/data/reports/tandem-report-<period>-<YYYY-MM-DD>.html` (+ .pdf если --pdf успешно)
7. Returns JSON `{html_path, pdf_path, pdf_status, filled, empty, stats}`

Если `pdf_status.ok == false` (Chromium не найден или timeout) — продолжай только с HTML, не падай. В caption Telegram упомяни: «PDF не сгенерирован: {reason}, HTML работает».

## Step 3 — Send as Telegram document(s) + public URL

После helper — **КРИТИЧНО**:

Helper возвращает JSON с полем `telegram_caption` — это **готовая строка** для Telegram caption. Используй её **БЕЗ ИЗМЕНЕНИЙ**:

- ❌ НЕ переписывай caption своими словами
- ❌ НЕ сокращай (там уже всё нужное в правильном формате)
- ❌ НЕ убирай URL (это критичный элемент для multi-device доступа)
- ❌ НЕ переводи русские/английские части
- ✅ Возьми `result["telegram_caption"]` как есть и используй для первого attachment

### Алгоритм отправки

1. **Если `result["pdf_path"]` != null** → `telegram_send_document(pdf_path, caption=result["telegram_caption"])`. Потом `telegram_send_document(html_path)` без caption (caption только на первом файле).
2. **Если только HTML** → `telegram_send_document(html_path, caption=result["telegram_caption"])`.
3. **НЕ** дублируй summary текстом в чат — caption + файлы = single source of truth.

### Пример correct flow

User: `/report week`

Bot internal:
1. `python3 .../generate_report.py --period week --pdf --gdoc` → returns JSON
2. Read `result["telegram_caption"]` (готовая строка, ~400 char)
3. `telegram_send_document(result["pdf_path"], caption=result["telegram_caption"])`
4. `telegram_send_document(result["html_path"])`
5. **Не пиши** дополнительных text-сообщений с дублированием.

## Step 4 — Acknowledge (короткое)

После двух attachments **одна** строка подтверждения (НЕ повторяй URL — он в caption):

```
✅ Готово · Что дальше? · /capture новые insights · /report month — за месяц
```

## Sections в отчёте (HTML)

| Section | Source | Если пусто |
|---|---|---|
| **Executive summary** | top 3 decisions + top 3 risks + 1 next_week_focus | «Добавь decisions через `/capture decision:`» |
| **Captures by type (pie chart)** | daily_log.md entries в окне | «Нет captures за период» |
| **Decisions made** | decisions.md в окне | «Добавь через `/capture decision:`» |
| **Weekly reviews** | weekly_review.md entries в окне | «Запусти `/week` в воскресенье» |
| **Active projects** | projects.md (priority high + medium + active) | «Заполни Next Actions в memory/projects.md» |
| **Top risks** | risks.md (severity × probability sorted) | «Заполни memory/risks.md» |
| **Energy/Stress trend (line chart)** | logs/daily/*.md::Evening блоки в окне | «Запусти `/evening` несколько дней» |
| **Activity timeline** | хронология captures + decisions + evenings | (auto-empty если первые 5 пусты) |

## Edge cases

| Случай | Поведение |
|---|---|
| **Все sections empty** | НЕ отправляй HTML файл. Reply text: «Памяти за <period> мало. Запусти /capture, /evening, /week несколько дней — потом /report.» |
| `--period quarter` но memory только за 7 дней | Helper фильтрует по существующим данным, секция «нет данных за месяц X-Y» появляется. |
| User просит «сделай отчёт с конкурентами» | Reply: «Конкурентный анализ требует real web scraping (Phase 4, separate project tandem-competitive-intel). В memory этого нет — не выдумываю.» |
| User просит PDF | PDF генерируется через `--pdf` (headless Chromium) и уходит вложением. Если Chromium недоступен — открой Google Doc (`--gdoc`) → File → Download → PDF/Word, тот же контент. |

## What NOT to do

- ❌ НЕ генерируй "Romania Economic Indicators" блок (нет real data sources)
- ❌ НЕ упоминай "Consumer Spending", "Interest Rates", market stats
- ❌ НЕ упоминай конкурентов с threat levels (Rovere PRIMARY THREAT etc)
- ❌ НЕ оборачивай short response в HTML — это **document**, для shareable артефакта
- ❌ НЕ забывай caption с указанием **пустых секций** — это honesty
- ❌ НЕ дублируй HTML контент text в чат — single artefact
