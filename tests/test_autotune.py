#!/usr/bin/env python3
"""
tests/test_autotune.py — Einmal-Automatik (core/vr_autotune.py)
==============================================================
Geprueft wird das, was im Fehlerfall wehtut:

  * Auf einem frischen System darf NICHTS umgestellt werden.
  * Umgestellt wird genau EINMAL — danach nie wieder, auch wenn der Nutzer
    hinterher von Hand etwas anderes waehlt.
  * Eine bewusst abgeschaltete Kompatibilitaet ("Deaktiviert") wird nicht
    ueberfahren.
  * Waehrend der WiVRn-Server laeuft, wird an seiner config.json nicht
    gedreht (er liest den Pfad nur beim Start).
  * Das Gedaechtnis fuer die Runtime-Umschaltung SteamVR <-> WiVRn.

Alles laeuft in einem temporaeren HOME; das echte System wird nie angefasst.
Ausgefuehrt mit:  python3 -m pytest tests/test_autotune.py
"""
import importlib
import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))


@pytest.fixture
def env(tmp_path, monkeypatch):
    """
    Frisches HOME + neu geladene Module.

    Noetig, weil paths.py und vr_environment.py ihre Pfade beim IMPORT aus
    HOME ableiten. Ohne Neuladen wuerden die Tests gegen das echte HOME
    laufen — genau das, was hier niemals passieren darf.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))

    import paths
    import vr_environment
    import backup_manager
    import vr_autotune
    for mod in (paths, vr_environment, backup_manager, vr_autotune):
        importlib.reload(mod)

    # Backups im Test nicht wirklich anlegen (kopiert sonst Systemordner).
    monkeypatch.setattr(vr_autotune.backup, "auto_backup_on_start", lambda: False)
    monkeypatch.setattr(vr_autotune.backup, "has_backup_flag", lambda: True)
    monkeypatch.setattr(vr_autotune.backup, "create_vr_backup", lambda: True)
    # Kein pgrep im Test.
    monkeypatch.setattr(vr_autotune, "server_is_running", lambda: False)

    return {"home": home, "autotune": vr_autotune, "venv": vr_environment}


def _make_vr_history(home):
    """Legt die Ordner an, die beweisen, dass schon einmal VR lief."""
    for sub in (".config/openvr", ".config/openxr", ".config/wivrn",
                ".local/share/openxr/1"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    manifest = home / ".local/share/openxr/1/openxr_wivrn.json"
    manifest.write_text(json.dumps({"runtime": {"library_path": "libopenxr_wivrn.so"}}))


def _make_xrizer(home):
    """Vollstaendige xrizer-Installation an einem Ort, den venv absucht."""
    d = home / ".local/share/xrizer/bin/linux64"
    d.mkdir(parents=True, exist_ok=True)
    (d / "vrclient.so").write_bytes(b"\x7fELF\x02")
    return str(home / ".local/share/xrizer")


def _wivrn_config(home):
    path = home / ".config/wivrn/config.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


# --------------------------------------------------------------------------- #
#  Frisches System: Finger weg
# --------------------------------------------------------------------------- #
def test_fresh_system_changes_nothing(env):
    at = env["autotune"]
    result = at.run_auto_setup()
    assert result["switched"] is False
    assert result["skipped"].startswith("missing:")
    assert at.xrizer_done() is False


def test_missing_openxr_share_dir_blocks_everything(env):
    """
    Der System-Ordner 'openxr' (im Backup: usr/openxr) gehoert zu den
    Pflichtpfaden — ohne ihn gibt es keine System-Installation, die man
    sichern oder umstellen koennte.
    """
    at = env["autotune"]
    home = env["home"]
    for sub in (".config/openvr", ".config/openxr", ".config/wivrn"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    _make_xrizer(home)

    result = at.run_auto_setup()
    assert result["switched"] is False
    assert result["skipped"].startswith("missing:")
    assert at.xrizer_done() is False


def test_required_paths_cover_all_backup_sources(env):
    """Die Pflichtliste muss dieselben Orte nennen, die das Backup sichert."""
    at = env["autotune"]
    _make_vr_history(env["home"])
    required = at.required_paths()
    assert str(env["home"] / ".config/openvr") in required
    assert str(env["home"] / ".config/openxr") in required
    assert str(env["home"] / ".config/wivrn") in required
    assert at.openxr_share_dir() in required
    assert at.openxr_share_dir().endswith("openxr")
    assert at.missing_paths() == []


def test_no_xrizer_installed_is_not_marked_done(env):
    """xrizer kann spaeter nachinstalliert werden — dann soll es noch greifen."""
    at = env["autotune"]
    _make_vr_history(env["home"])
    result = at.run_auto_setup()
    assert result["switched"] is False
    assert result["skipped"] == "no_xrizer"
    assert at.xrizer_done() is False


# --------------------------------------------------------------------------- #
#  Der Normalfall
# --------------------------------------------------------------------------- #
def test_switches_to_xrizer_once(env):
    at, venv = env["autotune"], env["venv"]
    _make_vr_history(env["home"])
    target = _make_xrizer(env["home"])

    result = at.run_auto_setup()
    assert result["switched"] is True
    assert result["path"] == target
    assert _wivrn_config(env["home"])["openvr-compat-path"] == target
    assert venv.current_openvr_compat() == (venv.OPENVR_PATH, target)
    assert at.xrizer_done() is True


def test_second_run_does_nothing_even_after_manual_change(env):
    """Nach der einmaligen Umstellung darf die App nie wieder hineinregieren."""
    at, venv = env["autotune"], env["venv"]
    _make_vr_history(env["home"])
    _make_xrizer(env["home"])
    at.run_auto_setup()

    # Nutzer stellt hinterher von Hand auf Standard zurueck
    venv.set_openvr_compat(venv.OPENVR_DEFAULT)
    result = at.run_auto_setup()

    assert result["switched"] is False
    assert result["skipped"] == "already_done"
    assert venv.current_openvr_compat()[0] == venv.OPENVR_DEFAULT


def test_disabled_is_not_overridden(env):
    """'Deaktiviert' ist eine bewusste Entscheidung (z. B. wegen SteamVR)."""
    at, venv = env["autotune"], env["venv"]
    _make_vr_history(env["home"])
    _make_xrizer(env["home"])
    venv.set_openvr_compat(venv.OPENVR_DISABLED)

    result = at.run_auto_setup()
    assert result["switched"] is False
    assert result["skipped"] == "disabled_by_user"
    assert venv.current_openvr_compat()[0] == venv.OPENVR_DISABLED
    assert at.xrizer_done() is False      # nicht abhaken — spaeter erneut pruefen


def test_running_server_is_left_alone(env, monkeypatch):
    at, venv = env["autotune"], env["venv"]
    _make_vr_history(env["home"])
    _make_xrizer(env["home"])
    monkeypatch.setattr(at, "server_is_running", lambda: True)

    result = at.run_auto_setup()
    assert result["skipped"] == "server_running"
    assert venv.current_openvr_compat()[0] == venv.OPENVR_DEFAULT
    assert at.xrizer_done() is False


def test_already_xrizer_marks_done_without_message(env):
    at, venv = env["autotune"], env["venv"]
    _make_vr_history(env["home"])
    target = _make_xrizer(env["home"])
    venv.set_openvr_compat(venv.OPENVR_PATH, target)

    result = at.run_auto_setup()
    assert result["switched"] is False          # keine Meldung
    assert result["skipped"] == "already_xrizer"
    assert at.xrizer_done() is True


# --------------------------------------------------------------------------- #
#  Gedaechtnis fuer SteamVR <-> WiVRn
# --------------------------------------------------------------------------- #
def test_remember_and_restore_previous_compat(env):
    at, venv = env["autotune"], env["venv"]
    target = _make_xrizer(env["home"])
    venv.set_openvr_compat(venv.OPENVR_PATH, target)

    assert at.remember_compat() is True
    venv.set_openvr_compat(venv.OPENVR_DISABLED)
    assert at.previous_compat() == (venv.OPENVR_PATH, target)

    mode, path = at.previous_compat()
    venv.set_openvr_compat(mode, path)
    at.forget_compat()
    assert at.previous_compat() is None
    assert venv.current_openvr_compat() == (venv.OPENVR_PATH, target)


def test_disabled_state_is_not_remembered(env):
    """Sonst waere die Frage beim Zurueckschalten 'Deaktiviert wiederherstellen?'."""
    at, venv = env["autotune"], env["venv"]
    venv.set_openvr_compat(venv.OPENVR_DISABLED)
    assert at.remember_compat() is False
    assert at.previous_compat() is None


def test_default_state_is_remembered(env):
    at, venv = env["autotune"], env["venv"]
    venv.set_openvr_compat(venv.OPENVR_DEFAULT)
    assert at.remember_compat() is True
    assert at.previous_compat() == (venv.OPENVR_DEFAULT, "")


def test_compat_label_is_readable(env):
    at, venv = env["autotune"], env["venv"]
    assert "xrizer" in at.compat_label(venv.OPENVR_PATH, "/opt/xrizer")
    assert at.compat_label(venv.OPENVR_DEFAULT) == "Default"
    assert at.compat_label(venv.OPENVR_DISABLED) == "Disabled"


def test_app_config_keys_survive(env):
    """Der Merker darf fremde Schluessel in der App-Config nicht wegwerfen."""
    at = env["autotune"]
    os.makedirs(os.path.dirname(at.APP_CONFIG_FILE), exist_ok=True)
    with open(at.APP_CONFIG_FILE, "w") as f:
        json.dump({"language": "de", "autostart_apps": ["x"]}, f)

    at.mark_xrizer_done("/opt/xrizer")
    with open(at.APP_CONFIG_FILE) as f:
        data = json.load(f)
    assert data["language"] == "de"
    assert data["autostart_apps"] == ["x"]
    assert data[at.KEY_XRIZER_DONE]
