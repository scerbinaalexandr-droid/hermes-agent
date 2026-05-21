---
name: web
description: Web research — search/fetch/render. NO paid APIs (DuckDuckGo HTML + Chromium uses in-image).
version: 0.1.0
author: alexandr.scerbina
metadata:
  hermes:
    tags: [ceo, web, research]
    command: /web
---

# /web — Web Research Skill

**Цель:** дать Гермесу руки для интернет-парсинга без платных сервисов. Три суб-команды:

| Sub-command | Что | Когда использовать |
|---|---|---|
| `/web search <запрос>` | поиск в DuckDuckGo (HTML, без API key) | найти источники, инициальная разведка |
| `/web fetch <URL>` | скачать и распарсить статическую страницу | конкретный URL, статичный HTML (новости, блоги, документы) |
| `/web render <URL>` | headless Chromium для JS-heavy страниц | SPA, Twitter, LinkedIn, динамический контент |

## Privacy & honesty guard

Все три суб-команды **возвращают URL источника** для каждого результата. Bot **ОБЯЗАН** приводить URL в ответе user'у — per soul.md §4a NO FAKE DATA.

Если веб-запрос **не дал результата** (404, timeout, captcha, robots.txt block) — **явно сообщить user'у "(нет данных)"**, не выдумывать.

## Rate limiting & politeness

- `time.sleep(1)` между request'ами в одной сессии
- User-Agent: `Hermes-CEO-Research-Bot/0.1 (contact: alexandr.scerbina@gmail.com)`
- Robots.txt — проверяется в fetch (skip если disallow для нашего UA)
- Max 3 retries на network error, exponential backoff

## Output budget

- Search: max 10 results × 250 char snippet
- Fetch: max 8000 char main content (truncated с явной маркой `[truncated]`)
- Render: max 8000 char DOM text

## Argument parsing

User передаёт через слэш-команду: `/web search курс лей румынский к евро 2026`. Bot парсит:
1. Первое слово после `/web` — sub-command (search / fetch / render)
2. Остальное — query (для search) или URL (для fetch/render)
3. Если sub-command не указан или непонятен → возвращай help text

## Execute

```bash
# Search
python skills/ceo/web/scripts/search.py "<query>"

# Fetch static
python skills/ceo/web/scripts/fetch.py "<url>"

# Render JS-heavy
python skills/ceo/web/scripts/render.py "<url>"
```

Каждый скрипт возвращает JSON:
```json
{
  "ok": true,
  "url": "<source url>",
  "title": "<page title>",
  "results": [...] | "content": "..."
}
```

При ошибке — `{"ok": false, "reason": "...", "url": "..."}`.

## Format for Telegram

После вызова скрипта bot форматирует результат в read-friendly Markdown для Telegram:
- Search → нумерованный список (1-10) с **title** + URL + 1-line snippet
- Fetch/Render → first 3000 char main content + footer "Источник: <url>"

## Use cases

- **Intel research** (Roadmap: `/intel week`) — search → fetch на топ-результатах
- **News watch** — fetch RSS endpoint конкретного издания
- **Competitor research** — search "<competitor> новости 2026" → fetch топ-3
- **Quick lookup** — "что произошло в X сегодня?" → search + fetch top result

## Limits

- DuckDuckGo может вернуть captcha если ≥30 req/min — soft fail с явным сообщением
- robots.txt уважается строго (per ethical research practice)
- Никакого scraping персональных данных (per soul.md privacy guard)
