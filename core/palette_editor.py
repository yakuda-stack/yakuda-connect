#!/usr/bin/env python3
"""
palette_editor.py — WayVR-Farbpalette bearbeiten
================================================
Schreibt ~/.config/wayvr/palettes/yakuda.json und faerbt damit Watch UND
Tastatur, weil WayVR beide aus derselben Palette speist.

WICHTIG — WayVR parst die Palette strikt (serde deny_unknown_fields):
  * ALLE 17 Felder muessen vorhanden sein
  * KEIN zusaetzliches Feld ist erlaubt (auch kein "name", kein Kommentar)
  * Farben als #RRGGBB oder #RRGGBBAA
Deshalb wird beim Speichern immer die volle Palette geschrieben und vorher
gegen genau diese Feldliste geprueft.

Damit die UI nicht 17 Farbfelder zeigen muss, gibt es EDITABLE: eine kleine
Auswahl sprechender Farben. Der Rest wird daraus abgeleitet (siehe derive()),
vor allem die on_*-Farben — die muessen zu ihrem Grund kontrastieren, sonst
ist z. B. die Tastaturbeschriftung beim Hover unlesbar.
"""
import os
import json

HOME = os.path.expanduser("~")
WAYVR_DIR    = os.path.join(HOME, ".config/wayvr")
PALETTES_DIR = os.path.join(WAYVR_DIR, "palettes")
CONF_D       = os.path.join(WAYVR_DIR, "conf.d")
PALETTE_NAME = "yakuda.json"
PALETTE_PATH = os.path.join(PALETTES_DIR, PALETTE_NAME)
# Muss zu overlay_manager.YAKUDA_CONF passen
YAKUDA_CONF  = os.path.join(CONF_D, "zz-yakuda-palette.json5")

# Reihenfolge wie in wgui/src/color.rs — WayVR akzeptiert exakt diese Felder
FIELDS = [
    "primary", "on_primary",
    "secondary", "on_secondary",
    "tertiary", "on_tertiary",
    "danger", "on_danger",
    "background", "on_background",
    "background_variant", "on_background_variant",
    "background_contrast", "on_background_contrast",
    "outline", "shadow", "highlight",
]

DEFAULTS = {
    "primary": "#b7bdf8",
    "on_primary": "#1a1d23",
    "secondary": "#8bd5ca",
    "on_secondary": "#1a1d23",
    "tertiary": "#4c566a",
    "on_tertiary": "#eceff4",
    "danger": "#ed8796",
    "on_danger": "#1a1d23",
    "background": "#181b21",
    "on_background": "#eceff4",
    "background_variant": "#2b2f38",
    "on_background_variant": "#d8dee9",
    "background_contrast": "#23272f",
    "on_background_contrast": "#eceff4",
    "outline": "#3b4252",
    "shadow": "#12141a",
    "highlight": "#b7bdf8",
}

# Was in der UI auswaehlbar ist: (Schluessel, Uebersetzungs-Key)
EDITABLE = [
    ("primary",             "palette_c_accent"),
    ("highlight",           "palette_c_active"),
    ("tertiary",            "palette_c_keyboard"),
    ("background",          "palette_c_bg"),
    ("background_variant",  "palette_c_button"),
    ("background_contrast", "palette_c_panel"),
    ("outline",             "palette_c_border"),
    ("danger",              "palette_c_danger"),
]


def _parse_hex(h):
    """'#rrggbb' oder '#rrggbbaa' -> (r, g, b). Wirft bei Unsinn."""
    h = h.strip().lstrip("#")
    if len(h) not in (6, 8):
        raise ValueError(f"ungueltige Farbe: #{h}")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def is_valid_hex(h):
    try:
        _parse_hex(h)
        return h.strip().startswith("#") and len(h.strip().lstrip("#")) in (6, 8)
    except Exception:
        return False


def contrast_for(bg_hex, light="#eceff4", dark="#1a1d23"):
    """
    Waehlt Schwarz oder Weiss als Vordergrund — je nachdem, was auf bg_hex
    besser lesbar ist. Relative Helligkeit nach WCAG.
    """
    r, g, b = _parse_hex(bg_hex)

    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return dark if lum > 0.35 else light


def derive(base):
    """
    Ergaenzt eine Teil-Palette zur vollen 17er-Palette.
    Die on_*-Farben werden aus ihrem Grund berechnet, damit Text immer lesbar
    bleibt — besonders on_tertiary (Tastaturbeschriftung beim Hover).
    """
    p = dict(DEFAULTS)
    p.update({k: v for k, v in base.items() if k in FIELDS})

    for fg, bg in (("on_primary", "primary"),
                   ("on_secondary", "secondary"),
                   ("on_tertiary", "tertiary"),
                   ("on_danger", "danger"),
                   ("on_background", "background"),
                   ("on_background_variant", "background_variant"),
                   ("on_background_contrast", "background_contrast")):
        # Nur ableiten, wenn nicht ausdruecklich vorgegeben
        if fg not in base:
            try:
                p[fg] = contrast_for(p[bg])
            except Exception:
                pass
    return p


def validate(p):
    """Gibt eine Liste von Problemen zurueck; leer = WayVR wird das fressen."""
    problems = []
    missing = [f for f in FIELDS if f not in p]
    extra = [k for k in p if k not in FIELDS]
    if missing:
        problems.append(f"Fehlende Felder: {', '.join(missing)}")
    if extra:
        problems.append(f"Unerlaubte Felder: {', '.join(extra)}")
    for k, v in p.items():
        if k in FIELDS and not is_valid_hex(v):
            problems.append(f"{k}: ungueltige Farbe '{v}'")
    return problems


def load_palette():
    """Liest die Palette; faellt auf die Vorgabe zurueck, wenn nichts da ist."""
    try:
        with open(PALETTE_PATH, "r") as f:
            data = json.load(f)
        return {k: data.get(k, DEFAULTS[k]) for k in FIELDS}
    except Exception:
        return dict(DEFAULTS)


def save_palette(p, activate=True):
    """
    Schreibt die Palette atomar nach ~/.config/wayvr/palettes/yakuda.json.

    Legt dabei ALLES an, was dazugehört — auch wenn ~/.config/wayvr vorher
    gar nicht existierte (z. B. direkt nach "WayVR zurücksetzen"):
        ~/.config/wayvr/palettes/yakuda.json          die Farben
        ~/.config/wayvr/conf.d/zz-yakuda-palette.json5 aktiviert sie

    Ohne die conf.d-Datei läge die Palette nur herum und WayVR würde sie nie
    benutzen. 'zz-' sorgt dafür, dass sie zuletzt gelesen wird und gewinnt —
    WayVR liest conf.d alphabetisch.

    Die on_*-Farben werden dabei IMMER neu aus ihrem Grund berechnet und
    nicht aus p übernommen. Grund: die UI bietet sie gar nicht an, und
    load_palette() liefert stets alle 17 Felder. Würden wir sie durchreichen,
    bliebe on_tertiary beim alten Wert, sobald jemand tertiary ändert —
    weiße Schrift auf weißer Taste.
    """
    base = {k: v for k, v in p.items() if k in FIELDS and not k.startswith("on_")}
    full = derive(base)
    problems = validate(full)
    if problems:
        raise ValueError("; ".join(problems))

    os.makedirs(PALETTES_DIR, exist_ok=True)
    tmp = PALETTE_PATH + ".part"
    with open(tmp, "w") as f:
        json.dump({k: full[k] for k in FIELDS}, f, indent=2)
        f.write("\n")
    os.replace(tmp, PALETTE_PATH)

    if activate:
        _activate()
    return PALETTE_PATH


def _activate():
    """
    Trägt unsere Palette in eine eigene conf.d-Datei ein. Bewusst eine eigene
    Datei, damit die Config des Nutzers unangetastet bleibt.

    Der Wert braucht die .json-Endung: nur dann sucht WayVR in palettes/
    statt nach einer eingebauten Palette.
    """
    os.makedirs(CONF_D, exist_ok=True)
    tmp = YAKUDA_CONF + ".part"
    with open(tmp, "w") as f:
        f.write("// yakuda-connect: Farbpalette fuer Watch + Tastatur.\n")
        f.write("// Diese Datei gehoert yakuda-connect und wird beim Speichern\n")
        f.write("// der Farben ueberschrieben. Eigene Einstellungen woanders ablegen.\n")
        json.dump({"color_palette": PALETTE_NAME}, f, indent=2)
        f.write("\n")
    os.replace(tmp, YAKUDA_CONF)


def reset_palette():
    return save_palette(dict(DEFAULTS))
