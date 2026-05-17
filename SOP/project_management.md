# SOP: Project Management

**Назначение:** как добавлять, обновлять, закрывать проекты в `memory/projects.md`.

---

## Структура проекта (блюпринт §04, §05)

Каждый проект в `memory/projects.md` имеет блок:

```markdown
## <Project Name>

Owner: <CEO / delegate>
Goal: <one sentence — что считаем "done">
Status: planning | active | blocked | review | done | archived
Priority: critical | high | medium | low
Deadline: YYYY-MM-DD | rolling | none
Next Actions:
  - [ ] <action 1>
  - [ ] <action 2>
Dependencies: <other projects / external / people>
Risks: <link to risks.md categories>
Documents: <Obsidian / Notion / paths>
Last Update: YYYY-MM-DD
Next Review: YYYY-MM-DD
```

---

## Initial projects (из блюпринта §05)

10 проектов в `memory/projects.md` (заполняется в Stage 3):

1. Tandem Group CEO System (this Hermes V1)
2. Tandem Casa 360°
3. Kitchens (Kitchen by Tandem)
4. TikTok / Marketing
5. Brasov Apartment Renovation
6. Health / Longevity
7. Personal Finance
8. Pharma Production Romania
9. Knowledge Capitalization
10. Learning & Expertise

---

## Add new project

Через `/capture` (Stage 5b) с маркером `project: <name>` — skill добавит skeleton block в `projects.md` и попросит дозаполнить через серию вопросов.

Или вручную — append блок в `memory/projects.md`, заполнить все 11 полей. Не оставлять Owner пустым (блюпринт §05 требует owner всегда).

---

## Update existing project

Через `/capture` с маркером `project: <name>, status: <new>` — skill парсит и обновляет конкретное поле.

Или вручную — изменить только нужные поля, всегда обновлять `Last Update: YYYY-MM-DD`.

---

## Close project

`Status: done` + дата в `Last Update`. **Не удалять блок** — переместить в секцию `## Archived` в конце файла (для retrospective).

---

## Project Logic правила (блюпринт §05)

Every project must have:
- ✅ Owner
- ✅ Next Actions (не пустой)
- ✅ Review dates
- ✅ Risks
- ✅ Dependencies
- ✅ Deadlines (или явный rolling/none)

Если хоть одно поле пустое → status = `planning`, не `active`.

---

## Связь с другими memory-файлами

- `projects.md` ← `daily_log.md` (entries про прогресс → агрегируются в weekly Update)
- `projects.md` → `risks.md` (если Risks ссылается на категорию из risks.md)
- `projects.md` → `decisions.md` (если decisions про конкретный проект)
- `projects.md` → `goals.md` (long-term goal проектируется через 1-2 active projects)
