#!/usr/bin/env python3
"""Kompakte Autostart-Zeilen: Anzeigename, + Programm, Zahnrad-Fenster."""
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import autostart_name as an

TOOLS = [{"name": "WayVR", "start_cmd": "wayvr"},
         {"name": "VRCX", "start_cmd": "vrcx", "flatpak_id": "org.vrcx.VRCX"}]


@pytest.mark.parametrize("cmd,mode,name,expected", [
    ("wayvr", "CMD", "", "WayVR"),
    ("gamemoderun wayvr --foo", "CMD", "", "WayVR"),
    ("flatpak run org.vrcx.VRCX", "CMD", "", "VRCX"),
    ("flatpak run io.github.foo.Bar", "CMD", "", "Bar"),
    ("/home/u/Apps/Tool-1.2.AppImage", "Custom Path", "", "Tool-1.2"),
    ("wayvr", "CMD", "Mein Overlay", "Mein Overlay"),
    ("unbekannt --flag", "CMD", "", "unbekannt"),
    ("", "CMD", "", ""),
])
def test_anzeigename(cmd, mode, name, expected):
    assert an.display_name(cmd, mode, name, TOOLS) == expected


class Host:
    """Das Noetigste, was eine Zeile vom Gastgeber braucht."""
    def __init__(self, tools=()):
        self.tools = list(tools)

    def _autostart_command_pool(self):
        return []

    def _autostart_mode_changed(self, mode, line_edit, button):
        pass

    def _autostart_browse(self, line_edit, combo):
        pass

    def _installed_tool_commands(self):
        return self.tools


@pytest.fixture
def host(qapp):
    from PySide6.QtWidgets import QWidget

    class Parent(QWidget, Host):
        def __init__(self):
            QWidget.__init__(self)
            Host.__init__(self)
    return Parent()


def _row(host, app=None):
    from ui.autostart_row import build_row
    return build_row(host, app)


def test_zeile_zeigt_nur_name_zahnrad_und_x(host):
    row = _row(host, {"type": "CMD", "cmd": "wayvr"})
    assert row["lbl_name"].text() == "WayVR"
    assert row["panel"].isHidden()
    assert not row["btn_settings"].isHidden()
    assert not row["btn_del"].isHidden()
    assert row["badge_debug"].isHidden() and row["badge_kill"].isHidden()


def test_abzeichen_zeigen_debug_und_kill(host):
    row = _row(host, {"type": "CMD", "cmd": "wayvr", "debug": True,
                      "kill_on": True, "kill": "pkill wayvr"})
    assert not row["badge_debug"].isHidden()
    assert not row["badge_kill"].isHidden()


def test_alte_gespeicherte_typen_bleiben(host):
    from ui.autostart_row import row_data
    assert row_data(_row(host, {"type": "CMD", "cmd": "x"}))["type"] == "CMD"
    path = row_data(_row(host, {"type": "Custom Path", "cmd": "/a/b"}))
    assert path["type"] == "Custom Path" and "name" not in path and "kill" not in path


def test_eigener_name_wird_gespeichert(host):
    from ui.autostart_row import row_data
    row = _row(host, {"type": "CMD", "cmd": "wayvr"})
    row["name_input"].setText("Overlay")
    assert row["lbl_name"].text() == "Overlay"
    assert row_data(row)["name"] == "Overlay"


def test_zahnrad_gibt_panel_an_die_karte_zurueck(host, monkeypatch):
    from PySide6.QtWidgets import QDialog
    from ui.autostart_row import open_row_settings
    seen = []
    monkeypatch.setattr(QDialog, "exec", lambda self: seen.append(self) or 0)
    row = _row(host, {"type": "CMD", "cmd": "wayvr"})
    open_row_settings(host, row)
    assert seen and row["panel"].parent() is row["widget"]
    assert row["panel"].isHidden()


def _pick(monkeypatch, index, accept=True):
    from PySide6.QtWidgets import QDialog, QListWidget

    def fake_exec(self):
        lists = self.findChildren(QListWidget)
        if lists:
            lists[0].setCurrentRow(index)
            return QDialog.Accepted if accept else QDialog.Rejected
        return QDialog.Rejected
    monkeypatch.setattr(QDialog, "exec", fake_exec)


def _tools(host):
    host.tools = [{"name": "WayVR", "cmd": "wayvr"}]


def test_pick_app(host, monkeypatch):
    from ui.autostart_row import pick_program
    _tools(host)
    _pick(monkeypatch, 3)
    assert pick_program(host) == {"type": "CMD", "cmd": "wayvr"}


def test_abbrechen_legt_keine_zeile_an(host, monkeypatch):
    from ui.autostart_row import add_program
    _tools(host)
    _pick(monkeypatch, 3, accept=False)
    made = []
    assert add_program(host, lambda app: made.append(app)) is None
    assert made == []


def test_eigener_befehl_ohne_eingabe_loescht_zeile(host, monkeypatch):
    from ui.autostart_row import add_program, build_row
    _pick(monkeypatch, 0)
    removed = []

    def append(app):
        return build_row(host, app, on_delete=removed.append)
    assert add_program(host, append) is None
    assert len(removed) == 1


def test_eigenes_programm_abbrechen(host, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from ui.autostart_row import pick_program
    _pick(monkeypatch, 1)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")))
    assert pick_program(host) is None
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: ("/opt/x", "")))
    assert pick_program(host) == {"type": "Custom Path", "cmd": "/opt/x"}


def test_tool_befehl_wird_programm(host, monkeypatch):
    import programs
    from ui.autostart_row import row_data
    monkeypatch.setattr(programs, "all_tools", lambda: TOOLS)
    row = _row(host, {"type": "CMD", "cmd": "wayvr"})
    assert row["combo"].mode() == "App"
    assert row_data(row)["type"] == "CMD"


def test_anderer_befehl_bleibt_eigener_befehl(host, monkeypatch):
    import programs
    monkeypatch.setattr(programs, "all_tools", lambda: TOOLS)
    assert _row(host, {"type": "CMD", "cmd": "wayvr --x"})["combo"].mode() == "CMD"
    assert _row(host, {"type": "Custom Path", "cmd": "wayvr"})["combo"].mode() == "Custom Path"


def test_tippen_springt_nicht_auf_programm(host, monkeypatch):
    import programs
    monkeypatch.setattr(programs, "all_tools", lambda: TOOLS)
    row = _row(host, {"type": "CMD", "cmd": ""})
    row["input"].setText("wayvr")
    assert row["combo"].mode() == "CMD"


def test_tooltip_zeigt_beschreibung_und_befehl(host, monkeypatch):
    import programs
    tools = [{"name": "WayVR", "start_cmd": "wayvr", "desc": "Overlay", "desc_eng": "Overlay"}]
    monkeypatch.setattr(programs, "all_tools", lambda: tools)
    tip = _row(host, {"type": "CMD", "cmd": "wayvr"})["lbl_name"].toolTip()
    assert tip == "Overlay\n\nwayvr"
    assert _row(host, {"type": "CMD", "cmd": "fremd"})["lbl_name"].toolTip() == "fremd"


def test_eigenes_icon_wird_gespeichert(host):
    from ui.autostart_row import row_data
    row = _row(host, {"type": "CMD", "cmd": "x", "icon": "/a/b.png"})
    assert row_data(row)["icon"] == "/a/b.png"
    assert not row["btn_icon_reset"].isHidden()


def test_icon_holen_nur_bei_bekanntem_programm_ohne_icon(host, monkeypatch, tmp_path):
    import paths
    import programs
    monkeypatch.setattr(paths, "config_root", lambda: str(tmp_path))
    monkeypatch.setattr(programs, "all_tools",
                        lambda: [{"key": "zz", "name": "ZZ", "start_cmd": "zzapp",
                                  "icon_url": "https://example.org/i.png"},
                                 {"key": "yy", "name": "YY", "start_cmd": "yyapp"}])
    row = _row(host, {"type": "CMD", "cmd": "zzapp"})
    assert not row["btn_icon_fetch"].isHidden() and row["btn_icon_fetch"].isEnabled()
    row = _row(host, {"type": "CMD", "cmd": "yyapp"})
    assert not row["btn_icon_fetch"].isHidden() and not row["btn_icon_fetch"].isEnabled()
    assert _row(host, {"type": "CMD", "cmd": "fremd"})["btn_icon_fetch"].isHidden()
    (tmp_path / "icons").mkdir()
    (tmp_path / "icons" / "zz.png").write_bytes(b"\x89PNG")
    assert _row(host, {"type": "CMD", "cmd": "zzapp"})["btn_icon_fetch"].isHidden()


def test_icons_lassen_sich_ausblenden(host):
    host._show_autostart_icons = False
    assert _row(host, {"type": "CMD", "cmd": "x"})["lbl_icon"].isHidden()


def test_auswahl_zeigt_icon_und_info(host, monkeypatch):
    from PySide6.QtWidgets import QDialog, QListWidget
    from ui.autostart_row import DESC_ROLE, pick_program
    host.tools = [{"key": "wayvr", "name": "WayVR", "cmd": "wayvr"},
                  {"name": "Unbekannt", "cmd": "xyz"}]
    seen = {}

    def fake_exec(self):
        listw = self.findChildren(QListWidget)[0]
        known, unknown = listw.item(3), listw.item(4)
        seen["icon"] = not known.icon().isNull()
        seen["info"] = bool(known.data(DESC_ROLE))
        seen["no_info"] = not unknown.data(DESC_ROLE)
        return QDialog.Rejected
    monkeypatch.setattr(QDialog, "exec", fake_exec)
    pick_program(host)
    assert seen == {"icon": True, "info": True, "no_info": True}


def test_seltene_tools_ganz_unten(host, monkeypatch):
    from PySide6.QtWidgets import QDialog, QListWidget
    from ui.autostart_row import pick_program
    host.tools = [{"key": "obah", "name": "obah", "cmd": "obah"},
                  {"key": "protonplus", "name": "ProtonPlus", "cmd": "protonplus"},
                  {"key": "wayvr", "name": "WayVR", "cmd": "wayvr"},
                  {"key": "unityhub", "name": "Unity Hub", "cmd": "unityhub"},
                  {"key": "vrcx", "name": "VRCX", "cmd": "vrcx"}]
    seen = []

    def fake_exec(self):
        listw = self.findChildren(QListWidget)[0]
        seen.extend(listw.item(i).text() for i in range(3, listw.count()))
        listw.setCurrentRow(3)
        return QDialog.Accepted
    monkeypatch.setattr(QDialog, "exec", fake_exec)
    assert pick_program(host) == {"type": "CMD", "cmd": "wayvr"}
    assert seen[:2] == ["WayVR", "VRCX"]
    assert seen[3:] == ["obah", "ProtonPlus", "Unity Hub"]


def test_steam_programm_hinzufuegen(host, monkeypatch):
    from PySide6.QtWidgets import QDialog, QListWidget
    import steam_tools
    from ui.autostart_row import pick_program
    monkeypatch.setattr(steam_tools, "available", lambda: True)
    monkeypatch.setattr(steam_tools, "installed_apps",
                        lambda: [{"appid": "3329480", "name": "VRCFaceTracking"}])
    monkeypatch.setattr(steam_tools, "autostart_command",
                        lambda appid: f"steam -applaunch {appid}")
    calls = []

    def fake_exec(self):
        listw = self.findChildren(QListWidget)[0]
        calls.append(1)
        listw.setCurrentRow(2 if len(calls) == 1 else 0)
        return QDialog.Accepted
    monkeypatch.setattr(QDialog, "exec", fake_exec)
    assert pick_program(host) == {"type": "CMD", "cmd": "steam -applaunch 3329480",
                                  "name": "VRCFaceTracking"}


def test_steam_apps_nur_software(tmp_path, monkeypatch):
    import games as games_db
    import steam_appinfo
    import steam_tools
    for appid, name in (("3329480", "VRCFaceTracking"), ("620", "Portal 2"),
                        ("1493710", "Proton Experimental")):
        (tmp_path / f"appmanifest_{appid}.acf").write_text(
            f'"AppState"\n{{\n"appid" "{appid}"\n"name" "{name}"\n}}\n')
    monkeypatch.setattr(games_db, "_steamapps_dirs", lambda: [str(tmp_path)])
    monkeypatch.setattr(steam_appinfo, "commons", lambda ids: (
        {"3329480": {"type": "Application"}, "620": {"type": "Game"}}, True))
    assert [a["name"] for a in steam_tools.installed_apps()] == ["VRCFaceTracking"]
