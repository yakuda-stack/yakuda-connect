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


# --------------------------------------------------------------------------- #
#  „Kippen = Druecken“
# --------------------------------------------------------------------------- #
TILT_STATE = {
    "actions": [{"name": "select", "type": 1, "hands": ["left", "right"], "description": "Select"},
                {"name": "turn", "type": 2, "hands": ["left"], "description": "Turn"}],
    "bindings": {"select": [L + "thumbstick/click"]},
    "sources": {"thumbstick_click": [L + "thumbstick/click"],
                "thumbstick_x": [L + "thumbstick/x"], "thumbstick_y": [L + "thumbstick/y"]},
}


def test_tilt_only_for_bool_on_stick_click():
    sel = xr.action_by_name(TILT_STATE, "select")
    turn = xr.action_by_name(TILT_STATE, "turn")
    assert xr.tilt_capable(TILT_STATE, sel, "left", "thumbstick/click")
    assert not xr.tilt_capable(TILT_STATE, turn, "left", "thumbstick/click")
    assert not xr.tilt_capable(TILT_STATE, sel, "left", "x/click")
    # rechts liefert das Profil keinen Stick -> kein Kippen
    assert not xr.tilt_capable(TILT_STATE, sel, "right", "thumbstick/click")


def test_tilt_on_default_is_not_moved_and_off_removes_mapping():
    sel = xr.action_by_name(TILT_STATE, "select")
    maps = {}
    xr.set_tilt(TILT_STATE, maps, sel, "left", "left", True)
    assert maps[("select", "left")]["tilt"] is True
    assert maps[("select", "left")]["source"] == "thumbstick_click"
    assert xr.has_tilt(maps, "select", "left")
    assert xr.on_path(TILT_STATE, maps, L + "thumbstick/click") == [(sel, "left", False)]
    xr.set_tilt(TILT_STATE, maps, sel, "left", "left", False)
    assert maps == {}


def test_tilt_label_on_card():
    sel = xr.action_by_name(TILT_STATE, "select")
    maps = {}
    xr.set_tilt(TILT_STATE, maps, sel, "left", "left", True)
    views = xr.build_views("oculus_touch", "left", TILT_STATE, maps, tilt_label="+ Kippen")
    labels = [b.label for v in views for sb in v.bindings for b in sb.inputs]
    assert "Select  (+ Kippen)" in labels


def test_tilt_written_as_axis_expression():
    ini = xb.render_config([{"action": "select", "hand": "left", "source": "thumbstick_click",
                             "source_hand": "left", "tilt": True}])
    assert "map = thumbstick_click.left" in ini
    assert ("axis1 = step(0.5, thumbstick_click.left + step(0.5, sqrt("
            "thumbstick_x.left * thumbstick_x.left + thumbstick_y.left * thumbstick_y.left)))") in ini
    # max()/min() sind in xrBinder vertauscht — nicht benutzen
    assert "max(" not in ini and "min(" not in ini
    # ohne Kippen keine Achs-Zeile
    assert "axis1" not in xb.render_config([{"action": "select", "hand": "left",
                                             "source": "thumbstick_click", "source_hand": "left"}])
    # Kippen nur fuer den Stick-Klick
    assert xb.tilt_expression("x_click", "left") is None


def test_tilt_threshold_against_drift():
    sel = xr.action_by_name(TILT_STATE, "select")
    maps = {}
    xr.set_tilt_threshold(maps, "select", "left", 0.8)          # ohne Kippen: nichts
    assert maps == {}
    xr.set_tilt(TILT_STATE, maps, sel, "left", "left", True)
    assert xr.tilt_threshold(maps, "select", "left") == 0.5
    xr.set_tilt_threshold(maps, "select", "left", 0.75)
    assert maps[("select", "left")]["tilt_threshold"] == 0.75
    ini = xb.render_config(xr.mappings_to_list(maps))
    assert "step(0.5, thumbstick_click.left + step(0.75, sqrt(" in ini
    # Grenzen und Standard
    xr.set_tilt_threshold(maps, "select", "left", 5)
    assert maps[("select", "left")]["tilt_threshold"] == xb.TILT_MAX
    xr.set_tilt_threshold(maps, "select", "left", 0.5)
    assert "tilt_threshold" not in maps[("select", "left")]
    assert xb.clamp_threshold("kaputt") == xb.TILT_THRESHOLD
    assert xb.clamp_threshold(float("nan")) == xb.TILT_THRESHOLD
    # Kippen aus: Schwelle weg
    xr.set_tilt_threshold(maps, "select", "left", 0.9)
    xr.set_tilt(TILT_STATE, maps, sel, "left", "left", False)
    assert maps == {}


# --------------------------------------------------------------------------- #
#  xrizer unter WiVRn: Runtime meldet keine Tasten (echter Stand von Gal*Gun 2)
# --------------------------------------------------------------------------- #
def _galgun_state():
    import json
    path = os.path.join(os.path.dirname(__file__), "data", "xrizer_galgun2_state.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_xrizer_default_layout_filled_in():
    st = _galgun_state()
    assert st["bindings"] == {} and not any(st["sources"].values())
    assert xb.fill_known_bindings(st)
    assert st["bindings"]["main-joystick-click"] == [L + "thumbstick/click",
                                                     "/user/hand/right/input/thumbstick/click"]
    assert st["bindings"]["a"] == [L + "x/click", "/user/hand/right/input/a/click"]
    assert "haptic" not in st["bindings"]
    # echte Zuordnungen werden nie ueberschrieben
    assert not xb.fill_known_bindings(STATE)


def test_xrizer_stick_click_card_offers_tilt():
    st = _galgun_state()
    xb.fill_known_bindings(st)
    ct = xr.detect_controller(st)
    assert ct == "oculus_touch"
    views = xr.build_views(ct, "left", st, {})
    labels = [b.label for v in views for sb in v.bindings for b in sb.inputs]
    assert "Main Joystick Click" in labels and "Application Menu" in labels
    click = xr.action_by_name(st, "main-joystick-click")
    # Runtime nennt keine Quellen -> nichts sperren, Kippen anbieten
    assert xr.tilt_capable(st, click, "left", "thumbstick/click")
    maps = {}
    xr.set_tilt(st, maps, click, "left", "left", True)
    ini = xb.render_config(xr.mappings_to_list(maps))
    assert "main-joystick-click.left = yc_1" in ini and "axis1 = step(" in ini


# --------------------------------------------------------------------------- #
#  Deadzone fuer Sticks (gegen Drift)
# --------------------------------------------------------------------------- #
DZ_STATE = {
    "actions": [{"name": "move", "type": 3, "hands": ["left", "right"], "description": "Move"},
                {"name": "look", "type": 3, "hands": [""], "description": "Look"},
                {"name": "both", "type": 3, "hands": [""], "description": "Both sticks"},
                {"name": "jump", "type": 1, "hands": ["left"], "description": "Jump"}],
    "bindings": {"move": [L + "thumbstick"],
                 "look": [L + "thumbstick"],
                 "both": [L + "thumbstick", "/user/hand/right/input/thumbstick"],
                 "jump": [L + "thumbstick/click"]},
    "sources": {},
}


def test_deadzone_only_for_stick_directions():
    a = lambda n: xr.action_by_name(DZ_STATE, n)  # noqa: E731
    assert xr.deadzone_capable(DZ_STATE, a("move"), "left", "thumbstick")
    assert not xr.deadzone_capable(DZ_STATE, a("jump"), "left", "thumbstick/click")
    assert not xr.deadzone_capable(DZ_STATE, a("move"), "left", "trackpad")
    # ohne Hand, nur links gebunden: geht
    assert xr.deadzone_capable(DZ_STATE, a("look"), "left", "thumbstick")
    # ohne Hand, auf beiden Sticks: nicht (sonst bekaeme rechts den linken Stick)
    assert not xr.deadzone_capable(DZ_STATE, a("both"), "left", "thumbstick")
    # Runtime nennt Quellen, aber kein thumbstick_x -> nicht anbieten
    st = dict(DZ_STATE, sources={"thumbstick": [L + "thumbstick"]})
    assert not xr.deadzone_capable(st, a("move"), "left", "thumbstick")


def test_deadzone_on_off_and_value():
    move = xr.action_by_name(DZ_STATE, "move")
    maps = {}
    xr.set_deadzone(DZ_STATE, maps, move, "left", "left", True)
    m = maps[("move", "left")]
    assert m["source"] == "thumbstick" and m["source_hand"] == "left"
    assert m["deadzone"] == xb.DEADZONE_DEFAULT
    assert xr.has_deadzone(maps, "move", "left")
    # liegt auf dem Standard-Platz -> nicht als verschoben markiert
    assert xr.on_path(DZ_STATE, maps, L + "thumbstick")[0] == (move, "left", False)
    xr.set_deadzone_value(maps, "move", "left", 0.3)
    assert xr.deadzone_value(maps, "move", "left") == 0.3
    xr.set_deadzone_value(maps, "move", "left", 9)
    assert m["deadzone"] == xb.DEADZONE_MAX
    xr.set_deadzone_value(maps, "move", "left", 0)
    assert m["deadzone"] == xb.DEADZONE_MIN
    # Regler ohne Deadzone: nichts
    xr.set_deadzone_value(maps, "move", "right", 0.3)
    assert ("move", "right") not in maps
    xr.set_deadzone(DZ_STATE, maps, move, "left", "left", False)
    assert maps == {}


def test_deadzone_on_moved_stick_keeps_mapping():
    move = xr.action_by_name(DZ_STATE, "move")
    maps = {("move", "left"): {"action": "move", "hand": "left", "source": "thumbstick",
                               "source_hand": "right"}}
    xr.set_deadzone(DZ_STATE, maps, move, "left", "right", True)
    xr.set_deadzone(DZ_STATE, maps, move, "left", "right", False)
    assert maps[("move", "left")]["source_hand"] == "right"
    assert "deadzone" not in maps[("move", "left")]


def test_deadzone_label_on_card():
    move = xr.action_by_name(DZ_STATE, "move")
    maps = {}
    xr.set_deadzone(DZ_STATE, maps, move, "left", "left", True)
    views = xr.build_views("oculus_touch", "left", DZ_STATE, maps, deadzone_label="Deadzone")
    labels = [b.label for v in views for sb in v.bindings for b in sb.inputs]
    assert "Move  (Deadzone 15 %)" in labels


def test_deadzone_written_as_axis_expressions():
    ini = xb.render_config([{"action": "move", "hand": "left", "source": "thumbstick",
                             "source_hand": "left", "deadzone": 0.2}])
    gate = "step(0.2, sqrt(thumbstick_x.left * thumbstick_x.left + thumbstick_y.left * thumbstick_y.left))"
    assert "map = thumbstick.left" in ini
    assert f"axis1 = thumbstick_x.left * {gate}" in ini
    assert f"axis2 = thumbstick_y.left * {gate}" in ini
    assert "max(" not in ini and "min(" not in ini
    # ohne Deadzone keine Achs-Zeilen
    assert "axis" not in xb.render_config([{"action": "move", "hand": "left",
                                            "source": "thumbstick", "source_hand": "left"}])
    # nur fuer Sticks
    assert xb.deadzone_expressions("trackpad", "left") is None
    assert xb.deadzone_expressions("thumbstick", "") is None
    assert xb.clamp_deadzone("kaputt") == xb.DEADZONE_DEFAULT
    assert xb.clamp_deadzone(float("nan")) == xb.DEADZONE_DEFAULT


def test_xrizer_main_joystick_offers_deadzone():
    st = _galgun_state()
    xb.fill_known_bindings(st)
    joy = xr.action_by_name(st, "main-joystick")
    assert xr.deadzone_capable(st, joy, "right", "thumbstick")
    maps = {}
    xr.set_deadzone(st, maps, joy, "right", "right", True)
    ini = xb.render_config(xr.mappings_to_list(maps))
    assert "main-joystick.right = yc_1" in ini
    assert "axis2 = thumbstick_y.right * step(0.15, sqrt(" in ini


def test_stick_deadzone_for_all_directions_on_stick():
    st = {"actions": [{"name": "move", "type": 3, "hands": ["left", "right"]},
                      {"name": "turn", "type": 3, "hands": ["right"]},
                      {"name": "jump", "type": 1, "hands": ["left"]}],
          "bindings": {"move": [L + "thumbstick"], "turn": ["/user/hand/right/input/thumbstick"],
                       "jump": [L + "thumbstick/click"]},
          "sources": {}}
    maps = {}
    assert xr.stick_deadzone(st, maps, "left") == 0.0
    assert xr.set_stick_deadzone(st, maps, "left", 0.25) == 1
    assert list(maps) == [("move", "left")]
    assert xr.stick_deadzone(st, maps, "left") == 0.25
    assert xr.set_stick_deadzone(st, maps, "right", 0.1) == 1
    assert maps[("turn", "right")]["deadzone"] == 0.1
    xr.set_stick_deadzone(st, maps, "left", 0)
    assert list(maps) == [("turn", "right")]


def test_axis_changed_detects_deadzone_and_tilt():
    a = [{"action": "move", "hand": "left", "source": "thumbstick", "deadzone": 0.2}]
    b = [{"action": "move", "hand": "left", "source": "thumbstick", "deadzone": 0.3}]
    c = [{"action": "menu", "hand": "left", "source": "x_click"}]
    assert xb.axis_changed(a, b)
    assert xb.axis_changed(a, [])
    assert not xb.axis_changed(a, a + c)
    assert not xb.axis_changed([], c)
    assert xb.axis_changed(c, [dict(c[0], tilt=True)])


# --------------------------------------------------------------------------- #
#  OpenXR-Vorlage (Spiel meldet keine Tasten, z. B. VRChat ueber xrizer)
# --------------------------------------------------------------------------- #
LR = ["left", "right"]
EMPTY = {
    "actions": [
        {"name": "global_in_jump", "type": 1, "hands": LR, "description": "Jump"},
        {"name": "global_in_use", "type": 1, "hands": LR, "description": "Use"},
        {"name": "global_in_grab", "type": 1, "hands": LR, "description": "Grab"},
        {"name": "global_in_move", "type": 3, "hands": LR, "description": "Move"},
        {"name": "global_in_lookhorizontal", "type": 2, "hands": LR,
         "description": "Look Horizontal"},
        {"name": "global_in_menu", "type": 1, "hands": LR, "description": "Menu"},
        {"name": "oculustouch_left_x_click", "type": 1, "hands": LR,
         "description": "Oculus Touch (L) X Press"},
        {"name": "global_in_mystery", "type": 1, "hands": LR, "description": "Something"},
        {"name": "aim", "type": 4, "hands": ["left"], "description": "Aim pose"},
    ],
    "bindings": {},
}


def test_template_only_offered_when_nothing_bound():
    assert xr.template_offered("oculus_touch", EMPTY, {})
    assert not xr.template_offered("oculus_touch", STATE, {})       # Wanderer: Tasten gemeldet
    assert not xr.template_offered("oculus_touch", {"actions": []}, {})
    m, _, _ = xr.template_mappings(EMPTY)
    assert not xr.template_offered("oculus_touch", EMPTY, m)        # schon angewendet


def test_template_assigns_common_layout():
    m, matched, total = xr.template_mappings(EMPTY, "oculus_touch")
    src = {k: (v["source"], v["source_hand"]) for k, v in m.items()}
    assert src[("global_in_jump", "right")] == ("a_click", "right")
    assert ("global_in_jump", "left") not in src
    assert src[("global_in_use", "left")] == ("trigger_value_b", "left")
    assert src[("global_in_use", "right")] == ("trigger_value_b", "right")
    assert src[("global_in_grab", "right")] == ("squeeze_value_b", "right")
    assert src[("global_in_move", "left")] == ("thumbstick", "left")
    assert src[("global_in_lookhorizontal", "right")] == ("thumbstick_x", "right")
    assert src[("global_in_menu", "left")] == ("menu_click", "left")
    assert ("global_in_menu", "right") not in src                    # System rechts bleibt frei
    assert src[("oculustouch_left_x_click", "left")] == ("x_click", "left")
    assert not any(k[0] == "global_in_mystery" for k in src)
    assert (matched, total) == (7, 8)                               # Pose zaehlt nicht
    bound, _ = xr.counts("oculus_touch", EMPTY, m)
    assert bound > 0


def test_template_uses_fallback_buttons_on_other_controllers():
    m, _, _ = xr.template_mappings(EMPTY, "knuckles")
    src = {k: (v["source"], v["source_hand"]) for k, v in m.items()}
    assert src[("oculustouch_left_x_click", "left")] == ("a_click", "left")   # Index: A statt X
    m, _, _ = xr.template_mappings(EMPTY, "vive_controller")
    src = {k: (v["source"], v["source_hand"]) for k, v in m.items()}
    assert src[("global_in_move", "left")] == ("trackpad", "left")           # Vive: Trackpad
