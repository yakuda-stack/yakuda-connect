#!/usr/bin/env python3
"""
ui/xr_deadzone_panel.py — Regler fuer die Stick-Deadzone (xrBinder)
===================================================================
Ein Panel mit drei Reglern (Links, Rechts, Beide). Arbeitet direkt auf dem
uebergebenen Umbelegungs-Dict (wird veraendert). Genutzt vom OpenXR-Dialog
(ui/xr_button_dialog.py) und vom OpenVR-Dialog (ui/binding_dialog.py) —
geschrieben wird immer in die xrBinder-Belegung.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QToolButton,
                               QVBoxLayout)

import xr_bindings as xr
import xrbinder as xb
from translations import tr


class DeadzonePanel(QFrame):
    def __init__(self, state, mappings, parent=None, controller_type=xr.DEFAULT_CT):
        super().__init__(parent)
        self.state = state
        self.mappings = mappings
        self.ct = controller_type
        self.setObjectName("bdpanel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(12)
        intro = QLabel(tr("xrd_deadzone_tip"))
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#a6b2c0; font-size:11px;")
        lay.addWidget(intro)
        self.rows = {}
        for key, label in (("left", tr("obah_left")), ("right", tr("obah_right")),
                           ("both", tr("xrd_deadzone_both"))):
            row = QHBoxLayout()
            row.setSpacing(10)
            name = QLabel(label.upper())
            name.setObjectName("bdsection")
            name.setMinimumWidth(80)
            row.addWidget(name)
            sl = QSlider(Qt.Horizontal)
            sl.setRange(0, int(xb.DEADZONE_MAX * 100))
            sl.setSingleStep(1)
            sl.setPageStep(5)
            sl.setToolTip(tr("xrd_deadzone_value_tip"))
            sl.valueChanged.connect(lambda v, k=key: self._changed(k, v))
            row.addWidget(sl, 1)
            val = QLabel()
            val.setMinimumWidth(44)
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val.setObjectName("bdfield")
            row.addWidget(val)
            rst = QToolButton()
            rst.setObjectName("bdx")
            rst.setText("↺")
            rst.setToolTip(tr("xrd_deadzone_reset_tip"))
            rst.setCursor(Qt.PointingHandCursor)
            rst.clicked.connect(lambda _=False, k=key: self._changed(k, 0, sync=True))
            row.addWidget(rst)
            lay.addLayout(row)
            info = QLabel()
            info.setWordWrap(True)
            info.setStyleSheet("color:#4c566a; font-size:11px; margin-left:90px;")
            lay.addWidget(info)
            self.rows[key] = {"slider": sl, "value": val, "reset": rst, "info": info}
        tpl_row = QHBoxLayout()
        self.btn_template = QPushButton(tr("xrb_template"))
        self.btn_template.setCursor(Qt.PointingHandCursor)
        self.btn_template.setMinimumHeight(30)
        self.btn_template.setToolTip(tr("xrd_deadzone_template_tip"))
        self.btn_template.clicked.connect(self._apply_template)
        tpl_row.addWidget(self.btn_template)
        tpl_row.addStretch()
        lay.addLayout(tpl_row)
        self.lbl_template = QLabel()
        self.lbl_template.setWordWrap(True)
        self.lbl_template.setStyleSheet("color:#ebcb8b; font-size:11px;")
        lay.addWidget(self.lbl_template)
        lay.addStretch()
        self.sync()

    @staticmethod
    def _sides(key):
        return ("left", "right") if key == "both" else (key,)

    def _changed(self, key, value, sync=False):
        if getattr(self, "_dz_syncing", False):
            return
        v = 0.0 if value <= 0 else max(xb.DEADZONE_MIN, value / 100)
        for side in self._sides(key):
            xr.set_stick_deadzone(self.state, self.mappings, side, v)
        self.sync()

    def _apply_template(self):
        """Ohne gemeldete Tasten liegt keine Funktion auf dem Stick — die
        Vorlage legt eine Standardbelegung an, danach gehen die Regler."""
        mappings, matched, total = xr.template_mappings(self.state, self.ct)
        if not mappings:
            self.lbl_template.setText(tr("xrb_template_none"))
            return
        self.mappings.clear()
        self.mappings.update(mappings)
        self.lbl_template.setText(tr("xrd_deadzone_template_applied").format(
            matched=matched, total=total))
        self.sync()

    def sync(self):
        """Regler, Werte und Hinweise aus den Umbelegungen neu setzen."""
        self._dz_syncing = True
        try:
            vals = {s: round(xr.stick_deadzone(self.state, self.mappings, s) * 100)
                    for s in ("left", "right")}
            acts = {s: xr.stick_actions(self.state, self.mappings, s) for s in ("left", "right")}
            for key, row in self.rows.items():
                sides = self._sides(key)
                usable = [s for s in sides if acts[s]]
                cur = [vals[s] for s in usable]
                same = len(set(cur)) == 1
                v = cur[0] if cur and same else 0
                row["slider"].setEnabled(bool(usable))
                row["slider"].setValue(v)
                if not cur:
                    txt = "—"
                elif not same:
                    txt = "≠"
                else:
                    txt = f"{v} %" if v else tr("xrd_deadzone_off")
                row["value"].setText(txt)
                row["reset"].setEnabled(any(cur))
                if key == "both":
                    row["info"].setText(tr("xrd_deadzone_differs") if cur and not same else "")
                    row["info"].setVisible(bool(cur) and not same)
                elif usable:
                    names = ", ".join(sorted({(a.get("description") or a["name"])
                                              for a, _h in acts[key]}))
                    row["info"].setText(tr("xrd_deadzone_affects").format(actions=names))
                else:
                    row["info"].setText(tr("xrd_deadzone_none"))
            self.btn_template.setVisible(
                xr.template_offered(self.ct, self.state, self.mappings))
        finally:
            self._dz_syncing = False


_MODE_BOX_CSS = """
    QFrame#dzModeBox { background:#3a3527; border:1px solid #ebcb8b; border-radius:6px; }
    QFrame#dzModeBox QCheckBox { color:#eceff4; font-size:12px; font-weight:bold; }
    QFrame#dzModeBox QCheckBox::indicator { width:16px; height:16px; }
    QFrame#dzModeBox QLabel { color:#d8c79a; font-size:11px; background:transparent; border:none; }
"""


def make_mode_box(checkbox):
    """Haken „Ich nutze nicht xrizer“ in einen auffaelligen Kasten packen —
    sonst wird er leicht uebersehen."""
    box = QFrame()
    box.setObjectName("dzModeBox")
    box.setStyleSheet(_MODE_BOX_CSS)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(12, 8, 12, 8)
    lay.setSpacing(2)
    checkbox.setText("⚠  " + tr("bd_deadzone_no_xrizer"))
    lay.addWidget(checkbox)
    hint = QLabel(tr("bd_deadzone_no_xrizer_hint"))
    hint.setWordWrap(True)
    lay.addWidget(hint)
    return box

