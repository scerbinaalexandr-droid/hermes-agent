---
name: capture
description: |
  Capture a thought, task, decision, insight, or meeting recap from voice memo
  or text into the right memory file. Auto-invoked when the user types
  /capture <text> in Telegram, sends a voice memo with the [тип] template, or
  uses semantic variants ("zapisat'", "запомни", "сохрани", "capture this").
  Routes by [тип]:
    meeting / recap → memory/daily_log.md (today's entry)
    decision        → memory/decisions.md (with full Date/Reason/Status shape)
    insight         → memory/memory.md::Current Strategic Themes (in-place)
    task            → memory/memory.md::Active Priorities (in-place bullet)
  Applies privacy guard from memory/soul.md (pseudonymize unknown partners,
  ranges for prices, no NDA-risk raw quotes).
version: 0.1.0
author: alexandr.scerbina
license: MIT
prerequisites:
  files:
    - memory/soul.md
    - memory/memory.md
    - memory/daily_log.md
    - memory/decisions.md
metadata:
  hermes:
    tags: [CEO, Capture, Voice, Memory, Telegram]
    commands: [/capture]
    triggers:
      - "/capture"
      - "запомни"
      - "сохрани"
      - "capture this"
      - "zapisat'"
---

# Capture — Voice Memo / Thought Router

**Purpose.** Поймать мысль / задачу / решение / инсайт / recap встречи и
положить в правильный файл memory без когнитивной нагрузки на user'а.
Per blueprint §06 + memory/soul.md::Voice memo template + UX rules.

**Trigger.** `/capture <text>` ИЛИ voice memo ИЛИ просто фраза в чате
(когда сообщение выглядит как thought/task/decision без явной команды).

## Voice-first flow (DEFAULT)

CEO диктует голосом — НЕ требуй template. **Auto-detect** и покажи черновик.

---

## Persona

Load `memory/soul.md` first. Apply privacy guard и voice memo template
strictly.

---

## Step 1 — Parse intent (auto)

Если user явно дал template `[тип]: ... [контекст]: ... [содержание]: ...` — забери поля как есть.

**Иначе (default)** — auto-detect из free-form текста / транскрипта voice:

1. **Тип** (priority order, первое совпадение wins):
   - "решил / решили / договорились / decision / выбрал" → `decision`
   - "встретился / встреча / созвон / meeting / call / поговорил с" → `meeting`
   - "итоги встречи / recap / summary / резюме" → `recap`
   - "сделать / нужно / todo / напомнить / задача" → `task`
   - всё остальное про мысль / идею / наблюдение → `insight`

2. **Контекст** — first proper noun или project name (Tandem Casa, Kitchen by Tandem, Brasov, Pharma RO, Lean Kitchen, etc.). Если нет — `(unspecified)`.

3. **Содержание** — основной message. **Apply privacy guard** из `soul.md`:
   - **семейные имена** (имя супруги, родителей) → ВСЕГДА "Супруга", "Мама", "Папа"
   - незнакомые партнёры → "партнёр X" / "поставщик Y" (исключения: Живко и др. tandem-context-known names)
   - точные цены договоров → диапазоны
   - banking / passwords / medical raw → НЕ сохраняй, спроси переформулировать

## Step 2 — Show draft (CRITICAL — НЕ сохраняй сразу)

Покажи user'у **черновик распознанного** с inline кнопками-like prompts:

```
🎤 Распознал:
*Тип:* {type}
*Контекст:* {context}
*Содержание:* {content_after_redaction}
→ Сохранить в `{target_file}::{target_section}`

Подтверди: «✅ да» / «✏️ поправь: <что>»  (или просто `/capture` снова с новым текстом)
```

Дай ~30 секунд (или до следующего сообщения user'а). Если user ответил:
- **«да» / «ok» / «✅» / «сохрани» / эмодзи галочки** → выполни сохранение (Step 3)
- **«поправь: тип task»** / **«нет, это task»** → re-route к новому типу, покажи новый draft
- **«отмена» / «cancel» / «нет»** → НЕ сохраняй, ответь «отменено» одной строкой
- **новое сообщение про другое** → старый capture отменён без сохранения

## Step 3 — Save (после явного approve)

---

Команда:
```bash
python skills/ceo/capture/scripts/capture.py --type <тип> --context "<context>" --content "<content>"
```

Helper использует `route_capture()` из `skills/ceo/_lib/memory.py`:

| Type | Target file | Action |
|---|---|---|
| `meeting` / `recap` | `memory/daily_log.md` | Append today's `### Capture (HH:MM) — <тип>` block |
| `decision` | `memory/decisions.md` | Append entry с Date/Decision/Reason/Expected/Review/Status=pending |
| `insight` | `memory/memory.md::Current Strategic Themes` | In-place append bullet |
| `task` | `memory/memory.md::Active Priorities (this week)` | In-place append `- [ ] ...` bullet |

Returns `{file, action, snippet}`.

---

## Step 4 — Acknowledge (после save)

≤2 строки + next-steps:

```
✅ {file}::{section} ← {2-3 word summary}

Что дальше? · /brief · /capture · /projects {if context был project}
```

**НЕ** показывай шаблон structured input — user уже понимает что voice-first работает.

---

## Edge cases

| Случай | Поведение |
|---|---|
| User дал template но `[тип]` не из списка | Reject. Reply: «Тип `X` не поддерживается. Доступно: meeting, decision, insight, recap, task. Перешли заново.» |
| `[содержание]` пустое после template | Reject с инструкцией дозаполнить. |
| `decision` без `[контекст]` | Сохрани с placeholder reason="(captured via /capture — fill in context)". Помечай в confirm. |
| `task` без явных action verbs | Сохрани как есть, но добавь в confirm: «task без явного действия — открой memory/memory.md и добавь deadline/owner если нужно.» |
| Privacy violation detected (e.g., user написал bank account, password) | НЕ сохраняй. Reply: «⚠ Обнаружены sensitive данные (password / bank / medical). Не сохранил по privacy guard из soul.md. Перешли без них.» |
| Voice memo обрезался / неполный | Сохрани что есть, помечай в confirm: «Memo выглядит неполным — повторно надиктуй?» |

---

## What NOT to do

- ❌ НЕ создавай новые проекты в projects.md через `/capture` — это для weekly review pathway (or future skill).
- ❌ НЕ модифицируй user.md / soul.md (manual-only).
- ❌ НЕ дублируй уже существующий task / insight (если идентичный bullet есть в memory.md, скажи user'у).
- ❌ НЕ обогащай контент LLM-генерацией — это `capture`, не «улучшение». Сохрани максимально близко к тому что user сказал (после privacy redaction).

---

## Extended Workflows (2026-06-05)

User requested two parallel collection systems. See `references/diary-and-protocol-workflow.md` for full spec:

1. **Daily Diary:** Continuous collection → weekly (Friday) + quarterly reports
2. **Excel Meeting Protocols:** On-demand capture → draft approval → email delivery to scerbinaalexandr@gmail.com

Both systems extend the core `/capture` flow with automated reporting and formal output formats.
