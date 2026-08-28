#!/usr/bin/env python3
"""
tests/test_background.py — Hintergrundbild
==========================================
Das Bild wurde bis v1.2.4 gespeichert, angezeigt (der Pfad stand in den
Einstellungen) — und war trotzdem nie zu sehen. Zwei Fehler lagen
uebereinander:

  * das Stylesheet am Wurzel-Widget zeichnete nichts, und
  * selbst wenn es gezeichnet haette, laege es unter dem deckenden
    Seitenstapel.

Deshalb pruefen die Tests hier nicht "ist der Pfad gespeichert" (das ging ja
schon), sondern das, was der Nutzer sieht: liegt ein Pixmap in der Ebene, hat
es Fenstergroesse, und liegt die Ebene ganz hinten?
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT))


@pytest.fixture
def bild(tmp_path):
    """Ein echtes PNG auf der Platte — kein Attrappen-Pfad."""
    from PySide6.QtGui import QColor, QPixmap
    pfad = tmp_path / "wallpaper.png"
    pixmap = QPixmap(400, 200)
    pixmap.fill(QColor("#ff0000"))
    assert pixmap.save(str(pfad)) is True
    return str(pfad)


@pytest.fixture
def ebene(qapp):
    from PySide6.QtWidgets import QWidget
    from ui.background import BackgroundLayer
    root = QWidget()
    root.resize(800, 600)
    # Sichtbar (offscreen), weil Qt versteckten Widgets keine Resize-Ereignisse
    # zustellt — und genau die haelt die Ebene auf Fenstergroesse.
    root.show()
    layer = BackgroundLayer(root)
    yield root, layer
    root.hide()


# --------------------------------------------------------------------------- #
#  1. Anzeigen
# --------------------------------------------------------------------------- #
def test_ohne_bild_bleibt_die_ebene_leer(ebene):
    _root, layer = ebene
    assert layer.set_image("") is False
    assert layer.isVisible() is False
    assert layer.path() == ""


def test_bild_wird_auf_fenstergroesse_gebracht(ebene, bild):
    root, layer = ebene
    assert layer.set_image(bild) is True
    assert layer.path() == bild
    # Das Bild ist 400x200, das Fenster 800x600 — angezeigt werden muss die
    # FENSTERgroesse (formatfuellender Ausschnitt), nicht die Bildgroesse.
    assert layer.pixmap().size().toTuple() == (800, 600)
    assert layer.geometry().size().toTuple() == (800, 600)


def test_bild_folgt_der_fenstergroesse(ebene, bild):
    root, layer = ebene
    layer.set_image(bild)
    root.resize(500, 400)
    assert layer.pixmap().size().toTuple() == (500, 400)


def test_kaputte_datei_fuehrt_nicht_zum_absturz(ebene, tmp_path):
    _root, layer = ebene
    kaputt = tmp_path / "kein_bild.png"
    kaputt.write_text("das ist kein PNG")
    assert layer.set_image(str(kaputt)) is False
    assert layer.path() == ""


def test_fehlende_datei_wird_still_uebergangen(ebene, tmp_path):
    _root, layer = ebene
    assert layer.set_image(str(tmp_path / "weg.png")) is False


# --------------------------------------------------------------------------- #
#  2. Wechseln und entfernen
# --------------------------------------------------------------------------- #
def test_bild_laesst_sich_wieder_entfernen(ebene, bild):
    _root, layer = ebene
    layer.set_image(bild)
    assert layer.set_image("") is False
    assert layer.isVisible() is False
    assert layer.path() == ""


def test_wechsel_auf_ein_anderes_bild(ebene, bild, tmp_path):
    from PySide6.QtGui import QColor, QPixmap
    _root, layer = ebene
    layer.set_image(bild)

    zweites = tmp_path / "zweites.png"
    pixmap = QPixmap(100, 100)
    pixmap.fill(QColor("#00ff00"))
    pixmap.save(str(zweites))
    assert layer.set_image(str(zweites)) is True
    assert layer.path() == str(zweites)


# --------------------------------------------------------------------------- #
#  3. Die Ebene darf nichts verdecken
# --------------------------------------------------------------------------- #
def test_ebene_liegt_hinter_den_bedienelementen(qapp, bild):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton, QWidget
    from ui.background import BackgroundLayer

    root = QWidget()
    root.resize(800, 600)
    knopf = QPushButton("Start", root)
    layer = BackgroundLayer(root)
    layer.set_image(bild)

    kinder = root.children()
    # lower() muss die Ebene VOR den Knopf sortieren — Qt zeichnet in dieser
    # Reihenfolge, das zuerst gezeichnete liegt also hinten.
    assert kinder.index(layer) < kinder.index(knopf)
    # Und Klicks muessen hindurchgehen, sonst waere die halbe App tot.
    assert layer.testAttribute(Qt.WA_TransparentForMouseEvents) is True


def test_ebene_wird_nicht_umgefaerbt(ebene):
    """Ein Thema faerbt Stylesheets um — an einem Bild gibt es nichts zu faerben."""
    _root, layer = ebene
    assert layer.property("yk_no_tint") is True


# --------------------------------------------------------------------------- #
#  4. Zusammenspiel mit den Einstellungen
# --------------------------------------------------------------------------- #
def test_theme_liefert_nur_vorhandene_pfade(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    from ui import theme

    theme.set_background("")
    assert theme.background_path() == ""
    assert theme.has_background() is False

    fehlt = tmp_path / "weg.png"
    theme.set_background(str(fehlt))
    assert theme.background_path() == ""       # Datei geloescht/verschoben

    da = tmp_path / "da.png"
    da.write_bytes(b"egal")
    theme.set_background(str(da))
    assert theme.background_path() == str(da)
    assert theme.has_background() is True
    theme.set_background("")


def test_stack_regel_traegt_den_schleier():
    """Die Flaeche hinter den Karten bekommt mit Bild einen leichten Schleier
    — und die Regel muss auf DIESEN Stapel begrenzt sein, sonst tragen die
    Sub-Tab-Stapel darin ihn ein zweites Mal auf."""
    from ui import theme
    css = theme.stack_tint_css()
    assert "QStackedWidget#ykpages" in css
    assert "rgba(" in css


def test_spalten_tint_faerbt_nur_hintergruende():
    """Sonst waere die SCHRIFT in der Seitenleiste halbdurchsichtig."""
    from ui import theme
    css = theme.make_translucent(
        "QListWidget { background-color: #1c1f26; color: #a6b2c0; }",
        theme.COLUMN_TINT)
    assert "rgba(" in css
    assert "color: #a6b2c0" in css


def test_bildregeln_nehmen_den_labels_den_hintergrund():
    """Ohne diese Regeln stehen dunkle Kaesten hinter jeder Beschriftung,
    sobald die Karte darueber durchscheinend wird."""
    from ui import theme
    assert "QLabel" in theme.IMAGE_SURFACES_CSS
    # QSlider gehoert NICHT dazu: sonst verschwindet der Griff.
    assert "QSlider" not in theme.IMAGE_SURFACES_CSS.split("{")[0]


# --------------------------------------------------------------------------- #
#  5. Die Fallen, die das Bild zweimal unsichtbar gemacht haben
# --------------------------------------------------------------------------- #
def test_kartenfarbe_folgt_dem_deckkraft_regler(tmp_path, monkeypatch):
    """
    Der Regler heisst "Deckkraft der Karten" — dann muss er die Farbe treffen,
    aus der die Karten wirklich gebaut sind (#21252b). Bis v1.2.5 wirkte er
    nur auf #2e3440, eine Farbe, die fast nirgends eine Karte einfaerbt: der
    Regler sah aus, als tue er nichts.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    from ui import theme

    theme.set_theme("default")
    theme.reset_colors()
    theme.set_card_opacity(80)
    ergebnis = theme.tint("QFrame#ykcard { background-color:#21252b; }")
    assert "rgba(" in ergebnis
    theme.set_card_opacity(100)


def test_dialoge_bleiben_deckend(tmp_path, monkeypatch):
    """Ein halbdurchsichtiger Dialog ueber laufendem Text ist unlesbar."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    from ui import theme

    theme.set_theme("default")
    theme.set_card_opacity(50)
    ergebnis = theme.tint("QDialog { background-color:#21252b; }",
                          allow_opacity=False)
    assert "rgba(" not in ergebnis
    theme.set_card_opacity(100)


def test_keine_blanken_qframe_selektoren():
    """
    QLabel erbt von QFrame. Ein Stylesheet mit blankem ``QFrame { ... }``
    faerbt deshalb JEDES Label darin mit — unsichtbar, solange die Farbe
    deckend ist, aber als dunkler Kasten im Bild, sobald die Karte
    durchscheinend wird. Deshalb gehoert in jede solche Regel ein Objektname.
    """
    import pathlib
    import re

    wurzel = pathlib.Path(__file__).resolve().parent.parent
    muster = re.compile(r"QFrame\s*\{")
    treffer = []
    for pfad in list((wurzel / "ui").rglob("*.py")) + list((wurzel / "core").rglob("*.py")):
        for nr, zeile in enumerate(pfad.read_text(encoding="utf-8").splitlines(), 1):
            # Kommentarzeilen auslassen — sonst ist die ERKLAERUNG dieser
            # Regel ihr erster Treffer. (Dieselbe Falle wie beim
            # APP_VERSION-Anker in core/main.py.)
            if zeile.lstrip().startswith("#"):
                continue
            if muster.search(zeile):
                treffer.append(f"{pfad.relative_to(wurzel)}:{nr}")
    assert not treffer, ("Blanker QFrame-Selektor (Objektnamen benutzen): "
                         + ", ".join(treffer))
