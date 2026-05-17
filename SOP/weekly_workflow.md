# SOP: Weekly Workflow

**Назначение:** ритм Hermes в воскресенье (CEO weekly review).

---

## Воскресный ритм (блюпринт §09 + §10)

| Время | Trigger | Action | Skill |
|---|---|---|---|
| Sunday 17:00 | cron (Stage 6) | Memory cleanup proposal → Telegram | `ceo/memory_cleanup` |
| Sunday 18:00 | cron (Stage 6) | Weekly CEO review prompt → Telegram | `ceo/weekly_ceo_review` |

В **V1 MVP** оба — не автоматизированы. User вызывает руками когда готов.

---

## Memory Cleanup Flow (Stage 5c, 17:00)

1. Skill сканирует:
   - `memory.md` (active context) — старее 14 дней? кандидат на архив
   - `daily_log.md` — entries >30 дней → предложить переместить в `logs/daily/archive/`
   - `weekly_review.md` — entries >12 недель → архив
   - Duplicate facts (грубая дедупликация по headers)
2. Skill возвращает **proposal** в Telegram — не делает изменения автоматически. Блюпринт §10: "Never delete automatically. Always show proposal first."
3. User отвечает: `approve`, `reject`, или редактирует список.
4. После approve — skill применяет изменения, лог в `logs/weekly/YYYY-WW.md`.

---

## Weekly CEO Review Flow (Stage 5, 18:00)

1. Skill читает: `projects.md`, `risks.md`, `daily_log.md` (last 7 entries), `weekly_review.md` (last entry, для сравнения).
2. Skill отправляет prompt в Telegram по структуре блюпринта §09:
   - Business, Cashflow, Sales, Production, Marketing, Team
   - Projects (status update по каждому)
   - Health, Family, Recovery, Learning
   - Key Risks (изменения с прошлой недели)
   - Key Decisions (принятые в этой неделе)
   - Next Week Focus
3. User отвечает разделами (можно несколькими сообщениями).
4. Skill агрегирует ответ → save:
   - `logs/weekly/YYYY-WW.md` (полный текст review)
   - `weekly_review.md` (append-only summary)
   - Update `projects.md` (status поля)
   - Update `risks.md` (new/closed)

---

## Принципы

- **Воскресный review — самый важный артефакт CEO.** Не пропускать. Если не сделан — карри-овер на понедельник.
- **Цикл закрытия:** weekly review → корректировка приоритетов → начало следующей недели в Monday brief.
- **Память consolidation.** Daily entries устаревают быстро; weekly summary — то что остаётся в долгосрочной памяти.

---

## Что НЕ в weekly workflow

- Финансовый отчёт компании (отдельный процесс через CFO)
- Performance reviews сотрудников (отдельная роль HR)
- Pharma research consolidation → Phase 4
