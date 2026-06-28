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
📝 /notes — протокол встречи: участники / решения / задачи → Google Sheet (голосом)
📔 /diary — дневник дня + протоколы встреч (голосом — auto)
✈️ /trip — план поездки / командировки → Google Sheet (голосом)

*Еженедельно:*
📅 /week — weekly CEO review, голосом (auto Sun 18:00)

*Коуч:*
🧭 /coach — персональный коуч: ICF / GROW / Колесо баланса / Co-Active + ритмы (Утро/Вечер/Неделя/Месяц)

*Просмотр:*
📋 /projects — активные проекты (опц. /projects high)
⚠ /risks — топ риски (опц. /risks high)
🔍 /find <запрос> — поиск по памяти (что мы решили / когда было)

*Утилиты:*
⏰ /remind <когда> <что> — напоминание (через 3ч / завтра в 10:00)
📊 /dashboard — кокпит: что на столе сейчас + впереди (HTML)
📊 /report [week|month|quarter] — отчёт: Google Doc + PDF + HTML (для команды)
🧠 /cleanup — гигиена памяти: устаревшее / дубли (предложения, не правки)
🤝 /handoff — делегировать read-доступ Chief of Staff (/handoff status)
💾 /backup — manual backup

---

💡 *Голосовые memo работают везде* — диктуй свободной формой, я разбираю
сам и показываю черновик для подтверждения.

🛡 *Privacy:* семейные имена → "Супруга" / "Мама" / "Папа"; цены договоров → диапазоны.

Что хочешь сделать сейчас?

[[menu_keyboard]]
```

## Keyboard (hands-free)

ВСЕГДА заканчивай ответ строкой `[[menu_keyboard]]` на отдельной строке — гейтвей
превращает её в постоянную клавиатуру-плитки под полем ввода (большие кнопки за
рулём). НЕ объясняй маркер и НЕ убирай его — в видимом тексте он не показывается.

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
