#!/usr/bin/env python3
"""Tests fuer core/killcmd_migrate.py — Kill-Befehle an Autostart-Zeilen."""
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "core"))

import killcmd_migrate as km  # noqa: E402


def test_migrate_matches_by_label_and_command():
    s = {"autostart_apps": [{"type": "CMD", "cmd": "vrcx"},
                            {"type": "Custom Path", "cmd": "/home/u/Apps/VRCX.AppImage"},
                            {"type": "CMD", "cmd": "wayvr"}],
         "custom_kill_commands": [{"label": "WayVR", "cmd": "pkill -f wayvr"},
                                  {"label": "", "cmd": "pkill -f VRCX.AppImage"},
                                  {"label": "Other", "cmd": "pkill foo"}]}
    assert km.migrate(s)
    assert s["autostart_apps"][2] == {"type": "CMD", "cmd": "wayvr", "kill_on": True,
                                      "kill": "pkill -f wayvr"}
    assert s["autostart_apps"][1]["kill"] == "pkill -f VRCX.AppImage"
    assert "kill" not in s["autostart_apps"][0]
    assert s["custom_kill_commands"] == [{"label": "Other", "cmd": "pkill foo"}]
    assert not km.migrate(s)                 # nur einmal


def test_all_kill_commands_uses_rows_and_rest():
    s = {"autostart_apps": [{"cmd": "a", "kill_on": True, "kill": "pkill a"},
                            {"cmd": "b", "kill_on": False, "kill": "pkill b"},
                            {"cmd": "c", "kill_on": True, "kill": "  "}],
         "custom_kill_commands": [{"label": "x", "cmd": "pkill x"}]}
    cmds = [e["cmd"] for e in km.all_kill_commands(s)]
    assert cmds == ["pkill x", "pkill a"]
