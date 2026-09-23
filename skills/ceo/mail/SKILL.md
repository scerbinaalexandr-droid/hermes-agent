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
      - "разложи почту"
      - "карантин"
      - "календарь"
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

## Что подключено (2026-09-23)

Ящик **scerbina21@gmail.com**. Права токена: почта — чтение, отправка, ярлыки и
перемещение (`gmail.modify`, `gmail.send`); календарь — полный (чтение, создание,
удаление событий); Google-таблицы — полный; Диск — чтение + свои файлы; контакты —
чтение. Нет доступа к серверным фильтрам Gmail (`gmail.settings.*`) — поэтому
раскладку делает наш сортировщик, а не фильтры Gmail.

## Папки и раскладка

```bash
HERMES_HOME=/opt/data /opt/hermes/.venv/bin/python /opt/data/scripts/mail_sort.py --dry-run
HERMES_HOME=/opt/data /opt/hermes/.venv/bin/python /opt/data/scripts/mail_sort.py [--days 365]
HERMES_HOME=/opt/data /opt/hermes/.venv/bin/python /opt/data/scripts/mail_sort.py --rules
```

Папки (ярлыки Gmail, видны на телефоне): Безопасность · Банки/<банк> ·
Путешествия/{Билеты,Отели,Авто} · Жильё · Документы · Подписки · **Карантин**.
Правила упорядочены — срабатывает первое; уже разложенное письмо повторный
прогон не трогает. **Карантин** = ярлык + уход из входящих (промо, соцсети,
рассылки); письма целы, ничего не удаляется.

### Другие ящики (mail.ru и прочие по IMAP)

```bash
HERMES_HOME=/opt/data /opt/hermes/.venv/bin/python /opt/data/scripts/mail_sort_imap.py --boxes
HERMES_HOME=/opt/data /opt/hermes/.venv/bin/python /opt/data/scripts/mail_sort_imap.py [--dry-run]
```

Те же папки и тот же порядок правил (общий файл `mail_rules.py`). Разница: в IMAP
папки настоящие, поэтому письмо **переносится** из входящих в папку (в Gmail —
ярлык + уход из входящих только для карантина). Ящики задаются переменными
Railway `MAIL_IMAP_<n>_HOST/_USER/_PASS/_NAME` (n = 1…10). Пароли — только в
переменных, в ответах и логах их нет. Ящик не подключён — скрипт молчит.

Так подключаются и остальные gmail-ящики владельца (`imap.gmail.com`, пароль
приложения): через API работает только главный ящик, у которого есть токен.
`--all` (или `--days 0`) разбирает входящие целиком, без ограничения по дате —
первый прогон по большому ящику делать так, дальше хватает окна в 90 дней.
Ящики владельца: `scerbina21@gmail.com` (API), `ascerbina@mail.ru`,
`scerbinaalexandr@gmail.com`, `alexscerbina@gmail.com`,
`alexandr.scerbina@gmail.com` (IMAP).

Владелец просит «разложи почту», «что в карантине», «добавь папку …» →
сначала `--dry-run` и показать, что уедет; боевой прогон — после «давай».
Новую папку или правило добавляет разработчик в `RULES` (скрипт — источник
истины), вручную ярлыки не плодить.

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
