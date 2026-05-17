---
name: menu
description: |
  CEO main menu — main entry point для @Hermes_Alex21_bot. Показывает все
  доступные команды одним сообщением с краткими описаниями. User не должен
  запоминать /brief, /evening, /week, etc. — `/menu` всегда напомнит.
  Auto-invoked when user types /menu, /start, /help, "что ты умеешь",
  "что я могу", "помощь", "menu".
version: 0.1.0
author: alexandr.scerbina
license: MIT
metadata:
  hermes:
    tags: [CEO, Menu, Entry, Telegram]
    commands: [/menu]
    triggers:
      - "/menu"
      - "что ты умеешь"
      - "что я могу"
      - "помощь"
      - "menu"
      - "help"
---

# CEO Menu — main entry point

**Purpose.** CEO не должен помнить 7+ slash-команд. `/menu` — single point of
reference. Показывает все CEO commands со one-line описанием и use case.

**Trigger.** `/menu`, `/start`, `/help`, "что ты умеешь", "что я могу".

## Output (Telegram, ≤ 1500 char, на русском)

```
🤖 *Hermes — твой Executive OS*

*Каждый день:*
☀️ /brief — утренний фокус (auto в 07:30 EEST)
🌙 /evening — вечерний recap, голосом (auto-prompt 21:30)
🎤 /capture — записать мысль / задачу / решение (голосом — auto)

*Еженедельно:*
📅 /week — weekly CEO review, голосом (auto Sun 18:00)

*Просмотр:*
📋 /projects — активные проекты (опц. /projects high)
⚠ /risks — топ риски (опц. /risks high)
🔍 /find <запрос> — поиск по памяти (что мы решили / когда было)

*Утилиты:*
⏰ /remind <когда> <что> — напоминание (через 3ч / завтра в 10:00)
💾 /backup — manual backup (Stage 7, in progress)

---

💡 *Голосовые memo работают везде* — диктуй свободной формой, я разбираю
сам и показываю черновик для подтверждения.

🛡 *Privacy:* семейные имена → "Супруга" / "Мама" / "Папа"; цены договоров → диапазоны.

Что хочешь сделать сейчас?
```

## Edge cases

| Случай | Поведение |
|---|---|
| Первый раз user пишет `/start` | Покажи menu + добавь приветственную строку «Привет, Александр. Hermes готов.» |
| Telegram payload limit | ≤4096 char — текущий menu helps stay well under |
| User спрашивает «что нового?» | Покажи menu + «Стейдж 6 cron активен с 2026-05-17» |

## What NOT to do

- ❌ Не показывай вторично если уже показал в этой session (cooldown 30 мин)
- ❌ Не давай длинные tutorials — это reference card, не doc
- ❌ Не upselling Phase 2-4 features (sparring/routine/trend scout) — они выключены
