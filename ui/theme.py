#!/usr/bin/env python3
"""
ui/theme.py — Farbthemen fuer die Oberflaeche
=============================================
Die Oberflaeche ist ueber die Jahre mit fest eingetragenen Farbwerten gewachsen
— rund 400 Hex-Angaben in etwa 110 Stylesheets. Ein Themensystem nachtraeglich
einzuziehen haette bedeutet, jedes dieser Stylesheets von Hand umzuschreiben:
viel Arbeit mit hoher Wahrscheinlichkeit, dabei einzelne Stellen zu vergessen,
die dann in einem hellen Thema schwarz auf schwarz stehen.

Deshalb der andere Weg: die Farben werden nicht an der Quelle geaendert,
sondern beim Anwenden ERSETZT. ``tint()`` nimmt ein fertiges Stylesheet und
tauscht jeden bekannten Grundfarbwert gegen den des aktiven Themas. Das
funktioniert fuer jedes Widget, auch fuer solche, die spaeter dazukommen, und
das Standardthema ist eine 1:1-Abbildung — es sieht also exakt aus wie vorher.

Wie die Zuordnung entsteht:
  * Jeder Grundfarbwert gehoert zu einer Rolle (Fenster, Karten, Rahmen ...).
  * Innerhalb einer Rolle gibt es Abstufungen (#2e3440 und #21252b sind beide
    Hintergrund, nur unterschiedlich dunkel). Der Abstand wird EINMAL aus den
    Standardfarben berechnet und auf die Themenfarbe uebertragen — ein Thema
    braucht also nur eine Farbe pro Rolle, die Abstufungen ergeben sich.

Bewusst NICHT themenfaehig sind die Signalfarben Gruen (#a3be8c) und Gelb
(#ebcb8b): "installiert" muss gruen bleiben und "Achtung" gelb, sonst traegt
die Farbe keine Bedeutung mehr. Rot ist eine Ausnahme, weil es im Entwurf als
eigene Rolle "Stop / Loeschen" auftaucht.
"""
import colorsys
import os
import re

import paths
from jsonio import read_json, write_json_atomic
from logging_setup import get_logger

log = get_logger("theme")

SETTINGS_FILE = "theme.json"

# --------------------------------------------------------------------------- #
#  Rollen und ihre Grundfarben
# --------------------------------------------------------------------------- #
# Erster Eintrag je Rolle = Bezugsfarbe. Die weiteren sind Abstufungen; ihr
# Helligkeitsabstand zur Bezugsfarbe wird auf das gewaehlte Thema uebertragen.
ROLE_BASES = {
    "window":    ["#181a1f", "#1a1d23", "#1c1f26", "#1e222a", "#282c34"],
    "sidebar":   ["#21252b"],
    "cards":     ["#2e3440"],
    "inner":     ["#3b4252", "#434c5e"],
    "borders":   ["#4c566a"],
    "text":      ["#d8dee9", "#eceff4", "#ffffff"],
    "secondary": ["#7b88a1"],
    "accent":    ["#5e81ac", "#81a1c1", "#88c0d0", "#b7bdf8"],
    "danger":    ["#bf616a", "#ed8796", "#d08770"],
}

ROLE_ORDER = ["accent", "window", "sidebar", "cards", "inner", "borders",
              "text", "secondary", "danger"]

# Schluessel fuer die Beschriftung in der Oberflaeche (locales/*.json)
ROLE_LABEL_KEYS = {
    "accent": "design_role_accent",
    "window": "design_role_window",
    "sidebar": "design_role_sidebar",
    "cards": "design_role_cards",
    "inner": "design_role_inner",
    "borders": "design_role_borders",
    "text": "design_role_text",
    "secondary": "design_role_secondary",
    "danger": "design_role_danger",
}

# --------------------------------------------------------------------------- #
#  Themen
# --------------------------------------------------------------------------- #
# Ein Thema legt EINE Farbe je Rolle fest. "default" ist die bisherige
# Oberflaeche und dient gleichzeitig als Rueckfall fuer unvollstaendige Themen.
THEMES = {
    "default": {
        "window": "#181a1f", "sidebar": "#21252b", "cards": "#2e3440",
        "inner": "#3b4252", "borders": "#4c566a", "text": "#d8dee9",
        "secondary": "#7b88a1", "accent": "#5e81ac", "danger": "#bf616a",
    },
    "carbon": {
        "window": "#121212", "sidebar": "#1b1b1b", "cards": "#242424",
        "inner": "#2f2f2f", "borders": "#454545", "text": "#e4e4e4",
        "secondary": "#9a9a9a", "accent": "#8e8e8e", "danger": "#c05a5a",
    },
    "nebula": {
        "window": "#16121f", "sidebar": "#1e1830", "cards": "#2a2140",
        "inner": "#372c52", "borders": "#4d3f70", "text": "#e2dcf5",
        "secondary": "#9a8fbf", "accent": "#9d7cf0", "danger": "#c25c7a",
    },
    "embers": {
        "window": "#17110d", "sidebar": "#211711", "cards": "#2e2018",
        "inner": "#3d2c20", "borders": "#573f2d", "text": "#f2e3d6",
        "secondary": "#b09277", "accent": "#e07b39", "danger": "#c9524a",
    },
    "grass": {
        "window": "#101610", "sidebar": "#161f16", "cards": "#1f2c1f",
        "inner": "#2a3a2a", "borders": "#3d5240", "text": "#dfe9dc",
        "secondary": "#8ba189", "accent": "#6fae63", "danger": "#c2605c",
    },
    "ocean": {
        "window": "#101820", "sidebar": "#16212b", "cards": "#1f2e3a",
        "inner": "#2a3e4d", "borders": "#3c5669", "text": "#dceaf2",
        "secondary": "#84a1b3", "accent": "#3fa9c9", "danger": "#c2606a",
    },
    "rose": {
        "window": "#191014", "sidebar": "#22161b", "cards": "#301f27",
        "inner": "#402a34", "borders": "#5a3c49", "text": "#f4dfe6",
        "secondary": "#b78d9c", "accent": "#e0699a", "danger": "#c9525c",
    },
    "mono": {
        "window": "#0d0d0d", "sidebar": "#151515", "cards": "#1f1f1f",
        "inner": "#2b2b2b", "borders": "#3f3f3f", "text": "#f2f2f2",
        "secondary": "#8f8f8f", "accent": "#d0d0d0", "danger": "#a85454",
    },
}

THEME_ORDER = ["default", "carbon", "nebula", "embers", "grass", "ocean",
               "rose", "mono"]


# --------------------------------------------------------------------------- #
#  Farbrechnung
# --------------------------------------------------------------------------- #
def _rgb(hex_str):
    h = hex_str.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02x}" for c in rgb)


def _lightness(hex_str):
    r, g, b = _rgb(hex_str)
    return colorsys.rgb_to_hls(r, g, b)[1]


def shift_lightness(hex_str, delta):
    """Farbe um einen Helligkeitsabstand verschieben (HLS, Farbton bleibt)."""
    r, g, b = _rgb(hex_str)
    h, light, s = colorsys.rgb_to_hls(r, g, b)
    light = max(0.0, min(1.0, light + delta))
    return _hex(colorsys.hls_to_rgb(h, light, s))


def _build_offsets():
    """{grundfarbe: (rolle, helligkeitsabstand)} — einmal beim Import."""
    table = {}
    for role, shades in ROLE_BASES.items():
        ref = _lightness(shades[0])
        for shade in shades:
            table[shade.lower()] = (role, _lightness(shade) - ref)
    return table


_OFFSETS = _build_offsets()

# Hintergrund-Eigenschaften — nur hier darf die Kartendeckkraft eingreifen.
# Bei 'color:' waere halbdurchsichtiger TEXT die Folge.
_BG_PATTERN = re.compile(
    r"(background(?:-color)?\s*:\s*)(#[0-9a-fA-F]{6})", re.IGNORECASE)
_HEX_PATTERN = re.compile(r"#[0-9a-fA-F]{6}")


# --------------------------------------------------------------------------- #
#  Einstellungen
# --------------------------------------------------------------------------- #
_state = {
    "theme": "default",
    "colors": {},          # rolle -> hex (Uebersteuerung durch den Nutzer)
    "background": "",      # Pfad zum Hintergrundbild ("" = keins)
    "card_opacity": 100,   # Prozent
}
_cache = {}


def settings_path():
    return paths.config_file(SETTINGS_FILE)


def load():
    """Gespeicherte Einstellungen einlesen (still, mit Rueckfall auf Standard)."""
    data = read_json(settings_path(), default={})
    if isinstance(data, dict):
        theme = data.get("theme")
        if theme in THEMES:
            _state["theme"] = theme
        colors = data.get("colors")
        if isinstance(colors, dict):
            _state["colors"] = {k: v for k, v in colors.items()
                                if k in ROLE_BASES and is_hex(v)}
        # Immer zuweisen, nicht nur bei Gueltigkeit: ein Bild, das inzwischen
        # geloescht oder auf einen USB-Stick verschoben wurde, muss aus dem
        # Zustand verschwinden — sonst zeigt die Oberflaeche weiter einen Pfad
        # an, hinter dem nichts mehr liegt.
        bg = data.get("background")
        _state["background"] = bg if (isinstance(bg, str) and bg
                                      and os.path.exists(bg)) else ""
        try:
            _state["card_opacity"] = max(20, min(100, int(data.get("card_opacity", 100))))
        except (TypeError, ValueError):
            _state["card_opacity"] = 100
    _cache.clear()
    return dict(_state)


def save():
    if not write_json_atomic(settings_path(), dict(_state)):
        log.warning("theme.json konnte nicht geschrieben werden.")
        return False
    return True


def is_hex(value):
    return isinstance(value, str) and bool(re.fullmatch(r"#[0-9a-fA-F]{6}", value))


def current():
    return dict(_state)


def role_color(role):
    """Aktive Farbe einer Rolle — Nutzerwahl schlaegt Thema."""
    override = _state["colors"].get(role)
    if is_hex(override):
        return override
    theme = THEMES.get(_state["theme"], THEMES["default"])
    return theme.get(role, THEMES["default"][role])


def set_theme(name):
    if name in THEMES:
        _state["theme"] = name
        # Beim Themenwechsel sollen die Themenfarben auch wirklich sichtbar
        # werden — sonst ueberdecken alte Einzelfarben das neue Thema.
        _state["colors"] = {}
        _cache.clear()


def set_color(role, hex_value):
    if role in ROLE_BASES and is_hex(hex_value):
        _state["colors"][role] = hex_value
        _cache.clear()


def reset_colors():
    _state["colors"] = {}
    _cache.clear()


def set_background(path):
    _state["background"] = path or ""


def set_card_opacity(percent):
    _state["card_opacity"] = max(20, min(100, int(percent)))
    _cache.clear()


def is_default():
    """True, wenn nichts vom Auslieferungszustand abweicht."""
    return (_state["theme"] == "default" and not _state["colors"]
            and not _state["background"] and _state["card_opacity"] == 100)


# --------------------------------------------------------------------------- #
#  Ersetzen
# --------------------------------------------------------------------------- #
def map_color(hex_str):
    """Eine Grundfarbe auf die Farbe des aktiven Themas abbilden."""
    key = hex_str.lower()
    if key in _cache:
        return _cache[key]
    entry = _OFFSETS.get(key)
    if entry is None:
        result = hex_str            # Signalfarben & Unbekanntes bleiben
    else:
        role, delta = entry
        result = shift_lightness(role_color(role), delta)
    _cache[key] = result
    return result


def _rgba(hex_str, alpha_percent):
    h = hex_str.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha_percent / 100:.2f})"


def tint(css):
    """
    Ein Stylesheet auf das aktive Thema umstellen.

    Im Standardthema ohne Aenderungen kommt die Zeichenkette unveraendert
    zurueck — dann wird auch nichts neu gesetzt.
    """
    if not css or is_default():
        return css

    opacity = _state["card_opacity"]

    def bg_sub(match):
        prop, color = match.group(1), match.group(2)
        mapped = map_color(color)
        # Deckkraft nur auf Karten/Innenflaechen: das Fenster selbst muss
        # deckend bleiben, sonst scheint der Desktop durch.
        role = _OFFSETS.get(color.lower(), (None, 0))[0]
        if opacity < 100 and role in ("cards", "inner"):
            return prop + _rgba(mapped, opacity)
        return prop + mapped

    css = _BG_PATTERN.sub(bg_sub, css)
    return _HEX_PATTERN.sub(lambda m: map_color(m.group(0)), css)


_app_base_qss = None


def apply_to_app(app):
    """
    Das Stylesheet der QApplication umfaerben.

    Ohne diesen Schritt bleibt die grosse Flaeche hinter den Karten in der
    Ausgangsfarbe: ``QStackedWidget { background-color: #181a1f; }`` und die
    Regeln fuer Dialoge, Menues und Tooltips stehen naemlich nicht an einem
    Widget, sondern an der Anwendung selbst — und apply_to_tree() laeuft nur
    ueber Widgets. Ergebnis waere ein umgefaerbtes Fenster mit einem
    Seitenhintergrund in der alten Farbe.
    """
    global _app_base_qss
    if app is None:
        return False
    if _app_base_qss is None:
        _app_base_qss = app.styleSheet()
    app.setStyleSheet(tint(_app_base_qss))
    return True


def window_background_css():
    """Stylesheet-Schnipsel fuer das Hintergrundbild (oder "")."""
    bg = _state["background"]
    if not bg or not os.path.exists(bg):
        return ""
    # border-image skaliert auf die Fenstergroesse, ohne zu kacheln.
    return f'#yk_root {{ border-image: url("{bg}") 0 0 0 0 stretch stretch; }}'


# --------------------------------------------------------------------------- #
#  Anwenden auf ein bestehendes Fenster
# --------------------------------------------------------------------------- #
_BASE_PROPERTY = "yk_base_qss"
# Widgets mit dieser Eigenschaft bleiben, wie sie sind. Gebraucht wird das fuer
# die Themen-Vorschaukacheln: sie ZEIGEN ja gerade die Farben eines anderen
# Themas. Wuerden sie mitgefaerbt, sahen alle acht Kacheln gleich aus und die
# Vorschau waere nutzlos.
_SKIP_PROPERTY = "yk_no_tint"


def apply_to_tree(root):
    """
    Alle Stylesheets unterhalb von ``root`` (inklusive) umfaerben.

    Das Original wird beim ersten Mal am Widget hinterlegt. Nur so laesst sich
    spaeter erneut faerben, ohne bereits ersetzte Farben ein zweites Mal zu
    ersetzen — was nach zwei Themenwechseln zu Farbmatsch fuehren wuerde.
    """
    if root is None:
        return 0
    from PySide6.QtWidgets import QWidget
    widgets = [root] + root.findChildren(QWidget)
    count = 0
    for widget in widgets:
        if widget.property(_SKIP_PROPERTY):
            continue
        base = widget.property(_BASE_PROPERTY)
        if base is None:
            base = widget.styleSheet()
            widget.setProperty(_BASE_PROPERTY, base)
        if not base:
            continue
        widget.setStyleSheet(tint(base))
        count += 1
    return count
