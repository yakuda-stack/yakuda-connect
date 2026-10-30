#!/usr/bin/env python3
"""
ui/tour.py — Gefuehrte Tour durch die App
=========================================
Zeigt Schritt fuer Schritt, was wo ist: wechselt den Tab, scrollt den
Bereich ins Bild, rahmt ihn golden ein und setzt ein goldenes, pulsierendes
ⓘ daneben. Eine Karte erklaert den Bereich (Zurueck / Weiter / Beenden).

Alles liegt IM Hauptfenster (keine eigenen Fenster) — so klappt es auch in
WayVR, wo zusaetzliche Fenster oft woanders landen. Die App bleibt dabei
bedienbar. Esc beendet die Tour.

Die Schritte stehen in core/tour_steps.py.
"""
import math
import os

from PySide6.QtCore import (QEvent, QObject, QPoint, QPointF, QRect, QSize, Qt, QTimer,
                            QVariantAnimation, Signal)
from PySide6.QtGui import (QColor, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap,
                           QPolygonF, QShortcut)
from PySide6.QtWidgets import (QAbstractScrollArea, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from translations import tr

GOLD = QColor("#ebcb8b")
ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def step_image(step):
    """Pfad des Bildes fuer einen Schritt oder ''. assets/tour/<id>.* gewinnt."""
    for ext in ("png", "jpg", "jpeg"):
        p = os.path.join(ASSETS, "tour", f"{step['id']}.{ext}")
        if os.path.isfile(p):
            return p
    img = step.get("image")
    if img and os.path.isfile(os.path.join(ASSETS, img)):
        return os.path.join(ASSETS, img)
    return ""


def flag_icon(code, w=36, h=24):
    """Flagge als Icon — selbst gezeichnet, weil Flaggen-Emojis unter Linux
    oft fehlen (nur zwei Buchstaben)."""
    pix = QPixmap(w, h)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    if code == "de":
        for i, c in enumerate(("#000000", "#dd0000", "#ffce00")):
            p.fillRect(0, i * h // 3, w, h // 3 + 1, QColor(c))
    elif code == "fr":
        for i, c in enumerate(("#0055a4", "#ffffff", "#ef4135")):
            p.fillRect(i * w // 3, 0, w // 3 + 1, h, QColor(c))
    else:                                   # en: Union Jack, vereinfacht
        p.fillRect(0, 0, w, h, QColor("#012169"))
        p.setPen(QPen(QColor("#ffffff"), h / 5))
        p.drawLine(0, 0, w, h)
        p.drawLine(0, h, w, 0)
        p.setPen(QPen(QColor("#c8102e"), h / 12))
        p.drawLine(0, 0, w, h)
        p.drawLine(0, h, w, 0)
        p.fillRect(int(w / 2 - h / 5), 0, int(2 * h / 5), h, QColor("#ffffff"))
        p.fillRect(0, int(h / 2 - h / 5), w, int(2 * h / 5), QColor("#ffffff"))
        p.fillRect(int(w / 2 - h / 9), 0, int(2 * h / 9) + 1, h, QColor("#c8102e"))
        p.fillRect(0, int(h / 2 - h / 9), w, int(2 * h / 9) + 1, QColor("#c8102e"))
    p.setPen(QPen(QColor("#4c566a"), 1))
    p.setBrush(Qt.NoBrush)
    p.drawRect(0, 0, w - 1, h - 1)
    p.end()
    return QIcon(pix)


LANGS = (("de", "Deutsch"), ("en", "English"), ("fr", "Français"))


class PulseMarker(QWidget):
    """Goldenes ⓘ mit pulsierendem Ring. Klicks gehen durch."""
    SIZE = 56

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedSize(self.SIZE, self.SIZE)
        self._phase = 0.0
        self.anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=1400)
        self.anim.setLoopCount(-1)
        self.anim.valueChanged.connect(self._tick)
        self.anim.start()

    def _tick(self, v):
        self._phase = float(v)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = self.rect().center()
        base = 13
        ring = base + 13 * self._phase
        glow = QColor(GOLD)
        glow.setAlphaF(max(0.0, 0.75 * (1.0 - self._phase)))
        p.setPen(QPen(glow, 3))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, ring, ring)
        breathe = 1.0 + 0.08 * math.sin(self._phase * 2 * math.pi)
        p.setPen(QPen(QColor("#2e3440"), 2))
        p.setBrush(GOLD)
        r = base * breathe
        p.drawEllipse(c, r, r)
        f = QFont(self.font())
        f.setBold(True)
        f.setPixelSize(17)
        p.setFont(f)
        p.setPen(QColor("#2e3440"))
        p.drawText(QRect(int(c.x() - r), int(c.y() - r), int(2 * r), int(2 * r)),
                   Qt.AlignCenter, "i")


class HighlightFrame(QFrame):
    """Goldener Rahmen um den erklaerten Bereich. Klicks gehen durch."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setObjectName("tourHighlight")
        self.setStyleSheet("QFrame#tourHighlight { border:2px solid #ebcb8b; border-radius:8px;"
                           " background:rgba(235,203,139,18); }")


_CARD_CSS = """
QFrame#tourCard { background:#242933; border:2px solid #ebcb8b; border-radius:10px; }
QLabel#tourStep { color:#ebcb8b; font-size:11px; font-weight:bold; }
QLabel#tourTitle { color:#eceff4; font-size:15px; font-weight:bold; }
QLabel#tourText { color:#d8dee9; font-size:12px; }
QPushButton { background:#3b4252; color:#eceff4; border:1px solid #4c566a; border-radius:5px;
              padding:6px 14px; font-size:12px; }
QPushButton:hover { background:#434c5e; }
QPushButton#tourNext { background:#ebcb8b; color:#2e3440; border:none; font-weight:bold; }
QPushButton#tourNext:hover { background:#f0d9a8; }
QPushButton#tourAction { background:#a3be8c; color:#2e3440; border:none; font-weight:bold; }
QPushButton#tourAction:hover { background:#b9d0a4; }
QPushButton#tourSkip { background:transparent; border:none; color:#7b88a1; }
QPushButton#tourSkip:hover { color:#bf616a; }
QPushButton#tourLang { padding:8px 10px; font-weight:bold; }
QPushButton#tourLang:checked { border:2px solid #ebcb8b; background:#3b4252; }
QLabel#tourImage { border:1px solid #3b4252; border-radius:6px; }
"""


class TourCard(QFrame):
    WIDTH = 380
    WIDE = 560                     # breiter, wenn ein Bild gezeigt wird
    lang_picked = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("tourCard")
        self.setStyleSheet(_CARD_CSS)
        self.setFixedWidth(self.WIDTH)
        self._image_path = ""
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(8)
        self.lbl_step = QLabel()
        self.lbl_step.setObjectName("tourStep")
        v.addWidget(self.lbl_step)
        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("tourTitle")
        self.lbl_title.setWordWrap(True)
        v.addWidget(self.lbl_title)
        self.lbl_image = QLabel()
        self.lbl_image.setObjectName("tourImage")
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setCursor(Qt.PointingHandCursor)
        self.lbl_image.mousePressEvent = lambda _e: self._enlarge()
        v.addWidget(self.lbl_image)
        # Sprachwahl (nur im ersten Schritt): Flaggen-Knoepfe
        self.lang_row = QWidget()
        lr = QHBoxLayout(self.lang_row)
        lr.setContentsMargins(0, 0, 0, 0)
        lr.setSpacing(8)
        self.lang_buttons = {}
        for code, name in LANGS:
            b = QPushButton(name)
            b.setObjectName("tourLang")
            b.setCheckable(True)
            b.setIcon(flag_icon(code))
            b.setIconSize(QSize(30, 20))
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, c=code: self.lang_picked.emit(c))
            lr.addWidget(b, 1)
            self.lang_buttons[code] = b
        v.addWidget(self.lang_row)
        self.lbl_text = QLabel()
        self.lbl_text.setObjectName("tourText")
        self.lbl_text.setWordWrap(True)
        self.lbl_text.setTextFormat(Qt.RichText)
        v.addWidget(self.lbl_text)
        self.btn_action = QPushButton()
        self.btn_action.setObjectName("tourAction")
        self.btn_action.setCursor(Qt.PointingHandCursor)
        v.addWidget(self.btn_action)
        row = QHBoxLayout()
        self.btn_skip = QPushButton(tr("tour_skip"))
        self.btn_skip.setObjectName("tourSkip")
        self.btn_skip.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.btn_skip)
        row.addStretch()
        self.btn_back = QPushButton("←  " + tr("tour_back"))
        self.btn_back.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.btn_back)
        self.btn_next = QPushButton()
        self.btn_next.setObjectName("tourNext")
        self.btn_next.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.btn_next)
        v.addLayout(row)

    def _enlarge(self):
        """Bild in gross: eigenes Fenster mit dem Bild in voller Breite."""
        if not self._image_path:
            return
        from PySide6.QtWidgets import QDialog
        dlg = QDialog(self.window())
        dlg.setWindowTitle(self.lbl_title.text())
        lay = QVBoxLayout(dlg)
        lbl = QLabel()
        pix = QPixmap(self._image_path)
        lbl.setPixmap(pix.scaledToWidth(min(pix.width(), 1100), Qt.SmoothTransformation))
        lay.addWidget(lbl)
        dlg.exec()

    def show_step(self, index, total, step):
        from translations import get_language
        sid = step["id"]
        self.btn_skip.setText(tr("tour_skip"))
        self.btn_back.setText("←  " + tr("tour_back"))
        self.lang_row.setVisible(step.get("action") == "language")
        for code, b in self.lang_buttons.items():
            b.setChecked(code == get_language())
        self.lbl_step.setText(tr("tour_step_of").format(n=index + 1, total=total))
        self.lbl_title.setText(tr(f"tour_{sid}_title"))
        self.lbl_text.setText(tr(f"tour_{sid}_text").replace("\n", "<br>"))
        path = step_image(step)
        pix = QPixmap(path) if path else QPixmap()
        self._image_path = path if not pix.isNull() else ""
        wide = not pix.isNull() and pix.width() > 1.6 * pix.height()
        self.setFixedWidth(self.WIDE if wide else self.WIDTH)
        if not pix.isNull():
            self.lbl_image.setPixmap(pix.scaled(self.width() - 34, 200 if wide else 120,
                                                Qt.KeepAspectRatio,
                                                Qt.SmoothTransformation))
            self.lbl_image.setToolTip(tr("tour_image_zoom"))
        self.lbl_image.setVisible(not pix.isNull())
        action = step.get("action")
        if action == "language":
            action = None                    # Flaggen statt Aktionsknopf
        self.btn_action.setVisible(bool(action))
        if action:
            self.btn_action.setText(tr(f"tour_action_{action}"))
        self.btn_back.setVisible(index > 0)
        last = index == total - 1
        self.btn_next.setText(tr("tour_finish") if last else tr("tour_next") + "  →")
        self.btn_skip.setVisible(not last)
        self.adjustSize()


class AppTour(QObject):
    """Steuert die Tour im Fenster ``win`` (VRApp)."""
    finished = Signal()
    completed = Signal()          # mit „Fertig“ beendet (nicht abgebrochen)
    action_requested = Signal(str)

    def __init__(self, win, steps):
        super().__init__(win)
        self.win = win
        self.steps = steps
        self.index = 0
        self._target = None
        self.frame = HighlightFrame(win)
        self.marker = PulseMarker(win)
        self.card = TourCard(win)
        self.card.btn_next.clicked.connect(self.next)
        self.card.btn_back.clicked.connect(self.back)
        self.card.btn_skip.clicked.connect(self.stop)
        self.card.btn_action.clicked.connect(
            lambda: self.action_requested.emit(self.steps[self.index].get("action") or ""))
        self.card.lang_picked.connect(lambda c: self.action_requested.emit("lang:" + c))
        self._esc = QShortcut(QKeySequence(Qt.Key_Escape), win)
        self._esc.activated.connect(self.stop)
        # Fenstergroesse / Scrollen aendern die Lage — regelmaessig nachziehen
        self._follow = QTimer(self)
        self._follow.setInterval(250)
        self._follow.timeout.connect(self._place)
        win.installEventFilter(self)

    # ------------------------------------------------------------------ #
    def start(self, index=0):
        self.index = max(0, min(index, len(self.steps) - 1))
        self._show()
        self._follow.start()

    def next(self):
        if self.index >= len(self.steps) - 1:
            self.completed.emit()
            self.stop()
            return
        self.index += 1
        self._show()

    def back(self):
        if self.index > 0:
            self.index -= 1
            self._show()

    def refresh(self):
        """Nach einem Sprachwechsel: aktuellen Schritt neu beschriften."""
        self._show()

    def stop(self):
        self._follow.stop()
        self.win.removeEventFilter(self)
        self._esc.setEnabled(False)
        for w in (self.frame, self.marker, self.card):
            w.hide()
            w.deleteLater()
        self.finished.emit()
        self.deleteLater()

    def eventFilter(self, obj, event):
        if obj is self.win and event.type() == QEvent.Resize:
            QTimer.singleShot(0, self._place)
        return False

    # ------------------------------------------------------------------ #
    def _show(self):
        step = self.steps[self.index]
        tab = step.get("tab")
        if tab is not None and hasattr(self.win.ui, "sidebar"):
            self.win.ui.sidebar.setCurrentRow(tab)
        sub = step.get("subtab")
        if sub:
            try:
                tabs, page = sub(self.win)
                if tabs is not None and page is not None:
                    tabs.setCurrentWidget(page)
            except Exception:                                  # noqa: BLE001
                pass
        self.card.show_step(self.index, len(self.steps), step)
        self.card.show()
        self.card.raise_()
        # Erst nach dem Tab-Wechsel steht das Layout
        QTimer.singleShot(120, self._focus_target)

    def _resolve(self):
        fn = self.steps[self.index].get("target")
        if fn is None:
            return None
        try:
            w = fn(self.win)
        except Exception:                                      # noqa: BLE001
            return None
        if isinstance(w, (list, tuple)):
            ws = [x for x in w if isinstance(x, QWidget)]
            return ws or None
        return [w] if isinstance(w, QWidget) else None

    def _focus_target(self):
        self._target = self._resolve()
        t = self._target[0] if self._target else None
        if t is not None:
            p = t.parentWidget()
            while p is not None:
                if isinstance(p, QScrollArea):
                    p.ensureWidgetVisible(t, 40, 80)
                    break
                p = p.parentWidget()
        self._place()

    def _target_rect(self):
        rects = [r for r in (self._widget_rect(t) for t in (self._target or [])) if r]
        if not rects:
            return None
        out = rects[0]
        for r in rects[1:]:
            out = out.united(r)
        return out

    def _widget_rect(self, t):
        if t is None or not t.isVisible():
            return None
        top_left = t.mapTo(self.win, QPoint(0, 0))
        rect = QRect(top_left, t.size())
        # Bei Scrollbereichen nur den sichtbaren Teil rahmen
        p = t.parentWidget()
        while p is not None and p is not self.win:
            if isinstance(p, QAbstractScrollArea):
                vp = p.viewport()
                vis = QRect(vp.mapTo(self.win, QPoint(0, 0)), vp.size())
                rect = rect.intersected(vis)
                break
            p = p.parentWidget()
        return rect if rect.isValid() and not rect.isEmpty() else None

    def _place(self):
        if not self.card.isVisible():
            return
        W, H = self.win.width(), self.win.height()
        self.card.adjustSize()
        cw, ch = self.card.width(), self.card.height()
        rect = self._target_rect()
        if rect is None:
            self.frame.hide()
            self.marker.hide()
            self.card.move(max(8, (W - cw) // 2), max(8, (H - ch) // 2))
            self.card.raise_()
            return
        m = 4
        self.frame.setGeometry(rect.adjusted(-m, -m, m, m))
        self.frame.show()
        s = PulseMarker.SIZE
        mx = min(max(0, rect.right() - s // 2), W - s)
        my = min(max(0, rect.top() - s // 2), H - s)
        self.marker.move(mx, my)
        self.marker.show()
        gap = 18
        small = rect.height() < 80
        if small and rect.bottom() + gap + ch <= H - 8:
            x, y = rect.left(), rect.bottom() + gap      # kleines Ziel: darunter
        elif rect.right() + gap + cw <= W - 8:
            x, y = rect.right() + gap, rect.top()
        elif rect.left() - gap - cw >= 8:
            x, y = rect.left() - gap - cw, rect.top()
        elif rect.bottom() + gap + ch <= H - 8:
            x, y = rect.left(), rect.bottom() + gap
        elif rect.top() - gap - ch >= 8:
            x, y = rect.left(), rect.top() - gap - ch
        else:
            x, y = W - cw - 16, H - ch - 16
        x = min(max(8, x), W - cw - 8)
        y = min(max(8, y), H - ch - 8)
        self.card.move(x, y)
        self.frame.raise_()
        self.marker.raise_()
        self.card.raise_()
