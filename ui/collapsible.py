#!/usr/bin/env python3
"""
ui/collapsible.py — Klapp-Kopfzeile fuer Bereiche (▾ / ▸)
=========================================================
Ein Pfeil-Knopf mit Titel, der einen Inhalts-Widget ein- und ausblendet.
Der Zustand wird je Bereich in config.json gemerkt
("collapsed_sections": {schluessel: true}).

    header = CollapsibleHeader("streaming_conn", body)
    header.setText("Titel")
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolButton

import paths
from jsonio import read_json, update_json

CONFIG_KEY = "collapsed_sections"


def _load():
    data = read_json(paths.config_file("config.json"), default={})
    sec = data.get(CONFIG_KEY) if isinstance(data, dict) else None
    return sec if isinstance(sec, dict) else {}


class CollapsibleHeader(QToolButton):
    def __init__(self, key, body, parent=None):
        super().__init__(parent)
        self.key = key
        self.body = body
        self.setObjectName("collapsibleHeader")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setStyleSheet("""
            QToolButton#collapsibleHeader { background:transparent; border:none; color:#88c0d0;
                                            font-size:13px; font-weight:bold; padding:2px 0; }
            QToolButton#collapsibleHeader:hover { color:#eceff4; }
        """)
        self.set_open(not _load().get(key, False), save=False)
        self.toggled.connect(lambda on: self.set_open(on))

    def setText(self, text):
        """„&“ ist bei Knoepfen ein Tastenkuerzel — hier soll es sichtbar sein."""
        super().setText((text or "").replace("&", "&&"))

    def set_open(self, is_open, save=True):
        self.blockSignals(True)
        self.setChecked(bool(is_open))
        self.blockSignals(False)
        self.setArrowType(Qt.DownArrow if is_open else Qt.RightArrow)
        self.body.setVisible(bool(is_open))
        if save:
            sec = _load()
            sec[self.key] = not is_open
            update_json(paths.config_file("config.json"), {CONFIG_KEY: sec})
