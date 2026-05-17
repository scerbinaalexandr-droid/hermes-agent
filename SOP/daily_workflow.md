# SOP: Daily Workflow

**Назначение:** ритм Hermes в течение дня. Что происходит автоматически (cron), что user делает руками.

---

## Расписание дня (по блюпринту §10)

| Время | Trigger | Action | Skill |
|---|---|---|---|
| 07:30 | cron (Stage 6) | Daily briefing → Telegram DM | `ceo/daily_briefing` |
| в течение дня | user вручную | `/capture <thought>` после встреч | `ceo/voice_to_task` |
| в течение дня | user вручную | Voice memos через Telegram | core voice → memory append |
| 21:30 | cron (Stage 6) | Evening review prompt → Telegram | `ceo/evening_review` |

В **V1 MVP** (Stage 0-4) автоматизации (cron) **не включены**. User вызывает `/brief` руками.

---

## Daily Briefing Flow

1. **07:30 — Hermes отправляет briefing в Telegram DM** (или user вызывает `/brief`).
2. Briefing содержит (блюпринт §07):
   - Date, Main Focus
   - Top 3 Business Priorities
   - Top 3 Personal Priorities
   - Meetings (если синхронизирован календарь — V2)
   - Deadlines (из projects.md `Deadline:` поля)
   - Health Action (из areas.md `Health` домена)
   - Family Touchpoint (из areas.md `Супруга` / `Parents`)
   - Energy Warning (из последнего evening review)
   - Main Risk Today (top risk из risks.md по priority)
   - One Important Question (генерируется LLM из контекста)
3. **Briefing сохраняется** в `logs/daily/YYYY-MM-DD.md`.
4. User либо ack'ает, либо корректирует фокус через `/capture`.

---

## Evening Review Flow (Stage 5)

1. **21:30 — Hermes отправляет evening review prompt** в Telegram.
2. User отвечает голосом / текстом по структуре (блюпринт §08):
   - Completed
   - Not Completed (+ Why)
   - Carry Over
   - Main Bottleneck
   - Energy Level (1-10)
   - Stress Level (1-10)
   - Health Status
   - Family Status
   - Lesson Learned
   - Tomorrow Focus
3. Skill парсит ответ → append в `logs/daily/YYYY-MM-DD.md`, `daily_log.md`, обновляет `memory.md` (active context).

---

## Принципы

- **Никогда не дублировать.** Если `/brief` отправляется автоматически в 07:30 — `/brief` от user'а в 09:00 показывает тот же briefing (cached) или regenerated по запросу.
- **Логи append-only.** `logs/daily/YYYY-MM-DD.md` не overwrites — добавляются секции (Brief, Capture #1, Evening Review).
- **Если cron job упал** — Telegram уведомление (delivery error → console + user notify). Не silent fail.

---

## Что НЕ в daily workflow

- Pharma research → отдельный cron (Phase 4, не V1)
- Trend scout → Phase 4
- Marketing decisions → не автоматизируем
- Финансовый отчёт → manual в `memory/areas.md::Finance` domain
