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

## Step 2 — Generate (HTML + PDF)

Запусти helper **с --pdf флагом**:

```bash
python skills/ceo/report/scripts/generate_report.py --period <week|month|quarter|all> --pdf --output /opt/data/reports/
```

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

После helper:

1. **Если PDF создан** (`pdf_status.ok == true`) — отправляй **сначала PDF, потом HTML** двумя `telegram_send_document` вызовами.
2. **Если PDF не создан** — только HTML.
3. **ВСЕГДА** показывай `public_url` в caption (если `upload_status.ok == true`). Это решает кейс «отчёт пришёл в один телефон, не в другой» — по URL открывается на любом устройстве.

### Caption template (≤500 char, русский)

```
📊 **Отчёт за <период>** готов

📈 Данные: <filled_count>/<total> секций (<filled_list>)
{if empty_count > 0} ⚠ Пустые: <empty_list> (как заполнить — внутри){endif}

🔗 **Открыть по ссылке:** <public_url>
   Работает на любом устройстве, ссылка persistent (не expires)

📎 Файлы во вложении:
• PDF — для шеринга команде (<pdf_size_kb> KB)
• HTML — interactive с charts (<html_size_kb> KB)
```

Если `upload_status.ok == false` — НЕ скрывай это. Добавь строку:
```
⚠ Публичная ссылка не загрузилась: <reason>. Только файлы во вложении.
```

4. **НЕ** дублируй summary в чат текстом — single source of truth = файлы + URL.

## Step 4 — Acknowledge

≤3 строки:

```
✅ Отчёт отправлен — PDF, HTML и публичная ссылка выше.
Что дальше? · /capture новые insights · /report month — за месяц
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
| User просит PDF | Reply: «PDF в production нет (reportlab не установлен). Открой `.html` в Chrome → File → Print → Save as PDF — same content.» |

## What NOT to do

- ❌ НЕ генерируй "Romania Economic Indicators" блок (нет real data sources)
- ❌ НЕ упоминай "Consumer Spending", "Interest Rates", market stats
- ❌ НЕ упоминай конкурентов с threat levels (Rovere PRIMARY THREAT etc)
- ❌ НЕ оборачивай short response в HTML — это **document**, для shareable артефакта
- ❌ НЕ забывай caption с указанием **пустых секций** — это honesty
- ❌ НЕ дублируй HTML контент text в чат — single artefact
