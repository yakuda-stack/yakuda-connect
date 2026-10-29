#!/usr/bin/env python3
"""
ui/game_settings_overlay.py — Spiel-Einstellungen als Popup im Fenster
======================================================================
Frueher klappte unter der Kachel ein Panel auf. Jetzt erscheint es als
Karte in der Mitte des Hauptfensters, darunter ein abgedunkelter
Hintergrund. Schliessen: kleines ✕, Esc oder Klick neben die Karte.

Bewusst ein Kind-Widget des Hauptfensters und KEIN eigenes Fenster: unter
Wayland darf eine App eigene Fenster nicht selbst positionieren — ein
QDialog landet je nach Compositor irgendwo. So sitzt es immer mittig.

Dazu ``CollapsibleSection``: Abschnitt mit Kopfzeile (▾/▸), der sich
auf- und zuklappen laesst. Der Zustand wird ueber ``state`` (ein dict des
Aufrufers) gemerkt, damit ein Neuaufbau (z. B. nach „Verwenden“) die
offenen Abschnitte nicht wieder zuklappt.
"""
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)


class GameSettingsOverlay(QWidget):
    closed = Signal()

    MAX_W = 860
    MARGIN = 40

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.StrongFocus)
        self.hide()

        self.card = QFrame(self)
        self.card.setObjectName("gameSettingsCard")
        self.card.setStyleSheet(
            "QFrame#gameSettingsCard { background-color:#21252b;"
            " border:1px solid #88c0d0; border-radius:10px; }")
        v = QVBoxLayout(self.card)
        v.setContentsMargins(16, 10, 10, 14)
        v.setSpacing(6)

        head = QHBoxLayout()
        self.lbl_title = QLabel("")
        self.lbl_title.setStyleSheet(
            "font-weight:bold; color:#eceff4; font-size:16px; border:none;")
        head.addWidget(self.lbl_title)
        self.head_extra = QHBoxLayout()
        head.addLayout(self.head_extra)
        head.addStretch()
        btn_x = QPushButton("✕")
        btn_x.setCursor(Qt.PointingHandCursor)
        btn_x.setFixedSize(26, 26)
        btn_x.setStyleSheet(
            "QPushButton { background:transparent; color:#7b88a1; border:none;"
            " font-size:15px; font-weight:bold; }"
            " QPushButton:hover { color:#bf616a; }")
        btn_x.clicked.connect(self.close_overlay)
        head.addWidget(btn_x)
        v.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")
        v.addWidget(self.scroll)

        self._content = None
        parent.installEventFilter(self)

    def set_content(self, title, widget, keep_scroll=False):
        """Inhalt tauschen. keep_scroll: Scrollposition behalten (Neuaufbau)."""
        pos = self.scroll.verticalScrollBar().value() if keep_scroll else 0
        old = self.scroll.takeWidget()
        if old is not None:
            old.hide()
            old.deleteLater()
        self._clear_head_extra()
        self.lbl_title.setText(title)
        self._content = widget
        self.scroll.setWidget(widget)
        self.scroll.verticalScrollBar().setValue(pos)

    def _clear_head_extra(self):
        while self.head_extra.count():
            item = self.head_extra.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def add_head_widget(self, widget):
        """Widgets neben dem Titel (z. B. Play-Knopf)."""
        self.head_extra.addWidget(widget)

    def open_overlay(self):
        self._relayout()
        self.show()
        self.raise_()
        self.setFocus()

    def close_overlay(self):
        if not self.isVisible():
            return
        self.hide()
        old = self.scroll.takeWidget()
        if old is not None:
            old.hide()
            old.deleteLater()
        self._content = None
        self.closed.emit()

    def _relayout(self):
        p = self.parentWidget()
        if p is None:
            return
        self.setGeometry(p.rect())
        w = min(self.MAX_W, max(320, self.width() - 2 * self.MARGIN))
        h = max(240, self.height() - 2 * self.MARGIN)
        self.card.setGeometry((self.width() - w) // 2, (self.height() - h) // 2, w, h)

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() == QEvent.Resize and self.isVisible():
            self._relayout()
        return False

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 150))

    def mousePressEvent(self, event):
        if not self.card.geometry().contains(event.position().toPoint()):
            self.close_overlay()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close_overlay()
            return
        super().keyPressEvent(event)


class CollapsibleSection(QFrame):
    """Abschnitt mit klickbarer Kopfzeile. ``body`` ist ein QVBoxLayout."""

    def __init__(self, title, key, state, default_open=False, parent=None):
        super().__init__(parent)
        self.setObjectName("collSection")
        self.setStyleSheet(
            "QFrame#collSection { background-color:#262a32; border:1px solid #2e3440;"
            " border-radius:6px; }")
        self._key = key
        self._state = state
        is_open = state.get(key, default_open)

        v = QVBoxLayout(self)
        v.setContentsMargins(10, 6, 10, 8)
        v.setSpacing(6)

        self.btn_head = QPushButton()
        self.btn_head.setCursor(Qt.PointingHandCursor)
        self.btn_head.setStyleSheet(
            "QPushButton { background:transparent; color:#88c0d0; border:none;"
            " font-size:12px; font-weight:bold; text-align:left; padding:2px 0; }"
            " QPushButton:hover { color:#eceff4; }")
        self._title = title
        self.btn_head.clicked.connect(self.toggle)
        v.addWidget(self.btn_head)

        self.body_widget = QWidget()
        self.body_widget.setStyleSheet("background:transparent;")
        self.body = QVBoxLayout(self.body_widget)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(8)
        v.addWidget(self.body_widget)

        self._set_open(is_open)

    def _set_open(self, is_open):
        self._open = is_open
        self.body_widget.setVisible(is_open)
        self.btn_head.setText(("▾  " if is_open else "▸  ") + self._title)
        self._state[self._key] = is_open

    def toggle(self):
        self._set_open(not self._open)
