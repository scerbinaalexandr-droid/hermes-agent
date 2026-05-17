---
name: find
description: |
  Search в CEO memory (memory/*.md + logs/daily/ + logs/weekly/ + Hermes
  session_search). Используй ВСЕГДА когда user спрашивает про past события /
  решения / встречи: "когда мы решили X", "что я говорил про Y", "найди про
  Tandem Casa Q3", "что было на встрече с Живко", "/find <query>".
  Returns 1-5 most relevant matches с датой + контекстом.
version: 0.1.0
author: alexandr.scerbina
license: MIT
prerequisites:
  files:
    - memory/decisions.md
    - memory/daily_log.md
    - memory/weekly_review.md
metadata:
  hermes:
    tags: [CEO, Search, Memory, Retrieval]
    commands: [/find]
    triggers:
      - "/find"
      - "найди"
      - "когда мы"
      - "что я говорил"
      - "что я решил"
      - "что было"
      - "помнишь про"
      - "search"
---

# Find — Memory Search

**Purpose.** Retrieval-first для CEO. Когда CEO спрашивает про прошлое — НЕ
выдумывай, ищи в реальной памяти. Hermes имеет `memory` + `session_search`
tools — используй их.

**Trigger.** `/find <query>` или semantic queries: "найди про X", "когда мы
решили Y", "что было на встрече с Z".

## Step 1 — Determine search scope

Извлеки **главные keywords** из запроса:
- Имя project (Tandem Casa, Kitchen, Brasov, Pharma RO, etc.)
- Имя partner / supplier (Живко, поставщик X)
- Тема (cashflow, marketing, IT, monthly review)
- Дата / период ("на прошлой неделе", "в апреле", "Q3")

Если query очень общий («что было важного») → fallback: top 5 decisions + last
3 weekly summaries.

## Step 2 — Multi-source search

В порядке приоритета:

1. **`memory/decisions.md`** — главный source для "что мы решили". Grep по
   keywords в Decision/Reason/Linked Projects полях.
2. **`memory/projects.md`** — для project-specific queries (status, next
   actions, notes).
3. **`memory/daily_log.md`** + **`logs/daily/*.md`** (recent 30 days) — для
   "когда было / встреча / capture".
4. **`memory/weekly_review.md`** + **`logs/weekly/*.md`** — для "на неделе W /
   в апреле".
5. **Hermes `session_search` tool** — для Telegram conversations history
   (voice memos, free-form messages user'а).
6. **`memory/risks.md`** — для risk-related queries.
7. **`memory/memory.md`** — для current strategic themes.

Стоп при первых 5 strong matches. Не вычитывай всё.

## Step 3 — Format result (compact)

```
🔍 Найдено по «{query}»:

1. *{date}* — {file}::{section}
   {1-2 строки relevant snippet}

2. *{date}* — {file}::{section}
   {snippet}

3. *{date}* — Telegram session ({platform mode})
   {snippet — privacy redacted}

...

(показано {N} из {M} matches — уточни query или `/find <query> all`)

Что дальше? · /capture — записать новое · /projects — статусы
```

Если matches=0:
```
🔍 По «{query}» ничего не нашёл в памяти.

Может быть:
- Другой формулировкой? («Tandem Casa» вместо «TC»)
- В Obsidian (внешняя память — я туда не лезу)?
- Запиши сейчас через /capture, если это важно
```

## Edge cases

| Случай | Поведение |
|---|---|
| Query с именем партнёра | Search как есть; в output redact unknown names на `партнёр X` |
| Query с чувствительной темой (банк, медицина) | Откажи: «Эта тема не в моей памяти (privacy guard)» |
| Query на дату из будущего | Reply: «{date} ещё не наступила. Не вижу future» |
| Query слишком общий («что было?») | Default fallback (top decisions + last weekly) с подсказкой уточнить |

## What NOT to do

- ❌ Не выдумывай matches. Если sources empty → честно «не нашёл».
- ❌ Не показывай raw snippets с sensitive content — apply privacy redaction.
- ❌ Не вычитывай все 30 days `logs/daily/` если первый source дал answer.
- ❌ Не привязывайся к точному wording — search semantic-y (Hermes session_search умеет FTS5).
