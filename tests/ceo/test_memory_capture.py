"""route_capture markdown-index placement (empty + non-empty sections)."""
import importlib

import pytest

from skills.ceo._lib import memory as m


@pytest.fixture
def mem(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_CEO_MEMORY_ROOT", str(tmp_path))
    importlib.reload(m)  # re-evaluate _DEFAULT_MEMORY_ROOT/env at import time
    p = tmp_path / "memory.md"
    p.write_text(
        "# Memory\n\n## Active Priorities (this week)\n\n## Current Strategic Themes\n",
        encoding="utf-8",
    )
    return p


def test_task_lands_in_active_priorities_when_section_empty(mem):
    m.route_capture("task", "", "купить лекарства")
    text = mem.read_text(encoding="utf-8")
    ap = text.split("## Active Priorities")[1].split("## Current Strategic")[0]
    assert "- [ ] купить лекарства" in ap  # NOT leaked into the next section


def test_insight_lands_in_strategic_themes(mem):
    m.route_capture("insight", "", "рынок в премиум")
    text = mem.read_text(encoding="utf-8")
    themes = text.split("## Current Strategic Themes")[1]
    assert "- рынок в премиум" in themes


def test_task_appends_after_existing_bullet(mem):
    mem.write_text(
        "# Memory\n\n## Active Priorities (this week)\n\n- [ ] старая\n\n"
        "## Current Strategic Themes\n",
        encoding="utf-8",
    )
    m.route_capture("task", "", "новая")
    ap = mem.read_text(encoding="utf-8").split("## Active Priorities")[1].split("## Current")[0]
    assert "- [ ] старая" in ap and "- [ ] новая" in ap
    assert ap.index("старая") < ap.index("новая")  # appended after, order preserved
