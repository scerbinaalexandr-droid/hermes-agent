---
name: diary
description: |
  Daily diary + structured meeting-protocol capture for the CEO of TANDEM Group.
  Two flows in one skill:
    1. DAILY DIARY (continuous) — CEO dictates throughout the day (voice or text);
       each input becomes a timestamped entry in today's diary file. Builds the
       long-term historical record for later weekly/quarterly review.
    2. MEETING PROTOCOL (on-demand) — structured minutes with participants /
       decisions / action items / summary, appended to the same daily file.
  Triggered by /diary, a voice memo about the day, or semantic variants:
  "запиши день", "дневник", "запиши протокол встречи", "diary", "что было сегодня".

  Different from /capture (routes thoughts/decisions into memory/*.md) and from
  /notes (saves standalone note files under logs/notes/). /diary keeps an
  append-only per-day journal under logs/diary/YYYY-MM-DD.md.

  Voice → Hermes STT auto-transcribes before this skill runs.
  Text → used as-is. Privacy guard from memory/soul.md applies.
version: 0.1.0
author: alexandr.scerbina
license: MIT
prerequisites:
  files:
    - memory/soul.md
metadata:
  hermes:
    tags: [CEO, Diary, Journal, Protocols, Voice, Telegram]
    commands: [/diary]
    triggers:
      - "/diary"
      - "запиши день"
      - "дневник"
      - "что было сегодня"
      - "запиши протокол встречи"
      - "diary"
---

# Diary — Daily Journal + Meeting Protocol

**Purpose.** Вести непрерывный дневник CEO (что сделано, встречи, решения,
наблюдения) и формальные протоколы встреч — append-only по дням в собственном
пространстве `logs/diary/`. Это исторический слой для будущих weekly/quarterly
обзоров и аналитики компетенций/опыта. НЕ заменяет `/capture` (быстрые мысли в
memory) и НЕ дублирует `/notes` (отдельные файлы заметок).

**Trigger.** `/diary <text>` в Telegram, voice memo про день, ИЛИ semantic
фраза. К моменту запуска skill'а ты уже имеешь готовый text (STT преобразовал
голос). Два режима, оба append'ятся в `logs/diary/YYYY-MM-DD.md`:
- **entry** — обычная дневниковая запись (default)
- **protocol** — структурированный протокол встречи

---

## Persona

Прочитай `memory/soul.md` ПЕРЕД любым действием. Privacy guard + premium
tandemcasa.ro tone применяются ко всему, что показываешь и сохраняешь.

---

## Step 0 — Gather context (read-only)

Перед показом черновика подтяни контекст дня (сколько записей уже есть сегодня,
последние дни) — чтобы append'ить, а не дублировать:

```bash
python skills/ceo/diary/scripts/diary.py --gather
```

Возвращает JSON: `{date, weekday, diary_file, today_blocks, today_diary, recent_daily_log}`.
Используй только реальные данные из этого вывода — ничего не выдумывай.

---

## Step 1 — Determine kind & parse

Авто-определи режим по содержанию (первое совпадение wins):

- **protocol** — "встреча / совещание / созвон / протокол / meeting / call /
  поговорили / договорились на встрече" + есть участники/решения.
- **entry** (default) — всё остальное: что сделал за день, наблюдение, итог дня,
  настрой, энергия.

**Для entry** извлеки: `content` (основной текст, обязателен), опц. `context`
(проект / тема), опц. `energy`, опц. `mood`.

**Для protocol** извлеки: `topic` (4-7 слов, обязателен), `participants`,
`decisions`, `action_items` (owner + deadline если названы), `summary`,
`raw_text` (оригинал для архивности). Отсутствует поле — оставь пустым, НЕ
выдумывай (soul.md §4a/§4c).

**Privacy guard (КРИТИЧНО, soul.md §Privacy guard):**
- Семья → "Супруга" / "Мама" / "Папа" — НИКОГДА реальное имя
- Незнакомые партнёры → "партнёр X / поставщик Y" (исключение — общеизвестные
  Tandem-context имена, напр. "Живко")
- Точные цены договоров → диапазоны ("400-500K MDL", не "470K MDL")
- Banking / passwords / медицина — НЕ сохраняй, попроси переформулировать

---

## Step 2 — Show draft for approval (CRITICAL — НЕ сохраняй сразу)

Покажи structured preview, premium+functional tone (scannable за 5 секунд):

**Для entry:**
```
📝 **Дневник | {date} {HH:MM}**

{content_after_redaction}

{«Энергия: X/10 · Настрой: …» — только если названо}

✅ Записать? | ✏️ Поправь | 🗑 Не надо
```

**Для protocol:**
```
⬛️ **{topic} | {date}**

🟡 **Ключевое решение**
{decisions[0] if exists}

📊 **Задачи:**
- [ ] {action_item}

✅ Сохранить протокол? | ✏️ Поправь | 🗑 Не надо
```

**INCREMENTAL CAPTURE** (CEO диктует частями между делами):
- Показывай running list после каждого пункта, нумеруй задачи.
- Эхо последнего пункта — подтверди распознавание.
- Спрашивай "Продолжай — или готово?" после каждого добавления.

**AUTO-SAVE — запись НЕ имеет права потеряться (инцидент 2026-06-06):**
Накопленный дневник/протокол живёт только в контексте чата, пока не сохранён.

1. **Битый input во время накопления** (голосовое не распозналось): СНАЧАЛА
   сохрани текущую версию (Step 3), ПОТОМ задавай уточняющий вопрос. Добавь
   строку: `💾 Авто-сохранил текущие {N} пунктов — ничего не потеряется.`
2. **Смена темы** (сообщение НЕ по записи, а несохранённое есть): СНАЧАЛА Step 3
   молча, упомяни одной строкой `💾 «{topic}» авто-сохранён ({N} пунктов)`,
   потом обрабатывай новое сообщение.
3. **Нет ответа на «Продолжай — или готово?»** — следующее не по теме сообщение
   считай «готово», сохрани (правило 2).

НИКОГДА не оставляй накопленное несохранённым в ожидании подтверждения.
Подтверждение управляет финальной версией — черновик сохраняется всегда.

---

## Step 3 — Save via helper

```bash
python skills/ceo/diary/scripts/diary.py --save '<JSON>'
```

JSON shape (entry):
```json
{"kind": "entry", "content": "...", "context": "Tandem Casa", "energy": "7/10", "mood": "..."}
```

JSON shape (protocol):
```json
{
  "kind": "protocol",
  "topic": "TANDEM Casa — кампания осень 2026",
  "participants": ["Александр", "партнёр X"],
  "decisions": ["..."],
  "action_items": ["Александр / 03.06 — ..."],
  "summary": "...",
  "raw_text": "..."
}
```

Helper append'ит блок в `logs/diary/YYYY-MM-DD.md` и возвращает JSON:
`{saved_path, kind, date, action_items_count}`. На prod путь — `/opt/data/logs/diary/`.
Если helper вернул `{"error": ...}` — surface error к user, НЕ создавай fake
confirmation.

---

## Step 4 — Acknowledge

≤ 4 строки, tandemcasa.ro format. Используй ТОЛЬКО `saved_path` из вывода helper'а:

```
✅ **Записано — {topic|"дневник"}**

📂 {saved_path}
📊 {action_items_count} задач зафиксированы (если protocol и >0)
```

---

## Edge cases

| Случай | Поведение |
|---|---|
| Короткий непонятный input («запиши») | Спроси одно уточнение: «Что записываем — запись дня или протокол встречи? Можно голосом.» |
| Voice memo на 5+ минут | НЕ обрезай — сохраняй raw + structured. Action items в приоритете. |
| Несколько записей за день | Все append'ятся в один файл `{date}.md` под отдельными `### Diary/### Protocol (HH:MM)` блоками — overwriting нет. |
| Запись встречи без консента (MD/RO double-consent law) | Спроси: «Собеседники в курсе записи? ✅ да / ❌ нет / 📝 redact имена». Если «нет» — НЕ сохраняй participants, только summary. |
| `--save` вернул `{"error": ...}` | Surface error дословно, НЕ создавай fake confirmation. |
| User просит еженедельный/квартальный отчёт по дневнику | Это будущая cron-фича (Phase 2+). Сейчас — предложи залогировать как TODO, не генерируй сводку с выдуманными цифрами. |
| User просит отправить протокол на email | Phase 3 (отправка от имени user'а). Mildly decline, предложи залогировать TODO. Протокол уже сохранён в `logs/diary/`. |

---

## What NOT to do

- ❌ НЕ пишет в `memory/*.md` — guard.py блокирует. Только `logs/diary/`.
  (Spec упоминал `memory/diary/`, но эта зона заблокирована guard'ом — Phase-1
  boundary побеждает, дневник живёт под `logs/`.)
- ❌ НЕ генерирует email-черновики / follow-up / КП (Phase 3).
- ❌ НЕ запускает research/конкурентов и не отправляет сообщения от имени user'а.
- ❌ НЕ выдумывает цифры, KPI, цитаты, имена, дедлайны (soul.md §4a/§4c) — если
  данных нет, оставь поле пустым и скажи об этом честно.
- ❌ НЕ дублирует `/capture` (быстрые мысли в memory) и `/notes` (отдельные
  файлы заметок) — `/diary` это append-only журнал по дням.
- ❌ НЕ генерирует weekly/quarterly сводки внутри skill'а без реальных данных —
  это отдельная cron-фича будущей фазы.
