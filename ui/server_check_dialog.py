#!/usr/bin/env python3
"""
ui/server_check_dialog.py — Einstellungen fuer "Timer Server Check"
===================================================================
Kleines Fenster zum Knopf rechts neben "Serverstatus pruefen": Timer an oder
aus und alle wie viele Sekunden der Serverstatus geprueft wird.

Es zeigt nur die Werte an und gibt sie zurueck. Speichern und den Timer
schalten macht core/tabs/dashboard_mixin.py.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractSpinBox, QCheckBox, QDialog, QDialogButtonBox,
                               QHBoxLayout, QLabel, QSpinBox, QVBoxLayout)

from translations import tr


class ServerCheckDialog(QDialog):
    def __init__(self, enabled, seconds, minimum, maximum, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("server_timer_title"))
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        hint = QLabel(tr("server_timer_desc"))
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.chk_enabled = QCheckBox(tr("server_timer_enable"))
        self.chk_enabled.setCursor(Qt.PointingHandCursor)
        self.chk_enabled.setChecked(enabled)
        layout.addWidget(self.chk_enabled)

        row = QHBoxLayout()
        lbl_interval = QLabel(tr("server_timer_interval"))
        self.spin_seconds = QSpinBox()
        self.spin_seconds.setRange(minimum, maximum)
        self.spin_seconds.setValue(seconds)
        self.spin_seconds.setSuffix(" s")
        # Zu kleine Eingaben werden auf das Minimum gesetzt, nicht verworfen.
        self.spin_seconds.setCorrectionMode(QAbstractSpinBox.CorrectToNearestValue)
        row.addWidget(lbl_interval)
        row.addStretch()
        row.addWidget(self.spin_seconds)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Cancel).setText(tr("cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        """Gewaehlte Werte als (an/aus, Sekunden)."""
        self.spin_seconds.interpretText()
        return self.chk_enabled.isChecked(), self.spin_seconds.value()
