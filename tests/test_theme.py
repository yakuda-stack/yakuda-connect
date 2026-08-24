#!/usr/bin/env python3
"""
tests/test_theme.py — Farbthemen
=================================
Die Oberflaeche hat rund 400 fest eingetragene Farbwerte. Statt jedes
Stylesheet umzuschreiben, ersetzt ui/theme.py die Farben beim Anwenden.
Das steht und faellt mit vier Eigenschaften, die hier geprueft werden:

  1. Standardthema = keine Aenderung. Wer nichts umstellt, sieht exakt das,
     was er vorher gesehen hat.
  2. Signalfarben bleiben. Gruen heisst "laeuft", Gelb heisst "Achtung" —
     das darf kein Thema umdeuten.
  3. Wiederholbar. Zweimal faerben darf nicht zweimal ersetzen, sonst wandert
     die Farbe bei jedem Themenwechsel weiter.
  4. Umkehrbar. Zurueck auf Standard muss wirklich der Ausgangszustand sein.
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT))

CSS = ("QLabel { background-color: #2e3440; color: #d8dee9; "
       "border: 1px solid #4c566a; } "
       "QPushButton { background: #5e81ac; color: #a3be8c; } "
       "QLabel#warn { color: #ebcb8b; }")


@pytest.fixture
def theme(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    from ui import theme as mod
    mod.set_theme("default")
    mod.reset_colors()
    mod.set_background("")
    mod.set_card_opacity(100)
    return mod


# --------------------------------------------------------------------------- #
#  1. Standard aendert nichts
# --------------------------------------------------------------------------- #
def test_standard_laesst_alles_wie_es_war(theme):
    assert theme.is_default() is True
    assert theme.tint(CSS) == CSS


def test_leeres_stylesheet_bleibt_leer(theme):
    theme.set_theme("ocean")
    assert theme.tint("") == ""
    assert theme.tint(None) is None


# --------------------------------------------------------------------------- #
#  2. Signalfarben
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["carbon", "nebula", "embers", "grass",
                                  "ocean", "rose", "mono"])
def test_gruen_und_gelb_bleiben(theme, name):
    theme.set_theme(name)
    ergebnis = theme.tint(CSS)
    assert "#a3be8c" in ergebnis, "Gruen (installiert/laeuft) wurde umgefaerbt"
    assert "#ebcb8b" in ergebnis, "Gelb (Achtung) wurde umgefaerbt"


@pytest.mark.parametrize("name", ["carbon", "nebula", "embers", "grass",
                                  "ocean", "rose", "mono"])
def test_thema_faerbt_wirklich_um(theme, name):
    theme.set_theme(name)
    ergebnis = theme.tint(CSS)
    assert "#2e3440" not in ergebnis      # Kartenfarbe ersetzt
    assert "#5e81ac" not in ergebnis      # Akzent ersetzt
    assert ergebnis != CSS


# --------------------------------------------------------------------------- #
#  3./4. Wiederholbar und umkehrbar
# --------------------------------------------------------------------------- #
def test_zweimal_faerben_aendert_nichts(theme):
    theme.set_theme("nebula")
    einmal = theme.tint(CSS)
    # tint() arbeitet immer auf dem ORIGINAL — genau das stellt apply_to_tree
    # ueber die gespeicherte Ausgangsfassung sicher.
    assert theme.tint(CSS) == einmal


def test_zurueck_auf_standard(theme):
    theme.set_theme("embers")
    assert theme.tint(CSS) != CSS
    theme.set_theme("default")
    assert theme.tint(CSS) == CSS


# --------------------------------------------------------------------------- #
#  Abstufungen, Deckkraft, Einzelfarben
# --------------------------------------------------------------------------- #
def test_abstufungen_bleiben_unterscheidbar(theme):
    """
    #2e3440 (Karten) und #3b4252 (innere Kaesten) sind zwei Ebenen. Faellt der
    Abstand weg, verschwinden die Kanten zwischen Kasten und Karte.
    """
    theme.set_theme("ocean")
    karte = theme.map_color("#2e3440")
    innen = theme.map_color("#3b4252")
    assert karte != innen
    assert theme._lightness(innen) > theme._lightness(karte)


def test_deckkraft_nur_auf_hintergruenden(theme):
    theme.set_theme("mono")
    theme.set_card_opacity(60)
    ergebnis = theme.tint(CSS)
    assert "rgba(" in ergebnis
    # Text darf NICHT durchsichtig werden. Achtung beim Pruefen: in
    # "background-color:" steckt "color:" mit drin — deshalb der Bindestrich
    # im Ausschluss.
    import re
    textfarben = re.findall(r"(?<!-)\bcolor:\s*(\S+?)[;\s}]", ergebnis)
    assert textfarben, "keine Textfarbe gefunden"
    assert all(v.startswith("#") for v in textfarben), textfarben


def test_fensterhintergrund_bleibt_deckend(theme):
    """Sonst scheint bei einem Hintergrundbild der Desktop durch das Fenster."""
    theme.set_theme("mono")
    theme.set_card_opacity(40)
    ergebnis = theme.tint("QWidget { background-color: #181a1f; }")
    assert "rgba(" not in ergebnis


def test_einzelfarbe_schlaegt_thema(theme):
    theme.set_theme("grass")
    theme.set_color("accent", "#ff0000")
    assert theme.role_color("accent") == "#ff0000"
    assert "#ff0000" in theme.tint(CSS)


def test_themenwechsel_raeumt_einzelfarben_weg(theme):
    """Sonst ueberdeckt eine alte Handfarbe das frisch gewaehlte Thema."""
    theme.set_color("accent", "#ff0000")
    theme.set_theme("rose")
    assert theme.role_color("accent") == theme.THEMES["rose"]["accent"]


def test_ungueltige_farbe_wird_ignoriert(theme):
    theme.set_color("accent", "rot")
    assert theme.role_color("accent") == theme.THEMES["default"]["accent"]


# --------------------------------------------------------------------------- #
#  Speichern und Laden
# --------------------------------------------------------------------------- #
def test_einstellungen_ueberleben_neustart(theme):
    theme.set_theme("embers")
    theme.set_color("cards", "#123456")
    theme.set_card_opacity(75)
    assert theme.save() is True

    theme.set_theme("default")
    theme.reset_colors()
    theme.set_card_opacity(100)
    theme.load()

    assert theme.current()["theme"] == "embers"
    assert theme.role_color("cards") == "#123456"
    assert theme.current()["card_opacity"] == 75


def test_kaputte_datei_wirft_nicht(theme):
    """Eine unbrauchbare theme.json darf den Start nicht verhindern."""
    path = pathlib.Path(theme.settings_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{kein json", encoding="utf-8")
    theme.load()
    assert theme.current()["theme"] in theme.THEMES


def test_verschwundenes_hintergrundbild_wird_verworfen(theme, tmp_path):
    theme.set_background(str(tmp_path / "gibtsnicht.png"))
    theme.save()
    theme.load()
    assert theme.current()["background"] == ""


def test_hintergrund_css_nur_mit_datei(theme, tmp_path):
    assert theme.window_background_css() == ""
    bild = tmp_path / "bg.png"
    bild.write_bytes(b"\x89PNG")
    theme.set_background(str(bild))
    css = theme.window_background_css()
    assert "yk_root" in css and str(bild) in css


# --------------------------------------------------------------------------- #
#  Vollstaendigkeit
# --------------------------------------------------------------------------- #
def test_jedes_thema_kennt_jede_rolle(theme):
    for name, farben in theme.THEMES.items():
        for rolle in theme.ROLE_BASES:
            assert rolle in farben, f"{name} fehlt die Rolle {rolle}"
            assert theme.is_hex(farben[rolle]), f"{name}/{rolle} ist kein Hexwert"


def test_alle_themen_sind_gelistet(theme):
    assert set(theme.THEME_ORDER) == set(theme.THEMES)


def test_beschriftungen_vorhanden(theme):
    import json
    for lang in ("en", "de"):
        data = json.loads((ROOT / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        for key in theme.ROLE_LABEL_KEYS.values():
            assert key in data, f"{key} fehlt in {lang}.json"
        for key in ("settings_sub_design", "design_group", "design_hint",
                    "design_colors", "design_background", "design_card_opacity"):
            assert key in data, f"{key} fehlt in {lang}.json"


# --------------------------------------------------------------------------- #
#  Anwendungs-Stylesheet und Ausnahmen
# --------------------------------------------------------------------------- #
def test_app_stylesheet_wird_mitgefaerbt(theme):
    """
    Die Flaeche hinter den Karten kommt aus dem Stylesheet der QApplication
    (QStackedWidget), nicht von einem Widget. Wird sie vergessen, steht ein
    umgefaerbtes Fenster auf einem Hintergrund in der alten Farbe — genau das
    war im Fehlerbild der rot markierte Bereich.
    """
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet("QStackedWidget { background-color: #181a1f; }")
    theme._app_base_qss = None            # Ausgangszustand neu erfassen

    theme.set_theme("ocean")
    assert theme.apply_to_app(app) is True
    assert "#181a1f" not in app.styleSheet()

    # und wieder zurueck
    theme.set_theme("default")
    theme.apply_to_app(app)
    assert "#181a1f" in app.styleSheet()
    theme._app_base_qss = None


def test_app_ohne_instanz_stuerzt_nicht_ab(theme):
    assert theme.apply_to_app(None) is False


def test_vorschaukacheln_werden_ausgenommen(theme):
    """
    Die Themenkacheln zeigen die Farben IHRES Themas. Faerbt man sie mit,
    sehen alle acht gleich aus — im Fehlerbild trug "Default" die Orangetoene
    von "Embers".
    """
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication, QLabel, QWidget
    QApplication.instance() or QApplication([])

    root = QWidget()
    normal = QLabel(root)
    normal.setStyleSheet("QLabel { background-color: #2e3440; }")
    kachel = QLabel(root)
    kachel.setStyleSheet("QLabel { background-color: #2e3440; }")
    kachel.setProperty("yk_no_tint", True)

    theme.set_theme("embers")
    theme.apply_to_tree(root)

    assert "#2e3440" not in normal.styleSheet()
    assert "#2e3440" in kachel.styleSheet()
