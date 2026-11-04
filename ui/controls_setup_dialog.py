#!/usr/bin/env python3
"""
ui/controls_setup_dialog.py — Einmal-Frage beim ersten Besuch im Controls-Tab
=============================================================================
Drei Haken mit je einem Satz, wofuer das Werkzeug gut ist:

    ☑ xrBinder   Deadzone gegen Stick-Drift, Tasten in OpenXR-Spielen
    ☑ obah       Tasten in SteamVR-Spielen umbelegen
    ☐ XR HOTAS   Flug-/Weltraumspiele (vorausgewaehlt, wenn solche Spiele
                 im Games-Tab gefunden wurden)

Schon Installiertes steht als „✓ installiert“ da und ist nicht waehlbar.
Knoepfe: Installieren / Spaeter / Nicht mehr fragen. Nur Oberflaeche —
die Logik steckt in core/tabs/controls_setup_mixin.py.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout)

from translations import tr
from ui.binding_dialog import DIALOG_CSS

INSTALL, LATER, NEVER = "install", "later", "never"


class ControlsSetupDialog(QDialog):
    """items: [(key, name, desc, installed, preselect)]"""

    def __init__(self, parent, items):
        super().__init__(parent)
        self.setObjectName("controlsSetupDialog")
        self.setStyleSheet(DIALOG_CSS)
        self.setModal(True)
        self.resize(560, 380)
        self.setWindowTitle(tr("ctlsetup_title"))
        self.choice = LATER
        self.checks = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)
        title = QLabel("🎮  " + tr("ctlsetup_title"))
        title.setObjectName("bdtitle")
        root.addWidget(title)
        intro = QLabel(tr("ctlsetup_intro"))
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#a6b2c0; font-size:12px;")
        root.addWidget(intro)

        panel = QFrame()
        panel.setObjectName("bdpanel")
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(14, 12, 14, 12)
        pv.setSpacing(4)
        for key, name, desc, installed, preselect in items:
            cb = QCheckBox(name + ("   " + tr("ctlsetup_installed") if installed else ""))
            cb.setChecked(bool(installed or preselect))
            cb.setEnabled(not installed)
            cb.setCursor(Qt.PointingHandCursor)
            cb.setStyleSheet("QCheckBox { color:#eceff4; font-weight:bold; font-size:13px; }"
                             "QCheckBox:disabled { color:#a3be8c; }")
            pv.addWidget(cb)
            lbl = QLabel(desc)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color:#a6b2c0; font-size:11px; margin-left:24px; margin-bottom:8px;")
            pv.addWidget(lbl)
            if not installed:
                self.checks[key] = cb
        root.addWidget(panel, 1)

        hint = QLabel(tr("ctlsetup_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#4c566a; font-size:11px;")
        root.addWidget(hint)

        foot = QHBoxLayout()
        btn_never = QPushButton(tr("ctlsetup_never"))
        btn_never.setCursor(Qt.PointingHandCursor)
        btn_never.clicked.connect(lambda: self._done(NEVER))
        foot.addWidget(btn_never)
        foot.addStretch()
        btn_later = QPushButton(tr("ctlsetup_later"))
        btn_later.setCursor(Qt.PointingHandCursor)
        btn_later.clicked.connect(lambda: self._done(LATER))
        foot.addWidget(btn_later)
        self.btn_install = QPushButton("⬇  " + tr("ctlsetup_install"))
        self.btn_install.setObjectName("bdprimary")
        self.btn_install.setCursor(Qt.PointingHandCursor)
        self.btn_install.setDefault(True)
        self.btn_install.clicked.connect(lambda: self._done(INSTALL))
        foot.addWidget(self.btn_install)
        root.addLayout(foot)
        for cb in self.checks.values():
            cb.toggled.connect(self._sync)
        self._sync()

    def _sync(self):
        self.btn_install.setEnabled(any(cb.isChecked() for cb in self.checks.values()))

    def _done(self, choice):
        self.choice = choice
        (self.accept if choice == INSTALL else self.reject)()

    def selected(self):
        return [k for k, cb in self.checks.items() if cb.isChecked()]
