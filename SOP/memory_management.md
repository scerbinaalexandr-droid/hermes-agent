# SOP: Memory Management

**Назначение:** как поддерживать `memory/*.md` в чистоте, когда чистить, как делать `cleanup proposal`.

---

## Memory philosophy (блюпринт §04)

Memory должна быть:
- structured
- compact
- regularly cleaned
- separated by purpose
- easy to update

Избегать:
- duplicated facts
- outdated context
- bloated memory

---

## Разделение по purpose

| Файл | Что хранит | Что НЕ хранит |
|---|---|---|
| `user.md` | Stable CEO profile (изменяется редко) | Текущие задачи / эмоциональные состояния |
| `soul.md` | Hermes persona + guardrails | User profile |
| `memory.md` | Active context (last 2-4 недели) | Историю старее месяца |
| `areas.md` | 12 life domains (структурные) | Конкретные проекты |
| `goals.md` | Long-term goals по доменам | Текущие задачи |
| `projects.md` | Active projects | Завершённые (move to Archived section) |
| `risks.md` | 8 категорий рисков | Конкретные incident reports |
| `decisions.md` | L3 решения с reason/result | Tactical day-to-day choices |
| `daily_log.md` | Хронология дня (append-only) | Long-term summary |
| `weekly_review.md` | Еженедельная summary (append-only) | Daily detail |

---

## Когда чистить (cleanup triggers)

1. **Воскресенье 17:00** — cron job `ceo/memory_cleanup` (Stage 6) показывает proposal
2. **Manual `/cleanup`** — user может запросить anytime
3. **memory.md > 5KB** — индикатор bloat
4. **daily_log.md > 50KB** — индикатор накопления, archive первую половину

---

## Cleanup Proposal Algorithm

Skill `ceo/memory_cleanup` (Stage 5c):

1. **Scan**:
   - Найти duplicates (по similar headers/content)
   - Найти outdated entries (>14 days в `memory.md`)
   - Найти projects.md блоки с `Status: done` и `Last Update` >30 days → archive
   - Найти risks.md блоки без updates >60 days → review or archive

2. **Generate proposal** в Telegram:
   ```
   📋 Memory Cleanup Proposal — 2026-05-17

   memory.md (5.2KB → 3.1KB):
     - Remove stale: "..." (added 2026-04-20)
     - Remove duplicate: "..." (also in projects.md)

   daily_log.md (52KB → 22KB):
     - Archive 2026-03-* → logs/daily/archive/

   projects.md:
     - Move "Old Project X" (status=done, 2026-04-01) → Archived section

   Reply: approve | reject | edit
   ```

3. **On `approve`** — apply changes, log в `logs/weekly/YYYY-WW.md`.
4. **On `reject`** — discard, no changes.
5. **On `edit`** — user редактирует список (e.g. "approve memory + reject projects").

---

## Append-only правила

| Файл | Mode | Note |
|---|---|---|
| `daily_log.md` | append-only | Никогда не перезаписывать |
| `weekly_review.md` | append-only | Только cleanup proposal может архивировать |
| `decisions.md` | append-only | Decisions — исторический record, не редактировать |
| `memory.md` | safe-overwrite | Только через cleanup proposal |
| `user.md` | safe-overwrite | Manual edit only, не через skill |
| `soul.md` | safe-overwrite | Manual edit only, не через skill |
| `areas.md` | safe-edit | Sections могут обновляться, но структура стабильная |
| `projects.md` | safe-edit | Per-project sections, не удалять — archive |
| `risks.md` | safe-edit | Same as projects.md |
| `goals.md` | safe-edit | Редко обновляется |

---

## Privacy reminders (из `memory/soul.md`)

В любой `memory/*.md` НЕ записывать:
- Пароли, банковские реквизиты
- Медицинские данные семьи
- Точные суммы договоров (диапазоны или `(see external doc)`)
- Чужие цитаты с встреч (после сохранения — переписать как "своё суждение")

ФИО незнакомых партнёров заменять на псевдонимы (`партнёр X`, `поставщик Y`).

---

## Не теряем ничего

- При cleanup → all removed content **сначала** копируется в `logs/weekly/YYYY-WW.md::cleanup-proposal-applied`
- Backup → `backups/` + GitHub (Stage 7)
- Episodic memory для milestone'ов → `~/.claude/memory/episodes/`
