#!/usr/bin/env python3
"""
ui/customization_widget.py — Design-Bereich in den Einstellungen
================================================================
Thema waehlen, einzelne Farben nachjustieren, ein Hintergrundbild hinterlegen
und die Deckkraft der Karten einstellen.

Die eigentliche Arbeit macht ui/theme.py; hier steht nur die Bedienung. Nach
jeder Aenderung wird sofort neu eingefaerbt — ein Thema, das man erst nach
einem Neustart sieht, waehlt niemand aus.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QColorDialog, QFileDialog, QGridLayout,
                               QHBoxLayout, QLabel, QPushButton, QSlider,
                               QVBoxLayout, QWidget)

from ui import theme
from translations import tr


class ThemeCard(QPushButton):
    """Vorschaukachel eines Themas: drei Farbstreifen plus Name."""

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.theme_name = name
        self.setCheckable(True)
        # Nicht mitfaerben: die Kachel zeigt die Farben IHRES Themas. Sonst
        # sehen alle acht gleich aus (im Fehlerbild trug die Kachel "Default"
        # die Orangetoene von "Embers").
        self.setProperty("yk_no_tint", True)
        self.setFixedSize(112, 84)
        self.setCursor(Qt.PointingHandCursor)
        colors = theme.THEMES[name]
        self.setText(name.capitalize())
        # Die Streifen entstehen ueber einen Farbverlauf mit harten Stopps —
        # so bleibt die Kachel ein einzelnes Widget ohne Kindelemente.
        self.setStyleSheet(f"""
            QPushButton {{
                color: {colors['text']};
                border: 2px solid #3b4252;
                border-radius: 6px;
                font-size: 11px;
                padding-top: 46px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {colors['window']}, stop:0.33 {colors['window']},
                    stop:0.33 {colors['cards']}, stop:0.66 {colors['cards']},
                    stop:0.66 {colors['accent']}, stop:1 {colors['accent']});
            }}
            QPushButton:checked {{ border: 2px solid {colors['accent']}; }}
        """)


class CustomizationWidget(QWidget):
    """Design-Seite. Sendet ``changed``, wenn neu eingefaerbt werden muss."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme_cards = {}
        self.color_buttons = {}
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ #
    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.lbl_hint = QLabel(tr("design_hint"))
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("color:#7b88a1; font-size:11px;")
        layout.addWidget(self.lbl_hint)

        # --- Themen ---
        grid = QGridLayout()
        grid.setSpacing(8)
        for index, name in enumerate(theme.THEME_ORDER):
            card = ThemeCard(name)
            card.clicked.connect(lambda _=False, n=name: self._pick_theme(n))
            self.theme_cards[name] = card
            grid.addWidget(card, index // 5, index % 5)
        layout.addLayout(grid)

        # --- Einzelfarben ---
        head = QHBoxLayout()
        self.lbl_colors = QLabel(tr("design_colors"))
        self.lbl_colors.setStyleSheet("font-weight:bold; font-size:12px;")
        head.addWidget(self.lbl_colors)
        head.addStretch(1)
        self.btn_reset = QPushButton(tr("design_reset_colors"))
        self.btn_reset.setFixedHeight(26)
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.clicked.connect(self._reset_colors)
        head.addWidget(self.btn_reset)
        layout.addLayout(head)

        colors_grid = QGridLayout()
        colors_grid.setSpacing(6)
        for index, role in enumerate(theme.ROLE_ORDER):
            btn = QPushButton(tr(theme.ROLE_LABEL_KEYS[role]))
            # Die Farbfelder zeigen die eingestellte Farbe — auch sie duerfen
            # nicht noch einmal durch die Ersetzung laufen.
            btn.setProperty("yk_no_tint", True)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, r=role: self._pick_color(r))
            self.color_buttons[role] = btn
            colors_grid.addWidget(btn, index // 3, index % 3)
        layout.addLayout(colors_grid)

        # --- Hintergrundbild ---
        bg_row = QHBoxLayout()
        self.lbl_background = QLabel(tr("design_background"))
        self.lbl_background.setStyleSheet("font-weight:bold; font-size:12px;")
        bg_row.addWidget(self.lbl_background)
        bg_row.addStretch(1)
        self.btn_bg_none = QPushButton(tr("design_bg_none"))
        self.btn_bg_none.setFixedHeight(26)
        self.btn_bg_none.clicked.connect(lambda: self._set_background(""))
        self.btn_bg_add = QPushButton(tr("design_bg_add"))
        self.btn_bg_add.setFixedHeight(26)
        self.btn_bg_add.clicked.connect(self._choose_background)
        bg_row.addWidget(self.btn_bg_none)
        bg_row.addWidget(self.btn_bg_add)
        layout.addLayout(bg_row)

        self.lbl_bg_path = QLabel("")
        self.lbl_bg_path.setStyleSheet("color:#7b88a1; font-size:11px;")
        layout.addWidget(self.lbl_bg_path)

        # --- Deckkraft ---
        op_row = QHBoxLayout()
        self.lbl_opacity = QLabel(tr("design_card_opacity"))
        op_row.addWidget(self.lbl_opacity)
        self.sld_opacity = QSlider(Qt.Horizontal)
        # Unter 20 % waere die Schrift auf einem hellen Hintergrundbild nicht
        # mehr lesbar — deshalb ist dort Schluss.
        self.sld_opacity.setRange(20, 100)
        self.sld_opacity.setSingleStep(5)
        self.sld_opacity.sliderReleased.connect(self._opacity_done)
        op_row.addWidget(self.sld_opacity, 1)
        self.lbl_opacity_value = QLabel("100%")
        self.lbl_opacity_value.setFixedWidth(46)
        op_row.addWidget(self.lbl_opacity_value)
        layout.addLayout(op_row)
        self.sld_opacity.valueChanged.connect(
            lambda v: self.lbl_opacity_value.setText(f"{v}%"))

    # ------------------------------------------------------------------ #
    def refresh(self):
        """Bedienelemente auf den gespeicherten Zustand bringen."""
        state = theme.current()
        for name, card in self.theme_cards.items():
            card.setChecked(name == state["theme"])
        for role, btn in self.color_buttons.items():
            color = theme.role_color(role)
            text_color = "#1a1d23" if theme._lightness(color) > 0.6 else "#eceff4"
            btn.setStyleSheet(
                f"QPushButton {{ background-color:{color}; color:{text_color};"
                f" border:1px solid #4c566a; border-radius:4px; font-size:11px; }}")
        self.sld_opacity.blockSignals(True)
        self.sld_opacity.setValue(state["card_opacity"])
        self.sld_opacity.blockSignals(False)
        self.lbl_opacity_value.setText(f"{state['card_opacity']}%")
        self.lbl_bg_path.setText(state["background"] or tr("design_bg_none_set"))

    def retranslate(self):
        self.lbl_hint.setText(tr("design_hint"))
        self.lbl_colors.setText(tr("design_colors"))
        self.btn_reset.setText(tr("design_reset_colors"))
        self.lbl_background.setText(tr("design_background"))
        self.btn_bg_none.setText(tr("design_bg_none"))
        self.btn_bg_add.setText(tr("design_bg_add"))
        self.lbl_opacity.setText(tr("design_card_opacity"))
        for role, btn in self.color_buttons.items():
            btn.setText(tr(theme.ROLE_LABEL_KEYS[role]))
        self.refresh()

    # ------------------------------------------------------------------ #
    def _pick_theme(self, name):
        theme.set_theme(name)
        theme.save()
        self.refresh()
        self.changed.emit()

    def _pick_color(self, role):
        start = QColor(theme.role_color(role))
        chosen = QColorDialog.getColor(start, self, tr(theme.ROLE_LABEL_KEYS[role]))
        if not chosen.isValid():
            return
        theme.set_color(role, chosen.name())
        theme.save()
        self.refresh()
        self.changed.emit()

    def _reset_colors(self):
        theme.reset_colors()
        theme.save()
        self.refresh()
        self.changed.emit()

    def _choose_background(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("design_bg_add"), "",
            "Bilder (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self._set_background(path)

    def _set_background(self, path):
        theme.set_background(path)
        theme.save()
        self.refresh()
        self.changed.emit()

    def _opacity_done(self):
        theme.set_card_opacity(self.sld_opacity.value())
        theme.save()
        self.changed.emit()
