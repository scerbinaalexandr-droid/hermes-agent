# hermes-agent — Decisions Log

**Project Memory tier** из ALEX21 Orchestration Corporation spec.

Сюда автоматически логируются:
- L3 архитектурные решения (с user approval)
- Значимые L2 решения (помеченные `commit-decision`)
- Pivot / scope change / стратегические повороты

Формат для каждой записи:

```
## [YYYY-MM-DD] <slug>
**Type:** L2 / L3
**Domain:** <Engineering / Design / etc>
**Context:** <conflict or driver>
**Options considered:** <list>
**Decision:** <chosen option>
**Rationale:** <reasoning>
**Risk if wrong:** <consequence>
**Reversal cost:** <effort>
**Decided by:** <user / meta-orchestrator>
```

---

## [2026-06-01] w1-hermes-to-96-execution-closed
**Type:** Milestone
**Domain:** Executive OS
**Context:** Закрыта W1 по плану HERMES_TO_96 (созданному 2026-05-28 через deep-planning protocol). Все 3 запланированных этапа + 4 внеплановых fix-а пройдены за 4 дня.
**Outcome:**
- Etap #1 token-monitor: /cost работает, 8 entries в pricing table для direct Anthropic 4.x generation добавлены (upstream Nous Research bug); daily cron daily_cost_report 20:55 UTC активен.
- Etap #2 telemetry: pre-handlers в gateway logат каждый update; /telemetry skill агрегирует с decision matrix; baseline накапливается.
- Etap #3 /notes: end-to-end pipeline voice/photo/text → AI structure → /opt/data/logs/notes/ → daily backup → mac launchd → ALEX21_VAULT/03 — Notes/ → iCloud → iPhone Obsidian. Verified первой заметкой 2026-06-01 (TANDEM Casa осень 2026 — на mac в Obsidian).
- Extra: /evening cron broken (interactive skill vs cron mismatch) → заменён на reminder cron 21:30 EEST.
- Extra: IMMUTABLE_ZONE hook false positive на `2>&1` починен (whitelist benign redirects: 2>&1, &>/dev/null, >&2).
**Rationale:** plan имел 14 этапов до W14, W1 (этапы 1-3) закрыты с zero regressions. Каждая ветка прошла smoke test + real deploy verify.
**Risk if wrong:** weeks 4-14 могут не повториться так чисто — введён 60-day Stilman audit kill-criterion на 2026-07-27.
**Reversal cost:** легко — каждый skill self-contained.
**Decided by:** user + agent (deep-planning protocol Phase 3)

---

## [2026-06-01] mac-sync-via-gh-credentials
**Type:** L3
**Domain:** Infra / Mac
**Context:** Запустили `setup-launchd.sh` для Obsidian sync — первый sync упал на "Host key verification failed". Mac ~/.ssh/ оказался пустой (нет SSH ключа), но gh CLI authenticated через GH_TOKEN.
**Options considered:**
- A: Generate SSH key + add to GitHub (5+ min user action + UI)
- B: PAT в plain text в скрипте (security hole)
- C: Use existing gh CLI credentials via `gh auth setup-git` + HTTPS URL
**Decision:** **C** — gh auth setup-git wires git credential helper to gh tokens. HTTPS URL вместо SSH в hermes-notes-sync.sh.
**Rationale:** Использует existing authenticated session (gh уже logged in для всей системы). Никаких новых secrets. Один-разовый `gh auth setup-git` — все private repos этого account доступны через git.
**Risk if wrong:** если gh CLI logout — sync падает. Mitigation: gh auth status уже в Prerequisites checklist setup-launchd.sh.
**Reversal cost:** revert URL → SSH одной строкой.
**Decided by:** agent после failure mode investigation

---

## [2026-05-31] notes-storage-architecture
**Type:** L3
**Domain:** Engineering / Data
**Context:** Архитектура /notes — где хранить и как sync в Obsidian. 3 варианта sync (until tomorrow / hourly / realtime), 3 варианта file layout (1 file/day / per-note / topic folders).
**Options considered:**
- Sync: until tomorrow (через daily backup) / hourly cron / per-note realtime
- Layout: 1 файл/день / 1 файл/note + index / тематические папки
**Decision:** Sync **until tomorrow** (через existing daily backup pipeline) + Layout **1 файл/note + daily index** (`/opt/data/logs/notes/YYYY-MM-DD/HHMM-<slug>.md` + `YYYY-MM-DD-index.md`).
**Rationale:** Sync через existing backup = 0 новой инфры. Per-note + index — Obsidian backlinks работают, daily browse удобно. Tradeoff "sync до завтра" принят — для meeting protocols ОК; ad-hoc thoughts всё равно в /capture.
**Risk if wrong:** заметка сделана в 14:00 не появится на iPhone до следующего дня. Mitigation: launchd cron каждые 6 часов (force-kick available manually).
**Reversal cost:** перейти на hourly sync — изменить StartInterval в plist (1 значение).
**Decided by:** user

---

## [2026-05-29] anthropic-pricing-table-patch
**Type:** L3
**Domain:** Engineering / Observability
**Context:** /cost показывал $0.00 при наличии 2 sessions с 185K cache tokens. Debug: cost_status=no_pricing для всех sessions с model=claude-sonnet-4-5-20250929 / claude-sonnet-4-6. Upstream Nous Research включил pricing entries только для Bedrock-prefixed моделей (`anthropic.claude-...`), но НЕ для direct Anthropic API.
**Decision:** Добавили 8 entries в `agent/usage_pricing.py` _OFFICIAL_DOCS_PRICING dict: sonnet-4-6 (bare + dated), sonnet-4-5-20250929, sonnet-4-7, opus-4-6/4-7, haiku-4-5 (bare + dated). Values from https://www.anthropic.com/pricing.
**Rationale:** Без этого patch token-monitor бесполезен — cost всегда $0. Минимально invasive — только добавление entries в существующую структуру.
**Risk if wrong:** если Anthropic меняет pricing — наши захардкоженные числа устаревают. Mitigation: review раз в 6 месяцев; pricing_version "anthropic-direct-2026-05" tags данные.
**Reversal cost:** удалить 8 entries — 1 commit.
**Decided by:** agent + user approval

---

## [2026-05-28] hermes-to-96-master-plan
**Type:** L3 / Strategic
**Domain:** Executive OS / Roadmap
**Context:** User попросил настроить Гермеса "до 96%" и сделать /psychologist + меню + /notes сразу. Прошли полный deep-planning protocol (триаж → 8 вопросов → эхо-тест → спарринг с матрицей 14 рисков → финализация).
**3 ключевых решения из Phase 2 sparring:**
1. **Stilman accepted: Hermes + Chief of Staff параллельно**, не AI-only. Hermes = информация+память, живой CoS = люди+встречи. 60-day audit kill-criterion на 2026-07-27 — если usage <30% от планируемого, freeze новых веток.
2. **/psychologist skipped**: Anthropic 30-day prompt retention несовместим с health data class. Живой психоаналитик ×2/мес (~€400-600) работает лучше + лицензирован. Inner_Mirror_Prompt.md остаётся в archive, не строим.
3. **Tempo: 1 ветка за раз + 7-day usage test**, не batch-релиз. Антипаттерн /coach (deploy без теста) больше не повторяем.
**Plan deliverable:** `.wiki/HERMES_TO_96.md` — 14 этапов, 4 допущения с дешёвыми тестами, бюджет $200/мес hard cap, чек-лист качества 10/10.
**Rationale:** User просил быстро, но deep-planning выявил риски ($200/мес token bleed, broken privacy для psy, mismatch interactive vs cron). Принят более медленный путь с validation gates.
**Risk if wrong:** темп замедлен до ~3 нед на 6 веток. Может быть слишком медленно если CoS найдётся быстро.
**Reversal cost:** легко — план модульный.
**Decided by:** user + agent (deep-planning Phase 3)

---

## [2026-05-28] no-daily-ro-digest-weekly-already-exists
**Type:** L3
**Domain:** Cost / Roadmap
**Context:** User просил утренний дайджест Румыния (econ+political+мебель+недвижимость). В `cron list` обнаружились уже существующие cron-jobs: Weekly MD+RO Digest (Пн 06:00 UTC) + Weekly Inflation Report Romania (Пн 09:00 UTC) + Monthly MD+RO Report.
**Decision:** Daily digest **НЕ строим** — weekly хватает. Этап #9 в HERMES_TO_96 closed без работы.
**Rationale:** Daily digest = ~$30/мес token spend + Risk #4 «дайджест не читается через 2 недели». Weekly уже работает и last run 25.05 был успешен. Если user реально хочет daily — можем добавить через 2 недели если weekly окажется недостаточным.
**Risk if wrong:** weekly может быть низкого качества — увидим в понедельник.
**Reversal cost:** создать daily cron — 5 минут.
**Decided by:** user

---

## [2026-05-17] decisions-log-init
**Type:** Setup
**Decision:** Создан decisions.md по STANDARDS §1 + начат V1 Executive OS блюпринт.
**Rationale:** Проект-форк Hermes использовался до сих пор без .wiki/ — нарушение ALEX21 стандартов. Чиним перед началом бизнес-логики.

---

## [2026-05-17] memory-folder-in-repo-root
**Type:** L3
**Domain:** Architecture
**Context:** Блюпринт V1 описывает `/memory`, `/SOP`, `/logs`, `/backups` как структурные папки. Hermes core хранит state в `~/.hermes/state.db` (SQLite). Конфликт: куда положить markdown memory layer?
**Options considered:**
- A) В корне репо (по блюпринту дословно)
- B) В подпапке `/ceo-os/` (изоляция от Hermes core)
- C) В `~/.hermes/ceo-os/` (вне репо, как user data)
**Decision:** A — в корне репо.
**Rationale:** Чистая аналогия с блюпринтом, шаблоны легко версионируются в git. Sensitive контент защищается через .gitignore (`/logs/*` exclude). Markdown layer существует параллельно с SQLite — не конкурирует.
**Risk if wrong:** Перемешивание с Hermes core может смутить будущих контрибьюторов форка. Mitigation: README раздел "Tandem CEO OS layer".
**Reversal cost:** 1-2 часа (git mv + правка путей в SKILL.md + loader).
**Decided by:** user 2026-05-17 (AskUserQuestion plan-mode).

---

## [2026-05-17] hermes-native-skill-format
**Type:** L3
**Domain:** Engineering
**Context:** CEO skills (daily_briefing, evening_review, weekly_ceo_review, voice_to_task, project_update, memory_cleanup) можно описать в (A) Hermes-native `skills/<cat>/<name>/SKILL.md`, (B) собственном `.skill.md` из блюпринта, (C) гибрид.
**Decision:** A — Hermes-native SKILL.md.
**Rationale:** Hermes skill loader уже находит и автоматически индексирует SKILL.md через `scripts/build_skills_index.py`. Нет смысла дублировать routing/discovery. CEO skills будут жить в `skills/ceo/<name>/SKILL.md`.
**Risk if wrong:** Если в будущем форк отделится от upstream Hermes — переносить skills придётся. Mitigation: вся CEO-логика изолирована в `skills/ceo/*` поддереве.
**Reversal cost:** низкая (переименование 6 файлов).
**Decided by:** user 2026-05-17.

---

## [2026-05-17] soul-md-canonical-in-memory
**Type:** L3
**Domain:** Architecture
**Context:** `docker/SOUL.md` (v2026-05-10 v2) уже содержит CEO persona + guardrails. Блюпринт требует `memory/soul.md`. Где single source of truth?
**Options considered:**
- A) `memory/soul.md` — canonical, `docker/SOUL.md` удалить и обновить `docker/entrypoint.sh` на чтение из `/memory`
- B) Symlink `docker/SOUL.md` → `memory/soul.md`
- C) Build-time copy в docker image
**Decision:** A — `memory/soul.md` canonical. `docker/SOUL.md` остаётся в этой сессии для backward compat, миграция docker/entrypoint.sh — следующая итерация (out of scope MVP).
**Rationale:** Markdown memory layer должен быть accessible не только из Docker (но и из CLI, тестов, локального dev). Symlink (B) сломается на не-Unix хостах. Copy (C) создаёт два источника правды.
**Risk if wrong:** Контент в `docker/SOUL.md` устареет относительно `memory/soul.md` пока миграция docker entrypoint не сделана. Mitigation: пометка в docker/SOUL.md шапке "see memory/soul.md".
**Reversal cost:** низкая.
**Decided by:** user 2026-05-17.

---

## [2026-05-17] mvp-vertical-scope
**Type:** L3
**Domain:** Scope / Roadmap
**Context:** Блюпринт описывает 12 этапов V1. Половина задач (cron infra, Telegram gateway, SQLite state) уже сделана Hermes core. Делать всё сразу — большой коммит без верификации.
**Options considered:**
- A) MVP-вертикаль: Stage 1+2+3+4 до рабочего /brief end-to-end
- B) Полный V1 (все 12 этапов одним заходом)
- C) Только compliance + foundation (Stage 1+2)
**Decision:** A — MVP-вертикаль.
**Rationale:** Один работающий сценарий end-to-end > много полусделанных. Принцип блюпринта `Reliability > Complexity`. Followups (evening/weekly/cron seeding/GitHub backup) — следующими итерациями.
**Reversal cost:** N/A (это roadmap решение).
**Decided by:** user 2026-05-17.

---

## [2026-05-17] ceo-commands-via-skill-loader-not-command-registry
**Type:** L3
**Domain:** Engineering
**Context:** Initial Stage 4 commit добавил `CommandDef("brief", ...)` в COMMAND_REGISTRY. End-to-end test показал что команда recognized в menu, но **не было handler'а** — агент не вызывал skill. Hermes auto-маппит `name:` field skill'а в `/<name>` команду через `agent.skill_commands.scan_skill_commands()`. CommandDef и skill-with-same-name создают конфликт (CommandDef wins в reserved_names).
**Options considered:**
- A) Удалить CommandDef("brief"), переименовать skill `name: daily_briefing` → `name: brief`, оставить только skill-side mapping
- B) Оставить CommandDef + написать explicit handler в gateway/run.py для каждой CEO команды
- C) Гибрид: CommandDef как alias, skill как implementation
**Decision:** A — pure skill-based registration.
**Rationale:** Hermes авторегистрирует /command из skill `name:` без необходимости core правок. Это upstream-safe (не модифицирует hermes_cli/commands.py). Telegram menu, slash autocomplete, command resolution, skill payload building — всё работает out of the box. CommandDef правки в core file = технический долг при rebase на upstream.
**Risk if wrong:** Если short name (`brief`, `evening`, `week`) станет занят upstream command в будущем — конфликт. Mitigation: проверка при `git pull` upstream Hermes изменений.
**Reversal cost:** низкая — restore CommandDef + добавить explicit handler в gateway/run.py.
**Decided by:** user 2026-05-17 (after Stage 4 routing diagnostic).

---

## [2026-05-17] external-dirs-via-cli-config-yaml
**Type:** L2
**Domain:** Engineering / Deploy
**Context:** Hermes сканирует `~/.hermes/skills/` + `external_dirs` из `~/.hermes/config.yaml`. На dev-машине обоих нет. Нужно подцепить `<repo>/skills/ceo/` без модификации user HOME.
**Decision:** создан локальный `<repo>/cli-config.yaml` (gitignored) с `skills.external_dirs: ./skills/ceo`. На production VPS аналогичная правка делается в `~/.hermes/config.yaml`.
**Rationale:** cli-config.yaml уже в .gitignore, Hermes doctor использует его как fallback при отсутствии primary config. Разделение dev (repo) / prod (HERMES_HOME).
**Reversal cost:** trivial.
**Decided by:** AI (L2 — engineering plumbing).

---

## [2026-05-17] hermes-home-config-yaml-required-for-skill-discovery
**Type:** L2
**Domain:** Engineering / Deploy
**Context:** `hermes reload-skills` → "No new skills detected". Root cause: `~/.hermes/config.yaml` отсутствовал (HERMES_HOME setup был partial — есть `~/.hermes/{cron,logs,memories,sessions,skills,SOUL.md}` но без config.yaml). `get_external_skills_dirs()` читает только `HERMES_HOME/config.yaml`; локальный `<repo>/cli-config.yaml` используется только `hermes doctor` для init, не runtime'ом. Без external_dirs Hermes сканирует только `~/.hermes/skills/` (был пустой) → 0 skills discovered.
**Decision:** создать `~/.hermes/config.yaml` (отсутствовал) минимальным контентом — только `skills.external_dirs` с **абсолютным путём** до repo `skills/ceo/`. На VPS аналогичная правка нужна вручную.
**Rationale:** Hermes runtime ожидает HERMES_HOME/config.yaml. Создание этого файла — стандартный setup-шаг (эквивалент `hermes doctor` или ручной правки). Безопасно: file отсутствовал, не overwrite существующий. Абсолютный путь обязателен — Hermes резолвит relative paths от HERMES_HOME, не от cwd, что создаёт hard-to-debug issues.
**Risk if wrong:** При смене repo location config.yaml ломается. Mitigation: документировано в CLAUDE.md deployment секции, на VPS — отдельный absolute path.
**Reversal cost:** trivial (удалить config.yaml).
**Decided by:** user (issue triage) → AI (fix executed) 2026-05-17.

---

## [2026-05-19] ceo-executive-dashboard-v2
**Type:** L3 (roadmap)
**Domain:** Product / UX (CEO OS Layer)
**Context:** Текущий /report даёт линейную таблицу decisions/projects/risks. User (CEO группы компаний) хочет executive cockpit, а не просто архив. Нужно покрыть все типы задач + planning forward + надиктованный backlog (чтобы ничего не терять).
**Options considered:**
  - A: Расширить текущий /report → добавить секции (Weekly Plan, Backlog, Focus, Health trend). Минимальный код-impact.
  - B: Новый skill /dashboard как evolution /report — сохраняет /report как archival, /dashboard как live cockpit.
  - C: Полная переработка /report. Risk: ломаем текущий рабочий MVP.
**Decision:** B + A hybrid — оставляем /report как retrospective (что было), добавляем /dashboard как forward-looking cockpit (что предстоит + bottom-line).
**Why:** User фокус — "не потерять задачи + видеть план + изучать удобно". Retrospective и forward-looking разные UX-режимы, mixing их в одну страницу = когнитивная перегрузка.
**Sections для /dashboard (V2):**
  1. **Top of mind today** — главный focus + 1 question (из briefing)
  2. **Backlog надиктованного** — все /capture task: за последние 30 дней, сгруппированные по: новые / в работе / готовы / отложено
  3. **Weekly Plan** — что запланировано на эту неделю (из памяти /week + Active Priorities)
  4. **Active projects** — карточки с progress bar + next action + дедлайн
  5. **Risks watching** — top 5 по severity × probability
  6. **Health & Energy trend** — Chart.js линия за 30 дней
  7. **Decisions log** — last 10
  8. **Quick capture box** — visual reminder как добавить task голосом
**How to apply:**
  - Engineering: новый skill skills/ceo/dashboard/SKILL.md + scripts/build_dashboard.py
  - Re-use existing collectors из generate_report.py (decisions, projects, risks, trend)
  - NEW collectors: weekly_plan (from memory/memory.md::Active Priorities), backlog (from memory/memory.md::Active Priorities filtered by [ ] checkbox state)
  - Karpathy guideline: surgical, не ломать /report
**Risk if wrong:** Низкий — /report остаётся как есть, /dashboard аддитивный.
**Reversal cost:** Низкий — отдельный skill, можно удалить директорию.
**Decided by:** user (Александр), confirmed 2026-05-19
**Status:** roadmap (не реализовано, следующая сессия)

---

## [2026-05-19] weekly-intelligence-report
**Type:** L3 (roadmap)
**Domain:** Product / Research (CEO OS Layer Phase 4)
**Context:** User хочет weekly digest по двум темам: (1) конкуренты — что они делают (новые продукты, кампании, цены), (2) экономика — макро Молдова/Румыния/ЕС, курсы валют, ставки, рынок мебели. Phase 4 из блюпринта ("Research Cron"), запускается после стабильного Phase 1 Memory Hub (≥30 дней).
**Options considered:**
  - A: Brave Search / Perplexity / Tavily MCP + curated source list (RSS / Telegram channels / industry sites). Структурированный LLM-pass.
  - B: Только LLM генерация без real sources. ❌ Нарушает soul.md §4a NO FAKE DATA.
  - C: Manual digest — user сам собирает, бот форматирует. Слабый ROI.
**Decision:** A — research-cron skill `/intel week` с реальными источниками.
**Why:** soul.md §4a banит fake stats. Без verified sources весь intelligence report = выдумка. User конкретно сказал "по всем типам задач" — значит честный, реальный, изучаемый. И вторая причина — это Phase 4 блюпринта, user готов когда Phase 1 стабилизируется.
**Sections для /intel week (V1):**
  1. **Competitor watch** — таблица: компания / что нового / источник (ссылка) / impact на нас (LLM judgment, marked as opinion)
  2. **Industry signals** — мебель MD+RO+EU, новые тренды, B2B-сигналы
  3. **Macro Moldova** — курс лей/евро, инфляция, ставка НБМ, политика
  4. **Macro Romania** — лей RO/евро, BNR rate, retail data, политика
  5. **EU furniture market** — Eurostat, IKEA earnings if available, design trends
  6. **Curated reads** — 3-5 ссылок недели "обязательно прочитать"
  7. **Source list** — явно, какие источники запрошены, какие не дали ответ
**How to apply:**
  - Tech stack: MCP — Brave Search + Tavily (для structured search) + WebFetch (для конкретных URL)
  - User должен дать список конкурентов (10-15) + источников (URL/RSS)
  - Skill: skills/ceo/intel/SKILL.md + scripts/fetch_intel.py + render_intel_report.py
  - LLM-pass с строгим промптом: каждый факт = inline citation (URL); если источник не дал данных = явно "(нет данных)"; opinion sections маркированы
  - Cron: суббота 17:00 → /intel week → отправка в Telegram + сохранение в /opt/data/reports/intel/
**Risk if wrong:** Средний — fake stats через faulty source parsing. Mitigator — strict citation requirement в LLM prompt + manual review первые 4 недели.
**Reversal cost:** Низкий — отдельный skill.
**Dependencies:** Brave/Tavily MCP setup, user-supplied source list (10-15 competitors + 10-15 macro sources).
**Decided by:** user (Александр), confirmed 2026-05-19
**Status:** roadmap (после стабилизации Phase 1, оценка: 2-3 недели тестирования /report текущего перед стартом)

---

## [2026-05-22] own-railway-reports-endpoint
**Type:** L3 (architecture)
**Domain:** Engineering / Privacy
**Context:** /report week отчёты приходят на один Telegram device, не на другой (multi-device sync issue Telegram client). Нужна публичная URL для отчёта работающая на любом устройстве с интернетом. Также нужно не отдавать CEO data на 3rd-party file hosts.
**Options considered:**
  - A: catbox.moe — free, 3rd-party. ❌ FAIL — HTTP 412 в проде с Railway IP.
  - B: 0x0.st / temp.sh — free, 3rd-party, volunteer-run. ❌ user не одобрил privacy concern, Claude Code auto-mode заблокировал тест.
  - C: Telegraph (Telegram own service) — статичный HTML без Chart.js.
  - D: **Свой Railway HTTP endpoint** — full control, privacy, persistent, бесплатно в pro plan.
**Decision:** D — `docker/reports_server.py` (stdlib http.server) запускается в background из entrypoint, отдаёт `/reports/<uuid>.html` через Railway public domain.
**Why:**
  - CEO data никогда не покидает user'скую инфраструктуру (privacy)
  - uuid4 в URL = 128-bit entropy, unguessable
  - Нет listing endpoint (`/reports/` без файла → 404)
  - Никаких pip-deps (stdlib only)
  - User отдельно контролирует domain (Railway Settings → Generate Domain)
**Reversal cost:** Средне — нужно поменять generate_report.py и удалить background process из entrypoint.
**Risk if wrong:** Низкий — endpoint можно отключить removed=true на Railway, скрипт упадёт обратно на «только файлы в Telegram».
**Decided by:** User (Александр) — выбран через AskUserQuestion 2026-05-22
**Status:** реализовано commit `1d5ec900e`. Domain `hermes-production-99b8.up.railway.app` verified health=200 OK.

---

## [2026-05-22] fabrication-identifiers-ban
**Type:** L3 (behavior / safety)
**Domain:** Honesty / soul.md
**Context:** Bot выдумал «Cron job 1a1379fdc38d — Weekly Inflation Report Romania, runs Mon 09:00 UTC+3» в ответе user'у. User проверил через /cron list — этой команды вообще не существует. Job был полностью fabricated. Это нарушение existing §4a NO FAKE DATA правила, но §4a покрывало только stats/quotes/sources, не identifiers.
**Options considered:**
  - A: Усилить §4a (расширить scope) — risk: слишком общее правило, hard to follow.
  - B: Добавить новый §4c — конкретный список запрещённых типов identifiers с примерами. ✓
  - C: Hard-code blocked patterns в bot prompt — fragile.
**Decision:** B — soul.md §4c с 10-row table запрещённых identifiers (cron IDs / tool names / file paths / process IDs / DB rows / API endpoints / external IDs / settings / dates / person names) + mandatory citation pattern для каждого упомянутого ID.
**Why:** Repository state pollution через fake identifiers создаёт false trust → user может trust что cron запланирован → реальная задача не выполнится → реальный business risk.
**Reversal cost:** Легко (один файл markdown).
**Risk if wrong:** Низкий — если правило слишком strict, можно ослабить за 1 edit.
**Decided by:** Claude Opus 4.7 после incident review
**Status:** реализовано commit `fe5f385de`. Marked L0 priority (above other rules).

---

## [2026-05-22] response-design-system-codified
**Type:** L3 (UX standard)
**Domain:** Bot communication style
**Context:** User увидел эталонный bot ответ (2026-05-21, курс RON/EUR с ECB URL + Telegram link preview) — попросил применить тот же дизайн ко всем ответам. Существующий soul.md §1-8 не покрывал visual structure.
**Decision:** Добавить soul.md §9 (Response Design System) + §10 (Self-eval checklist).
  - §9: универсальный template (emoji + bold title + sections), 18 функциональных emoji с значением, formatting rules, length budget, mandatory sections в порядке, forbidden patterns, 2 эталонных примера
  - §10: 4-вопрос pre-send checklist (scannable / honest / sourced / actionable)
**Why:** Каждый CEO skill читает soul.md через _lib/memory.py — правила применяются автоматически без правки 12+ SKILL.md файлов. Single source of truth.
**Reversal cost:** Легко.
**Decided by:** User (Александр), confirmed 2026-05-22
**Status:** реализовано commit `e909e02d9`.

---

## [2026-05-23] model-source-is-config-yaml-not-env
**Type:** L3 (architecture / ops)
**Domain:** Engineering / Deploy
**Context:** Prod bot @Hermes_Alex21_bot падал на каждом LLM-вызове: `HTTP 400: claude-haiku-4-5 is not a valid model ID`. Railway env `HERMES_MODEL=claude-sonnet-4-6` был выставлен 22 мая, но бот его игнорировал — `/new` показывал `Model: claude-haiku-4-5`, Provider: anthropic.
**Root cause:** Hermes резолвит дефолтную модель gateway ТОЛЬКО из `config.yaml` (`model.default`) в HERMES_HOME (`/opt/data` = Railway volume), а НЕ из env. Подтверждено кодом:
  - `gateway/run.py:839 _resolve_gateway_model` — *"Read model from config.yaml — single source of truth"*
  - `auth.py:4109 _save_model_choice` — *"stored in config.yaml only — NOT in .env. avoids conflicts where env vars would stomp each other"*
  В volume оставался сид от 17 мая с `model: claude-haiku-4-5` (голый id невалиден для Anthropic direct — требуется dated `claude-haiku-4-5-20251001` либо другая модель). Idempotent `ceo-os-entrypoint.sh` не перезатирает существующий volume config → правка env была no-op.
**Options considered:**
  - A: менять Railway env `HERMES_MODEL` — ❌ Hermes его не читает для gateway default.
  - B: shell в контейнер + править `/opt/data/config.yaml` — ❌ нет CLI-доступа (мёртвый `RAILWAY_API_TOKEN` в `~/.zshrc:14` блокировал `railway login`).
  - C: **`/model <id> --global` из Telegram** — ✓ Level-2 gateway handler (как `/new`), пишет `config.yaml.model.default` на volume, БЕЗ LLM-вызова, без редеплоя.
**Decision:** C — `/model claude-sonnet-4-6 --global` в Telegram.
**Why (на будущее):** Менять модель/провайдера прода НЕ через Railway env `HERMES_MODEL` — только через `/model <id> --global` или правку `config.yaml` на volume.
**How to apply:** Смена модели на проде → `/model <valid-id> --global` в Telegram → проверить `/whoami` (он делает реальный LLM-вызов). Для Anthropic direct использовать canonical id (`claude-sonnet-4-6`, `claude-opus-4-7`), не укороченные без даты.
**Reversal cost:** Легко (повторный `/model … --global`).
**Risk if wrong:** Низкий.
**Decided by:** Claude Opus 4.7 (диагностика по коду) + User (Александр) выполнил fix-команды.
**Status:** ✅ verified prod 2026-05-23 23:13 — `/whoami` отвечает без HTTP 400, `/model` → `Current: claude-sonnet-4-6 on Anthropic`. Деплоя/коммита кода не требовалось (config-only fix на volume).

---

## [2026-05-24] security-hooks-via-native-shell-hooks
**Type:** L3 (architecture / security)
**Domain:** Engineering / Security
**Context:** INSTRUCTION_02 — защита `memory/*`, секретов, контроль исходящих. Инструкция предлагала `hooks.yaml` с собственной схемой (`trigger.tool`, `action: block`, `rate_limit`, `notify_telegram`) — **этой схемы в Hermes нет**, файл был бы проигнорирован (фейк-защита).
**Discovery:** Hermes уже сильно защищён нативно (≈10 подсистем, ~67/100 из коробки): `tools/approval.py` (hardline blocklist + dangerous-command approval + Telegram-подтверждение), `agent/file_safety.py` (denylist .ssh/.env/system), `tools/url_safety.py` (SSRF), `gateway/pairing.py` (auth+lockout), `agent/shell_hooks.py` + `hermes_cli/plugins.py` (настоящие hooks через `cli-config.yaml`/`config.yaml` `hooks:` блок, события `pre/post_tool_call` и др.), `agent/tool_guardrails.py` (loop guardrails).
**Decision:** Реализовать через РОДНОЙ shell-hooks механизм, 0 правок upstream-core:
  - `scripts/hooks/guard.py` (pre_tool_call): блок записи в `memory/*.md` (write_file/patch/terminal), `git push` агентом, curl/wget exfil. Fail-open (approval.py hardline — пол).
  - `scripts/hooks/audit.py` (post_tool_call): лог всех вызовов в `logs/hooks/audit.log`.
  - `tool_loop_guardrails.hard_stop_enabled: true` + `HERMES_REDACT_SECRETS=1` (env).
  - Non-TTY gateway требует `HERMES_ACCEPT_HOOKS=1` (Railway env) — иначе hooks молча пропускаются.
**Why:** Родной механизм > параллельный самопал: не дублирует существующее, не ломает merge с upstream, реально исполняется. `memory/*` был единственным реальным пробелом (`.env`/`config.yaml`/`rm -rf` уже покрыты approval.py).
**How to apply:** Менять/добавлять hooks → правка `config.yaml` `hooks:` блок (НЕ через бот — он не должен менять свои hooks) + скрипт в `scripts/hooks/`. На проде проверять реальной попыткой через Telegram (gateway-регистрация hooks подтверждается только рантаймом).
**Reversal cost:** Легко (убрать hooks блок из config + env).
**Decided by:** Claude Opus 4.7 (аудит кода + Explore) + User (Александр) выбрал «родной путь».
**Status:** ✅ verified prod 2026-05-24 11:18 — бот заблокировал `echo >> /opt/data/memory/soul.md` через guard.py. Commits `1dd54fba8`, `99376694b`.

---

## [2026-05-24] entrypoint-config-self-healing + dated-model-ids
**Type:** L3 (ops / incident)
**Domain:** Deploy / Reliability
**Context:** Во время INSTRUCTION_02 редеплои уронили прод дважды.
**Incident 1 — config corruption:** `ceo-os-entrypoint.sh` section 1 делал bash/awk-merge `config.yaml`, грепая skills-путь с 4 пробелами. После того как `/model --global` переписал config через `yaml.dump` (2-пробельный отступ списков), awk вставлял 4-пробельный элемент рядом с 2-пробельным → **невалидный YAML** → `load_config()` → {} → `model.default` терялся → `HTTP 400: No models provided`, провайдер откатывался на openrouter. Каждый рестарт повторял порчу. Воспроизведено локально (yaml.safe_load → ParserError).
  **Fix:** `scripts/hooks/ensure_config.py` (Python, через `/opt/hermes/.venv/bin/python`) заменил bash/awk. Само-лечится: битый YAML → пересборка с нуля; восстанавливает `model.default`; всегда пишет валидный YAML; идемпотентно. Протестировано 4 сценария локально. Commit `99376694b`.
**Incident 2 — bare model alias rejected:** даже с правильным config (`model=claude-sonnet-4-6`, `provider=anthropic`) Anthropic API отвергал голый `claude-sonnet-4-6` → `HTTP 400: ... is not a valid model ID` (хотя 23.05 работал — причина смены поведения не установлена).
  **Fix:** переход на **датированный snapshot** `claude-sonnet-4-5-20250929` (provider anthropic) → работает. **Lesson: на Anthropic direct использовать ДАТИРОВАННЫЕ ID** (`...-YYYYMMDD`), не голые алиасы — они нестабильны.
**How to apply:**
  - Управление `config.yaml` на volume — ТОЛЬКО через `ensure_config.py` (Python+yaml), НИКОГДА через bash/awk-склейку YAML.
  - Модель прода — датированный Anthropic ID. Railway env `HERMES_MODEL` обновить на датированный (сейчас стоит битый `claude-sonnet-4-6` — landmine для rebuild-fallback).
**Reversal cost:** Средне.
**Decided by:** Claude Opus 4.7 (локальная репродукция) + User (Александр).
**Status:** ✅ verified prod 2026-05-24 — бот отвечает с `claude-sonnet-4-5-20250929`. TODO: ensure_config fallback → датированный + HERMES_MODEL env fix.

---

## [2026-05-24] true-root-cause-inference-provider
**Type:** L3 (ops / incident — ИСТИННАЯ причина модельной саги)
**Domain:** Deploy / Provider routing
**Context:** Несмотря на фиксы выше, бот продолжал падать «HTTP 400: <model> is not a valid model ID» по любой модели (haiku → claude-sonnet-4-6 → claude-sonnet-4-5-20250929), причём паттерн «работает пару часов после /model, потом /new/redeploy — снова ломается».
**Root cause (истинный):** Railway env **`HERMES_INFERENCE_PROVIDER=openrouter`**. `gateway/run.py:568` передаёт его как `requested` в `resolve_requested_provider` (runtime_provider.py:299), и explicit `requested` ПЕРЕБИВАЕТ `config.yaml model.provider`. → ВСЕ запросы gateway шли в **OpenRouter**, который НЕ принимает голые Anthropic-ID (нужен `anthropic/...` slug) → 400. Ошибка несла OpenRouter-style `user_id`. `/model --provider anthropic --global` чинил только текущую сессию → сброс возвращал openrouter-дефолт. **Мы лечили МОДЕЛЬ, а корень был в ПРОВАЙДЕРЕ.** OpenRouter был добавлен ранее (OPENROUTER_API_KEY) и создал конфликт с дефолтным anthropic-стеком.
**Decision:** Railway env `HERMES_INFERENCE_PROVIDER`: `openrouter` → `anthropic`.
**Why:** gateway-дефолт провайдера становится anthropic → Anthropic direct (ANTHROPIC_API_KEY) → голый dated-ID валиден → переживает /new и redeploy.
**How to apply:** При «not a valid model ID» — СНАЧАЛА проверять `HERMES_INFERENCE_PROVIDER` (должен быть `anthropic`), НЕ модель. Провайдер и формат модели держать консистентными (anthropic → голый dated id; openrouter → `anthropic/...` slug).
**Reversal cost:** Легко (одна env-переменная).
**Decided by:** Claude Opus 4.7 (чтение gateway/run.py:568 + runtime_provider.py) + User (Александр) поменял env.
**Status:** ✅ verified prod 2026-05-24 17:23 — /whoami работает, переживает /new.

---

## [2026-05-24] github-memory-backup
**Type:** L3 (data protection)
**Domain:** Deploy / Backup
**Context:** INSTRUCTION_03 — защита `memory/*` (невосстановимо) от потери Railway Volume.
**Decision:** `skills/ceo/backup/scripts/backup.py` (stdlib, токен скрабится) → daily `no_agent` cron 03:00 UTC снапшотит memory/ + logs/daily (30d) + logs/hooks + config.yaml в приватный repo `hermes-memory-backup`. Whitelist + exclude (.env/secrets/sessions). Entrypoint стейджит скрипт в `/opt/data/scripts/` (cron требует --script под HERMES_HOME/scripts/). no_agent = 0 LLM-токенов + минует guard (прямой subprocess).
**Why:** Третий слой защиты (Mac + Railway Volume + GitHub), полная git-history, $0, не зависит от Railway-аккаунта.
**How to apply:** Менять/чинить — через config + скрипт (не бот). PAT fine-grained, ТОЛЬКО backup-repo, Contents:write, 90d expiry (rotate 2026-08). Env: BACKUP_GITHUB_TOKEN/REPO_URL/GIT_USER_NAME/GIT_USER_EMAIL.
**Reversal cost:** Легко.
**Decided by:** Claude Opus 4.7 (адаптация под реальный Hermes cron, не выдуманный yaml) + User.
**Status:** ✅ ЗАКРЫТО. /backup verified prod 2026-05-24 14:25 — snapshot pushed (memory/+logs/+config.yaml, без .env). Cron создан: job `f35d551d4a4b` daily_memory_backup `0 3 * * *` no_agent, next run 2026-05-25 03:00 UTC. Commits 5a327a310, 4d07d4508, 584b487c2. NB: `hermes cron create --script` хочет путь ОТНОСИТЕЛЬНО ~/.hermes/scripts/ (не абсолютный); venv-CLI `/opt/hermes/.venv/bin/hermes`; `/cron` — не slash-команда бота.

---

## [2026-05-24] coach-as-isolated-optin-skill
**Type:** L3
**Domain:** Engineering / Product
**Context:** Установка стороннего «ИИ-коуча» (Георгий Ривера: системный промпт + 4 методики ICF/GROW/Колесо/Co-Active + 4 ритма) в прод-бота. Файлы прошли security-аудит (10 MD прочитаны — нет скрытых unicode / инъекций / эксфильтрации). Проблема: `01_Системный_промпт` — полноценный системный промпт; есть пересечение с существующими ритмами Hermes (`/brief` `/evening` `/week` — намеренно НЕ коучинговые, в evening явно «❌ не давай coaching»); коучинг ≈ Phase-2 sparring, который в soul.md выключен.
**Options considered:**
- A) Влить промпт в `memory/soul.md` (глобально) — отклонено: перепишет персону Hermes + конфликт с Phase-boundaries + soul.md canonical/manual-only.
- B) Апгрейдить /brief /evening /week в коучинговые — отклонено user'ом: меняет текущее поведение, противоречит «evening = не коучинг», больше риска.
- C) Отдельный изолированный скилл `/coach`, активный только в сессии — выбрано.
**Decision:** C. Новый скилл `skills/ceo/coach/` (SKILL.md + 8 references + helper `coach_log.py`). Persona читает soul.md ПЕРВЫМ (приоритет privacy/tone/zero-fake-data), затем коуч-надстройка с границей «активна только внутри /coach». Тон **смягчённый для CEO** (вопросы в основе, но прямая рекомендация по запросу/при нехватке времени). Контекст = существующая память (user/goals/areas/memory — без дубль-файла). Артефакты → `logs/coaching/YYYY-MM-DD.md` (НЕ memory/*) через helper → не триггерит guard.py. soul.md НЕ трогаем.
**Why:** Минимальное вмешательство (Karpathy): ничего существующего не ломаем, обычное поведение Hermes неизменно, легко откатить (удалить папку скилла). Изоляция снимает конфликт с Phase-boundaries — коучинг это явный opt-in, не дефолт.
**How to apply:** Расширять коуча — внутри `skills/ceo/coach/` (новые методики → references/, routing → SKILL.md). НЕ переносить коуч-тон в глобальную персону. Если позже захотим синергию с `/brief` — добавить запись коуч-инсайта в `memory/daily_log.md` через helper (как evening), отдельным решением. logs/coaching добавлен в backup.py INCLUDE (без ротации — история коуча ценна долгосрочно).
**Risk if wrong:** Коуч-тон «протечёт» в обычные ответы. Mitigation: явная граница в Persona + What-NOT-to-do. Reversal: удалить `skills/ceo/coach/` + откатить 3 мелкие правки (SOP/menu/backup).
**Reversal cost:** Низкая (изолированная папка + 3 surgical правки).
**Decided by:** User (Александр) — AskUserQuestion: «коуч отдельно» + «смягчённый тон» — 2026-05-24. Реализация Claude Opus 4.7.
**Status:** ✅ ЗАКРЫТО (базово). Commit 515ccdb88 → push → Railway redeploy → verified prod 2026-05-24 22:19: `/coach` зарегистрирован (slash из `name: coach`), pre-flight check пройден, `coach_log.py --gather` отработал на томе, меню коуча отрисовано (4 ритма + 4 методики). Осталось опционально: довести полную сессию до сохранения артефакта в `logs/coaching/` (save-path).
**NB:** slash-команда деривится из поля `name` скилла (`scan_skill_commands` agent/skill_commands.py:272-294), НЕ из `metadata.hermes.commands`; скан live при старте процесса (deploy = рестарт = авто-регистрация, индекс не пересобирать). «Unknown command» сразу после push = деплой ещё не докатился, не баг.

## 2026-06-07 — Anti-loss protocol system + STT fix (session: protocols)

**Decision 1 — STT:** прод `config.yaml` stt.local: `model: base→small`, `language: ''→'ru'` (бэкап: config.yaml.bak-20260607).
**Why:** Whisper-base без язык-hint галлюцинировал английский и коверкал русские голосовые («куконь», «Плин») — протоколы CEO становились нечитаемыми. Контейнер 32 CPU тянет small; конфиг читается на каждый вызов (рестарт не нужен); ensure_config.py трогает только model.* — фикс не затрётся.
**How to apply:** менять stt.* только в /opt/data/config.yaml на Railway volume; для идеала — Groq whisper-large-v3-turbo (нужен GROQ_API_KEY).

**Decision 2 — notes AUTO-SAVE:** протокол сохраняется автоматически при битом input / смене темы / не-ответе на «Продолжай — или готово?».
**Why:** инцидент 2026-06-06 — протокол встречи с Корнелиу (6 задач) жил только в контексте чата: бот ждал подтверждения, пользователь не ответил, протокол не был сохранён. Восстановлен вручную из state.db → logs/notes/2026-06-05/.
**How to apply:** правило в notes/SKILL.md Step 3; черновик сохраняется всегда, подтверждение управляет только финальной версией.

**Decision 3 — brief Logging через terminal-хелпер:** memory/daily_log.md пишется ТОЛЬКО через `append_entry()` (terminal), logs/daily — write_file.
**Why:** CEO OS guard (scripts/hooks/guard.py) блокирует write_file в memory/*.md by design; модель в cron-сессии 06.06 запаниковала и не записала вообще ничего, плюс сделала ложный вывод что guard покрывает logs/.
**How to apply:** инструкция в brief/SKILL.md §Logging однозначна; guard НЕ менять — он работает правильно.

**Note — skills_sync manifest:** capture/notes на проде помечены user-modified (Hermes правил их 05-06.06) → деплой их НЕ обновляет. Прод-дельты перенесены в git (этот коммит), прод-версии = git-версии. Будущие правки этих двух скиллов доставлять на прод вручную (railway ssh) или сбросив hash в /opt/data/skills/.bundled_manifest.

---

## 2026-06-20 — phase1-module-buildout
**Type:** L3 (engineering / product)
**Domain:** Engineering / CEO OS skills
**Context:** Автономная ultracode-сессия «выстроить помощника». После git-реконсиляции с origin (fast-forward подтянул 07.06 фиксы STT/notes-autosave) построены 5 Phase-1-безопасных модулей через workflow (ресёрч convention contract + бестпрактисов Hermes → параллельная сборка → адверсариальное ревью каждого, 12 субагентов). **0 правок upstream-core.**
**Built:**
- `/cleanup` (Stage 5c, висел с 17.05) — read-only memory-hygiene proposer; НИКОГДА не пишет memory (guard.py), только предложения с цитированием реального поля/даты.
- `/dashboard` (roadmap Направление 1, 19.05) — forward-looking Executive Cockpit (HTML, как /report, но вперёд).
- `/diary` — дневник + протоколы встреч, append-only в logs/diary/ (не memory — guard); зеркалит notes AUTO-SAVE.
- `/handoff` + `docs/COS_ONBOARDING.md` (#13, под найм CoS) — делегирование read-доступа; **скилл НЕ мутирует env**, только документирует + подтверждает identity.
- mac-mirror (#12, Risk #9) — launchd 6h pull backup-repo в read-only зеркало `~/Documents/01_CODE/hermes-mirror` (HTTPS+gh, не SSH). Файлы готовы, установка отложена (зеркало вне песочницы проекта).
**Two bugs caught by adversarial review (пофикшены + верифицированы локально):**
1. cleanup `_scan_decisions` фабриковал предложение из template-плейсхолдера внутри ```-fence (нарушение soul.md §4c/§4a NO FAKE IDENTIFIERS). Fix: strip ```-fences + split по level-2 `##` (как реальные decisions) + skip 'YYYY'/'<...>'. Verified: цитирует реальное «2026-05-17 — start-hermes-v1-mvp».
2. handoff `list_allowed.py` считал allowlist как precedence (telegram OR gateway), а gateway `_is_authorized` делает UNION (TELEGRAM ∪ TELEGRAM_GROUP ∪ GATEWAY) → скрывал реально-авторизованных. Fix: UNION + per-id provenance. Verified: все 3 entry видны.
**Why:** (a) закрыть давно-висящие Stage 5c / roadmap пункты в рамках Phase 1; (b) подготовить инфраструктуру под Stilman parallel-track (CoS, #13) и DR (#12); (c) workflow + adversarial review поймали 2 fake-data/security бага ДО прода — ровно класс ошибок, который soul.md §4a/§4c запрещает.
**How to apply:** новые CEO-скиллы строить по convention contract (frontmatter name→slash, stdlib + sys.path fallback /opt/hermes, guard-safe logs/ не memory/, no-fake-data/identifiers, Response Design). Любой raw-text парсер decisions/projects/risks ОБЯЗАН strip-ить ```-fences перед split (все три файла содержат markdown-шаблоны). Access-control скиллы (handoff) — паттерн «документируй, не мутируй»: LLM-driven мутация env = privilege-escalation вектор, guard.py её не ловит → граница by design.
**Reversal cost:** Низкая — каждый модуль = изолированная новая папка + surgical shared-правки (menu/SOP/backup INCLUDE/.gitignore).
**Decided by:** Claude Opus 4.8 (ultracode workflow) + User (Александр) — директива «огонь».
**Status:** ✅ Built + reviewed + fixed + verified локально (py_compile + smoke зелёные). ⏳ Deploy + menu-popup whitelist (hermes_cli/commands.py — protected, отдельный апрув) + mac-mirror install — в прод-батче, ждут апрува.
