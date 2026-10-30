#!/usr/bin/env python3
"""
ui/deadzone_dialog.py — Knopf „◎ Deadzone“ im Controls-Tab
==========================================================
Schneller Zugang fuer neue Nutzer: Deadzone fuer BEIDE Sticks des
gewaehlten Spiels, ohne erst auf die Joystick-Karte zu klicken.

  * Standard: xrBinder (OpenXR) — wirkt auch mit xrizer (DeadzonePanel).
  * Haken „nicht xrizer“ (nur OpenVR-Spiele): deadzone_pct in die
    SteamVR-Bindings, ueber alle Action Sets.

Gearbeitet wird auf Kopien; der Aufrufer speichert nach „Übernehmen“.
"""
import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSlider, QToolButton, QVBoxLayout, QWidget)

import obah_editor as oe
from translations import tr
from ui.binding_dialog import DIALOG_CSS


class DeadzoneDialog(QDialog):
    def __init__(self, parent, *, dz, game, binding=None, controller_type=""):
        super().__init__(parent)
        self.setObjectName("deadzoneDialog")
        self.setStyleSheet(DIALOG_CSS)
        self.setModal(True)
        self.resize(620, 440)
        self.setWindowTitle(tr("dzd_title").format(game=game))
        self.dz = dz or {}
        self.ct = controller_type
        self.dz_mappings = (copy.deepcopy(self.dz["mappings"])
                            if "mappings" in self.dz else None)
        self.binding = copy.deepcopy(binding) if binding is not None else None
        self.pct_changed = False
        self.dz_steamvr = bool(self.binding is not None and self.dz.get("steamvr"))

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)
        t = QLabel("◎  " + tr("xrd_deadzone") + f"  ·  {game}")
        t.setObjectName("bdtitle")
        root.addWidget(t)

        self.chk_steamvr = None
        if self.binding is not None:
            self.chk_steamvr = QCheckBox(tr("bd_deadzone_no_xrizer"))
            self.chk_steamvr.setToolTip(tr("bd_deadzone_no_xrizer_tip"))
            self.chk_steamvr.setChecked(self.dz_steamvr)
            self.chk_steamvr.toggled.connect(self._mode_changed)
            from ui.xr_deadzone_panel import make_mode_box
            root.addWidget(make_mode_box(self.chk_steamvr))

        self.xr_box = self._build_xr_box()
        root.addWidget(self.xr_box, 1)
        self.pct_box = self._build_pct_box() if self.binding is not None else None
        if self.pct_box is not None:
            root.addWidget(self.pct_box, 1)

        foot = QHBoxLayout()
        foot.addStretch()
        cancel = QPushButton(tr("bd_cancel"))
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        foot.addWidget(cancel)
        ok = QPushButton("✓  " + tr("bd_apply"))
        ok.setObjectName("bdprimary")
        ok.setCursor(Qt.PointingHandCursor)
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        foot.addWidget(ok)
        root.addLayout(foot)
        self._mode_changed(self.dz_steamvr)

    # ------------------------------------------------------------------ #
    def _build_xr_box(self):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        if self.dz_mappings is not None:
            from ui.xr_deadzone_panel import DeadzonePanel
            if self.binding is not None:
                info = QLabel(tr("bd_deadzone_xr_info").format(game=self.dz.get("game", "")))
                info.setWordWrap(True)
                info.setStyleSheet("color:#7b88a1; font-size:11px;")
                lay.addWidget(info)
            panel = DeadzonePanel(self.dz["state"], self.dz_mappings,
                                  controller_type=self.ct or "oculus_touch")
            self.dz_rows = panel.rows
            lay.addWidget(panel, 1)
        else:
            note = QLabel(self.dz.get("note", ""))
            note.setWordWrap(True)
            note.setObjectName("bdpanel")
            note.setStyleSheet("color:#ebcb8b; font-size:12px; padding:14px;")
            note.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            lay.addWidget(note, 1)
        return box

    def _build_pct_box(self):
        panel = QFrame()
        panel.setObjectName("bdpanel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)
        info = QLabel(tr("dzd_pct_info"))
        info.setWordWrap(True)
        info.setStyleSheet("color:#7b88a1; font-size:11px;")
        lay.addWidget(info)
        self.pct_rows = {}
        for key, label in (("left", tr("obah_left")), ("right", tr("obah_right")),
                           ("both", tr("xrd_deadzone_both"))):
            row = QHBoxLayout()
            row.setSpacing(10)
            name = QLabel(label.upper())
            name.setObjectName("bdsection")
            name.setMinimumWidth(80)
            row.addWidget(name)
            sl = QSlider(Qt.Horizontal)
            sl.setRange(0, 100)
            sl.setPageStep(5)
            sl.valueChanged.connect(lambda v, k=key: self._pct_changed(k, v))
            row.addWidget(sl, 1)
            val = QLabel()
            val.setObjectName("bdfield")
            val.setMinimumWidth(44)
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(val)
            rst = QToolButton()
            rst.setObjectName("bdx")
            rst.setText("↺")
            rst.setCursor(Qt.PointingHandCursor)
            rst.clicked.connect(lambda _=False, k=key: self._pct_changed(k, 0))
            row.addWidget(rst)
            lay.addLayout(row)
            self.pct_rows[key] = {"slider": sl, "value": val, "reset": rst}
        self.pct_hint = QLabel()
        self.pct_hint.setWordWrap(True)
        self.pct_hint.setStyleSheet("color:#ebcb8b; font-size:11px;")
        lay.addWidget(self.pct_hint)
        lay.addStretch()
        return panel

    @staticmethod
    def _sides(key):
        return ("left", "right") if key == "both" else (key,)

    def _pct_changed(self, key, value):
        if getattr(self, "_pct_syncing", False):
            return
        for side in self._sides(key):
            if oe.set_stick_deadzone_pct(self.binding, self.ct, side, value):
                self.pct_changed = True
        self._sync_pct()

    def _sync_pct(self):
        self._pct_syncing = True
        try:
            vals = {s: oe.stick_deadzone_pct(self.binding, self.ct, s) for s in ("left", "right")}
            for key, row in self.pct_rows.items():
                cur = [v for s in self._sides(key) for v in vals[s]]
                same = len(set(cur)) <= 1
                v = cur[0] if cur and same else 0
                row["slider"].setEnabled(bool(cur))
                row["slider"].setValue(v)
                row["value"].setText("—" if not cur else ("≠" if not same else
                                     (f"{v} %" if v else tr("xrd_deadzone_off"))))
                row["reset"].setEnabled(any(cur))
            none = not vals["left"] and not vals["right"]
            self.pct_hint.setText(tr("dzd_pct_none") if none else "")
        finally:
            self._pct_syncing = False

    def _mode_changed(self, steamvr):
        self.dz_steamvr = bool(steamvr)
        self.xr_box.setVisible(not self.dz_steamvr)
        if self.pct_box is not None:
            self.pct_box.setVisible(self.dz_steamvr)
            if self.dz_steamvr:
                self._sync_pct()
