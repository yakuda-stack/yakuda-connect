#!/usr/bin/env python3
"""
ui/info_popover.py — Info-Fenster mit anklickbaren Links
========================================================
Gemeldet auf GitHub (sebastin25): Die Tooltips der (ⓘ)-Symbole enthalten
teilweise Links — etwa die Quelle des WayVR-Designs. Der Tooltip schliesst
sich aber, sobald die Maus ihn verlaesst, und genau das passiert auf dem Weg
zum Link. Der Link ist also sichtbar, aber nicht erreichbar.

Ursache: ``QToolTip.showText`` erzeugt ein Fenster, das Mausereignisse gar
nicht erst annimmt — es ist als reine Anzeige gedacht. Mit Qt-Bordmitteln
laesst sich daran nichts drehen.

Loesung: Beim KLICK auf das (ⓘ) erscheint stattdessen dieses kleine Fenster.
Es bleibt stehen, bis man daneben klickt oder Esc drueckt, und seine Links
sind normale, anklickbare Links. Beim blossen Ueberfahren mit der Maus bleibt
es beim gewohnten Tooltip — daran aendert sich nichts.

Benutzung:

    from ui.info_popover import show_info_popover
    show_info_popover(button, "<b>Titel</b><br>Text mit <a href='...'>Link</a>")
"""
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class InfoPopover(QFrame):
    """Kleines, rahmenloses Fenster mit Rich-Text und klickbaren Links."""

    # Nur EIN Popover gleichzeitig. Ohne das bliebe bei schnellen Klicks auf
    # mehrere (ⓘ) ein Stapel offener Fenster stehen.
    _current = None

    def __init__(self, html, parent=None):
        # Popup: Qt schliesst das Fenster automatisch, sobald daneben oder in
        # ein anderes Fenster geklickt wird — genau das gewuenschte Verhalten.
        super().__init__(parent, Qt.Popup)
        self.setObjectName("infoPopover")
        self.setStyleSheet(
            "#infoPopover { background-color:#2e3440; border:1px solid #4c566a;"
            " border-radius:6px; }"
            " QLabel { color:#eceff4; font-size:12px; background:transparent; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        self.label = QLabel(html)
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.RichText)
        # Links anklickbar machen UND den Text markierbar lassen (praktisch,
        # um einen Pfad aus der Erklaerung herauszukopieren).
        self.label.setTextInteractionFlags(
            Qt.TextBrowserInteraction | Qt.TextSelectableByMouse)
        self.label.setOpenExternalLinks(False)   # wir oeffnen selbst, s. u.
        self.label.linkActivated.connect(self._open_link)
        self.label.setMaximumWidth(460)
        layout.addWidget(self.label)

    def _open_link(self, url):
        """Link im Standardbrowser oeffnen und das Popover schliessen."""
        QDesktopServices.openUrl(url)
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if InfoPopover._current is self:
            InfoPopover._current = None
        super().closeEvent(event)


def show_info_popover(anchor, html):
    """
    Zeigt ``html`` als Popover unterhalb von ``anchor`` (meist das ⓘ-Symbol).

    Ragt das Fenster rechts oder unten aus dem Bildschirm, wird es
    hineingeschoben — sonst waere der Text auf einem kleinen Bildschirm oder
    bei einer Karte am rechten Rand abgeschnitten.
    """
    if InfoPopover._current is not None:
        try:
            InfoPopover._current.close()
        except RuntimeError:
            # Qt hat das Fenster schon abgeraeumt — nichts weiter zu tun.
            InfoPopover._current = None

    pop = InfoPopover(html, anchor.window())
    InfoPopover._current = pop
    pop.adjustSize()

    pos = anchor.mapToGlobal(QPoint(0, anchor.height() + 4))
    screen = anchor.screen()
    if screen is not None:
        area = screen.availableGeometry()
        x = min(pos.x(), area.right() - pop.width() - 8)
        x = max(x, area.left() + 8)
        y = pos.y()
        if y + pop.height() > area.bottom():
            # Kein Platz nach unten -> ueber dem Symbol anzeigen.
            y = max(area.top() + 8,
                    anchor.mapToGlobal(QPoint(0, 0)).y() - pop.height() - 4)
        pos = QPoint(x, y)

    pop.move(pos)
    pop.show()
    return pop
