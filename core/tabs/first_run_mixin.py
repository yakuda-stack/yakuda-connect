#!/usr/bin/env python3
"""
core/tabs/first_run_mixin.py — Erst-Einrichtung beim ersten Dashboard-Besuch
============================================================================
Reihenfolge, immer nacheinander und nie gleichzeitig:

    1. Performance-Setup   (dashboard_optimize_mixin.py)
    2. WayVR installieren? (dashboard_wayvr_mixin.py) — laeuft eine
       Installation/Design-Einrichtung, wird auf deren Ende gewartet
    3. Tour anbieten       (tour_mixin.py)

Schutz gegen Durcheinander:
  * _first_run_busy: solange die Kette laeuft, startet keine zweite
    (z. B. erneuter Klick aufs Dashboard).
  * Waehrend einer Tour startet die Kette nicht — die Tour wechselt selbst
    aufs Dashboard.
  * Jeder Start bekommt eine Nummer (_first_run_gen). Geplante Schritte
    eines aelteren Starts (z. B. vom automatischen Dashboard-Sprung beim
    Programmstart, vor einem Zuruecksetzen) verwerfen sich selbst.
  * Jeder Schritt wartet, bis das Fenster sichtbar ist, nichts mehr laedt
    und kein anderes Fenster (z. B. „Was ist neu“) offen ist. Wichtig, weil
    die App beim Start selbst aufs Dashboard springt, sobald alle Pakete da
    sind — dann laeuft die Kette, ohne dass jemand geklickt hat.

Advanced Mode → Einstellungen → Erweitert: „Ersteinrichtung zuruecksetzen“
loescht die drei Merker, als waere das Dashboard nie geoeffnet worden.
"""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

import vr_optimize as vopt
from jsonio import read_json, write_json_atomic
from logging_setup import get_logger
from translations import tr

log = get_logger("first_run")

FIRST_RUN_KEYS = ("dashboard_optimize_asked", "dashboard_wayvr_asked", "tour_asked")
_SESSION_FLAGS = ("_optimize_checked", "_wayvr_offer_checked", "_tour_offer_checked",
                  "_first_run_busy", "_tour_after_wayvr")
RETRY_MS = 500


class FirstRunMixin:

    # ------------------------------------------------------------------ #
    #  Zustand
    # ------------------------------------------------------------------ #
    def tour_running(self):
        return getattr(self, "_tour", None) is not None

    def first_run_may_start(self):
        return not getattr(self, "_first_run_busy", False) and not self.tour_running()

    def first_run_ready(self):
        """Darf jetzt ein Popup der Kette erscheinen?"""
        return (self.isVisible() and not getattr(self, "is_loading", False)
                and QApplication.activeModalWidget() is None
                and not self.tour_running())

    def first_run_begin(self):
        """Neuer Start der Kette. Rueckgabe: seine Nummer."""
        self._first_run_gen = getattr(self, "_first_run_gen", 0) + 1
        self._first_run_busy = True
        return self._first_run_gen

    def first_run_current(self, gen):
        return gen == getattr(self, "_first_run_gen", 0)

    def first_run_when_ready(self, fn, gen=None):
        """fn ausfuehren, sobald first_run_ready() — sonst spaeter erneut pruefen.
        Gehoert der Schritt zu einem veralteten Start (gen), passiert nichts."""
        if gen is None:
            gen = getattr(self, "_first_run_gen", 0)
        if not self.first_run_current(gen):
            return
        if self.first_run_ready():
            fn()
        else:
            QTimer.singleShot(RETRY_MS, lambda: self.first_run_when_ready(fn, gen))

    # ------------------------------------------------------------------ #
    #  Kette
    # ------------------------------------------------------------------ #
    def first_run_after_optimize(self):
        """Schritt 2 → 3. Startet die WayVR-Einrichtung im Hintergrund,
        kommt die Tour erst danach (first_run_after_wayvr)."""
        started = False
        if hasattr(self, "maybe_offer_wayvr"):
            started = bool(self.maybe_offer_wayvr())
        if started:
            self._tour_after_wayvr = True
            return
        self._first_run_offer_tour()

    def first_run_after_wayvr(self):
        """Aus dem Ende der WayVR-Installation / Design-Einrichtung."""
        if getattr(self, "_tour_after_wayvr", False):
            self._tour_after_wayvr = False
            self._first_run_offer_tour()

    def _first_run_offer_tour(self):
        gen = getattr(self, "_first_run_gen", 0)

        def offer():
            try:
                if hasattr(self, "maybe_offer_tour"):
                    self.maybe_offer_tour()
            finally:
                self._first_run_busy = False
        QTimer.singleShot(300, lambda: self.first_run_when_ready(offer, gen))

    # ------------------------------------------------------------------ #
    #  Zuruecksetzen (Advanced Mode)
    # ------------------------------------------------------------------ #
    def reset_first_run_state(self):
        """Merker dieser Sitzung loeschen; noch geplante Schritte verwerfen."""
        for attr in _SESSION_FLAGS:
            setattr(self, attr, False)
        self._first_run_gen = getattr(self, "_first_run_gen", 0) + 1

    def reset_first_run(self):
        if QMessageBox.question(self, tr("firstrun_group"), tr("firstrun_reset_confirm"),
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) != QMessageBox.Yes:
            return
        path = vopt.APP_CONFIG_FILE
        data = read_json(path, default={})
        if not isinstance(data, dict):
            data = {}
        for key in FIRST_RUN_KEYS:
            data.pop(key, None)
        if not write_json_atomic(path, data):
            QMessageBox.warning(self, tr("firstrun_group"), tr("firstrun_reset_failed"))
            return
        self.reset_first_run_state()
        log.info("[Erst-Einrichtung] zurueckgesetzt.")
        QMessageBox.information(self, tr("firstrun_group"), tr("firstrun_reset_done"))
