"""Задачи CEO на канбан-досках — единственное место хранения.

Раньше задачи жили во вкладке Google-таблицы (tasks_list.py). Владелец
потребовал убрать дублирование и работать в приложении, поэтому доски канбана
стали единственным местом, а таблица осталась архивом.

Схема задач Hermes не имеет поля срока (см. kanban_db.SCHEMA_SQL), а трогать
ядро нельзя — поэтому срок пишется в тело задачи строкой `Срок: YYYY-MM-DD`
и оттуда же читается. Формат фиксированный: по нему работают напоминания.

Команды:
  --boards                     список досок с числом открытых задач
  --add --board <slug> --title "..." [--assignee ...] [--due ...] [--note ...]
  --list [--board <slug>] [--days N]   открытые задачи, разложенные по срокам
  --done <task_id> [--board <slug>]    закрыть задачу

Всё возвращает JSON — форматирует ответ уже сам агент.
Ошибки не выбрасываются наружу: помощник не должен ронять диалог.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import re
import sys

# На проде скиллы лежат на волюме, а код Hermes — в образе.
_roots = ["/opt/hermes"]
try:
    _roots.append(str(pathlib.Path(__file__).resolve().parents[4]))
except IndexError:  # запуск из произвольного каталога (например, при проверке)
    pass
for _p in _roots:
    if _p not in sys.path and pathlib.Path(_p).exists():
        sys.path.insert(0, _p)

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Europe/Chisinau")
except Exception:  # pragma: no cover
    _TZ = _dt.timezone(_dt.timedelta(hours=3))

_DUE_RE = re.compile(r"Срок:\s*(\d{4}-\d{2}-\d{2})")
_OPEN_STATUSES = ("triage", "todo", "ready", "running", "blocked")


def _today() -> _dt.date:
    return _dt.datetime.now(_TZ).date()


def _kdb():
    import hermes_cli.kanban_db as k  # импорт отложен: путь настраивается выше
    return k


def _boards() -> list[dict]:
    k = _kdb()
    out = []
    for b in k.list_boards():
        slug = b.get("slug") if isinstance(b, dict) else str(b)
        name = b.get("name") if isinstance(b, dict) else str(b)
        out.append({"slug": slug, "name": name})
    return out


def _open_tasks(board: str) -> list[dict]:
    k = _kdb()
    conn = k.connect(board=board)
    try:
        tasks = k.list_tasks(conn, include_archived=False)
    finally:
        conn.close()
    result = []
    for t in tasks:
        status = getattr(t, "status", "") or ""
        if status not in _OPEN_STATUSES:
            continue
        body = getattr(t, "body", "") or ""
        m = _DUE_RE.search(body)
        result.append({
            "id": getattr(t, "id", ""),
            "title": getattr(t, "title", ""),
            "assignee": getattr(t, "assignee", "") or "",
            "status": status,
            "due": m.group(1) if m else "",
            "board": board,
        })
    return result


def cmd_boards() -> dict:
    rows = []
    for b in _boards():
        try:
            rows.append({**b, "open": len(_open_tasks(b["slug"]))})
        except Exception:
            rows.append({**b, "open": None})
    return {"boards": rows}


def cmd_add(args) -> dict:
    k = _kdb()
    slugs = {b["slug"] for b in _boards()}
    if args.board not in slugs:
        return {"ok": False, "error": "unknown_board",
                "message": f"Доски «{args.board}» нет.",
                "boards": sorted(slugs)}

    parts = []
    if args.note:
        parts.append(args.note.strip())
    if args.due:
        try:
            _dt.date.fromisoformat(args.due)
        except ValueError:
            return {"ok": False, "error": "bad_due",
                    "message": "Срок нужен в формате ГГГГ-ММ-ДД."}
        parts.append(f"Срок: {args.due}")
    body = "\n\n".join(parts) if parts else None

    conn = k.connect(board=args.board)
    try:
        task_id = k.create_task(
            conn,
            title=args.title.strip(),
            body=body,
            assignee=(args.assignee or None),
            created_by=(args.created_by or "Александр"),
        )
    finally:
        conn.close()
    if not isinstance(task_id, str):
        task_id = getattr(task_id, "id", str(task_id))
    return {"ok": True, "id": task_id, "board": args.board,
            "title": args.title.strip(),
            "assignee": args.assignee or "", "due": args.due or ""}


def cmd_list(args) -> dict:
    today = _today()
    horizon = today + _dt.timedelta(days=max(1, args.days))
    boards = [args.board] if args.board else [b["slug"] for b in _boards()]

    overdue, soon, later, no_due = [], [], [], []
    for slug in boards:
        try:
            tasks = _open_tasks(slug)
        except Exception:
            continue
        for t in tasks:
            if not t["due"]:
                no_due.append(t)
                continue
            try:
                d = _dt.date.fromisoformat(t["due"])
            except ValueError:
                no_due.append(t)
                continue
            if d < today:
                t["days_late"] = (today - d).days
                overdue.append(t)
            elif d <= horizon:
                t["days_left"] = (d - today).days
                soon.append(t)
            else:
                later.append(t)

    overdue.sort(key=lambda x: x["due"])
    soon.sort(key=lambda x: x["due"])
    later.sort(key=lambda x: x["due"])
    return {"today": today.isoformat(),
            "total_open": len(overdue) + len(soon) + len(later) + len(no_due),
            "overdue": overdue, "soon": soon, "later": later, "no_due": no_due}


def cmd_done(args) -> dict:
    k = _kdb()
    boards = [args.board] if args.board else [b["slug"] for b in _boards()]
    for slug in boards:
        try:
            conn = k.connect(board=slug)
        except Exception:
            continue
        try:
            task = k.get_task(conn, args.done)
            if task is None:
                continue
            k.complete_task(conn, args.done, result="Закрыто владельцем")
            return {"ok": True, "id": args.done, "board": slug,
                    "title": getattr(task, "title", "")}
        except Exception as e:
            return {"ok": False, "error": type(e).__name__,
                    "message": "Не удалось закрыть задачу."}
        finally:
            conn.close()
    return {"ok": False, "error": "not_found",
            "message": "Задача с таким номером не найдена."}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--boards", action="store_true")
    p.add_argument("--add", action="store_true")
    p.add_argument("--list", action="store_true")
    p.add_argument("--done", metavar="TASK_ID")
    p.add_argument("--board")
    p.add_argument("--title")
    p.add_argument("--assignee")
    p.add_argument("--due", help="ГГГГ-ММ-ДД")
    p.add_argument("--note")
    p.add_argument("--created-by", dest="created_by")
    p.add_argument("--days", type=int, default=7)
    args = p.parse_args()

    try:
        if args.boards:
            out = cmd_boards()
        elif args.add:
            if not (args.board and args.title):
                out = {"ok": False, "error": "missing_args",
                       "message": "Нужны доска и текст задачи."}
            else:
                out = cmd_add(args)
        elif args.done:
            out = cmd_done(args)
        elif args.list:
            out = cmd_list(args)
        else:
            out = {"ok": False, "error": "no_command"}
    except Exception as e:
        out = {"ok": False, "error": type(e).__name__,
               "message": "Не удалось обратиться к доскам."}

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
