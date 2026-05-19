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
