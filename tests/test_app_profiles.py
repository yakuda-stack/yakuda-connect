#!/usr/bin/env python3
"""Tests fuer die App-Profile (core/app_profiles.py)."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "core"))

import app_profiles  # noqa: E402
import paths  # noqa: E402


@pytest.fixture
def home(tmp_path, monkeypatch):
    root = tmp_path / "yc"
    (root / "config").mkdir(parents=True)
    monkeypatch.setattr(paths, "config_root", lambda: str(root))
    monkeypatch.setattr(paths, "config_file", lambda name: str(root / "config" / name))
    return root


def _cfg(home):
    return json.loads((home / "config" / "config.json").read_text())


def _write_cfg(home, data):
    (home / "config" / "config.json").write_text(json.dumps(data))


def test_valid_names():
    for ok in ("yakuda", "Freund 1", "VR – Abend"):
        assert app_profiles.valid_name(ok)
    for bad in ("", " x", "x ", ".hidden", "a/b", "a\\b", "x" * 41, None):
        assert not app_profiles.valid_name(bad)


def test_save_skips_global_keys(home):
    _write_cfg(home, {"bitrate": 50, "language": "de", "tour_asked": "x",
                      "foo_seen": True, "autostart_profiles": [1]})
    assert app_profiles.save_profile("a")
    data = json.loads((home / "profiles" / "a.json").read_text())
    assert data["settings"] == {"bitrate": 50}


def test_load_keeps_global_keys_and_sets_active(home):
    _write_cfg(home, {"bitrate": 50, "autostart_apps": ["x"], "language": "de"})
    app_profiles.save_profile("a")
    _write_cfg(home, {"bitrate": 99, "language": "fr", "extra": 1})
    cfg = app_profiles.load_profile("a")
    assert cfg["bitrate"] == 50
    assert cfg["autostart_apps"] == ["x"]
    assert cfg["language"] == "fr"
    assert "extra" not in cfg
    assert _cfg(home)[app_profiles.ACTIVE_KEY] == "a"
    assert app_profiles.active_profile() == "a"


def test_autostart_profiles_global_unless_switch(home):
    _write_cfg(home, {"autostart_profiles": ["A"]})
    app_profiles.save_profile("p")
    _write_cfg(home, {"autostart_profiles": ["B"]})
    assert app_profiles.load_profile("p")["autostart_profiles"] == ["B"]

    _write_cfg(home, {"autostart_profiles": ["A"], app_profiles.AUTOSTART_IN_PROFILE_KEY: True})
    app_profiles.save_profile("q")
    _write_cfg(home, {"autostart_profiles": ["B"], app_profiles.AUTOSTART_IN_PROFILE_KEY: True})
    assert app_profiles.load_profile("q")["autostart_profiles"] == ["A"]


def test_extra_files_follow_profile(home):
    (home / "config" / "theme.json").write_text(json.dumps({"accent": "#111"}))
    _write_cfg(home, {})
    app_profiles.save_profile("a")
    (home / "config" / "theme.json").write_text(json.dumps({"accent": "#999"}))
    (home / "config" / "controls_layout.json").write_text("{}")
    app_profiles.load_profile("a")
    assert json.loads((home / "config" / "theme.json").read_text()) == {"accent": "#111"}
    assert not (home / "config" / "controls_layout.json").exists()


def test_rename_copy_delete(home):
    _write_cfg(home, {"bitrate": 1})
    app_profiles.save_profile("a")
    app_profiles.set_active("a")
    assert app_profiles.rename_profile("a", "b")
    assert app_profiles.active_profile() == "b"
    assert app_profiles.copy_profile("b", "c")
    assert app_profiles.list_profiles() == ["b", "c"]
    assert not app_profiles.copy_profile("b", "c")
    assert app_profiles.delete_profile("b")
    assert app_profiles.active_profile() == ""
    assert app_profiles.list_profiles() == ["c"]


def test_export_import(home, tmp_path):
    _write_cfg(home, {"bitrate": 7})
    app_profiles.save_profile("a")
    dest = tmp_path / "out.json"
    assert app_profiles.export_profile("a", str(dest))
    assert app_profiles.import_name(str(dest)) == "a"
    assert app_profiles.import_profile(str(dest), "b")
    assert json.loads((home / "profiles" / "b.json").read_text())["settings"] == {"bitrate": 7}
    junk = tmp_path / "junk.json"
    junk.write_text("[1, 2]")
    assert app_profiles.import_name(str(junk)) == ""


def test_pending_switch(home):
    _write_cfg(home, {"bitrate": 5})
    app_profiles.save_profile("a")
    _write_cfg(home, {"bitrate": 6})
    assert app_profiles.apply_pending() is None
    app_profiles.request_switch("a")
    cfg = app_profiles.apply_pending()
    assert cfg["bitrate"] == 5
    assert app_profiles.apply_pending() is None


def test_profiles_survive_reset(home):
    import app_reset
    _write_cfg(home, {"bitrate": 5})
    app_profiles.save_profile("a")
    assert app_reset.reset_app()
    assert app_profiles.list_profiles() == ["a"]
