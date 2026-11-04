#!/usr/bin/env python3
"""
core/tabs/tour_mixin.py — App-Tour anbieten, starten, „Alles installieren“
==========================================================================
* Einmalig nach dem WayVR-Angebot (erstes Oeffnen des Dashboards) fragt die
  App, ob sie eine kurze Tour zeigen soll. Merker in config.json.
* Einstellungen → Allgemein → „Tour starten“ zeigt sie jederzeit erneut.
* Im Controls-Schritt: „Alles installieren“ installiert XR HOTAS und obah
  nacheinander (Standard-Installationsart) und baut/aktiviert xrBinder.

Die Oberflaeche steckt in ui/tour.py, die Schritte in core/tour_steps.py.
"""
import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

import vr_optimize as vopt
from jsonio import read_json, update_json
from logging_setup import get_logger
from translations import tr

log = get_logger("tour")

KEY_TOUR_ASKED = "tour_asked"


class TourMixin:

    # ------------------------------------------------------------------ #
    #  Angebot + Start
    # ------------------------------------------------------------------ #
    def maybe_offer_tour(self):
        """Nach dem WayVR-Angebot: einmal fragen."""
        data = read_json(vopt.APP_CONFIG_FILE, default={})
        if getattr(self, "_tour_offer_checked", False) or (
                isinstance(data, dict) and data.get(KEY_TOUR_ASKED)):
            return
        self._tour_offer_checked = True
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        update_json(vopt.APP_CONFIG_FILE, {KEY_TOUR_ASKED: stamp})
        answer = QMessageBox.question(self, tr("tour_offer_title"), tr("tour_offer_text"),
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if answer == QMessageBox.Yes:
            self.start_tour()

    def start_tour(self, index=0):
        from tour_steps import STEPS
        from ui.tour import AppTour
        # Fehlen Grundpakete, sperrt die App alle Tabs ausser Installation —
        # die Tour wuerde dann bei jedem Schritt eine Fehlermeldung ausloesen.
        if self.are_critical_packages_missing() or self.installation_running():
            QMessageBox.information(self, tr("tour_offer_title"), tr("tour_locked"))
            return
        old = getattr(self, "_tour", None)
        if old is not None:
            try:
                old.stop()
            except RuntimeError:
                pass
        # Wer die Tour (auch per Einstellungen) gesehen hat, wird nicht mehr gefragt
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        update_json(vopt.APP_CONFIG_FILE, {KEY_TOUR_ASKED: stamp})
        self._tour = AppTour(self, STEPS)
        self._tour.action_requested.connect(self._on_tour_action)
        self._tour.finished.connect(lambda: setattr(self, "_tour", None))
        # Nach „Fertig“ aufs Dashboard — erst wenn die Tour wirklich weg ist
        self._tour.completed.connect(
            lambda: QTimer.singleShot(0, lambda: self.ui.sidebar.setCurrentRow(1)))
        self._tour.start(index)

    def _on_tour_action(self, action):
        if action.startswith("lang:"):
            # Sprache der ganzen App umstellen (wie in Einstellungen → Allgemein)
            combo = self.ui.combo_language
            idx = combo.findData(action[5:])
            if idx >= 0 and idx != combo.currentIndex():
                combo.setCurrentIndex(idx)
            if getattr(self, "_tour", None) is not None:
                self._tour.refresh()
            return
        if action == "controls_install_all":
            self.controls_install_all()

    # ------------------------------------------------------------------ #
    #  Controls: alles installieren
    # ------------------------------------------------------------------ #
    def controls_install_all(self):
        """„Alles installieren“ im Controls-Schritt der Tour: XR HOTAS, obah
        und xrBinder — ueber denselben Weg wie die Einmal-Frage im Controls-Tab
        (core/tabs/controls_setup_mixin.py). Gilt danach als beantwortet."""
        from tabs.controls_setup_mixin import ORDER
        items = self.controls_setup_items()
        names = [n for _k, n, _d, installed, _p in items if not installed]
        if not names:
            QMessageBox.information(self, tr("tour_install_all_title"), tr("tour_install_all_none"))
            return
        if QMessageBox.question(self, tr("tour_install_all_title"),
                                tr("tour_install_all_text").format(items="\n".join(
                                    "• " + n for n in names)),
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.Yes) != QMessageBox.Yes:
            return
        self._mark_controls_setup_asked()
        self.controls_install(ORDER)
