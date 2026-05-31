---
name: notes
description: |
  Structured note / meeting protocol / decision log capture for the CEO of
  TANDEM Group. Triggered when the user types /notes, sends a voice memo with
  meeting context, photographs a printed protocol, or uses semantic variants:
  "запиши встречу", "запиши протокол", "сохрани заметку", "сохрани протокол",
  "noted", "meeting notes", "запиши совещание".

  Different from /capture (which routes thoughts/decisions to memory/*.md):
  /notes saves STRUCTURED meeting/observation artifacts to its own space
  (logs/notes/), with explicit participants / decisions / action items /
  summary fields. Surfaces in Obsidian ALEX21_VAULT/03 — Notes/ via daily
  backup pipeline (sync 1x/day, see launchd plist hermes-notes-sync.plist).

  Voice → Hermes STT auto-transcribes before this skill runs.
  Photo → Hermes Claude Vision auto-extracts text before this skill runs.
  Text → used as-is.

  Privacy guard from memory/soul.md applies (Супруга, диапазоны цен, etc.).
version: 1.0.0
author: alexandr.scerbina
license: MIT
prerequisites:
  files:
    - memory/soul.md
metadata:
  hermes:
    tags: [CEO, Notes, Meetings, Protocols, Voice, Telegram, Obsidian]
    commands: [/notes]
    triggers:
      - "/notes"
      - "запиши встречу"
      - "запиши протокол"
      - "запиши совещание"
      - "сохрани заметку"
      - "сохрани протокол"
      - "meeting notes"
      - "noted"
      - "protocol"
---

# Notes — Structured Meeting / Protocol Capture

**Purpose.** Поймать встречу, протокол, голосовую заметку или фото-протокол
и сохранить в **структурированном виде** (участники / решения / action items
/ summary) в личное notes-пространство. НЕ заменяет /capture (который кладёт
быстрые мысли в memory/*). НЕ дублирует /coach (коуч-сессии).

**Trigger.** `/notes` в Telegram, voice memo контекстом встречи, фото
протокола, ИЛИ semantic фраза. Hermes уже:
- транскрибирует voice → текст (STT)
- извлекает текст из фото (Claude Vision)

К моменту этого скилла ты уже имеешь готовый text для structuring.

---

## Persona

Прочитай `memory/soul.md` ПЕРЕД любым действием. Privacy guard + tone применяются.

---

## Step 1 — Receive raw input

LLM получает один из:
- **Text** — прямое сообщение (`/notes <text>` или free-form trigger phrase + content)
- **Transcript** — от voice memo (Hermes уже преобразовал)
- **Vision extraction** — от фотографии (Claude Vision уже извлёк текст)

Если контент короткий и непонятный («запиши») — спроси одно уточнение:
*"Что записываем? Дай context — встреча с кем? Тема? Можно голосом."*

---

## Step 2 — Parse structure

Извлеки следующие поля. Если поле отсутствует — оставь `null`/`[]`, НЕ выдумывай.

| Поле | Описание | Пример |
|---|---|---|
| `topic` | 4-7 слов суть встречи / заметки | "TANDEM Casa — кампания осень 2026" |
| `meeting_type` | meeting / call / personal-note / observation / decision-log / protocol | "meeting" |
| `participants` | список людей (применить privacy guard) | ["Александр", "Анна (Tandem Casa CRM)", "партнёр X"] |
| `date` | дата события (если не указана — today) | "2026-05-31" |
| `decisions` | список принятых решений с обоснованием | ["Запускаем кампанию 15 сентября — согласовано с production"] |
| `action_items` | список action items с owner + deadline | ["Александр / 03.06 — финальный бриф маркетингу"] |
| `summary` | 3-5 предложений общего смысла | "..." |
| `raw_text` | оригинальный transcript / OCR text (для архивности) | (всё что пришло) |

**Privacy guard (КРИТИЧНО):**
- Семья (Супруга, Мама, Папа) — НИКОГДА не сохраняй имя
- Незнакомые партнёры → "партнёр X / поставщик Y" (исключения — общеизвестные имена в Tandem контексте)
- Точные цены договоров → диапазоны ("400-500K MDL", не "470K MDL")
- Banking, passwords, медицина — НЕ сохраняй вообще, попроси переформулировать

---

## Step 3 — Show draft for approval (CRITICAL — НЕ сохраняй сразу)

Покажи в чате compact preview ≤ 1500 char:

```
📝 *Notes draft*

*{topic}* — {date} · {meeting_type}
*Участники:* {participants}

*Решения:*
- ...

*Action items:*
- ...

*Summary:* {summary}

---
Сохранить? ✅ да / ✏️ поправь {field} / 🗑 не надо
```

Если user просит правку — обнови соответствующее поле и покажи снова.
Если user соглашается — переход к Step 4. Если отменяет — ничего не сохраняй.

---

## Step 4 — Save via helper

```bash
python /opt/data/scripts/notes_log.py --save '<JSON>'
```

JSON shape:
```json
{
  "topic": "TANDEM Casa — кампания осень 2026",
  "meeting_type": "meeting",
  "date": "2026-05-31",
  "participants": ["Александр", "Анна (TC CRM)"],
  "decisions": ["..."],
  "action_items": ["..."],
  "summary": "...",
  "raw_text": "..."
}
```

Helper создаёт два файла:
- `/opt/data/logs/notes/YYYY-MM-DD/HHMM-<slug>.md` — сама заметка
- `/opt/data/logs/notes/YYYY-MM-DD-index.md` — daily index (append)

И возвращает JSON: `{"saved_path": "...", "index_path": "...", "obsidian_eta": "tomorrow 06:00 EEST after launchd sync"}`.

---

## Step 5 — Acknowledge

≤ 4 строки:

```
✅ Сохранено: {topic}
{saved_path}
Появится в Obsidian ALEX21_VAULT/03 — Notes/{YYYY-MM-DD}/ — завтра утром.
{N} action items зафиксированы.
```

---

## Edge cases

| Случай | Поведение |
|---|---|
| Фото рукописного протокола (cyrillic) | Claude Vision возвращает best-effort. Помечай `accuracy: "manual_review_recommended"` в notes если очевидны ошибки распознавания. |
| Voice memo на 5+ минут | НЕ обрезай — saving raw + structured. Action items имеют приоритет. |
| Запись встречи с партнёром без консента (MD/RO double-consent law) | Спроси: *"Подтверди — собеседники в курсе записи? AI structuring создаёт хранимую копию переговоров. ✅ да / ❌ нет / 📝 redact имена"*. Если "нет" — НЕ сохраняй participants, только summary. |
| User пытается сохранить banking/passwords/health | Откажись: "Эти данные не идут в notes. Положи в защищённое место (1Password)." |
| User дублирует note (тот же topic за день) | Сохрани оба, не overwriting. Имена файлов уникальны по HHMM. |
| `--save` падает с error | Surface error к user, НЕ создавай fake confirmation. |

---

## What this does NOT do

- ❌ НЕ пишет в memory/*.md (это /capture зона)
- ❌ НЕ запускается как cron (notes требуют user input)
- ❌ НЕ синхронит в realtime — sync через daily backup + launchd на mac
- ❌ НЕ работает с встроенными images без extraction (только plain text после Vision/STT)
- ❌ НЕ заменяет /capture для quick thoughts — там не нужна вся структура

---

## Setup (one-time for Obsidian sync)

После first deploy — установи на mac launchd plist чтобы notes синхронились
в Obsidian vault. Файл `~/.config/hermes/hermes-notes-sync.plist` + команда
`launchctl load ...` — будет дан separately. Без него notes остаются только в
GitHub backup repo (доступны через clone, но не в Obsidian iPhone).
