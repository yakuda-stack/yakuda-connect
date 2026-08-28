#!/usr/bin/env python3
"""
ui/background.py — Hintergrundbild hinter der Oberflaeche
========================================================
Warum eine eigene Ebene und kein Stylesheet?

Bis v1.2.4 wurde das Bild als ``border-image`` an das Wurzel-Widget gehaengt.
Sichtbar wurde davon nichts, aus zwei Gruenden:

1. QWidget zeichnet Stylesheet-Hintergruende nur eingeschraenkt. Fuer ein
   schlichtes QWidget (und genau das ist das Wurzel-Widget) unterstuetzt Qt
   ``background``, aber nicht zuverlaessig ``border-image`` — ohne
   ``WA_StyledBackground`` bleibt die Flaeche leer.
2. Selbst wenn es gezeichnet wuerde, laege es unter zwei deckenden Flaechen:
   die Seitenleiste und der Seitenstapel haben eigene Hintergrundfarben und
   verdecken das Wurzel-Widget vollstaendig. Zu sehen waere das Bild nur an
   den Raendern — und die gibt es nicht, das Layout hat keine Raender.

Deshalb hier eine echte Ebene: ein QLabel als erstes Kind des Wurzel-Widgets,
per ``lower()`` ganz nach hinten gestellt. Es haelt sich ueber einen
Ereignisfilter selbst auf Fenstergroesse und zeigt das Bild formatfuellend
(mittiger Ausschnitt, kein Verzerren). Mausklicks gehen hindurch.

Damit das Bild auch WIRKLICH zu sehen ist, muss die Flaeche darueber
durchsichtig werden — das erledigt core/main.py (apply_theme) fuer den
Seitenstapel. Die Karten bleiben deckend, bis der Nutzer die Deckkraft
herunterzieht; so bleibt der Text in jedem Fall lesbar.
"""
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel

from logging_setup import get_logger

log = get_logger("background")


class BackgroundLayer(QLabel):
    """Bildebene ganz hinten im Fenster. Ohne Bild unsichtbar und kostenlos."""

    def __init__(self, root):
        super().__init__(root)
        self.setObjectName("yk_background")
        # Nicht umfaerben: hier steht ein Bild, keine Farbe.
        self.setProperty("yk_no_tint", True)
        # Klicks sollen an die Bedienelemente durchgehen, nicht am Bild haengen.
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setScaledContents(False)
        self.setAlignment(Qt.AlignCenter)
        self._source = QPixmap()
        self._path = ""
        root.installEventFilter(self)
        self.hide()

    # ------------------------------------------------------------------ #
    def path(self):
        """Pfad des aktuell angezeigten Bildes ("" = keins)."""
        return self._path

    def set_image(self, path):
        """
        Bild setzen, wechseln oder (mit "") entfernen.

        Rueckgabe: True, wenn danach ein Bild sichtbar ist. Der Aufrufer
        braucht das, um die Flaeche darueber durchsichtig zu schalten.
        """
        path = path or ""
        if path and path == self._path and not self._source.isNull():
            self._fit()                    # gleiches Bild, evtl. neue Groesse
            return True

        self._path = ""
        self._source = QPixmap()
        if path:
            pixmap = QPixmap(path)
            if pixmap.isNull():
                # Kaputte oder unlesbare Datei: kein Grund fuer einen Dialog,
                # aber es gehoert ins Log — sonst sucht der Nutzer den Fehler
                # in der App statt in seiner Datei.
                log.warning("Hintergrundbild nicht lesbar: %s", path)
            else:
                self._source = pixmap
                self._path = path

        if self._source.isNull():
            self.clear()
            self.hide()
            return False

        self._fit()
        self.show()
        # Nach hinten: alles, was danach angelegt wurde, liegt sonst darunter.
        self.lower()
        return True

    # ------------------------------------------------------------------ #
    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() in (
                QEvent.Resize, QEvent.Show):
            self._fit()
        return False

    def _fit(self):
        """Auf Fenstergroesse bringen und den mittigen Ausschnitt zeigen."""
        parent = self.parentWidget()
        if parent is None or self._source.isNull():
            return
        size = parent.size()
        if size.width() <= 0 or size.height() <= 0:
            return
        self.setGeometry(0, 0, size.width(), size.height())
        # KeepAspectRatioByExpanding + Ausschnitt statt schlichtem Strecken:
        # ein 16:9-Wallpaper wuerde im schmalen Fenster sonst zur Karikatur.
        scaled = self._source.scaled(size, Qt.KeepAspectRatioByExpanding,
                                     Qt.SmoothTransformation)
        x = max(0, (scaled.width() - size.width()) // 2)
        y = max(0, (scaled.height() - size.height()) // 2)
        self.setPixmap(scaled.copy(x, y, size.width(), size.height()))
