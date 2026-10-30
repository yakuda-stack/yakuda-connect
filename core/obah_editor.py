#!/usr/bin/env python3
"""
obah_editor.py — Daten fuer die Bindings-Ansicht im Controls-Tab
================================================================
Liest wie obahs "Edit Bindings"-Bildschirm (src/screens/edit_bindings.rs):

  * die Action Sets des Spiels (actions.json -> "action_sets") als Tabs,
  * je Controller-Seite alle Eingaben aus dem Controller-Profil,
  * und fuer jede Eingabe, was in der geladenen Binding-Datei darauf liegt
    ("Als Trigger: Ziehen -> Springen", ...).

Die Profil-Tabelle unten ist aus obahs profiles/*.json uebernommen
(obah, MIT-Lizenz, (c) galister) — nur die Angaben, die hier gebraucht
werden: Pfad, Typ, Seite, Faehigkeiten (click/touch/value/force),
Reihenfolge und der Bildpunkt (binding_image_point), an dem die Eingabe
auf dem Controllerbild liegt. Posen, Skelett und Vibration stehen mit in der
Tabelle: die Controller-Karten zeigen sie nicht (wie in obah), sie erscheinen
im Bereich "Posen, Haptik & Skelett" (siehe aux_sources).

Bearbeiten (Stand obah 0.1.1, SourceBindingModal): Bindings einer Eingabe
als Entwuerfe herausnehmen, Modus/Aktionen/Parameter aendern, zurueck-
schreiben, und die Datei als xrizer-, VapoR- oder OpenComposite-Binding
speichern. Die Regeln (welche Modi eine Eingabe kann, welche Aktionen zu
welchem Feld passen, bekannte Parameter) sind obahs Regeln.
"""
import copy
import json
import os
import shutil
from dataclasses import dataclass, field

from logging_setup import get_logger

log = get_logger("obah_editor")

# (pfad, typ, seite, faehigkeiten c=click t=touch v=value f=force, order, (x, y))
PROFILES = {
    "gamepad": {"ui_mode": "single_device", "inputs": [
        ("/input/a", "button", "", "c", 1, (174, 89)),
        ("/input/b", "button", "", "c", 2, (192, 73)),
        ("/input/back", "button", "", "c", 16, (130, 75)),
        ("/input/dpad_down", "button", "", "c", 11, (84, 117)),
        ("/input/dpad_left", "button", "", "c", 13, (71, 106)),
        ("/input/dpad_right", "button", "", "c", 14, (94, 106)),
        ("/input/dpad_up", "button", "", "c", 12, (84, 97)),
        ("/input/guide", "button", "", "c", 17, (113, 52)),
        ("/input/trigger_left", "trigger", "", "v", 7, (49, 13)),
        ("/input/trigger_right", "trigger", "", "v", 8, (176, 13)),
        ("/input/joystick_left", "joystick", "", "c", 5, (52, 84)),
        ("/input/joystick_right", "joystick", "", "c", 6, (145, 114)),
        ("/input/shoulder_left", "button", "", "c", 9, (50, 28)),
        ("/input/shoulder_right", "button", "", "c", 10, (177, 28)),
        ("/input/start", "button", "", "c", 15, (94, 75)),
        ("/input/x", "button", "", "c", 3, (159, 75)),
        ("/input/y", "button", "", "c", 4, (175, 60)),
    ]},
    "knuckles": {"ui_mode": "controller_handed", "inputs": [
        ("/input/system", "button", "", "ct", 1, (34, 45)),
        ("/input/a", "button", "", "ct", 6, (26, 42)),
        ("/input/b", "button", "", "ct", 5, (18, 37)),
        ("/input/trigger", "trigger", "", "ctv", 2, (11, 60)),
        ("/input/trackpad", "trackpad", "", "tf", 3, (27, 37)),
        ("/input/grip", "trigger", "", "tvf", 7, (47, 86)),
        ("/input/thumbstick", "joystick", "", "ct", 4, (31, 26)),
        ("/input/pinch", "pinch", "", "", 8, (27, 37)),
        ("/input/finger/index", "trigger", "", "", 100, (56, 86)),
        ("/input/finger/middle", "trigger", "", "", 101, (56, 86)),
        ("/input/finger/ring", "trigger", "", "", 102, (56, 86)),
        ("/input/finger/pinky", "trigger", "", "", 103, (56, 86)),
        ("/pose/raw", "pose", "", "", 99, (5, 35)),
        ("/pose/base", "pose", "", "", 99, (65, 136)),
        ("/pose/handgrip", "pose", "", "", 99, (56, 95)),
        ("/pose/grip", "pose", "", "", 99, (56, 95)),
        ("/pose/tip", "pose", "", "", 99, (5, 35)),
        ("/pose/gdc2015", "pose", "", "", 99, (5, 35)),
        ("/input/skeleton/left", "skeleton", "left", "", 99, (5, 35)),
        ("/input/skeleton/right", "skeleton", "right", "", 99, (5, 35)),
        ("/output/haptic", "vibration", "", "", 99, (5, 35)),
    ]},
    "oculus_touch": {"ui_mode": "controller_handed", "inputs": [
        ("/input/joystick", "joystick", "", "ct", 2, (54, 31)),
        ("/input/trigger", "trigger", "", "tv", 1, (22, 85)),
        ("/input/grip", "trigger", "", "tv", 3, (100, 86)),
        ("/input/a", "button", "right", "ct", 4, (70, 49)),
        ("/input/b", "button", "right", "ct", 5, (54, 55)),
        ("/input/x", "button", "left", "ct", 4, (70, 49)),
        ("/input/y", "button", "left", "ct", 5, (54, 55)),
        ("/input/system", "button", "left", "ct", 0, (72, 39)),
        ("/input/thumbrest", "button", "", "t", 99, (70, 65)),
        ("/input/skeleton/right", "skeleton", "right", "", 99, (11, 150)),
        ("/input/skeleton/left", "skeleton", "left", "", 99, (11, 150)),
        ("/output/haptic", "vibration", "", "", 99, (72, 39)),
        ("/pose/raw", "pose", "", "", 99, (14, 16)),
        ("/pose/base", "pose", "", "", 99, (11, 150)),
        ("/pose/handgrip", "pose", "", "", 99, (24, 86)),
        ("/pose/tip", "pose", "", "", 99, (14, 16)),
        ("/pose/openxr_aim", "pose", "", "", 99, (14, 16)),
        ("/pose/openxr_grip", "pose", "", "", 99, (24, 86)),
    ]},
    "rift": {"ui_mode": "hmd", "inputs": [
        ("/proximity", "button", "", "", 99, (60, 60)),
        ("/input/remote_dpad/down", "button", "", "", 99, (142, 48)),
        ("/input/remote_dpad/up", "button", "", "", 99, (142, 6)),
        ("/input/remote_dpad/left", "button", "", "", 99, (122, 25)),
        ("/input/remote_dpad/right", "button", "", "", 99, (162, 25)),
        ("/input/remote_dpad/enter", "button", "", "c", 99, (142, 25)),
        ("/input/remote_back", "button", "", "c", 99, (142, 64)),
        ("/input/tap", "button", "", "c", 99, (60, 60)),
        ("/pose/raw", "pose", "", "", 99, (105, 200)),
        ("/input/system", "button", "", "", 99, (180, 110)),
        ("/pose/raw", "pose", "", "", 99, (63, 148)),
    ]},
    "svl_hand_interaction_augmented": {"ui_mode": "controller_handed", "inputs": [
        ("/input/index_pinch", "trigger", "", "v", 1, (15, 25)),
        ("/input/middle_pinch", "trigger", "", "v", 1, (35, 6)),
        ("/input/ring_pinch", "trigger", "", "v", 1, (47, 8)),
        ("/input/pinky_pinch", "trigger", "", "v", 3, (57, 15)),
        ("/input/grip", "trigger", "", "v", 3, (45, 50)),
        ("/input/index_point", "trigger", "", "t", 99, (25, 10)),
        ("/input/skeleton/right", "skeleton", "right", "", 99, (40, 50)),
        ("/input/skeleton/left", "skeleton", "left", "", 99, (40, 50)),
        ("/input/system", "button", "left", "c", 0, (72, 39)),
        ("/pose/raw", "pose", "", "", 99, (14, 16)),
        ("/pose/grip", "pose", "", "", 99, (14, 16)),
        ("/pose/tip", "pose", "", "", 99, (14, 16)),
        ("/output/haptic", "vibration", "", "", 99, (5, 35)),
    ]},
    "vive_controller": {"ui_mode": "controller_handed", "inputs": [
        ("/input/trackpad", "trackpad", "", "ct", 2, (66, 59)),
        ("/input/trigger", "trigger", "", "cv", 1, (41, 64)),
        ("/input/grip", "button", "", "c", 3, (52, 87)),
        ("/input/application_menu", "button", "", "c", 4, (64, 35)),
        ("/input/system", "button", "", "c", 5, (67, 81)),
        ("/input/skeleton/right", "skeleton", "right", "", 99, (62, 16)),
        ("/input/skeleton/left", "skeleton", "left", "", 99, (62, 16)),
        ("/pose/raw", "pose", "", "", 99, (62, 16)),
        ("/pose/base", "pose", "", "", 99, (65, 150)),
        ("/pose/handgrip", "pose", "", "", 99, (52, 86)),
        ("/pose/grip", "pose", "", "", 99, (52, 86)),
        ("/pose/openxr_handmodel", "pose", "", "", 99, (52, 86)),
        ("/pose/openxr_handmodel_r", "pose", "", "", 99, (52, 86)),
        ("/pose/tip", "pose", "", "", 99, (62, 16)),
        ("/pose/front", "pose", "", "", 99, (62, 16)),
        ("/pose/gdc2015", "pose", "", "", 99, (62, 16)),
        ("/output/haptic", "vibration", "", "", 99, (66, 59)),
    ]},
    "vive_focus3_controller": {"ui_mode": "controller_handed", "inputs": [
        ("/input/joystick", "joystick", "", "ct", 1, (42, 18)),
        ("/input/trigger", "trigger", "", "ctv", 2, (37, 6)),
        ("/input/grip", "trigger", "", "ctv", 3, (20, 53)),
        ("/input/b", "button", "right", "ct", 4, (20, 23)),
        ("/input/a", "button", "right", "ct", 5, (27, 35)),
        ("/input/x", "button", "left", "ct", 6, (34, 33)),
        ("/input/y", "button", "left", "ct", 7, (25, 23)),
        ("/input/system", "button", "left", "ct", 0, (55, 33)),
        ("/input/skeleton/right", "skeleton", "right", "", 99, (25, 25)),
        ("/input/skeleton/left", "skeleton", "left", "", 99, (25, 25)),
        ("/output/haptic", "vibration", "", "", 99, (25, 25)),
        ("/pose/raw", "pose", "", "", 99, (25, 25)),
        ("/pose/base", "pose", "", "", 99, (25, 25)),
        ("/pose/handgrip", "pose", "", "", 99, (25, 25)),
        ("/pose/tip", "pose", "", "", 99, (25, 25)),
        ("/pose/openxr_aim", "pose", "", "", 99, (25, 25)),
    ]},
}



# --------------------------------------------------------------------------- #
#  Datenklassen
# --------------------------------------------------------------------------- #
@dataclass
class InputDef:
    path: str
    type: str
    side: str
    click: bool
    touch: bool
    value: bool
    force: bool
    order: int
    point: tuple

    @property
    def name(self):
        """obah: source_name_from_path — letzter Pfadteil, '_' -> ' '."""
        return short_path(self.path).replace("_", " ")


@dataclass
class ActionSet:
    name: str          # /actions/global
    usage: str         # single | leftright | hidden | ''
    label: str         # Anzeigename fuer den Tab


@dataclass
class BoundInput:
    """Eine Zeile unter einem Modus: 'Ziehen -> Springen'."""
    input: str
    action: str        # voller Aktionspfad oder ''
    label: str         # Anzeigename der Aktion oder ''


@dataclass
class SourceBinding:
    mode: str
    inputs: list = field(default_factory=list)       # [BoundInput]
    parameters: dict = field(default_factory=dict)


@dataclass
class InputView:
    """Alles, was die Ansicht fuer EINE Eingabe einer Seite braucht."""
    input: InputDef
    bindings: list = field(default_factory=list)     # [SourceBinding]

    @property
    def bound(self):
        """Mindestens eine Aktion liegt auf dieser Eingabe."""
        return any(i.action for b in self.bindings for i in b.inputs)


@dataclass
class Manifest:
    path: str
    action_sets: list          # [ActionSet]
    actions: dict              # {pfad_lower: (pfad, typ)}
    localization: dict         # {language_tag_lower: {pfad_lower: text}}


# --------------------------------------------------------------------------- #
#  Hilfen
# --------------------------------------------------------------------------- #
def short_path(path):
    """obah: short_path — letzter nicht-leerer Pfadteil."""
    parts = [p for p in (path or "").split("/") if p]
    return parts[-1] if parts else (path or "")


def profile_inputs(controller_type):
    prof = PROFILES.get(controller_type)
    if not prof:
        return []
    out = []
    for path, typ, side, flags, order, point in prof["inputs"]:
        out.append(InputDef(path=path, type=typ, side=side, click="c" in flags,
                            touch="t" in flags, value="v" in flags, force="f" in flags,
                            order=order, point=point))
    # obah: nach order, dann Name, dann Pfad
    out.sort(key=lambda d: (d.order, d.name, d.path))
    return out


def ui_mode(controller_type):
    return (PROFILES.get(controller_type) or {}).get("ui_mode", "controller_handed")


def is_handed(controller_type):
    return ui_mode(controller_type) == "controller_handed"


AUX_TYPES = ("pose", "skeleton", "vibration")
CHORD_TYPES = ("button", "trigger", "joystick", "trackpad", "pinch")


def inputs_for_side(controller_type, side):
    """
    obah: collect_source — bei controller_handed landen Eingaben mit
    side=left nur links, side=right nur rechts, ohne Seite auf beiden.
    side: 'left' | 'right' | 'single'
    """
    defs = [d for d in profile_inputs(controller_type) if d.type not in AUX_TYPES]
    if side == "single":
        return defs
    return [d for d in defs if not d.side or d.side == side]


def pretty_set_name(name):
    """'/actions/one_hand' -> 'One Hand', '/actions/ActionMenu' -> 'Action Menu'."""
    raw = short_path(name).replace("_", " ")
    out = ""
    for i, ch in enumerate(raw):
        if i and ch.isupper() and raw[i - 1].islower():
            out += " "
        out += ch
    return " ".join(w[:1].upper() + w[1:] for w in out.split())


# --------------------------------------------------------------------------- #
#  Laden
# --------------------------------------------------------------------------- #
def _read_json(path):
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def load_manifest(actions_json):
    """actions.json lesen. Wirft ValueError mit lesbarer Meldung bei Fehlern."""
    try:
        data = _read_json(actions_json)
    except (OSError, ValueError) as exc:
        raise ValueError(f"actions.json: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("actions.json: kein JSON-Objekt")

    loc = {}
    for entry in data.get("localization") or []:
        if isinstance(entry, dict) and entry.get("language_tag"):
            loc[entry["language_tag"].lower()] = {
                k.lower(): v for k, v in entry.items()
                if k != "language_tag" and isinstance(v, str)}

    actions = {}
    for a in data.get("actions") or []:
        if isinstance(a, dict) and a.get("name"):
            actions[a["name"].lower()] = (a["name"], a.get("type", ""))

    sets = []
    for s in data.get("action_sets") or []:
        if isinstance(s, dict) and s.get("name"):
            sets.append(ActionSet(name=s["name"], usage=(s.get("usage") or "").lower(),
                                  label=pretty_set_name(s["name"])))
    if not sets:
        raise ValueError("actions.json: keine Action Sets")
    return Manifest(path=actions_json, action_sets=sets, actions=actions, localization=loc)


def load_binding(path):
    """Binding-Datei lesen; None = leer ('Start from scratch' / fehlt)."""
    if not path:
        return {}
    try:
        data = _read_json(path)
    except (OSError, ValueError) as exc:
        raise ValueError(f"{os.path.basename(path)}: {exc}") from exc
    return data if isinstance(data, dict) else {}


def localized(manifest, path, lang="en"):
    """
    Anzeigename einer Aktion / eines Action Sets. Reihenfolge: Sprache der
    App (de -> de_de, de, ...), dann Englisch, dann letzter Pfadteil.
    """
    if not path:
        return ""
    key = path.lower()
    prefs = [t for t in manifest.localization if t.startswith(lang.lower())] \
        + [t for t in manifest.localization if t.startswith("en")]
    for tag in prefs:
        text = manifest.localization[tag].get(key)
        if text:
            return text
    canonical = manifest.actions.get(key, (path, ""))[0]
    return short_path(canonical)


def set_label(manifest, action_set, lang="en"):
    """Tab-Beschriftung: lokalisiert (falls vorhanden), '(L/R)' wie in obah."""
    text = localized(manifest, action_set.name, lang)
    if text == short_path(action_set.name):
        text = action_set.label
    return f"{text} (L/R)" if action_set.usage == "leftright" else text


def _set_bindings(binding, set_name):
    """obah: find_action_set_bindings — exakt, sonst ohne '/' am Ende und
    ohne Gross-/Kleinschreibung."""
    sets = binding.get("bindings") or {}
    if set_name in sets:
        return sets[set_name] or {}
    want = set_name.rstrip("/").lower()
    for k, v in sets.items():
        if k.rstrip("/").lower() == want:
            return v or {}
    return {}


def _matches(binding_path, profile_path, side):
    """obah: source_binding_matches."""
    b = (binding_path or "").lower()
    p = profile_path.lower()
    if not (b == p or b.endswith(p)):
        return False
    if side == "left":
        return "/left/" in b or b.startswith("/user/hand/left")
    if side == "right":
        return "/right/" in b or b.startswith("/user/hand/right")
    return True


def expected_inputs(d, mode):
    """obah: expected_inputs — welche Zeilen ein Modus fuer diese Eingabe hat."""
    if mode == "toggle_button":
        return ["toggle"]
    if mode == "button":
        return (["click"] if (d.click or d.value or d.force) else []) + (["touch"] if d.touch else [])
    if mode == "trigger":
        return (["pull"] if (d.value or d.force) else []) + (["click"] if d.click else []) \
            + (["touch"] if d.touch else [])
    if mode in ("joystick", "trackpad"):
        return ["position"] + (["click"] if d.click else []) + (["touch"] if d.touch else []) \
            + (["force"] if d.force else [])
    if mode == "dpad":
        return ["north", "south", "east", "west", "center"]
    if mode == "grab":
        return ["grab"] + (["value"] if d.value else []) + (["force"] if d.force else []) \
            + (["touch"] if d.touch else [])
    if mode == "scalar_constant":
        return ["value"]
    return []


def build_view(manifest, binding, controller_type, set_name, side, lang="en"):
    """
    Liste von InputView fuer eine Seite ('left' | 'right' | 'single') und ein
    Action Set — Reihenfolge wie im Profil (order).
    """
    sources = _set_bindings(binding, set_name).get("sources") or []
    out = []
    for d in inputs_for_side(controller_type, side):
        view = InputView(input=d)
        for src in sources:
            if not isinstance(src, dict) or not _matches(src.get("path"), d.path, side):
                continue
            mode = (src.get("mode") or "").lower()
            given = src.get("inputs") or {}
            # obah: display_inputs — bei toggle_button mit Eingaben nur die
            # vorhandenen, sonst die erwarteten plus alles Unbekannte
            names = [] if (mode == "toggle_button" and given) else expected_inputs(d, mode)
            names += [k for k in given if k not in names]
            rows = []
            for n in names:
                out_path = ((given.get(n) or {}).get("output") or "") if isinstance(given.get(n), dict) else ""
                rows.append(BoundInput(input=n, action=out_path,
                                       label=localized(manifest, out_path, lang) if out_path else ""))
            view.bindings.append(SourceBinding(mode=mode, inputs=rows,
                                               parameters=dict(src.get("parameters") or {})))
        out.append(view)
    return out



# --------------------------------------------------------------------------- #
#  Bearbeiten — Regeln aus obah (edit_bindings.rs)
# --------------------------------------------------------------------------- #
def supports_toggle_button(d):
    """obah: InputSourceDef::supports_toggle_button."""
    if d.type in ("button", "trigger", "pinch"):
        return True
    if d.type in ("joystick", "trackpad"):
        return d.click or d.touch or d.value or d.force
    return False


def supported_modes(d):
    """obah: supported_modes — waehlbare Modi fuer diese Eingabe."""
    modes = {
        "button": ["button"],
        "trigger": ["button", "trigger"],
        "pinch": ["button", "trigger"],
        "joystick": ["button", "joystick", "dpad", "scroll"],
        "trackpad": ["button", "trackpad", "dpad", "scroll"],
    }.get(d.type, [])
    modes = list(modes)
    if supports_toggle_button(d):
        modes.insert(min(1, len(modes)), "toggle_button")
    return modes


def required_action_type(mode, inp):
    """obah: required_action_type — welcher Aktionstyp in dieses Feld passt."""
    if mode == "toggle_button" and inp in ("toggle", "click", "touch"):
        return "boolean"
    if (mode, inp) in (("trigger", "pull"), ("grab", "value"), ("grab", "force"),
                       ("joystick", "force"), ("trackpad", "force"),
                       ("scalar_constant", "value")):
        return "vector1"
    if (mode, inp) in (("joystick", "position"), ("trackpad", "position")):
        return "vector2"
    if mode in ("button", "trigger", "joystick", "trackpad") and inp in ("click", "touch"):
        return "boolean"
    if mode == "dpad" or (mode == "grab" and inp in ("grab", "touch")):
        return "boolean"
    return None


def compatible_actions(manifest, set_name, mode, inp, current=None):
    """
    obah: compatible_action_options — [None, pfad, ...]: alle Aktionen des
    Action Sets ('<set>/in/...') mit passendem Typ. Eine unbekannte, schon
    eingetragene Aktion bleibt erhalten, damit nichts still verloren geht.
    """
    prefix = set_name.rstrip("/").lower() + "/in/"
    need = required_action_type(mode, inp)
    options = [None]
    for key, (name, typ) in manifest.actions.items():
        if not key.startswith(prefix):
            continue
        if need is None or (typ or "").lower() == need:
            options.append(name)
    if current and not any(o and o.lower() == current.lower() for o in options):
        options.append(current)
    return options


# (name, englische Beschriftung, Standardwert, Auswahl)
def known_parameter_specs(d, mode):
    """obah: known_parameter_specs."""
    out = []
    scalar = [n for n, f in (("click", d.click), ("touch", d.touch),
                             ("value", d.value), ("force", d.force)) if f]
    if mode == "dpad":
        out.append(("deadzone_pct", "Deadzone percent", "25", []))
        out.append(("overlap_pct", "Direction overlap percent", "0", []))
        sub = [n for n, f in (("touch", d.touch), ("click", d.click)) if f] or ["touch", "click"]
        out.append(("sub_mode", "Activation component", sub[0], sub))
    elif mode in ("button", "toggle_button", "trigger"):
        if len(scalar) > 1 or d.value or d.force:
            default = "force" if d.force else "value" if d.value else "click" if d.click else "touch"
            out.append(("force_input", "Physical component", default, scalar))
        if d.value or d.force:
            out.append(("click_activate_threshold", "Click activation threshold", "0.8", []))
            out.append(("click_deactivate_threshold", "Click release threshold", "0.7", []))
            out.append(("touch_activate_threshold", "Touch activation threshold", "0.1", []))
            out.append(("touch_deactivate_threshold", "Touch release threshold", "0.05", []))
        out.append(("haptic_amplitude", "Activation haptic amplitude", "0.0", []))
    elif mode == "grab":
        out.append(("force_hold_threshold", "Grab hold threshold", "0.02", []))
        out.append(("force_release_threshold", "Grab release threshold", "0.01", []))
    elif mode in ("joystick", "trackpad"):
        out.append(("deadzone_pct", "Deadzone percent", "0", []))
        out.append(("maxzone_pct", "Maximum zone percent", "100", []))
        out.append(("invert", "Axis inversion", "n", ["n", "x", "y", "xy"]))
    return out


def parse_parameter_value(text):
    """obah: parse_parameter_value — 'json:<...>' = JSON, sonst Text."""
    if text.startswith("json:"):
        try:
            return json.loads(text[5:])
        except ValueError as exc:
            raise ValueError(f"JSON: {exc}") from exc
    return text


def format_parameter_value(value):
    """Umkehrung fuer das Eingabefeld: Text bleibt Text, alles andere json:..."""
    return value if isinstance(value, str) else "json:" + json.dumps(value)


def _single_root(binding):
    """obah: infer_single_device_user_root — '/user/gamepad' o. Ae. aus der Datei."""
    for sets in (binding.get("bindings") or {}).values():
        for key in ("sources", "poses", "skeleton", "haptics"):
            for entry in (sets or {}).get(key) or []:
                path = (entry or {}).get("path") or ""
                idx = [path.find(m) for m in ("/input/", "/pose/", "/output/") if path.find(m) > 0]
                if idx:
                    return path[:min(idx)]
    return None


def new_binding_path(d, side, controller_type, binding):
    """obah: default_binding_path — Pfad fuer ein NEUES Binding dieser Eingabe."""
    if d.path.startswith("/user/"):
        return d.path
    if side == "left":
        root = "/user/hand/left"
    elif side == "right":
        root = "/user/hand/right"
    elif ui_mode(controller_type) == "hmd":
        root = "/user/head"
    else:
        root = _single_root(binding)
    return (root.rstrip("/") + d.path) if root else d.path


def _set_entry(binding, set_name, create=False):
    """Eintrag des Action Sets in der Datei (obah: resolved_action_set_name)."""
    sets = binding.setdefault("bindings", {}) if create else (binding.get("bindings") or {})
    if set_name in sets:
        return sets[set_name]
    want = set_name.rstrip("/").lower()
    for k in sets:
        if k.rstrip("/").lower() == want:
            return sets[k]
    if create:
        sets[set_name] = {"sources": []}
        return sets[set_name]
    return None


def source_drafts(binding, set_name, d, side):
    """Kopien aller Bindings, die auf dieser Eingabe liegen (obah: drafts)."""
    entry = _set_entry(binding, set_name) or {}
    return [copy.deepcopy(s) for s in entry.get("sources") or []
            if isinstance(s, dict) and _matches(s.get("path"), d.path, side)]


def apply_drafts(binding, set_name, d, side, drafts):
    """
    obah: apply_binding_modal — alte Bindings der Eingabe raus, Entwuerfe an
    derselben Stelle wieder rein (Reihenfolge der Datei bleibt erhalten).
    """
    entry = _set_entry(binding, set_name, create=True)
    sources = entry.setdefault("sources", [])
    idx = next((i for i, s in enumerate(sources)
                if isinstance(s, dict) and _matches(s.get("path"), d.path, side)), len(sources))
    kept = [s for s in sources
            if not (isinstance(s, dict) and _matches(s.get("path"), d.path, side))]
    before = sum(1 for s in sources[:idx]
                 if not (isinstance(s, dict) and _matches(s.get("path"), d.path, side)))
    entry["sources"] = kept[:before] + [copy.deepcopy(x) for x in drafts] + kept[before:]


def new_draft(d, side, controller_type, binding):
    """obah: add_binding — erster unterstuetzter Modus, noch ohne Aktionen."""
    modes = supported_modes(d)
    if not modes:
        return None
    return {"path": new_binding_path(d, side, controller_type, binding),
            "mode": modes[0], "inputs": {}}


def draft_inputs(d, draft):
    """obah: display_inputs — Felder, die der Entwurf im Editor zeigt."""
    mode = (draft.get("mode") or "").lower()
    given = draft.get("inputs") or {}
    names = [] if (mode == "toggle_button" and given) else expected_inputs(d, mode)
    return names + [k for k in given if k not in names]


def set_draft_mode(d, draft, mode):
    """obah: set_selected_mode — Felder, die der neue Modus nicht kennt, fallen weg."""
    if (draft.get("mode") or "") != mode:
        allowed = expected_inputs(d, mode)
        draft["mode"] = mode
        draft["inputs"] = {k: v for k, v in (draft.get("inputs") or {}).items() if k in allowed}


def set_draft_action(draft, inp, output):
    """obah: set_selected_action — None entfernt die Zuordnung."""
    inputs = draft.setdefault("inputs", {})
    if output:
        extra = inputs.get(inp) if isinstance(inputs.get(inp), dict) else {}
        inputs[inp] = dict(extra, output=output)
    else:
        inputs.pop(inp, None)


def set_draft_parameter(draft, name, value, original=None):
    """obah: apply_parameter_editor — Name eindeutig (ohne Gross/klein)."""
    name = (name or "").strip()
    if not name:
        raise ValueError("empty")
    params = draft.setdefault("parameters", {})
    for k in params:
        if k.lower() == name.lower() and not (original and k.lower() == original.lower()):
            raise ValueError("exists")
    if original and original != name:
        params.pop(original, None)
    params[name] = value


def remove_draft_parameter(draft, name):
    params = draft.get("parameters") or {}
    params.pop(name, None)
    if not params:
        draft.pop("parameters", None)


def draft_summary(manifest, draft, lang="en"):
    """'(Stick_Click, Move)' wie in obahs Liste: belegte Aktionen, sortiert."""
    names = sorted({localized(manifest, (v or {}).get("output", ""), lang)
                    for v in (draft.get("inputs") or {}).values()
                    if isinstance(v, dict) and v.get("output")})
    return ", ".join(names)


# --------------------------------------------------------------------------- #
#  Speichern
# --------------------------------------------------------------------------- #
SAVE_KINDS = ("xrizer", "vapor", "opencomposite")


def save_path(game, controller_type, kind):
    """obah: BindingSourceKind::save_path."""
    import obah_bindings as ob
    if kind == "xrizer":
        return ob.xrizer_path(game.game_folder, controller_type)
    if kind == "vapor":
        return ob.vapor_path(game.game_folder)
    if kind == "opencomposite":
        return ob.opencomposite_path(game.game_folder, controller_type)
    raise ValueError(kind)


def save_binding(binding, path, controller_type):
    """
    Datei schreiben wie obah (JSON, eingerueckt, Ordner anlegen). Anders als
    obah wird eine vorhandene Datei vorher als '<name>.bak' gesichert —
    ein Fehlklick soll keine Belegung kosten. Atomar: erst in eine
    Temp-Datei, dann umbenennen.
    """
    data = dict(binding)
    data.setdefault("controller_type", controller_type)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.isfile(path):
        shutil.copy2(path, path + ".bak")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)
    return path


# --------------------------------------------------------------------------- #
#  Posen, Haptik, Skelett und Chords (obah: "Other" / "Chords")
# --------------------------------------------------------------------------- #
# obah zeigt diese Bindings nicht bei den Controller-Tasten, sondern in zwei
# eigenen Listen. Sie hängen nicht an einer Taste, sondern an einem Pfad:
#   poses     — wohin die Hand zeigt (/pose/raw, /pose/tip, ...)
#   skeleton  — Fingertracking (/input/skeleton/left)
#   haptics   — Vibration (/output/haptic)
#   chords    — mehrere Tasten zusammen ergeben EINE Aktion
PATH_KINDS = ("poses", "skeleton", "haptics")
# Welcher Aktionstyp und welche Richtung gehoert zu welcher Liste
# (obah: PathBindingKind::action_type / action_direction).
PATH_KIND_ACTION = {"poses": ("pose", "in"), "skeleton": ("skeleton", "in"),
                    "haptics": ("vibration", "out")}
# obah: ChordInputKind
CHORD_KINDS = ("held", "single", "click", "touch")


def _sides_for(d, controller_type):
    """obah: source_sides — auf welchen Seiten diese Profilangabe vorkommt."""
    if not is_handed(controller_type):
        return ["single"]
    if d.side in ("left", "right"):
        return [d.side]
    return ["left", "right"]


def _aux_name(d, side, controller_type):
    """obah: profile_source_display_name — 'Left Haptic', 'Right Raw', ..."""
    name = d.name
    if d.type == "skeleton":
        # obah nennt den Eintrag nur "left"/"right" — mit der Seite davor
        # stuende da "Left left". "Skeleton" ist verstaendlicher.
        name = "Skeleton" if is_handed(controller_type) else f"Skeleton ({d.name})"
    if not is_handed(controller_type):
        return name
    return {"left": "Left " + name, "right": "Right " + name}.get(side, name)


def aux_sources(controller_type, binding):
    """
    Pfad-Quellen dieses Controllers (obah: collect_aux_sources).

    Rueckgabe: (path_sources, chord_sources)
      path_sources : [{"path", "name", "kind"}]  kind aus PATH_KINDS
      chord_sources: [{"path", "name"}]
    """
    kind_of = {"pose": "poses", "skeleton": "skeleton", "vibration": "haptics"}
    paths, chords = [], []
    seen_p, seen_c = set(), set()
    for d in profile_inputs(controller_type):
        for side in _sides_for(d, controller_type):
            full = new_binding_path(d, side, controller_type, binding)
            name = _aux_name(d, side, controller_type)
            if d.type in kind_of:
                key = (kind_of[d.type], full.lower())
                if key not in seen_p:
                    seen_p.add(key)
                    paths.append({"path": full, "name": name, "kind": kind_of[d.type]})
            elif d.type in CHORD_TYPES:
                # obah: is_reserved_system_source — /input/system gehoert dem
                # System und laesst sich nicht in einen Chord stecken.
                if d.path.lower().endswith("/input/system"):
                    continue
                if full.lower() not in seen_c:
                    seen_c.add(full.lower())
                    chords.append({"path": full, "name": name})
    order = {k: i for i, k in enumerate(PATH_KINDS)}
    paths.sort(key=lambda s: (order[s["kind"]], s["name"], s["path"]))
    chords.sort(key=lambda s: (s["name"], s["path"]))
    return paths, chords


def action_choices(manifest, set_name, action_type, direction="in", current=None):
    """
    obah: action_choices — Aktionen des Action Sets mit genau diesem Typ und
    dieser Richtung ('<set>/in/...' bzw. '<set>/out/...').
    """
    prefix = f"{set_name.rstrip('/').lower()}/{direction}/"
    out = []
    for key, (name, typ) in manifest.actions.items():
        if key.startswith(prefix) and (typ or "").lower() == action_type:
            out.append(name)
    if current and not any(o.lower() == current.lower() for o in out):
        out.append(current)
    return out


def path_bindings(binding, set_name, kind):
    """Die Liste poses/skeleton/haptics eines Action Sets (Kopie)."""
    entry = _set_entry(binding, set_name) or {}
    return [copy.deepcopy(b) for b in (entry.get(kind) or []) if isinstance(b, dict)]


def chord_bindings(binding, set_name):
    entry = _set_entry(binding, set_name) or {}
    return [copy.deepcopy(b) for b in (entry.get("chords") or []) if isinstance(b, dict)]


def set_path_binding(binding, set_name, kind, index, draft):
    """Eintrag ersetzen (index) oder anhaengen (index=None)."""
    entry = _set_entry(binding, set_name, create=True)
    items = entry.setdefault(kind, [])
    if index is None:
        items.append(copy.deepcopy(draft))
    elif 0 <= index < len(items):
        items[index] = copy.deepcopy(draft)


def remove_path_binding(binding, set_name, kind, index):
    entry = _set_entry(binding, set_name) or {}
    items = entry.get(kind) or []
    if 0 <= index < len(items):
        del items[index]
        if not items:
            entry.pop(kind, None)


def set_chord_binding(binding, set_name, index, draft):
    entry = _set_entry(binding, set_name, create=True)
    items = entry.setdefault("chords", [])
    if index is None:
        items.append(copy.deepcopy(draft))
    elif 0 <= index < len(items):
        items[index] = copy.deepcopy(draft)


def remove_chord_binding(binding, set_name, index):
    entry = _set_entry(binding, set_name) or {}
    items = entry.get("chords") or []
    if 0 <= index < len(items):
        del items[index]
        if not items:
            entry.pop("chords", None)


def chord_inputs(draft):
    """[(pfad, art)] eines Chords — die Datei speichert Paare als Liste."""
    out = []
    for item in draft.get("inputs") or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            out.append((str(item[0]), str(item[1])))
        elif isinstance(item, dict) and item.get("path"):
            # Nicht obahs Form, aber schon in freier Wildbahn gesehen
            out.append((item["path"], item.get("kind", "held")))
    return out


def set_chord_inputs(draft, pairs):
    draft["inputs"] = [[p, k] for p, k in pairs]


def new_path_draft(manifest, set_name, kind, sources):
    """obah: AddPath — erste passende Quelle und erste passende Aktion."""
    action_type, direction = PATH_KIND_ACTION[kind]
    actions = action_choices(manifest, set_name, action_type, direction)
    src = next((s for s in sources if s["kind"] == kind), None)
    if not src or not actions:
        return None
    return {"output": actions[0], "path": src["path"]}


def new_chord_draft(manifest, set_name, sources):
    """obah: AddChord — erste Quelle als 'held', erste boolesche Aktion."""
    actions = action_choices(manifest, set_name, "boolean", "in")
    if not sources or not actions:
        return None
    return {"inputs": [[sources[0]["path"], "held"]], "output": actions[0]}


def can_add_path_binding(manifest, set_name, kind, sources):
    """obah: can_add_path_binding — Quelle UND passende Aktion muessen da sein."""
    action_type, direction = PATH_KIND_ACTION[kind]
    return (any(s["kind"] == kind for s in sources)
            and bool(action_choices(manifest, set_name, action_type, direction)))


# --------------------------------------------------------------------------- #
#  deadzone_pct fuer einen ganzen Stick (Deadzone-Knopf im Controls-Tab)
# --------------------------------------------------------------------------- #
def stick_sources(binding, controller_type, side):
    """Alle Belegungen im Modus 'joystick' auf dem Stick dieser Seite —
    ueber ALLE Action Sets (die Deadzone soll ueberall gleich sein)."""
    paths = [d.path for d in inputs_for_side(controller_type, side) if d.type == "joystick"]
    out = []
    for entry in (binding.get("bindings") or {}).values():
        for s in (entry or {}).get("sources") or []:
            if (isinstance(s, dict) and (s.get("mode") or "").lower() == "joystick"
                    and any(_matches(s.get("path"), p, side) for p in paths)):
                out.append(s)
    return out


def stick_deadzone_pct(binding, controller_type, side):
    """Liste der deadzone_pct-Werte (int) der Stick-Belegungen dieser Seite."""
    vals = []
    for s in stick_sources(binding, controller_type, side):
        raw = (s.get("parameters") or {}).get("deadzone_pct", 0)
        try:
            vals.append(int(round(float(raw))))
        except (TypeError, ValueError):
            vals.append(0)
    return vals


def set_stick_deadzone_pct(binding, controller_type, side, value):
    """deadzone_pct auf allen Stick-Belegungen dieser Seite setzen (0 = entfernen).
    Rueckgabe: Anzahl geaenderter Belegungen."""
    srcs = stick_sources(binding, controller_type, side)
    for s in srcs:
        if value > 0:
            s.setdefault("parameters", {})["deadzone_pct"] = str(int(value))
        else:
            remove_draft_parameter(s, "deadzone_pct")
    return len(srcs)
