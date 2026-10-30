#!/usr/bin/env python3
"""
core/tabs/dashboard_wayvr_mixin.py — Einmal-Popup "WayVR installieren?"
=======================================================================
Kommt beim ALLERERSTEN Oeffnen des Dashboards direkt nach dem
"Fuer VR optimieren"-Popup. Zeigt ein Beispielbild (assets/wayvr_preview.jpg)
und fragt, ob WayVR installiert werden soll.

Bei "Ja":
  1. WayVR wird ueber die Tools-Karte installiert (gleiche Logik wie dort,
     Installationsart waehlt der Nutzer im Popup).
  2. Danach wird automatisch das cubee-cb-Design nach ~/.config/wayvr
     kopiert (Ordner wird angelegt, falls er fehlt).

Ist WayVR schon installiert, wird nur noch das Design angeboten.
Sind WayVR UND Design schon da, erscheint das Popup gar nicht.
"""
import datetime
import os
import shutil

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
                               QLabel, QVBoxLayout)

import appimage_installer as appimg
import overlay_manager as ovl
import vr_optimize as vopt
from jsonio import read_json, update_json
from translations import tr
from logging_setup import get_logger

log = get_logger("dashboard_wayvr")

KEY_WAYVR_ASKED = "dashboard_wayvr_asked"
PREVIEW_IMAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "..", "assets", "wayvr_preview.jpg")


def _already_asked():
    data = read_json(vopt.APP_CONFIG_FILE, default={})
    return isinstance(data, dict) and bool(data.get(KEY_WAYVR_ASKED))


def _mark_asked():
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    if not update_json(vopt.APP_CONFIG_FILE, {KEY_WAYVR_ASKED: stamp}):
        log.warning("Merker %s konnte nicht geschrieben werden.", KEY_WAYVR_ASKED)


class _WayVRDialog(QDialog):
    """Bild + Frage + (falls noetig) Auswahl der Installationsart."""

    def __init__(self, parent, installed, methods, labels, default):
        super().__init__(parent)
        self.setWindowTitle(tr("wayvr_offer_title"))
        lay = QVBoxLayout(self)

        pix = QPixmap(PREVIEW_IMAGE)
        if not pix.isNull():
            img = QLabel()
            img.setPixmap(pix.scaledToWidth(460, Qt.SmoothTransformation))
            img.setAlignment(Qt.AlignCenter)
            lay.addWidget(img)

        text = QLabel(tr("wayvr_offer_text_installed" if installed else "wayvr_offer_text"))
        text.setWordWrap(True)
        lay.addWidget(text)

        self.combo = None
        if not installed and len(methods) >= 2:
            row = QHBoxLayout()
            row.addWidget(QLabel(tr("wayvr_offer_method")))
            self.combo = QComboBox()
            for m in methods:
                self.combo.addItem(labels.get(m, m), m)
            idx = self.combo.findData(default)
            if idx >= 0:
                self.combo.setCurrentIndex(idx)
            row.addWidget(self.combo, 1)
            lay.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Yes | QDialogButtonBox.No)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def method(self):
        return self.combo.currentData() if self.combo is not None else None


class DashboardWayVRMixin:

    def maybe_offer_wayvr(self):
        """Aus der Erst-Einrichtung (first_run_mixin). Rueckgabe: True, wenn
        jetzt im Hintergrund installiert/eingerichtet wird (Tour wartet darauf)."""
        if getattr(self, "_wayvr_offer_checked", False) or _already_asked():
            return False
        self._wayvr_offer_checked = True
        _mark_asked()

        self._ensure_tools_ui()             # Tools-Tab wird sonst erst beim Oeffnen gebaut
        card = self.ui.tool_cards.get("wayvr")
        if not card:
            return False
        installed = self._wayvr_is_installed(card)
        if installed and ovl.is_design_installed():
            log.info("[WayVR] WayVR + Design schon da — kein Popup.")
            return False

        tool = card.get("tool", {})
        methods = card.get("methods") or appimg.detect_install_methods(tool)
        if not installed and not methods:
            log.info("[WayVR] Keine Installationsart verfuegbar — kein Popup.")
            return False

        dlg = _WayVRDialog(self, installed, methods, self._wayvr_method_labels(card),
                           self._selected_method(card))
        if dlg.exec() != QDialog.Accepted:
            return False

        if installed:
            self.start_wayvr_design_install()
            return True

        chosen = dlg.method()
        combo = card.get("combo_method")
        if chosen and combo is not None:
            idx = combo.findData(chosen)
            if idx >= 0:
                combo.setCurrentIndex(idx)

        self._wayvr_auto_design = True
        self.install_tool("wayvr")
        if card["btn_install"].isEnabled():
            self._wayvr_auto_design = False     # Installation nicht gestartet
            return False
        return True

    def _wayvr_is_installed(self, card):
        status = card.get("status") or {}
        if any(status.get(k) for k in ("appimage_installed", "pm_installed",
                                        "flatpak_installed", "cargo_installed",
                                        "script_installed")):
            return True
        return shutil.which("wayvr") is not None

    def _wayvr_method_labels(self, card):
        labels = {}
        combo = card.get("combo_method")
        if combo is not None:
            for i in range(combo.count()):
                labels[combo.itemData(i)] = combo.itemText(i)
        return labels

    def wayvr_install_finished(self, success):
        """Aus on_tool_installed: True, wenn das Popup die Installation gestartet hat."""
        if not getattr(self, "_wayvr_auto_design", False):
            return False
        self._wayvr_auto_design = False
        if success:
            self.start_wayvr_design_install()
        else:
            self.first_run_after_wayvr()        # Tour trotzdem anbieten
        return True
