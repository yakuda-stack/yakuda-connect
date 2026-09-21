#!/usr/bin/env python3
"""
tests/test_obah_bindings.py — Auswahl-Schritte von obah (Spiel/Controller/Bindings)
==================================================================================
Nachgebaute Steam-Bibliothek mit einem Unity-typischen Spiel:
  <Spiel>/<Spiel>_Data/StreamingAssets/SteamVR/actions.json
mit Default-Bindings fuer Index und Touch, dazu eine xrizer-Datei und eine
VapoR-Datei — so wie obah sie im Spielordner sucht.
"""
import json
import os
import sys
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import obah_bindings as ob  # noqa: E402


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) if not isinstance(data, str) else data)


@pytest.fixture
def library(tmp_path):
    sa = tmp_path / "steamapps"
    # Spiel 1: installdir weicht vom Namen ab (Steam macht das oft)
    game = sa / "common" / "SpaceGame"
    steamvr = game / "SpaceGame_Data" / "StreamingAssets" / "SteamVR"
    _write(steamvr / "actions.json", {
        "actions": [],
        "default_bindings": [
            {"controller_type": "knuckles", "binding_url": "bindings_knuckles.json"},
            {"controller_type": "oculus_touch", "binding_url": "bindings_touch.json"},
            {"controller_type": "unbekannt", "binding_url": "x.json"},
        ]})
    _write(steamvr / "bindings_knuckles.json", {"controller_type": "knuckles"})
    _write(steamvr / "bindings_touch.json", {"controller_type": "oculus_touch"})
    _write(game / "xrizer" / "knuckles.json", {})
    _write(game / "xrizer" / "vivecontroller.json", {})     # ohne Unterstriche!
    _write(game / "vapor_binding.json", {"controller_type": "oculus_touch"})
    _write(game / "OpenComposite" / "gamepad.json", {})

    # Spiel 2: kein VR -> taucht nicht auf
    (sa / "common" / "FlatGame").mkdir(parents=True)
    # Spiel 3: Manifest mit anderem erlaubten Namen, alphabetisch vorne
    _write(sa / "common" / "aero" / "bin" / "vr_actions.json", {"default_bindings": []})

    apps = [
        {"appid": "1", "name": "Space Game: Deluxe", "installdir": "SpaceGame", "steamapps": str(sa)},
        {"appid": "2", "name": "Flat Game", "installdir": "FlatGame", "steamapps": str(sa)},
        {"appid": "3", "name": "Aero", "installdir": "aero", "steamapps": str(sa)},
        {"appid": "4", "name": "Deinstalliert", "installdir": "weg", "steamapps": str(sa)},
    ]
    return apps


def test_list_games_only_vr_and_sorted(library):
    games = ob.list_games(apps=library)
    assert [g.name for g in games] == ["Aero", "Space Game: Deluxe"]
    space = games[1]
    assert space.actions_json.endswith("SteamVR/actions.json")


def test_find_actions_json_respects_depth(tmp_path):
    deep = tmp_path / "a" / "b" / "c"
    _write(deep / "actions.json", {})
    assert ob.find_actions_json(str(tmp_path)) is not None
    assert ob.find_actions_json(str(tmp_path), max_depth=2) is None


def test_scan_bindings_like_obah(library):
    game = ob.list_games(apps=library)[1]
    gb = ob.scan_bindings(game)
    assert set(gb.controllers) == set(ob.CONTROLLER_TYPES)   # immer alle Profile
    k = gb.controllers["knuckles"]
    assert (k.default, k.xrizer, k.vapor, k.opencomposite) == (True, True, False, False)
    t = gb.controllers["oculus_touch"]
    assert (t.default, t.xrizer, t.vapor) == (True, False, True)
    assert gb.controllers["vive_controller"].xrizer is True    # vivecontroller.json
    assert gb.controllers["gamepad"].opencomposite is True
    assert not gb.controllers["rift"].any()


def test_sources_order_and_scratch_always_last(library):
    gb = ob.scan_bindings(ob.list_games(apps=library)[1])
    assert gb.controllers["knuckles"].sources() == ["default", "xrizer", "scratch"]
    assert gb.controllers["oculus_touch"].sources() == ["default", "vapor", "scratch"]
    assert gb.controllers["rift"].sources() == ["scratch"]


def test_binding_file_resolution(library):
    game = ob.list_games(apps=library)[1]
    assert ob.binding_file(game, "knuckles", "default").endswith("bindings_knuckles.json")
    assert ob.binding_file(game, "knuckles", "xrizer").endswith("xrizer/knuckles.json")
    assert ob.binding_file(game, "vive_controller", "xrizer").endswith("xrizer/vivecontroller.json")
    assert ob.binding_file(game, "oculus_touch", "vapor").endswith("vapor_binding.json")
    assert ob.binding_file(game, "rift", "default") is None
    assert ob.binding_file(game, "knuckles", "scratch") is None


def test_missing_default_file(library, tmp_path):
    game = ob.list_games(apps=library)[1]
    os.remove(ob.binding_file(game, "knuckles", "default"))
    assert ob.binding_file(game, "knuckles", "default") is None
    assert ob.binding_file(game, "knuckles", "default", must_exist=False).endswith("bindings_knuckles.json")


def test_labels():
    assert ob.format_name("oculus_touch") == "Oculus Touch"
    assert ob.controller_label("knuckles") == "Valve Index (Knuckles)"


# --------------------------------------------------------------------------- #
#  Oberflaeche
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def app(qapp, tmp_path_factory):
    os.environ["HOME"] = str(tmp_path_factory.mktemp("home"))
    from PySide6.QtWidgets import QMessageBox
    for m in ("warning", "information", "critical"):
        setattr(QMessageBox, m, staticmethod(lambda *a, **k: QMessageBox.Ok))
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    from main import VRApp
    window = VRApp()
    yield window
    window.close()


def _wait_scan(app, qapp):
    w = app._obah_scan_worker
    if w is not None:
        w.wait(5000)
    for _ in range(20):
        qapp.processEvents()


def test_panel_collapsed_and_lazy(app):
    assert not app.ui.obah_body.isVisibleTo(app.ui.tab_controls)
    assert app._obah_scanned is False        # vor dem Aufklappen wird nichts gesucht


def test_panel_fills_dropdowns(app, qapp, library, monkeypatch):
    games = ob.list_games(apps=library)
    monkeypatch.setattr(ob, "list_games", lambda cancelled=None: games)
    app.ui.btn_obah_expand.setChecked(True)
    _wait_scan(app, qapp)
    ui = app.ui
    assert ui.obah_body.isVisibleTo(ui.tab_controls)
    assert [ui.combo_obah_game.itemText(i) for i in range(ui.combo_obah_game.count())] \
        == ["Aero", "Space Game: Deluxe"]

    ui.combo_obah_game.setCurrentIndex(1)
    assert ui.combo_obah_controller.count() == len(ob.CONTROLLER_TYPES)
    # Voreinstellung: Oculus/Meta Touch
    assert ui.combo_obah_controller.currentData() == "oculus_touch"

    ui.combo_obah_controller.setCurrentIndex(ui.combo_obah_controller.findData("knuckles"))
    assert [ui.combo_obah_source.itemData(i) for i in range(ui.combo_obah_source.count())] \
        == ["default", "xrizer", "scratch"]
    # Voreinstellung: xrizer
    assert ui.combo_obah_source.currentData() == "xrizer"
    assert "xrizer/knuckles.json" in ui.lbl_obah_hint.text()

    # Automatisch erzwungenes 'scratch' (Spiel ohne Bindings) wird NICHT mitgenommen
    ui.combo_obah_game.setCurrentIndex(0)
    assert ui.combo_obah_source.currentData() == "scratch"
    ui.combo_obah_game.setCurrentIndex(1)
    assert ui.combo_obah_controller.currentData() == "knuckles"
    assert ui.combo_obah_source.currentData() == "xrizer"

    # Eine SELBST getroffene Wahl bleibt beim Spielwechsel
    ui.combo_obah_source.setCurrentIndex(0)          # default
    ui.combo_obah_game.setCurrentIndex(0)
    ui.combo_obah_game.setCurrentIndex(1)
    assert ui.combo_obah_source.currentData() == "default"
    sel = app.obah_selection()
    assert sel[0].name == "Space Game: Deluxe" and sel[1:] == ("knuckles", "default")

    # Sprachwechsel behaelt die komplette Auswahl
    ui.combo_obah_source.setCurrentIndex(1)
    app.obah_retranslate()
    assert app.obah_selection()[1:] == ("knuckles", "xrizer")


def test_no_games(app, qapp, monkeypatch):
    monkeypatch.setattr(ob, "list_games", lambda cancelled=None: [])
    app.start_obah_game_scan()
    _wait_scan(app, qapp)
    assert not app.ui.combo_obah_game.isEnabled()
    assert not app.ui.combo_obah_controller.isEnabled()
    assert not app.ui.combo_obah_source.isEnabled()
    assert app.obah_selection() is None


# --------------------------------------------------------------------------- #
#  Spiele aus dem Games-Tab — auch Nicht-Steam (v1.3.2)
# --------------------------------------------------------------------------- #
def test_list_games_includes_games_tab(library, tmp_path):
    # Nicht-Steam-Spiel mit Action-Datei im Startordner
    heroic = tmp_path / "Games" / "Heroic"
    _write(heroic / "Data" / "actions.json", {"default_bindings": []})
    # eigenes Spiel ohne Action-Datei
    local = tmp_path / "Games" / "Local"
    local.mkdir(parents=True)
    (local / "game.x86_64").write_text("")
    library_entries = [
        {"id": "2", "name": "Flat Game", "kind": "steam", "exe": ""},
        {"id": "1", "name": "Space Game: Deluxe", "kind": "steam", "exe": ""},
        {"id": "3000000001", "name": "Heroic VR", "kind": "shortcut", "exe": ""},
        {"id": "local:1", "name": "Lokal", "kind": "local",
         "exe": str(local / "game.x86_64")},
    ]
    shortcuts = {"3000000001": {"start_dir": f'"{heroic}"', "exe": '"/usr/bin/heroic"'}}
    games = ob.list_games(apps=library, library=library_entries, shortcuts=shortcuts)
    by_name = {g.name: g for g in games}
    assert [g.name for g in games] == ["Aero", "Flat Game", "Heroic VR", "Lokal",
                                       "Space Game: Deluxe"]
    assert by_name["Heroic VR"].kind == ob.KIND_SHORTCUT
    assert by_name["Heroic VR"].actions_json.endswith("actions.json")
    assert not by_name["Lokal"].has_manifest and by_name["Lokal"].kind == ob.KIND_LOCAL
    assert not by_name["Flat Game"].has_manifest
    assert by_name["Space Game: Deluxe"].has_manifest       # nicht doppelt
    assert len({g.key for g in games}) == len(games)
    # ohne Manifest: keine Bindings, auch kein Blick ins Arbeitsverzeichnis
    assert not any(a.any() for a in ob.scan_bindings(by_name["Lokal"]).controllers.values())


def test_library_folder_skips_home_and_system(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert ob.library_folder(str(tmp_path), "") == ""
    assert ob.library_folder("/usr/bin", "") == ""
    game = tmp_path / "g"
    game.mkdir()
    assert ob.library_folder("", str(game / "run.sh")) == str(game.resolve())


def test_panel_lists_games_without_manifest(app, qapp, monkeypatch, tmp_path):
    games = [ob.ObahGame(name="Beat", appid="local:1", game_folder=str(tmp_path),
                         actions_json="", kind=ob.KIND_LOCAL)]
    monkeypatch.setattr(ob, "list_games", lambda cancelled=None: games)
    app.start_obah_game_scan()
    _wait_scan(app, qapp)
    ui = app.ui
    assert ui.combo_obah_game.isEnabled() and ui.combo_obah_game.count() == 1
    assert not ui.combo_obah_controller.isEnabled()
    assert app.obah_selection() is None
    assert "⚠" in ui.lbl_obah_hint.text()


def test_unreal_manifest_name_and_prefix(tmp_path):
    """steamvr_manifest.json (Unreal) zaehlt — aber nur mit echten Aktionen."""
    game = tmp_path / "Thief"
    _write(game / "Config" / "SteamVRBindings" / "steamvr_manifest.json",
           {"actions": [{"name": "/actions/main/in/grab", "type": "boolean"}]})
    assert ob.find_actions_json(str(game)).endswith("steamvr_manifest.json")
    fake = tmp_path / "Fake"
    _write(fake / "steamvr_manifest.json", {"irgendwas": 1})
    assert ob.find_actions_json(str(fake)) is None
    # Proton-Prefix
    pref = tmp_path / "pfx" / "AppData" / "Local"
    _write(pref / "Wanderer" / "Saved" / "Config" / "steamvr_manifest.json",
           {"actions": []})
    assert ob.find_prefix_manifest("1", dirs=[str(pref)]).endswith("steamvr_manifest.json")


def test_manual_manifest_wins(library, tmp_path):
    mf = tmp_path / "eigene" / "actions.json"
    _write(mf, {"actions": []})
    entries = [{"id": "local:1", "name": "Beat Saber", "kind": "local", "exe": ""}]
    games = ob.list_games(apps=library, library=entries, search_prefix=False,
                          manual={"local:local:1": str(mf)})
    beat = next(g for g in games if g.name == "Beat Saber")
    assert beat.has_manifest and beat.manual
    assert beat.game_folder == str(mf.parent)
    assert beat.ident == "local:local:1"


def test_panel_pick_manifest(app, qapp, monkeypatch, tmp_path):
    mf = tmp_path / "picked" / "actions.json"
    _write(mf, {"actions": [], "default_bindings": []})
    bad = tmp_path / "bad.json"
    _write(bad, {"nope": 1})
    games = [ob.ObahGame(name="Golf It", appid="571740", game_folder="",
                         actions_json="", kind=ob.KIND_STEAM)]
    monkeypatch.setattr(ob, "list_games", lambda cancelled=None: games)
    saved = {}
    monkeypatch.setattr(ob, "set_manual_manifest", lambda i, p: saved.update({i: p}) or True)
    app.start_obah_game_scan()
    _wait_scan(app, qapp)
    ui = app.ui
    assert ui.btn_obah_pick_manifest.isEnabled()
    assert not ui.combo_obah_controller.isEnabled()
    assert app.pick_obah_manifest(str(bad)) is False
    assert app.pick_obah_manifest(str(mf)) is True
    assert saved == {"steam:571740": str(mf)}
    assert ui.combo_obah_controller.isEnabled()
    assert app.obah_selection() is not None
