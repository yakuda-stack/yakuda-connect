#!/usr/bin/env python3
"""
tests/test_encoder_hints.py — Erklaerung neben der Encoder-Auswahl
=================================================================
Der Streaming-Tab zeigt neben der Encoder-Liste, welcher Encoder zu welcher
Grafikkarte gehoert. Zwei Dinge koennen dabei still kaputtgehen:

1. **Die Listeneintraege sind zugleich Konfigurationswerte.** Ihr Text wandert
   ueber ``config_manager.sync_with_wivrn`` (kleingeschrieben) in WiVRns
   ``config.json``. Schreibt jemand die Erklaerung in den Eintrag selbst — aus
   "nvenc" wird "nvenc (Nvidia)" — landet genau das in der fremden Config und
   bedeutet dort nichts. Der Server startet dann nicht, und der Grund steht in
   einer Datei, in die niemand schaut.

2. **Die Angaben muessen zu WiVRn passen.** Sie stammen aus dessen
   ``docs/configuration.md``, Abschnitt ``encoder``:

       x264    software encoding
       nvenc   Nvidia hardware encoding
       vaapi   AMD/Intel hardware encoding
       vulkan  experimental, for any GPU that supports vulkan video encode
"""
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "ui"))
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def tab(qapp):
    """Ein aufgebauter Streaming-Tab (offscreen).

    Die QApplication kommt aus tests/conftest.py und lebt laenger als dieses
    Fixture — eine eigene hier anzulegen war die Ursache dafuer, dass der Lauf
    beim Aufraeumen abstuerzte.
    """
    import tempfile
    os.environ["HOME"] = tempfile.mkdtemp(prefix="yakuda-enc-")

    from streaming_tab import StreamingTab
    widget = StreamingTab()
    widget.show()
    qapp.processEvents()
    yield widget

    # Siehe tests/conftest.py: deterministisch abraeumen, solange die
    # QApplication lebt — sonst stuerzt der Lauf am Ende ab.
    import shiboken6
    widget.close()
    shiboken6.delete(widget)
    qapp.processEvents()


# --------------------------------------------------------------------------- #
#  Die Eintraege duerfen sich nicht veraendern
# --------------------------------------------------------------------------- #
def test_listeneintraege_bleiben_reine_konfigurationswerte(tab):
    """
    Kein Erklaertext im Eintrag selbst — sonst steht er hinterher in WiVRns
    config.json.
    """
    combo = tab.combo_encoder
    eintraege = [combo.itemText(i) for i in range(combo.count())]
    assert eintraege == ["Auto", "nvenc", "vaapi", "Vulkan", "x264"]
    for eintrag in eintraege:
        assert "(" not in eintrag, f"Erklaerung im Eintrag gelandet: {eintrag}"
        assert " " not in eintrag, f"Leerzeichen im Konfigurationswert: {eintrag}"


def test_gewaehlter_wert_kommt_unveraendert_in_der_config_an(tab):
    """
    Der Weg, den der Wert wirklich nimmt: currentText().lower() landet als
    'encoder' in WiVRns Konfiguration (config_manager.sync_with_wivrn).
    """
    for eintrag, erwartet in (("nvenc", "nvenc"), ("vaapi", "vaapi"),
                              ("Vulkan", "vulkan"), ("x264", "x264")):
        tab.combo_encoder.setCurrentText(eintrag)
        assert tab.combo_encoder.currentText().lower() == erwartet


# --------------------------------------------------------------------------- #
#  Die Erklaerung selbst
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("lang", ["en", "de"])
def test_jeder_encoder_hat_eine_erklaerung(tab, lang):
    from translations import set_language
    set_language(lang)
    tab.retranslate()
    try:
        for i in range(tab.combo_encoder.count()):
            tab.combo_encoder.setCurrentIndex(i)
            text = tab.lbl_encoder_hint.text()
            name = tab.combo_encoder.itemText(i)
            assert text, f"{lang}/{name}: keine Erklaerung"
            assert not text.startswith("streaming_enc_"), \
                f"{lang}/{name}: unuebersetzt ({text})"
    finally:
        set_language("en")
        tab.retranslate()


@pytest.mark.parametrize("lang", ["en", "de"])
def test_jeder_eintrag_hat_einen_tooltip(tab, lang):
    """Sichtbar schon beim Aufklappen — also bevor man ausgewaehlt hat."""
    from PySide6.QtCore import Qt

    from translations import set_language
    set_language(lang)
    tab.retranslate()
    try:
        for i in range(tab.combo_encoder.count()):
            tip = tab.combo_encoder.itemData(i, Qt.ToolTipRole)
            assert tip, f"{lang}: Tooltip fehlt fuer {tab.combo_encoder.itemText(i)}"
    finally:
        set_language("en")
        tab.retranslate()


def test_erklaerungen_nennen_die_richtige_hardware(tab):
    """Abgeglichen mit WiVRns docs/configuration.md (Abschnitt 'encoder')."""
    from translations import set_language, tr
    set_language("en")
    erwartet = {
        "streaming_enc_nvenc":  ["nvidia"],
        "streaming_enc_vaapi":  ["amd", "intel"],
        "streaming_enc_vulkan": ["vulkan", "experimental"],
        "streaming_enc_x264":   ["software", "cpu"],
    }
    for key, woerter in erwartet.items():
        text = tr(key).lower()
        for wort in woerter:
            assert wort in text, f"{key}: '{wort}' fehlt in '{text}'"


def test_vulkan_ist_als_experimentell_gekennzeichnet():
    """
    WiVRn nennt vulkan ausdruecklich experimentell und beschraenkt es auf
    h264/h265. Das zu verschweigen waere die bequemere, aber falsche Angabe —
    'laeuft auf jeder modernen GPU' allein weckt zu viel Vertrauen.
    """
    from translations import set_language, tr
    for lang, wort in (("en", "experimental"), ("de", "experimentell")):
        set_language(lang)
        assert wort in tr("streaming_enc_vulkan").lower(), f"{lang}: Hinweis fehlt"
    set_language("en")


def test_sammel_tooltip_listet_alle_vier_encoder():
    from translations import set_language, tr
    for lang in ("en", "de"):
        set_language(lang)
        text = tr("streaming_encoder_tip").lower()
        for name in ("nvenc", "vaapi", "vulkan", "x264"):
            assert name in text, f"{lang}: {name} fehlt im Tooltip"
    set_language("en")
