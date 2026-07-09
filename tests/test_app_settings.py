"""Behavior of the JSON-backed application settings store.

Settings live outside the database so they survive DB restores and can never
block startup. These tests confirm defaults, round-trip persistence, key
filtering, and graceful recovery from a corrupt file — all against a temporary
data directory so the real user settings are never touched.
"""
import json

import pytest

from app import app_settings, paths


@pytest.fixture(autouse=True)
def temp_data_dir(tmp_path, monkeypatch):
    """Point paths.data_dir at a temp directory for every test in this module."""
    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
    return tmp_path


def test_defaults_when_no_file(temp_data_dir):
    loaded = app_settings.load_settings()
    assert loaded == app_settings.DEFAULTS
    # A fresh dict, not a shared reference to DEFAULTS.
    assert loaded is not app_settings.DEFAULTS


def test_save_and_load_roundtrip(temp_data_dir):
    app_settings.save_settings({"auto_check_updates": False, "skipped_version": "4.4.0"})
    loaded = app_settings.load_settings()
    assert loaded["auto_check_updates"] is False
    assert loaded["skipped_version"] == "4.4.0"
    # Untouched keys keep their defaults.
    assert loaded["notify_updates"] is True


def test_unknown_keys_are_ignored(temp_data_dir):
    merged = app_settings.save_settings({"bogus_key": 123, "notify_updates": False})
    assert "bogus_key" not in merged
    assert merged["notify_updates"] is False


def test_corrupt_file_falls_back_to_defaults(temp_data_dir):
    app_settings.settings_path().write_text("{not valid json", encoding="utf-8")
    assert app_settings.load_settings() == app_settings.DEFAULTS


def test_non_object_json_falls_back_to_defaults(temp_data_dir):
    app_settings.settings_path().write_text("[1, 2, 3]", encoding="utf-8")
    assert app_settings.load_settings() == app_settings.DEFAULTS


def test_write_is_atomic_and_leaves_no_temp_files(temp_data_dir):
    app_settings.save_settings({"auto_check_updates": False})
    leftovers = list(temp_data_dir.glob("*.tmp"))
    assert leftovers == []
    on_disk = json.loads(app_settings.settings_path().read_text(encoding="utf-8"))
    assert on_disk["auto_check_updates"] is False
