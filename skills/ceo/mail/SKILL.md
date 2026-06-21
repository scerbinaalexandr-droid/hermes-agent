---
name: mail
description: |
  CEO email через подключённый Google (Gmail OAuth). Используй ВСЕГДА когда CEO
  спрашивает про почту: "что в почте", "проверь почту", "письма за сегодня",
  "найди письмо от", "непрочитанные", "email", "inbox", "ответь на письмо".
  Это ЕДИНСТВЕННЫЙ email-инструмент CEO. НЕ используй himalaya — Google уже
  подключён через OAuth.
version: 0.1.0
author: alexandr.scerbina
metadata:
  hermes:
    tags: [ceo, mail, gmail, email]
    command: /mail
    triggers:
      - "/mail"
      - "почта"
      - "что в почте"
      - "проверь почту"
      - "письма"
      - "непрочитанные письма"
      - "email"
      - "inbox"
      - "найди письмо"
---

# /mail — Gmail для CEO

**Цель:** читать и (по подтверждению) отправлять почту CEO через уже подключённый
Google-аккаунт. Авторизация сделана через OAuth — токен на `/opt/data/google_token.json`.

> ⚠️ **НЕ используй himalaya** и любой другой email-CLI. Почта CEO работает ТОЛЬКО
> через google-workspace (`google_api.py gmail ...`). Himalaya не установлен и не нужен.

## Движок

Все вызовы — через bundled-скрипт google-workspace, с `HERMES_HOME=/opt/data`:

```
HERMES_HOME=/opt/data /opt/hermes/.venv/bin/python \
  /opt/hermes/skills/productivity/google-workspace/scripts/google_api.py gmail <action> ...
```

Sub-actions: `search QUERY --max N` · `get <id>` · `send` · `reply` · `labels` · `modify`.

## Steps

1. **Понять запрос → собрать Gmail-query:**
   - «что в почте / за сегодня» → `search 'in:inbox newer_than:1d' --max 10`
   - «непрочитанные» → `search 'is:unread in:inbox' --max 15`
   - «письма от X» → `search 'from:X' --max 10`
   - «за неделю» → `newer_than:7d`. Без уточнения — `in:inbox newer_than:2d`.
2. **Выполнить** команду через terminal (см. Движок).
3. **Суммаризировать по-русски**, scannable, premium-тон (формат tandemcasa.ro):
   заголовок + список «отправитель — тема — 1 строка сути». Важное/требующее ответа — вверх.
   Если пусто — честно «📭 Новых писем нет» (НЕ выдумывать — soul.md §4a).
4. **Прочитать конкретное письмо** → `gmail get <id>` → пересказать суть + предложить действие.

## Отправка писем (Phase-1 граница)

- Hermes **НЕ отправляет письма сам**. По запросу «напиши/ответь письмо» —
  **составить черновик**, показать CEO, и отправить (`gmail send`/`reply`) **ТОЛЬКО**
  после явного подтверждения («отправь», «да, шли»).
- Privacy guard (soul.md): не раскрывать содержимое чужих писем третьим лицам,
  семейные имена → роли, без банковских/медицинских деталей в пересказе.

## What NOT to do

- ❌ НЕ использовать himalaya / IMAP-CLI — только google_api.py.
- ❌ НЕ отправлять/удалять/архивировать письма без явного подтверждения CEO.
- ❌ НЕ выдумывать письма/отправителей/темы (soul.md §4a) — если поиск пуст, так и сказать.
- ❌ НЕ показывать полные адреса/содержимое в групповых чатах — только в личке CEO.
