#!/usr/bin/env python3
"""
ui/no_wheel.py — Aufklapplisten reagieren nicht aufs Mausrad
============================================================
Wer mit dem Mausrad durch einen Tab scrollt und dabei ueber eine QComboBox
faehrt, aendert sonst still deren Auswahl (im Controls-Tab: Spiel,
Controller, Quelle — und damit die ganze Ansicht). Hier bekommt die
GESCHLOSSENE Combo das Rad nicht: das Ereignis wird ignoriert, Qt reicht es
von selbst ans Elternfenster weiter, und die Seite scrollt normal. In der
AUFGEKLAPPTEN Liste scrollt das Rad wie gewohnt — die ist ein eigenes Fenster.

Performance: Frueher hing dafuer ein Event-Filter an der ganzen
QApplication. Dann laeuft JEDES Ereignis der App (Mausbewegung, Neuzeichnen,
Timer …) durch Python — beim Start allein ueber 100.000 Mal. Jetzt wird nur
QComboBox.wheelEvent ersetzt: kostet nichts, solange niemand ueber einer
Combo scrollt. Gilt fuer alle Combos, die aus Python erzeugt werden (auch
schon vorhandene); Combos in reinen Qt-Dialogen bleiben unberuehrt.

install(app) einmal aufrufen; mehrfacher Aufruf ist harmlos.
"""
from PySide6.QtWidgets import QComboBox

_INSTALLED = False


def _wheel_ignored(self, event):
    event.ignore()          # -> Qt gibt das Rad an das Elternfenster weiter


def install(app=None):
    """Mausrad fuer geschlossene Aufklapplisten abschalten."""
    global _INSTALLED
    if not _INSTALLED:
        QComboBox.wheelEvent = _wheel_ignored
        _INSTALLED = True
    return _INSTALLED
