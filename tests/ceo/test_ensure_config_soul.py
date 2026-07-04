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


def test_language_rule_appended_and_idempotent(monkeypatch, tmp_path):
    """The always-Russian rule (2026-07-02 Ukrainian-drift fix) must land and
    explicitly forbid Ukrainian, including in autonomous/cron mode."""
    soul = tmp_path / "SOUL.md"
    soul.write_text("# Persona\nbase content\n", encoding="utf-8")
    monkeypatch.setattr(ec, "SOUL_PATH", str(soul))

    ec._ensure_soul_rule()
    body = soul.read_text(encoding="utf-8")
    assert ec._SOUL_LANG_MARKER in body
    assert "украинский" in body.lower()  # the failure mode it forbids
    assert "cron" in body.lower()        # covers the autonomous path

    ec._ensure_soul_rule()
    assert soul.read_text(encoding="utf-8").count(ec._SOUL_LANG_MARKER) == 1


def test_needs_dated_id_guards_bare_anthropic_alias():
    assert ec._needs_dated_id("claude-sonnet-4-6", "anthropic") is True
    assert ec._needs_dated_id("claude-opus-4-8", "anthropic") is True
    assert ec._needs_dated_id("claude-sonnet-4-5-20250929", "anthropic") is False
    # non-Anthropic providers use their own aliases — never rewritten
    assert ec._needs_dated_id("claude-sonnet-4-6", "openrouter") is False
    assert ec._needs_dated_id("google/gemini-2.5-pro", "openrouter") is False


def test_first_boot_seeds_soul_then_appends_rules(monkeypatch, tmp_path):
    """On a fresh volume SOUL.md does not exist yet; the hook must seed it from
    the in-image docker/SOUL.md and then append all CEO rules on the FIRST boot
    (previously the rules only landed on the second boot)."""
    soul = tmp_path / "SOUL.md"
    seed = tmp_path / "seed.md"
    seed.write_text("# Base persona\n", encoding="utf-8")
    monkeypatch.setattr(ec, "SOUL_PATH", str(soul))
    monkeypatch.setattr(ec, "_SOUL_SEED_PATH", str(seed))

    ec._ensure_soul_rule()
    body = soul.read_text(encoding="utf-8")
    assert "# Base persona" in body          # seeded from docker/SOUL.md
    assert ec._SOUL_LANG_MARKER in body       # rules appended same boot
    assert ec._SOUL_CLEAN_MARKER in body


def test_no_soul_and_no_seed_is_noop(monkeypatch, tmp_path):
    missing = tmp_path / "nope.md"
    monkeypatch.setattr(ec, "SOUL_PATH", str(missing))
    monkeypatch.setattr(ec, "_SOUL_SEED_PATH", str(tmp_path / "no-seed.md"))
    ec._ensure_soul_rule()  # no target, no seed → must not raise / not create
    assert not missing.exists()
