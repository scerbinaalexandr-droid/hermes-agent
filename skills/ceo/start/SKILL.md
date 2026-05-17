---
name: start
description: |
  /start alias to /menu. Telegram bots conventionally respond to /start as
  entry point. Hermes doesn't have a default /start handler — this skill fills
  the gap. Just shows the same menu as /menu skill.
version: 0.1.0
author: alexandr.scerbina
license: MIT
metadata:
  hermes:
    tags: [CEO, Start, Entry, Telegram, Alias]
    commands: [/start]
    triggers:
      - "/start"
      - "/help"
---

# Start — Telegram bot entry alias

When user types `/start` (Telegram convention) or `/help` — **invoke the
`menu` skill** for full main menu. This skill exists so `/start` is not
"Unknown command".

## Output

Behave **identically** to `/menu` skill — load `skills/ceo/menu/SKILL.md`
instructions and render the same main-menu output. Можно prepend единственную
строку приветствия для первого `/start`:

```
Привет, Александр. Hermes готов.

[затем — содержимое /menu skill output]
```

## What NOT to do

- ❌ Не дублируй menu content в этом файле — single source of truth = `menu/SKILL.md`
- ❌ Не показывай tutorial / onboarding — это reference card, не doc
