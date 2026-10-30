#!/usr/bin/env python3
"""Tests: Deadzone in der OpenVR-Ansicht (wird in xrBinder geschrieben)."""
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "core"))

import obah_bindings as ob  # noqa: E402
import obah_editor as oe  # noqa: E402
import xr_openvr_link as link  # noqa: E402

L = "/user/hand/left/input/"
R = "/user/hand/right/input/"
STATE = {
    "actions": [{"name": "move", "type": 3, "hands": ["left", "right"], "description": "Move"}],
    "bindings": {"move": [L + "thumbstick", R + "thumbstick"]},
    "sources": {},
}


def _game(folder):
    return ob.ObahGame(name="Test", appid="123", game_folder=str(folder), actions_json="x.json")


def test_find_app_by_exe(tmp_path, monkeypatch):
    monkeypatch.setattr(link.xb, "state_dir", lambda: str(tmp_path / "state"))
    (tmp_path / "game" / "bin").mkdir(parents=True)
    (tmp_path / "game" / "bin" / "MyGame.exe").write_text("")
    assert link.find_app(_game(tmp_path / "game"), ["Other", "MyGame"]) == "MyGame"


def test_find_app_unreal_path(tmp_path, monkeypatch):
    monkeypatch.setattr(link.xb, "state_dir", lambda: str(tmp_path / "state"))
    p = tmp_path / "game" / "GG" / "Binaries" / "Win64"
    p.mkdir(parents=True)
    (p / "GG-Win64-Shipping.exe").write_text("")
    name = "GG/Binaries/Win64/GG-Win64-Shipping"
    assert link.find_app(_game(tmp_path / "game"), [name]) == name


def test_find_app_none(tmp_path, monkeypatch):
    monkeypatch.setattr(link.xb, "state_dir", lambda: str(tmp_path / "state"))
    (tmp_path / "game").mkdir()
    assert link.find_app(_game(tmp_path / "game"), ["Nope"]) is None


def _dialog(dz):
    from ui.binding_dialog import BindingDialog
    d = next(i for i in oe.inputs_for_side("oculus_touch", "left") if i.type == "joystick")
    return BindingDialog(None, manifest={}, binding={}, controller_type="oculus_touch",
                         set_name="/actions/main", set_label="Main", input_def=d,
                         side="left", drafts=[], deadzone=dz)


def test_joystick_dialog_has_deadzone_tab(qapp):
    before = {}
    dlg = _dialog({"state": STATE, "mappings": before, "game": "Test"})
    assert dlg.tabs is not None and dlg.tabs.count() == 2
    dlg.tabs.setCurrentIndex(1)
    assert dlg.dz_panel.isVisibleTo(dlg) and not dlg.bind_body.isVisibleTo(dlg)
    dlg.dz_rows["left"]["slider"].setValue(20)
    assert dlg.dz_mappings[("move", "left")]["deadzone"] == 0.2
    assert before == {}                      # Original bleibt unberuehrt
    dlg.deleteLater()


def test_joystick_dialog_note_without_app(qapp):
    dlg = _dialog({"note": "Spiel einmal starten"})
    assert dlg.tabs.count() == 2 and dlg.dz_mappings is None
    dlg.deleteLater()


NO_KEYS = {
    "actions": [{"name": "move", "type": 3, "hands": ["left", "right"], "description": "Move"},
                {"name": "jump", "type": 1, "hands": [], "description": "Jump"}],
    "bindings": {},
    "sources": {},
}


def test_template_button_unlocks_sliders(qapp):
    from ui.xr_deadzone_panel import DeadzonePanel
    maps = {}
    panel = DeadzonePanel(NO_KEYS, maps)
    assert not panel.rows["left"]["slider"].isEnabled()
    assert panel.btn_template.isVisibleTo(panel) or not panel.btn_template.isHidden()
    panel.btn_template.click()
    assert maps
    assert panel.btn_template.isHidden()
    assert panel.rows["left"]["slider"].isEnabled()
    panel.rows["left"]["slider"].setValue(20)
    assert maps[("move", "left")]["deadzone"] == 0.2
    panel.deleteLater()


def _stick_dialog(dz, drafts):
    from ui.binding_dialog import BindingDialog
    d = next(i for i in oe.inputs_for_side("oculus_touch", "left") if i.type == "joystick")
    m = oe.Manifest(path="", action_sets=[], actions={}, localization={})
    return BindingDialog(None, manifest=m, binding={}, controller_type="oculus_touch",
                         set_name="/actions/main", set_label="Main", input_def=d,
                         side="left", drafts=drafts, deadzone=dz)


def test_no_xrizer_writes_deadzone_pct(qapp):
    drafts = [{"path": "/user/hand/left/input/joystick", "mode": "joystick", "inputs": {}},
              {"path": "/user/hand/left/input/joystick", "mode": "button", "inputs": {}}]
    dlg = _stick_dialog({"state": STATE, "mappings": {}, "game": "T", "steamvr": False}, drafts)
    assert not dlg.dz_steamvr and dlg.dz_pct_box.isHidden()
    dlg.chk_steamvr.setChecked(True)
    assert dlg.dz_steamvr and dlg.dz_xr_box.isHidden()
    dlg.pct_slider.setValue(20)
    assert dlg.drafts[0]["parameters"]["deadzone_pct"] == "20"
    assert "parameters" not in dlg.drafts[1]
    assert dlg.dz_mappings == {}               # xrBinder bleibt unberuehrt
    dlg.pct_slider.setValue(0)
    assert "parameters" not in dlg.drafts[0]
    dlg.deleteLater()


def test_no_xrizer_preset_and_no_joystick_binding(qapp):
    dlg = _stick_dialog({"note": "x", "steamvr": True}, [])
    assert dlg.chk_steamvr.isChecked() and not dlg.pct_slider.isEnabled()
    dlg.deleteLater()


def _binding():
    L_, R_ = "/user/hand/left/input/joystick", "/user/hand/right/input/joystick"
    return {"bindings": {
        "/actions/global": {"sources": [
            {"path": L_, "mode": "joystick", "inputs": {}},
            {"path": R_, "mode": "joystick", "inputs": {}},
            {"path": L_, "mode": "button", "inputs": {}}]},
        "/actions/menu": {"sources": [{"path": L_, "mode": "joystick", "inputs": {}}]}}}


def test_stick_deadzone_pct_all_sets():
    b = _binding()
    assert oe.set_stick_deadzone_pct(b, "oculus_touch", "left", 25) == 2
    assert oe.stick_deadzone_pct(b, "oculus_touch", "left") == [25, 25]
    assert oe.stick_deadzone_pct(b, "oculus_touch", "right") == [0]
    oe.set_stick_deadzone_pct(b, "oculus_touch", "left", 0)
    assert "parameters" not in b["bindings"]["/actions/menu"]["sources"][0]


def test_deadzone_dialog_pct_and_xr(qapp):
    from ui.deadzone_dialog import DeadzoneDialog
    b = _binding()
    dlg = DeadzoneDialog(None, dz={"state": STATE, "mappings": {}, "game": "T", "steamvr": True},
                         game="T", binding=b, controller_type="oculus_touch")
    assert dlg.xr_box.isHidden() and not dlg.pct_box.isHidden()
    dlg.pct_rows["both"]["slider"].setValue(30)
    assert dlg.pct_changed and oe.stick_deadzone_pct(dlg.binding, "oculus_touch", "right") == [30]
    assert oe.stick_deadzone_pct(b, "oculus_touch", "right") == [0]     # Original unberuehrt
    dlg.chk_steamvr.setChecked(False)
    dlg.dz_rows["left"]["slider"].setValue(20)
    assert dlg.dz_mappings[("move", "left")]["deadzone"] == 0.2
    dlg.deleteLater()


def test_deadzone_dialog_xr_game_has_no_checkbox(qapp):
    from ui.deadzone_dialog import DeadzoneDialog
    dlg = DeadzoneDialog(None, dz={"state": STATE, "mappings": {}, "game": "T"}, game="T")
    assert dlg.chk_steamvr is None and dlg.pct_box is None
    dlg.deleteLater()


def test_tabbar_ignores_mouse_wheel(qapp):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QTabBar
    from ui import no_wheel
    no_wheel.install()
    bar = QTabBar()
    for t in ("Global", "One Hand", "Menu"):
        bar.addTab(t)
    ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
                     Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    bar.wheelEvent(ev)
    assert bar.currentIndex() == 0 and not ev.isAccepted()
    bar.deleteLater()
