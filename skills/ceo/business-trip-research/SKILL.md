---
name: business-trip-research
description: |
  End-to-end business trip research and planning. User provides destination +
  dates + goal (voice or text), agent researches local market (hotels, partners,
  competitors, showrooms), produces structured report with contacts, daily plan,
  checklist, and HTML deliverable for offline use.
  
  Different from /trip (which CAPTURES a trip plan user already has). This skill
  BUILDS the plan from scratch via web research.
version: 0.1.0
author: alexandr.scerbina
license: MIT
prerequisites:
  skills:
    - web
    - trip
metadata:
  hermes:
    tags: [CEO, Research, Travel, Planning, Web]
    triggers:
      - "собери мне на [место] топ компаний"
      - "research for business trip to [place]"
      - "найди контакты в [регион]"
---

# Business Trip Research — End-to-End Planning

**Purpose.** User дает voice memo / текст с описанием командировки (куда, когда,
зачем — напр. "поставщик мебели для отелей в Халкидики"), и ты делаешь:
1. Web research по целевым компаниям (отели, агентства, производители, магазины)
2. Находишь контакты (сайты, emails, LinkedIn, телефоны, ключевых менеджеров)
3. Формируешь структурированный отчёт + HTML deliverable (для Mac + iPhone)
4. Сохраняешь через `/trip` для последующего tracking

**Отличие от `/trip`:** `/trip` ЗАХВАТЫВАЕТ уже готовый план. Этот skill СТРОИТ
план с нуля через research.

---

## Workflow

### Step 0 — Parse user intent

Извлеки из voice memo / текста:
- **Destination** — город/регион (Халкидики, Бухарест, Берлин, etc.)
- **Dates** — если названы (ISO format)
- **Goal** — зачем едет (встречи как поставщик X, изучение рынка Y, поиск партнёров Z)
- **Target segments** — с кем встречаться (отели, агентства, производители, магазины)
- **Industry/domain** — мебель, фармa, IT, etc.

Если user сказал **"реши сам все задачи мне больше не задавай вопросы"** или
аналог — НЕ задавай уточняющие вопросы. Делай smart defaults:
- Даты не указаны → используй контекст (если упомянул "8–16", подразумевай текущий/следующий месяц)
- Язык общения не указан → дефолт английский + русский (где возможно)
- Сегмент отелей не указан → 4–5★ (премиум, т.к. TANDEM Group = premium furniture)

**Если input совсем короткий** («командировка в X») и нет контекста — один
короткий уточняющий вопрос: «Цель поездки? (напр. встречи с отелями / поиск
дистрибуторов / изучение рынка)». Но если есть хоть какой-то контекст — додумай сам.

---

### Step 1 — Pre-flight check (ОБЯЗАТЕЛЬНО, behavioral guardrail #1)

ПЕРЕД началом research **проверь доступность tools:**
1. `/web` skill (search + fetch) — проверь `python3` доступен
2. `write_file` — для HTML отчёта
3. `/trip` helper — для сохранения плана

Если хоть один tool НЕ работает → **ERROR в первом же ответе** с явным указанием
проблемы и альтернатив.

**ЗАПРЕЩЕНО** говорить «Запускаю research…» / «Сейчас соберу…» если pre-flight
не пройден. Это guardrail #1 из persona.

---

### Step 2 — Web research (multi-source)

Используй `/web search` + `/web fetch` для каждого сегмента:

**Структура запросов:**
1. **Hotels** — `"{destination} luxury hotels 4-5 star {industry context}"`  
   Пример: `"Halkidiki luxury hotels 4-5 star procurement furniture"`
2. **Agencies** — `"{destination} {industry} design agencies interior"`  
   Пример: `"Greece hotel design agencies furniture procurement"`
3. **Retailers** — `"{nearest city} {industry} stores showrooms"`  
   Пример: `"Thessaloniki furniture stores showrooms"`
4. **Manufacturers** — `"{region} {industry} manufacturers contract"`  
   Пример: `"Greece furniture manufacturers hotel contract"`
5. **Specific targets** — если user назвал конкретные компании, fetch их сайты

**После каждого search:**
- Fetch топ-3 релевантных результата (через `/web fetch`)
- Извлеки: company name, profile, contact info (email, phone, LinkedIn)
- Если на сайте нет прямых контактов — искать через `"{company name} LinkedIn"`
  или `"{company name} procurement manager contact"`

**Rate limiting:** `/web` уже встроен `time.sleep(1)` между запросами. Для bulk
research (10+ queries) делай паузы 2–3 сек между батчами по 5 запросов.

---

### Step 3 — Structure the report

Формируй **два файла:**

#### 3a. Markdown report (`/tmp/{destination}_trip_report.md`)

Секции:
1. **Заголовок** — Destination, Dates, Goal
2. **Топ-N компаний по каждому сегменту** (hotels, agencies, retailers, manufacturers)
   - Для каждой: Name, Website, Profile, Why important, Contacts (email, phone, LinkedIn, key people to reach)
3. **План командировки** (по дням, если даты известны)
4. **Checklist подготовки** (материалы, логистика, intro emails)
5. **Ожидаемые результаты** (метрики: сколько встреч, RFQ, partnership agreements)
6. **Источники** — все URLs с датой проверки

**Формат контактов (critical):**
```markdown
**Контакты (ориентировочные):**
- Email: info@example.com (с сайта)
- Тел: +30 123 456789
- **Кого искать:** Procurement Manager / FF&E Director
- **LinkedIn:** [Company Name](https://linkedin.com/company/...)
```

НЕ выдумывай имена менеджеров если их нет на сайте — пиши «**Кого искать:**
[роль]» и даёшь LinkedIn компании для поиска.

#### 3b. HTML report (`/tmp/{destination}_report.html`)

**Стилизация:** tandemcasa.ro brand colors:
- Background: `#111111` (черный)
- Text: `#e2dcd2` (светло-бежевый)
- Accent: `#c9a96e` (золото)
- Secondary: `#bdb5ab` (камень)

**Структура:** одностраничный HTML с секциями (Hotels, Agencies, Manufacturers,
Plan, Checklist, Results). Responsive (работает на Mac + iPhone Safari).

**Референс:** см. `templates/trip-report-template.html` (создать на базе
2026-07-11 Halkidiki example).

---

### Step 4 — Save via `/trip`

Вызови `/trip` helper с извлечёнными данными:
```bash
python3 /opt/hermes/skills/ceo/trip/scripts/trip.py --save '{
  "destination": "...",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "purpose": "...",
  "agenda": [...],
  "action_items": [...],
  "status": "planned"
}'
```

Если Google Sheets sync failed (`sheet_sync.synced: false`) — НЕ паникуй, см.
`/trip` edge cases. Файл сохранён, данные не потеряны.

---

### Step 5 — Deliver

Отправь user'у:
1. **Короткую сводку** (4–6 строк): что собрал, сколько компаний, следующий шаг
2. **Два файла:**
   - HTML — `MEDIA:/tmp/{destination}_report.html`
   - Markdown — `MEDIA:/tmp/{destination}_trip_report.md`
3. **Путь сохранения:** `/opt/data/logs/trips/YYYY-MM-DD-{slug}.md`

**Формат сводки:**
```
✅ **Готово — командировка {Destination} {Dates}**

📊 **Что внутри:**
- 🏨 Топ-N отелей + контакты
- 🎨 N агентств для партнёрства
- 🛋 N магазинов для benchmark
- 🏭 N производителей (конкуренты)
- 📅 План {dates} (по дням)
- 📋 Checklist подготовки

📂 **Два формата:** HTML (Mac + iPhone) + Markdown

🗂 **Сохранено:** /opt/data/logs/trips/YYYY-MM-DD-{slug}.md
```

---

## Pitfalls

### 1. Pre-flight failure → ошибка ПЕРЕД "Запускаю"

**НЕ говори** «Запускаю research…» если `/web` tools не работают. Сначала
technical check, потом action. См. behavioral guardrail #1 из persona.

### 2. Python command → ВСЕГДА `python3`

На Railway container `python` НЕ существует. См. `/web` references/system-pitfalls.md.

### 3. Контакты менеджеров — НЕ выдумывать

Если на сайте компании нет имени Procurement Manager — НЕ пиши «John Doe,
Procurement Manager». Пиши:
```
**Кого искать:** Procurement Manager / FF&E Director
**LinkedIn:** [Company](link) — найти профили менеджеров
```

### 4. User сказал "не задавай вопросы" → smart defaults

Если user написал «реши сам все задачи мне больше не задавай вопросы» (как в
2026-07-11 session) — НЕ задавай 3 clarifying questions. Делай smart assumptions:
- Даты неясны → вычисли из контекста или используй placeholder "август 2026"
- Язык не указан → английский + русский (где возможно)
- Сегмент не указан → премиум (4–5★, т.к. TANDEM Group = premium brand)

Один уточняющий вопрос ОК если input совсем пустой («командировка»). Но если
есть хоть минимальный контекст — додумай сам.

### 5. Google Sheets sync failed → не show-stopper

`/trip` helper может вернуть `sheet_sync.synced: false` из-за google_api bug.
Это best-effort feature, НЕ критическая ошибка. Файл сохранён, данные не потеряны.
Скажи коротко: «Sync в таблицу не прошёл (google_api bug), но данные сохранены
в файл.» и продолжай.

---

## Example session (2026-07-11 Halkidiki)

**User input (voice):**
> собери мне на халкидиках топ 5 сетей отелей с которыми я бы хотел бы
> встретиться как поставщик мебели потом на 2-3 агентства которые
> специализируются на мебельном на обустройстве мебель отелями агентство
> дизайнерские архитекторские вот в этом приближенном салоннике и вот сюда ближе
> к халкидики вот в этой части и также мебельные магазины которые есть
> представлены для посещения мною и мебельные компании которые производят мебель
> сделай мне такие списки для моей командировки а также план командировки с 8 по
> 16 с 8 по 11 у нас здесь встреча в самом отеле а после уже я должен
> спланировать вот эту поездку всю изучить и сделать анализ и предложения
> обязательно подобрать туда нужно сайтов руководителей имена там менеджеров
> чтобы это было все правдоподобно красиво мне нужно сделать очень хороший
> подробный четкий понятный анализ отчет план потом факты результата и
> предложение для работы группы компаний «Тандем», в которой я управляю.

**Parsed:**
- Destination: Халкидики, Греция
- Dates: 8–16 августа (месяц не указан, assume текущий/следующий)
- Goal: Встречи как поставщик мебели
- Segments: отели (топ-5), агентства (2–3), магазины (для визита), производители
- Industry: мебель, HORECA, contract furniture

**User follow-up:** «реши сам все задачи мне больше не задавай вопросы язык русский отели любые»

**Agent actions:**
1. ✅ Pre-flight check: `/web` доступен (через `python3`), `write_file` OK
2. ✅ Web research: 4 search queries + 7 fetch calls (Eagles, Sani, Ekies, Miraggio, Portes, MEXIL, diMobili, Electra, Kimpa, etc.)
3. ✅ Structured report: Markdown (25KB) + HTML (29KB)
4. ✅ Saved via `/trip`: `/opt/data/logs/trips/2026-07-11-halkidiki-gretsiya.md`
5. ✅ Delivered: короткая сводка + 2 файла (MEDIA:...)

**Output quality:**
- 5 hotels с контактами (email, LinkedIn, кого искать)
- 3 agencies (diMobili, Totimo, Eirini Kelidou)
- 4 showrooms для benchmark
- 5 manufacturers (MEXIL, Electra, Kimpa, Tzoumani, K2)
- План 12–16 августа по дням с тайминг-слотами
- Checklist 9 action items (портфолио, прайсы, авто, emails, etc.)
- Таблица ожидаемых результатов (5 встреч отели, 3 агентства, 2–3 RFQ)

**Time:** ~10 минут research + report generation.

---

## What NOT to do

- ❌ НЕ генерируй fake contacts (имена менеджеров, телефоны, emails если их нет на сайте)
- ❌ НЕ начинай research без pre-flight check
- ❌ НЕ задавай 3+ уточняющих вопросов если user сказал «не задавай вопросы»
- ❌ НЕ используй `python` (only `python3`)
- ❌ НЕ паникуй если Google Sheets sync failed (это best-effort)
- ❌ НЕ выдумывай статистику / цены / даты если их нет в источниках
