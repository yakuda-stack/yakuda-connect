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
  * Standard    alles zuruecksetzen, was diese Taste betrifft

Gearbeitet wird auf einer Kopie der Umbelegungen; geschrieben wird erst mit
„Speichern“ im Controls-Tab. Die Regeln stehen in core/xr_bindings.py.
"""
import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton,
                               QToolButton, QVBoxLayout, QWidget)

import xr_bindings as xr
import xrbinder as xb
from translations import get_language, tr
from ui.binding_dialog import DIALOG_CSS

KIND_KEYS = {"click": "xrd_kind_click", "touch": "xrd_kind_touch", "value": "xrd_kind_value",
             "force": "xrd_kind_force", "x": "xrd_kind_x", "y": "xrd_kind_y",
             "dir": "xrd_kind_dir"}


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

        panel = QFrame()
        panel.setObjectName("bdpanel")
        self.body = QVBoxLayout(panel)
        self.body.setContentsMargins(14, 12, 14, 12)
        self.body.setSpacing(10)
        root.addWidget(panel, 1)

        hint = QLabel(tr("xrd_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#4c566a; font-size:11px;")
        root.addWidget(hint)

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

    def _reset(self):
        xr.reset_paths(self.state, self.mappings, self.paths)
        self._render()
