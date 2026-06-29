"""CEO Telegram menu Работа⇄Личное toggle: label routing + per-chat mode store."""
import pytest

from gateway.platforms.telegram import TelegramAdapter as T


def test_label_resolves_across_both_modes():
    assert T._menu_label_to_command("🎙 Заметка") == "/capture"
    assert T._menu_label_to_command("📋 Встреча") == "/notes"      # work-only tile
    assert T._menu_label_to_command("🎂 ДР") == "/birthday"        # personal-only tile
    assert T._menu_label_to_command("🛠 Настройка") == "/tune"     # shared tile
    assert T._menu_label_to_command("несуществует") is None


def test_toggle_tiles_map_to_mode_sentinels():
    assert T._menu_label_to_command("👤 Личное →") == "__mode:personal"
    assert T._menu_label_to_command("💼 Работа →") == "__mode:work"


def test_mode_store_default_and_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    a = T.__new__(T)  # skip heavy __init__; mode helpers are self-contained
    assert a._get_menu_mode(12345) == "work"  # default
    a._set_menu_mode(12345, "personal")
    assert a._get_menu_mode(12345) == "personal"
    a._set_menu_mode(12345, "work")
    assert a._get_menu_mode(12345) == "work"


def test_mode_store_persists_across_instances(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    T.__new__(T)._set_menu_mode(999, "personal")
    assert T.__new__(T)._get_menu_mode(999) == "personal"  # read back from disk


def test_mode_store_unknown_value_normalized_to_work(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    a = T.__new__(T)
    a._set_menu_mode(1, "garbage")
    assert a._get_menu_mode(1) == "work"


def test_both_layouts_have_toggle_first_and_no_dead_tiles():
    for layout, expected_toggle in (
        (T._CEO_MENU_WORK, "__mode:personal"),
        (T._CEO_MENU_PERSONAL, "__mode:work"),
    ):
        assert layout[0][0][1] == expected_toggle  # top row is the toggle
        for row in layout[1:]:
            for _lbl, cmd in row:
                assert cmd.startswith("/")  # every non-toggle tile is a real command
