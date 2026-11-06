#!/usr/bin/env python3
"""Tools ueber Steam: Methode, Status, Start und Kill-Vorschlag."""
import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

import appimage_installer as ai
import autostart_name as an
import games as games_db
import killcmd_suggest as ks
import steam_tools
import tool_launcher
import vr_environment as venv

TOOL = {"key": "x", "name": "X", "start_cmd": "xbin", "install_methods": ["steam"],
        "steam_appid": "123"}


@pytest.fixture
def steam(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/steam" if n == "steam" else None)
    monkeypatch.setattr(games_db, "_steamapps_dirs", lambda: [str(tmp_path)])
    return tmp_path


def test_methode_nur_mit_steam(steam, monkeypatch):
    assert ai.detect_install_methods(TOOL) == ["steam"]
    monkeypatch.setattr(shutil, "which", lambda _n: None)
    monkeypatch.setattr(venv, "steam_is_flatpak", lambda: False)
    assert ai.detect_install_methods(TOOL) == []


def test_status_aus_appmanifest(steam):
    assert steam_tools.is_installed("123") is False
    (steam / "appmanifest_123.acf").write_text("x")
    assert steam_tools.is_installed("123") is True


def test_install_oeffnet_steam_link(steam, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **k: calls.append(argv))
    assert steam_tools.install("123") is True
    assert steam_tools.uninstall("123") is True
    assert calls == [["steam", "steam://install/123"], ["steam", "steam://uninstall/123"]]


def test_start_ueber_steam(steam):
    assert tool_launcher.build_command(TOOL, {"steam_installed": True}) == \
        ["steam", "-applaunch", "123"]


def test_autostart_erkennt_steam_tool(steam):
    cmd = steam_tools.autostart_command("123")
    assert cmd == "steam -applaunch 123"
    assert an.find_tool(cmd, "CMD", [TOOL]) is TOOL
    assert an.is_tool_command(cmd, [TOOL]) is True
    assert an.display_name(cmd, "CMD", "", [TOOL]) == "X"


@pytest.mark.parametrize("cmd", ["steam -applaunch 123",
                                 "flatpak run com.valvesoftware.Steam -applaunch 123"])
def test_kill_vorschlag_beendet_nie_steam(cmd):
    assert ks.suggest(cmd) == ""


def test_tools_json_steam_eintraege():
    data = json.loads((ROOT / "config" / "tools.json").read_text(encoding="utf-8"))
    tools = {t["key"]: t for t in data["apps"] + data["osc"]}
    assert tools["vrcft-avalonia"]["steam_appid"] == "3329480"
    assert tools["vrcft-avalonia"]["steam_beta"] == "avalonia"
    assert tools["baballonia"]["steam_appid"] == "4091970"
    assert "steam" in tools["baballonia"]["install_methods"]


@pytest.fixture
def config(monkeypatch, tmp_path):
    monkeypatch.setattr(games_db, "APP_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setattr(games_db, "detect_gpu_vendor", lambda: "amd")


def _vrchat_toggles():
    return games_db.resolved_toggles(games_db.GAMES["438100"])


def test_vrchat_amd_parameter_standardmaessig_an(config):
    game = games_db.GAMES["438100"]
    assert game["launch_params"] == {"amd": "%command%", "nvidia": "%command%"}
    keys = {t["key"]: t for t in _vrchat_toggles()}
    assert keys["vrc_avpro_proton"]["default"] and keys["vrc_amd_stutter"]["default"]
    assert keys["vrc_avpro_proton"]["panel_only"] and keys["vrc_amd_stutter"]["panel_only"]


def test_vrchat_nvidia_hat_nur_den_avpro_schalter(monkeypatch):
    monkeypatch.setattr(games_db, "detect_gpu_vendor", lambda: "nvidia")
    keys = {t["key"] for t in _vrchat_toggles()}
    assert "vrc_avpro_proton" in keys
    assert "vrc_amd_stutter" not in keys


def test_alte_einstellungen_behalten_die_parameter(config):
    import json as js
    with open(games_db.APP_CONFIG, "w") as fh:
        js.dump({"games_launch_toggles": {"438100": {"toggles": ["force_openxr"], "custom": ""}}}, fh)
    keys, _custom = games_db.load_launch_toggles("438100", _vrchat_toggles())
    assert "vrc_avpro_proton" in keys and "vrc_amd_stutter" in keys


def test_abschalten_bleibt_gespeichert(config):
    games_db.save_launch_toggles("438100", ["vrc_avpro_proton"], "")
    keys, _custom = games_db.load_launch_toggles("438100", _vrchat_toggles())
    assert "vrc_avpro_proton" in keys and "vrc_amd_stutter" not in keys


class _Tabs:
    def __init__(self, index):
        self.index = index

    def currentIndex(self):
        return self.index

    def setCurrentIndex(self, index):
        self.index = index


@pytest.mark.parametrize("start,visible,expected", [
    (0, {"apps": 0, "osc": 2}, 1),
    (1, {"apps": 3, "osc": 0}, 0),
    (0, {"apps": 1, "osc": 2}, 0),
    (0, {"apps": 0, "osc": 0}, 0),
])
def test_tools_wechselt_zum_reiter_mit_treffern(start, visible, expected):
    from types import SimpleNamespace
    from tabs.tools_mixin import ToolsTabMixin
    host = SimpleNamespace(ui=SimpleNamespace(tools_subtabs=_Tabs(start)))
    ToolsTabMixin._show_tools_page_with_results(host, visible)
    assert host.ui.tools_subtabs.index == expected
