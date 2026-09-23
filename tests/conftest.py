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
import atexit
import os
import shutil
import sys
import tempfile

import pytest

# --------------------------------------------------------------------------- #
#  Eigenes Wegwerf-HOME fuer den ganzen Testlauf
# --------------------------------------------------------------------------- #
# Frueher schrieben einige Testdateien (exit_guard, gpu_select, obah_*,
# tool_launcher, xrbinder) in das ECHTE ~/.config/yakuda-connect: core/paths.py
# liest HOME beim Import, und wer vor dem Test-eigenen HOME importiert wurde,
# behielt den echten Pfad. Folgen: Tests veraenderten die Einstellungen des
# Entwicklers, und test_gpu_select schlug zufaellig fehl, sobald dort eine
# gespeicherte Grafikkarte stand.
#
# Diese Datei laedt pytest VOR allen Testmodulen — hier gesetzt, sieht jeder
# spaetere Import schon das Wegwerf-HOME. XDG_* fliegen raus, damit sie nicht
# doch wieder auf den echten Ordner zeigen. Tests, die ein eigenes HOME
# brauchen, setzen es wie bisher selbst (liegt dann ohnehin in tmp).
_TEST_HOME = tempfile.mkdtemp(prefix="yc-test-home-")
os.environ["HOME"] = _TEST_HOME
for _var in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
    os.environ.pop(_var, None)
atexit.register(shutil.rmtree, _TEST_HOME, ignore_errors=True)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Kein echter Server-Stopp und kein Waechter-Prozess aus Tests heraus —
# siehe core/exit_guard.py (DISABLE_ENV).
os.environ.setdefault("YAKUDA_NO_EXIT_GUARD", "1")

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


@pytest.fixture(autouse=True)
def _fresh_gpu_cache():
    """gpu_select merkt sich die Grafikkarten fuer die Sitzung — in Tests
    wuerde ein Test sonst die (gefaelschten) Karten des vorigen sehen."""
    mod = sys.modules.get("gpu_select")
    if mod is not None and hasattr(mod, "clear_cache"):
        mod.clear_cache()
    yield
