#!/usr/bin/env python3
"""Tests fuer core/killcmd_suggest.py — Kill-Vorschlag aus dem Startbefehl."""
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "core"))

import pytest  # noqa: E402

import killcmd_suggest as ks  # noqa: E402


@pytest.mark.parametrize("cmd,mode,expected", [
    ("wayvr", "CMD", "pkill -f wayvr"),
    ("wayvr --openxr", "CMD", "pkill -f wayvr"),
    ("/usr/bin/vrcx", "CMD", "pkill -f vrcx"),
    ("env FOO=1 gamemoderun vrcx", "CMD", "pkill -f vrcx"),
    ("PROTON_LOG=1 osc-leash", "CMD", "pkill -f osc-leash"),
    ("flatpak run io.github.wivrn.wivrn", "CMD", "flatpak kill io.github.wivrn.wivrn"),
    ("bash -c 'slimevr --headless'", "CMD", "pkill -f slimevr"),
    ("/home/u/Apps/VRCX.AppImage", "Custom Path", "pkill -f VRCX.AppImage"),
    ("/opt/My App/start.sh", "Custom Path", "pkill -f start.sh"),
    ("/opt/x/My Tool.AppImage", "Custom Path", "pkill -f 'My Tool.AppImage'"),
    ("", "CMD", ""),
    ("   ", "Custom Path", ""),
    ("env FOO=1", "CMD", ""),
])
def test_suggest(cmd, mode, expected):
    assert ks.suggest(cmd, mode) == expected


def test_kill_field_gets_suggestion(window):
    w = window
    w._vr_add_row_clicked()
    r = w.autostart_rows[-1]
    r["combo"].setCurrentText("Custom Path")
    r["input"].setText("/home/u/Apps/VRCX.AppImage")
    r["chk_kill"].setChecked(True)                    # Haken setzt Fokus -> Vorschlag
    w._autostart_offer_kill_suggestion(r)
    assert r["kill_input"].text() == "pkill -f VRCX.AppImage"
    assert r["kill_input"].selectedText() == "pkill -f VRCX.AppImage"   # Tippen ersetzt ihn
    r["kill_input"].setText("meins")
    w._autostart_offer_kill_suggestion(r)             # Eigenes bleibt unangetastet
    assert r["kill_input"].text() == "meins"


def test_start_button_launches_rows(window, monkeypatch):
    called = []
    monkeypatch.setattr(type(window), "launch_autostart_apps", lambda self: called.append(1))
    window._vr_add_row_clicked()
    window.autostart_rows[-1]["input"].setText("wayvr")
    window._update_autostart_start_button()
    assert window.ui.btn_autostart_start.isEnabled()
    window.ui.btn_autostart_start.click()
    assert called == [1]
    for r in list(window.autostart_rows):
        r["input"].setText("")
    window._update_autostart_start_button()
    assert not window.ui.btn_autostart_start.isEnabled()


from test_exit_guard import window, _FakeProc, exit_guard, wivrn_server  # noqa: E402,F401


def test_profile_rows_have_kill_and_run_it_on_stop(window, monkeypatch):
    import exit_guard as eg
    import autostart_profiles as engine
    import killcmd_migrate
    w = window
    prof = w._profile_add({"name": "T", "trigger": "VRChat.exe", "apps": []})
    w._profile_add_row(prof, {"type": "CMD", "cmd": "vrcx"})
    r = prof["rows"][-1]
    assert r["widget"].objectName() == "autostartRowCard" and prof["col_labels"]
    r["chk_kill"].setChecked(True)
    w._autostart_offer_kill_suggestion(r)
    assert r["kill_input"].text() == "pkill -f vrcx"
    data = w._profile_data(prof)
    assert data["apps"][-1]["kill_on"] and data["apps"][-1]["kill"] == "pkill -f vrcx"
    assert engine.kill_commands(data) == [{"label": "vrcx", "cmd": "pkill -f vrcx"}]
    ran = []
    monkeypatch.setattr(eg, "run_kill_commands", lambda entries: ran.extend(entries))
    prof["ext"] = [[999999, 0]]                   # „laeuft“
    w._profile_stop(prof)
    assert [e["cmd"] for e in ran] == ["pkill -f vrcx"]
    settings = {"autostart_profiles": [data]}
    assert [e["cmd"] for e in killcmd_migrate.all_kill_commands(settings)] == ["pkill -f vrcx"]
