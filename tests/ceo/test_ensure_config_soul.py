"""ensure_config appends the cross-cutting SOUL persona rules idempotently.

Focus on the 2026-06-30 'clean messages' rule (no technical/diagnostic noise in
user-facing text) — it must land in an existing SOUL.md and not duplicate on
re-run.
"""
import importlib.util

_SPEC = importlib.util.spec_from_file_location(
    "ensure_config_under_test", "scripts/hooks/ensure_config.py")
ec = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ec)


def test_clean_rule_appended_and_idempotent(monkeypatch, tmp_path):
    soul = tmp_path / "SOUL.md"
    soul.write_text("# Persona\nbase content\n", encoding="utf-8")
    monkeypatch.setattr(ec, "SOUL_PATH", str(soul))

    ec._ensure_soul_rule()
    body = soul.read_text(encoding="utf-8")
    assert ec._SOUL_CLEAN_MARKER in body
    assert "никаких тех-данных" in body  # the human-facing rule title fragment

    # idempotent: a second run must not duplicate the block
    ec._ensure_soul_rule()
    assert soul.read_text(encoding="utf-8").count(ec._SOUL_CLEAN_MARKER) == 1


def test_no_soul_file_is_noop(monkeypatch, tmp_path):
    missing = tmp_path / "nope.md"
    monkeypatch.setattr(ec, "SOUL_PATH", str(missing))
    ec._ensure_soul_rule()  # must not raise / must not create the file
    assert not missing.exists()
