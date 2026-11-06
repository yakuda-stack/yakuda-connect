#!/usr/bin/env python3
"""
ui/auto_height_text.py — Textfeld, das immer so hoch ist wie sein Inhalt
========================================================================
Fuer Texte in einer Seite mit Scrollbereich: gescrollt wird die Seite, das
Feld selbst zeigt den ganzen Text und hat keinen eigenen Rollbalken.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTextEdit


class AutoHeightTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.document().contentsChanged.connect(self._fit_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_height()

    def _fit_height(self):
        document = self.document()
        document.setTextWidth(self.viewport().width())
        chrome = self.height() - self.viewport().height()
        height = int(document.size().height()) + chrome + 2
        if height != self.height():
            self.setFixedHeight(height)
