#!/usr/bin/env python3
"""Create / refresh the worker profiles for the «Поручения» board.

Run at boot by docker/ceo-os-entrypoint.sh (as the hermes user). Idempotent:
config.yaml and SOUL.md are rewritten from the templates in this skill on
every boot (the repo is the source of truth, like ensure_config.py for the
main profile); memories, sessions and skills of a profile are never touched.

Profiles live at $HERMES_HOME/profiles/<name>/ — where the kanban dispatcher
looks for an assignee. Bundled skills are seeded by Hermes on the worker's
first start; the worker skill itself is enabled via `skills.disabled`.
"""
import os
import sys
from pathlib import Path

import yaml

HOME = Path(os.environ.get("HERMES_HOME", "/opt/data"))
BUNDLED_SKILLS = Path("/opt/hermes/skills")
HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / "profiles"

MODEL = {"default": "claude-sonnet-4-5-20250929", "provider": "anthropic",
         "base_url": "https://api.anthropic.com"}

# role → (toolsets the worker gets, bundled skills it may load)
ROLES = {
    "researcher": (["web", "file", "skills", "todo", "memory"], {"kanban-worker", "humanizer"}),
    "analyst":    (["terminal", "file", "skills", "todo", "memory"], {"kanban-worker", "xlsx", "pdf", "ocr-and-documents"}),
    "scribe":     (["file", "skills", "todo", "memory"], {"kanban-worker", "pdf", "ocr-and-documents"}),
    "writer":     (["file", "skills", "todo", "memory"], {"kanban-worker", "humanizer", "docx"}),
    # «Зеркало»: no web, no terminal — nothing it hears can leave the profile.
    "mirror":     (["file", "skills", "memory"], {"kanban-worker"}),
}
# The therapist keeps a long-term picture of the owner (its own, closed memory);
# other workers only keep notes about their craft.
MEMORY = {
    "default": {"memory_enabled": True, "user_profile_enabled": False,
                "memory_char_limit": 2200, "user_char_limit": 1375},
    "mirror":  {"memory_enabled": True, "user_profile_enabled": True,
                "memory_char_limit": 4400, "user_char_limit": 2750},
}
# Never available to a worker, whatever the toolset list says.
HARD_OFF = ["delegation", "messaging", "cronjob", "browser", "code_execution",
            "tts", "image_gen", "video", "moa", "rl", "homeassistant"]


def bundled_skill_names() -> set[str]:
    names: set[str] = set()
    if BUNDLED_SKILLS.is_dir():
        for md in BUNDLED_SKILLS.rglob("SKILL.md"):
            rel = md.relative_to(BUNDLED_SKILLS)
            if rel.parts and rel.parts[0] not in ("ceo", ".archive"):
                names.add(md.parent.name)
    return names


def profile_config(role: str) -> dict:
    toolsets, keep = ROLES[role]
    return {
        "model": dict(MODEL),
        "toolsets": toolsets,
        "agent": {
            "max_turns": 40,
            "reasoning_effort": "medium",
            "disabled_toolsets": HARD_OFF,
        },
        # No chat to answer an approval prompt: dangerous commands are simply
        # refused (hardline blocklist stays on regardless).
        "approvals": {"mode": "manual", "timeout": 30, "cron_mode": "deny"},
        "command_allowlist": [],
        "terminal": {"backend": "local", "cwd": "."},
        "security": {"redact_secrets": True, "allow_private_urls": False},
        "skills": {"disabled": sorted(bundled_skill_names() - keep)},
        "memory": dict(MEMORY.get(role, MEMORY["default"])),
        "compression": {"enabled": True},
        "display": {"lifecycle_notices": False},
        "auxiliary": {
            t: {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"}
            for t in ("title_generation", "compression", "session_search", "web_extract", "approval")
        },
    }


def main() -> int:
    common = (TEMPLATES / "_common.md").read_text(encoding="utf-8")
    root = HOME / "profiles"
    root.mkdir(parents=True, exist_ok=True)
    for role in ROLES:
        pdir = root / role
        for sub in ("memories", "sessions", "logs", "skills", "cron", "workspace"):
            (pdir / sub).mkdir(parents=True, exist_ok=True)
        (pdir / "config.yaml").write_text(
            yaml.safe_dump(profile_config(role), allow_unicode=True, sort_keys=False),
            encoding="utf-8")
        soul = (TEMPLATES / f"{role}.md").read_text(encoding="utf-8").rstrip() + "\n\n" + common
        (pdir / "SOUL.md").write_text(soul, encoding="utf-8")
        print(f"[assign] profile {role}: config + SOUL refreshed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
