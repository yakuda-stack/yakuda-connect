#!/usr/bin/env python3
"""
vr_runtime_widget.py — OpenXR-Runtime-Umschaltung + VR-Prioritaet (Settings-Tab)
===============================================================================
Beide Boxen lagen frueher im Streaming-Tab. Dort waren sie falsch aufgehoben:
Der Streaming-Tab stellt ein, WIE gestreamt wird (Encoder, Aufloesung,
Kompatibilitaets-Layer) — das hier sind dagegen einmalige System-Reparaturen
("welche OpenXR-Runtime ist aktiv?", "darf wivrn-server mit hoher Prioritaet
laufen?"). Die gehoeren zu den anderen Fixes unter Einstellungen -> VR & OpenXR.

Der Aufbau folgt dem Vorbild von ui/queryfix_widget.py: ein eigenstaendiges
Widget, das ui_main.py nur noch einhaengt. Dadurch musste die Logik beim
Umzug nicht in main.py wandern und bleibt an einer Stelle testbar.

Einbau (macht ui_main.py):
    from ui.vr_runtime_widget import VrRuntimeWidget
    self.vr_runtime_widget = VrRuntimeWidget()
    vr_v.addWidget(self.vr_runtime_widget)

Oeffentliche Methoden:
    refresh()      — beide Statusanzeigen neu pruefen (z. B. beim Tab-Wechsel)
    retranslate()  — Texte nach Sprachwechsel neu setzen
"""

import json
import os
import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)

# core/ liegt auf dem sys.path (starter.py haengt ihn an) — zur Sicherheit
# hier trotzdem nochmal, damit das Widget auch standalone importierbar ist.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'core')))
import proc
import vr_environment as venv
from logging_setup import get_logger
from translations import tr

log = get_logger("vr_runtime_widget")


class VrRuntimeWidget(QWidget):
    """Zwei Karten im Settings-Look: OpenXR-Runtime-Umschaltung und
    VR-Prioritaet (CAP_SYS_NICE) samt Latenz-Tipps."""

    _CSS_PRIMARY = ("QPushButton { background-color:#5e81ac; color:white; border:none;"
                    " font-weight:bold; padding:8px 14px; border-radius:4px; font-size:12px; }"
                    " QPushButton:hover { background-color:#81a1c1; }"
                    " QPushButton:disabled { background-color:#3b4252; color:#7b88a1; }")
    _CSS_SECONDARY = ("QPushButton { background-color:#2e3440; color:#d8dee9; border:1px solid #4c566a;"
                      " font-weight:bold; padding:8px 14px; border-radius:4px; font-size:12px; }"
                      " QPushButton:hover { background-color:#3b4252; border-color:#5e81ac; }"
                      " QPushButton:disabled { background-color:#272b33; color:#616b7f; }")

    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        # ------------------------------------------------------------------
        #  Karte 1 — OpenXR-Runtime (WiVRn / SteamVR umschalten)
        # ------------------------------------------------------------------
        card, cv = self._card()

        self.lbl_openxr_title = QLabel(tr("streaming_openxr"))
        self.lbl_openxr_title.setStyleSheet("color:#eceff4; font-size:13px; font-weight:bold;")
        cv.addWidget(self.lbl_openxr_title)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.lbl_status_title = QLabel(tr("streaming_status"))
        self.lbl_status_title.setStyleSheet("color:#7b88a1; font-size:12px;")
        self.lbl_active_runtime = QLabel(tr("streaming_checking"))
        self.lbl_active_runtime.setStyleSheet("font-weight:bold; color:#ebcb8b; font-size:13px;")
        status_row.addWidget(self.lbl_status_title)
        status_row.addWidget(self.lbl_active_runtime)
        status_row.addStretch()
        cv.addLayout(status_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_switch_wivrn = QPushButton(tr("streaming_wivrn_btn"))
        self.btn_switch_wivrn.setCursor(Qt.PointingHandCursor)
        self.btn_switch_wivrn.setStyleSheet(self._CSS_PRIMARY)
        self.btn_switch_steamvr = QPushButton(tr("streaming_steam_btn"))
        self.btn_switch_steamvr.setCursor(Qt.PointingHandCursor)
        self.btn_switch_steamvr.setStyleSheet(self._CSS_SECONDARY)
        btn_row.addWidget(self.btn_switch_wivrn)
        btn_row.addWidget(self.btn_switch_steamvr)
        cv.addLayout(btn_row)

        root.addWidget(card)

        # ------------------------------------------------------------------
        #  Karte 2 — VR-Prioritaet (CAP_SYS_NICE) + Latenz-Tipps
        # ------------------------------------------------------------------
        card, cv = self._card()

        self.lbl_prio_title = QLabel(tr("streaming_prio"))
        self.lbl_prio_title.setStyleSheet("color:#eceff4; font-size:13px; font-weight:bold;")
        cv.addWidget(self.lbl_prio_title)

        self.lbl_prio_desc = QLabel(tr("streaming_prio_desc"))
        self.lbl_prio_desc.setWordWrap(True)
        self.lbl_prio_desc.setStyleSheet("color:#7b88a1; font-size:11px;")
        cv.addWidget(self.lbl_prio_desc)

        prio_row = QHBoxLayout()
        prio_row.setSpacing(8)
        self.lbl_prio_status = QLabel(tr("streaming_checking"))
        self.lbl_prio_status.setStyleSheet("font-weight:bold; color:#ebcb8b; font-size:13px;")
        self.btn_vr_priority = QPushButton(tr("streaming_prio_btn"))
        self.btn_vr_priority.setCursor(Qt.PointingHandCursor)
        self.btn_vr_priority.setStyleSheet(self._CSS_PRIMARY)
        prio_row.addWidget(self.lbl_prio_status)
        prio_row.addStretch()
        prio_row.addWidget(self.btn_vr_priority)
        cv.addLayout(prio_row)

        self.lbl_perf_tips = QLabel(tr("perf_tips"))
        self.lbl_perf_tips.setStyleSheet(
            "color:#d8dee9; font-size:11px; background-color:#2e3440;"
            " border-radius:4px; padding:8px;")
        self.lbl_perf_tips.setWordWrap(True)
        self.lbl_perf_tips.setTextFormat(Qt.RichText)
        cv.addWidget(self.lbl_perf_tips)

        root.addWidget(card)

        # --- Signale ---
        self.btn_switch_wivrn.clicked.connect(self.set_openxr_runtime_wivrn)
        self.btn_switch_steamvr.clicked.connect(self.set_openxr_runtime_steamvr)
        self.btn_vr_priority.clicked.connect(self.enable_vr_priority)

        self.refresh()

    # ----------------------------------------------------------------------
    #  Hilfen
    # ----------------------------------------------------------------------
    def _card(self):
        """Karte im gleichen Look wie die uebrigen Settings-Karten."""
        card = QFrame()
        card.setStyleSheet("QFrame { background-color:#21252b; border-radius:10px; }")
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)
        return card, v

    def refresh(self):
        """Beide Statusanzeigen neu pruefen."""
        self.check_active_openxr_runtime()
        self.check_vr_priority()

    def retranslate(self):
        """Statische Texte neu setzen (nach Sprachwechsel)."""
        self.lbl_openxr_title.setText(tr("streaming_openxr"))
        self.lbl_status_title.setText(tr("streaming_status"))
        self.btn_switch_wivrn.setText(tr("streaming_wivrn_btn"))
        self.btn_switch_steamvr.setText(tr("streaming_steam_btn"))
        self.lbl_prio_title.setText(tr("streaming_prio"))
        self.lbl_prio_desc.setText(tr("streaming_prio_desc"))
        self.btn_vr_priority.setText(tr("streaming_prio_btn"))
        self.lbl_perf_tips.setText(tr("perf_tips"))
        # Status-Texte sind sprachabhaengig -> neu ermitteln
        self.refresh()

    # ----------------------------------------------------------------------
    #  OpenXR-Runtime
    # ----------------------------------------------------------------------
    def check_active_openxr_runtime(self):
        """Prueft, welche OpenXR-Runtime aktuell im System aktiv ist."""
        try:
            active_json = os.path.expanduser("~/.config/openxr/1/active_runtime.json")
            if os.path.exists(active_json):
                with open(active_json) as f:
                    content = f.read()
                if "wivrn" in content.lower():
                    self._set_runtime_label(tr("streaming_rt_wivrn"), "#a3be8c")
                elif "steamvr" in content.lower():
                    self._set_runtime_label(tr("streaming_rt_steamvr"), "#81a1c1")
                else:
                    self._set_runtime_label(tr("streaming_rt_other"), "#ebcb8b")
            else:
                self._set_runtime_label(tr("streaming_rt_none"), "#bf616a")
        except Exception as e:
            self._set_runtime_label(tr("streaming_rt_error") + str(e), "#bf616a")

    def _set_runtime_label(self, text, color):
        self.lbl_active_runtime.setText(text)
        self.lbl_active_runtime.setStyleSheet(
            f"font-weight:bold; color:{color}; font-size:13px;")

    def _write_active_runtime(self, library_path):
        """Schreibt active_runtime.json in alle bekannten OpenXR-Verzeichnisse
        (Host + Steam-Flatpak-Sandbox)."""
        data = {"file_format_version": "1.0.0", "runtime": {"library_path": library_path}}
        for d in venv.openxr_config_dirs():
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "active_runtime.json"), "w") as f:
                json.dump(data, f, indent=4)

    def set_openxr_runtime_wivrn(self):
        """Schaltet die OpenXR-Runtime auf WiVRn um."""
        try:
            self._write_active_runtime(venv.find_wivrn_manifest())
            self.check_active_openxr_runtime()
            QMessageBox.information(self, tr("streaming_rt_switched"), tr("streaming_rt_wivrn_ok"))
        except Exception as e:
            log.warning("OpenXR-Runtime WiVRn: %s", e)
            QMessageBox.critical(self, tr("error"), tr("streaming_rt_switch_err") + str(e))

    def set_openxr_runtime_steamvr(self):
        """Schaltet die OpenXR-Runtime auf SteamVR um."""
        try:
            self._write_active_runtime(venv.find_steamvr_manifest())
            self.check_active_openxr_runtime()
            QMessageBox.information(self, tr("streaming_rt_switched"), tr("streaming_rt_steam_ok"))
        except Exception as e:
            log.warning("OpenXR-Runtime SteamVR: %s", e)
            QMessageBox.critical(self, tr("error"), tr("streaming_rt_switch_err") + str(e))

    # ----------------------------------------------------------------------
    #  VR-Prioritaet (CAP_SYS_NICE)
    # ----------------------------------------------------------------------
    def _wivrn_server_path(self):
        """Findet die wivrn-server-Binary (Symlinks aufgeloest). None, wenn nicht da."""
        return venv.wivrn_server_binary()

    def check_vr_priority(self):
        """Prueft, ob die wivrn-server-Binary bereits CAP_SYS_NICE besitzt."""
        path = self._wivrn_server_path()
        if not path:
            self._set_prio_label(tr("streaming_prio_missing"), "#bf616a")
            self.btn_vr_priority.setEnabled(False)
            return

        # Bei Nix (read-only /nix/store) ist setcap nicht moeglich
        if not venv.supports_setcap():
            self._set_prio_label(tr("streaming_prio_unsupported"), "#ebcb8b")
            self.btn_vr_priority.setEnabled(False)
            return

        try:
            res = subprocess.run(["getcap", path], stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, text=True,
                                 timeout=proc.DEFAULT_TIMEOUT)
            has_cap = "cap_sys_nice" in res.stdout.lower()
        except Exception:
            has_cap = False

        if has_cap:
            self._set_prio_label(tr("streaming_prio_on"), "#a3be8c")
            self.btn_vr_priority.setEnabled(False)
        else:
            self._set_prio_label(tr("streaming_prio_off"), "#ebcb8b")
            self.btn_vr_priority.setEnabled(True)

    def _set_prio_label(self, text, color):
        self.lbl_prio_status.setText(text)
        self.lbl_prio_status.setStyleSheet(
            f"font-weight:bold; color:{color}; font-size:13px;")

    def enable_vr_priority(self):
        """Setzt CAP_SYS_NICE auf die wivrn-server-Binary (per pkexec)."""
        path = self._wivrn_server_path()
        if not path:
            QMessageBox.warning(self, tr("error"), tr("streaming_prio_missing"))
            return
        try:
            res = subprocess.run(
                ["pkexec", "setcap", "cap_sys_nice+ep", path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                timeout=proc.LONG_TIMEOUT)
            if res.returncode == 0:
                QMessageBox.information(self, tr("streaming_prio_ok_title"),
                                        tr("streaming_prio_ok_text"))
            else:
                QMessageBox.critical(self, tr("error"),
                                     tr("streaming_prio_err") + "\n\n" + (res.stderr or "").strip())
        except Exception as e:
            QMessageBox.critical(self, tr("error"),
                                 tr("streaming_prio_err") + "\n\n" + str(e))
        self.check_vr_priority()
