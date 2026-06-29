"""CEO-OS guard: SOUL.md (persona) write protection — blocks direct writes but
leaves the sanctioned /tune subprocess append and plain reads untouched."""
import json
import pathlib
import subprocess
import sys

GUARD = str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "guard.py")


def _run(payload: dict) -> str:
    r = subprocess.run([sys.executable, GUARD], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=20)
    return (r.stdout or "").strip()


def _blocked(out: str) -> bool:
    return bool(out) and json.loads(out).get("decision") == "block"


def test_write_file_to_soul_blocked():
    out = _run({"tool_name": "write_file",
                "tool_input": {"path": "/opt/data/SOUL.md", "content": "x"}})
    assert _blocked(out) and "SOUL.md" in out


def test_shell_redirect_into_soul_blocked():
    out = _run({"tool_name": "terminal",
                "tool_input": {"command": "echo hi >> /opt/data/SOUL.md"}})
    assert _blocked(out)


def test_tune_subprocess_allowed():
    # the sanctioned mutation path — no /SOUL.md in argv, no shell write-op
    out = _run({"tool_name": "terminal",
                "tool_input": {"command": "python /opt/hermes/skills/ceo/tune/scripts/tune.py --rule \"пиши короче\""}})
    assert not _blocked(out)


def test_reading_soul_allowed():
    out = _run({"tool_name": "terminal",
                "tool_input": {"command": "cat /opt/data/SOUL.md"}})
    assert not _blocked(out)


def test_memory_md_still_blocked():
    out = _run({"tool_name": "write_file",
                "tool_input": {"path": "memory/soul.md", "content": "x"}})
    assert _blocked(out)


def test_python_open_write_to_soul_blocked():
    out = _run({"tool_name": "execute_code",
                "tool_input": {"code": "open('/opt/data/SOUL.md','w').write('x')"}})
    assert _blocked(out)


def test_cd_relative_redirect_to_soul_blocked():
    out = _run({"tool_name": "terminal",
                "tool_input": {"command": "cd /opt/data && echo hi >> SOUL.md"}})
    assert _blocked(out)


def test_write_text_to_soul_blocked():
    out = _run({"tool_name": "execute_code",
                "tool_input": {"code": "import pathlib; pathlib.Path('/opt/data/SOUL.md').write_text('x')"}})
    assert _blocked(out)


def test_tune_subprocess_with_soul_word_in_rule_allowed():
    # a rule that mentions "SOUL.md" but runs via tune.py (no write-op) must NOT block
    out = _run({"tool_name": "terminal",
                "tool_input": {"command": "python /opt/hermes/skills/ceo/tune/scripts/tune.py --rule \"не пиши про SOUL.md\""}})
    assert not _blocked(out)
