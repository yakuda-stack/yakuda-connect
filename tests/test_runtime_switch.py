#!/usr/bin/env python3
"""
tests/test_runtime_switch.py — Umschaltung der aktiven OpenXR-Runtime
====================================================================
Der Kern dieser Tests ist eine einzige Regel:

    In ``active_runtime.json`` gehoert der Pfad einer BIBLIOTHEK (.so),
    niemals der eines weiteren Manifests (.json).

Genau daran hing der Fehler, den der "Steam-Fix" der App eigentlich behebt:
Steams pressure-vessel laesst ``capsule-capture-libs`` ueber den Eintrag
laufen und bricht bei einer .json mit "invalid `Elf' handle" ab. Die
Umschaltung auf SteamVR trug jahrelang selbst eine .json ein — die
Statusanzeige meldete den Zustand danach folgerichtig als "defekt".

Ausgefuehrt mit:  python3 -m pytest tests/test_runtime_switch.py
"""
import importlib
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

ELF64 = b"\x7fELF\x02" + b"\x00" * 16
ELF32 = b"\x7fELF\x01" + b"\x00" * 16


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Frisches HOME; die Module leiten ihre Pfade beim Import daraus ab."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))

    import paths
    import vr_environment
    import openxr_manager
    for mod in (paths, vr_environment, openxr_manager):
        importlib.reload(mod)

    return {"home": home, "venv": vr_environment, "oxr": openxr_manager}


def _install_steamvr(home, lib_bytes=ELF64, library_path="./bin/linux64/steamxr_linux64.so"):
    """Legt eine SteamVR-Installation an, wie Steam sie ausliefert."""
    base = home / ".local/share/Steam/steamapps/common/SteamVR"
    (base / "bin/linux64").mkdir(parents=True)
    (base / "bin/linux64/steamxr_linux64.so").write_bytes(lib_bytes)
    (base / "steamxr_linux64.json").write_text(json.dumps({
        "file_format_version": "1.0.0",
        "runtime": {"name": "SteamVR", "library_path": library_path},
    }))
    return base


def _active_runtime(home):
    path = home / ".config/openxr/1/active_runtime.json"
    return json.loads(path.read_text())


# --------------------------------------------------------------------------- #
#  Manifest -> Bibliothek aufloesen
# --------------------------------------------------------------------------- #
def test_steamvr_lib_is_resolved_from_manifest(env):
    base = _install_steamvr(env["home"])
    lib = env["venv"].find_steamvr_lib()
    assert lib == str(base / "bin/linux64/steamxr_linux64.so")


def test_steamvr_lib_empty_without_steamvr(env):
    assert env["venv"].find_steamvr_lib() == ""


def test_manifest_pointing_at_json_is_rejected(env):
    """Ein library_path, der auf ein Manifest zeigt, darf nicht durchgehen."""
    _install_steamvr(env["home"], library_path="./steamxr_linux64.json")
    lib, _mon = env["venv"].resolve_manifest_libs(
        env["venv"].find_steamvr_manifest())
    assert lib is None
    # Der Fallback findet trotzdem die echte .so daneben
    assert env["venv"].find_steamvr_lib().endswith(".so")


def test_32bit_library_is_rejected(env):
    _install_steamvr(env["home"], lib_bytes=ELF32)
    assert env["venv"].find_steamvr_lib() == ""


# --------------------------------------------------------------------------- #
#  Umschalten auf SteamVR
# --------------------------------------------------------------------------- #
def test_switch_writes_library_not_manifest(env):
    oxr, home = env["oxr"], env["home"]
    _install_steamvr(home)

    ok, code, _detail = oxr.apply_steamvr_runtime()
    assert (ok, code) == (True, "ok")

    lib = _active_runtime(home)["runtime"]["library_path"]
    assert lib.endswith(".so")
    assert not lib.endswith(".json")
    assert pathlib.Path(lib).is_absolute()


def test_status_is_ok_after_switching_to_steamvr(env):
    """
    Vorher meldete die Statusanzeige "defekt", direkt nachdem der Nutzer
    selbst auf SteamVR umgestellt hatte — weil dort eine .json stand.
    """
    oxr = env["oxr"]
    _install_steamvr(env["home"])
    oxr.apply_steamvr_runtime()

    state, _detail = oxr.current_status()
    assert state == "ok"
    assert oxr.active_runtime_name() == "steamvr"


def test_switch_without_steamvr_reports_missing(env):
    oxr = env["oxr"]
    ok, code, detail = oxr.apply_steamvr_runtime()
    assert ok is False
    assert code == "steamvr_not_found"
    assert detail.endswith("steamxr_linux64.json")
    assert not (env["home"] / ".config/openxr/1/active_runtime.json").exists()


def test_previous_runtime_is_backed_up(env):
    oxr, home = env["oxr"], env["home"]
    _install_steamvr(home)
    target = home / ".config/openxr/1/active_runtime.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"runtime": {"library_path": "/usr/lib/wivrn/libopenxr_wivrn.so"}}')

    ok, _code, backup = oxr.apply_steamvr_runtime()
    assert ok is True
    assert backup and pathlib.Path(backup).exists()
    assert "wivrn" in pathlib.Path(backup).read_text()


# --------------------------------------------------------------------------- #
#  Erkennung der aktiven Runtime (Grundlage der Steam-Fix-Rueckfrage)
# --------------------------------------------------------------------------- #
def test_active_runtime_name_none_without_file(env):
    assert env["oxr"].active_runtime_name() == "none"


def test_active_runtime_name_detects_wivrn(env):
    home = env["home"]
    target = home / ".config/openxr/1/active_runtime.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"runtime": {"library_path": "/usr/lib/wivrn/libopenxr_wivrn.so"}}')
    assert env["oxr"].active_runtime_name() == "wivrn"


def test_active_runtime_name_detects_steamvr(env):
    _install_steamvr(env["home"])
    env["oxr"].apply_steamvr_runtime()
    assert env["oxr"].active_runtime_name() == "steamvr"
