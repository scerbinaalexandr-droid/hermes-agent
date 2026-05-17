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
Per blueprint §06 + memory/soul.md::Voice memo template.

**Trigger.** `/capture <text>` или voice memo с шаблоном.

---

## Persona

Load `memory/soul.md` first. Apply privacy guard и voice memo template
strictly.

---

## Step 1 — Parse intent

Voice memo template:
```
[тип]: meeting | decision | insight | recap | task
[контекст]: с кем / о чём / какой проект
[содержание]: суть
```

Если user явно дал template — забери поля.
Если free-form (`/capture <text>` или просто текст без template):

1. **Определи `тип`** по эвристикам:
   - содержит "решил / decided / decision" → `decision`
   - содержит "встреча / meeting / созвон / call" → `meeting`
   - содержит "сделать / todo / нужно / напоминание" → `task`
   - содержит "понял / insight / идея / обратил внимание" → `insight`
   - содержит "итоги / recap / summary встречи" → `recap`
   - иначе → `insight` (default safe choice)

2. **Извлеки `контекст`** — кто / о чём / какой проект (если упоминается). Если нет — `(unspecified)`.

3. **Извлеки `содержание`** — суть. **Apply privacy guard:**
   - имена незнакомых партнёров → "партнёр X", "поставщик Y", "клиент Z" (исключения: общеизвестные имена в Tandem context — Живко и пр.)
   - точные цены договоров → диапазоны или "(see external doc)"
   - чужие цитаты с встреч → переформулируй как "своё суждение"

4. **Когда `тип` определён эвристикой (не явно дан)** — подтверди user'у в финальном reply: «Записал как `<тип>`. Если не то — поправь.»

---

## Step 2 — Save

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

## Step 3 — Confirm to user

Короткий ответ:

```
✅ {file} ← {action}
   "{snippet shortened to ≤120 char}"

   Tip: для structured input используй template:
   [тип]: ...
   [контекст]: ...
   [содержание]: ...
```

`Tip:` показывай ТОЛЬКО если user слал free-form (не template). После 3 free-forms подряд (per soul.md rule) — спроси «нужна другая структура?»

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
