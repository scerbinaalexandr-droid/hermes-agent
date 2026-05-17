# Decisions Log

> CEO L3/L2 decisions с обоснованием. Append-only. Блюпринт §04.
> Не редактировать прошлые записи — добавлять новые.
> Это **business decisions log**. Архитектурные tech-решения — `.wiki/decisions.md`.
> Updated: 2026-05-17 (init).

---

## Format

```markdown
### YYYY-MM-DD — <decision slug>

Date: YYYY-MM-DD
Decision: <what was decided, one sentence>
Reason: <why — context, drivers, constraints>
Expected Result: <what success looks like>
Review Date: YYYY-MM-DD
Status: pending | applied | reviewed | reversed
Linked Projects: <projects.md references>
Linked Risks: <risks.md references>
```

---

## 2026-05-17 — start-hermes-v1-mvp

Date: 2026-05-17
Decision: запускаем Hermes V1 Executive OS блюпринт, MVP-вертикаль до рабочего `/brief`
Reason: текущая CEO operating model (Telegram + Obsidian manually) недостаточна — теряются решения, нет daily/weekly ритма, перегруз растёт. Hermes уже имеет 70% инфраструктуры (skills/cron/Telegram), достроить недостающее (memory layer + CEO skills) выгоднее чем строить заново.
Expected Result: через 30 дней — стабильный daily ритм через Telegram (`/brief` утром, `/evening` вечером, `/week` воскресенье), все memory файлы заполнены, CEO ритуалы выполняются ≥80% дней без напоминаний.
Review Date: 2026-06-17
Status: pending
Linked Projects: Tandem Group CEO System (Hermes V1)
Linked Risks: overload, burnout

---

<новые decisions добавляются ниже>
