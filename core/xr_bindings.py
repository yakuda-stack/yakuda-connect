#!/usr/bin/env python3
"""
core/xr_bindings.py — OpenXR-Spiele in der Controller-Ansicht (xrBinder)
========================================================================
Der Controls-Tab zeigt OpenVR-Spiele (obah) als zwei Controller mit einer
Karte je Taste. OpenXR-Spiele sollen genauso aussehen. Dieses Modul
uebersetzt zwischen den beiden Welten:

  * Spielseite (xrBinder):  Aktionen des Spiels ("Menue oeffnen") mit ihren
    Standard-Tasten (Pfade wie /user/hand/left/input/menu/click) und unsere
    Umbelegungen {(aktion, hand): {"source": ..., "source_hand": ...}}.
  * Ansichtsseite (obah):   Controller-Profil mit Eingaben (/input/x ...),
    je Eingabe eine Karte (oe.InputView).

Je Karte steht, welche Funktionen des Spiels GERADE auf dieser Taste liegen
— Standard plus Umbelegungen, ohne abgeschaltete. Aendern heisst immer:
eine Funktion auf eine Taste legen (sie verschwindet dann von ihrer alten)
oder von einer Taste nehmen. Daraus entstehen die Umbelegungen, die
core/xrbinder.py in die xrBinder-INI schreibt.

Kein Qt, keine Dateien — alles hier ist mit einfachen Tests pruefbar.
"""
import re
from collections import OrderedDict

import obah_editor as oe
import xrbinder as xb

TOUCH = "/interaction_profiles/oculus/touch_controller"
INDEX = "/interaction_profiles/valve/index_controller"
VIVE = "/interaction_profiles/htc/vive_controller"

# obah-Controllertyp -> OpenXR-Profil
CT_PROFILE = {"oculus_touch": TOUCH, "knuckles": INDEX, "vive_controller": VIVE}
DEFAULT_CT = "oculus_touch"

# obah-Eingabe -> Name der Komponente in OpenXR (/user/hand/*/input/<name>/...)
OBAH_TO_XR = {
    "oculus_touch": {"/input/joystick": "thumbstick", "/input/trigger": "trigger",
                     "/input/grip": "squeeze", "/input/a": "a", "/input/b": "b",
                     "/input/x": "x", "/input/y": "y", "/input/system": "menu",
                     "/input/thumbrest": "thumbrest"},
    "knuckles": {"/input/system": "system", "/input/a": "a", "/input/b": "b",
                 "/input/trigger": "trigger", "/input/trackpad": "trackpad",
                 "/input/grip": "squeeze", "/input/thumbstick": "thumbstick"},
    "vive_controller": {"/input/trackpad": "trackpad", "/input/trigger": "trigger",
                        "/input/grip": "squeeze", "/input/application_menu": "menu",
                        "/input/system": "system"},
}

TYPE_NAMES = {1: "bool", 2: "float", 3: "vector2"}


# --------------------------------------------------------------------------- #
#  Controller erkennen
# --------------------------------------------------------------------------- #
def detect_controller(state):
    """
    Welcher Controller ist im Spiel aktiv? Die Quellen des Layers, die im
    aktiven Profil gebunden sind, verraten es: X/Y gibt es nur bei Touch,
    ein Trackpad mit A-Taste nur bei Index, Trackpad + Menue bei Vive.
    """
    bound = {name for name, paths in (state.get("sources") or {}).items() if paths}
    if bound & {"x_click", "y_click", "x_touch", "y_touch", "thumbrest_touch"}:
        return "oculus_touch"
    if "trackpad_touch" in bound and "a_click" in bound:
        return "knuckles"
    if "trackpad_click" in bound and "menu_click" in bound and "thumbstick" not in bound:
        return "vive_controller"
    return DEFAULT_CT


# --------------------------------------------------------------------------- #
#  Pfade, Komponenten, Quellen
# --------------------------------------------------------------------------- #
def components(ct, side, base):
    """Komponenten einer Taste im OpenXR-Profil, z. B. ['x/click', 'x/touch']."""
    prof = xb.PROFILES.get(CT_PROFILE.get(ct, TOUCH), {})
    comps = list(prof.get(side, [])) + list(prof.get("both", []))
    return [c for c in comps if c == base or c.startswith(base + "/")]


def comp_path(side, comp):
    return f"/user/hand/{side}/input/{comp}"


def comp_kind(comp):
    """'x/click' -> 'click', 'thumbstick' -> 'dir'."""
    return comp.split("/", 1)[1] if "/" in comp else "dir"


def source_for(comp, action_type):
    """Quelle, die diese Komponente fuer eine Aktion dieses Typs liefert (oder None)."""
    typ = TYPE_NAMES.get(action_type)
    if "/" not in comp:
        name = comp if typ == "vector2" else None
    else:
        base, kind = comp.split("/", 1)
        name = f"{base}_{kind}"
        if typ == "bool":
            name = name if kind in ("click", "touch") else (name + "_b" if kind in ("value", "force") else None)
        elif typ == "float":
            name = name if kind in ("value", "force", "x", "y") else (name + "_f" if kind == "click" else None)
        else:
            name = None
    return name if name and name in xb.build_sources() else None


def source_path(source, source_hand):
    """Umgekehrt: Quelle + Hand -> Pfad (None fuer 'Aus')."""
    if not source or source in xb.OFF_SOURCE.values() or not source_hand:
        return None
    name = source[:-2] if source.endswith(("_f", "_b")) else source
    comp = name.replace("_", "/", 1)
    return comp_path(source_hand, comp)


def source_available(state, source, hand):
    """Ist die Quelle im aktiven Profil fuer diese Hand gebunden? Ohne Abfrage: ja."""
    bound = state.get("sources") or {}
    if not any(bound.values()):
        return True                     # Runtime verraet nichts (z. B. xrizer) -> nicht sperren
    return any(xb.hand_of_path(p) == hand for p in bound.get(source, []))


# --------------------------------------------------------------------------- #
#  Umbelegungen
# --------------------------------------------------------------------------- #
def mappings_from_list(lst):
    """Liste aus der gespeicherten Datei -> {(aktion, hand): mapping}."""
    out = OrderedDict()
    for m in lst or []:
        out[(m["action"], m.get("hand", ""))] = dict(m)
    return out


def mappings_to_list(mappings):
    return [dict(m) for m in mappings.values()]


def actions(state):
    """Umlegbare Aktionen (Knopf, Wert, Richtung) des Spiels."""
    return [a for a in state.get("actions") or []
            if a.get("type") in TYPE_NAMES and xb.valid_action_name(a.get("name", ""))]


def action_by_name(state, name):
    return next((a for a in actions(state) if a["name"] == name), None)


def default_paths(state, name, hand):
    paths = (state.get("bindings") or {}).get(name, [])
    return [p for p in paths if not hand or xb.hand_of_path(p) == hand]


def effective_paths(state, mappings, name, hand):
    """Wo liegt die Funktion gerade? Umbelegung vor Standard; 'Aus' = nirgends."""
    m = mappings.get((name, hand))
    if m is not None:
        p = source_path(m["source"], m.get("source_hand"))
        return [p] if p else []
    return default_paths(state, name, hand)


def _at_default(state, key, m):
    """Liegt die Umbelegung m genau auf dem (einzigen) Standard-Platz?"""
    target = source_path(m["source"], m.get("source_hand"))
    defaults = default_paths(state, *key)
    return target is not None and defaults == [target]


def is_moved(state, mappings, key):
    """Umgelegt (↪)? Nur „Kippen“ auf dem Standard-Platz zaehlt nicht."""
    m = mappings.get(key)
    return m is not None and not _at_default(state, key, m)


def on_path(state, mappings, path):
    """[(aktion, hand, umgelegt?)] aller Funktionen, die gerade auf path liegen."""
    out = []
    for act in actions(state):
        for hand in act.get("hands") or [""]:
            if path in effective_paths(state, mappings, act["name"], hand):
                out.append((act, hand, is_moved(state, mappings, (act["name"], hand))))
    return out


# --------------------------------------------------------------------------- #
#  „Kippen = Druecken“ (Stick-Klick loest auch beim blossen Kippen aus)
# --------------------------------------------------------------------------- #
TILT_COMP = "thumbstick/click"


def tilt_capable(state, act, side, comp):
    """Geht „Kippen“ fuer diese Funktion auf dieser Komponente?"""
    return (comp == TILT_COMP and TYPE_NAMES.get(act.get("type")) == "bool"
            and all(source_available(state, s, side)
                    for s in (xb.TILT_SOURCE, "thumbstick_x", "thumbstick_y")))


def has_tilt(mappings, name, hand):
    m = mappings.get((name, hand))
    return bool(m and m.get("tilt"))


def tilt_threshold(mappings, name, hand):
    m = mappings.get((name, hand)) or {}
    return xb.clamp_threshold(m.get("tilt_threshold", xb.TILT_THRESHOLD))


def set_tilt_threshold(mappings, name, hand, value):
    """Schwelle fuer eine Funktion mit Kippen setzen (0.2 … 0.95)."""
    m = mappings.get((name, hand))
    if not m or not m.get("tilt"):
        return
    v = xb.clamp_threshold(value)
    if v == xb.TILT_THRESHOLD:
        m.pop("tilt_threshold", None)        # Standard: nicht extra speichern
    else:
        m["tilt_threshold"] = v


def set_tilt(state, mappings, act, hand, side, on):
    """Kippen an/aus fuer eine Funktion, die auf dem Stick-Klick dieser Seite liegt."""
    key = (act["name"], hand)
    m = mappings.get(key)
    if on:
        if m is None:
            m = {"action": act["name"], "hand": hand, "source": xb.TILT_SOURCE,
                 "source_hand": side}
            mappings[key] = m
        m["tilt"] = True
        return
    if m is None:
        return
    m.pop("tilt", None)
    m.pop("tilt_threshold", None)
    if _at_default(state, key, m):
        del mappings[key]                    # nur noch Standard — keine Umbelegung


# --------------------------------------------------------------------------- #
#  Deadzone fuer Sticks (gegen Stick-Drift)
# --------------------------------------------------------------------------- #
DEADZONE_COMP = "thumbstick"


def deadzone_capable(state, act, side, comp, hand=None):
    """Geht eine Deadzone fuer diese Richtungs-Funktion auf diesem Stick?

    Funktionen ohne Hand gelten fuer beide Sticks. Die Deadzone liest aber
    nur EINEN Stick — liegt so eine Funktion auch auf dem anderen Stick,
    wuerde der sonst mit umgelegt. Dann also nicht anbieten.
    """
    if comp != DEADZONE_COMP or TYPE_NAMES.get(act.get("type")) != "vector2":
        return False
    if not all(source_available(state, s, side)
               for s in (xb.DEADZONE_SOURCE, "thumbstick_x", "thumbstick_y")):
        return False
    if hand is None:
        hand = hand_for(act, side)
    if not hand:
        return all(xb.hand_of_path(p) == side for p in default_paths(state, act["name"], ""))
    return True


def has_deadzone(mappings, name, hand):
    m = mappings.get((name, hand))
    return bool(m and m.get("deadzone") is not None)


def deadzone_value(mappings, name, hand):
    m = mappings.get((name, hand)) or {}
    return xb.clamp_deadzone(m.get("deadzone", xb.DEADZONE_DEFAULT))


def set_deadzone_value(mappings, name, hand, value):
    """Deadzone einer Funktion aendern (nur, wenn sie an ist)."""
    m = mappings.get((name, hand))
    if m and m.get("deadzone") is not None:
        m["deadzone"] = xb.clamp_deadzone(value)


def set_deadzone(state, mappings, act, hand, side, on):
    """Deadzone an/aus fuer eine Funktion auf dem Stick dieser Seite."""
    key = (act["name"], hand)
    m = mappings.get(key)
    if on:
        if m is None:
            m = {"action": act["name"], "hand": hand, "source": xb.DEADZONE_SOURCE,
                 "source_hand": side}
            mappings[key] = m
        m.setdefault("deadzone", xb.DEADZONE_DEFAULT)
        return
    if m is None:
        return
    m.pop("deadzone", None)
    if _at_default(state, key, m) and not m.get("tilt"):
        del mappings[key]                    # nur noch Standard — keine Umbelegung


def stick_actions(state, mappings, side):
    """[(aktion, hand)] aller Stick-Richtungen, die gerade auf dem Stick dieser
    Seite liegen und eine Deadzone vertragen (siehe deadzone_capable)."""
    path = comp_path(side, DEADZONE_COMP)
    return [(act, hand) for act, hand, _m in on_path(state, mappings, path)
            if deadzone_capable(state, act, side, DEADZONE_COMP, hand)]


def stick_deadzone(state, mappings, side):
    """Deadzone des Sticks dieser Seite (0.0 = aus)."""
    for act, hand in stick_actions(state, mappings, side):
        if has_deadzone(mappings, act["name"], hand):
            return deadzone_value(mappings, act["name"], hand)
    return 0.0


def set_stick_deadzone(state, mappings, side, value):
    """Deadzone fuer ALLE Stick-Richtungen auf diesem Stick setzen.
    value <= 0 schaltet sie ab. Rueckgabe: Anzahl betroffener Funktionen."""
    entries = stick_actions(state, mappings, side)
    on = value is not None and float(value) > 0
    for act, hand in entries:
        set_deadzone(state, mappings, act, hand, side, on)
        if on:
            set_deadzone_value(mappings, act["name"], hand, value)
    return len(entries)


def hand_for(act, side):
    hands = act.get("hands") or [""]
    if side in hands:
        return side
    return "" if hands == [""] else hands[0]


def assign(state, mappings, act, side, comp):
    """Funktion act auf die Komponente comp dieser Seite legen. False = passt nicht."""
    src = source_for(comp, act["type"])
    if not src:
        return False
    hand = hand_for(act, side)
    key = (act["name"], hand)
    path = comp_path(side, comp)
    if path in default_paths(state, act["name"], hand) and len(default_paths(state, act["name"], hand)) == 1:
        mappings.pop(key, None)             # das ist ihr Standard — keine Umbelegung noetig
    else:
        mappings[key] = {"action": act["name"], "hand": hand, "source": src, "source_hand": side}
    return True


def unassign(state, mappings, act, hand, path):
    """Funktion von dieser Taste nehmen."""
    key = (act["name"], hand)
    m = mappings.get(key)
    if m is not None and source_path(m["source"], m.get("source_hand")) == path:
        del mappings[key]                    # zurueck auf den Standard ...
        if path not in default_paths(state, act["name"], hand):
            return
    typ = TYPE_NAMES[act["type"]]
    # ... und liegt der Standard auf genau dieser Taste: abschalten
    mappings[key] = {"action": act["name"], "hand": hand,
                     "source": xb.OFF_SOURCE[typ], "source_hand": ""}


def reset_paths(state, mappings, paths):
    """Alles, was diese Pfade betrifft, auf Standard zurueck (Knopf 'Standard')."""
    paths = set(paths)
    for key, m in list(mappings.items()):
        target = source_path(m["source"], m.get("source_hand"))
        if target in paths:
            del mappings[key]
        elif target is None and paths & set(default_paths(state, *key)):
            del mappings[key]


def has_changes_on(state, mappings, paths):
    paths = set(paths)
    for key, m in mappings.items():
        target = source_path(m["source"], m.get("source_hand"))
        if target in paths or (target is None and paths & set(default_paths(state, *key))):
            return True
    return False


# --------------------------------------------------------------------------- #
#  OpenXR-Vorlage (Knopf „OpenXR-Vorlage verwenden“)
# --------------------------------------------------------------------------- #
# Manche Spiele (z. B. VRChat ueber xrizer) melden Aktionen, aber die Runtime
# verraet keine einzige Taste -> alle Karten „nichts belegt“. Die Vorlage legt
# dann eine uebliche Standardbelegung an: erst ueber Tastennamen im Aktions-
# namen ("oculustouch_left_x_click", "Thumbstick X"), sonst ueber die
# Bedeutung ("Jump" -> A, "Grab" -> Griff). Ergebnis sind normale
# Umbelegungen: ungespeichert, pruefbar, per „Verwerfen“ weg.

# Tastenname im Text -> Komponente (Reihenfolge = Vorrang)
_TPL_COMPONENT_WORDS = (
    ("thumbrest", ("thumbrest",)),
    ("thumbstick", ("thumbstick", "joystick", "stick", "trackpad", "touchpad", "analog")),
    ("trigger", ("trigger",)),
    ("squeeze", ("grip", "squeeze")),
    ("menu", ("menu",)),
    ("system", ("system",)),
)
_TPL_LETTERS = ("a", "b", "x", "y")

# Bedeutung -> (Komponente, feste Seite oder None = je Hand, Bool-Art)
_TPL_MEANINGS = (
    (("jump",), "a", "right"),
    (("crouch", "prone", "duck"), "thumbstick/click", "right"),
    (("sprint", "run"), "thumbstick/click", "left"),
    (("pause", "options", "quickmenu"), "menu", "left"),
    (("mute", "mic", "microphone", "voice", "talk"), "y", "left"),
    (("back", "cancel"), "b", "right"),
    (("grab", "grabbing", "pickup", "pick", "hold", "drop", "climb"), "squeeze", None),
    (("use", "interact", "fire", "shoot", "select", "confirm"), "trigger", None),
)
_TPL_MOVE = ("move", "movement", "locomotion", "walk", "strafe", "teleport")
_TPL_TURN = ("turn", "rotate", "rotation", "look", "snap", "camera", "scroll")

# Fehlt eine Taste am Controller: Ersatz (Index hat A/B statt X/Y, Vive ein Trackpad)
_TPL_FALLBACK = {"x": ("a",), "y": ("b",), "a": ("x",), "b": ("y",),
                 "menu": ("system", "b", "y"), "system": ("menu", "b"),
                 "thumbstick": ("trackpad",), "thumbrest": ()}


def _tpl_tokens(act):
    text = f"{act.get('name', '')} {act.get('description', '')}"
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text).lower()
    text = text.replace("oculus touch", "oculustouch")   # sonst waere "touch" die Art
    return [t for t in re.split(r"[^a-z0-9]+", text) if t]


def _tpl_side(tokens):
    has_l = bool({"left", "l", "lhand", "lefthand"} & set(tokens))
    has_r = bool({"right", "r", "rhand", "righthand"} & set(tokens))
    return "left" if has_l and not has_r else "right" if has_r and not has_l else None


def _tpl_kinds(tokens, action_type, base):
    typ = TYPE_NAMES.get(action_type)
    if typ == "vector2":
        return [""]
    if typ == "float":
        if base in ("thumbstick", "trackpad"):
            if {"x", "horizontal"} & set(tokens):
                return ["x"]
            if {"y", "vertical"} & set(tokens):
                return ["y"]
            return []
        return ["value", "force", "click"]
    if "touch" in tokens and base not in ("thumbrest",):
        return ["touch"]
    if base == "thumbrest":
        return ["touch"]
    return ["click", "value"]


def _tpl_resolve(ct, side, base, kinds, action_type):
    """Passende Komponente dieser Seite (mit Ersatztasten) oder None."""
    for b in (base,) + _TPL_FALLBACK.get(base, ()):
        comps = components(ct, side, b)
        for kind in kinds:
            comp = b if kind == "" else f"{b}/{kind}"
            if comp in comps and source_for(comp, action_type):
                return comp
    return None


def _tpl_target(tokens, action_type):
    """(Basis-Komponente, Seite oder None, Arten) fuer eine Aktion — oder None."""
    side = _tpl_side(tokens)
    tset = set(tokens)
    # 1) Tastenname steht im Namen
    for base, words in _TPL_COMPONENT_WORDS:
        if tset & set(words):
            if base in ("menu", "system") and side != "right":
                base, side = "menu", "left"     # System rechts ist bei Quest reserviert
            return base, side, _tpl_kinds(tokens, action_type, base)
    if "axis" not in tset and tset & {"button", "press", "click", "touch", "btn"}:
        for letter in _TPL_LETTERS:
            if letter in tset:
                return letter, side, _tpl_kinds(tokens, action_type, letter)
    # 2) Bedeutung
    typ = TYPE_NAMES.get(action_type)
    if typ == "vector2" or (typ == "float" and tset & {"horizontal", "vertical"}):
        if tset & set(_TPL_MOVE):
            return "thumbstick", "left", _tpl_kinds(tokens, action_type, "thumbstick")
        if tset & set(_TPL_TURN):
            return "thumbstick", "right", _tpl_kinds(tokens, action_type, "thumbstick")
        if typ == "vector2":
            return "thumbstick", side, [""]
        return None
    for words, target, fixed in _TPL_MEANINGS:
        if tset & set(words):
            base, _, kind = target.partition("/")
            kinds = [kind] if kind else _tpl_kinds(tokens, action_type, base)
            return base, side or fixed, kinds
    return None


def template_mappings(state, ct=DEFAULT_CT):
    """
    Standardbelegung fuer ein Spiel ohne gemeldete Tasten.
    Rueckgabe: (mappings, zugeordnete Aktionen, alle Aktionen).
    """
    mappings = OrderedDict()
    acts = actions(state)
    matched = 0
    for act in acts:
        target = _tpl_target(_tpl_tokens(act), act["type"])
        if not target:
            continue
        base, side, kinds = target
        hands = [h for h in (act.get("hands") or []) if h in ("left", "right")]
        sides = [side] if side else (hands or ["left", "right"])
        hit = False
        for s in sides:
            comp = _tpl_resolve(ct, s, base, kinds, act["type"])
            if comp and assign(state, mappings, act, s, comp):
                hit = True
            if not act.get("hands") and hit:
                break                   # Aktion ohne Hand: nur eine Taste
        matched += 1 if hit else 0
    return mappings, matched, len(acts)


def template_offered(ct, state, mappings):
    """Knopf zeigen? Aktionen da, aber keine Taste belegt und nichts umgelegt."""
    if not actions(state) or mappings:
        return False
    bound, _total = counts(ct, state, mappings)
    return bound == 0


# --------------------------------------------------------------------------- #
#  Karten fuer die Controller-Ansicht
# --------------------------------------------------------------------------- #
def card_inputs(ct, side):
    """Die Eingaben (obah-InputDefs) dieser Seite, die es in OpenXR gibt."""
    table = OBAH_TO_XR.get(ct, {})
    return [d for d in oe.inputs_for_side(ct, side)
            if d.path in table and components(ct, side, table[d.path])]


def card_paths(ct, side, input_path):
    base = OBAH_TO_XR.get(ct, {}).get(input_path)
    return [comp_path(side, c) for c in components(ct, side, base)] if base else []


MOVED_MARK = "↪ "


def build_views(ct, side, state, mappings, tilt_label="+ tilt", deadzone_label="deadzone"):
    """oe.InputView je Taste: je Komponente die Funktionen, die darauf liegen."""
    out = []
    table = OBAH_TO_XR.get(ct, {})
    for d in card_inputs(ct, side):
        view = oe.InputView(input=d)
        for comp in components(ct, side, table[d.path]):
            rows = []
            for act, hand, moved in on_path(state, mappings, comp_path(side, comp)):
                label = (act.get("description") or act["name"])
                if has_tilt(mappings, act["name"], hand):
                    label += f"  ({tilt_label})"
                if has_deadzone(mappings, act["name"], hand):
                    pct = round(deadzone_value(mappings, act["name"], hand) * 100)
                    label += f"  ({deadzone_label} {pct} %)"
                rows.append(oe.BoundInput(input="", action=act["name"],
                                          label=(MOVED_MARK if moved else "") + label))
            if rows:
                view.bindings.append(oe.SourceBinding(mode=comp_kind(comp), inputs=rows))
        out.append(view)
    return out


def counts(ct, state, mappings, sides=("left", "right")):
    """(belegte Tasten, alle Tasten) fuer die Statuszeile."""
    total = bound = 0
    for side in sides:
        for v in build_views(ct, side, state, mappings):
            total += 1
            bound += 1 if v.bindings else 0
    return bound, total
