#!/usr/bin/env python3
"""
queryfix_widget.py — UI für den Quick OSC Query Fix (Settings-Tab)
==================================================================
PySide6-Portierung des portablen queryfix-Widgets (Original: PyQt6,
aus OSC-DreamChatbox), angepasst an das Nord-Design und das
Übersetzungssystem (translations.tr) von yakuda-connect.

Aufbau:
    [ Quick OSC Query Fix                (🔧 Fix OSCQuery) ]
    [ Beschreibung                                          ]
    [ ▸ Unterstützte Programme anzeigen (N)                 ]  <- Expander
    [   scrollbare Liste (feste Maximalhöhe)                ]
    [   Detail-Box (Pfad + Parameter), klappt pro Eintrag   ]
    [ Ergebniszeilen nach dem Fix                           ]

Einbau (macht ui_main.py):
    from ui.queryfix_widget import QueryFixWidget
    self.oscquery_widget = QueryFixWidget()
    layout.addWidget(self.oscquery_widget)

Die Programmliste lebt in core/queryfix.py (PROGRAMS) — dort ein
Dict anhängen, und Liste/Details/Fix ziehen automatisch nach.
"""

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QGroupBox, QHBoxLayout, QLabel,
                               QListWidget, QPushButton, QVBoxLayout, QWidget)

# core/ liegt auf dem sys.path (starter.py/ui_main.py hängen ihn an) —
# zur Sicherheit hier trotzdem nochmal, damit das Widget auch standalone läuft.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'core')))
import queryfix
from translations import tr


class QueryFixWidget(QGroupBox):
    """Komplette OSCQuery-Fix-Box: Fix-Button, auf-/zuklappbare
    scrollbare Programmliste, Detail-Klappe pro Programm, Ergebnisanzeige."""

    def __init__(self, log_fn=print, parent=None):
        super().__init__(tr("oscquery_group"), parent)
        self.log = log_fn
        self._details_idx = -1

        root = QVBoxLayout(self)
        root.setSpacing(8)

        # --- Beschreibung ---
        self.lbl_desc = QLabel(tr("oscquery_desc"))
        self.lbl_desc.setStyleSheet("color: #d8dee9; font-size: 11px;")
        self.lbl_desc.setWordWrap(True)
        root.addWidget(self.lbl_desc)

        # --- Button-Reihe: Fix + Expander ---
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_fix = QPushButton(tr("oscquery_fix_btn"))
        self.btn_fix.setCursor(Qt.PointingHandCursor)
        self.btn_fix.setStyleSheet("""
            QPushButton { background-color: #5e81ac; color: white; border: none;
                          font-weight: bold; padding: 8px 14px; border-radius: 4px; font-size: 12px; }
            QPushButton:hover { background-color: #81a1c1; }
            QPushButton:disabled { background-color: #3b4252; color: #7b88a1; }
        """)
        self.btn_fix.clicked.connect(self.on_fix)
        btn_row.addWidget(self.btn_fix)

        self.btn_expander = QPushButton()
        self.btn_expander.setCursor(Qt.PointingHandCursor)
        self.btn_expander.setStyleSheet("""
            QPushButton { background-color: #2e3440; color: #d8dee9; border: 1px solid #4c566a;
                          font-weight: bold; padding: 8px 14px; border-radius: 4px; font-size: 12px; }
            QPushButton:hover { background-color: #3b4252; border-color: #5e81ac; }
        """)
        self.btn_expander.clicked.connect(self.on_expand)
        btn_row.addWidget(self.btn_expander)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # --- Ausklappbarer Bereich: Liste + Details ---
        self.body = QWidget()
        body_l = QVBoxLayout(self.body)
        body_l.setContentsMargins(0, 4, 0, 0)
        body_l.setSpacing(6)

        self.list = QListWidget()
        self.list.setMaximumHeight(140)   # feste Höhe -> Scrollbar bei vielen Einträgen
        self.list.setStyleSheet("""
            QListWidget { background-color: #21252b; border: 1px solid #2e3440;
                          border-radius: 6px; padding: 4px; color: #eceff4; font-size: 12px; }
            QListWidget::item { padding: 5px 8px; border-radius: 4px; }
            QListWidget::item:hover { background-color: #2e3440; }
            QListWidget::item:selected { background-color: #3b4252; color: #ffffff; }
        """)
        for prog in queryfix.PROGRAMS:
            self.list.addItem(prog["name"])
        self.list.itemClicked.connect(self.on_select)
        body_l.addWidget(self.list)

        self.details = QFrame()
        self.details.setStyleSheet(
            "QFrame { background-color: #2e3440; border-radius: 4px; }")
        det_l = QVBoxLayout(self.details)
        det_l.setContentsMargins(12, 8, 12, 10)
        self.lbl_details = QLabel("")
        self.lbl_details.setStyleSheet(
            "color: #d8dee9; font-family: monospace; font-size: 11px; background: transparent;")
        self.lbl_details.setWordWrap(True)
        self.lbl_details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        det_l.addWidget(self.lbl_details)
        self.details.hide()
        body_l.addWidget(self.details)

        self.body.hide()
        root.addWidget(self.body)

        # --- Ergebnisanzeige ---
        self.lbl_result = QLabel("")
        self.lbl_result.setStyleSheet("color: #7b88a1; font-size: 11px;")
        self.lbl_result.setWordWrap(True)
        root.addWidget(self.lbl_result)

        self._update_expander_text()

    # ---------------------------------------------------------- Helpers
    def _update_expander_text(self):
        n = len(queryfix.PROGRAMS)
        if self.body.isHidden():
            self.btn_expander.setText(
                tr("oscquery_show_programs").format(n=n))
        else:
            self.btn_expander.setText(tr("oscquery_hide_programs"))

    def _details_text(self, prog):
        return (f"{prog['name']}\n"
                f"  {tr('oscquery_detail_path')}  {prog['path']}\n"
                f"  {tr('oscquery_detail_param')}  {queryfix.param_str(prog)}")

    # ---------------------------------------------------------- Handler
    def on_expand(self):
        """Klappt die Liste der unterstützten Programme ein/aus."""
        self.body.setVisible(self.body.isHidden())
        if self.body.isHidden():
            self.details.hide()
            self._details_idx = -1
            self.list.clearSelection()
        self._update_expander_text()

    def on_select(self, item):
        """Klick auf ein Programm: Details (Pfad + Parameter) unter der
        Liste ein-/ausklappen; erneuter Klick auf denselben Eintrag schließt."""
        idx = self.list.row(item)
        if idx == self._details_idx and not self.details.isHidden():
            self.details.hide()
            self._details_idx = -1
            self.list.clearSelection()
            return
        self.lbl_details.setText(self._details_text(queryfix.PROGRAMS[idx]))
        self.details.show()
        self._details_idx = idx

    def on_fix(self):
        """Wendet den Fix auf alle unterstützten Programme an und zeigt
        das Ergebnis pro Programm an."""
        results = queryfix.fix_all(self.log)
        parts = []
        for name, ok, code, detail in results:
            msg = tr(f"oscquery_msg_{code}")
            if detail:
                msg = f"{msg} ({detail})" if code in ("unreadable", "write_failed") \
                    else f"{msg} — {detail}"
            parts.append(f"{'✅' if ok else '❌'} {name}: {msg}")
        parts.append(tr("oscquery_restart_hint"))
        self.lbl_result.setText("\n".join(parts))

    # ---------------------------------------------------------- Sprache
    def retranslate(self):
        """Wird von ui_main.retranslate_ui() beim Sprachwechsel aufgerufen."""
        self.setTitle(tr("oscquery_group"))
        self.lbl_desc.setText(tr("oscquery_desc"))
        self.btn_fix.setText(tr("oscquery_fix_btn"))
        self._update_expander_text()
        if self._details_idx >= 0 and not self.details.isHidden():
            self.lbl_details.setText(
                self._details_text(queryfix.PROGRAMS[self._details_idx]))
        self.lbl_result.setText("")
