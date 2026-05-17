---
title: hermes-agent — Patterns
type: reference
updated: 2026-05-17
tags: [wiki, hermes-agent, patterns]
---

# hermes-agent — Patterns

Паттерны фоrk-проекта. Hermes core (upstream) + CEO OS layer (V1).

## Architecture

**Двухслойная модель памяти:**
- `~/.hermes/state.db` (SQLite, WAL) — fast lookup, session history, Hermes core. Не трогаем.
- `memory/*.md` — long-term structured memory для CEO. Читается skill loader'ом.

**Skill discovery:** `scripts/build_skills_index.py` → автоиндекс `SKILL.md` файлов. CEO skills живут в `skills/ceo/<name>/SKILL.md`.

**Gateway routing:** `gateway/platforms/telegram.py::_handle_command()` (≈line 2956) — точка регистрации slash-команд. CEO команды (`/brief`, `/evening`, `/week`, ...) маршрутизируются к skill через COMMAND_REGISTRY.

**Cron:** `cron/jobs.py` + `cron/scheduler.py`. Job'ы хранятся в `~/.hermes/cron/jobs.json`. CEO jobs seedится через `hermes cron create` (Stage 6, вне MVP).

## Code conventions

- Python 3.11+ (Hermes baseline)
- `dart format` не применимо (нет Flutter)
- `black` для нового Python кода в `skills/ceo/_lib/*`
- Conventional commits с scope `ceo-os`: `feat(ceo-os): ...`, `fix(ceo-os): ...`
- Memory markdown — UTF-8, append-only там где помечено, structured headers (`##` для разделов)

## Memory file convention

| Файл | Read pattern | Write pattern |
|---|---|---|
| `memory/user.md` | каждый запрос | редко (manual) |
| `memory/soul.md` | каждый запрос | редко (manual) |
| `memory/memory.md` | каждый запрос | umiarkowanie (через /capture или cleanup) |
| `memory/areas.md` | по релевантности | редко |
| `memory/projects.md` | по релевантности | через /capture, /project_update |
| `memory/risks.md` | по релевантности | через /risks |
| `memory/goals.md` | weekly | редко |
| `memory/decisions.md` | по релевантности | через /decision |
| `memory/daily_log.md` | last N entries | append через /brief, /evening |
| `memory/weekly_review.md` | last entry | append через /week |

## Testing

- Hermes existing tests: `tests/`
- CEO skills: ad-hoc smoke tests через CLI (`hermes skills run daily_briefing`)
- End-to-end: Telegram bot → `/brief` → проверить ответ глазами (нет автоматического e2e в MVP)

## Deployment

- Docker (`docker-compose.yml`) — production
- Local dev — `./hermes` или `uv run hermes`
- Telegram bot — @Hermes_Alex21_bot (production)

## Anti-patterns

- ❌ Не дублировать Hermes core (skill loader, gateway, scheduler — используем как есть)
- ❌ Не писать "новый scheduler" — `hermes cron` достаточно
- ❌ Не редактировать `agent/`, `run_agent.py`, `cli.py` без необходимости — это upstream код
- ❌ Не помещать sensitive data (имена, цены договоров) в `memory/projects.md` без псевдонимов — см. privacy guard в `memory/soul.md`
- ❌ Не вызывать multi-agent / sparring / proactive messaging в Phase 1 (см. boundaries в `memory/soul.md`)
- ❌ Не пушить `logs/*` в git (см. .gitignore)
