---
title: hermes-agent — Context
type: reference
updated: 2026-05-17
tags: [wiki, hermes-agent, ceo-os, tandem]
---

# hermes-agent — Context
**Updated:** 2026-05-17
**Phase:** V1 Executive OS — MVP-вертикаль (Stage 0-4) для CEO Tandem Group

## Что это за проект

Fork Nous Research Hermes Agent, переоснащённый для использования как **Executive Operating System** для Alexandr Scerbina (CEO TANDEM Group, MD+RO). Бренды: TANDEM Group, Tandem Casa 360°, Kitchen by Tandem, Arlengo, Lean Kitchen.

Источник архитектуры V1: `~/Downloads/hermes_claude_code_sequential_files_blueprint.md`.
Плановый файл: `~/.claude/plans/hermes-claude-code-sequential-files-blue-partitioned-gizmo.md`.

## Текущая задача

Построить MVP-вертикаль V1: рабочая команда `/brief` в Telegram (@Hermes_Alex21_bot) → daily briefing из `/memory/*.md`.

Этапы:
- ✅ Stage 0 — ALEX21 Compliance (.wiki + CLAUDE.md)
- ✅ Stage 1 — Audit report сохранён (`.wiki/AUDIT_2026-05-17.md`)
- ✅ Stage 2 — Folder structure (/memory, /SOP, /logs, /backups + .gitignore patches)
- ✅ Stage 3 — Memory content + loader (10 markdown файлов + `skills/ceo/_lib/memory.py`)
- ✅ Stage 4 — `/brief` skill working end-to-end
- ✅ Stage 4b — Skill loader routing (rename, placeholder skills, COMMAND_REGISTRY rollback)
- ✅ Stage 4c — `~/.hermes/config.yaml` с external_dirs
- ✅ Stage 5 — `/evening` (blueprint §08) + `/week` (blueprint §09) real implementations
- ✅ Stage 5b — `/capture` (4 routing types для voice memo / text)
- ✅ Stage 5c — `/projects`, `/risks` listings (priority/severity sorted)
- ✅ Stage 5d — Extended memory loader (all_projects, all_risks, route_capture, update_project_field, ...)
- ⏳ Stage 6 — Cron seeding (5 jobs) — operational, VPS access
- ⏳ Stage 7 — GitHub private backup — operational, GITHUB_TOKEN + repo setup

**6 из 7 CEO команд real-implemented**, 1 placeholder (/backup для Stage 7).

## Принятые решения

См. `decisions.md`. Главные:
- `/memory`, `/SOP`, `/logs`, `/backups` — в КОРНЕ репо (по блюпринту)
- Skills формат — Hermes-native `skills/ceo/<name>/SKILL.md`
- `docker/SOUL.md` — база для `memory/soul.md` (расширение, не дубль)
- Scope первой итерации — MVP-вертикаль до `/brief` end-to-end

## Следующие шаги

1. **End-to-end тест** `/brief` через Telegram @Hermes_Alex21_bot (запустить gateway, отправить /brief, проверить ответ + лог в `logs/daily/`)
2. **Дозаполнить** user.md (Leadership Style, Communication Style разделы) и memory.md (Active Priorities этой недели)
3. **Commit** серией: feat(ceo-os): stage 0, ..., stage 4
4. Stage 5 (next iteration): evening_review, weekly_ceo_review skills + `/evening`, `/week`
5. Stage 6: cron seeding (07:30 brief, 21:30 evening, Sun 17:00 cleanup, Sun 18:00 weekly, 00:30 backup)
6. Stage 7: GitHub private backup automation

## Открытые блокеры

- `memory/user.md` — нужны personal data из `docker/SOUL.md` + дополнение (handled inline в Stage 3)
- Telegram end-to-end тест возможен только когда user готов запустить бот / контейнер

## Continuation Notes

### Snapshot 2026-05-18 (перед /compact)

**Production state (Railway):**
- Project: `4e83ef6c-268f-4021-81f0-6807906432a7`
- Service: `ab136f58-0bfb-49fb-9c12-8fe38210e301`
- Last commit deployed: `3291f6f45` (feat(ceo-os): /report HTML dashboard + honesty harness)
- Container: `HERMES_HOME=/opt/data`, `WORKDIR=/opt/hermes`, model `claude-haiku-4-5`
- Allowed users: `746810595` (CEO chat_id)

**Skills shipped (12 CEO + 1 alias = 13):**
- `/menu`, `/start`, `/brief`, `/evening`, `/week`, `/projects`, `/risks`,
  `/capture`, `/find`, `/remind`, `/report`, `/backup` + safety `/stop`
- Все voice-first (auto-detect type), Russian output, Супруга-pseudonym, compact mode
- `/report` — НОВОЕ — generates real-data HTML dashboard, sends as Telegram document

**Architectural decisions taken (L3, см. `.wiki/decisions.md`):**
1. CEO commands регистрируются через skill loader (не CommandDef в core)
2. `~/.hermes/config.yaml` создан с `skills.external_dirs` (production hand-patched via railway ssh)
3. `docker/ceo-os-entrypoint.sh` wrapper — seeds config + memory + chown owner на boot
4. `.dockerignore` whitelist для skills/ceo/**/*.{md,py,txt} (фикс блокирующего `*.md`)
5. Telegram bot menu whitelist (`hermes_cli/commands.py::_CEO_TELEGRAM_MENU_NAMES`) — 12 CEO + /stop, остальные ~88 commands hidden from popup
6. soul.md §4a — strict NO FAKE DATA rule (после fake-report incident 2026-05-18)
7. `/report` skill — single artefact (Telegram document, no inline duplicate), open identically on Mac + iPhone

**Cron jobs active в production:**
- `92ee5dfa0e33` Brief 07:30 EEST (04:30 UTC)
- `37e08a7c13ed` Evening 21:30 EEST (18:30 UTC)
- `6318d6c709f5` Weekly Sun 18:00 EEST (Sun 15:00 UTC)

**Active TODOs:**
- ⏳ User должен revoke leaked token `900d8c82-...` после deploy (он засветил его в screenshots Terminal)
- ⏳ User должен в Telegram попробовать: `/menu`, `/report week`, voice memo для `/capture`
- ⏳ Заполнить `memory/memory.md::Active Priorities` через `/capture task:`
- ⏳ `/cleanup` skill (Stage 5c) — not yet implemented, placeholder
- ⏳ `/backup` skill (Stage 7) — placeholder, GitHub private repo backup not yet wired

**Open lessons from session:**
- Token leak pattern повторился **4 раза** в эту сессию (`99de4100-`, `a80059e7-`, `900d8c82-`, и в TextSession). Episode 2026-05-06 уже фиксировал эту проблему. Lesson: для CEO non-tech user НЕ просить никогда paste'ить токен в command-line. OAuth login через TTY-Terminal — only safe path.
- Bot ранее (до 2026-05-18 morning) генерировал HTML отчёт с полностью fake stats (Consumer Spending 3.2%, Rovere PRIMARY THREAT). Файл `TANDEM_Weekly_Report_Printable.html` попал к user на Mac. Hardened soul.md §4a против этого.

**File paths key:**
- Repo: `/Users/scerbinaalexandr/Documents/01_CODE/hermes-agent/`
- Plan: `~/.claude/plans/hermes-claude-code-sequential-files-blue-partitioned-gizmo.md`
- Blueprint: `~/Downloads/hermes_claude_code_sequential_files_blueprint.md`
- ALL-on-in wiki (Hermes operational): `~/Documents/01_CODE/ALL-on-in/.wiki/`
- Production logs: `railway logs --deployment` (via `env -u RAILWAY_API_TOKEN railway logs ...`)
- Report output (production): `/opt/data/reports/tandem-report-<period>-YYYY-MM-DD.html`

**После /compact продолжать с:**
1. Verify deploy `3291f6f45` active в production (Telegram bot отвечает с новой honesty + /report работает)
2. Revoke leaked token (см. Active TODOs)
3. User в Telegram: `/report week` → должен получить HTML файлом

---

## Snapshot 2026-05-19 (auto-saved перед /compact)

**Сессия началась:** 2026-05-17 утром (~3 дня многоступенчатой работы)
**Сессия закрыта на:** /report skill end-to-end debug — последнее состояние
**Контекст на момент snapshot:** ~80%
**Last commit на main:** `9d4737163` (fix: add /opt/hermes fallback to sys.path)

### 🏗 Архитектурные решения этой сессии (помимо ранее зафиксированных)

1. **CEO commands → Hermes-native SKILL.md, НЕ CommandDef** — авторегистрация через skill loader, без правки core. Reversal: trivially.
2. **Memory layer = markdown в /memory + Hermes SQLite параллельно** — двойной слой не конкурирует, .md для long-term structured, SQLite для fast lookup.
3. **Production deployment = Railway** (project `4e83ef6c-268f-4021-81f0-6807906432a7`, service `ab136f58-0bfb-49fb-9c12-8fe38210e301`, fork `scerbinaalexandr-droid/hermes-agent`). Deploy через `railway up` manual ИЛИ GitHub auto после Source connect. Reversal: легко.
4. **`docker/ceo-os-entrypoint.sh` wrapper** = 1-line Dockerfile ENTRYPOINT swap, upstream `entrypoint.sh` НЕ модифицирован. Seedит config.yaml + memory templates + chown на каждый boot, idempotent. Reversal: trivial — restore ENTRYPOINT line.
5. **`.dockerignore` whitelist** для `skills/ceo/**/*.{md,py}` + `SOP/**/*.md` (фикс блокирующего `*.md` global). Reversal: trivial.
6. **Telegram bot menu whitelist** в `hermes_cli/commands.py::_CEO_TELEGRAM_MENU_NAMES` — 12 CEO + /stop, остальные ~88 admin/skills hidden from popup (чтобы CEO случайно не тапнул `/new`). Reversal: trivial.
7. **`/report` skill: real-data ONLY + dual format (HTML + PDF)** — генерация только из memory/*. PDF via headless Chromium CLI `--print-to-pdf` (Chromium уже в image, line 53 Dockerfile). Reversal: легко.
8. **Honesty harness in `soul.md` §4a** — strict NO FAKE DATA rule после incident с `TANDEM_Weekly_Report_Printable.html` fake report.
9. **Reports sharing = Telegram forward (НЕ public URL hosting)** — chosen by user 2026-05-18. Avoids hosting infra, files forwardable to team in Telegram.
10. **sys.path fallback `/opt/hermes`** в 7 скриптах CEO — потому что Hermes skill-sync копирует только директории с SKILL.md (`_lib/` остаётся в `/opt/hermes/`, не попадает в `/opt/data/`).

### 🎨 Визуальные / UX достижения

- **HTML report template** (skills/ceo/report/scripts/generate_report.py) — dark theme TANDEM (gold #c4a747 accent), Chart.js doughnut (captures by type) + line (energy/stress trend), responsive mobile, print-friendly CSS.
- **`/menu` skill output** — главный экран бота с 11 CEO командами + emoji + privacy reminder + tip про voice memo.
- **Telegram bot menu (popup)** — curated до 12 commands в логическом порядке (menu/start → daily ritual → view → write → admin → safety).

### 📁 Ключевые file paths

- `/Users/scerbinaalexandr/Documents/01_CODE/hermes-agent/` — repo
- `/Users/scerbinaalexandr/Documents/01_CODE/ALL-on-in/.wiki/` — Hermes operational wiki (decisions, log)
- `~/.claude/plans/hermes-claude-code-sequential-files-blue-partitioned-gizmo.md` — план реализации
- `~/Downloads/hermes_claude_code_sequential_files_blueprint.md` — блюпринт V1
- Production Railway volume: `/opt/data/` (HERMES_HOME), `/opt/hermes/` (WORKDIR, image)
- Production reports: `/opt/data/reports/tandem-report-<period>-YYYY-MM-DD.html` + `.pdf`

### 🔑 Идентификаторы

- Railway project: `4e83ef6c-268f-4021-81f0-6807906432a7`
- Railway service: `ab136f58-0bfb-49fb-9c12-8fe38210e301` (hermes)
- GitHub fork: `scerbinaalexandr-droid/hermes-agent`
- Telegram bot: `@Hermes_Alex21_bot`
- Allowed user chat_id: `746810595`
- Model: `claude-haiku-4-5` (Anthropic direct)
- ENV vars (имена): `TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `HERMES_HOME=/opt/data`, `HERMES_UID=10000`, `HERMES_CEO_MEMORY_ROOT=/opt/data/memory`
- Cron jobs production: `92ee5dfa0e33` brief 07:30 EEST, `37e08a7c13ed` evening 21:30 EEST, `6318d6c709f5` week Sun 18:00 EEST

### 📋 Open TODOs (для следующей сессии после /compact)

- [ ] **Verify deploy `9d4737163` active** на Railway → проверить через UI или Telegram `/report week` работает end-to-end (HTML + PDF приходят файлами)
- [ ] **Cron Monday weekly report** — после успешного `/report` ручного теста, user просит bot: «Создай рекуррентный cron job: понедельник 08:00 EEST → /report week, отправляй сюда»
- [ ] **Revoke ВСЕ leaked Railway tokens** на https://railway.com/account/tokens (4 раза засветились в этой сессии). Сейчас RAILWAY_API_TOKEN в Terminal env невалидный.
- [ ] **GitHub Source auto-deploy** — Railway → Service Settings → Source показывает «Auto deploy unavailable». Нужно install Railway GitHub App для webhook auto-trigger (сейчас manual Redeploy через UI).
- [ ] **Fill memory/memory.md::Active Priorities** — user отложил, заполнить через `/capture task:` в Telegram постепенно.
- [ ] **Stage 5c — /cleanup skill** (memory hygiene proposals)
- [ ] **Stage 7 — GitHub backup automation** (private repo + cron 00:30)
- [ ] **`hermes_cli/commands.py` core правка** — добавлен `_CEO_TELEGRAM_MENU_NAMES` whitelist. При rebase upstream Hermes требует manual conflict resolution.

### ⚠ Lessons learned (новые, добавить в decisions.md)

1. **Hermes skill-sync копирует ТОЛЬКО директории с SKILL.md** — `_lib/` (Python helper без SKILL.md) НЕ попадает в `/opt/data/skills/`, остаётся только в `/opt/hermes/` image path. Scripts должны иметь fallback sys.path на `/opt/hermes`.
2. **Token leak pattern recurring** — 4 раза в эту сессию (`99de4100-`, `a80059e7-`, `900d8c82-`, текущий expired). User paste'ит токены в chat / screenshots. Episode 2026-05-06 уже зафиксировал паттерн. Lesson **повторно**: для CEO non-tech user не просить paste токены ни в chat ни в Terminal screenshots; **OAuth login через TTY only**.
3. **Bot caches skill body** — после deploy с fixed скриптом bot всё ещё использует cached старую версию. Нужно `/reload_skills` ИЛИ `/new` (fresh session) чтобы подхватить.
4. **`railway up && railway up` parse error in zsh** — Cmd+V в Terminal разбивает строку на newlines если она была длинной. Лучше давать 2 отдельные команды.
5. **`/opt/data/cron/jobs.json` root-owned** — мой первый chown patch (memory/logs/backups) забыл `cron/`. Это блокировало bot от создания cron jobs самостоятельно через cronjob tool. Fixed в commit `addc7079e`.
6. **Railway Account Tokens auto-revoke if leaked publicly** — токен `900d8c82-...` после паблик-paste в screenshots стал invalid (`Unauthorized` через 30 минут). Railway has token scanning или secrets detection.

### 🔗 Continuation в следующей сессии

1. **Прочитать** этот CONTEXT.md + `.wiki/decisions.md` + `.wiki/AUDIT_2026-05-17.md`
2. **Проверить production state:** запустить `env -u RAILWAY_API_TOKEN railway status` (после OAuth re-login если нужно) или открыть Railway UI dashboard, удостовериться что ACTIVE = `9d4737163`
3. **Telegram test:** `/reload_skills` → `/report week` → должно прийти 2 файла. Если не работает — debug через `railway logs --deployment` (нужен auth).
4. **Cron Monday 08:00:** одно сообщение bot'у в Telegram (см. Open TODOs)
5. **Если deploy failure или другие issues** — открыть Railway logs, искать `[ceo-os-init]` + ошибки скриптов
6. **Не повторять token leak pattern** — для CLI auth используем только OAuth `railway login` через interactive TTY (отдельное окно Terminal)

---

---

## Continuation 2026-05-19 (session end)

**Сессия закрыта на:** /report дашборд работает с реальными данными; парсер capture template исправлен; entrypoint per-file merge seed; локальный preview готов в Downloads/.

**Что в production:** commit `f95084d28` (требует Railway Redeploy если auto-deploy off). После redeploy entrypoint попытается seedить недостающие memory/*.md файлы (existing user content не трогает).

### 🛣 Roadmap для следующих сессий (зафиксировано user'ом 2026-05-19)

**Направление 1 — `/dashboard` skill (CEO Executive Cockpit v2)**
Не retrospective как `/report`, а forward-looking cockpit. См. decisions.md `[2026-05-19] ceo-executive-dashboard-v2`.
Ключевые секции: Top-of-mind today, Backlog надиктованного (`/capture task:` за 30 дней), Weekly Plan, Active projects with progress, Risks watching, Health trend, Decisions log, Quick capture reminder.
**Trigger для старта:** user скажет «делаем dashboard» или после ≥1 недели использования текущего /report.

**Направление 2 — `/intel week` skill (Weekly Intelligence Report)**
Конкуренты + макроэкономика MD/RO/EU + рынок мебели. Phase 4 блюпринта. См. decisions.md `[2026-05-19] weekly-intelligence-report`.
**Pre-requisites перед стартом:**
  1. Brave Search MCP + Tavily MCP подключены (config в ~/.claude/config/mcp/)
  2. User даёт список: 10-15 конкурентов + 10-15 macro/news источников (URL/RSS)
  3. Phase 1 Memory Hub стабилен (≥2 недели без багов)
**Trigger для старта:** user готов диктовать список источников.

### 🧪 Что user будет тестить в процессе (без помощи Claude)
- Daily: `/brief` утром, `/evening` вечером
- Weekly: `/week` в воскресенье, `/report week` в понедельник
- Ad-hoc: `/capture task: ...` голосом / текстом
- Inspect: `/projects`, `/risks`, `/find <query>`, `/menu`
**Если что-то ломается:** user возвращается с конкретным "вот это сломано" — Claude чинит.

### 📋 Open TODOs (carry-over)
- [ ] User: revoke leaked Railway tokens (4 шт) на https://railway.com/account/tokens
- [ ] User: install Railway GitHub App для auto-deploy (Settings → Source → Connect GitHub App)
- [ ] User: заполнить memory/memory.md::Active Priorities через `/capture task:`
- [ ] Cron job для Monday 08:00 weekly report (user попросит бот в Telegram)
- [ ] Roadmap: `/dashboard` skill (Направление 1 выше)
- [ ] Roadmap: `/intel week` skill (Направление 2 выше)
- [ ] Stage 5c: `/cleanup` skill (memory hygiene proposals)
- [ ] Stage 7: GitHub backup automation (private repo + cron 00:30)
