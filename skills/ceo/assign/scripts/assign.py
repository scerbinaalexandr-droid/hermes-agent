#!/usr/bin/env python3
"""Put an assignment on the «Поручения» board for a named worker profile.

    python skills/ceo/assign/scripts/assign.py --role researcher \
        --title "Рынок продажи бизнесов в Австрии" \
        --brief "<полная постановка: что нужно, зачем, что считать готовым>" \
        [--priority 0|1|2] [--chat-id <telegram chat>]

Prints JSON. The owner's Telegram chat is subscribed to the task so the
gateway delivers one line when the worker finishes or blocks.
`--roles` lists the available workers.
"""
import argparse
import json
import os
import pathlib
import sys

_p = os.environ.get("HERMES_AGENT_DIR", "/opt/hermes")
if _p not in sys.path and pathlib.Path(_p).exists():
    sys.path.insert(0, _p)

BOARD = "assignments"
BOARD_NAME = "Поручения"
ROLES = {
    "researcher": "🔎 Ресерчер — изучить, найти, сравнить, собрать источники",
    "analyst":    "📊 Аналитик — таблицы, расчёты, выгрузки, Excel",
    "scribe":     "📝 Протоколист — транскрипт → резюме, решения, задачи",
    "writer":     "✍️ Редактор — тексты, КП, описания, черновики писем",
}
OWNER_CHAT = os.environ.get("HERMES_OWNER_CHAT_ID", "385068170")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--roles", action="store_true")
    ap.add_argument("--role")
    ap.add_argument("--title")
    ap.add_argument("--brief", default="")
    ap.add_argument("--priority", type=int, default=0)
    ap.add_argument("--chat-id", default=OWNER_CHAT)
    args = ap.parse_args()

    if args.roles:
        print(json.dumps({"roles": ROLES}, ensure_ascii=False, indent=2))
        return 0
    if args.role not in ROLES or not args.title:
        print(json.dumps({"ok": False, "error": "bad_args",
                          "message": "Нужны роль и название поручения.",
                          "roles": list(ROLES)}, ensure_ascii=False))
        return 0

    import hermes_cli.kanban_db as k
    k.create_board(BOARD, name=BOARD_NAME, icon="📨", color="#b69668")
    conn = k.connect(board=BOARD)
    try:
        task_id = k.create_task(
            conn,
            title=args.title.strip(),
            body=args.brief.strip() or None,
            assignee=args.role,
            created_by="Александр",
            priority=max(0, min(args.priority, 2)),
            max_runtime_seconds=1800,  # a worker never runs longer than 30 min
        )
        if not isinstance(task_id, str):
            task_id = getattr(task_id, "id", str(task_id))
        k.add_notify_sub(conn, task_id=task_id, platform="telegram", chat_id=str(args.chat_id))
    finally:
        conn.close()
    print(json.dumps({"ok": True, "id": task_id, "board": BOARD, "role": args.role,
                      "title": args.title.strip()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # the skill turns this into one human sentence
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        sys.exit(0)
