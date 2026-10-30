#!/usr/bin/env python3
"""
core/tour_steps.py — Die Schritte der App-Tour
==============================================
Jeder Schritt:
  id       Schluessel der Texte: tour_<id>_title / tour_<id>_text (Locales)
  tab      Seite in der Sidebar (Index wie in ui_main: 0 Installation,
           1 Dashboard, 2 Streaming, 3 Tools, 4 Games, 5 Controls, 6 Settings)
           oder None = Seite nicht wechseln
  target   Funktion (Fenster -> Widget oder Liste von Widgets), an dem das
           goldene ⓘ pulsiert (Liste: Rahmen um alle zusammen).
           None = Karte mittig, ohne Markierung.
  subtab   optional: Funktion (Fenster -> (QTabWidget, Seite)) zum Umschalten
  image    optional: Bild aus assets/ fuer die Karte
  action   optional: Sonderknopf auf der Karte ("controls_install_all")

Eigene Bilder: liegt assets/tour/<id>.png (oder .jpg), zeigt die Karte es
automatisch — ohne Code-Aenderung.

Kein Qt-Import — die Liste laesst sich ohne Oberflaeche pruefen.
"""

DASHBOARD, STREAMING, TOOLS, GAMES, CONTROLS, SETTINGS = 1, 2, 3, 4, 5, 6
INSTALLATION = 0


def _ui(name):
    return lambda w: getattr(w.ui, name, None)


def _controls_cards(w):
    rows = getattr(w.ui, "controls_rows", {})
    cards = [(rows.get(k) or {}).get("card") for k in ("xr-hotas", "obah")]
    return [c for c in cards + [getattr(w.ui, "xrbinder_card", None)] if c is not None]


def _settings_page(name):
    return lambda w: (w.ui.settings_subtabs, getattr(w.ui, name, None))


def _tools_first(w):
    tabs = getattr(w.ui, "tools_subtabs", None)
    return (tabs, tabs.widget(0)) if tabs is not None else (None, None)


STEPS = [
    {"id": "intro", "tab": None, "target": None, "image": "yakuda_icon_512.png",
     "action": "language"},
    {"id": "install", "tab": INSTALLATION, "target": _ui("pkg_group")},
    {"id": "server", "tab": DASHBOARD, "target": _ui("toggle_server")},
    {"id": "perf", "tab": DASHBOARD, "target": _ui("btn_performance_setup")},
    {"id": "headsets", "tab": DASHBOARD, "target": _ui("headset_group")},
    {"id": "autostart", "tab": DASHBOARD, "target": _ui("autostart_group")},
    {"id": "compat", "tab": STREAMING,
     "target": lambda w: getattr(getattr(w, "streaming_settings", None), "compat_group", None)},
    {"id": "encoder", "tab": STREAMING,
     "target": lambda w: getattr(getattr(w, "streaming_settings", None), "encoder_group", None)},
    {"id": "profiles", "tab": STREAMING, "target": _ui("autostart_profiles_group")},
    {"id": "tools", "tab": TOOLS, "target": _ui("tools_subtabs"), "subtab": _tools_first},
    {"id": "games", "tab": GAMES, "target": _ui("btn_games_scan")},
    {"id": "controls", "tab": CONTROLS, "target": _controls_cards,
     "action": "controls_install_all"},
    {"id": "xrbinder", "tab": CONTROLS, "target": _ui("xrbinder_card")},
    {"id": "obah", "tab": CONTROLS, "target": _ui("obah_panel")},
    {"id": "design", "tab": SETTINGS, "target": _ui("settings_subtabs"),
     "subtab": _settings_page("page_settings_design")},
    {"id": "settings_vr", "tab": SETTINGS, "target": _ui("settings_subtabs"),
     "subtab": _settings_page("page_settings_vr")},
    {"id": "again", "tab": SETTINGS, "target": _ui("btn_tour"),
     "subtab": _settings_page("page_settings_general")},
    {"id": "done", "tab": None, "target": None},
]
