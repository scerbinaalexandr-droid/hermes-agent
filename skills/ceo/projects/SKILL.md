---
name: projects
description: |
  Compact Telegram listing of active projects from memory/projects.md for the
  CEO of TANDEM Group. Auto-invoked when the user types /projects in Telegram
  (variants: "show projects", "что в проектах", "проекты"). Returns a
  priority-sorted table: name | status | priority | deadline | next action.
  Filters by optional `<priority>` arg (`/projects high`, `/projects medium`).
  Archived projects excluded.
version: 0.1.0
author: alexandr.scerbina
license: MIT
prerequisites:
  files:
    - memory/projects.md
metadata:
  hermes:
    tags: [CEO, Projects, Listing, Telegram]
    commands: [/projects]
    triggers:
      - "/projects"
      - "show projects"
      - "что в проектах"
      - "проекты"
---

# Projects Listing

**Purpose.** Быстрая сводка active projects для CEO. Без диалога — один запрос,
один ответ.

**Trigger.** `/projects` или `/projects <priority>` (high|medium|low).

---

## Persona

Load `memory/soul.md`. Apply privacy guard if any project name needs to be
pseudonymized (unlikely for own projects, but if list includes external
partner-led ones — apply).

---

## Step 1 — Gather

```bash
python skills/ceo/projects/scripts/list_projects.py
# or:
python skills/ceo/projects/scripts/list_projects.py --priority high
```

Returns JSON `{projects: [...], filter: ..., total: N}`. Each project dict
has: name, status, priority, deadline, last_update, next_action_first.

---

## Step 2 — Format for Telegram (**на русском**)

Output one message, MarkdownV2-safe, ≤4096 char:

```
📋 Проекты — всего {N}, фильтр={filter or 'все'}

🔴 high (высокий приоритет):
• *<name>* — `<status>`
  Дедлайн: <deadline>
  След.: <next_action_first or '—'>

🟡 medium (средний):
• ...

🟢 low (низкий):
• ...
```

Group by priority desc. Within each group: sort by deadline (soonest first;
`rolling` / `continuous` / empty → end).

If `--priority` filter applied — show only that group, no other headers.

If total = 0:
```
📋 Активных проектов нет.
Открой memory/projects.md и заполни (10 initial projects per blueprint §05).
```

---

## Edge cases

| Случай | Поведение |
|---|---|
| User typed `/projects xyz` (unknown priority) | Ignore filter, show all + note: «Unknown priority filter `xyz`. Showing all.» |
| `next_action_first` пустое | Display `—`. Не выдумывай. |
| Длинный list >4096 char | Split: show high+medium first message, low in second `(2/2)` |
| Project status=`blocked` | Add ⛔ prefix |
| Project status=`done` | Excluded automatically (already in Archived section parser skips) |

---

## What NOT to do

- ❌ НЕ создавай / обновляй проекты через `/projects` — это для `/capture` или `/week`.
- ❌ НЕ показывай Owner / Documents / Dependencies / Risks fields в Telegram (overflow). Доступно через manual open of `memory/projects.md`.
- ❌ НЕ группируй по чему-то кроме priority (это блюпринт §05 default).
