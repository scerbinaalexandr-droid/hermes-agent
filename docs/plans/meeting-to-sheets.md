# Meeting → Sheets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Status:** PLAN ONLY — не реализовывать без явного «go» от CEO.

**Goal:** Голосовая заметка о встрече → резюме + action items → строки в одном мастер-Google-Sheet (вкладки `Протоколы` и `Задачи`), с колонкой «направление», видимо с телефона.

**Architecture:** Переиспользуем существующий пайплайн `voice → STT → /notes` (он уже даёт structured JSON: topic/summary/decisions/action_items). Добавляем **один новый stateless-скрипт** `sheets_meeting_sync.py`, который берёт тот же JSON + классифицированное направление и делает идемпотентный `append` в 2 вкладки через уже существующий `google_api.py sheets append`. `/notes` и `/diary` **не модифицируем по коду** — только добавляем один шаг-вызов в `SKILL.md` (инструкция для LLM, не Python). Никакого абстрактного storage-слоя.

**Tech Stack:** Python 3.11+, существующий `google_api.py` (Google Sheets API v4, scope `spreadsheets` уже в коде), pytest, JSON CLI-контракт как у `notes_log.py`.

## Global Constraints

- Секреты — только env, не в коде. Sheet ID живёт в env `HERMES_MEETING_SHEET_ID` (gitignored `.env` локально / Railway env на проде). Verbatim из spec: «Создание/шеринг целевого Sheet и любое расширение OAuth scope — действие CEO».
- Переиспользовать, не переписывать: voice→STT, извлечение резюме/`action_items` из `/notes`, функции Sheets из `google_api.py`.
- Минимальный scope: только сценарий «пост-встречная голосовая заметка → 2 вкладки». Никакой SaaS-обобщённости, multi-tenant, 12 отдельных Sheets.
- Не трогать: `agent/`, `run_agent.py`, `cli.py`, `hermes_state.py`, `tests/` (upstream), `cron/scheduler.py`, `gateway/platforms/*` кроме `telegram.py`. **`notes_log.py` и `diary.py` — НЕ менять** (только читать их контракт).
- Privacy guard (`memory/soul.md`): партнёры → псевдонимы, цены → диапазоны, банк/медицина → отказ. Применяется на уровне LLM в `/notes`, в Sheet попадает уже redacted-текст.
- Phase 1: никаких subagents в skill execution, не отправлять сообщения от имени user, не генерировать письма. Этот срез — только запись данных в Sheet, в рамках Phase 1.
- Commit convention: `feat(ceo-os): ...`.

## Допущение (подтверждено spec)

Вход = **пост-встречная голосовая заметка** по существующему пайплайну `voice → STT → /notes`. **НЕ** живое аудио встречи с диаризацией (out of scope).

## Out of scope

Живое аудио/диаризация; командировки (#1); обобщённый task-трекер (#4); email-доставка протокола; 12 отдельных Sheets; любая обобщённость «на будущее».

---

## Известные факты (из research, опора для задач)

- `/notes` helper: `python <skill>/notes/scripts/notes_log.py --save '<JSON>'` → возвращает `{"saved_path","index_path","action_items_count",...}`.
  JSON-схема `/notes`: `topic, meeting_type, date(ISO), participants[], decisions[], action_items[], summary, raw_text`.
- `/diary` protocol helper: `python <skill>/diary/scripts/diary.py --save '<JSON>'`, схема protocol: `kind="protocol", topic, participants[], decisions[], action_items[], summary, raw_text`.
- `action_items` формат строки: `"owner / дедлайн — описание"` (диктуется существующими скиллами).
- `google_api.py` CLI:
  - `sheets get SHEET_ID "Лист!A1:Z"` → `{"values":[[...]]}`
  - `sheets append SHEET_ID "Лист!A:Z" --values '[[...]]'` → `{"updatedCells":N}` (`valueInputOption=USER_ENTERED`, `insertDataOption=INSERT_ROWS`)
  - SCOPES содержат `https://www.googleapis.com/auth/spreadsheets` (write) — re-consent не нужен **если токен выдан после добавления scope** (проверяется в Task 0).
- 12 направлений (`memory/areas.md`, точные ярлыки): `CEO / Tandem Group`, `Finance & Capital`, `Health`, `Супруга`, `Parents`, `Sport`, `Learning`, `Travel & Recovery`, `Brasov Apartment`, `Pharma Project Romania`, `Personal Expertise`, `Knowledge Capitalization`.

---

## Схема колонок

### Вкладка `Протоколы` (1 строка = 1 встреча)

| Кол. | Поле | Источник | Пример |
|---|---|---|---|
| A | `note_id` | `saved_path` из `/notes` (уникален: `YYYY-MM-DD/HHMM-slug.md`) | `2026-06-24/1430-tandem-supply.md` |
| B | `date` | `date` (ISO) | `2026-06-24` |
| C | `time` | `HHMM` из `saved_path` | `14:30` |
| D | `направление` | классификатор (см. ниже) | `Finance & Capital` |
| E | `topic` | `topic` | `Переговоры с поставщиком ЛДСП` |
| F | `participants` | `participants[]` → `; ` join (redacted) | `Поставщик A; CFO` |
| G | `summary` | `summary` | `Согласовали отсрочку…` |
| H | `decisions` | `decisions[]` → нумерованный join | `1) … 2) …` |
| I | `action_items_count` | `len(action_items)` | `3` |
| J | `created_at` | момент записи (ISO, UTC) | `2026-06-24T15:10:00Z` |

### Вкладка `Задачи` (1 строка = 1 action item)

| Кол. | Поле | Источник | Пример |
|---|---|---|---|
| A | `task_id` | `note_id + "#" + index` | `2026-06-24/1430-tandem-supply.md#0` |
| B | `note_id` | родительская встреча (для связи) | `2026-06-24/1430-tandem-supply.md` |
| C | `date` | `date` встречи | `2026-06-24` |
| D | `направление` | то же, что у встречи | `Finance & Capital` |
| E | `topic` | `topic` встречи | `Переговоры с поставщиком ЛДСП` |
| F | `task` | текст после `—` в `action_item` (или вся строка) | `Прислать обновлённый прайс` |
| G | `owner` | до первого `/` в `action_item` (или пусто) | `Поставщик A` |
| H | `due` | между первым `/` и `—` (или пусто) | `до 27.06` |
| I | `status` | константа `open` при создании | `open` |
| J | `created_at` | момент записи (ISO, UTC) | `2026-06-24T15:10:00Z` |

> Парсинг `action_item`: формат `owner / due — описание`. Если разделителей нет — `owner`/`due` пустые, `task` = вся строка. Сознательно простой (нет NLP).

## Классификация направления

Порядок (первый сработавший побеждает):

1. **Явный тег** — если в `raw_text`/`summary` есть `по <Направление>:` или `#<Направление>` (case-insensitive, по точным/частичным ярлыкам из 12) → берём его.
2. **LLM-классификация** — `/notes` уже видит весь текст; в его `SKILL.md` добавляем инструкцию вернуть поле `area` = ровно один из 12 ярлыков. Скрипт принимает `--area`.
3. **Фолбэк** — если `area` пуст/не из списка 12 → `Не определено`.

> Скрипт **валидирует** `area` против списка 12 (+ `Не определено`). Невалидное значение → `Не определено` (без падения).

## Где живёт Sheet ID

- Env `HERMES_MEETING_SHEET_ID`. Скрипт читает `os.environ.get("HERMES_MEETING_SHEET_ID")`. Если пусто → корректная ошибка с инструкцией (stop, действие CEO).
- НЕ в `config.yaml`, НЕ в git.

---

## File Structure

- **Create:** `skills/ceo/_lib/sheets_meeting_sync.py` — единственный новый модуль: классификация-валидация area, парсинг action_items, построение строк, идемпотентный append, CLI + `--dry-run`.
- **Create:** `tests/ceo/test_sheets_meeting_sync.py` — unit-тесты (google_api замокан).
- **Modify (только текст-инструкция, не Python-логика):** `skills/ceo/notes/SKILL.md` — добавить поле `area` в JSON-схему + один шаг «после успешного `notes_log.py --save` вызови `sheets_meeting_sync.py`».
- **Read-only справка:** `skills/productivity/google-workspace/scripts/google_api.py`, `skills/ceo/notes/scripts/notes_log.py`, `skills/ceo/_lib/memory.py`, `memory/areas.md`.

Почему один файл: вся новая логика — это «преобразовать готовый JSON в строки и добавить их в Sheet». Одна ответственность, держится в контексте целиком.

---

## Task 0: Pre-flight (CEO action + проверка scope) — БЛОКИРУЮЩАЯ

**Files:** нет изменений кода.

**Interfaces:**
- Produces: рабочий `HERMES_MEETING_SHEET_ID`, подтверждённый write-доступ к Sheet.

- [ ] **Step 1 (CEO):** Создать пустой Google Sheet «Hermes — Протоколы и задачи». Создать в нём 2 вкладки с точными именами: `Протоколы`, `Задачи`. В строку 1 каждой вкладки вписать заголовки колонок из схемы выше.
- [ ] **Step 2 (CEO):** Расшарить Sheet на тот же Google-аккаунт, под которым выдан OAuth-токен Hermes (alexandr.scerbina@gmail.com), с правом «Редактор».
- [ ] **Step 3 (CEO):** Передать Sheet ID (из URL `/d/<ID>/edit`). Claude пропишет его в env (`HERMES_MEETING_SHEET_ID`) на Railway и в локальный `.env`.
- [ ] **Step 4 (verify scope, read-only):** Подтвердить, что выданный токен реально содержит write-scope, **не читая токен**:

Run (local, secret-safe):
```bash
python skills/productivity/google-workspace/scripts/google_api.py sheets get "$HERMES_MEETING_SHEET_ID" "Протоколы!A1:J1"
```
Expected: JSON с заголовками строки 1 (доступ есть).

- [ ] **Step 5 (verify write):** Пробная запись в пустую служебную область и удаление вручную CEO (или запись в `Задачи!A1` no-op):
```bash
python skills/productivity/google-workspace/scripts/google_api.py sheets append "$HERMES_MEETING_SHEET_ID" "Задачи!A:J" --values '[["__selftest__","","","","","","","","",""]]'
```
Expected: `{"updatedCells": ...}` без ошибки.
**Stop condition:** если ошибка `403 insufficient authentication scopes` / `PERMISSION_DENIED` → токен старый, нужен re-consent OAuth (**действие CEO**), стоп. Строку `__selftest__` после успеха удалить (CEO вручную или Task 6 dry-run больше её не трогает).

---

## Task 1: Классификация и валидация направления

**Files:**
- Create: `skills/ceo/_lib/sheets_meeting_sync.py`
- Test: `tests/ceo/test_sheets_meeting_sync.py`

**Interfaces:**
- Produces: `AREAS: list[str]` (12 ярлыков + не входит `Не определено`); `classify_area(area_hint: str|None, text: str) -> str`.

- [ ] **Step 1: Write the failing test**
```python
# tests/ceo/test_sheets_meeting_sync.py
from skills.ceo._lib.sheets_meeting_sync import classify_area, AREAS

def test_explicit_tag_wins():
    assert classify_area(None, "по Finance & Capital: обсудили cashflow") == "Finance & Capital"

def test_area_hint_used_when_valid():
    assert classify_area("Health", "разговор про сон") == "Health"

def test_invalid_hint_falls_back():
    assert classify_area("Маркетинг", "что-то непонятное") == "Не определено"

def test_empty_falls_back():
    assert classify_area(None, "ничего конкретного") == "Не определено"

def test_twelve_areas_present():
    assert "CEO / Tandem Group" in AREAS and len(AREAS) == 12
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/ceo/test_sheets_meeting_sync.py -v`
Expected: FAIL (ModuleNotFoundError / classify_area not defined).

- [ ] **Step 3: Write minimal implementation**
```python
# skills/ceo/_lib/sheets_meeting_sync.py
from __future__ import annotations
import re

AREAS = [
    "CEO / Tandem Group", "Finance & Capital", "Health", "Супруга",
    "Parents", "Sport", "Learning", "Travel & Recovery",
    "Brasov Apartment", "Pharma Project Romania",
    "Personal Expertise", "Knowledge Capitalization",
]
UNKNOWN = "Не определено"

def classify_area(area_hint: str | None, text: str) -> str:
    # 1) explicit tag "по <area>:" or "#<area>" wins
    low = (text or "").lower()
    for a in AREAS:
        if f"по {a.lower()}" in low or f"#{a.lower()}" in low:
            return a
    # 2) LLM-provided hint, if valid
    if area_hint and area_hint.strip() in AREAS:
        return area_hint.strip()
    # 3) fallback
    return UNKNOWN
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/ceo/test_sheets_meeting_sync.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**
```bash
git add skills/ceo/_lib/sheets_meeting_sync.py tests/ceo/test_sheets_meeting_sync.py
git commit -m "feat(ceo-os): area classifier for meeting→sheets"
```

---

## Task 2: Парсинг action_items + построение строк обеих вкладок

**Files:**
- Modify: `skills/ceo/_lib/sheets_meeting_sync.py`
- Test: `tests/ceo/test_sheets_meeting_sync.py`

**Interfaces:**
- Consumes: `classify_area` (Task 1).
- Produces:
  - `parse_action_item(s: str) -> tuple[str, str, str]` → `(owner, due, task)`
  - `build_protocol_row(note: dict, note_id: str, area: str, now_iso: str) -> list[str]` → 10 значений (A..J)
  - `build_task_rows(note: dict, note_id: str, area: str, now_iso: str) -> list[list[str]]` → по строке на action item

- [ ] **Step 1: Write the failing test**
```python
from skills.ceo._lib.sheets_meeting_sync import (
    parse_action_item, build_protocol_row, build_task_rows,
)

NOTE = {
    "topic": "Переговоры с поставщиком",
    "date": "2026-06-24",
    "participants": ["Поставщик A", "CFO"],
    "summary": "Согласовали отсрочку.",
    "decisions": ["Берём отсрочку 30 дней"],
    "action_items": ["Поставщик A / до 27.06 — прислать прайс", "Подготовить договор"],
}
NID = "2026-06-24/1430-postavshchik.md"

def test_parse_full():
    assert parse_action_item("Поставщик A / до 27.06 — прислать прайс") == ("Поставщик A","до 27.06","прислать прайс")

def test_parse_plain():
    assert parse_action_item("Подготовить договор") == ("","","Подготовить договор")

def test_protocol_row_shape():
    row = build_protocol_row(NOTE, NID, "Finance & Capital", "2026-06-24T15:10:00Z")
    assert len(row) == 10
    assert row[0] == NID and row[1] == "2026-06-24" and row[2] == "14:30"
    assert row[3] == "Finance & Capital" and row[8] == "2"

def test_task_rows():
    rows = build_task_rows(NOTE, NID, "Finance & Capital", "2026-06-24T15:10:00Z")
    assert len(rows) == 2
    assert rows[0][0] == NID + "#0" and rows[0][6] == "Поставщик A" and rows[0][8] == "open"
    assert rows[1][5] == "Подготовить договор"
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/ceo/test_sheets_meeting_sync.py -v`
Expected: FAIL (functions not defined).

- [ ] **Step 3: Write minimal implementation** (append to module)
```python
def _time_from_note_id(note_id: str) -> str:
    m = re.search(r"/(\d{2})(\d{2})-", note_id or "")
    return f"{m.group(1)}:{m.group(2)}" if m else ""

def parse_action_item(s: str) -> tuple[str, str, str]:
    s = (s or "").strip()
    owner, due, task = "", "", s
    if "—" in s:
        left, task = s.split("—", 1)
        task = task.strip()
        if "/" in left:
            owner, due = [p.strip() for p in left.split("/", 1)]
        else:
            owner = left.strip()
    return owner, due, task

def build_protocol_row(note: dict, note_id: str, area: str, now_iso: str) -> list[str]:
    ai = note.get("action_items") or []
    decisions = note.get("decisions") or []
    return [
        note_id,
        note.get("date", ""),
        _time_from_note_id(note_id),
        area,
        note.get("topic", ""),
        "; ".join(note.get("participants") or []),
        note.get("summary", ""),
        " ".join(f"{i+1}) {d}" for i, d in enumerate(decisions)),
        str(len(ai)),
        now_iso,
    ]

def build_task_rows(note: dict, note_id: str, area: str, now_iso: str) -> list[list[str]]:
    rows = []
    for i, item in enumerate(note.get("action_items") or []):
        owner, due, task = parse_action_item(item)
        rows.append([
            f"{note_id}#{i}", note_id, note.get("date", ""), area,
            note.get("topic", ""), task, owner, due, "open", now_iso,
        ])
    return rows
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/ceo/test_sheets_meeting_sync.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add skills/ceo/_lib/sheets_meeting_sync.py tests/ceo/test_sheets_meeting_sync.py
git commit -m "feat(ceo-os): build protocol/task rows from note JSON"
```

---

## Task 3: Идемпотентный append (через google_api), с dry-run

**Files:**
- Modify: `skills/ceo/_lib/sheets_meeting_sync.py`
- Test: `tests/ceo/test_sheets_meeting_sync.py`

**Interfaces:**
- Consumes: `build_protocol_row`, `build_task_rows`.
- Produces: `sync_note(note: dict, area_hint: str|None, sheet_id: str, gw, now_iso: str, dry_run: bool=False) -> dict`
  где `gw` — адаптер с методами `get(sheet_id, rng) -> list[list[str]]` и `append(sheet_id, rng, values) -> None` (обёртка над `google_api.py`; в тестах мок).
  Возвращает `{"protocol_written": bool, "tasks_written": int, "skipped": bool, "area": str}`.

- [ ] **Step 1: Write the failing test** (mock gw — без реальных вызовов Google)
```python
from skills.ceo._lib.sheets_meeting_sync import sync_note

class FakeGW:
    def __init__(self, existing_ids=None):
        self.existing = existing_ids or []
        self.appended = []  # (range, values)
    def get(self, sheet_id, rng):
        # вернуть колонку note_id для Протоколы!A:A
        return [[i] for i in self.existing]
    def append(self, sheet_id, rng, values):
        self.appended.append((rng, values))

NOTE = {"topic":"T","date":"2026-06-24","participants":[],"summary":"s",
        "decisions":[],"action_items":["a / d — x","y"]}
NID = "2026-06-24/1430-t.md"

def test_first_write_appends_both_tabs():
    gw = FakeGW()
    res = sync_note(NOTE, "Health", "SID", gw, "2026-06-24T15:00:00Z", note_id=NID)
    assert res["protocol_written"] and res["tasks_written"] == 2 and not res["skipped"]
    ranges = [r for r, _ in gw.appended]
    assert any("Протоколы" in r for r in ranges) and any("Задачи" in r for r in ranges)

def test_idempotent_skip_when_note_id_exists():
    gw = FakeGW(existing_ids=[NID])
    res = sync_note(NOTE, "Health", "SID", gw, "2026-06-24T15:00:00Z", note_id=NID)
    assert res["skipped"] and res["tasks_written"] == 0 and gw.appended == []

def test_dry_run_writes_nothing():
    gw = FakeGW()
    res = sync_note(NOTE, "Health", "SID", gw, "2026-06-24T15:00:00Z", note_id=NID, dry_run=True)
    assert gw.appended == [] and res["protocol_written"] is True  # planned, not executed
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/ceo/test_sheets_meeting_sync.py -v`
Expected: FAIL (sync_note not defined).

- [ ] **Step 3: Write minimal implementation**
```python
def sync_note(note, area_hint, sheet_id, gw, now_iso, *, note_id, dry_run=False):
    text = " ".join([note.get("summary", ""), note.get("raw_text", "")])
    area = classify_area(area_hint, text)
    existing = {row[0] for row in gw.get(sheet_id, "Протоколы!A:A") if row}
    if note_id in existing:
        return {"protocol_written": False, "tasks_written": 0, "skipped": True, "area": area}
    proto = build_protocol_row(note, note_id, area, now_iso)
    tasks = build_task_rows(note, note_id, area, now_iso)
    if not dry_run:
        gw.append(sheet_id, "Протоколы!A:J", [proto])
        if tasks:
            gw.append(sheet_id, "Задачи!A:J", tasks)
    return {"protocol_written": True, "tasks_written": len(tasks), "skipped": False, "area": area}
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/ceo/test_sheets_meeting_sync.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add skills/ceo/_lib/sheets_meeting_sync.py tests/ceo/test_sheets_meeting_sync.py
git commit -m "feat(ceo-os): idempotent sync_note with dry-run"
```

---

## Task 4: CLI-обёртка + реальный google_api адаптер

**Files:**
- Modify: `skills/ceo/_lib/sheets_meeting_sync.py`
- Test: `tests/ceo/test_sheets_meeting_sync.py`

**Interfaces:**
- Produces: `main(argv)` — CLI `--save '<JSON>' [--area X] [--note-id ID] [--dry-run]`; класс `GoogleApiGW` (вызывает `google_api.py` через subprocess, парсит JSON).

- [ ] **Step 1: Write the failing test** (CLI парсинг + GW адаптер на subprocess замокан)
```python
import json, subprocess
from skills.ceo._lib import sheets_meeting_sync as m

def test_cli_requires_sheet_id(monkeypatch, capsys):
    monkeypatch.delenv("HERMES_MEETING_SHEET_ID", raising=False)
    rc = m.main(["--save", json.dumps({"topic":"t","action_items":[]}), "--note-id","x"])
    assert rc != 0
    assert "HERMES_MEETING_SHEET_ID" in capsys.readouterr().err

def test_gw_get_parses_subprocess(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout):
        class R: returncode=0; stdout=json.dumps({"values":[["id1"]]}); stderr=""
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)
    gw = m.GoogleApiGW("/path/google_api.py")
    assert gw.get("SID","Протоколы!A:A") == [["id1"]]
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/ceo/test_sheets_meeting_sync.py -v`
Expected: FAIL (main/GoogleApiGW not defined).

- [ ] **Step 3: Write minimal implementation**
```python
import os, sys, json, subprocess, datetime as _dt, argparse

GOOGLE_API = os.environ.get(
    "HERMES_GOOGLE_API",
    "/opt/hermes/skills/productivity/google-workspace/scripts/google_api.py",
)

class GoogleApiGW:
    def __init__(self, script=GOOGLE_API):
        self.script = script
    def _run(self, *args):
        r = subprocess.run([sys.executable, self.script, *args],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError(f"google_api failed: {r.stderr.strip()[:300]}")
        return r.stdout
    def get(self, sheet_id, rng):
        out = self._run("sheets", "get", sheet_id, rng)
        return (json.loads(out) or {}).get("values", []) if out.strip() else []
    def append(self, sheet_id, rng, values):
        self._run("sheets", "append", sheet_id, rng, "--values", json.dumps(values, ensure_ascii=False))

def _now_iso():
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", required=True)
    ap.add_argument("--area", default=None)
    ap.add_argument("--note-id", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    sheet_id = os.environ.get("HERMES_MEETING_SHEET_ID")
    if not sheet_id:
        sys.stderr.write("HERMES_MEETING_SHEET_ID is not set — CEO must create Sheet and set env.\n")
        return 2
    note = json.loads(a.save)
    res = sync_note(note, a.area, sheet_id, GoogleApiGW(), _now_iso(),
                    note_id=a.note_id, dry_run=a.dry_run)
    print(json.dumps(res, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/ceo/test_sheets_meeting_sync.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add skills/ceo/_lib/sheets_meeting_sync.py tests/ceo/test_sheets_meeting_sync.py
git commit -m "feat(ceo-os): CLI + google_api adapter for meeting sync"
```

---

## Task 5: Подключить шаг в `/notes` SKILL.md (без правки Python)

**Files:**
- Modify: `skills/ceo/notes/SKILL.md`

**Interfaces:**
- Consumes: `saved_path` из `notes_log.py` (как `--note-id`), весь JSON (как `--save`), `area` от LLM.

- [ ] **Step 1:** В JSON-схеме `/notes` (раздел Step 4) добавить **опциональное** поле `"area"` — один из 12 ярлыков `areas.md` или пусто; инструкция LLM: классифицировать встречу в одно направление, явный тег «по <Направление>:» перекрывает.
- [ ] **Step 2:** Добавить шаг после успешного `notes_log.py --save` (только для `meeting_type ∈ {meeting, call, protocol}`):
```bash
python skills/ceo/_lib/sheets_meeting_sync.py --save '<тот же JSON>' --area '<area>' --note-id '<saved_path из ответа notes_log>'
```
с пометкой: ошибки Sheets-синка **не блокируют** сохранение `.md` (best-effort; вывести предупреждение, не падать).
- [ ] **Step 3 (verify, не меняя Python):** прогнать существующие тесты `/notes`, убедиться что контракт `notes_log.py` не затронут.
Run: `pytest tests/ -k notes -v` (если есть) и `python skills/ceo/notes/scripts/notes_log.py --gather` — Expected: без изменений в поведении.
- [ ] **Step 4: Commit**
```bash
git add skills/ceo/notes/SKILL.md
git commit -m "feat(ceo-os): wire /notes → meeting sheet sync (instruction step)"
```

---

## Task 6: End-to-end проверка на тестовом Sheet + регрессия

**Files:** нет изменений кода.

- [ ] **Step 1 (dry-run):** на реальном `HERMES_MEETING_SHEET_ID`:
```bash
python skills/ceo/_lib/sheets_meeting_sync.py --save '{"topic":"Тест поставщик","date":"2026-06-24","participants":["Поставщик A"],"summary":"по Finance & Capital: отсрочка","decisions":["Отсрочка 30 дней"],"action_items":["Поставщик A / до 27.06 — прислать прайс","Подготовить договор"]}' --note-id "2026-06-24/9999-test.md" --dry-run
```
Expected: JSON `{"protocol_written":true,"tasks_written":2,"skipped":false,"area":"Finance & Capital"}`, в Sheet ничего не записано.

- [ ] **Step 2 (реальная запись):** убрать `--dry-run`. Expected: 1 строка в `Протоколы`, 2 строки в `Задачи`, `направление=Finance & Capital`.
- [ ] **Step 3 (идемпотентность):** повторить ту же команду. Expected: `{"skipped":true,...}`, новых строк нет.
- [ ] **Step 4 (классификация, 3 примера):** прогнать с `summary` без тега для `Health`, `CEO / Tandem Group`, мусорного → проверить `area` (`Health` по hint, корректное направление, `Не определено`).
- [ ] **Step 5 (мобильный):** CEO открывает Sheet с телефона — строки видны.
- [ ] **Step 6 (регрессия):** убедиться, что `/notes` и `/diary` сохраняют `.md` как раньше (создать обычную заметку, проверить файл в `logs/notes/`).
- [ ] **Step 7:** удалить тестовые строки (`note_id` `...9999-test.md` и `__selftest__`) — CEO вручную или оставить как смоук-маркер.

---

## Минимальный vs рекомендованный вариант

- **Минимальный (ручной вызов):** Tasks 0–4 + 6. Скрипт работает как отдельная команда; CEO/ассистент вызывает `sheets_meeting_sync.py` вручную после `/notes`. Ноль касаний `/notes`. Самый безопасный, но не автоматический.
- **Рекомендованный (авто через /notes):** + Task 5. Голос → `/notes` → и `.md`, и Sheet автоматически. Касание `/notes` минимальное (только текст SKILL.md, без правки `notes_log.py`), синк best-effort и не ломает сохранение заметки.

Рекомендация: **рекомендованный** — он и есть «реальная работа ассистента» из брифа, а риск ограничен (Python `/notes` не трогаем; синк не блокирует `.md`).

## Риски и откат

| Риск | Митигация | Откат |
|---|---|---|
| Токен без write-scope (старый) | Task 0 Step 5 ловит до реализации | Stop → CEO re-consent OAuth |
| Sheets-синк падает и роняет `/notes` | best-effort обёртка (Task 5 Step 2): ошибка → warning, не raise | `.md` всё равно сохранён |
| Дубли при ретраях | идемпотентность по `note_id`/`task_id` (Task 3) | повтор → `skipped` |
| Неверная классификация | явный тег перекрывает; фолбэк `Не определено` (не теряем строку) | поправить ярлык в Sheet вручную |
| Privacy leak в Sheet | в Sheet попадает уже redacted текст из `/notes` (guard на LLM-уровне) | удалить строку |
| Регрессия `/notes`/`/diary` | Python не трогаем; Task 6 Step 6 регрессия | `git revert` SKILL.md |

## Stop conditions

- `403 / PERMISSION_DENIED` на write → стоп, re-consent (CEO).
- Нужно создать/расшарить Sheet или менять env → стоп, согласование CEO.
- Любой намёк на утечку env при проверках → стоп.

---

## Self-Review (против spec)

- ✅ Вход = пост-встречная голосовая заметка (допущение зафиксировано, диаризация out of scope).
- ✅ Один мастер-Sheet, 2 вкладки `Протоколы`/`Задачи`, 1 строка/встреча и 1 строка/action item.
- ✅ Колонка `направление` в обеих; классификация: явный тег → LLM-hint → `Не определено`.
- ✅ Идемпотентность по `note_id`/`task_id`, без потери данных.
- ✅ Переиспользование: voice→STT, `/notes` извлечение, `google_api.py` sheets — новый код только склейка.
- ✅ Sheet ID в env; создание/шеринг Sheet и re-consent — действия CEO (Task 0, stop conditions).
- ✅ Минимальный scope; нет абстрактного storage-слоя, нет 12 Sheets, нет email-доставки.
- ✅ Тесты: dry-run в тестовый Sheet, классификация на примерах, регрессия `/notes`/`/diary`.
- ✅ Минимальный и рекомендованный варианты предложены.
- ✅ Privacy guard, Phase 1, «не трогать» соблюдены.
