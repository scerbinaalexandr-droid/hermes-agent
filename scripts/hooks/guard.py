#!/usr/bin/env python3
"""CEO OS pre_tool_call guard (INSTRUCTION_02).

Covers ONLY the gaps not already handled by Hermes' native security layers
(tools/approval.py already gates .env / config.yaml / rm -rf / chmod 777 /
curl|sh; agent/file_safety.py blocks .ssh / system files). This guard adds:

  1. memory/*.md protection  — block direct write/delete of CEO memory files
     (soul, decisions, projects, ...) via write_file/patch tool or via shell
     redirect/rm/mv/tee/sed. Legit edits go through /capture, /evening, /week
     skills (which write inside their own Python, not via these tool calls).
  2. git push block          — the agent must never push; Alexandr pushes
     manually from CLI.
  3. curl/wget exfiltration  — block uploading a local file to an external URL
     (-d @file / --data-binary @ / -F ...=@ / --post-file), a classic
     prompt-injection data-exfil vector.

Wire contract (agent/shell_hooks.py):
  stdin  : {"hook_event_name","tool_name","tool_input":{...},"session_id","cwd","extra"}
  stdout : {"decision":"block","reason":"..."}  -> blocks the tool call
           (empty / anything else) -> allow

Fail-open by design: any parse/logic error -> allow. The native approval.py
hardline blocklist remains the fail-closed floor below this guard, so a bug
here can never strip the catastrophic-command protection.
"""
import sys
import json
import re

# Exact CEO memory filenames (precise list -> low false-positive rate).
_MEM_RE = re.compile(
    r'(?:[\w.\-/]*?/)?memory/'
    r'(?:soul|decisions|projects|areas|goals|risks|user|memory|daily_log|weekly_review)'
    r'\.md\b',
    re.IGNORECASE,
)
# Shell write/delete operators that indicate a mutation (reads like cat/grep pass).
_WRITE_OP_RE = re.compile(r'(>>?|(?<!\w)(?:rm|mv|cp|tee|truncate|dd)\b|sed\s+-i)')
_GIT_PUSH_RE = re.compile(r'\bgit\s+push\b')
# curl/wget uploading a local file to a URL.
_EXFIL_RE = re.compile(
    r'\b(?:curl|wget)\b.*'
    r'(?:--data-binary|--data|-d|-F\s*\S*=|--post-file=?)\s*@',
    re.IGNORECASE | re.DOTALL,
)


def _block(reason: str) -> None:
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def main() -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        return
    data = json.loads(raw)
    tool = (data.get("tool_name") or "").strip()
    ti = data.get("tool_input")
    ti = ti if isinstance(ti, dict) else {}
    blob = " ".join(str(v) for v in ti.values()) if ti else str(data.get("tool_input") or "")

    if tool in ("write_file", "patch"):
        if _MEM_RE.search(blob):
            _block(
                "Прямая запись/патч в memory/*.md заблокирована (CEO OS guard). "
                "Память меняется только через скиллы /capture, /evening, /week — "
                "или попроси Александра подтвердить изменение в чате."
            )

    if tool in ("terminal", "execute_code"):
        cmd = str(ti.get("command") or ti.get("code") or blob)
        if _GIT_PUSH_RE.search(cmd):
            _block(
                "git push от агента заблокирован (CEO OS guard). "
                "Пуш в репозиторий делает Александр вручную из CLI."
            )
        if _EXFIL_RE.search(cmd):
            _block(
                "Отправка локального файла на внешний URL заблокирована "
                "(CEO OS guard — защита от exfiltration). Если это легитимная "
                "загрузка — попроси Александра."
            )
        if _MEM_RE.search(cmd) and _WRITE_OP_RE.search(cmd):
            _block(
                "Изменение memory/*.md через shell заблокировано (CEO OS guard). "
                "Используй скилл /capture, /evening или /week."
            )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # fail-open: never break the tool flow on a guard bug; native
        # approval.py hardline blocklist is the fail-closed floor.
        pass
