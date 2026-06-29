"""Markdown memory layer for CEO OS skills.

Loader + updater для /memory/*.md файлов согласно V1 блюпринту.

Design contract (from .wiki/decisions.md::memory-folder-in-repo-root):
- /memory/*.md — long-term structured memory (markdown)
- ~/.hermes/state.db — fast lookup / session history (Hermes core, untouched here)
- Read pattern: каждый skill вызывает load_memory([list_of_files]) → dict[name → str]
- Write pattern: append-only для daily_log/weekly_review/decisions;
  safe-edit для projects/risks/areas/goals; manual-only для user/soul.

Privacy: see /memory/soul.md::Privacy guard. This module does NOT enforce
privacy redaction — that is skill-level responsibility (skill prompts must
include redaction rules from soul.md when echoing user input back to memory).
"""

from __future__ import annotations

import datetime as _dt
import os
import pathlib
import re
from typing import Iterable

# Default location: repo root /memory/. Override via env for tests.
_DEFAULT_MEMORY_ROOT = pathlib.Path(__file__).resolve().parents[3] / "memory"


class MemoryError(RuntimeError):
    """Raised on memory layer integrity failures (missing required file, etc.)."""


def memory_root() -> pathlib.Path:
    """Return memory directory path (env-override aware)."""
    env_root = os.environ.get("HERMES_CEO_MEMORY_ROOT")
    if env_root:
        return pathlib.Path(env_root).expanduser().resolve()
    return _DEFAULT_MEMORY_ROOT


# Canonical memory files (блюпринт §04). Order matters for load_all().
KNOWN_FILES: tuple[str, ...] = (
    "user",
    "soul",
    "memory",
    "areas",
    "goals",
    "projects",
    "risks",
    "decisions",
    "daily_log",
    "weekly_review",
)

# Files where write is append-only. Mutating prior content forbidden through this module.
APPEND_ONLY: frozenset[str] = frozenset({"daily_log", "weekly_review", "decisions"})

# Files where write through this module is forbidden (manual edit only).
MANUAL_ONLY: frozenset[str] = frozenset({"user", "soul"})


def _resolve(name: str) -> pathlib.Path:
    if name not in KNOWN_FILES:
        raise MemoryError(f"Unknown memory file: {name!r}. Known: {KNOWN_FILES}")
    return memory_root() / f"{name}.md"


def load_memory(names: Iterable[str]) -> dict[str, str]:
    """Read multiple memory files; missing file → empty string (with explicit marker).

    Returns dict[name → content]. Каллер должен handle missing/empty markers.
    """
    out: dict[str, str] = {}
    for name in names:
        path = _resolve(name)
        if not path.exists():
            out[name] = f"<!-- MISSING: memory/{name}.md not found -->\n"
        else:
            out[name] = path.read_text(encoding="utf-8")
    return out


def load_all() -> dict[str, str]:
    """Load all canonical memory files in defined order."""
    return load_memory(KNOWN_FILES)


def append_entry(name: str, header: str, body: str) -> pathlib.Path:
    """Append a dated entry to an append-only file.

    Header format: '## <header>' — caller decides what header is (e.g. date, slug).
    Returns the file path written.
    """
    if name not in APPEND_ONLY:
        raise MemoryError(
            f"append_entry() rejects {name!r} — only append-only files allowed: {sorted(APPEND_ONLY)}"
        )
    path = _resolve(name)
    if not path.exists():
        raise MemoryError(
            f"Cannot append: {path} does not exist. Initialize template first."
        )
    block = f"\n\n## {header}\n\n{body.rstrip()}\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(block)
    return path


def safe_write(name: str, content: str) -> pathlib.Path:
    """Overwrite a safe-edit file. Forbidden for append-only and manual-only files.

    Caller is responsible for preserving existing structure (this function trusts caller).
    For `memory.md` cleanup → safe_write IS the cleanup mechanism after proposal approval.
    """
    if name in APPEND_ONLY:
        raise MemoryError(f"{name!r} is append-only. Use append_entry().")
    if name in MANUAL_ONLY:
        raise MemoryError(
            f"{name!r} is manual-only. Edit /memory/{name}.md by hand."
        )
    if name not in KNOWN_FILES:
        raise MemoryError(f"Unknown memory file: {name!r}")
    path = _resolve(name)
    path.write_text(content, encoding="utf-8")
    return path


def today_iso() -> str:
    """Today date in YYYY-MM-DD."""
    return _dt.date.today().isoformat()


def extract_section(content: str, header: str) -> str | None:
    """Pull a markdown section by `## header` from content. Returns None if absent.

    Used by skills to grab e.g. 'Active Priorities' from memory.md or
    'Top 3' lists from briefing artefacts.
    """
    pattern = re.compile(
        rf"^##\s+{re.escape(header)}\s*\n(.*?)(?=\n##\s|\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(content)
    if not m:
        return None
    return m.group(1).strip()


def last_entries(name: str, limit: int = 3) -> list[str]:
    """Return last `limit` `## YYYY-MM-DD` entries from a log-style file.

    Works on daily_log.md / weekly_review.md / decisions.md.
    Each returned string is the entry body (without the `## header` line).
    """
    if name not in {"daily_log", "weekly_review", "decisions"}:
        raise MemoryError(
            f"last_entries() expects log-style file. Got: {name!r}"
        )
    path = _resolve(name)
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"^##\s+", text, flags=re.MULTILINE)
    entries = [b for b in blocks[1:] if b.strip()]
    return entries[-limit:]


def projects_by_priority(priority: str = "high") -> list[dict[str, str]]:
    """Parse projects.md and return blocks with matching Priority field.

    Returns list of dicts with at least: name, owner, goal, status, priority,
    deadline, next_actions (joined string).

    Heuristic parser — projects.md uses '## <Project Name>' headers + key:value lines.
    """
    path = _resolve("projects")
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    out: list[dict[str, str]] = []
    blocks = re.split(r"^##\s+", text, flags=re.MULTILINE)
    for block in blocks[1:]:
        lines = block.splitlines()
        if not lines:
            continue
        name = lines[0].strip()
        # Skip the "Archived" section bucket
        if name.lower().startswith("archived"):
            continue
        proj: dict[str, str] = {"name": name}
        for line in lines[1:]:
            stripped = line.strip()
            if not stripped:
                continue
            if ":" in stripped and not stripped.startswith("-"):
                key, _, val = stripped.partition(":")
                proj[key.strip().lower().replace(" ", "_")] = val.strip()
        if _normalize_rank_token(proj.get("priority", "")) == priority.lower():
            out.append(proj)
    return out


def assert_memory_present(required: Iterable[str] | None = None) -> None:
    """Raise MemoryError if any required memory file is missing.

    Default: all KNOWN_FILES. Pass narrower list to relax for specific skills.
    """
    required = list(required) if required is not None else list(KNOWN_FILES)
    missing = [n for n in required if not _resolve(n).exists()]
    if missing:
        raise MemoryError(
            f"Missing required memory files: {missing}. "
            f"Run Stage 2 (folder structure) first."
        )


# ── Extended helpers added in Stage 5/5b/5c ──────────────────────────────


_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "": 0}
_PROBABILITY_RANK = {"high": 3, "medium": 2, "low": 1, "": 0}


def _normalize_rank_token(raw: str) -> str:
    """Strip inline notes from rank-like fields ('medium (high после gate)' → 'medium').

    Takes the first word, lowercased, stripped of common punctuation. Empty
    input → ''.
    """
    raw = (raw or "").strip().lower()
    if not raw:
        return ""
    head = re.split(r"[\s(,\-/;]+", raw, maxsplit=1)[0]
    return head.strip()


def all_projects() -> list[dict[str, str]]:
    """Parse projects.md into a list of dicts regardless of priority.

    Skips the trailing 'Archived' bucket. Each dict has at least:
    name, owner, goal, status, priority, deadline, last_update, next_review.
    """
    path = _resolve("projects")
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    out: list[dict[str, str]] = []
    blocks = re.split(r"^##\s+", text, flags=re.MULTILINE)
    for block in blocks[1:]:
        lines = block.splitlines()
        if not lines:
            continue
        name = lines[0].strip()
        if name.lower().startswith("archived"):
            continue
        proj: dict[str, str] = {"name": name}
        next_actions: list[str] = []
        in_next_actions = False
        for line in lines[1:]:
            stripped = line.strip()
            if not stripped:
                in_next_actions = False
                continue
            if stripped.lower().startswith("next actions:"):
                in_next_actions = True
                continue
            if in_next_actions and stripped.startswith("-"):
                next_actions.append(stripped.lstrip("- ").rstrip())
                continue
            if ":" in stripped and not stripped.startswith("-"):
                in_next_actions = False
                key, _, val = stripped.partition(":")
                proj[key.strip().lower().replace(" ", "_")] = val.strip()
        if next_actions:
            proj["next_actions_list"] = "\n".join(next_actions)
        out.append(proj)
    return out


def all_risks() -> list[dict[str, str]]:
    """Parse risks.md into list of dicts. Each block is '### <title>' under a category header.

    Returns dicts with: title, category, severity, probability, status, trigger,
    mitigation, owner, last_reviewed, linked_projects.
    """
    path = _resolve("risks")
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    out: list[dict[str, str]] = []
    # Split by '### ' (each risk is a sub-header under '## <Category>')
    blocks = re.split(r"^###\s+", text, flags=re.MULTILINE)
    for block in blocks[1:]:
        lines = block.splitlines()
        if not lines:
            continue
        title = lines[0].strip()
        # Skip placeholder titles like '<Specific cashflow risk>'
        if title.startswith("<") and title.endswith(">"):
            continue
        risk: dict[str, str] = {"title": title}
        for line in lines[1:]:
            stripped = line.strip()
            if not stripped:
                continue
            if ":" in stripped and not stripped.startswith("-"):
                key, _, val = stripped.partition(":")
                key_norm = key.strip().lower().replace(" ", "_")
                risk[key_norm] = val.strip()
        out.append(risk)
    return out


def risks_by_severity(min_severity: str = "medium") -> list[dict[str, str]]:
    """Return risks ranked by severity*probability, filtered by min_severity floor.

    Tolerates inline notes after the rank token (e.g. 'medium (renovations)'
    is treated as 'medium' via _normalize_rank_token).
    """
    floor = _SEVERITY_RANK.get(min_severity.lower(), 0)
    items = []
    for r in all_risks():
        sev_rank = _SEVERITY_RANK.get(_normalize_rank_token(r.get("severity", "")), 0)
        if sev_rank < floor:
            continue
        prob_rank = _PROBABILITY_RANK.get(_normalize_rank_token(r.get("probability", "")), 0)
        items.append((sev_rank * prob_rank, sev_rank, prob_rank, r))
    items.sort(key=lambda t: (-t[0], -t[1], -t[2]))
    return [r for _, _, _, r in items]


def update_project_field(project_name: str, field: str, value: str) -> bool:
    """Safe-edit a single field on a project in projects.md.

    Returns True if the project block was found and updated, False otherwise.
    Field matching is case-insensitive on the raw label ('Status', 'Last Update', etc.).
    """
    path = _resolve("projects")
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    # Match the project header and capture everything up to the next ## or EOF.
    header_re = re.compile(
        rf"(^##\s+{re.escape(project_name)}\s*\n)(.*?)(?=^##\s|\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    m = header_re.search(text)
    if not m:
        return False
    body = m.group(2)
    # Look for the field within the body.
    field_re = re.compile(
        rf"^({re.escape(field)})\s*:\s*.*$",
        flags=re.MULTILINE | re.IGNORECASE,
    )
    new_body, n = field_re.subn(rf"\1: {value}", body, count=1)
    if n == 0:
        # Field absent — append it at the end of the block.
        new_body = body.rstrip() + f"\n{field}: {value}\n"
    new_text = text[: m.start(2)] + new_body + text[m.end(2) :]
    path.write_text(new_text, encoding="utf-8")
    return True


def today_hhmm() -> str:
    """Return current local HH:MM."""
    return _dt.datetime.now().strftime("%H:%M")


def iso_week() -> str:
    """Return ISO week label YYYY-Www (e.g. 2026-W20)."""
    today = _dt.date.today()
    year, week, _ = today.isocalendar()
    return f"{year}-W{week:02d}"


_CAPTURE_TYPES = {"meeting", "decision", "insight", "recap", "task"}


def route_capture(memo_type: str, context: str, content: str) -> dict[str, str]:
    """Route a voice memo / capture to the right memory file by type.

    Returns dict {file, action, snippet} describing what was written.

    Routing:
      meeting / recap → memory/daily_log.md (append today's entry)
      decision        → memory/decisions.md (append entry with shape)
      insight         → memory/memory.md::Current Strategic Themes (in-place append)
      task            → memory/memory.md::Active Priorities (in-place append as bullet)
    """
    memo_type = (memo_type or "").lower().strip()
    if memo_type not in _CAPTURE_TYPES:
        raise MemoryError(
            f"Unknown capture type {memo_type!r}. Expected one of {sorted(_CAPTURE_TYPES)}"
        )
    context = (context or "").strip()
    content = (content or "").strip()

    if memo_type in {"meeting", "recap"}:
        snippet = f"### Capture ({today_hhmm()}) — {memo_type}"
        body = f"**Context:** {context or '(none)'}\n\n{content}"
        append_entry("daily_log", today_iso(), f"{snippet}\n{body}")
        return {"file": "memory/daily_log.md", "action": "appended", "snippet": snippet}

    if memo_type == "decision":
        slug_words = context.lower().split()[:3] or content.lower().split()[:3] or ["decision"]
        slug = "-".join(re.sub(r"[^a-z0-9-]", "", w) for w in slug_words) or "decision"
        header = f"{today_iso()} — {slug}"
        body = (
            f"Date: {today_iso()}\n"
            f"Decision: {content}\n"
            f"Reason: (captured via /capture — fill in context: {context or 'n/a'})\n"
            f"Expected Result: (to fill)\n"
            f"Review Date: (to fill)\n"
            f"Status: pending"
        )
        append_entry("decisions", header, body)
        return {"file": "memory/decisions.md", "action": "appended", "snippet": header}

    # insight or task — touch memory.md (safe-edit, in-place section append)
    path = _resolve("memory")
    text = path.read_text(encoding="utf-8")
    if memo_type == "task":
        header = "Active Priorities (this week)"
        bullet = f"- [ ] {content}" + (f" — {context}" if context else "")
    else:  # insight
        header = "Current Strategic Themes"
        bullet = f"- {content}" + (f" — {context}" if context else "")
    # Capture ONLY the header line (trailing spaces/tabs, not blank lines) so an
    # empty section doesn't let `\s*` swallow the blank line and push the bullet
    # into the NEXT section. Body starts right after the header newline.
    pattern = re.compile(
        rf"^(##\s+{re.escape(header)}[ \t]*\n)(.*?)(?=\n##\s|\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        # Section missing — append at end.
        text = text.rstrip() + f"\n\n## {header}\n\n{bullet}\n"
    else:
        section_head = m.group(1)
        section_body = m.group(2).rstrip()
        # Insert bullet BEFORE any trailing `---` thematic break in the section
        # body, so the new item stays inside the section visually.
        body_lines = section_body.splitlines()
        insert_at = len(body_lines)
        for i in range(len(body_lines) - 1, -1, -1):
            stripped = body_lines[i].strip()
            if not stripped:
                continue
            if stripped == "---":
                insert_at = i
                continue
            break
        body_lines.insert(insert_at, bullet)
        new_body = "\n".join(body_lines)
        text = (
            text[: m.start()]
            + section_head
            + new_body
            + "\n"
            + text[m.end() :]
        )
    path.write_text(text, encoding="utf-8")
    return {"file": "memory/memory.md", "action": f"appended to {header}", "snippet": bullet}
