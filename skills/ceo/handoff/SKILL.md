---
name: handoff
description: |
  Делегирование read-доступа к Hermes будущему Chief of Staff (CoS) —
  Stilman parallel-track, HERMES_TO_96 Этап #13. Объясняет процедуру выдачи
  доступа второму человеку (CoS chat_id), что CoS видит и НЕ видит (privacy
  guard: никаких health/bank/family данных), и как Александр сам добавляет
  запись в TELEGRAM_ALLOWED_USERS на Railway. Skill НЕ меняет env сам —
  он документирует процедуру и подтверждает identity.
  `/handoff status` — показывает текущий allowlist (redacted, last-3 digits).
  Используй при: "handoff", "доступ для ассистента", "Chief of Staff",
  "добавить помощника", "делегировать доступ", "/handoff".
version: 0.1.0
author: alexandr.scerbina
license: MIT
prerequisites:
  files:
    - memory/soul.md
metadata:
  hermes:
    tags: [CEO, Access, Delegation, Telegram]
    commands: [/handoff]
    triggers:
      - "/handoff"
      - "доступ для ассистента"
      - "добавить chief of staff"
      - "делегировать доступ"
      - "give my assistant access"
---

# Handoff — делегирование доступа Chief of Staff

**Purpose.** Подготовка к найму живого Chief of Staff (Stilman parallel-track,
HERMES_TO_96 Этап #13). Skill даёт безопасную процедуру: как выдать CoS
**read-доступ** к Hermes, не нарушив privacy guard. Hermes остаётся информационным
ядром (память + контекст), CoS берёт на себя людей и встречи. Доступ выдаётся
осознанно, одним подтверждённым chat_id, и в любой момент отзывается.

**Trigger.** `/handoff` — показать процедуру делегирования.
`/handoff status` — показать текущий allowlist (redacted).

---

## Persona

Load `memory/soul.md`. Применяй privacy guard + premium tandemcasa.ro tone:
прямо, сканируется за 5 секунд, без корпоративного наполнителя. Это про
**контроль доступа** — тон спокойный, ответственный, без алармизма.

---

## Step 1 — Определить sub-команду

- Сообщение содержит слово `status` (`/handoff status`, "покажи доступы",
  "кто имеет доступ") → перейти к **Step 5 (Status)**.
- Иначе (`/handoff`, "как добавить CoS", "делегировать доступ") →
  перейти к **Step 2 (процедура делегирования)**.

---

## Step 2 — Объяснить модель доступа (division of labor)

Выведи в Telegram (≤1500 char):

```
🤝 **Handoff — доступ Chief of Staff** — read-доступ к Hermes для одного помощника

**Разделение труда:**
- **Hermes** = информация + память (brief, проекты, риски, поиск по истории)
- **CoS** = люди + встречи (звонки, координация, follow-up вне Hermes)

**CoS получает (read):**
- /brief, /projects, /risks, /find, /report — рабочий контекст
- /menu — навигация по командам

**CoS НЕ получает (privacy guard):**
- ❌ health/энергия/стресс данные (/coach, дневник)
- ❌ банк, цены договоров точные суммы
- ❌ семейные имена и личные заметки
- ❌ запись в память от своего имени (write-доступ остаётся за тобой)

**Что дальше?** · /handoff status · подробности ниже
```

---

## Step 3 — Подтвердить identity CoS (precondition)

Доступ выдаётся **только по подтверждённому chat_id**. Прежде чем менять env:

1. CoS пишет боту `/whoami` со своего устройства → получает свой `Chat ID`.
2. CoS присылает этот Chat ID Александру (НЕ боту — человеку).
3. Александр сверяет: это действительно нужный человек, число выглядит как
   валидный Telegram user ID (9-10 цифр).

Выведи инструкцию:

```
📋 **Шаг идентификации CoS** — перед выдачей доступа

1. Попроси CoS написать боту `/whoami` — он вернёт свой **Chat ID**.
2. CoS передаёт тебе этот Chat ID лично (не в бота).
3. Сверь: число 9-10 цифр, это точно нужный человек.

Без подтверждённого Chat ID доступ не выдаётся. Identity → потом env.
```

---

## Step 4 — Процедура добавления (выполняет Александр на Railway, НЕ skill)

🚨 **Skill НЕ мутирует env.** Изменение `TELEGRAM_ALLOWED_USERS` — ручное
действие Александра в Railway. Skill только документирует процедуру.

Выведи (используй `inline code` для команд):

```
🛠 **Добавить CoS в allowlist** — вручную на Railway (ты, не Hermes)

Текущий формат `TELEGRAM_ALLOWED_USERS` — список через запятую:
`<owner_id_1>,<owner_id_2>` (два твоих телефона)

Добавляешь CoS как третью запись:
`<owner_id_1>,<owner_id_2>,<cos_chat_id>`

Где:
- Railway → service `hermes` → Variables → `TELEGRAM_ALLOWED_USERS`
- Допиши `,<cos_chat_id>` в конец, сохрани → редеплой подхватит.

**Отзыв доступа:** убираешь `,<cos_chat_id>` → сохраняешь. Мгновенно.

**Источник процедуры:** memory/two-telegram-accounts.md + gateway/config.py
(allow_from → TELEGRAM_ALLOWED_USERS).
```

**ВАЖНО:** не подставляй реальные chat_id в этот шаблон — оставь плейсхолдеры
`<owner_id_1>` / `<cos_chat_id>`. Реальные ID живут только в Railway env.

---

## Step 5 — Status (`/handoff status`)

Запусти helper (read-only, redacted):

```bash
python3 skills/ceo/handoff/scripts/list_allowed.py
```

(на проде путь: `python3 /opt/data/skills/ceo/handoff/scripts/list_allowed.py` —
если основной путь не найден, попробуй `/opt/hermes/...`.)

Helper читает `TELEGRAM_ALLOWED_USERS` из env и возвращает JSON с **redacted**
записями (только last-3 цифры, полные ID никогда не печатаются).

Сформируй ответ из JSON (поля `count`, `owners`, `delegates`, `entries[].masked`,
`entries[].role_hint`, `effective_source`):

```
🔐 **Allowlist Hermes** — кто имеет доступ к боту

**Всего записей:** <count> (владелец: <owners>, делегаты: <delegates>)
**Источник:** <effective_source>

<для каждой entry:>
- `<masked>` — <role_hint>

**Что значит:**
- owner = твои устройства (личный + рабочий телефон)
- delegate = добавленный помощник (CoS)

🛡 ID показаны только last-3 цифры — full ID живёт лишь в Railway env.

**Что дальше?** · /handoff (как добавить) · отзыв — убрать запись в Railway
```

Если `count == 0` — выведи fail-loud (env не прочитан в этой среде):

```
⚠ Не удалось прочитать allowlist из env (`TELEGRAM_ALLOWED_USERS` пуст).
Возможно: запуск вне прод-среды, или переменная задана через config (allow_from).
Что сделать: проверь Railway → service `hermes` → Variables.
```

---

## Edge cases

| Случай | Поведение |
|---|---|
| User просит «дай CoS write-доступ / пусть пишет в память» | Отклонить: Phase 1 — write остаётся за Александром. CoS = read-only. Предложить залогировать как TODO Phase 2+. |
| User присылает реальный chat_id и просит «добавь сам» | Skill НЕ меняет env. Напомни: правка `TELEGRAM_ALLOWED_USERS` — вручную на Railway (Step 4). |
| User просит «пусть Hermes отправит CoS сообщение/приглашение» | Отклонить: Phase 1 — Hermes не шлёт сообщения от имени user'а третьим лицам. |
| `/handoff status` вне прод-среды (env пуст) | Fail-loud (Step 5), не выдумывай записи. |
| User спрашивает «а CoS увидит мой /coach / здоровье?» | Чётко: нет. Privacy guard режет health/bank/family на уровне самих skills, не на уровне allowlist. |
| Helper не запустился (путь не найден) | Сообщи технической ошибкой, дай альтернативу — проверить Railway Variables вручную. Не выдумывай состояние allowlist. |

---

## What NOT to do

- ❌ НЕ менять `TELEGRAM_ALLOWED_USERS` или любой env из skill — это ручное
  действие Александра на Railway. Skill документирует, не мутирует.
- ❌ НЕ печатать полные chat_id / user_id в ответе — только redacted last-3
  (helper уже редактирует; не разворачивай обратно).
- ❌ НЕ записывать ничего в `memory/*.md` (guard.py блокирует) — этот skill
  read-only, у него нет write-фазы вообще.
- ❌ НЕ выдумывать состав allowlist, количество записей или chat_id без
  реального вывода helper'а (soul.md §4c — NO FAKE IDENTIFIERS). Нет вывода →
  fail-loud, не угадывай.
- ❌ НЕ выдавать CoS write-доступ, права отправки сообщений или доступ к
  health/bank/family данным — privacy guard non-negotiable.
- ❌ НЕ отправлять сообщения / приглашения CoS от имени Александра (Phase 1).
