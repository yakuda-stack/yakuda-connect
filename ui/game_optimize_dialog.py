#!/usr/bin/env python3
"""
ui/game_optimize_dialog.py — Assistent „✨ Optimieren“ im Spiel-Popup
=====================================================================
Ein paar kurze Fragen, dann richtet die App alles fuer das Spiel ein:

  1. (VRChat) Cache-Groesse: Erklaerung + Regler, Standard 30 GB
  2. Startoptionen: jede Option mit Erklaerung, Empfehlung vorausgewaehlt
  3. Zusammenfassung: was gleich passiert (Proton-Version wird automatisch
     gewaehlt, VRChat-Bilder-Fix laeuft automatisch, …)

Nur Oberflaeche — angewendet wird in core/tabs/games_optimize_mixin.py.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSlider, QStackedWidget, QVBoxLayout, QWidget)

from translations import tr
from ui.binding_dialog import DIALOG_CSS


def _muted(text, size=11):
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setTextFormat(Qt.RichText)
    lbl.setStyleSheet(f"color:#a6b2c0; font-size:{size}px;")
    return lbl


class GameOptimizeDialog(QDialog):
    """
    toggles: [(key, label, tip, checked, enabled)]
    cache:   None (kein VRChat / kein Prefix) oder (wert, min, max, standard)
    plan:    Zeilen fuer die Zusammenfassung, die nicht von den Fragen abhaengen
             (z. B. Proton-Version, Bilder-Fix)
    """

    def __init__(self, parent, *, game, toggles, cache=None, plan=()):
        super().__init__(parent)
        self.setObjectName("gameOptimizeDialog")
        self.setStyleSheet(DIALOG_CSS)
        self.setModal(True)
        self.resize(640, 520)
        self.setWindowTitle(tr("gopt_title").format(game=game))
        self.cache = cache
        self.plan = list(plan)
        self.checks = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)
        self.lbl_step = QLabel()
        self.lbl_step.setStyleSheet("color:#ebcb8b; font-size:11px; font-weight:bold;")
        root.addWidget(self.lbl_step)
        title = QLabel("✨  " + tr("gopt_title").format(game=game))
        title.setObjectName("bdtitle")
        root.addWidget(title)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.pages = []
        if cache is not None:
            self._add_page(self._cache_page())
        if toggles:
            self._add_page(self._toggles_page(toggles))
        self.summary_page = self._summary_page()
        self._add_page(self.summary_page)

        foot = QHBoxLayout()
        cancel = QPushButton(tr("bd_cancel"))
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        foot.addWidget(cancel)
        foot.addStretch()
        self.btn_back = QPushButton("←  " + tr("tour_back"))
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.clicked.connect(lambda: self._go(-1))
        foot.addWidget(self.btn_back)
        self.btn_next = QPushButton()
        self.btn_next.setObjectName("bdprimary")
        self.btn_next.setCursor(Qt.PointingHandCursor)
        self.btn_next.setDefault(True)
        self.btn_next.clicked.connect(self._next)
        foot.addWidget(self.btn_next)
        root.addLayout(foot)
        self._go(0)

    # ------------------------------------------------------------------ #
    def _add_page(self, w):
        self.pages.append(w)
        self.stack.addWidget(w)

    def _panel(self):
        panel = QFrame()
        panel.setObjectName("bdpanel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)
        return panel, lay

    def _cache_page(self):
        value, lo, hi, default = self.cache
        panel, lay = self._panel()
        head = QLabel(tr("gopt_cache_q"))
        head.setObjectName("bdsection")
        lay.addWidget(head)
        lay.addWidget(_muted(tr("gopt_cache_text").format(default=default)))
        row = QHBoxLayout()
        self.cache_slider = QSlider(Qt.Horizontal)
        self.cache_slider.setRange(lo, hi)
        self.cache_slider.setPageStep(10)
        self.cache_slider.setValue(value)
        row.addWidget(self.cache_slider, 1)
        self.cache_val = QLabel()
        self.cache_val.setObjectName("bdfield")
        self.cache_val.setMinimumWidth(120)
        row.addWidget(self.cache_val)
        lay.addLayout(row)
        btn_default = QPushButton(tr("gopt_cache_keep").format(default=default))
        btn_default.setCursor(Qt.PointingHandCursor)
        btn_default.clicked.connect(lambda: self.cache_slider.setValue(default))
        brow = QHBoxLayout()
        brow.addWidget(btn_default)
        brow.addStretch()
        lay.addLayout(brow)

        def show(v):
            txt = f"{v} GB"
            if v == default:
                txt += "  " + tr("games_vrc_cache_default")
            self.cache_val.setText(txt)
        self.cache_slider.valueChanged.connect(show)
        show(value)
        lay.addStretch()
        return panel

    def _toggles_page(self, toggles):
        panel, lay = self._panel()
        head = QLabel(tr("gopt_toggles_q"))
        head.setObjectName("bdsection")
        lay.addWidget(head)
        lay.addWidget(_muted(tr("gopt_toggles_text")))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")
        scroll.viewport().setAutoFillBackground(False)
        inner = QWidget()
        inner.setObjectName("goptInner")
        inner.setStyleSheet("QWidget#goptInner { background:transparent; }")
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 6, 0)
        iv.setSpacing(10)
        for key, label, tip, checked, enabled in toggles:
            cb = QCheckBox(label)
            cb.setChecked(bool(checked) and enabled)
            cb.setEnabled(enabled)
            cb.setCursor(Qt.PointingHandCursor)
            cb.setStyleSheet("QCheckBox { color:#eceff4; font-weight:bold; font-size:12px; }")
            iv.addWidget(cb)
            if tip:
                t = _muted(tip, 11)
                t.setStyleSheet("color:#a6b2c0; font-size:11px; margin-left:24px;")
                iv.addWidget(t)
            self.checks[key] = cb
        iv.addStretch()
        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)
        return panel

    def _summary_page(self):
        panel, lay = self._panel()
        head = QLabel(tr("gopt_summary_head"))
        head.setObjectName("bdsection")
        lay.addWidget(head)
        self.lbl_summary = _muted("", 12)
        self.lbl_summary.setStyleSheet("color:#d8dee9; font-size:12px;")
        lay.addWidget(self.lbl_summary)
        lay.addStretch()
        return panel

    def _refresh_summary(self):
        lines = list(self.plan)
        if self.cache is not None:
            lines.append(tr("gopt_sum_cache").format(gb=self.cache_value()))
        keys = self.enabled_keys()
        names = [self.checks[k].text() for k in keys]
        lines.append(tr("gopt_sum_toggles").format(
            items=", ".join(names) if names else tr("gopt_sum_none")))
        self.lbl_summary.setText("<br>".join("• " + l for l in lines))

    # ------------------------------------------------------------------ #
    def _go(self, delta):
        i = max(0, min(self.stack.currentIndex() + delta, len(self.pages) - 1))
        self.stack.setCurrentIndex(i)
        last = i == len(self.pages) - 1
        if last:
            self._refresh_summary()
        self.lbl_step.setText(tr("tour_step_of").format(n=i + 1, total=len(self.pages)))
        self.btn_back.setVisible(i > 0)
        self.btn_next.setText(tr("gopt_apply") if last else tr("tour_next") + "  →")

    def _next(self):
        if self.stack.currentIndex() >= len(self.pages) - 1:
            self.accept()
        else:
            self._go(1)

    def cache_value(self):
        return self.cache_slider.value() if self.cache is not None else None

    def enabled_keys(self):
        return [k for k, cb in self.checks.items() if cb.isChecked()]
