#!/usr/bin/env python3
"""
tests/test_obah_aux.py — Posen/Haptik/Skelett, Chords, Profile, Zeichnungen
===========================================================================
Der Rest des Controls-Tabs, der nicht an einer Controller-Taste haengt:

  * die beiden Listen aus obahs "Other"- und "Chords"-Bereich
  * benannte Profile (Belegung + Anordnung unter eigenem Namen)
  * Zeichnungen aller Controller, die im Dropdown stehen
  * deckende Aufklapplisten
  * die Nachfrage beim Schliessen mit ungespeicherten Aenderungen
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
import obah_editor as oe  # noqa: E402

A = "/actions/"


@pytest.fixture
def game(tmp_path):
    """VRChat-artiges Spiel mit Posen, Haptik und einem Chord."""
    g = tmp_path / "VRChat"
    svr = g / "VRChat_Data" / "StreamingAssets" / "SteamVR"
    svr.mkdir(parents=True)
    (g / "xrizer").mkdir()
    manifest = {
        "actions": [{"name": A + n, "type": t} for n, t in (
            ("Global/in/Jump", "boolean"), ("Global/in/Move", "vector2"),
            ("Global/in/Gesture", "boolean"), ("Global/in/Pose", "pose"),
            ("Global/in/Skel", "skeleton"), ("Global/out/Haptic", "vibration"),
            ("Menu/in/Select", "boolean"))],
        "action_sets": [{"name": "/actions/Global", "usage": "leftright"},
                        {"name": "/actions/Menu"}],
        "default_bindings": [],
    }
    (svr / "actions.json").write_text(json.dumps(manifest))
    binding = {"controller_type": "oculus_touch", "bindings": {"/actions/Global": {
        "sources": [{"path": "/user/hand/left/input/joystick", "mode": "joystick",
                     "inputs": {"position": {"output": A + "Global/in/Move"}}}],
        "poses": [{"output": A + "Global/in/Pose", "path": "/user/hand/left/pose/raw"}],
        "haptics": [{"output": A + "Global/out/Haptic", "path": "/user/hand/left/output/haptic"}],
        "chords": [{"inputs": [["/user/hand/left/input/x", "held"],
                               ["/user/hand/left/input/y", "held"]],
                    "output": A + "Global/in/Gesture"}],
    }}}
    (g / "xrizer" / "oculustouch.json").write_text(json.dumps(binding))
    return ob.ObahGame(name="VRChat", appid="438100", game_folder=str(g),
                       actions_json=str(svr / "actions.json"))


# --------------------------------------------------------------------------- #
#  Regeln (obah)
# --------------------------------------------------------------------------- #
def test_aux_sources_like_obah():
    paths, chords = oe.aux_sources("oculus_touch", {})
    kinds = {s["kind"] for s in paths}
    assert kinds == {"poses", "skeleton", "haptics"}
    # nach Art gruppiert (Posen, Skelett, Haptik) und darin nach Namen sortiert
    order = [oe.PATH_KINDS.index(s["kind"]) for s in paths]
    assert order == sorted(order)
    for kind in oe.PATH_KINDS:
        names = [s["name"] for s in paths if s["kind"] == kind]
        assert names == sorted(names)
    assert [s["name"] for s in paths if s["kind"] == "skeleton"] == ["Left Skeleton",
                                                                    "Right Skeleton"]
    assert "/user/hand/left/pose/raw" in [s["path"] for s in paths]
    assert "/user/hand/right/output/haptic" in [s["path"] for s in paths]
    # Skelett ist seitengebunden: links nur links
    skel = [s["path"] for s in paths if s["kind"] == "skeleton"]
    assert "/user/hand/left/input/skeleton/left" in skel
    assert "/user/hand/left/input/skeleton/right" not in skel
    # Chord-Quellen: Tasten beider Haende, aber NICHT /input/system
    assert any(p["path"].endswith("/input/x") for p in chords)
    assert not any(p["path"].endswith("/input/system") for p in chords)
    # Posen tauchen nicht als Karte auf
    assert not any(d.type in oe.AUX_TYPES for d in oe.inputs_for_side("oculus_touch", "left"))


def test_aux_sources_single_device_root():
    """Gamepad: die Wurzel kommt aus der Datei (obah: infer_single_device_user_root)."""
    b = {"bindings": {"/actions/m": {"sources": [{"path": "/user/gamepad/input/a"}]}}}
    _paths, chords = oe.aux_sources("gamepad", b)
    assert all(p["path"].startswith("/user/gamepad/input/") for p in chords)
    assert all(not p["name"].startswith(("Left ", "Right ")) for p in chords)


def test_action_choices_direction_and_type(game):
    m = oe.load_manifest(game.actions_json)
    assert oe.action_choices(m, "/actions/Global", "pose", "in") == [A + "Global/in/Pose"]
    assert oe.action_choices(m, "/actions/Global", "vibration", "out") == [A + "Global/out/Haptic"]
    # Vibration steht unter /out/ — unter /in/ gibt es sie nicht
    assert oe.action_choices(m, "/actions/Global", "vibration", "in") == []
    assert oe.action_choices(m, "/actions/Menu", "pose", "in") == []
    # Reihenfolge wie in der actions.json (so macht es obah auch)
    assert oe.action_choices(m, "/actions/Global", "boolean", "in") == [A + "Global/in/Jump",
                                                                       A + "Global/in/Gesture"]


def test_path_bindings_round_trip(game):
    b = oe.load_binding(ob.binding_file(game, "oculus_touch", "xrizer"))
    poses = oe.path_bindings(b, "/actions/Global", "poses")
    assert len(poses) == 1 and poses[0]["path"].endswith("/pose/raw")
    poses[0]["path"] = "/user/hand/left/pose/tip"
    oe.set_path_binding(b, "/actions/Global", "poses", 0, poses[0])
    assert oe.path_bindings(b, "/actions/Global", "poses")[0]["path"].endswith("/pose/tip")
    oe.set_path_binding(b, "/actions/Global", "poses", None,
                        {"output": A + "Global/in/Pose", "path": "/user/hand/right/pose/raw"})
    assert len(oe.path_bindings(b, "/actions/Global", "poses")) == 2
    oe.remove_path_binding(b, "/actions/Global", "poses", 0)
    oe.remove_path_binding(b, "/actions/Global", "poses", 0)
    assert oe.path_bindings(b, "/actions/Global", "poses") == []
    assert "poses" not in b["bindings"]["/actions/Global"]      # leere Liste faellt weg


def test_chord_round_trip(game):
    b = oe.load_binding(ob.binding_file(game, "oculus_touch", "xrizer"))
    chords = oe.chord_bindings(b, "/actions/Global")
    assert oe.chord_inputs(chords[0]) == [("/user/hand/left/input/x", "held"),
                                          ("/user/hand/left/input/y", "held")]
    oe.set_chord_inputs(chords[0], [("/user/hand/left/input/x", "touch")])
    oe.set_chord_binding(b, "/actions/Global", 0, chords[0])
    saved = oe.chord_bindings(b, "/actions/Global")[0]
    assert saved["inputs"] == [["/user/hand/left/input/x", "touch"]]     # Paare als Liste
    oe.remove_chord_binding(b, "/actions/Global", 0)
    assert "chords" not in b["bindings"]["/actions/Global"]


def test_new_drafts_and_availability(game):
    m = oe.load_manifest(game.actions_json)
    sources, chords = oe.aux_sources("oculus_touch", {})
    assert oe.can_add_path_binding(m, "/actions/Global", "poses", sources)
    assert not oe.can_add_path_binding(m, "/actions/Menu", "poses", sources)   # keine Aktion
    draft = oe.new_path_draft(m, "/actions/Global", "haptics", sources)
    assert draft["output"] == A + "Global/out/Haptic" and "output/haptic" in draft["path"]
    chord = oe.new_chord_draft(m, "/actions/Global", chords)
    assert len(oe.chord_inputs(chord)) == 1 and chord["output"].startswith(A + "Global/in/")
    assert oe.new_chord_draft(m, "/actions/Menu", chords)["output"] == A + "Menu/in/Select"


def test_saved_file_keeps_poses_and_chords(game, tmp_path):
    b = oe.load_binding(ob.binding_file(game, "oculus_touch", "xrizer"))
    out = str(tmp_path / "out" / "oculustouch.json")
    oe.save_binding(b, out, "oculus_touch")
    data = json.load(open(out))["bindings"]["/actions/Global"]
    assert data["poses"] and data["haptics"] and data["chords"]
    assert data["chords"][0]["inputs"][0] == ["/user/hand/left/input/x", "held"]


# --------------------------------------------------------------------------- #
#  Zeichnungen
# --------------------------------------------------------------------------- #
def test_every_offered_controller_has_a_drawing(qapp):
    from ui.controller_view import DRAWINGS
    assert set(DRAWINGS) == set(ob.CONTROLLER_TYPES)
    for ct, (func, box, scale) in DRAWINGS.items():
        for side in ("left", "right"):
            body, parts = func(side)
            assert body and parts, ct
            assert scale > 0 and box.width() > 0
            # jede Taste muss innerhalb der Zeichenflaeche liegen
            for d in oe.inputs_for_side(ct, "single" if not oe.is_handed(ct) else side):
                x, y = d.point
                assert box.left() - 1 <= x <= box.right() + 1, (ct, d.path)
                assert box.top() - 1 <= y <= box.bottom() + 1, (ct, d.path)


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
    window.resize(1400, 900)
    yield window
    window.close()


@pytest.fixture
def loaded(app, qapp, game, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "_obah_layout_file", lambda: str(tmp_path / "layout.json"))
    monkeypatch.setattr(app, "_obah_profiles_file", lambda: str(tmp_path / "profiles.json"))
    monkeypatch.setattr(ob, "list_games", lambda cancelled=None: [game])
    app._obah_scanned = False
    app._obah_user_source = None
    app._obah_user_controller = "oculus_touch"
    app._set_obah_dirty(False)
    app.ui.btn_obah_expand.setChecked(True)
    app.start_obah_game_scan()
    app._obah_scan_worker.wait(5000)
    for _ in range(20):
        qapp.processEvents()
    app._fill_obah_profiles()
    return app


def _rows(app, key):
    layout = app.ui.obah_aux_lists[key]["rows"]
    return [layout.itemAt(i).widget() for i in range(layout.count())]


def test_aux_lists_show_entries_and_add_rows(loaded):
    texts = [w.text() for w in _rows(loaded, "paths")]
    assert any("Left raw" in t and "→" in t for t in texts)
    assert any("Left haptic" in t for t in texts)
    assert sum(1 for t in texts if t.startswith("＋")) == 3      # Pose/Skelett/Vibration
    chords = [w.text() for w in _rows(loaded, "chords")]
    # Die Art ("held") steht in der Sprache der Anwendung dahinter — hier
    # zaehlen nur die beiden Quellen und das Plus dazwischen.
    from ui.binding_dialog import chord_kind_name
    held = chord_kind_name("held")
    assert any(f"Left x ({held}) + Left y ({held})" in t for t in chords)
    assert chords[-1].startswith("＋")

    # Action Set ohne passende Aktionen: kein Hinzufuegen, dafuer ein Hinweis
    ui = loaded.ui
    ui.obah_set_tabs.setCurrentIndex(1)                          # Menu
    texts = [w.text() for w in _rows(loaded, "paths") if hasattr(w, "text")]
    assert not any(t.startswith("＋") for t in texts)
    ui.obah_set_tabs.setCurrentIndex(0)


def test_edit_pose_via_dialog(loaded, monkeypatch, game):
    import ui.binding_dialog as bd

    def fake_exec(dlg):
        i = dlg.combo_src.findData("/user/hand/left/pose/tip")
        dlg.combo_src.setCurrentIndex(i)
        return bd.PathBindingDialog.Accepted
    monkeypatch.setattr(bd.PathBindingDialog, "exec", fake_exec)
    loaded.edit_obah_path_binding("poses", 0)
    assert loaded._obah_dirty
    poses = oe.path_bindings(loaded._obah_edit["binding"], "/actions/Global", "poses")
    assert poses[0]["path"] == "/user/hand/left/pose/tip"
    assert any("Left tip" in w.text() for w in _rows(loaded, "paths"))


def test_add_and_delete_chord(loaded, monkeypatch):
    import ui.binding_dialog as bd
    before = len(oe.chord_bindings(loaded._obah_edit["binding"], "/actions/Global"))

    def add(dlg):
        dlg._add_input()
        return bd.ChordBindingDialog.Accepted
    monkeypatch.setattr(bd.ChordBindingDialog, "exec", add)
    loaded.edit_obah_chord_binding(None)
    chords = oe.chord_bindings(loaded._obah_edit["binding"], "/actions/Global")
    assert len(chords) == before + 1
    assert len(oe.chord_inputs(chords[-1])) == 2

    def delete(dlg):
        dlg.deleted = True
        return bd.ChordBindingDialog.Accepted
    monkeypatch.setattr(bd.ChordBindingDialog, "exec", delete)
    loaded.edit_obah_chord_binding(len(chords) - 1)
    assert len(oe.chord_bindings(loaded._obah_edit["binding"], "/actions/Global")) == before


def test_chord_dialog_keeps_at_least_one_input(qapp, game):
    from ui.binding_dialog import ChordBindingDialog
    m = oe.load_manifest(game.actions_json)
    b = oe.load_binding(ob.binding_file(game, "oculus_touch", "xrizer"))
    _p, sources = oe.aux_sources("oculus_touch", b)
    dlg = ChordBindingDialog(None, manifest=m, set_name="/actions/Global",
                             set_label="Global", sources=sources,
                             draft=oe.chord_bindings(b, "/actions/Global")[0], is_new=False)
    assert len(dlg.pairs) == 2
    dlg._remove_input(0)
    assert len(dlg.pairs) == 1
    dlg._remove_input(0)
    assert len(dlg.pairs) == 1                                   # die letzte bleibt


# --------------------------------------------------------------------------- #
#  Profile
# --------------------------------------------------------------------------- #
def test_profile_save_load_delete(loaded, monkeypatch, qapp):
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    app = loaded
    ui = app.ui
    view = ui.obah_view_left

    # Anordnung aendern und eine Belegung setzen
    order = view.card_order()
    view.set_layout({"order": list(reversed(order)), "image": [12, 34]})
    app._save_obah_layout(view, view.layout_state())
    d = next(x for x in oe.inputs_for_side("oculus_touch", "left") if x.path == "/input/y")
    draft = oe.new_draft(d, "left", "oculus_touch", app._obah_edit["binding"])
    oe.set_draft_action(draft, "click", A + "Global/in/Jump")
    oe.apply_drafts(app._obah_edit["binding"], "/actions/Global", d, "left", [draft])
    app._set_obah_dirty(True)

    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Mein Setup", True)))
    app.save_obah_profile()
    assert ui.combo_obah_profile.findData("Mein Setup") >= 0
    stored = json.load(open(app._obah_profiles_file()))["profiles"]["Mein Setup"]
    assert stored["controller"] == "oculus_touch" and stored["game"] == "VRChat"
    assert stored["layout"]["oculus_touch:left"]["image"] == [12, 34]

    # alles wegwerfen, dann das Profil laden
    app.discard_obah_changes()
    view.set_layout({})
    app._save_obah_layout(view, {})
    assert not app._obah_dirty
    ui.combo_obah_profile.setCurrentIndex(ui.combo_obah_profile.findData("Mein Setup"))
    app.load_obah_profile()
    assert app._obah_dirty                                     # Belegung ist wieder da
    assert view.layout_state()["image"] == [12, 34]
    assert view.card_order() == list(reversed(order))
    left = {v.input.path: v for v in oe.build_view(
        app._obah_edit["manifest"], app._obah_edit["binding"], "oculus_touch",
        "/actions/Global", "left")}
    assert left["/input/y"].bound

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    app.delete_obah_profile()
    assert ui.combo_obah_profile.findData("Mein Setup") < 0


def test_profile_of_other_controller_applies_layout_only(loaded, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    app = loaded
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Index", True)))
    app.save_obah_profile()
    profiles = json.load(open(app._obah_profiles_file()))["profiles"]
    profiles["Index"]["controller"] = "knuckles"
    profiles["Index"]["binding"] = {"controller_type": "knuckles", "bindings": {}}
    profiles["Index"]["layout"] = {"oculus_touch:left": {"image": [5, 5], "order": []}}
    with open(app._obah_profiles_file(), "w") as fh:
        json.dump({"profiles": profiles}, fh)
    app._fill_obah_profiles(select="Index")

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    app._set_obah_dirty(False)
    app.load_obah_profile()
    # Belegung NICHT uebernommen (gehoert zu einem anderen Controller)
    assert not app._obah_dirty
    assert app._obah_edit["binding"]["controller_type"] == "oculus_touch"
    assert app.ui.obah_view_left.layout_state()["image"] == [5, 5]


# --------------------------------------------------------------------------- #
#  Aufklapplisten und Schliessen
# --------------------------------------------------------------------------- #
def test_dropdowns_are_opaque(loaded, qapp, game):
    from ui.opaque_combo import is_opaque
    ui = loaded.ui
    for combo in (ui.combo_obah_game, ui.combo_obah_controller, ui.combo_obah_source,
                  ui.combo_obah_profile):
        assert is_opaque(combo)

    from ui.binding_dialog import BindingDialog
    edit = loaded._obah_edit
    d = next(x for x in oe.inputs_for_side("oculus_touch", "left") if x.path == "/input/joystick")
    dlg = BindingDialog(None, manifest=edit["manifest"], binding=edit["binding"],
                        controller_type="oculus_touch", set_name="/actions/Global",
                        set_label="Global", input_def=d, side="left",
                        drafts=oe.source_drafts(edit["binding"], "/actions/Global", d, "left"))
    combos = dlg.editor_host.findChildren(type(ui.combo_obah_game))
    assert combos and all(is_opaque(c) for c in combos)


def test_close_asks_when_unsaved(loaded, monkeypatch, game):
    from PySide6.QtWidgets import QMessageBox
    app = loaded
    app._set_obah_dirty(True)
    seen = []

    def fake_exec(box):
        seen.append(box.text())
        for b in box.buttons():
            if box.buttonRole(b) == QMessageBox.RejectRole:     # Abbrechen
                b.click()
        return 0
    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    assert app.confirm_obah_close() is False                    # App bleibt offen
    assert seen and app._obah_dirty

    def discard(box):
        for b in box.buttons():
            if box.buttonRole(b) == QMessageBox.DestructiveRole:
                b.click()
        return 0
    monkeypatch.setattr(QMessageBox, "exec", discard)
    assert app.confirm_obah_close() is True
    assert not app._obah_dirty

    # Speichern schreibt die Datei und laesst schliessen
    app._set_obah_dirty(True)

    def save(box):
        for b in box.buttons():
            if box.buttonRole(b) == QMessageBox.AcceptRole:
                b.click()
        return 0
    monkeypatch.setattr(QMessageBox, "exec", save)
    assert app.confirm_obah_close() is True
    assert os.path.isfile(ob.xrizer_path(game.game_folder, "oculus_touch"))


def test_close_event_is_wired_and_signal_safe():
    """closeEvent fragt nach — ausser beim Beenden per Signal."""
    src = (ROOT / "core" / "main.py").read_text(encoding="utf-8")
    body = src[src.index("def closeEvent"):src.index("def closeEvent") + 1600]
    assert "confirm_obah_close()" in body
    assert "exit_guard.quit_requested_by_signal" in body
    assert "event.ignore()" in body
    guard = (ROOT / "core" / "exit_guard.py").read_text(encoding="utf-8")
    assert "quit_requested_by_signal = True" in guard


# --------------------------------------------------------------------------- #
#  Texturen, Zentrierung, Einklappen
# --------------------------------------------------------------------------- #
def test_every_controller_has_a_texture_file(qapp):
    """Zu jedem Controller aus dem Dropdown liegt ein Bild in assets/controls."""
    from ui.controller_view import texture_file
    for ct in ob.CONTROLLER_TYPES:
        sides = ("left", "right") if oe.is_handed(ct) else ("single",)
        for side in sides:
            found = texture_file(ct, side)
            assert found, (ct, side)
            path, mirror = found
            assert os.path.isfile(path)
            # Seitenweise Bilder werden NICHT noch einmal gespiegelt
            assert mirror is (os.path.basename(path) == ct + ".png" and side == "right")


def test_texture_replaces_drawing_and_falls_back(qapp, monkeypatch, tmp_path):
    """Fehlt das Bild, wird wieder gezeichnet — ohne Absturz."""
    import ui.controller_view as cv
    view = cv.ControllerBindingView()
    views = [oe.InputView(input=d) for d in oe.inputs_for_side("knuckles", "left")]
    texts = {"modes": {}, "inputs": {}, "unbound": "—", "none": "—", "title": "L"}
    view.set_data("knuckles", "left", views, texts)
    assert view._texture() is not None

    monkeypatch.setattr(cv, "ASSET_TEXTURE_DIR", str(tmp_path / "leer"))
    monkeypatch.setattr(cv, "texture_dirs", lambda: [str(tmp_path / "leer")])
    cv.clear_texture_cache()
    assert view._texture() is None
    view.set_data("knuckles", "left", views, texts)     # zeichnet wieder selbst
    assert view.card_count() == len(views)


def test_controller_sits_in_the_middle_of_the_box(qapp):
    """Ohne eigene Anordnung steht die Zeichnung mittig zur Kartenspalte."""
    from ui.controller_view import ControllerBindingView
    view = ControllerBindingView()
    views = [oe.InputView(input=d) for d in oe.inputs_for_side("oculus_touch", "left")]
    view.resize(900, 600)
    view.set_data("oculus_touch", "left",
                  views, {"modes": {}, "inputs": {}, "unbound": "—", "none": "—", "title": "L"})
    tops = [view.card_rect(i) for i in range(view.card_count())]
    column = (min(r.top() for r in tops), max(r.bottom() for r in tops))
    img = view._img_rect
    assert abs(img.center().y() - (column[0] + column[1]) / 2) < 2


def test_collapsing_hides_everything_below_but_keeps_it_working(loaded, qapp):
    """Zugeklappt ist nichts mehr zu sehen — die Auswahl bleibt aber stehen."""
    ui = loaded.ui
    assert ui.obah_editor.isVisibleTo(ui.tab_controls)
    before = ui.obah_view_left.card_count()

    ui.btn_obah_expand.setChecked(False)
    assert not ui.obah_body.isVisibleTo(ui.tab_controls)
    assert not ui.obah_editor.isVisibleTo(ui.tab_controls)
    assert loaded._obah_edit is not None            # Daten sind weiter geladen
    assert ui.obah_view_left.card_count() == before

    ui.btn_obah_expand.setChecked(True)
    assert ui.obah_editor.isVisibleTo(ui.tab_controls)


def test_aux_section_is_its_own_collapsible_block(loaded, qapp):
    """Der untere Teil klappt getrennt auf und bleibt befuellt."""
    ui = loaded.ui
    assert not ui.obah_aux_body.isVisibleTo(ui.obah_editor)     # standardmaessig zu
    assert ui.obah_aux_lists["paths"]["rows"].count() > 0       # trotzdem gefuellt

    ui.btn_obah_aux_expand.setChecked(True)
    assert ui.obah_aux_body.isVisibleTo(ui.obah_editor)
    ui.btn_obah_aux_expand.setChecked(False)
    assert not ui.obah_aux_body.isVisibleTo(ui.obah_editor)


# --------------------------------------------------------------------------- #
#  Aufgeraeumter Modus
# --------------------------------------------------------------------------- #
def test_tidy_mode_leaves_only_the_names(qapp):
    """Aufgeraeumt: die Karte zeigt den Namen der Taste, nicht ihre Belegung."""
    from ui.controller_view import ControllerBindingView
    view = ControllerBindingView()
    views = [oe.InputView(input=d) for d in oe.inputs_for_side("oculus_touch", "left")]
    view.resize(900, 600)
    view.set_data("oculus_touch", "left", views,
                  {"modes": {}, "inputs": {}, "unbound": "—", "none": "—", "title": "L"})
    tall = view.card_rect(0).height()
    assert view.card_lines(0)                      # vorher steht die Belegung da

    view.set_tidy(True)
    assert view.is_tidy()
    assert view.card_lines(0) == []                # nachher nicht mehr
    assert view.card_rect(0).height() < tall       # und die Karte ist kleiner

    view.set_tidy(False)
    assert not view.is_tidy()
    assert view.card_lines(0)


def test_single_cards_toggle_and_flip_the_mode(qapp):
    """Alles einzeln versteckt = aufgeraeumt; eine wieder her = nicht mehr."""
    from ui.controller_view import ControllerBindingView
    view = ControllerBindingView()
    views = [oe.InputView(input=d) for d in oe.inputs_for_side("oculus_touch", "left")]
    paths = [v.input.path for v in views]
    view.set_data("oculus_touch", "left", views,
                  {"modes": {}, "inputs": {}, "unbound": "—", "none": "—", "title": "L"})

    states = []
    view.tidy_changed.connect(states.append)
    for path in paths:
        view.toggle_compact(path)
    assert view.is_tidy() and states[-1] is True
    assert states.count(True) == 1                 # erst mit der letzten Karte

    view.toggle_compact(paths[0])
    assert not view.is_tidy() and states[-1] is False
    assert view.is_compact(paths[1]) and not view.is_compact(paths[0])


def test_tidy_state_is_remembered_per_controller(loaded, qapp, tmp_path):
    """Die Auswahl steht in der Anordnungsdatei und kommt zurueck."""
    app = loaded
    ui = app.ui
    left = ui.obah_view_left
    first = left.card_order()[0]
    left.toggle_compact(first)

    stored = json.load(open(app._obah_layout_file()))
    assert stored["oculus_touch:left"]["compact"] == [first]

    app._render_obah_views()                       # wie nach einem Neuaufbau
    assert ui.obah_view_left.is_compact(first)


def test_button_and_cards_stay_in_step(loaded, qapp):
    """Knopf schaltet beide Haende; Rechtsklick-Aenderungen stellen ihn nach."""
    app = loaded
    ui = app.ui
    btn = ui.btn_obah_tidy
    assert not btn.isChecked()

    btn.setChecked(True)
    assert ui.obah_view_left.is_tidy() and ui.obah_view_right.is_tidy()

    # eine einzelne Karte wieder hervorholen -> Knopf springt heraus
    ui.obah_view_left.toggle_compact(ui.obah_view_left.card_order()[0])
    assert not btn.isChecked()

    # und wieder verstecken -> Knopf rastet von selbst ein
    ui.obah_view_left.set_tidy(True)
    assert btn.isChecked()
    btn.setChecked(False)
    assert not ui.obah_view_left.is_tidy()


def test_reset_layout_also_brings_the_bindings_back(loaded, qapp):
    app = loaded
    ui = app.ui
    ui.btn_obah_tidy.setChecked(True)
    assert ui.obah_view_left.has_manual_layout()
    app.reset_obah_layout()
    assert not ui.obah_view_left.is_tidy()
    assert not ui.btn_obah_tidy.isChecked()


# --------------------------------------------------------------------------- #
#  points.json — Punkte passend zu den mitgelieferten Bildern (v1.3.2)
# --------------------------------------------------------------------------- #
def test_every_texture_input_has_a_point(qapp):
    """Jedes Bild mit Eintrag in points.json kennt alle Eingaben seiner Seite."""
    import ui.controller_view as cv
    cv.clear_texture_cache()
    for ct in ob.CONTROLLER_TYPES:
        sides = ("left", "right") if oe.is_handed(ct) else ("single",)
        for side in sides:
            tex = cv.texture_layout(ct, side)
            if tex is None:
                continue                    # altes Verfahren (Profilpunkte)
            pix, crop, pts = tex
            want = {d.path for d in oe.inputs_for_side(ct, side)}
            assert want <= set(pts), (ct, side, want - set(pts))
            for path in want:               # alles liegt auf dem sichtbaren Teil
                x, y = pts[path]
                assert crop.contains(x, y), (ct, side, path, (x, y))


def test_points_follow_the_texture(qapp):
    """Mit points.json sitzen die Punkte im Bildrechteck, an der Bildstelle."""
    import ui.controller_view as cv
    cv.clear_texture_cache()
    view = cv.ControllerBindingView()
    views = [oe.InputView(input=d) for d in oe.inputs_for_side("knuckles", "left")]
    view.resize(900, 600)
    view.set_data("knuckles", "left", views, {"title": "L"})
    pix, crop, pts = cv.texture_layout("knuckles", "left")
    rect = view._img_rect
    assert abs(rect.width() / rect.height() - crop.width() / crop.height()) < 0.01
    for i in range(view.card_count()):
        path = view._layout[i][2].input.path
        pt = view.point_of(i)
        assert rect.adjusted(-1, -1, 1, 1).contains(pt), path
        k = rect.width() / crop.width()
        assert abs(pt.x() - (rect.left() + (pts[path][0] - crop.left()) * k)) < 0.5


def test_mirrored_generic_texture_mirrors_points(qapp, tmp_path, monkeypatch):
    """Nur ein Bild ohne Seite: rechts wird es samt Punkten gespiegelt."""
    from PySide6.QtGui import QColor, QImage
    import ui.controller_view as cv
    img = QImage(200, 100, QImage.Format_ARGB32)
    img.fill(QColor(20, 30, 40, 255))
    img.save(str(tmp_path / "knuckles.png"))
    (tmp_path / "points.json").write_text(json.dumps(
        {"knuckles": {"size": [200, 100], "points": {"/input/trigger": [20, 50]}}}))
    monkeypatch.setattr(cv, "texture_dirs", lambda: [str(tmp_path)])
    cv.clear_texture_cache()
    assert cv.texture_layout("knuckles", "left")[2]["/input/trigger"] == (20, 50)
    assert cv.texture_layout("knuckles", "right")[2]["/input/trigger"] == (180, 50)


def test_wrong_aspect_ignores_points(qapp, tmp_path, monkeypatch):
    """Eigenes Bild mit anderem Seitenverhaeltnis: Punkte aus dem Profil."""
    from PySide6.QtGui import QColor, QImage
    import ui.controller_view as cv
    img = QImage(300, 100, QImage.Format_ARGB32)
    img.fill(QColor(20, 30, 40, 255))
    img.save(str(tmp_path / "knuckles_left.png"))
    (tmp_path / "points.json").write_text(json.dumps(
        {"knuckles_left": {"size": [100, 100], "points": {"/input/trigger": [20, 50]}}}))
    monkeypatch.setattr(cv, "texture_dirs", lambda: [str(tmp_path)])
    cv.clear_texture_cache()
    assert cv.texture_layout("knuckles", "left") is None


def _pair(ct):
    from ui.controller_view import ControllerBindingView, ControllerPair
    left, right = ControllerBindingView(), ControllerBindingView()
    pair = ControllerPair(left, right)
    pair.resize(1300, 600)
    for v, side in ((left, "left"), (right, "right")):
        v.set_data(ct, side, [oe.InputView(input=d) for d in oe.inputs_for_side(ct, side)],
                   {"title": side})
    pair.show()                  # versteckt kommen keine resizeEvents an
    pair.relayout()
    return pair, left, right


def test_left_and_right_same_size_and_mirrored(qapp):
    for ct in ("oculus_touch", "knuckles", "vive_controller", "vive_focus3_controller"):
        pair, left, right = _pair(ct)
        assert left._img_rect.size() == right._img_rect.size(), ct
        # gleicher Abstand zur Mitte
        gap_l = left.width() - left._img_rect.right()
        gap_r = right._img_rect.left()
        assert abs(gap_l - gap_r) < 1, (ct, gap_l, gap_r)


def test_controller_stops_at_the_middle_and_mirrors(qapp):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    pair, left, right = _pair("knuckles")
    saved = []
    right.layout_changed.connect(saved.append)
    c = left._img_rect.center()
    steps = ((QEvent.MouseButtonPress, c, left.mousePressEvent),
             (QEvent.MouseMove, c + QPointF(10, 0), left.mouseMoveEvent),
             (QEvent.MouseMove, c + QPointF(500, 40), left.mouseMoveEvent),
             (QEvent.MouseButtonRelease, c + QPointF(500, 40), left.mouseReleaseEvent))
    for typ, pos, fn in steps:
        btns = Qt.NoButton if typ == QEvent.MouseButtonRelease else Qt.LeftButton
        fn(QMouseEvent(typ, pos, pos, Qt.LeftButton, btns, Qt.NoModifier))
    assert left._img_rect.right() <= left.width() + 0.5          # nicht ueber die Wand
    assert right._img_rect.left() >= -0.5
    assert abs(left._img_rect.top() - right._img_rect.top()) < 0.5   # gespiegelt mit
    assert saved and saved[-1]["image"] is not None                  # Gegenseite gemerkt


def test_both_controllers_on_same_height_with_different_cards(qapp):
    """Mehr/laengere Karten auf einer Seite duerfen den Controller nicht versetzen."""
    from ui.controller_view import ControllerBindingView, ControllerPair
    for ct in ("oculus_touch", "vive_controller", "vive_focus3_controller"):
        left, right = ControllerBindingView(), ControllerBindingView()
        pair = ControllerPair(left, right)
        pair.resize(1300, 600)
        pair.show()
        left.set_data(ct, "left", [oe.InputView(input=d)
                                   for d in oe.inputs_for_side(ct, "left")], {})
        right.set_data(ct, "right", [oe.InputView(input=d)
                                     for d in oe.inputs_for_side(ct, "right")[:2]], {})
        # alte, versetzte Anordnung: nur rechts verschoben
        right.set_layout({"image": [0, 80]})
        pair.sync_mirror()
        pair.relayout()
        assert abs(left._img_rect.top() - right._img_rect.top()) < 0.5, ct
        assert left._img_rect.size() == right._img_rect.size(), ct


def _drag_card(view, idx, delta):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    c = view.card_rect(idx).center()
    for typ, pos, fn in ((QEvent.MouseButtonPress, c, view.mousePressEvent),
                         (QEvent.MouseMove, c + QPointF(8, 0), view.mouseMoveEvent),
                         (QEvent.MouseMove, c + delta, view.mouseMoveEvent),
                         (QEvent.MouseButtonRelease, c + delta, view.mouseReleaseEvent)):
        btns = Qt.NoButton if typ == QEvent.MouseButtonRelease else Qt.LeftButton
        fn(QMouseEvent(typ, pos, pos, Qt.LeftButton, btns, Qt.NoModifier))


def test_card_can_go_to_outer_column_and_back(qapp):
    from PySide6.QtCore import QPointF
    pair, left, right = _pair("oculus_touch")
    first = left.card_order()[0]
    _drag_card(left, 0, QPointF(-240, 0))            # nach aussen
    assert left.is_outer(first)
    order = left.card_order()
    idx = order.index(first)
    inner = next(i for i, p in enumerate(order) if not left.is_outer(p))
    assert left.card_rect(idx).right() < left.card_rect(inner).left()  # links daneben
    assert list(left.layout_state()["outer"]) == [first]
    assert left.has_manual_layout()
    # Anordnung merken und wiederherstellen
    state = left.layout_state()
    left.set_layout({})
    assert not left.is_outer(first)
    left.set_layout(state)
    assert left.is_outer(first)
    # zurueck in die innere Spalte
    idx = left.card_order().index(first)
    _drag_card(left, idx, QPointF(240, 0))
    assert not left.is_outer(first)


def test_combo_ignores_mouse_wheel(qapp):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication, QComboBox, QWidget
    from ui import no_wheel
    no_wheel.install(QApplication.instance())
    host = QWidget()
    combo = QComboBox(host)
    combo.addItems(["a", "b", "c"])
    combo.setCurrentIndex(0)
    host.show()
    ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
                     Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(combo, ev)
    assert combo.currentIndex() == 0


def test_outer_column_free_height_without_overlap(qapp):
    """Aussen stehen Karten frei in der Hoehe — nicht nach oben gezwungen."""
    from PySide6.QtCore import QPointF
    pair, left, right = _pair("oculus_touch")

    def rect(path):
        return left.card_rect(left.card_order().index(path))

    grip_inner = rect("/input/grip")
    _drag_card(left, left.card_order().index("/input/grip"), QPointF(-240, 0))
    assert left.is_outer("/input/grip")
    assert abs(rect("/input/grip").top() - grip_inner.top()) < 2     # bleibt unten
    # zweite Karte knapp darueber: rutscht darunter/darueber, ueberlappt nie
    y = left.card_order().index("/input/y")
    target = rect("/input/grip").top() - rect("/input/y").top() - 10
    _drag_card(left, y, QPointF(-240, target))
    a, b = rect("/input/grip"), rect("/input/y")
    assert not a.intersects(b)
    # gemerkt und wiederhergestellt
    state = left.layout_state()
    left.set_layout({})
    left.set_layout(state)
    assert abs(rect("/input/grip").top() - a.top()) < 0.5
    assert abs(rect("/input/y").top() - b.top()) < 0.5
    # aeltere Form (Liste) laedt weiter: von oben gestapelt
    left.set_layout({"outer": ["/input/grip"]})
    assert left.is_outer("/input/grip")
