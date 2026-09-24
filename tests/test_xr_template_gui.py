#!/usr/bin/env python3
"""
tests/test_xr_template_gui.py — Knopf „OpenXR-Vorlage verwenden“
================================================================
OpenXR-Spiel mit Aktionen, aber ohne gemeldete Tasten (wie VRChat ueber
xrizer): Knopf sichtbar -> Klick legt Umbelegungen an (ungespeichert) ->
Knopf verschwindet -> „Verwerfen“ -> Knopf wieder da.
"""
import os
import sys
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

LR = ["left", "right"]
ACTIONS = [
    {"name": "global_in_jump", "type": 1, "hands": LR, "description": "Jump"},
    {"name": "global_in_grab", "type": 1, "hands": LR, "description": "Grab"},
    {"name": "global_in_move", "type": 3, "hands": LR, "description": "Move"},
]


@pytest.fixture(scope="module")
def app(qapp, tmp_path_factory):
    home = tmp_path_factory.mktemp("home")
    os.environ["HOME"] = str(home)
    from PySide6.QtWidgets import QMessageBox
    for m in ("warning", "information", "critical"):
        setattr(QMessageBox, m, staticmethod(lambda *a, **k: QMessageBox.Ok))
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    from main import VRApp
    window = VRApp()
    yield window
    window.close()


def test_template_button_flow(app, monkeypatch):
    import xrbinder as xb
    monkeypatch.setattr(xb, "load_state", lambda name: {"actions": ACTIONS, "bindings": {}})
    monkeypatch.setattr(xb, "needs_rebuild", lambda: False)
    monkeypatch.setattr(app.ui.xrbinder_session, "request_dump", lambda name: None)
    monkeypatch.setattr(app.ui.xrbinder_card, "is_enabled", lambda: True)
    btn = app.ui.btn_xr_template

    app._xr_enter("VRChat")
    assert not btn.isHidden()
    assert "xrizer" in app.ui.lbl_obah_hint.text()

    btn.click()
    assert app._obah_dirty
    assert ("global_in_jump", "right") in app._xr_mappings
    assert btn.isHidden()
    assert "3" in app.ui.lbl_obah_editor_status.text()

    app.xr_discard()
    assert not app._xr_mappings
    assert not btn.isHidden()

    app._xr_leave()
    assert btn.isHidden()
