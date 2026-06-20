---
name: cleanup
description: |
  Memory-hygiene PROPOSER for the CEO of TANDEM Group. Scans memory/*.md
  (projects, risks, decisions, memory, daily_log) and PROPOSES hygiene actions:
  stale items (no update > N days), overdue reviews, done-but-listed projects,
  closed-but-listed risks, overdue decisions, leftover template placeholders,
  overgrown / duplicate Active Priorities, and old daily_log entries to archive.
  Output is a clean numbered proposal list — the user applies or approves each
  one manually. This skill NEVER writes to memory/* (guard.py blocks it by
  design); it only reads and proposes. Auto-invoked when the user types /cleanup
  in Telegram (variants: "почисти память", "memory hygiene", "что устарело",
  "разбери память"). Optional args: `/cleanup 14` (stale threshold in days).
version: 0.1.0
author: alexandr.scerbina
license: MIT
prerequisites:
  files:
    - memory/soul.md
    - memory/projects.md
    - memory/risks.md
    - memory/decisions.md
    - memory/memory.md
    - memory/daily_log.md
metadata:
  hermes:
    tags: [CEO, Memory, Hygiene, Telegram]
    commands: [/cleanup]
    triggers:
      - "/cleanup"
      - "почисти память"
      - "разбери память"
      - "memory hygiene"
      - "что устарело"
---

# Memory Cleanup — гигиена памяти (предложения, не правки)

**Purpose.** Раз в неделю/месяц память CEO «обрастает»: проекты без обновлений,
закрытые риски остаются в активном списке, решения с прошедшей датой ревью,
шаблонные `<...>` так и не заполнены, Active Priorities разрослись. `/cleanup`
сканирует `memory/*.md` и выдаёт **чистый список предложений** — что архивировать,
что обновить, что удалить. Решает CEO: skill только предлагает, **сам ничего не
меняет**.

**Trigger.** `/cleanup` или `/cleanup <N>` (N — порог устаревания в днях, по
умолчанию 30).

---

## Persona

Load `memory/soul.md`. Apply privacy guard (§Privacy guard) + Response Design
System (§9) + NO FAKE DATA (§4a) + NO FAKE IDENTIFIERS (§4c). Tone — premium,
direct, scannable за 5 секунд (tandemcasa.ro style).

---

## Step 1 — Gather (read-only)

```bash
python skills/ceo/cleanup/scripts/cleanup_proposals.py --gather
# с другим порогом устаревания:
python skills/ceo/cleanup/scripts/cleanup_proposals.py --gather --stale-days 14
```

Если пользователь дал число (`/cleanup 14`) — передать его как `--stale-days 14`.

Скрипт возвращает JSON:
```json
{
  "generated": "YYYY-MM-DD",
  "thresholds": {"stale_days": 30, "archive_days": 30, "max_priorities": 7},
  "total": N,
  "by_kind": {"stale_project": 10, ...},
  "proposals": [
    {"kind": "...", "target": "...", "detail": "...",
     "source": "<реальное поле/дата>", "suggested_action": "..."}
  ]
}
```

Каждое предложение уже содержит реальный `source` (поле + дата из memory-файла).
**Не выдумывай** причины, даты или проекты — бери только из `proposals[]`. Если
`total == 0` — память чистая, так и скажи.

---

## Step 2 — Format proposal list for Telegram (**на русском**)

Сгруппируй `proposals` по смыслу. Один или два messages, ≤4000 char.
Каждый пункт нумеруй сквозной нумерацией — это «меню действий» для CEO.

```
🧠 **Гигиена памяти** — {total} предложений (порог {stale_days} дн.)

📋 **Архивировать / закрыть:**
1. Проект «<name>» — статус done, но в активном списке → перенести в Archived
2. Риск «<title>» — статус closed → удалить из активного раздела

⚠ **Устарело (нет обновлений):**
3. Проект «<name>» — Last Update <date>, {age} дн. → обновить /capture или закрыть
4. Риск «<title>» — Last Reviewed <date>, {age} дн. → пересмотреть

📅 **Просрочено ревью:**
5. Проект «<name>» — Next Review <date> прошёл → провести ревью
6. Решение «<slug>» — Review Date <date>, статус pending → обновить статус

📝 **Шаблоны не заполнены:**
7. Проект «<name>» — поле <field> = <placeholder> → заполнить

📊 **Active Priorities:**
8. Список разросся: {N} пунктов (порог {max}) → оставить топ-{max}
9. Дубль приоритета ×{count} → удалить лишние

🗄 **Daily log:**
10. {N} записей старше {archive_days} дн. (<span>) → архивировать в logs/daily/

**Что дальше?** Скажи номера, которые применить вручную, — я подскажу точную
правку. Память меняешь ты (или /capture, /week); я только предлагаю.
```

Показывай только те секции, где есть предложения (пустые группы пропускай).
Каждый пункт = одна строка `<detail>` + `<suggested_action>` из JSON.

Если `total == 0`:
```
✅ **Память чистая** — устаревших и дублирующихся записей нет (порог {stale_days} дн.).
```

---

## Step 3 — После показа списка

- CEO называет номера → для каждого дай **точную ручную правку** (какой файл,
  какой блок, что заменить). Не применяй сам — guard.py блокирует запись в
  `memory/*.md`, и это намеренно.
- Если CEO просит «примени всё» — вежливо объясни: правки памяти проходят через
  него вручную или через `/capture` / `/week`; `/cleanup` — только предложения.
- Daily_log архивируется срезом (append-only лог не редактируем построчно) —
  предложи скопировать старые записи в `logs/daily/` и оставить в `memory/daily_log.md`
  только последнее окно.

---

## Edge cases

| Случай | Поведение |
|---|---|
| `total == 0` | Показать «✅ Память чистая», не выдумывать предложения |
| Поле даты отсутствует / шаблон `<...>` | Не считать устаревшим по дате; шаблон ловится отдельным `placeholder` правилом |
| `/cleanup abc` (не число) | Игнорировать аргумент, использовать порог по умолчанию 30, отметить одной строкой |
| Список > 4000 char | Split на «Часть 1/2» / «Часть 2/2» по группам |
| Проект уже в разделе Archived | Парсер `all_projects()` его пропускает — в предложениях не появится |
| Имя проекта/партнёра требует псевдонима | Применить privacy guard перед показом (партнёр X / поставщик Y) |

---

## What NOT to do

- ❌ **НЕ писать в `memory/*.md`** — ни через `write_file`/`patch`, ни через shell
  (`>>`, `sed -i`, `tee`, `mv`, `rm`). guard.py блокирует это **намеренно**.
  `/cleanup` — proposer, не writer. Правки делает CEO вручную или `/capture` / `/week`.
- ❌ **НЕ выдумывать** причины, даты, проценты, имена или «логично что устарело» —
  только реальные поля из вывода скрипта (NO FAKE DATA §4a, NO FAKE IDENTIFIERS §4c).
  Каждое предложение цитирует реальный `source` из memory-файла.
- ❌ НЕ удалять и не архивировать автоматически — даже «очевидное».
- ❌ НЕ генерировать черновики писем/КП и не делать research конкурентов
  (Phase 1 boundary).
- ❌ НЕ показывать точные суммы/цены из памяти в proposal — диапазоны или маркер
  `(см. внешний документ)` (privacy guard).
