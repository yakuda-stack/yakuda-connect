#!/usr/bin/env python3
"""
ui/xrbinder_panel.py — Controls-Tab: Karte „xrBinder“ (Einrichtung)
===================================================================
Steht oben im Controls-Tab neben XR HOTAS und obah und sieht genauso aus:
Schalter, Name, Beschreibung, Status, Knopf. Der Schalter

  * baut xrBinder beim ersten Mal (Terminal, core/xrbinder.py),
  * traegt das Layer ein, schreibt die Grundkonfiguration und startet den
    IPC-Dienst,
  * startet die Sitzung (core/xrbinder_session.py), die laufende Spiele
    erkennt.

Bearbeitet werden die Tasten NICHT hier, sondern im Bereich
„Controls per obah & xrBinder“: OpenXR-Spiele stehen dort in der
Spieleliste und bekommen dieselbe Controller-Ansicht wie OpenVR-Spiele
(core/tabs/xr_controls_mixin.py).
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)

import xrbinder as xb
from logging_setup import get_logger
from translations import get_language, tr

log = get_logger("xrbinder_panel")

# Gleiche Knoepfe wie die Karten darueber (ui_main.setup_controls_tab)
_BTN_CSS = """
    QPushButton { background-color:#3b4252; color:#88c0d0; font-size:11px;
                  padding:0px 14px; border-radius:4px; border:none; }
    QPushButton:hover { background-color:#4c566a; }
    QPushButton:disabled { background-color:#2e3440; color:#4c566a; }
"""
_PRIMARY_CSS = """
    QPushButton { background-color:#5e81ac; color:white; font-size:11px; font-weight:bold;
                  padding:0px 14px; border-radius:4px; border:none; }
    QPushButton:hover { background-color:#81a1c1; }
"""


def _lang():
    return "de" if get_language() == "de" else "en"


class XrBinderCard(QFrame):
    """Die Einrichtungs-Karte. ``session`` ist die XrBinderSession der App."""

    enabled_changed = Signal(bool)
    rendered = Signal()                 # Status neu gezeichnet (Hinweis im obah-Bereich)

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._build_worker = None
        self.setObjectName("controlcard")
        self.setStyleSheet("""
            QFrame#controlcard { background-color: #21252b; border-radius: 6px;
                                 border: 1px solid #2e3440; }
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(12)
        from ui.ui_main import ToggleSwitch
        self.toggle = ToggleSwitch()
        self.toggle.toggled.connect(self._on_toggle)
        row.addWidget(self.toggle, 0, Qt.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.lbl_title = QLabel()
        self.lbl_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #eceff4;")
        text_col.addWidget(self.lbl_title)
        self.lbl_desc = QLabel()
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setStyleSheet("color: #a6b2c0; font-size: 12px;")
        text_col.addWidget(self.lbl_desc)
        row.addLayout(text_col, 1)

        self.lbl_status = QLabel()
        self.lbl_status.setStyleSheet("color: #7b88a1; font-size: 12px; font-style: italic;")
        row.addWidget(self.lbl_status, 0, Qt.AlignVCenter)

        self.btn_build = QPushButton()
        self.btn_build.setCursor(Qt.PointingHandCursor)
        self.btn_build.setFixedHeight(28)
        self.btn_build.setStyleSheet(_BTN_CSS)
        self.btn_build.clicked.connect(self.start_build)
        row.addWidget(self.btn_build, 0, Qt.AlignVCenter)
        outer.addLayout(row)

        # Warnung: von Hand kopierte zweite Installation
        self.foreign_row = QWidget()
        warn = QHBoxLayout(self.foreign_row)
        warn.setContentsMargins(64, 0, 0, 0)
        self.lbl_foreign = QLabel()
        self.lbl_foreign.setWordWrap(True)
        self.lbl_foreign.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_foreign.setStyleSheet("color:#ebcb8b; font-size:11px;")
        warn.addWidget(self.lbl_foreign, 1)
        self.btn_cleanup = QPushButton()
        self.btn_cleanup.setCursor(Qt.PointingHandCursor)
        self.btn_cleanup.setFixedHeight(26)
        self.btn_cleanup.setStyleSheet(_BTN_CSS)
        self.btn_cleanup.clicked.connect(self._cleanup_foreign)
        warn.addWidget(self.btn_cleanup)
        self.foreign_row.setVisible(False)
        outer.addWidget(self.foreign_row)

        session.bus_changed.connect(lambda _ok: self.render())
        self.retranslate()

    # ------------------------------------------------------------------ #
    def retranslate(self):
        self.lbl_title.setText(tr("xrb_card_title"))
        self.lbl_desc.setText(tr("xrb_card_desc"))
        self.btn_cleanup.setText(tr("xrb_cleanup"))
        self.render()

    def is_enabled(self):
        return self.toggle.isChecked()

    def activate(self):
        """Beim Start der App: Zustand lesen, ggf. Dienst + Sitzung starten."""
        enabled = xb.layer_enabled() and xb.is_built()
        self._set_toggle(enabled)
        if enabled:
            try:
                xb.ensure_service()
            except Exception as exc:  # noqa: BLE001 — der Start darf nie daran scheitern
                log.warning("xrBinder-Dienst nicht startbar: %s", exc)
            self.session.start()
        self.render()

    def shutdown(self):
        self.session.stop()
        if self._build_worker is not None and self._build_worker.isRunning():
            self._build_worker.terminate()
            self._build_worker.wait(1000)

    def render(self):
        building = self._build_worker is not None and self._build_worker.isRunning()
        rebuild = xb.needs_rebuild()
        if building:
            status = tr("xrb_building")
        elif not xb.is_built():
            status = tr("controls_not_installed")
        elif rebuild:
            status = tr("xrb_status_rebuild_needed")
        elif self.toggle.isChecked():
            status = tr("xrb_status_service_ok") if xb.port_in_use() else tr("xrb_status_service_off")
        else:
            rev = xb.installed_revision()[:7]
            status = tr("xrb_status_built").format(rev=rev).replace(" ()", "")
        self.lbl_status.setText(status)
        self.btn_build.setText(tr("xrb_rebuild") if xb.is_built() else tr("xrb_install"))
        self.btn_build.setStyleSheet(_PRIMARY_CSS if rebuild else _BTN_CSS)
        self.btn_build.setEnabled(not building)
        foreign = xb.foreign_manifests()
        self.foreign_row.setVisible(bool(foreign))
        if foreign:
            self.lbl_foreign.setText(tr("xrb_foreign").format(paths="\n".join(foreign)))
        self.rendered.emit()

    def is_building(self):
        return self._build_worker is not None and self._build_worker.isRunning()

    def request_on(self):
        """Vom Hinweis im obah-Bereich: wie ein Klick auf den Schalter."""
        if self.is_building():
            return
        if xb.is_built() and xb.needs_rebuild():
            self.start_build()
        elif not self.toggle.isChecked():
            self.toggle.setChecked(True)

    # ------------------------------------------------------------------ #
    def _set_toggle(self, on):
        self.toggle.blockSignals(True)
        self.toggle.setChecked(on)
        self.toggle.sync_offset()
        self.toggle.blockSignals(False)

    def _on_toggle(self, checked):
        if checked:
            if not xb.is_built():
                if QMessageBox.question(self, tr("xrb_card_title"), tr("xrb_install_text"),
                                        QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                    self._set_toggle(False)
                    return
                self.start_build()
                return
            self._enable()
        else:
            xb.disable()
            self.session.stop()
            self.enabled_changed.emit(False)
            self.render()

    def _enable(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            service, _backup = xb.enable()
        except OSError as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, tr("xrb_card_title"), f"{tr('xrb_enable_failed')}\n\n{exc}")
            self._set_toggle(False)
            return
        QApplication.restoreOverrideCursor()
        if not service:
            QMessageBox.warning(self, tr("xrb_card_title"), tr("xrb_service_failed"))
        self._set_toggle(True)
        self.session.start()
        self.enabled_changed.emit(True)
        self.render()

    def start_build(self):
        if self._build_worker is not None and self._build_worker.isRunning():
            return
        self._build_worker = xb.make_build_worker(_lang())
        self._build_worker.status_signal.connect(self.lbl_status.setText)
        self._build_worker.finished_signal.connect(self._on_build_done)
        self._build_worker.start()
        self.render()

    def _on_build_done(self, ok):
        self._build_worker = None
        if not ok:
            QMessageBox.warning(self, tr("xrb_card_title"),
                                tr("xrb_build_failed").format(log=xb.log_path()))
            if not xb.layer_enabled():
                self._set_toggle(False)
            self.render()
            return
        # Nach einem Neubau laeuft evtl. noch der alte Dienst — neu starten.
        if xb.layer_enabled() or self.toggle.isChecked():
            xb.stop_service()
            self._enable()
        self.render()

    def _cleanup_foreign(self):
        moved = []
        for path in xb.foreign_manifests():
            try:
                target = xb.cleanup_manual_copy(path)
            except OSError as exc:
                log.warning("Aufraeumen fehlgeschlagen (%s): %s", path, exc)
                target = ""
            if target:
                moved.append(target)
        QMessageBox.information(self, tr("xrb_card_title"),
                                tr("xrb_cleanup_done").format(path=moved[0]) if moved
                                else tr("xrb_cleanup_system"))
        self.render()
