#!/usr/bin/env python3
"""Tests fuer ui/xr_button_dialog.py — Tab „Deadzone“ im Stick-Dialog."""
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "core"))

import pytest  # noqa: E402

import xr_bindings as xr  # noqa: E402

L = "/user/hand/left/input/"
R = "/user/hand/right/input/"
STATE = {
    "actions": [{"name": "move", "type": 3, "hands": ["left", "right"], "description": "Move"},
                {"name": "menu", "type": 1, "hands": ["left"], "description": "Menu"}],
    "bindings": {"move": [L + "thumbstick", R + "thumbstick"], "menu": [L + "x/click"]},
    "sources": {},
}


def _open(path, side="left"):
    from ui.xr_button_dialog import XrButtonDialog
    d = next(i for i in xr.card_inputs("oculus_touch", side) if i.path == path)
    return XrButtonDialog(None, controller_type="oculus_touch", side=side, input_def=d,
                          state=STATE, mappings={}, game="Test")


@pytest.fixture
def stick(qapp):
    dlg = _open("/input/joystick")
    yield dlg
    dlg.deleteLater()


def test_tabs_only_on_stick(qapp):
    dlg = _open("/input/x")
    assert dlg.tabs is None and dlg.dz_panel is None
    dlg.deleteLater()


def test_deadzone_tab_sliders(stick):
    assert stick.tabs.count() == 2
    stick.tabs.setCurrentIndex(1)
    assert not stick.panel.isVisibleTo(stick) and stick.dz_panel.isVisibleTo(stick)
    rows = stick.dz_rows
    assert rows["left"]["slider"].value() == 0
    assert rows["left"]["value"].text() in ("Aus", "Off")
    rows["left"]["slider"].setValue(20)
    assert stick.mappings[("move", "left")]["deadzone"] == 0.2
    assert ("move", "right") not in stick.mappings
    assert rows["both"]["value"].text() == "≠"
    # Beide setzt beide gleich
    rows["both"]["slider"].setValue(30)
    assert stick.mappings[("move", "left")]["deadzone"] == 0.3
    assert stick.mappings[("move", "right")]["deadzone"] == 0.3
    assert rows["right"]["slider"].value() == 30
    # zu klein -> Minimum
    rows["right"]["slider"].setValue(2)
    assert stick.mappings[("move", "right")]["deadzone"] == 0.05
    # ↺ links: aus, rechts bleibt
    rows["left"]["reset"].click()
    assert ("move", "left") not in stick.mappings
    assert stick.mappings[("move", "right")]["deadzone"] == 0.05
    rows["both"]["reset"].click()
    assert stick.mappings == {}


def test_deadzone_tab_names_affected_actions(stick):
    assert "Move" in stick.dz_rows["left"]["info"].text()
