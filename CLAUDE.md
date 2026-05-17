# hermes-agent — Claude Code Project Rules

> Inherits global rules from `~/.claude/CLAUDE.md` + `~/.claude/STANDARDS.md`.
> Этот файл — project-specific overrides и контекст.

---

## Что это за проект

Fork **Nous Research Hermes Agent**, переоснащённый как **Executive Operating System** для **Alexandr Scerbina, CEO TANDEM Group** (мебельный холдинг, Молдова + Румыния; бренды: TANDEM Group, Tandem Casa 360°, Kitchen by Tandem, Arlengo, Lean Kitchen).

**Источник архитектуры V1:** `~/Downloads/hermes_claude_code_sequential_files_blueprint.md`
**План реализации:** `~/.claude/plans/hermes-claude-code-sequential-files-blue-partitioned-gizmo.md`
**Текущая фаза:** V1 MVP-вертикаль — Stage 0-4 до рабочего `/brief` через Telegram.

---

## Стек проекта

- **Language:** Python 3.11+
- **Runtime:** uv + venv
- **LLM:** OpenRouter + Anthropic + 24 других провайдера (см. `cli-config.yaml.example`)
- **State:** SQLite (`~/.hermes/state.db`) + Markdown layer (`memory/*.md`)
- **Messaging:** Telegram (@Hermes_Alex21_bot), Discord, Slack, WhatsApp, Signal, Email
- **Skills:** Hermes-native `SKILL.md` в `skills/<category>/<name>/`
- **MCP:** Hermes Gateway экспортирует 9 MCP tools (`mcp_serve.py`)
- **Cron:** `cron/jobs.py` + `cron/scheduler.py` (`hermes cron create`)
- **Deploy:** Docker (`docker-compose.yml`)

---

## CEO OS Layer (V1) — структура

```
hermes-agent/
├── memory/        ← long-term structured memory (markdown)
│   ├── user.md           — CEO profile
│   ├── soul.md           — Hermes persona (canonical, ex-docker/SOUL.md)
│   ├── memory.md         — active context
│   ├── areas.md          — 12 life domains
│   ├── goals.md          — long-term goals
│   ├── projects.md       — active projects
│   ├── risks.md          — 8 risk categories
│   ├── decisions.md      — Date/Decision/Reason/Result/Review/Status
│   ├── daily_log.md      — append-only
│   └── weekly_review.md  — append-only
├── SOP/           ← Standard Operating Procedures
│   ├── telegram_commands.md
│   ├── daily_workflow.md
│   ├── weekly_workflow.md
│   ├── project_management.md
│   └── memory_management.md
├── logs/          ← gitignored, runtime logs
│   ├── daily/YYYY-MM-DD.md
│   ├── weekly/YYYY-WW.md
│   └── telegram_inputs/
├── backups/       ← gitignored, для GitHub backup (Stage 7)
└── skills/ceo/    ← CEO-specific Hermes skills
    ├── _lib/memory.py    — memory loader/updater helper
    ├── daily_briefing/SKILL.md
    ├── evening_review/SKILL.md     (Stage 5)
    ├── weekly_ceo_review/SKILL.md  (Stage 5)
    ├── voice_to_task/SKILL.md      (Stage 5b)
    ├── project_update/SKILL.md     (Stage 5c)
    └── memory_cleanup/SKILL.md     (Stage 5c)
```

---

## Bootkit (рекомендуемые skills/agents для этого проекта)

- **karpathy-guidelines** — surgical changes, minimum code
- **code-critic** — review CEO skills перед commit
- **security-code-reviewer** — обязательно после touching `gateway/platforms/telegram.py`
- **flask-patterns** / **flutter-patterns** — не применимо (Hermes ≠ Flask/Flutter)
- **detail-extractor** — при изменении `memory/*.md` шаблонов (важна структура)
- **github-security** — перед первым деплоем V1 + при создании GitHub backup (Stage 7)

---

## Project-specific правила

### Privacy guard (КРИТИЧНО — из `memory/soul.md`)

- НЕ запрашивать/сохранять: пароли, банк, медицину семьи
- ФИО партнёров — псевдонимы (исключения: общеизвестные имена в Tandem контексте)
- Конкретные цены — диапазоны, не точные суммы
- Цитаты с встреч — после сохранения предлагать переписать как "своё суждение"

### Phase boundaries

В Phase 1 (Memory Hub, 30 дней) **ЗАПРЕЩЕНО**:
- Генерировать черновики писем/КП/follow-up без явного запроса (Phase 3)
- Devil's advocate / sparring (Phase 2)
- Research-cron на конкурентов (Phase 4)
- Отправлять сообщения от имени user'а
- Delegate subagents в skill execution

### Не трогать без явного запроса

- `agent/` — Hermes core LLM adapters
- `run_agent.py`, `cli.py` — upstream code
- `hermes_state.py` — SQLite layer
- `tests/` — upstream tests
- `cron/scheduler.py` core logic — только seed jobs через CLI
- `gateway/platforms/*` кроме `telegram.py` (там surgical edits для CEO commands)

### Commit convention

`feat(ceo-os): <description>` для CEO OS layer изменений.
`fix(ceo-os): ...`, `docs(ceo-os): ...`, `chore(ceo-os): ...`.

Если редактируется Hermes core (редко) — другой scope: `feat(gateway): ...`, `fix(cron): ...`, etc.

---

## Karpathy Second Brain

- При завершении сессии — обновить `.wiki/CONTEXT.md` (Continuation Notes), append в `.wiki/log.md`
- L3 решения → `.wiki/decisions.md` с **Why** + **How to apply**
- Milestone → episode snapshot в `~/.claude/memory/episodes/`
- Obsidian page update — `~/.../ALEX21_VAULT/02 — ПРОЕКТЫ/hermes-agent/` (создать при первом milestone)

---

## Quality threshold

LEAN21 9.6/10 — стандарт. Не передаём брак. End-to-end проверка `/brief` обязательна перед "MVP done".
