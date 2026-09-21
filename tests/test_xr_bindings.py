#!/usr/bin/env python3
"""Tests fuer core/xr_bindings.py — OpenXR-Spiele in der Controller-Ansicht."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import xr_bindings as xr  # noqa: E402
import xrbinder as xb  # noqa: E402

L = "/user/hand/left/input/"

# So sieht Wanderer (Unreal) aus: je Taste eine Aktion, beide Haende angelegt,
# aber nur an einer Hand gebunden.
STATE = {
    "actions": [
        {"name": "oculustouch_left_x_click", "type": 1, "hands": ["left", "right"],
         "description": "Oculus Touch (L) X Press"},
        {"name": "oculustouch_left_menu_click", "type": 1, "hands": ["left", "right"],
         "description": "Oculus Touch (L) Menu"},
        {"name": "oculustouch_left_trigger_axis", "type": 2, "hands": ["left", "right"],
         "description": "Oculus Touch (L) Trigger Axis"},
        {"name": "aim", "type": 4, "hands": ["left"], "description": "Aim pose"},
    ],
    "bindings": {
        "oculustouch_left_x_click": [L + "x/click"],
        "oculustouch_left_menu_click": [L + "menu/click"],
        "oculustouch_left_trigger_axis": [L + "trigger/value"],
    },
    "sources": {"x_click": [L + "x/click"], "menu_click": [L + "menu/click"],
                "trigger_value": [L + "trigger/value"]},
}


def act(name):
    return xr.action_by_name(STATE, name)


def test_detect_controller():
    assert xr.detect_controller(STATE) == "oculus_touch"
    assert xr.detect_controller({"sources": {"trackpad_touch": ["x"], "a_click": ["x"]}}) == "knuckles"
    assert xr.detect_controller({}) == "oculus_touch"


def test_components_and_sources():
    assert xr.components("oculus_touch", "left", "x") == ["x/click", "x/touch"]
    assert xr.components("oculus_touch", "left", "a") == []          # A gibt es links nicht
    assert xr.source_for("x/click", 1) == "x_click"
    assert xr.source_for("x/click", 2) == "x_click_f"
    assert xr.source_for("trigger/value", 1) == "trigger_value_b"
    assert xr.source_for("x/touch", 2) is None
    assert xr.source_for("thumbstick", 3) == "thumbstick"
    assert xr.source_path("trigger_value_b", "right") == "/user/hand/right/input/trigger/value"
    assert xr.source_path(xb.OFF_SOURCE["bool"], "") is None


def test_cards_show_defaults_without_pose():
    views = {v.input.path: v for v in xr.build_views("oculus_touch", "left", STATE, {})}
    x = views["/input/x"]
    assert [b.mode for b in x.bindings] == ["click"]
    assert x.bindings[0].inputs[0].label == "Oculus Touch (L) X Press"
    assert views["/input/system"].bindings[0].inputs[0].action == "oculustouch_left_menu_click"
    assert "/input/a" not in views                    # A ist rechts
    right = {v.input.path: v for v in xr.build_views("oculus_touch", "right", STATE, {})}
    assert right["/input/a"].bindings == []           # rechts liegt nichts (nur links gebunden)


def test_move_menu_to_x_and_disable_x():
    """Der Fall aus dem Alltag: X soll das Menue oeffnen, X selbst nichts mehr."""
    m = {}
    assert xr.assign(STATE, m, act("oculustouch_left_menu_click"), "left", "x/click")
    xr.unassign(STATE, m, act("oculustouch_left_x_click"), "left", L + "x/click")
    on_x = [(a["name"], moved) for a, _h, moved in xr.on_path(STATE, m, L + "x/click")]
    assert on_x == [("oculustouch_left_menu_click", True)]
    assert xr.on_path(STATE, m, L + "menu/click") == []
    lst = xr.mappings_to_list(m)
    assert {"action": "oculustouch_left_menu_click", "hand": "left",
            "source": "x_click", "source_hand": "left"} in lst
    assert {"action": "oculustouch_left_x_click", "hand": "left",
            "source": xb.OFF_SOURCE["bool"], "source_hand": ""} in lst
    # Karte zeigt die umgelegte Funktion mit Pfeil
    views = {v.input.path: v for v in xr.build_views("oculus_touch", "left", STATE, m)}
    assert views["/input/x"].bindings[0].inputs[0].label.startswith(xr.MOVED_MARK)
    assert views["/input/system"].bindings == []


def test_unassign_moved_goes_back_home():
    m = {}
    xr.assign(STATE, m, act("oculustouch_left_menu_click"), "left", "x/click")
    xr.unassign(STATE, m, act("oculustouch_left_menu_click"), "left", L + "x/click")
    assert m == {}                                    # wieder auf dem Menue-Knopf
    assert xr.on_path(STATE, m, L + "menu/click")


def test_assign_back_to_default_removes_mapping():
    m = {}
    xr.assign(STATE, m, act("oculustouch_left_menu_click"), "left", "x/click")
    xr.assign(STATE, m, act("oculustouch_left_menu_click"), "left", "menu/click")
    assert m == {}


def test_type_mismatch_rejected():
    m = {}
    assert not xr.assign(STATE, m, act("oculustouch_left_trigger_axis"), "left", "x/touch")
    assert m == {}
    assert xr.assign(STATE, m, act("oculustouch_left_trigger_axis"), "left", "x/click")
    assert m[("oculustouch_left_trigger_axis", "left")]["source"] == "x_click_f"


def test_reset_button():
    m = {}
    xr.assign(STATE, m, act("oculustouch_left_menu_click"), "left", "x/click")
    xr.unassign(STATE, m, act("oculustouch_left_x_click"), "left", L + "x/click")
    x_paths = xr.card_paths("oculus_touch", "left", "/input/x")
    assert xr.has_changes_on(STATE, m, x_paths)
    xr.reset_paths(STATE, m, x_paths)
    assert m == {}
    assert not xr.has_changes_on(STATE, m, x_paths)


def test_roundtrip_and_counts():
    m = xr.mappings_from_list([{"action": "oculustouch_left_x_click", "hand": "left",
                                "source": xb.OFF_SOURCE["bool"], "source_hand": ""}])
    assert xr.on_path(STATE, m, L + "x/click") == []
    bound, total = xr.counts("oculus_touch", STATE, m)
    assert total > bound > 0
