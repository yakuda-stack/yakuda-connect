#!/usr/bin/env python3
"""
core/tabs/dashboard_optimize_mixin.py — Einmal-Popup "Fuer VR optimieren"
=========================================================================
Beim ALLERERSTEN Oeffnen des Dashboards fragt die App einmal, ob sie alles
fuer maximale VR-Performance einrichten soll. Die Logik (welche Fixes offen
sind, wie sie ausgefuehrt werden) liegt in core/vr_optimize.py — hier nur
Dialog, Hintergrund-Thread und das Auffrischen der Knoepfe.

Regeln:
  * Nur einmal: der Merker steht in config.json und wird gesetzt, sobald
    das Dashboard das erste Mal geoeffnet wurde — egal, ob Ja oder Nein.
  * Sind alle Fixes schon aktiv, erscheint das Popup gar nicht.
"""
from PySide6.QtCore import QThread, QTimer, Signal as QtSignal
from PySide6.QtWidgets import QMessageBox

import vr_optimize as vopt
from translations import tr
from logging_setup import get_logger

log = get_logger("dashboard_optimize")


class _OptimizeWorker(QThread):
    """pkexec blockiert, bis der Nutzer das Passwort eingibt — nicht im GUI-Thread."""
    done = QtSignal(dict)

    def __init__(self, steps):
        super().__init__()
        self.steps = steps

    def run(self):
        try:
            results = vopt.apply_all(self.steps)
        except Exception as exc:                               # noqa: BLE001
            log.warning("[Optimize] fehlgeschlagen: %s", exc)
            results = {s: (False, str(exc)) for s in self.steps}
        self.done.emit(results)


class DashboardOptimizeMixin:

    def maybe_offer_vr_optimize(self):
        """Aus on_tab_changed (Dashboard): Start der Erst-Einrichtung
        (Reihenfolge und Schutz siehe core/tabs/first_run_mixin.py)."""
        if getattr(self, "_optimize_checked", False) or not self.first_run_may_start():
            return
        self._optimize_checked = True
        gen = self.first_run_begin()

        def step():
            if vopt.already_asked():
                self._optimize_next(False)
            else:
                self._offer_vr_optimize()
        QTimer.singleShot(400, lambda: self.first_run_when_ready(step, gen))

    def open_vr_optimize(self):
        """Knopf „Performance-Setup“ im Dashboard — oeffnet das Popup jederzeit."""
        worker = getattr(self, "_optimize_worker", None)
        if worker is not None and worker.isRunning():
            return
        self._offer_vr_optimize(manual=True)

    def _offer_vr_optimize(self, manual=False):
        vopt.mark_asked()
        self._optimize_manual = manual
        try:
            steps = vopt.pending_steps()
        except Exception as exc:                               # noqa: BLE001
            log.warning("[Optimize] Pruefung fehlgeschlagen: %s", exc)
            self._optimize_next(manual)
            return
        if not steps:
            log.info("[Optimize] Alle Fixes schon aktiv — kein Popup.")
            if manual:
                QMessageBox.information(self, tr("optimize_title"), tr("optimize_all_active"))
            self._optimize_next(manual)
            return

        items = "\n".join("• " + tr(f"optimize_item_{s}") for s in steps)
        answer = QMessageBox.question(
            self, tr("optimize_title"),
            tr("optimize_ask_manual" if manual else "optimize_ask").format(items=items),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if answer != QMessageBox.Yes:
            self._optimize_next(manual)
            return

        self._optimize_worker = _OptimizeWorker(steps)
        self._optimize_worker.done.connect(self._on_vr_optimize_done)
        self._optimize_worker.start()

    def _on_vr_optimize_done(self, results):
        lines = []
        for name, (ok, err) in results.items():
            mark = "✔" if ok else "✖"
            line = f"{mark} {tr(f'optimize_item_{name}')}"
            if not ok and err:
                line += f"  ({err})"
            lines.append(line)

        if results.get(vopt.FIREWALL, (False,))[0]:
            self._mark_firewall_done()
        if results.get(vopt.NETBUFFERS, (False,))[0]:
            self._mark_netbuffers_done()
        if hasattr(self.ui, "vr_runtime_widget"):
            self.ui.vr_runtime_widget.refresh()
        self.refresh_openxr_status()
        self.fill_openxr_fields()
        self.refresh_openvr_ui()

        all_ok = all(ok for ok, _e in results.values())
        key = "optimize_done" if all_ok else "optimize_partial"
        box = QMessageBox.information if all_ok else QMessageBox.warning
        box(self, tr("optimize_title"), tr(key).format(items="\n".join(lines)))
        self._optimize_next(getattr(self, "_optimize_manual", False))

    def _optimize_next(self, manual):
        """Nach dem Erst-Popup geht die Kette weiter (WayVR, dann Tour)."""
        if manual:
            return
        self.first_run_after_optimize()
