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
# Keine Update-Checks gegen GitHub beim Start jedes VRApp (core/main.py).
# Die liefen beim Testende oft noch -> Qt bricht mit SIGABRT ab (Code 6/134).
os.environ.setdefault("YAKUDA_NO_STARTUP_NETCHECK", "1")

# Sicherheitsnetz: jeden gestarteten QThread merken und am Ende abwarten.
_threads = []


def _track_qthreads():
    import weakref
    from PySide6.QtCore import QThread
    if getattr(QThread.start, "_yc_tracked", False):
        return
    orig = QThread.start

    def start(self, *args, **kwargs):
        _threads.append(weakref.ref(self))
        return orig(self, *args, **kwargs)
    start._yc_tracked = True
    QThread.start = start


_track_qthreads()


def _guard_single_shots():
    """
    QTimer.singleShot ohne Kontext-Objekt feuert auch, wenn das Fenster
    dahinter schon geloescht ist (siehe _delete_closed_windows). Im echten
    Programm passiert das nicht, in Tests landet dann ein „Internal C++ object
    already deleted“ mitten in einem fremden Test. Solche Nachzuegler werden
    hier still verworfen, jeder andere Fehler bleibt sichtbar.
    """
    from PySide6.QtCore import QTimer
    if getattr(QTimer.singleShot, "_yc_guarded", False):
        return
    orig = QTimer.singleShot

    def guarded(*args, **kwargs):
        if len(args) == 2 and callable(args[1]):
            func = args[1]

            def safe():
                try:
                    func()
                except RuntimeError as exc:
                    if "already deleted" not in str(exc):
                        raise
            return orig(args[0], safe, **kwargs)
        return orig(*args, **kwargs)
    guarded._yc_guarded = True
    QTimer.singleShot = staticmethod(guarded)


_guard_single_shots()


# Exit-Code des Testlaufs, fuer den harten Ausstieg in pytest_unconfigure.
_exitstatus = None   # None = Lauf kam nie bis sessionfinish


def pytest_sessionfinish(session, exitstatus):
    global _exitstatus
    _exitstatus = int(exitstatus)
    still = []
    for ref in _threads:
        th = ref()
        try:
            if th is not None and th.isRunning():
                th.requestInterruption()
                th.quit()
                if not th.wait(15000):
                    still.append(type(th).__name__)
        except RuntimeError:
            pass
    if still:
        sys.stderr.write(f"\nconftest: Threads liefen noch: {still} — beende hart\n")
        sys.stderr.flush()
        sys.stdout.flush()
        os._exit(int(exitstatus))

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


@pytest.fixture(autouse=True)
def _delete_closed_windows():
    """
    Geschlossene Hauptfenster nach jedem Test wirklich loeschen.

    ``close()`` versteckt ein Fenster nur, Qt behaelt es samt allen Widgets.
    Jedes neue VRApp setzt aber das Stylesheet der QApplication, und Qt
    wendet das auf ALLE noch vorhandenen Widgets an — auch auf die der alten,
    geschlossenen Fenster. Dadurch wurde jeder Fensterstart langsamer als der
    vorige (0,4 s -> mehrere Sekunden), der ganze Lauf dauerte ueber 35 Minuten
    und test_theme lief zeitweise in den Timeout.

    Geloescht wird nur, was closeEvent schon aufgeraeumt hat
    (``_exit_cleanup_done``) — Fenster, die ein Modul noch weiter benutzt,
    bleiben unangetastet.
    """
    yield
    if "PySide6.QtWidgets" not in sys.modules:
        return
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return
    closed = [w for w in app.topLevelWidgets() if getattr(w, "_exit_cleanup_done", False)]
    for w in closed:
        w.deleteLater()
    if closed:
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


# --------------------------------------------------------------------------- #
#  Harter Ausstieg nach dem Testlauf (gegen SIGSEGV beim Beenden)
# --------------------------------------------------------------------------- #
# Alle Tests gruen, und trotzdem endete "pytest" mit Signal 11 (SIGSEGV):
# Der Absturz passiert erst NACH der Zusammenfassung, wenn Python beim
# Beenden die Qt-Objekte (Widgets, QApplication, Threads) in zufaelliger
# Reihenfolge abraeumt. Fuer Release-Skripte und die CI sieht das aus wie
# ein Fehlschlag, obwohl nichts kaputt ist.
#
# Loesung: Ganz zum Schluss — nachdem pytest alles ausgegeben und alle
# anderen Plugins fertig sind (trylast) — beenden wir den Prozess sofort
# mit dem ECHTEN Exit-Code. Qt raeumt dann gar nicht erst auf.
# Fehlgeschlagene Tests liefern also weiterhin einen Fehler-Code.
#
# os._exit() ueberspringt atexit — deshalb das Wegwerf-HOME hier selbst
# loeschen. Abschalten (z. B. zum Untersuchen des Absturzes):
#     YAKUDA_TEST_NO_HARD_EXIT=1 python3 -m pytest
@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    if os.environ.get("YAKUDA_TEST_NO_HARD_EXIT"):
        return
    # Nur der Haupt-Prozess — nicht ein pytest-xdist-Worker.
    if hasattr(config, "workerinput"):
        return
    # Kein Ergebnis (z. B. Aufruf-Fehler) -> pytest normal enden lassen,
    # sonst wuerde ein Fehler als 0 = Erfolg gemeldet.
    if _exitstatus is None:
        return
    shutil.rmtree(_TEST_HOME, ignore_errors=True)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exitstatus)
