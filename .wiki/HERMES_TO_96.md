---
title: Hermes до 96% — Master Plan
type: roadmap
created: 2026-05-28
owner: Alexandr Scerbina
review_cadence: weekly (sunday evening)
kill_audit_date: 2026-07-27 (60 дней от старта)
status: active
tags: [roadmap, hermes, ceo-os, deep-planning]
---

# План: Hermes до 96%

> Прошёл протокол `deep-planning` 2026-05-28: триаж → 8 вопросов → эхо-тест → спарринг с матрицей рисков → финализация. Этот документ — итог Фазы 3. Каждая строка с риском прослеживается до spaarring-таблицы.

## 1. Контекст и цель

CEO TANDEM Group (5 брендов, MD+RO) с уже работающими 12+ CEO-скиллами в Telegram (@Hermes_Alex21_bot). Боль — 4 источника одновременно: информационный шум, cognitive load встреч, забывание между бизнесами, изоляция CEO. Решение хочется через один Telegram entry-point с продвинутым меню.

**96% =** zero «технических ошибок» (как случай с /coach 28 мая, когда `coach_log.py` отсутствовал в проде), каждая команда ≥9.6/10 (LEAN21), реальное снижение когнитивной нагрузки подтверждено usage-данными.

**Параллельный трек:** найм Chief of Staff (Stilman-аргумент принят). Hermes = информация+память, CoS = люди+встречи. Hermes должен переживать появление CoS — документация и access spaces заранее.

## 2. Что НЕ делаем (явные границы)

- **/psychologist не строим.** Решено отказаться: Anthropic 30-дневный prompt retention несовместим с health data; вместо этого — живой психоаналитик ×2/мес (~€400-600).
- **Не делаем batch-релизы.** 1 ветка → 7 дней реального usage → решение go/kill → следующая ветка. Антипаттерн `/coach` (deploy без теста) больше не повторяем.
- **Не строим inline-меню до telemetry baseline.** Допущение «inline удобнее текста» тестируется через данные, не через интуицию.
- **Не подключаем Calendar/Email (Composio) до Phase 2 roadmap.** Сначала валидация ядра.
- **Не делаем Docker-изоляцию (Finance/Marketing агенты, V3 блюпринта).** Нет реального use case с нужным privilege boundary; over-engineering.
- **Не запускаем Termux/Android агент (V4).** В roadmap зафиксировано, но не сейчас.
- **Не меняем основную модель.** `claude-sonnet-4-6` стабильна; triada DeepSeek/GPT — только для конкретных под-задач (Roadmap-7).

## 3. Допущения, на которых стоит план

| # | Допущение | Тест | Kill-criteria |
|---|-----------|------|---------------|
| A1 | Иерархическое inline-меню удобнее свободного текста | 7 дней telemetry в текущем `/menu`: счётчик кнопок vs текста | <30% через кнопки → НЕ строим inline, оставляем текст-driven |
| A2 | Voice-транскрипция русского с TANDEM-терминами достигает ≥85% точности через Whisper-large-v3 | 5 voice memo разной длины + manual diff | <85% accuracy → /notes идёт как text-only режим, voice откладываем |
| A3 | Photo OCR печатных протоколов через Claude Vision даёт ≥80% accuracy | 3 фото разного качества + manual diff | <80% → /notes принимает только text/voice, фото идут на Phase 2 |
| A4 | Утренний дайджест Румыния (econ+political+мебель+недвижимость) реально читается | 14-дневный pilot, open-rate в Telegram | <50% дней с реальным открытием → kill cron, переводим в on-demand |

## 4. Этапы и контрольные точки

| # | Этап | Действие | Старт | Финиш | Зависимость | Бюджет | KPI этапа |
|---|------|----------|-------|-------|-------------|--------|-----------|
| 1 | **Token monitoring** (Risk #2 mitigation) | Cron-задача `token-monitor`: ежедневный pull Anthropic usage, alert при >$7/день, авто-pause при >$10/день. Telegram-нотификация в личку. | W1 D1 | W1 D2 | — | 2 часа, $0 token | Алерт срабатывает в тестовом сценарии (искусственно >$7) |
| 2 | **/menu telemetry sprint** (A1 test) | Добавить в gateway hook: лог каждого update.message (text vs callback_query) с тегом. Дашборд через `/report telemetry`. | W1 D2 | W1 D3 | — | 1 час, $0 | Лог пишется на каждое сообщение; `/report telemetry` показывает breakdown |
| 3 | **/notes — build** | Skill `skills/ceo/notes/`: SKILL.md + helper `notes_log.py` (--save text, --save voice, --save photo). Whisper API для voice. Claude Vision для OCR. AI structuring (участники/решения/action items). Push в `~/Library/.../ALEX21_VAULT/03 — Notes/YYYY-MM-DD.md` через GitHub-mirror (Railway → private GH repo → Obsidian git sync). | W1 D3 | W1 D5 | #1 (token monitor active) | 6 часов, ~$10 token | SKILL.md + helper зеленый в CI, deploy на Railway success |
| 4 | **/notes — pilot 7 дней** | Реальное использование: минимум 1 use case в день (voice/text/photo). Метрика — фактическое количество созданных notes. | W1 D5 | W2 D5 | #3 deployed | $5-15 token | ≥5 notes за 7 дней; ≥1 protocol с фото; subjective rating ≥7/10 |
| 5 | **/notes — go/kill решение** | Аудит pilot: usage ≥5? accuracy A2/A3 hit? фидбек user-а. Решение: ship as-is / itrate / kill. | W2 D5 | W2 D6 | #4 done | 0 | Решение записано в `.wiki/decisions.md` |
| 6 | **/menu telemetry — анализ A1** | Анализ 7-дневной telemetry. Если ≥30% callback_query — go на inline-меню. Иначе — оставляем текст-режим, инвестируем в semantic triggers. | W2 D6 | W2 D7 | #2 + 7 дней данных | 1 час | Решение записано; если go — переходим к #7, если kill — к #9 |
| 7 | **Inline-меню build (условно)** | Многоуровневое меню (Ритмы / Сессии / Запись / Контроль / Настройки). Сохраняем свободный текст как fallback. Test перед deploy: все 17+ команд доступны через кнопки. | W2 D7 | W3 D2 | #6 = go | 8 часов, $2 token | Все команды доступны; manual test 30 минут — 0 ошибок |
| 8 | **Inline-меню — pilot 7 дней** | Реальное использование, telemetry продолжает писать. | W3 D2 | W4 D2 | #7 | $5 | ≥30% обращений через кнопки сохраняется |
| 9 | **Утренний дайджест Румыния — build** | Skill `skills/ceo/morning_ro/` + helper `digest_ro.py`. Источники: Adevarul, ZF, Profit.ro, Imobiliare.ro, Mobexpert/Lemet news. Через текущий `/web` skill (нет платных API). Cron 08:00 EEST. | W4 D2 | W4 D4 | #8 если go ИЛИ #6 если kill | 4 часа, $0 setup + $5/нед token | Skill deployed, manual run возвращает 5 разделов |
| 10 | **Утренний дайджест RO — pilot 14 дней** | Cron live. Открытие в Telegram считается «прочтением» (приблизительно через Telegram bot API read receipts). | W4 D4 | W6 D4 | #9 | $30 token | ≥7/14 дней реального открытия |
| 11 | **Provider fallback chain** (Risk #3 mit.) | OpenRouter как secondary; auto-switch при HTTP 4xx/5xx от Anthropic. Ollama (mac mini) как tertiary — но только настройка путей, без зависимости. | W6 D4 | W6 D6 | #10 done | 4 часа, $0 | Искусственный simulate Anthropic-fail → автопереключение работает |
| 12 | **Read-only mirror на mac** (Risk #9 mit.) | Cron на mac: каждые 6 часов pull `/opt/data/memory` и `/opt/data/logs` через GitHub backup repo → локальный mirror в `~/Documents/01_CODE/hermes-mirror/`. Доступ только-чтение. | W6 D6 | W7 D1 | — | 3 часа, $0 | Mirror up-to-date; в test offline Railway → данные доступны на mac |
| 13 | **CoS access space** | Подготовка к появлению живого Chief of Staff: документация `docs/COS_ONBOARDING.md`, отдельный allowed_users entry в env, отдельный CEO-skill `/handoff <cos_id>` для делегирования. | W7 D1 | W7 D3 | — | 3 часа, $0 | Документ готов; test add second allowed_id → бот отвечает обоим |
| 14 | **60-day Stilman audit** | Полный аудит usage по каждой ветке. Метрика per skill: open count / total day count. <30% → ветка замораживается, токены реинвестируются в найм CoS. | 2026-07-27 | 2026-07-27 | все ветки live | 2 часа | Решение по каждой ветке записано в `decisions.md` |

**Phase 2 roadmap** (после 96% на текущем ядре, ориентир — Aug-Oct 2026, в отдельной planning-сессии):
- R-1: Calendar/Email через Composio (#4 блюпринта) — после найма CoS, чтобы шаринг был согласован
- R-2: Bookmarks digest (#6 блюпринта)
- R-3: Humanizer skill (#5) — port из ALEX21
- R-4: NotebookLM integration (#10) — Q4 2026
- R-5: Support triage (#7) — only если TANDEM Casa CRM начнёт получать Telegram-обращения
- R-6: Content tracking YouTube (#2) — только если запустим Tandem YouTube канал
- R-7: Triada profiles (conductor/worker/critic) — DeepSeek для voice-структуры, GPT для критики дайджеста — после стабильности 30 дней

## 5. Риски и реакция (из спарринга)

| # | Уровень | Риск | Митигация в плане | Ранний индикатор | Триггер плана Б |
|---|---------|------|-------------------|------------------|------------------|
| 1 | **Крит** | Token bleed >$200/мес | Этап #1 — token-monitor с авто-pause | Anthropic dashboard >$7/день | Авто-pause; ручной разбор какой skill съел |
| 2 | **Крит** | Stilman прав: реальное решение — CoS | Этап #13 (CoS access space) + #14 (60-day audit) | usage <30% по веткам через 60 дней | Замораживаем skills, бюджет в найм CoS |
| 3 | **Сред** | Меню никто не использует | Этап #2 (telemetry) + #6 (gate на go) | <30% callback_query за 7 дней | Не строим inline, оставляем текст |
| 4 | **Сред** | Дайджест RO не читается | Этап #10 (14-day pilot с open-rate) | <50% open-rate за 14 дней | Kill cron, перевод в on-demand `/digest ro` |
| 5 | **Сред** | Voice/OCR качество < target | Этапы #4, A2/A3 тесты | <85% / <80% accuracy | Text-only режим /notes |
| 6 | **Сред** | Railway падение в критичный момент | Этап #12 (read-only mac mirror) | Railway status red | Mirror на mac — доступ только-чтение |
| 7 | **Сред** | Я (Claude) пропускаю детали при batch | План структурно 1-ветка-за-раз; этапы атомарные | «технические ошибки» в Telegram | Stop-the-line: следующая ветка не стартует пока предыдущая не closed |
| 8 | **Сред** | Юр риск /notes (запись без консента) | UI rule: перед сохранением встречи — disclaimer «AI-помощник делает заметки, подтверди» | Любая запись бизнес-конфликта | Не сохранять без явного `/notes confirm`; авто-redaction имён партнёров |
| 9 | **Сред** | Anthropic убил модель / сменил pricing | Этап #11 — provider fallback chain | HTTP 4xx от Anthropic | OpenRouter → Ollama по очереди |

## 6. Ресурсы

- **Деньги**:
  - Текущий Anthropic spend: NEEDS BASELINE (запросить отдельно)
  - Бюджет на этапы #1-14: +$60-100/мес token spend (с учётом дайджеста + voice + photo)
  - Hard cap: $200/мес — при превышении авто-pause
  - Параллельно: €60K/год CoS — отдельный бюджет, не из Hermes pool
- **Люди**:
  - Исполнитель: я (Claude) через Claude Code
  - Тестер: Alexandr (без жёстких слотов, но 1 ветка ждёт твоего usage 7 дней)
  - Будущий: CoS — закладываем access с этапа #13
- **Инструменты/доступы**:
  - Railway (готово)
  - GitHub private backup (готово, cron `f35d551d4a4b`)
  - Anthropic API + OpenRouter (для fallback)
  - Whisper API (нужен setup)
  - mac mini для read-only mirror + потенциально Ollama в Phase 2
  - Obsidian ALEX21_VAULT (готово, нужна новая папка `03 — Notes`)
- **Юридическое**: для /notes — самодельный consent flow перед каждой записью встречи (не lawyer-grade, но best-effort)

## 7. Метрики успеха и провала

**Зелёный (продолжаем):**
- ≥5 /notes за неделю pilot, accuracy A2/A3 hit
- ≥30% обращений через кнопки (если меню построили) ИЛИ ≥10 свободно-текстовых обращений в неделю (если меню не строили)
- Дайджест RO open-rate ≥50% дней
- Zero «технических ошибок» в Telegram (как было с /coach)
- Anthropic spend ≤$10/день average

**Жёлтый (вмешательство):**
- 3-5 /notes за неделю или accuracy 80-85% — итерация промпта/настроек
- 15-30% callback usage — переделка меню (упрощение)
- Дайджест 4-7 дней open — уменьшить размер/частоту
- 1-2 минорные ошибки в Telegram — fix без kill
- Spend $10-15/день — analyze & optimize

**Красный (kill-criteria, останавливаем ветку):**
- <3 /notes за неделю → kill /notes
- <30% callback после 7 дней → не строим inline-меню
- <50% open-rate дайджеста за 14 дней → kill cron
- Любая «техническая ошибка» в Telegram длится >24 часа без fix → stop-the-line, root cause
- Anthropic spend >$15/день 3 дня подряд → авто-pause
- **Master kill-criterion**: 60-day audit (W14, 2026-07-27) — общий usage Hermes <30% от запланированного → freeze всех новых веток, бюджет в найм CoS

## 8. Первая неделя — конкретные шаги

| День | Действие | Я / ты |
|------|----------|--------|
| **W1 D1 (29 мая)** | Я: setup token-monitor (#1). Ты: ответить — какой текущий Anthropic monthly spend (открыть console.anthropic.com → Usage) | оба |
| **W1 D2 (30 мая)** | Я: добавить telemetry в gateway (#2). Deploy. | я |
| **W1 D3 (31 мая)** | Я: начать build /notes — SKILL.md + helper skeleton (#3 part 1). Ты: создать папку `~/Library/.../ALEX21_VAULT/03 — Notes/` (просто пустую). | оба |
| **W1 D4 (1 июня)** | Я: voice transcription + Claude Vision OCR + Obsidian sync (#3 part 2). Deploy. | я |
| **W1 D5 (2 июня)** | Я: smoke test /notes 5 командами. Ты: первая реальная заметка (любого типа). | оба |
| **W1 D6-7 (3-4 июня)** | Ты: использовать /notes по реальным cases. Я: жду фидбек. | ты |
| **W2 D1 (5 июня)** | Я: pull telemetry meanwhile, отчёт по A1 baseline (промежуточный). | я |

## 9. Открытые вопросы / отложенные решения

| Вопрос | К дате | Решающий | Критерий |
|--------|--------|----------|----------|
| Какой текущий monthly Anthropic spend? Нужно для baseline | 2026-05-29 | Alexandr | Open console.anthropic.com → Usage → Last 30 days |
| Кто будет искать CoS — рекрутер или сам? | 2026-06-15 | Alexandr | Отдельный deep-planning по этой теме |
| Whisper API ключ — OpenAI direct или через OpenRouter? | 2026-05-30 | я + Alexandr | Цена/скорость comparison, я делаю |
| Photo OCR — Claude Vision vs Gemini 1.5 Flash (10x дешевле)? | 2026-05-31 | я | A/B на 5 фото, выбираем по cost/accuracy |
| Telegram bot allowed_users — добавлять кого-то ещё (cos placeholder)? | 2026-06-25 | Alexandr | После старта поиска CoS |
| 60-day audit — кто проводит? | 2026-07-20 | Alexandr | Решить за 1 неделю до даты |

---

## Журнал решений (Phase 2 → Phase 3)

| Дата | Развилка | Опции | Выбор | Обоснование | Условие пересмотра |
|------|----------|-------|-------|-------------|---------------------|
| 2026-05-28 | Stilman: Hermes vs CoS | A: bridge / B: only Hermes / C: parallel / D: defer | **C: parallel** | Hermes закрывает информацию+память, CoS закрывает людей+встречи — роли не дублируются. Принят аргумент о пределах AI-помощника. | 60-day audit; если usage <30% — переход к A |
| 2026-05-28 | /psychologist privacy | A: Ollama / B: ZDR Anthropic / C: default / D: skip | **D: skip** | Anthropic 30-day retention несовместим с health data; Ollama на mac mini оверкилл для 2-3 сессий/мес; живой психоаналитик решает лучше за €400-600/мес | Не пересматривать в этом плане; в Phase 2 roadmap не вернёт |
| 2026-05-28 | Tempo развития | A: 1 ветка + test / B: 2 параллельно / C: batch 3 / D: roadmap only | **A: 1 за раз + 7-дн test** | Антипаттерн /coach (deploy без теста) больше не повторяем; usage validation выше скорости релиза | После 60-day audit — если 100% веток успешны, можно ускорить до 2 параллельно |
| 2026-05-28 | Telegram меню | A: плоское / B: иерархическое / C: native / D: гибрид | **B: иерархическое, НО ПОСЛЕ telemetry** | Принят preview-mock; но допущение A1 требует проверки данными | По результату 7-дневной telemetry: ≥30% callbacks → строим, <30% → не строим |
| 2026-05-28 | /notes scope | A: minimum / B: voice+AI / C: full+Obsidian / D: +photo OCR | **D: полный pipeline + Obsidian + photo OCR** | Закрывает 3 источника боли (cognitive load встреч, забывание, обработка протоколов) | Если A2/A3 не пройдут — degradation до C, B, A в порядке |

---

## Чек-лист качества плана

- [x] Каждый Критический риск из Фазы 2 закрыт строкой в плане (#1→этап #1; #2→этап #14)
- [x] Каждое Допущение имеет дешёвый тест ДО основной инвестиции (A1→этап #2; A2,A3→этап #4; A4→этап #10)
- [x] Назван один владелец каждого этапа (я / Alexandr / оба — явно)
- [x] Все сроки имеют дату (W1 D1 = 29 мая 2026, etc.)
- [x] Бюджет суммируется по этапам и сходится с общим ($200/мес hard cap)
- [x] Заданы метрики зелёного/жёлтого/красного (секция 7)
- [x] Объявлены kill-criteria (по каждой ветке + master 60-day audit)
- [x] Первая неделя расписана по дням (секция 8)
- [x] Зафиксировано, что НЕ делаем (секция 2)
- [x] План помещается на 1 экран Obsidian (секция 1+8 = quick read)

**10/10 — план годен.**

---

## Continuation Notes (для future-me, future-CoS, или другой сессии)

Перед началом работы по этому плану — прочитать в порядке:
1. Этот файл целиком
2. `.wiki/CONTEXT.md` (current state)
3. `.wiki/decisions.md` (past architectural)
4. `Downloads/Inner_Mirror_Prompt.md` (если будем возвращаться к /psychologist в далёком будущем)
5. `Downloads/Гермес -идеи и настройки.docx` (источник roadmap идей)

При L3-решении (изменение этапа, kill ветки, изменение метрики) — записать в `decisions.md` с **Why:** и **How to apply:**.

При milestone (любой этап #1-14 closed) — episode snapshot в `~/.claude/memory/episodes/`.
