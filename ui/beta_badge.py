#!/usr/bin/env python3
"""
ui/beta_badge.py — blaues „BETA“-Abzeichen
==========================================
Kennzeichnet Beta-Builds (z. B. Proton-RTSP-Wayland-GE) in der
Proton-Auswahl. Ein Icon faellt in der Liste mehr auf als ein „(Beta)“
hinter dem Namen.
"""
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

COLOR = "#5e81ac"
TEXT_COLOR = "#eceff4"
ICON_SIZE = QSize(34, 14)

_icon = None


def beta_icon():
    """Kleines blaues Schild mit „BETA“, einmal gebaut und wiederverwendet."""
    global _icon
    if _icon is not None:
        return _icon
    ratio = 2
    pix = QPixmap(ICON_SIZE * ratio)
    pix.setDevicePixelRatio(ratio)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(COLOR))
    rect = QRectF(0, 0, ICON_SIZE.width(), ICON_SIZE.height())
    painter.drawRoundedRect(rect, 3, 3)
    font = QFont()
    font.setPixelSize(9)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(TEXT_COLOR))
    painter.drawText(rect, Qt.AlignCenter, "BETA")
    painter.end()
    _icon = QIcon(pix)
    return _icon


def beta_html(text):
    """Badge-Text in derselben Farbe wie das Icon (fuer QLabel)."""
    return f'<span style="color:{COLOR};">{text}</span>'
