#!/usr/bin/env python3
"""
ui/advanced_panel.py — Technische Details im Advanced Mode
==========================================================
Ein schmaler, ausklappbarer Kasten, der unter eine Schaltflaeche gehaengt
wird. Ist der Advanced Mode aus (Standard), ist er komplett unsichtbar und
belegt keinen Platz — die Oberflaeche sieht dann exakt so aus wie vorher.

Ist er an, zeigt der Kasten zu der jeweiligen Aktion:

    * eine kurze Erklaerung, was die Aktion tut
    * die betroffenen Dateien/Pfade
    * die benoetigten Berechtigungen
    * den passenden Terminal-Befehl mit Kopier-Knopf

Der Befehl wird NICHT ausgefuehrt. Es gibt bewusst keinen "Ausfuehren"-Knopf:
wer den Befehl selbst laufen lassen will, soll ihn auch selbst im Terminal
sehen. Der Kopier-Knopf ist die einzige Aktion.

Einbau (eine Zeile pro Stelle):

    from ui.advanced_panel import AdvancedBox
    cv.addWidget(AdvancedBox("openxr_fix"))

Woher die Inhalte kommen: core/advanced_info.py — dort steht pro Aktion, was
sie anfasst. Dieses Modul stellt es nur dar.

Sichtbarkeit
------------
Alle erzeugten Kaesten tragen sich in eine Liste ein. ``refresh_all()``
schaltet sie gemeinsam ein oder aus — die aufrufende Stelle (core/main.py)
muss sie also nicht selbst einsammeln, auch wenn sie in drei verschiedenen
Widgets stecken.
"""
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QToolButton, QVBoxLayout, QWidget)

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'core')))
import advanced_info as adv
from logging_setup import get_logger
from translations import tr

log = get_logger("advanced_panel")


# Alle lebenden Kaesten. Qt-Widgets koennen von C++ abgeraeumt worden sein,
# deshalb wird beim Durchgehen jeder Zugriff abgesichert (RuntimeError).
_boxes = []


def refresh_all():
    """Alle Kaesten an den aktuellen Zustand des Advanced Mode angleichen."""
    alive = []
    for box in _boxes:
        try:
            box.refresh()
            alive.append(box)
        except RuntimeError:
            # Widget wurde geloescht (Tab neu aufgebaut) — still aussortieren.
            continue
    _boxes[:] = alive


def retranslate_all():
    """Nach einem Sprachwechsel alle Kaesten neu beschriften."""
    alive = []
    for box in _boxes:
        try:
            box.retranslate()
            alive.append(box)
        except RuntimeError:
            continue
    _boxes[:] = alive


class AdvancedBox(QWidget):
    """Ausklappbarer Kasten mit den technischen Angaben zu einer Aktion."""

    def __init__(self, action_id, parent=None):
        super().__init__(parent)
        self.action_id = action_id
        self._expanded = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(4)

        # --- Kopfzeile: Aufklapp-Knopf ------------------------------------
        self.btn_toggle = QToolButton()
        self.btn_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_toggle.setStyleSheet(
            "QToolButton { color:#7b88a1; background:transparent; border:none;"
            " font-size:11px; font-weight:bold; padding:2px 0; text-align:left; }"
            " QToolButton:hover { color:#88c0d0; }")
        self.btn_toggle.clicked.connect(self._toggle)
        root.addWidget(self.btn_toggle, 0, Qt.AlignLeft)

        # --- Inhalt (erst nach dem Aufklappen sichtbar) --------------------
        self.body = QFrame()
        self.body.setStyleSheet(
            "QFrame { background-color:#1e222a; border:1px solid #3b4252;"
            " border-radius:6px; }")
        body_v = QVBoxLayout(self.body)
        body_v.setContentsMargins(10, 8, 10, 8)
        body_v.setSpacing(6)

        self.lbl_explain = QLabel("")
        self.lbl_explain.setWordWrap(True)
        self.lbl_explain.setStyleSheet(
            "color:#d8dee9; font-size:11px; border:none; background:transparent;")
        body_v.addWidget(self.lbl_explain)

        self.lbl_paths = QLabel("")
        self.lbl_paths.setWordWrap(True)
        self.lbl_paths.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_paths.setStyleSheet(
            "color:#7b88a1; font-size:11px; font-family:monospace;"
            " border:none; background:transparent;")
        body_v.addWidget(self.lbl_paths)

        self.lbl_perms = QLabel("")
        self.lbl_perms.setWordWrap(True)
        self.lbl_perms.setStyleSheet(
            "color:#7b88a1; font-size:11px; border:none; background:transparent;")
        body_v.addWidget(self.lbl_perms)

        # --- Befehl + Kopier-Knopf ----------------------------------------
        self.cmd_row = QWidget()
        cmd_layout = QHBoxLayout(self.cmd_row)
        cmd_layout.setContentsMargins(0, 0, 0, 0)
        cmd_layout.setSpacing(8)

        self.lbl_cmd = QLabel("")
        self.lbl_cmd.setWordWrap(True)
        self.lbl_cmd.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_cmd.setStyleSheet(
            "color:#a3be8c; font-size:11px; font-family:monospace;"
            " border:none; background:transparent;")
        cmd_layout.addWidget(self.lbl_cmd, 1)

        self.btn_copy = QPushButton(tr("tools_copy"))
        self.btn_copy.setCursor(Qt.PointingHandCursor)
        self.btn_copy.setStyleSheet(
            "QPushButton { background-color:#3b4252; color:#d8dee9;"
            " border:1px solid #4c566a; border-radius:4px; padding:4px 10px;"
            " font-size:11px; font-weight:bold; }"
            " QPushButton:hover { background-color:#4c566a; border-color:#5e81ac; }")
        self.btn_copy.clicked.connect(self._copy)
        cmd_layout.addWidget(self.btn_copy, 0, Qt.AlignTop)
        body_v.addWidget(self.cmd_row)

        self.lbl_source = QLabel("")
        self.lbl_source.setStyleSheet(
            "color:#4c566a; font-size:10px; border:none; background:transparent;")
        body_v.addWidget(self.lbl_source)

        self.body.setVisible(False)
        root.addWidget(self.body)

        _boxes.append(self)
        self.retranslate()
        self.refresh()

    # ------------------------------------------------------------------ #
    #  Zustand
    # ------------------------------------------------------------------ #
    def refresh(self):
        """Sichtbarkeit an den Advanced Mode angleichen."""
        on = adv.is_enabled()
        self.setVisible(on)
        if not on:
            # Beim Ausschalten wieder einklappen: wird der Modus spaeter
            # erneut aktiviert, stehen nicht ueberall offene Kaesten.
            self._expanded = False
            self.body.setVisible(False)
            self._update_toggle_text()

    def retranslate(self):
        """Texte neu aufbauen (Sprachwechsel oder erster Aufbau)."""
        self._update_toggle_text()
        if self._expanded:
            self._fill()

    def _update_toggle_text(self):
        arrow = "▾" if self._expanded else "▸"
        # "Technical details: Firewall & Ports" — der Zusatz macht mehrere
        # Kaesten auf einer Seite unterscheidbar. Fehlt er, bleibt es beim
        # allgemeinen Text.
        short = adv.short_title(self.action_id)
        label = tr("adv_details_btn")
        if short:
            label = f"{label}: {short}"
        # QToolButton deutet ein einzelnes '&' als Tastenkuerzel und
        # verschluckt es: aus "Firewall & Ports" wurde sichtbar
        # "Firewall _Ports". Verdoppeln ist die von Qt vorgesehene
        # Schreibweise fuer ein echtes '&' (siehe tr_amp in translations.py).
        self.btn_toggle.setText(f"{arrow} {label}".replace("&", "&&"))

    def _toggle(self):
        self._expanded = not self._expanded
        if self._expanded:
            self._fill()
        self.body.setVisible(self._expanded)
        self._update_toggle_text()

    # ------------------------------------------------------------------ #
    #  Inhalt
    # ------------------------------------------------------------------ #
    def _fill(self):
        """
        Angaben frisch holen. Bewusst erst beim Aufklappen: die Ermittlung
        liest Dateien und ruft teils Programme auf (Firewall-Erkennung). Das
        soll nicht bei jedem Aufbau der Seite passieren, sondern nur dann,
        wenn jemand wirklich hinschaut.
        """
        d = adv.describe(self.action_id)

        self.lbl_explain.setText(d["explain"])
        self.lbl_explain.setVisible(bool(d["explain"]))

        if d["paths"]:
            self.lbl_paths.setText(
                f"<b>{tr('adv_paths_label')}</b><br>" + "<br>".join(
                    p.replace("<", "&lt;") for p in d["paths"]))
            self.lbl_paths.setVisible(True)
        else:
            self.lbl_paths.setVisible(False)

        if d["perms"]:
            self.lbl_perms.setText(
                f"<b>{tr('adv_perms_label')}</b> " + " · ".join(d["perms"]))
            self.lbl_perms.setVisible(True)
        else:
            self.lbl_perms.setVisible(False)

        self._commands = d["commands"]
        if self._commands:
            self.lbl_cmd.setText(
                f"<b>{tr('adv_cmd_label')}</b><br>" + "<br>".join(
                    c.replace("<", "&lt;") for c in self._commands))
            self.cmd_row.setVisible(True)
        else:
            self.cmd_row.setVisible(False)

        self.lbl_source.setText(f"{tr('adv_source_label')} {d['source']}"
                                if d["source"] else "")
        self.lbl_source.setVisible(bool(d["source"]))

    def _copy(self):
        """Befehl(e) in die Zwischenablage — ohne sie auszufuehren."""
        commands = getattr(self, "_commands", [])
        if not commands:
            return
        QApplication.clipboard().setText("\n".join(commands))
        self.btn_copy.setText(tr("adv_copied"))
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, lambda: self.btn_copy.setText(tr("tools_copy")))
