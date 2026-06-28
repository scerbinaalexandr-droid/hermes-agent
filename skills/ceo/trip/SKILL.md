---
name: trip
description: |
  Trip / business-travel planning capture for the CEO of TANDEM Group (Moldova
  ↔ Romania, brand sites). Records a STRUCTURED travel plan — destination,
  dates, purpose, agenda/meetings, tasks — as a per-trip file and mirrors it to
  the master Google Sheet (Поездки tab) so trips accumulate as data for later
  analytics (how many trips, where, how long, why).

  Triggered by /trip, a voice memo about an upcoming or planned trip, or
  semantic variants: "планирую поездку", "командировка", "еду в Бухарест",
  "поездка в", "составь план поездки", "trip", "съездить в".

  Different from /diary (daily journal of what happened) and /notes (meeting
  minutes). /trip is forward-looking: a plan for a journey. Voice → Hermes STT
  auto-transcribes before this skill runs. Privacy guard from memory/soul.md applies.
version: 0.1.0
author: alexandr.scerbina
license: MIT
prerequisites:
  files:
    - memory/soul.md
metadata:
  hermes:
    tags: [CEO, Trip, Travel, Planning, Voice, Telegram, Sheets]
    commands: [/trip]
    triggers:
      - "/trip"
      - "планирую поездку"
      - "командировка"
      - "еду в"
      - "поездка в"
      - "составь план поездки"
      - "trip"
---

# Trip — Business-Travel Planner

**Purpose.** Записать план поездки/командировки CEO (куда, когда, зачем, какие
встречи, что подготовить) как структурированный файл + строку в мастер-таблице
Google Sheets (вкладка **Поездки**). Это forward-looking слой: накапливает
данные о поездках для будущей аналитики (частота, география, цели, длительность).
НЕ дублирует `/diary` (журнал прошедшего дня) и `/notes` (протоколы встреч).

**Trigger.** `/trip <text>` в Telegram, голосовое про предстоящую поездку, ИЛИ
semantic фраза. К моменту запуска skill'а ты уже имеешь готовый text (STT
преобразовал голос).

---

## Persona

Прочитай `memory/soul.md` ПЕРЕД любым действием. Privacy guard + premium
tandemcasa.ro tone применяются ко всему, что показываешь и сохраняешь.

---

## Step 0 — Gather context (read-only)

```bash
python skills/ceo/trip/scripts/trip.py --gather
```

Возвращает JSON: `{date, trips_dir, recent_trips}`. Используй только реальные
данные из вывода — если поездка похожа на недавнюю, уточни, новая это или
дополнение к существующей. Ничего не выдумывай.

---

## Step 1 — Parse the plan

Извлеки из текста:

- **destination** (обязателен) — город/страна/объект: "Бухарест", "Брашов,
  квартира", "Кишинёв → Яссы".
- **start_date** / **end_date** — ISO `YYYY-MM-DD` если названы. Относительные
  даты ("в следующий вторник", "10-12 июля") переведи в ISO, опираясь на `date`
  из Step 0. Не уверен в годе — бери текущий. Нет дат — оставь пустыми.
- **purpose** — цель одной фразой ("переговоры по Pharma + осмотр квартиры").
- **agenda** — список пунктов плана/встреч (по дням, если названо).
- **action_items** — что подготовить ДО поездки (брони, документы, договоры).
- **area** — одно из 12 направлений (`memory/areas.md`), если очевидно
  (бизнес-поездка → "CEO / Tandem Group" или "Pharma Project Romania"; отдых →
  "Travel & Recovery"). Не очевидно — оставь пустым.
- **notes** — логистика, бюджет-диапазон, прочее.
- **status** — `planned` (default), `done` если поездка уже состоялась.

Отсутствует поле — оставь пустым, НЕ выдумывай (soul.md §4a/§4c).

**Privacy guard (КРИТИЧНО, soul.md §Privacy guard):**
- Семья → "Супруга" / "Мама" / "Папа" — НИКОГДА реальное имя.
- Незнакомые партнёры → "партнёр X / поставщик Y" (исключение — общеизвестные
  Tandem-context имена).
- Точные суммы → диапазоны ("бюджет 1-2K EUR", не "1470 EUR").
- Banking / passwords / номера паспортов — НЕ сохраняй, попроси переформулировать.

---

## Step 2 — Show draft for approval (CRITICAL — НЕ сохраняй сразу)

Покажи structured preview (scannable за 5 секунд):

```
✈️ **Поездка — {destination} | {start}–{end}**

🎯 {purpose}

📋 **План:**
- {agenda items}

✅ **Подготовить:**
- [ ] {action_items}

[[draft_actions]]
```

**Кнопки черновика (hands-free, за рулём):** ВСЕГДА заканчивай черновик строкой
`[[draft_actions]]` на отдельной строке — гейтвей превращает её в кнопки
✅ Сохранить · ✏️ Дополнить · 🗑 Удалить под сообщением. Реакция на них:
- приходит **«Сохрани текущий черновик…»** → выполни Step 3 (сохрани) для показанного черновика;
- приходит **«Отмени текущий черновик…»** → НЕ сохраняй, ответь «🗑 Черновик отменён»;
- юзер диктует ещё (дополнение) → допиши в черновик и снова покажи превью с `[[draft_actions]]`.

**INCREMENTAL CAPTURE** (CEO диктует частями):
- Показывай running list после каждого пункта, эхо последнего — подтверди
  распознавание, спрашивай "Продолжай — или готово?".

**AUTO-SAVE — план НЕ имеет права потеряться (инцидент 2026-06-06):**
Накопленный план живёт только в контексте чата, пока не сохранён.
1. Битый input во время накопления → СНАЧАЛА сохрани текущую версию (Step 3),
   ПОТОМ уточняй. Добавь: `💾 Авто-сохранил текущий план — ничего не потеряется.`
2. Смена темы при несохранённом плане → СНАЧАЛА Step 3 молча, упомяни строкой
   `💾 «{destination}» авто-сохранён`, потом обрабатывай новое сообщение.

НИКОГДА не оставляй накопленное несохранённым в ожидании подтверждения.

---

## Step 3 — Save via helper

```bash
python skills/ceo/trip/scripts/trip.py --save '<JSON>'
```

JSON shape:
```json
{
  "destination": "Бухарест, Румыния",
  "start_date": "2026-07-10",
  "end_date": "2026-07-12",
  "purpose": "Переговоры по Pharma Project + осмотр квартиры Brasov",
  "agenda": ["10.07 встреча с поставщиком A", "11.07 осмотр квартиры Brasov"],
  "action_items": ["Подготовить договор", "Забронировать отель"],
  "area": "Pharma Project Romania",
  "status": "planned",
  "notes": "бюджет 1-2K EUR"
}
```

Helper пишет файл `logs/trips/YYYY-MM-DD-<slug>.md` (prod: `/opt/data/logs/trips/`)
и зеркалит строку в Sheet (вкладка Поездки). Возвращает JSON:
`{saved_path, destination, action_items_count, sheet_sync}`.

- `sheet_sync.synced == true` — поездка попала в таблицу.
- `sheet_sync.synced == false` — файл сохранён, но не в Sheet (best-effort);
  скажи об этом одной строкой, НЕ выдумывай успех.
- Helper вернул `{"error": ...}` — surface error дословно, НЕ создавай fake confirmation.

---

## Step 4 — Acknowledge

≤ 4 строки, используй ТОЛЬКО `saved_path` из вывода helper'а:

```
✅ **Поездка записана — {destination}**

📂 {saved_path}
📊 {action_items_count} задач к подготовке (если >0)
📈 В таблице Поездки (если sheet_sync.synced)
```

---

## Edge cases

| Случай | Поведение |
|---|---|
| Короткий непонятный input («поездка») | Спроси одно уточнение: «Куда и когда едем? Можно голосом — продиктуй цель и даты.» |
| Нет дат | Сохраняй без дат (поля пустые), не выдумывай. «Дней» в таблице останется пустым. |
| Поездка уже состоялась | `status: "done"` — запиши как факт. Для разбора встреч в поездке используй `/notes`/`/diary`. |
| `--save` вернул `{"error": ...}` | Surface error дословно, НЕ создавай fake confirmation. |
| User просит забронировать/купить билет | Phase 3 (действия от имени user'а). Mildly decline, залогируй как action_item «забронировать …». План уже сохранён. |
| User просит отчёт «сколько я ездил» | Данные копятся в Sheet (вкладка Поездки) — это будущая аналитика. Не выдумывай цифры; скажи, что данные накапливаются для разбора. |

---

## What NOT to do

- ❌ НЕ пишет в `memory/*.md` — guard.py блокирует. Только `logs/trips/`.
- ❌ НЕ бронирует, не покупает, не отправляет письма от имени user'а (Phase 3).
- ❌ НЕ выдумывает даты, суммы, имена, дедлайны (soul.md §4a/§4c) — нет данных,
  оставь поле пустым и скажи честно.
- ❌ НЕ дублирует `/diary` (журнал дня) и `/notes` (протоколы встреч) — `/trip`
  это план поездки.
- ❌ НЕ генерирует аналитические сводки по поездкам с выдуманными цифрами — это
  будущая cron-фича; сейчас данные только накапливаются.
