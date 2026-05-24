---
name: whoami
description: |
  Diagnostic — возвращает Telegram chat_id, username, full_name текущего пользователя.
  Используй когда нужно понять идентификаторы текущей сессии — например, чтобы
  убедиться что на двух телефонах один Telegram аккаунт (одинаковый chat_id)
  vs два разных (разные chat_id).
version: 0.1.0
author: alexandr.scerbina
license: MIT
metadata:
  hermes:
    tags: [ceo, debug, telegram, diagnostic]
    commands: [/whoami]
    triggers:
      - "/whoami"
      - "кто я"
      - "мой chat id"
      - "мой telegram id"
---

# /whoami — Telegram Identity

Этот skill **НЕ запускает скрипт**. Он инструктирует LLM считать identifiers из текущего Telegram update context и вернуть форматированный ответ.

## Что собрать из context

Текущий Telegram update имеет (доступно через bot runtime):

- `chat_id` — числовой ID chat'a (для personal chat = твой user ID)
- `user_id` — твой Telegram user ID (обычно совпадает с chat_id в personal chat)
- `username` — @handle (если установлен; может отсутствовать)
- `first_name` + `last_name` — display name
- `language_code` — `ru`, `en` etc
- `platform` — `Telegram` (фиксировано для этого gateway)

**ВАЖНО — graceful degradation (НЕ отвечай ошибкой):**
- `chat_id` практически всегда доступен. Если в контексте он назван **«Home Channel ID»** — это и есть `chat_id` для personal DM, используй его.
- Если какого-то поля (`username`, `first_name`, `language_code`) в контексте НЕТ — выведи его как «недоступно». Это нормально, НЕ ошибка.
- Технической ошибкой (секция Fallback) отвечай ТОЛЬКО если нет ВООБЩЕ никакого chat_id / Home Channel ID. Минимум — всегда покажи Chat ID.

## Output format (применяй §9 Response Design System из soul.md)

```
🪪 **Твой Telegram identity**

**Chat ID:** `<chat_id>`
**User ID:** `<user_id>`
**Username:** @<username> (или «не установлен»)
**Имя:** <first_name> <last_name>
**Язык:** <language_code>
**Платформа:** Telegram

**Что это значит:**
- Bot отправляет тебе ответы в chat с этим Chat ID
- Если на двух телефонах **один Telegram аккаунт** → Chat ID **одинаковый** на обоих (Telegram сам синхронизирует messages)
- Если **два разных аккаунта** (разные номера) → Chat ID **разные** → bot их видит как отдельных users

**Диагностика для проблемы «отчёт приходит только в один телефон»:**
1. Запусти `/whoami` на **другом** устройстве
2. Сравни **Chat ID**:
   - Одинаковый → проблема не у bot'a, а в Telegram client settings (Storage / Auto-Download)
   - Разные → у тебя 2 аккаунта; нужно добавить второй в `allowed_users` config

**Источник:** Telegram Update context (live).
```

## Privacy

User видит только **СВОИ** идентификаторы — это безопасно. Не show чужие user_ids даже если они есть в context.

## Fallback (крайний случай)

Используй ТОЛЬКО если в контексте нет НИ `chat_id`, НИ «Home Channel ID» —
т.е. вообще никакого идентификатора (impossible в normal flow). Если есть хотя
бы Home Channel ID — это НЕ этот случай: выведи обычный output с Chat ID и
пометь недоступные поля как «недоступно».

```
⚠️ ТЕХНИЧЕСКАЯ ОШИБКА — не могу прочитать identity из context

Причина: bot runtime не передал chat_id в skill execution.
Что нужно: пересоздай session (`/new`) и попробуй снова.
Альтернатива: посмотри в Telegram → Settings → Devices, там виден свой user ID.
```
