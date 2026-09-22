#!/usr/bin/env python3
"""
tests/test_tool_launcher.py — "▶ Starten" auf den Tool-Karten
=============================================================
Jede Karte im Tools-Tab kann ihr Programm starten. Zwei Stolpersteine:

1. Der PATH der Desktop-Sitzung enthaelt ``~/.local/bin`` (AppImage) und
   ``~/.cargo/bin`` (Cargo) nicht zuverlaessig — ein blosses Popen(["wayvr"])
   scheitert dann, obwohl das Programm installiert ist.
2. Kommandozeilenprogramme (obah, XR HOTAS, adb) brauchen ein Terminal,
   sonst passiert sichtbar nichts.
"""
import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tool_launcher as tl  # noqa: E402


def _exe(path):
    path.write_text("#!/bin/sh\ntrue\n")
    path.chmod(0o755)
    return str(path)


def test_finds_local_bin_and_cargo_bin_before_path(tmp_path, monkeypatch):
    local = tmp_path / "local"
    cargo = tmp_path / "cargo"
    local.mkdir()
    cargo.mkdir()
    _exe(local / "wayvr")
    _exe(cargo / "obah")
    monkeypatch.setattr(tl, "EXTRA_BIN_DIRS", (str(local), str(cargo)))
    assert tl.resolve_binary("wayvr") == str(local / "wayvr")
    assert tl.resolve_binary("obah") == str(cargo / "obah")
    assert tl.resolve_binary("gibtesnicht-xyz") is None


def test_launch_args_only_for_the_appimage(tmp_path, monkeypatch):
    """
    launch_args gehoeren laut programs.py der AppImage. Einer AUR-Fassung
    dieselben Schalter unterzuschieben, kann sie zum Abbruch bringen.
    """
    local = tmp_path / "bin"
    local.mkdir()
    _exe(local / "vrcx")
    monkeypatch.setattr(tl, "EXTRA_BIN_DIRS", (str(local),))
    tool = {"key": "vrcx", "start_cmd": "vrcx", "launch_args": "--no-install --no-desktop"}
    assert tl.build_command(tool, {"appimage_installed": True}) == [
        str(local / "vrcx"), "--no-install", "--no-desktop"]
    assert tl.build_command(tool, {"pm_installed": True}) == [str(local / "vrcx")]


def test_flatpak_is_the_fallback_when_no_binary_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "EXTRA_BIN_DIRS", (str(tmp_path),))
    monkeypatch.setattr(tl.shutil, "which", lambda _c: None)
    tool = {"key": "protonplus", "start_cmd": "protonplus",
            "flatpak_id": "com.vysp3r.ProtonPlus"}
    assert tl.build_command(tool, {"flatpak_installed": True}) == [
        "flatpak", "run", "com.vysp3r.ProtonPlus"]
    assert tl.build_command(tool, {}) is None


def test_terminal_line_quotes_the_command_and_waits(tmp_path):
    line = tl.terminal_wrapper(["/opt/my tools/obah", "--x"], "Fehlercode", "Enter ... ")
    assert "'/opt/my tools/obah' --x" in line        # Leerzeichen im Pfad
    assert line.rstrip().endswith('_')               # read am Ende: Fenster bleibt
    assert "Fehlercode" in line


def test_terminal_tools_are_marked_in_tools_json():
    """obah (TUI), XR HOTAS und adb schreiben auf die Konsole."""
    data = json.loads((ROOT / "config" / "tools.json").read_text(encoding="utf-8"))
    flagged = {t["key"] for sec in ("apps", "osc") for t in data[sec] if t.get("terminal")}
    assert {"obah", "xr-hotas", "android-tools"} <= flagged
    for sec in ("apps", "osc"):
        for tool in data[sec]:
            assert tl.wants_terminal(tool) is bool(tool.get("terminal"))


def test_start_without_terminal_program_says_so(tmp_path, monkeypatch):
    local = tmp_path / "bin"
    local.mkdir()
    _exe(local / "obah")
    monkeypatch.setattr(tl, "EXTRA_BIN_DIRS", (str(local),))
    tool = {"key": "obah", "start_cmd": "obah", "terminal": True}
    with pytest.raises(RuntimeError):
        tl.start(tool, {}, terminal=(None, []))


def test_start_reports_a_missing_command(tmp_path, monkeypatch):
    monkeypatch.setattr(tl, "EXTRA_BIN_DIRS", (str(tmp_path),))
    monkeypatch.setattr(tl.shutil, "which", lambda _c: None)
    with pytest.raises(FileNotFoundError):
        tl.start({"key": "weg", "start_cmd": "weg"}, {})


def test_started_program_survives_the_app(tmp_path, monkeypatch):
    """start_new_session: beendet man yakuda-connect, laeuft das Tool weiter."""
    seen = {}

    def fake_popen(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return object()

    local = tmp_path / "bin"
    local.mkdir()
    _exe(local / "wayvr")
    monkeypatch.setattr(tl, "EXTRA_BIN_DIRS", (str(local),))
    monkeypatch.setattr(tl.subprocess, "Popen", fake_popen)
    tl.start({"key": "wayvr", "start_cmd": "wayvr"}, {})
    assert seen["argv"] == [str(local / "wayvr")]
    assert seen["kwargs"]["start_new_session"] is True


# --------------------------------------------------------------------------- #
#  Oberflaeche
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def app(qapp, tmp_path_factory):
    os.environ["HOME"] = str(tmp_path_factory.mktemp("home"))
    from PySide6.QtWidgets import QMessageBox
    for m in ("warning", "information", "critical"):
        setattr(QMessageBox, m, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from main import VRApp
    window = VRApp()
    yield window
    window.close()


def test_tools_tab_is_built_on_first_open(app, monkeypatch):
    """Tools-Tab kostet ~10 MB — erst beim ersten Oeffnen bauen, genau einmal."""
    if not app.ui._tools_built:
        assert app.ui.tool_cards == {}
        # Controls-Tab kennt die Tools trotzdem (aus tools.json)
        assert app._control_tool("obah").get("key") == "obah"
    # Ohne installierte Pakete sperrt die App alle Tabs ausser Installation
    monkeypatch.setattr(app, "are_critical_packages_missing", lambda: False)
    app.on_tab_changed(3)                       # Tools
    assert app.ui._tools_built and app.ui.tool_cards
    cards = dict(app.ui.tool_cards)
    app._ensure_tools_ui()                      # zweiter Aufruf baut nichts neu
    assert app.ui.tool_cards == cards


def test_every_card_has_a_start_button_next_to_the_command(app):
    app._ensure_tools_ui()
    cards = app.ui.tool_cards
    assert cards
    for key, card in cards.items():
        assert "btn_start" in card, key
        # Der Knopf sitzt in der Befehlszeile und ist damit automatisch nur
        # sichtbar, wenn das Werkzeug installiert ist.
        assert card["btn_start"].parent() is card["cmd_widget"]


def test_button_starts_the_tool_of_that_card(app, monkeypatch):
    started = []
    import tool_launcher
    monkeypatch.setattr(tool_launcher, "start",
                        lambda tool, status=None, **kw: started.append(tool["key"]))
    app._ensure_tools_ui()
    key = next(iter(app.ui.tool_cards))
    app.ui.tool_cards[key]["btn_start"].click()
    assert started == [key]
