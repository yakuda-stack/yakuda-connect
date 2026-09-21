#!/usr/bin/env python3
"""
ui/no_wheel.py — Aufklapplisten reagieren nicht aufs Mausrad
============================================================
Wer mit dem Mausrad durch einen Tab scrollt und dabei ueber eine QComboBox
faehrt, aendert sonst still deren Auswahl (im Controls-Tab: Spiel,
Controller, Quelle — und damit die ganze Ansicht). Dieser Filter nimmt der
geschlossenen Combo das Rad weg und gibt es an das Elternfenster weiter,
damit die Seite ganz normal weiterscrollt. In der AUFGEKLAPPTEN Liste
scrollt das Rad wie gewohnt — die ist ein eigenes Fenster und wird hier
nicht angefasst.

install(app) einmal aufrufen; wirkt fuer alle Combos der App.
"""
from PySide6.QtCore import QCoreApplication, QEvent, QObject
from PySide6.QtWidgets import QComboBox


class _NoWheel(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and isinstance(obj, QComboBox):
            parent = obj.parentWidget()
            if parent is not None:
                # an die Seite weiterreichen: dort scrollt die ScrollArea
                QCoreApplication.sendEvent(parent, event)
            return True
        return False


_FILTER = None


def install(app):
    """Filter an der Anwendung anbringen (mehrfacher Aufruf ist harmlos)."""
    global _FILTER
    if app is None or _FILTER is not None:
        return _FILTER
    _FILTER = _NoWheel(app)
    app.installEventFilter(_FILTER)
    return _FILTER
