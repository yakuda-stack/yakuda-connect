#!/usr/bin/env python3
"""
tests/conftest.py — gemeinsame Vorbereitung fuer die Qt-Tests
=============================================================
Hier steht genau eine Sache, und die ist wichtiger, als sie aussieht:
**eine einzige QApplication fuer den ganzen Testlauf, deren Referenz
festgehalten wird.**

Warum
-----
Qt-Widgets gehoeren zu einer QApplication. Raeumt Python das
QApplication-Objekt ab, waehrend noch Widgets leben, faehrt Qt den Speicher
unter ihnen weg — der Testlauf endet dann mit

    malloc_consolidate(): unaligned fastbin chunk detected
    Aborted

und zwar NACH der letzten bestandenen Pruefung, beim Aufraeumen. Genau das
passierte, als zwei Testmodule sich ihre QApplication jeweils selbst in einer
lokalen Variablen anlegten: sobald die Fixture-Funktion zurueckkam, war die
Referenz weg, das Objekt wurde eingesammelt, und die noch offenen Widgets des
anderen Moduls standen im Leeren. Reproduzierbar war das nur in etwa zwei von
drei Laeufen — Speicherfehler sind selten hoeflich genug, immer aufzutreten.

Die Fixture hier hat ``scope="session"`` und legt die Referenz zusaetzlich in
einer Modulvariablen ab. Damit lebt die QApplication laenger als jedes
modulweite Fixture, und die Widgets werden in der richtigen Reihenfolge
abgeraeumt: erst sie, dann die Anwendung.

tests/smoke.py macht dasselbe (dort mit einem ausdruecklichen ``noqa``), ist
aber ein eigenstaendiges Skript und braucht diese Datei nicht.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Haelt die QApplication am Leben, bis der Prozess endet. NICHT entfernen,
# auch wenn keine andere Stelle sie liest — siehe Modul-Docstring.
_app = None


@pytest.fixture(scope="session")
def qapp():
    """Die eine QApplication fuer alle Tests."""
    global _app
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    return _app
