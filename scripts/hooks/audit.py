#!/usr/bin/env python3
"""CEO OS post_tool_call audit (INSTRUCTION_02).

Append a one-line record of every tool call to
``$HERMES_HOME/logs/hooks/audit.log`` for post-incident review. Observer only:
emits no stdout, so it never blocks or alters a tool call.

Wire contract (agent/shell_hooks.py): reads the hook JSON on stdin.
Fail-open: any error is swallowed so logging can never break the agent.
"""
import sys
import os
import json
import datetime


def main() -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        return
    data = json.loads(raw)
    home = os.environ.get("HERMES_HOME", "/opt/data")
    logdir = os.path.join(home, "logs", "hooks")
    os.makedirs(logdir, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tool = data.get("tool_name") or "?"
    sid = str(data.get("session_id") or "")[:12]
    with open(os.path.join(logdir, "audit.log"), "a", encoding="utf-8") as fh:
        fh.write(f"{ts}\t{tool}\tsession={sid}\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
