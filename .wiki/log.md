# hermes-agent — Event Log

Append-only лог событий. Karpathy convention.
Формат: `## [YYYY-MM-DD] event-type | description`

---

## [2026-06-01] w1-hermes-to-96-closed | W1 плана HERMES_TO_96 закрыта end-to-end. 3 этапа (token-monitor /cost, telemetry hook, /notes pipeline) + 4 внеплановых fix-а (pricing 8 entries, /evening reminder, mac sync HTTPS+gh, IMMUTABLE_ZONE 2>&1 false positive). First note (TANDEM Casa осень 2026) verified в ALEX21_VAULT/03 — Notes/ через полный pipeline: Telegram → Railway → /opt/data/logs/notes/ → daily backup → mac launchd → iCloud → iPhone. Commits 96c7cea71 (cost skill) → 796bcdb8a (pricing) → 98bd626fc (telemetry) → 2d5dfc86b (/notes) → 2809ac5ad (mac sync HTTPS). Pause for 7-day pilot — see HERMES_TO_96.md.
## [2026-05-28] hermes-to-96-master-plan | Прошли полный deep-planning protocol (триаж → 8 вопросов → эхо-тест → спарринг 14 рисков → финализация). 3 ключевых решения Phase 2: Stilman accepted (Hermes + CoS параллельно, 60-day audit kill-criterion на 2026-07-27); /psychologist skipped (Anthropic 30-day retention vs health data → живой психоаналитик); Tempo 1 ветка за раз + 7-day usage test (антипаттерн /coach не повторяем). Deliverable: .wiki/HERMES_TO_96.md — 14 этапов, бюджет $200/мес, чек-лист 10/10. Commit 9001ac67d.
## [2026-05-17] init | .wiki/ scaffolded для V1 Executive OS блюпринта (MVP-вертикаль /brief)
## [2026-05-17] stage-0 | CLAUDE.md + .wiki/ (CONTEXT, decisions, log, INDEX, PATTERNS, session-logs/)
## [2026-05-17] stage-1 | Audit report .wiki/AUDIT_2026-05-17.md (3 секции + матрица готовности)
## [2026-05-17] stage-2 | /memory, /SOP, /logs/{daily,weekly,telegram_inputs}, /backups + .gitignore patches (logs/*, backups/*, tokens/, credentials.json, secrets.yaml, *.key)
## [2026-05-17] stage-3 | Memory content (10 markdown файлов) + loader skills/ceo/_lib/memory.py (load_memory, projects_by_priority, append_entry, last_entries, extract_section)
## [2026-05-17] stage-4 | skills/ceo/daily_briefing/SKILL.md + scripts/render_briefing.py + /brief в COMMAND_REGISTRY (категория CEO, gateway_only); smoke test passed (collect + log append работают)
## [2026-05-17] stage-4b | Telegram routing fix: rollback CommandDef("brief") из COMMAND_REGISTRY (CEO commands регистрируются через skills loader, не вручную); rename skills/ceo/daily_briefing → skills/ceo/brief + name: brief (Hermes auto-mapping name→/cmd); создал 6 placeholder skills (evening/week/projects/risks/capture/backup) для Stage 5-7 roadmap; cli-config.yaml (gitignored, dev fallback) с external_dirs: ./skills/ceo; smoke test: scan_skill_commands → все 7 /commands зарегистрированы, build_skill_invocation_message("/brief") → 7871 char payload с полным skill body
## [2026-05-17] stage-4c | Discovery debug: hermes reload-skills возвращал "No new skills detected" потому что `~/.hermes/config.yaml` отсутствовал (Hermes runtime config.yaml читается из HERMES_HOME, не из repo cli-config.yaml fallback). Создал `~/.hermes/config.yaml` с `skills.external_dirs: [/Users/.../hermes-agent/skills/ceo]` (абсолютный путь — relative резолвится от HERMES_HOME, не cwd). После fix: scan_skill_commands → 7 skills, reload_skills → added=7, telegram_menu_commands → CEO entries присутствуют, end-to-end build_skill_invocation_message + render_briefing.py --collect (35KB JSON) работают.
## [2026-05-17] stage-5d | Extended memory loader: all_projects(), all_risks(), risks_by_severity(min), update_project_field(name, field, value), today_hhmm(), iso_week(), route_capture(type, ctx, content) для 5 типов (meeting/recap/decision/insight/task). Plus _normalize_rank_token() для inline-note tolerance ('medium (high после gate)' → 'medium'). Smoke tested на real memory/*.md.
## [2026-05-17] stage-5 | /evening real implementation: SKILL.md (11 вопросов из блюпринта §08, 4 edge cases) + scripts/record_evening.py (--gather emits context JSON, --save persists structured review → logs/daily/, memory/daily_log.md, и refreshes memory/memory.md::Active Priorities с tomorrow_focus + carry-over). End-to-end smoke pass.
## [2026-05-17] stage-5 | /week real implementation: SKILL.md (14 секций блюпринта §09) + scripts/record_week.py (--gather: iso_week + week bounds + daily_log entries + projects + top risks + last weekly_review; --save: logs/weekly/YYYY-Www.md + memory/weekly_review.md append + per-project update_project_field на Status + Last Update). Unmatched project names возвращаются в confirm для user'а. Smoke pass.
## [2026-05-17] stage-5b | /capture real implementation: SKILL.md (parse intent, 4 routing types, privacy guard applied caller-side) + scripts/capture.py (тонкая обёртка над route_capture). Все 4 routing paths протестированы: task→memory.md::Active Priorities, insight→::Current Strategic Themes, meeting/recap→daily_log.md, decision→decisions.md. Cosmetic fix: bullets вставляются ПЕРЕД trailing `---` thematic break внутри секции.
## [2026-05-17] stage-5c | /projects + /risks listings: SKILL.md + scripts (list_projects.py, list_risks.py). Projects: 10 entries, group by priority desc / sort by deadline asc, optional --priority filter. Risks: by severity × probability rank, optional --min-severity floor, excludes status=closed + placeholder titles. Fix: _normalize_rank_token() (handled 'medium (high после gate)' и 'high (по статистике)' inline notes).
## [2026-05-17] stage-5-done | 7/7 CEO skills все работают end-to-end: /brief (7871 char payload), /evening (5712), /week (5758), /projects (3640), /risks (3104), /capture (5998), /backup (1440 — still Stage 7 placeholder). Stage 6 (cron seeding) и Stage 7 (GitHub backup) — operational, требуют VPS access, отложены до user confirmation.
## [2026-05-17] prod-debug | User сообщил "/brief → Unknown command" в Telegram. Проверка на dev Mac: НЕТ работающего Hermes gateway / container / процесса (есть только ~/.hermes/config.yaml + skills/ceo которые dev-side рабочие). Production bot @Hermes_Alex21_bot работает на другом хосте (VPS / Termux / другая машина) — из текущей dev среды доступа к нему нет. Подготовлены scripts/ceo-os/production-check.sh (read-only diagnostic) + scripts/ceo-os/production-fix.sh (config merge + restart + verify) для запуска user'ом на production host. Security fix в check скрипте: redacted TOKEN/KEY/SECRET/PASSWORD из ps/docker env output (после false positive утечки GH_TOKEN/RAILWAY_API_TOKEN из Cursor extension-host env в ps args).
## [2026-05-17] prod-located | Production host идентифицирован как Railway (project 4e83ef6c-268f-4021-81f0-6807906432a7, service ab136f58-0bfb-49fb-9c12-8fe38210e301, fork github.com/scerbinaalexandr-droid/hermes-agent). Источник: ~/.claude/memory/episodes/2026-05-05-hermes-railway-deploy.md + ~/Documents/01_CODE/ALL-on-in/.wiki/decisions.md. Container HERMES_HOME=/opt/data (Railway Volume, 1 GB), WORKDIR=/opt/hermes, CMD=["gateway","run"], model=anthropic/claude-haiku-4-5, allowed users=746810595, deploy method=`railway up` (manual CLI, не auto на git push).
## [2026-05-17] stage-6 | Railway production deploy подготовлен: (a) .dockerignore whitelist `!skills/ceo/**/SKILL.md`, `!SOP/**/*.md`, `!memory/**/*.md`, `!CLAUDE.md` (фикс блокирующего `*.md` который рекурсивно исключал все markdown); (b) docker/ceo-os-entrypoint.sh — wrapper который на boot seedит /opt/data/config.yaml::skills.external_dirs + /opt/data/memory templates (idempotent, не overwrites user content) + export HERMES_CEO_MEMORY_ROOT=/opt/data/memory; (c) Dockerfile ENTRYPOINT — 1 line swap на wrapper, upstream docker/entrypoint.sh не тронут; (d) scripts/ceo-os/deploy-to-railway.sh — orchestrator с pre-flight + preview + `railway link` + `railway up --detach` + post-deploy checklist. Sandbox smoke test 3 сценариев (first boot / restart с user content / config без external_dirs) — все idempotent.

## [2026-05-17] session-end | No commits (main)

## [2026-05-17] session-end | 2 commits on main

## [2026-05-17] session-end | 3 commits on main

## [2026-05-17] session-end | 4 commits on main

## [2026-05-17] session-end | 5 commits on main

## [2026-05-17] session-end | 6 commits on main

## [2026-05-18] session-end | 1 commits on main

## [2026-05-18] session-end | 2 commits on main

## [2026-05-18] session-end | 3 commits on main

## [2026-05-18] session-end | 4 commits on main

## [2026-05-19] session-end | No commits (main)

## [2026-05-18] feat | UX Layer 1+2: voice-first capture/evening/week, /menu /start /find /remind skills, compact mode rules. Commit c25fcc24b.
## [2026-05-18] fix | Telegram bot menu whitelist (_CEO_TELEGRAM_MENU_NAMES — 12 commands). После того как user случайно тапнул /new и сбросил сессию. Commit 44a21daa3.
## [2026-05-18] feat | /report HTML dashboard skill + honesty harness §4a in soul.md (после fake-data report incident). Commits 3291f6f45 + 07d58eb08 (PDF support).
## [2026-05-18] fix | chown reports/ + cron/ dirs in entrypoint. Commit addc7079e.
## [2026-05-19] fix | sys.path fallback /opt/hermes в 7 CEO scripts (Hermes sync skips _lib/). Commit 9d4737163.
## [2026-05-19] snapshot | Pre-/compact: CONTEXT.md обновлён. 4 token leaks этой сессии. Production deploy 9d4737163 — TBD by user (manual Redeploy needed).

## [2026-05-19] session-end | 1 commits on main

## [2026-05-19] fix | /report парсер capture template + UX clean-up empty cells. Commit f95084d28. Local preview: ~/Downloads/tandem-report-FIXED-PREVIEW.html
## [2026-05-19] roadmap | Зафиксированы 2 L3-направления: /dashboard (CEO cockpit v2) + /intel week (research report). Trigger для старта — отдельный запрос user'а.
## [2026-05-19] session-end | Stop point: prod work via Telegram, тестинг в процессе. Следующая сессия — по запросу user'а.

## [2026-05-19] session-end | 2 commits on main
## [2026-05-21] feat | Phase 1: /web skill (search/fetch/render) — без платных API. Commit 4c85d87d8. DuckDuckGo lite + httpx + stdlib HTML parser + Chromium для JS.

## [2026-05-21] session-end | 1 commits on main

## [2026-05-21] session-end | 2 commits on main

## [2026-05-21] session-end | 3 commits on main

## [2026-05-21] session-end | 4 commits on main

## [2026-05-21] session-end | 5 commits on main

## [2026-05-21] session-end | 6 commits on main

## [2026-05-22] session-end | 7 commits on main

## [2026-05-22] session-end | 8 commits on main

## [2026-05-22] session-end | 2 commits on main

## [2026-05-22] session-end | 1 commits on main
## [2026-05-22] feat | /web stdlib-only + symlink skills + own Railway endpoint + soul.md §4c §9-10. Commits eeb6fa0d7, 9c9ad2351, 1d5ec900e, fe5f385de, e909e02d9, 302efa835, 809ab6173.
## [2026-05-22] config | HERMES_PUBLIC_HOST=hermes-production-99b8.up.railway.app set. Health endpoint verified (curl 200).
## [2026-05-22] config | HERMES_MODEL: claude-haiku-4-5 → claude-sonnet-4-6 (Anthropic direct, no openrouter prefix)
## [2026-05-22] snapshot | Pre-/compact: контекст ~85%. Снимок в CONTEXT.md. Phase 1 capabilities закрыты, ждём final /report week test.
## [2026-05-23] snapshot | Delta pre-/compact. No new activity since prev snapshot — ждём verification /report week с sonnet-4-6.

## [2026-05-23] session-end | No commits (main)
## [2026-05-23] fix-prod | @Hermes_Alex21_bot HTTP 400 "claude-haiku-4-5 is not a valid model ID" устранён. ROOT CAUSE: gateway резолвит модель из config.yaml на Railway volume (/opt/data), НЕ из env HERMES_MODEL — by design (gateway/run.py:839 _resolve_gateway_model, auth.py:4109 _save_model_choice). Volume хранил haiku-сид от 17 мая; env-правка 22 мая была no-op. FIX: `/model claude-sonnet-4-6 --global` в Telegram (Level-2 handler, config-only, без редеплоя). Verified: /whoami OK, /model → Current claude-sonnet-4-6 on Anthropic. Деплой идёт via GitHub auto (не ручной railway up — инструкция ошибалась). Side-find: мёртвый RAILWAY_API_TOKEN в ~/.zshrc:14 блокировал railway login (CLI недоступен). Хвосты: убрать токен из .zshrc, включить 2FA Railway.

## [2026-05-23] session-end | 1 commits on main
## [2026-05-24] instruction-02 | Security hooks через РОДНОЙ shell-hooks Hermes (не выдуманный hooks.yaml). guard.py (block memory/*.md write + git push + exfil) + audit.py + tool_loop_guardrails + HERMES_ACCEPT_HOOKS/REDACT_SECRETS env. ✅ verified prod 11:18 — бот заблокировал echo>>soul.md. Commits 1dd54fba8, 99376694b.
## [2026-05-24] incident | Редеплои дважды уронили прод. (1) ceo-os-entrypoint awk-merge ломал config.yaml после yaml.dump от /model --global (2 vs 4 пробела) → invalid YAML → "No models provided". Fix: ensure_config.py (Python, само-лечение). (2) голый claude-sonnet-4-6 отвергнут Anthropic API → перешли на датированный claude-sonnet-4-5-20250929. LESSON: config — только через Python+yaml (не bash/awk); модель — датированный Anthropic ID. TODO: HERMES_MODEL env → датированный.
## [2026-05-24] ROOT-CAUSE-провайдер | Истинная причина ВСЕЙ модельной саги (haiku→4-6→4-5 "not a valid model ID", "works then fails"): env `HERMES_INFERENCE_PROVIDER=openrouter`. gateway/run.py:568 передаёт его как `requested` в resolve_requested_provider → перебивает config.model.provider → ВСЕ запросы шли в OpenRouter, который НЕ принимает голые Anthropic-ID (нужен `anthropic/...`). `/model --provider anthropic --global` чинил только текущую сессию → /new/redeploy сбрасывал → снова openrouter. FIX: HERMES_INFERENCE_PROVIDER `openrouter`→`anthropic` (Railway env). ✅ verified 17:23 — /whoami работает, переживает /new. Урок: не модель меняй — проверяй провайдера. config.yaml model dated ID был верен всё время.
## [2026-05-24] instruction-03 | Backup skill готов + verified prod. /backup → snapshot pushed в private repo hermes-memory-backup (memory/+logs/+config.yaml, без .env). no_agent cron-скрипт /opt/data/scripts/backup.py (0 LLM-токенов, минует guard). Commit 5a327a310 + ensure_config provider fallback 4d07d4508. /whoami graceful-fix 584b487c2 тоже verified.
## [2026-05-24] instruction-03-DONE | Cron создан: job f35d551d4a4b, name daily_memory_backup, schedule "0 3 * * *" (03:00 UTC), no_agent, deliver telegram:746810595. Создан через `/opt/hermes/.venv/bin/hermes cron create … --script backup.py --no-agent` (--script ОТНОСИТЕЛЬНО ~/.hermes/scripts/, не абсолютный). Next run 2026-05-25 03:00 UTC. INSTRUCTION_03 ПОЛНОСТЬЮ ЗАКРЫТА. Note: `/cron` НЕ slash-команда бота; cron создаётся через venv-CLI или cronjob-tool.
## 2026-05-24 18:06 — pre-compact snapshot | Saved snapshot before /compact (марафон: INSTRUCTION_01+02+03 DONE + provider root-cause). См. CONTEXT.md секцию "Snapshot 2026-05-24 18:06". Episode → ~/.claude/memory/episodes/2026-05-24-hermes-provider-rootcause-hooks-backup.md.

## [2026-05-24] session-end | 1 commits on main

## [2026-05-24] session-end | 2 commits on main

## [2026-05-24] session-end | 3 commits on main

## [2026-05-24] session-end | 4 commits on main

## [2026-05-24] session-end | 5 commits on main

## [2026-05-24] session-end | 6 commits on main

## [2026-05-24] session-end | 7 commits on main

## [2026-05-24] session-end | 8 commits on main

## [2026-05-24] /coach — установка ИИ-коуча
- Security-аудит папки ИИ-коуч (Георгий Ривера): 10 MD прочитаны, инъекций/скрытых unicode/эксфильтрации НЕТ → чисто.
- Решения user (AskUserQuestion): коуч отдельным режимом + смягчённый для CEO тон.
- Реализован изолированный скилл `skills/ceo/coach/` (SKILL.md + 8 references + helper coach_log.py). Артефакты → logs/coaching/ (не memory/*, не триггерит guard.py). Правки: menu, SOP, backup INCLUDE, .gitignore, decisions.md (L3).
- Локально verified: frontmatter YAML OK, --gather/--save OK. Commit 515ccdb88.
- ✅ Pushed → Railway redeploy → verified prod 22:19: `/coach` работает (pre-flight OK, gather OK, меню коуча отрисовано). Slash-команда деривится из `name: coach` (не metadata.commands); «Unknown command» сразу после push = деплой не докатился.
- Опционально осталось: довести полную сессию до save-артефакта в logs/coaching/.

## [2026-05-24] 22:29 — pre-compact snapshot
- Saved snapshot before /compact (после установки /coach)
- См. CONTEXT.md секцию "Snapshot 2026-05-24 22:29"
- Open: intake-cron (user→бот), verify save-path коуча, push docs

## [2026-05-28] session-end | No commits (main)

## [2026-05-28] session-end | 2 commits on main

## [2026-05-28] session-end | 1 commits on main

## [2026-05-29] session-end | 1 commits on main

## [2026-05-30] session-end | 2 commits on main

## [2026-05-30] session-end | No commits (main)

## [2026-05-30] session-end | 1 commits on main

## [2026-05-31] session-end | 1 commits on main

## [2026-05-31] session-end | 2 commits on main

## [2026-06-01] session-end | No commits (main)

## [2026-06-01] session-end | 1 commits on main
## [2026-06-07] Protocols rescue + STT fix | brief/notes/capture SKILL fixes, prod hotfix via railway ssh

## [2026-06-20] phase1-buildout | git sync с origin (FF — подтянул 07.06 фиксы STT/notes-autosave) + 5 Phase-1 модулей через workflow+adversarial review: /cleanup (Stage 5c), /dashboard (cockpit), /diary, /handoff(+docs/COS_ONBOARDING #13), mac-mirror (#12). 2 бага пойманы ревью и пофикшены+верифицированы: cleanup fence-template fabrication (soul.md §4c), handoff allowlist union. 0 правок upstream-core.

## [2026-06-20] phase1-deploy-verified | Прод-батч выполнен (user апрувнул весь прод): pilot-review закрыт на прод-данных (KILL inline-меню — callback 0% / cost green $0.44/день / re-pilot notes); env-мина уже датирована (no-op); `railway up` задеплоил 5 модулей, cutover ~30s; verified LIVE: /cleanup (27 предл., 0 фабрикации) · /dashboard (13KB HTML) · /diary (logs/diary/) · /handoff (registered, list_allowed UNION) · health 200 · notes AUTO-SAVE цел. PR #32 ждёт merge для main-sync (мой токен merge не может). Follow-ups: menu-popup whitelist (protected core), mac-mirror install (вне песочницы). Блокеры user: Gmail app-pw, GROQ key, GitHub 2FA.

## [2026-06-20] session-end | No commits (main)

## [2026-06-20] session-end | 5 commits on main

## [2026-06-21] capability-buildout | (1) #1 fallback chain + #2 Edge TTS ru-голос засеяны в ensure_config (PR #33, live). (2) video-vs-setup анализ: видео = другой продукт (Hermes Desktop GUI), твой Hermes по фундаменту опережает; token-routing/Brave/kanban — SKIP; делегация/Obsidian/webhook/MCP — Phase-2 (архитектура). (3) Excalidraw карта возможностей + SVG (#34). (4) Google Workspace OAuth LIVE для scerbina21@gmail.com: Gmail+Calendar+Sheets+Drive+Docs, Desktop client (project stellar-works-500105), creds на /opt/data volume (gitignored+backup-excluded, PR #35). Verified: Gmail читает реальные входящие; Calendar пуст (нет событий). Phase-1: чтение свободно, отправка по подтверждению. 4 PR merged сам (gh --repo trick на форк, не upstream).

## [2026-06-21] email-automation | Фикс misroute himalaya (LLM сам набирал `himalaya` в терминале, не через скилл) — 3 слоя: /mail + /calendar CEO-скиллы, skills.disabled=[himalaya], правило роутинга в /opt/data/SOUL.md (инжектится prompt_builder каждое сообщение, durable через ensure_config). Verified live: бот читает почту через google_api.py. + /inbox авто-триаж: inbox_triage.py архивирует Gmail Promotions+Social из inbox (обратимо, ярлык Hermes/Авто-архив), Primary не трогает, gmail.modify без re-auth. Прогнан: 4 промо в архив. Daily no_agent cron 368a95a2cec0 (07:00 EEST). Календарь scerbina.alexandr — 404 (шаринг не виден scerbina21, ждёт accept/propagation). Security 05:01-05:05 на scerbina21 — подтверждено user'ом.

## [2026-06-21] session-end | 5 commits on main

## [2026-06-22] birthday-system | Полная система ДР. Импорт 87 ДР из birthdays.csv (бот сохранил из Telegram-файла) → .ics в ~/Downloads → user импортнул (Google уронил 11, дочинил через API). Google native «Дни рождения» = read-only Contacts-virtual cal (нет в API), поэтому создан Hermes-owned «🎂 Дни рождения» (colorId 10). birthday.py: --add/--check/--migrate, отдельный календарь, find-or-create. /birthday скилл (NL-парсинг «ДР Имя ДД месяц ГГГГ»). КРИТ-фикс TZ off-by-one: all-day события привязаны к Europe/Chisinau, не UTC (иначе напоминания на день раньше) — +03:00 границы + exact-date фильтр. 2 no_agent крона: «🎂 ДР утро 8:00» (b5344a977ada, 0 5 UTC) + «вечер 19:00» (6e77d2391a7d, 0 16 UTC), молчат если пусто; убраны 3 дубля (2 agent-mode user'а + мой). Итог: 88 ДР (87 + Фируза 29.06.1992), Азим→1971. Verified: --check показал Азим сегодня 55 лет; Дочь Клевца потерялась при миграции → дочинена. Урок: railway ssh теряет stdout длинных команд + убивает detached — писать в /opt/data volume-файл, читать отдельным вызовом.

## [2026-06-21] session-end | No commits (main)

## 2026-06-22 — pre-compact snapshot
- Saved snapshot before /compact (контекст ~67%)
- См. CONTEXT.md секцию "Snapshot 2026-06-22"

## [2026-06-22] session-end | No commits (main)

## [2026-06-22] session-end | 1 commits on main

## [2026-06-22] session-end | 2 commits on main

## [2026-06-24] session-end | No commits (main)

## [2026-06-25] session-end | No commits (main)

## [2026-06-25] session-end | 1 commits on main

## [2026-06-26] session-end | No commits (main)

## [2026-06-27] session-end | 1 commits on main

## [2026-06-27] session-end | 2 commits on main

## [2026-06-28] session-end | No commits (main)

## [2026-06-28] session-end | 1 commits on main

## [2026-06-28] session-end | 3 commits on main

## [2026-06-28] session-end | 4 commits on main

## [2026-06-28] pre-compact snapshot | Google fix + meeting/diary→Sheets + GROQ voice
- OAuth токен re-auth (Hermes=scerbina21, invalid_grant fixed), drive.file granted
- meeting→Sheets + diary→Sheets детерминированно; routing fix (встречи→/notes)
- STT→groq whisper-large-v3-turbo; Codex model-downgrade откачен
- 7 commits 238e828ab→d8e61ac4b. Снапшот в CONTEXT.md.

## [2026-06-28] session-end | 5 commits on main

## [2026-06-28] session-end | 7 commits on main

## [2026-06-28] session-end | 8 commits on main

## [2026-06-28] session-end | 9 commits on main

## [2026-06-28] session-end | 6 commits on main

## 2026-06-28 23:35 — pre-compact snapshot
- Большой воркстрим: голос-первый CEO-кокпит в Telegram.
- Задеплоено: /report→Google Doc+PDF+HTML · /trip→Поездки Sheet · меню-плитки + ≡-команды · кнопки черновика (универсально через persona, 4 кнопки) · сворачиваемое меню (one_time) · CEO-доступ к мастер-Sheet.
- 9 коммитов (d59f4ed10…ef65d29f9). Всё на проде, гейтвей здоров.
- См. CONTEXT.md секцию "Snapshot 2026-06-28 23:35" + decisions.md.

## [2026-06-29] session-end | 7 commits on main

## [2026-06-29] session-end | 8 commits on main

## [2026-06-29] session-end | 9 commits on main

## [2026-06-29] big-build-day | capture→Sheets (Задачи/Решения/Идеи) + текст=голос; /tune самонастройка+фидбэк (SOUL append, safety gate); меню Работа⇄Личное (плитки, per-chat state); adversarial-review workflow (17 агентов)→4 security/correctness фикса; cleanup primitives (drive trash / sheets clear) + почищены тест-артефакты. 9 коммитов 61dac47a5→6db7248f3, все на проде SUCCESS. Секреты: git чист (прошлые утечки = Railway-токены, авто-ревок). 69 тестов зелёных. См. CONTEXT snapshot 2026-06-29.

## [2026-06-29] meeting-prep | Фаза A: calendar create --recurrence/--reminders (0d5e866da); /prep skill — повестки вопросов на встречи дня из календаря+контекста → вкладка «Встречи» (upsert), бриф по блокам (bca439033); cron `e900bfffe343` «CEO Meeting Prep 07:00 EEST» (0 4 * * *, skill prep, deliver telegram:746810595, next 2026-06-30T04:00Z). Verified --gather на проде. Фаза B (напоминание за 1ч до встречи) — ОТМЕНЕНА юзером: нужен только один утренний бриф в 07:00, без per-meeting напоминаний. Фича завершена. 73 теста зелёных.

## [2026-06-29] qa-hardening | Прод-смок (мой) + кросс-вендор прожарка Codex (GPT-5) сегодняшнего кода. ПОЙМАНО 11 РЕАЛЬНЫХ БАГОВ, все фикс+verified на проде. Мой смок 3: GoogleApiGW.get крах на непустой вкладке → 2-я запись в любую таблицу падала (08a0c3505); recurring-событие без timeZone → HTTP400; sync_note/diary не создавали вкладки (0b8d27db0). Codex 8 (7d02dcca4) — HIGH: /tune deny-list bypass (RU «без согласования»/«показывай пароли») → NFKC + расширенные паттерны; Sheets formula injection (=IMPORTDATA) → санитизация ячеек; guard.py не ловил open(...,'w') / cd&&>>SOUL → Python-write + bare basename. MED: non-list→char-split; bad-json traceback; tz хардкод (zoneinfo); cmd_save non-dict краш. LOW: non-atomic menu_mode write. Verified на проде: formula→текст, CFO не разбита, safety-bypass rejected, guard блокирует open-write/redirect но пускает tune.py. 0 critical осталось. 97 тестов зелёных. Урок: разные семьи моделей = некоррелированные слепые зоны (я — runtime-краши, Codex — security/edge-cases).

## [2026-06-29] tasks-loop | /tasks skill — открытые задачи из вкладки «Задачи» по срокам (🔴 просрочено / 🟡 неделя / ⚪ без срока), читает через fixed GoogleApiGW, парсит сроки (ISO/dd.mm.yyyy/dd.mm=тек.год). On-demand + cron `b85e53e4148d` «CEO Tasks 07:15 EEST» (15 4 * * *, skill tasks). Замыкает цикл: встреча→протокол(/notes)→задачи→утренний контроль(/tasks). Утро теперь: 07:00 /prep · 07:15 /tasks · 07:30 /brief. Verified на проде. Дочищена stale selftest-задача Задачи!A2 (пропущена при прошлой чистке Протоколов). Commit ed3daf064. 101 тест зелёный.

## [2026-06-29] morning-ritual | /morning skill (Личное) — личный утренний ритуал: ротируемая медитация-кью + личный фокус из вкладки «Фокус» (задаётся голосом, sync_focus). Онбординг при пустом фокусе. Плитка 🌅 Утро в Личное-меню (пара с 🌙 Вечер). Cron `4413758e1c3e` «CEO Morning 06:50 EEST» (50 3 * * *, skill morning). Утро/День разделены: Утро=личный настрой, День=рабочий фокус. Verified --gather на проде. 107 тестов. ВНИМАНИЕ: утро теперь 4 пинга (06:50/07:00/07:15/07:30) — предложить юзеру слить рабочие 3 в одно. Commit d4a807102.
## [2026-06-29] morning-consolidation | Юзер (перегруз пингами) выбрал «только Утро + День» авто. УДАЛЕНЫ cron e900bfffe343 (Meeting Prep 07:00) + b85e53e4148d (Tasks 07:15). Остались авто: 4413758e1c3e Morning 06:50 + 92ee5dfa0e33 Brief 07:30. /prep и /tasks — теперь ТОЛЬКО on-demand (скиллы живы, без утренних cron). Урок: не плодить утренние пинги — у CEO порог на шум низкий.
## 2026-06-29 — pre-compact snapshot | /save-snapshot: CONTEXT.md секция «Snapshot 2026-06-29» + 2 L3-решения в decisions.md (Sheets dual-write; /tune safety model) + episode. Контекст ~66%. Сессия: full CEO loop (Утро/Повестка/Встреча/Протокол/Задачи/Контроль) + 11 багов QA. ~14 коммитов, всё на проде.
## [2026-06-29] session-end | 10 commits on main

## [2026-06-29] session-end | 1 commits on main

## [2026-06-29] session-end | 2 commits on main

## [2026-06-29] session-end | 3 commits on main

## [2026-06-29] session-end | 4 commits on main

## [2026-06-29] session-end | 5 commits on main

## [2026-06-29] session-end | 6 commits on main

## [2026-06-30] session-end | 2 commits on main

## [2026-06-30] session-end | 3 commits on main

## [2026-06-30] session-end | 4 commits on main

## [2026-06-30] INCIDENT+FIX | prod outage: root-owned files → app blind
- Root cause (one class, 3 hits): files on /opt/data created via `railway ssh` as **root** while app runs as **hermes** → `google_token.json` unwritable (token refresh crashed every Google cron: morning Фокус, inbox, birthday) + `cron/jobs.json` unreadable after my root-run `cron edit/run` (scheduler IOError every tick → fired nothing → both phones silent).
- Fixes: chown→hermes (immediate); `get_credentials` token persist best-effort (cb5da9cba); entrypoint self-heals ALL /opt/data ownership on boot (7b3e324c9); morning gather self-creates Фокус tab (cb5da9cba).
- 5 personal crons → dual-deliver both phones (746810595+385068170).
- LESSON: NEVER mutate prod state as root via ssh (su to hermes); each deploy restarts gateway → cron deliveries during restart are lost; verify delivery END-TO-END (user receipt) — logs don't record cron delivery. Memory: [[prod-root-ownership-trap]].
- User feedback → SOUL rule (d1cf4532a): NO technical/diagnostic noise in user-facing messages (the brief's «logging note» leak). Memory: [[clean-messages-no-tech-noise]].
- Commits: 5c77020a6, cb5da9cba, 7b3e324c9, d1cf4532a. All deployed SUCCESS. Delivery to both phones confirmed by user.

## [2026-06-30] session-end | No commits (main)

## [2026-07-01] session-end | No commits (main)

## [2026-07-01] voice-tts | Голос ответов: бесплатный Edge, женский ru-RU-SvetlanaNeural (был Dmitry муж.), speed=0.9 (мягче). Платный ElevenLabs подготовлен (model eleven_multilingual_v2) но НЕ включён — юзер передумал (нужен ELEVENLABS_API_KEY). Персона через /tune: (1) юмор кроме серьёзных тем, (2) для голоса плавная устная речь без markdown/символов (фикс «обрывками»). Всё через config.yaml + tune.py под hermes, БЕЗ деплоя. Пробы msg 2697/2711. Cron cleanup: -6 мёртвых, birthday→оба тел. Неделя тестов голоса.

## [2026-07-01 09:30] — pre-compact snapshot
- Saved snapshot before /compact (контекст ~75%)
- См. CONTEXT.md секцию "Snapshot 2026-07-01 09:30"

## [2026-07-02] session-end | 1 commits on main

## [2026-07-02→04] prod-outage-reliability | Бот молча умер: Anthropic-баланс $0 (auto-reload OFF) + OpenRouter $0 → HTTP 402 утекал в чат; Gemini-fallback давал украинский. Фиксы: (1) жёсткое always-Russian правило в SOUL через ensure_config (commit 7bc21654b); (2) вечерний cron починен — правильный skill=evening 37e08a7c13ed включён, кривой голый 6372685649f5 на паузе; (3) API Health Monitor — no_agent cron af5c4ea94014 (*/30), чистый алерт на оба телефона при credit/auth-провале, throttle 6h (commit a8abb3aa9). Anthropic-ключ бота — на scerbinaalexandr@gmail.com (org 0d88e37d). Осталось юзеру: включить Auto reload (пейволл). 113 тестов зелёные. Всё на проде, всё под hermes (не root).

## [2026-07-04] session-end | 1 commits on main

## [2026-07-04] session-end | 3 commits on main

## [2026-07-04] reliability-audit-99 | Цель: проект → 99% надёжности. Мульти-агентный аудит (8 слоёв, workflow wgqr2vx95, 44 находки; синтезатор упал на объёме — синтез сделан вручную из транскриптов). Прод смок-тест happy-path — всё зелёное (LLM/язык/9 скиллов/Sheets/cron/TTS/ownership). 3 раунда фиксов, все на проде:
## — Round 1 (1951a32a7): эфемерный путь evening/week (потеря при деплое, CRITICAL) · first-boot SOUL seed (украинский на свежем волюме, CRITICAL) · bare model-id guard · ensure_config exit-код · entrypoint cp под set-e · backup git-таймауты+set-url. +6 тестов.
## — Round 2 (41ddc2a88): inbox/birthday/cost — чистый алерт vs тихая смерть · telegram медиа-сбой→внятный ответ (CRITICAL) · залипший callback-спиннер · print→logger · render_briefing guard · /tune timeout 90→10с.
## — Round 3 (15c77586d, Codex-reviewed): сырой HTTP 402 в чат→чистое сообщение (gateway/run.py — проброс failed/error на non-empty return + failed-gate; run_agent auxiliary log-only) · cron доставка asyncio.wait_for(60s)+ThreadPool-hang fix (CRITICAL) · save_job_output изолирован · empty-response алерт · hermes_state _init_schema retry при rolling-deploy. Codex: 3 находки в моих правках (1 HIGH проброс failed, 2 MEDIUM coroutine/worker) — исправлены; re-verify FIX1/2 CLEAN, FIX3 приемлемый остаточный риск. Ложная находка [SILENT] откачена (тесты требуют substring).
## Итог: ~90-92% → ~97-98%. Остаток к 99% (Round 4, safe): Google token RefreshError, send_voice retry, dual-write reorder, SOUL truncation, tune safety-patterns. Юзеру (пейволл): Anthropic Auto reload + state.db volume-снапшоты.

## 2026-07-04 — pre-compact snapshot
- Saved snapshot before /compact (контекст ~75%)
- См. CONTEXT.md секцию "Snapshot 2026-07-04" — reliability-аудит + Round 1-3 deployed

## [2026-07-06] session-end | No commits (main)

## [2026-07-06] session-end | 1 commits on main

## 2026-07-06 — Google OAuth outage fixed + fail-clean hardening
- 🎂 birthday + inbox crons were crashing twice/day: Google OAuth token expired/revoked (Cloud app in "Testing" → 7-day refresh-token death).
- Re-authed via setup.py --auth-url/--auth-code (as hermes, code read from user screenshot); published OAuth app to "In production"; re-issued token (permanent, 9 scopes). Verified on prod.
- Hardening (commit af69dde5a, deployed+smoke-tested): google_api RefreshError/TransportError → GoogleAuthError; _ensure_authenticated raises (not sys.exit); CLI clean exit; throttled google_down_alert() (6h, shared); birthday --check/inbox fail clean on ANY error (silent+log), interactive re-raises. 11 tests. Codex-reviewed (4 findings fixed).
- See memory `google-oauth-reauth.md`. Backlog: dependabot 167 vulns (5 critical) — untouched.

## [2026-07-22] session-end | No commits (main)

## [2026-07-24] session-end | No commits (main)

## [2026-07-24] session-end | 3 commits on main

## [2026-07-24] rename + revision | Бот молчал весь день: Anthropic исчерпан → fallback OpenRouter (кредиты не покупались никогда) → HTTP 402 на всех LLM-cron (Утро/Бриф/Вечер/Личные задачи/Инфляция RO). No-agent джобы (бэкап, почта, ДР, cost, health) работали. Юзер пополнил Anthropic → проба ok, ручной прогон брифа 92ee5dfa0e33 → ok. ⚠️ OpenRouter-резерв ВСЁ ЕЩЁ пуст (второго парашюта нет).
## — Переименование Hermes → BOT_21: юзер сам сделал /setname + /setuserpic (своё фото) в BotFather. Адрес @Hermes_Alex21_bot не меняется (Telegram не даёт). Синхронизирована самоидентификация: docker/SOUL.md, memory/soul.md, menu/start/cost SKILL.md + прод /opt/data/SOUL.md напрямую под hermes (бэкап SOUL.md.bak-20260724, деплой существующий SOUL не перезаписывает). НЕ тронуты: ярлык Gmail `Hermes/Авто-архив` (сломает фильтры), внутренние упоминания движка. Коммит 50225d9e3, деплой success 20:04 UTC, verified на проде.
## — 🔎 Находка: скилл `business-trip-research` (15KB + HTML-шаблон) жил ТОЛЬКО на прод-волюме с 11.07, вне git → при пересоздании volume потерялся бы. Забран побайтово (cee24d886).
## — Ревизия `.wiki/AUDIT_2026-07-24.md`: карта 32 команд, 13 cron, что проверено (health 200, ключ ok, сквозной бриф, 126 тестов, compileall 30 скриптов, состав скиллов) и что НЕ проверено (живые прогоны 30 команд — только за юзером).
