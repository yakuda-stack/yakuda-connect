#!/usr/bin/env python3
"""
ui/xr_button_dialog.py — eine Taste eines OpenXR-Spiels belegen (xrBinder)
==========================================================================
Gegenstueck zu ui/binding_dialog.py fuer OpenXR-Spiele, im selben Stil.
Klick auf eine Karte in der Controller-Ansicht oeffnet ihn:

    X · Links
    DRUECKEN      Oculus Touch (L) X Press            ✕
                  ＋ Funktion zuweisen
    BERUEHREN     (nichts)
                  ＋ Funktion zuweisen
    ↺ Standard fuer diese Taste        Abbrechen   ✓ Uebernehmen

  * ✕           Funktion von der Taste nehmen (war sie hierher verschoben,
                geht sie an ihre alte Taste zurueck; sonst wird sie abgeschaltet)
  * ＋           Funktion des Spiels auf diese Taste legen (sie verschwindet
                von ihrer bisherigen Taste). Angeboten wird nur, was vom Typ
                her passt.
  * ⇄ Kippen    nur beim Stick-Klick: Funktion loest auch aus, wenn der
                Stick nur gekippt wird (wie Community-Bindings unter SteamVR)
  * Deadzone    nur beim Stick: eigener Tab oben mit Reglern Links / Rechts /
                Beide (0 = aus, 5–50 %), je mit ↺. Kleiner Ausschlag zaehlt als
                Mitte — gegen Stick-Drift. Gilt fuer alle Stick-Richtungen des
                Spiels auf diesem Stick.
  * Standard    alles zuruecksetzen, was diese Taste betrifft

Gearbeitet wird auf einer Kopie der Umbelegungen; geschrieben wird erst mit
„Speichern“ im Controls-Tab. Die Regeln stehen in core/xr_bindings.py.
"""
import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton,
                               QSlider, QSpinBox, QTabBar, QToolButton, QVBoxLayout, QWidget)

import xr_bindings as xr
import xrbinder as xb
from translations import get_language, tr
from ui.binding_dialog import DIALOG_CSS

KIND_KEYS = {"click": "xrd_kind_click", "touch": "xrd_kind_touch", "value": "xrd_kind_value",
             "force": "xrd_kind_force", "x": "xrd_kind_x", "y": "xrd_kind_y",
             "dir": "xrd_kind_dir"}


_TAB_CSS = """
    QTabBar::tab { background:#2e3440; color:#a6b2c0; padding:5px 14px; margin-right:4px;
                   border:1px solid #3b4252; border-radius:4px; font-size:12px; }
    QTabBar::tab:hover { color:#88c0d0; }
    QTabBar::tab:selected { background:#3b4f63; color:#eceff4; border-color:#5e81ac; }
"""


_TILT_CSS = """
    QToolButton { background:#2e3440; color:#a6b2c0; font-size:11px; padding:2px 10px;
                  border-radius:4px; border:1px solid #3b4252; }
    QToolButton:hover { color:#88c0d0; border-color:#4c566a; }
    QToolButton:checked { background:#3b4f63; color:#eceff4; border-color:#5e81ac; }
"""


def kind_label(kind):
    return tr(KIND_KEYS.get(kind, "xrd_kind_click")) if kind in KIND_KEYS else kind


def _lang():
    return "de" if get_language() == "de" else "en"


class XrButtonDialog(QDialog):
    def __init__(self, parent, *, controller_type, side, input_def, state, mappings, game):
        super().__init__(parent)
        self.setObjectName("xrButtonDialog")
        self.setStyleSheet(DIALOG_CSS)
        self.setModal(True)
        self.resize(620, 420)
        self.ct = controller_type
        self.side = side
        self.d = input_def
        self.state = state
        self.mappings = copy.deepcopy(mappings)
        base = xr.OBAH_TO_XR[controller_type][input_def.path]
        self.comps = xr.components(controller_type, side, base)
        self.paths = [xr.comp_path(side, c) for c in self.comps]

        name = input_def.name[:1].upper() + input_def.name[1:]
        side_txt = {"left": tr("obah_left"), "right": tr("obah_right")}.get(side, "")
        title = f"{name}  ·  {side_txt}" if side_txt else name
        self.setWindowTitle(tr("xrd_window_title").format(button=title, game=game))

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)
        t = QLabel(title)
        t.setObjectName("bdtitle")
        root.addWidget(t)
        sub = QLabel(tr("xrd_subtitle").format(game=game))
        sub.setObjectName("bdpath")
        root.addWidget(sub)

        # Nur beim Stick: Tabs „Belegung | Deadzone“
        self.has_deadzone_tab = xr.DEADZONE_COMP in self.comps
        self.tabs = None
        if self.has_deadzone_tab:
            self.tabs = QTabBar()
            self.tabs.setObjectName("xrdTabs")
            self.tabs.setDrawBase(False)
            self.tabs.setExpanding(False)
            self.tabs.setStyleSheet(_TAB_CSS)
            self.tabs.addTab(tr("xrd_tab_bindings"))
            self.tabs.addTab("◎  " + tr("xrd_deadzone"))
            root.addWidget(self.tabs)

        panel = QFrame()
        panel.setObjectName("bdpanel")
        self.body = QVBoxLayout(panel)
        self.body.setContentsMargins(14, 12, 14, 12)
        self.body.setSpacing(10)
        root.addWidget(panel, 1)
        self.panel = panel

        self.dz_panel = None
        if self.has_deadzone_tab:
            self.dz_panel = self._build_deadzone_panel()
            self.dz_panel.hide()
            root.addWidget(self.dz_panel, 1)

        hint = QLabel(tr("xrd_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#4c566a; font-size:11px;")
        root.addWidget(hint)
        self.hint = hint

        foot = QHBoxLayout()
        self.btn_reset = QPushButton("↺  " + tr("xrd_reset_button"))
        self.btn_reset.setObjectName("bddanger")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.clicked.connect(self._reset)
        foot.addWidget(self.btn_reset)
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
        self._render()
        if self.tabs is not None:
            self.tabs.currentChanged.connect(self._show_tab)

    # ------------------------------------------------------------------ #
    #  Deadzone-Tab
    # ------------------------------------------------------------------ #
    def _show_tab(self, index):
        dz = index == 1
        self.panel.setVisible(not dz)
        self.dz_panel.setVisible(dz)
        self.hint.setText(tr("xrd_deadzone_hint") if dz else tr("xrd_hint"))
        self.btn_reset.setVisible(not dz)
        if not dz:
            self._render()          # Kartentexte (Deadzone-Angabe) auffrischen
        else:
            self._sync_deadzone()

    def _build_deadzone_panel(self):
        panel = QFrame()
        panel.setObjectName("bdpanel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(12)
        intro = QLabel(tr("xrd_deadzone_tip"))
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#a6b2c0; font-size:11px;")
        lay.addWidget(intro)
        self.dz_rows = {}
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
            sl.valueChanged.connect(lambda v, k=key: self._dz_changed(k, v))
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
            rst.clicked.connect(lambda _=False, k=key: self._dz_changed(k, 0, sync=True))
            row.addWidget(rst)
            lay.addLayout(row)
            info = QLabel()
            info.setWordWrap(True)
            info.setStyleSheet("color:#4c566a; font-size:11px; margin-left:90px;")
            lay.addWidget(info)
            self.dz_rows[key] = {"slider": sl, "value": val, "reset": rst, "info": info}
        lay.addStretch()
        self._sync_deadzone()
        return panel

    def _dz_sides(self, key):
        return ("left", "right") if key == "both" else (key,)

    def _dz_changed(self, key, value, sync=False):
        if getattr(self, "_dz_syncing", False):
            return
        v = 0.0 if value <= 0 else max(xb.DEADZONE_MIN, value / 100)
        for side in self._dz_sides(key):
            xr.set_stick_deadzone(self.state, self.mappings, side, v)
        self._sync_deadzone()

    def _sync_deadzone(self):
        """Regler, Werte und Hinweise aus den Umbelegungen neu setzen."""
        self._dz_syncing = True
        try:
            vals = {s: round(xr.stick_deadzone(self.state, self.mappings, s) * 100)
                    for s in ("left", "right")}
            acts = {s: xr.stick_actions(self.state, self.mappings, s) for s in ("left", "right")}
            for key, row in self.dz_rows.items():
                sides = self._dz_sides(key)
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
        finally:
            self._dz_syncing = False

    # ------------------------------------------------------------------ #
    def _clear(self):
        while self.body.count():
            item = self.body.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def _render(self):
        self._clear()
        for comp, path in zip(self.comps, self.paths, strict=True):
            row = QWidget()
            row.setStyleSheet("background:transparent;")
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(12)
            sec = QLabel(kind_label(xr.comp_kind(comp)).upper())
            sec.setObjectName("bdsection")
            sec.setMinimumWidth(110)
            sec.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            h.addWidget(sec, 0, Qt.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(4)
            available = any(xr.source_for(comp, t) and xr.source_available(
                self.state, xr.source_for(comp, t), self.side) for t in xr.TYPE_NAMES)
            for act, hand, moved in xr.on_path(self.state, self.mappings, path):
                line = QHBoxLayout()
                lbl = QLabel((xr.MOVED_MARK if moved else "") + (act.get("description") or act["name"]))
                lbl.setObjectName("bdfield")
                lbl.setToolTip(act["name"])
                line.addWidget(lbl, 1)
                if xr.tilt_capable(self.state, act, self.side, comp):
                    t = QToolButton()
                    t.setCheckable(True)
                    t.setChecked(xr.has_tilt(self.mappings, act["name"], hand))
                    t.setText("⇄  " + tr("xrd_tilt"))
                    t.setToolTip(tr("xrd_tilt_tip"))
                    t.setCursor(Qt.PointingHandCursor)
                    t.setStyleSheet(_TILT_CSS)
                    t.toggled.connect(lambda on, a=act, hd=hand: self._tilt(a, hd, on))
                    line.addWidget(t)
                    if xr.has_tilt(self.mappings, act["name"], hand):
                        # Schwelle gegen Stick-Drift: ab wie viel Ausschlag Kippen zaehlt
                        sb = QSpinBox()
                        sb.setRange(int(xb.TILT_MIN * 100), int(xb.TILT_MAX * 100))
                        sb.setSingleStep(5)
                        sb.setSuffix(" %")
                        sb.setValue(round(xr.tilt_threshold(self.mappings, act["name"], hand) * 100))
                        sb.setToolTip(tr("xrd_tilt_threshold_tip"))
                        sb.valueChanged.connect(
                            lambda v, a=act, hd=hand: xr.set_tilt_threshold(self.mappings, a["name"], hd, v / 100))
                        line.addWidget(sb)
                x = QToolButton()
                x.setObjectName("bdx")
                x.setText("✕")
                x.setToolTip(tr("xrd_remove_tip"))
                x.setCursor(Qt.PointingHandCursor)
                x.clicked.connect(lambda _=False, a=act, hd=hand, p=path: self._remove(a, hd, p))
                line.addWidget(x)
                col.addLayout(line)
            add = QToolButton()
            add.setObjectName("bdadd")
            add.setText("＋  " + tr("xrd_add"))
            add.setCursor(Qt.PointingHandCursor)
            add.setPopupMode(QToolButton.InstantPopup)
            menu = self._add_menu(comp)
            add.setMenu(menu)
            add.setEnabled(available and not menu.isEmpty())
            if not available:
                add.setToolTip(tr("xrd_not_available"))
            col.addWidget(add, 0, Qt.AlignLeft)
            h.addLayout(col, 1)
            self.body.addWidget(row)
        self.body.addStretch()
        self.btn_reset.setEnabled(xr.has_changes_on(self.state, self.mappings, self.paths))

    def _add_menu(self, comp):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background:#21252b; color:#d8dee9; border:1px solid #3b4252; }"
                           " QMenu::item { padding:6px 18px; }"
                           " QMenu::item:selected { background:#3b4252; color:#88c0d0; }"
                           " QMenu::item:disabled { color:#4c566a; }")
        lang = _lang()
        here = xr.comp_path(self.side, comp)
        main, other = [], []
        for act in xr.actions(self.state):
            src = xr.source_for(comp, act["type"])
            if not src or not xr.source_available(self.state, src, self.side):
                continue
            hand = xr.hand_for(act, self.side)
            now = xr.effective_paths(self.state, self.mappings, act["name"], hand)
            if here in now:
                continue
            label = act.get("description") or act["name"]
            # Gehoert zum aktiven Controller, wenn sie dort eine Standard-Taste
            # hat oder gerade irgendwo liegt. Der Rest (andere Controller-Profile,
            # Funktionen ohne Taste) kommt unten in ein Untermenue.
            if now or xr.default_paths(self.state, act["name"], ""):
                where = " / ".join(xb.path_label(p, lang) for p in now) or tr("xrd_nowhere")
                main.append((label, where, act))
            else:
                other.append((label, "", act))
        main.sort(key=lambda e: (e[1] == tr("xrd_nowhere"), e[0].lower()))
        other.sort(key=lambda e: e[0].lower())
        for label, where, act in main:
            a = menu.addAction(f"{label}    ({where})")
            a.triggered.connect(lambda _=False, ac=act, c=comp: self._assign(ac, c))
        if other:
            if main:
                menu.addSeparator()
            sub = menu.addMenu(tr("xrd_other").format(n=len(other)))
            sub.setStyleSheet(menu.styleSheet() + " QMenu { color:#7b88a1; }")
            sub.setToolTipsVisible(True)
            for label, _where, act in other:
                a = sub.addAction(label)
                a.setToolTip(tr("xrd_other_tip"))
                a.triggered.connect(lambda _=False, ac=act, c=comp: self._assign(ac, c))
        return menu

    def _assign(self, act, comp):
        xr.assign(self.state, self.mappings, act, self.side, comp)
        self._render()

    def _remove(self, act, hand, path):
        xr.unassign(self.state, self.mappings, act, hand, path)
        self._render()

    def _tilt(self, act, hand, on):
        xr.set_tilt(self.state, self.mappings, act, hand, self.side, on)
        self._render()

    def _reset(self):
        xr.reset_paths(self.state, self.mappings, self.paths)
        self._render()
