#!/usr/bin/env python3
"""
ui/controller_view.py — Controller mit beschrifteten Tasten (SteamVR-Stil)
==========================================================================
Eine Seite (links/rechts) eines Controllers: in der Mitte eine Zeichnung,
aussen je Eingabe eine Karte mit den Bindings, und eine Linie von der Karte
zu der Stelle auf der Zeichnung, an der die Eingabe sitzt.

Die Stellen kommen aus obahs Controller-Profilen (binding_image_point, siehe
core/obah_editor.py). Die Zeichnungen sind eigene, schematische Grafiken —
keine Kopie der SteamVR- oder Hersteller-Icons. Gezeichnet ist immer die
LINKE Hand; die rechte ist die gespiegelte linke, wie in SteamVR.

Bedienung:
  * Klick auf eine Karte (oder ihren Punkt) -> card_clicked(pfad)
  * Karte ziehen  -> sie rastet an der Stelle ein, an der man sie loslaesst;
                     die Karten darunter ruecken nach. Es ueberlappt nie
                     etwas, und man kann alles wieder zurueckschieben.
  * Karte weit nach aussen ziehen -> sie kommt in eine zweite, aeussere
                     Spalte (zum Sortieren); zurueckziehen holt sie wieder rein.
  * Zeichnung ziehen -> NUR der Controller wandert (mit seinen Punkten und
                     Linien); die Karten bleiben, wo sie sind.
  Nach dem Loslassen kommt layout_changed(dict) — der Controls-Tab merkt
  sich Reihenfolge und Controller-Position je Controller und Seite.

Karten wachsen und schrumpfen mit ihrem Inhalt (mehr Bindings = hoeher).

Texturen
--------
Statt der eingebauten Zeichnung kann ein Bild benutzt werden. Gesucht wird
nach ``<controller_type>.png`` (bzw. ``_left`` / ``_right`` fuer eine Seite)
in diesen Ordnern, in dieser Reihenfolge:

    1. ``<Config-Ordner>/controls``   — eigene Bilder des Nutzers
    2. ``assets/controls``            — die mitgelieferten Bilder

Fehlt die Datei, wird wie bisher gezeichnet. Gibt es nur ein Bild ohne
Seite, wird es fuer rechts gespiegelt — wie die Zeichnung.

Wo die Punkte auf dem Bild sitzen, steht in ``points.json`` im selben
Ordner wie das Bild — je Bild (Dateiname ohne Endung) die Pixel jeder
Eingabe::

    "knuckles_left": {"size": [1108, 1419],
                      "points": {"/input/trigger": [935, 540], ...}}

Mit Eintrag bekommt das Bild sein eigenes Seitenverhaeltnis, und die Punkte
sitzen genau auf den Tasten. Das Bild wird nicht zugeschnitten: links und
rechts sollten dieselbe Groesse haben, dann sind beide gleich gross.
Ohne Eintrag gilt das alte Verfahren: das Bild wird in die Zeichenflaeche
aus DRAWINGS eingepasst und die Punkte kommen aus obahs Profil.
"""
import json
import os

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QPainter, QPainterPath,
                           QPainterPathStroker, QPen, QPixmap)
from PySide6.QtWidgets import QSizePolicy, QWidget

# Farben (Nord, wie der Rest der App)
C_CARD = QColor("#21252b")
C_CARD_BORDER = QColor("#3b4252")
C_CARD_HOVER = QColor("#88c0d0")
C_TITLE = QColor("#eceff4")
C_TYPE = QColor("#616e88")
C_MODE = QColor("#88c0d0")
C_INPUT = QColor("#7b88a1")
C_ACTION = QColor("#a3be8c")
C_NONE = QColor("#4c566a")
C_LINE = QColor("#4c566a")
C_LINE_BOUND = QColor("#5e81ac")
C_BODY = QColor("#2e3440")
C_BODY_EDGE = QColor("#4c566a")
C_PART = QColor("#3b4252")
C_PART_EDGE = QColor("#616e88")
C_DROP = QColor("#5e81ac")

CARD_W = 220
CARD_PAD = 8
CARD_GAP = 8
COL_GAP = 16             # Abstand zwischen innerer und aeusserer Kartenspalte
IMG_MARGIN = 40          # Abstand Kartenspalte <-> Zeichnung (Platz fuer Linien)
TEX_MAX_H = 330          # Bild mit eigenen Punkten: hoechstens so hoch ...
TEX_MAX_W = 380          # ... und so breit (Pixel auf dem Schirm)
DRAG_THRESHOLD = 5       # Pixel, ab denen aus einem Klick ein Ziehen wird


# --------------------------------------------------------------------------- #
#  Zeichnungen
# --------------------------------------------------------------------------- #
# Eigene, schematische Grafiken im Koordinatensystem des jeweiligen Profils
# (binding_image_point). Keine Kopie fremder Icons — nur so gezeichnet, dass
# die Bedienelemente dort sitzen, wo das Profil sie erwartet. Gezeichnet ist
# die linke Hand; die rechte wird gespiegelt.
def _circle(x, y, r):
    p = QPainterPath()
    p.addEllipse(QPointF(x, y), r, r)
    return p


def _ellipse(x, y, rx, ry):
    p = QPainterPath()
    p.addEllipse(QPointF(x, y), rx, ry)
    return p


def _rrect(x, y, w, h, r):
    p = QPainterPath()
    p.addRoundedRect(QRectF(x, y, w, h), r, r)
    return p


def _capsule(x1, y1, x2, y2, r):
    """Strecke mit runden Enden — Finger, Griffleisten, Riemen."""
    line = QPainterPath(QPointF(x1, y1))
    line.lineTo(x2, y2)
    stroker = QPainterPathStroker()
    stroker.setWidth(2 * r)
    stroker.setCapStyle(Qt.RoundCap)
    return stroker.createStroke(line).simplified()


def _poly(*pts, close=True):
    """Linien- und Kurvenzug: (x, y) = Linie, (c1x, c1y, c2x, c2y, x, y) = Kurve."""
    p = QPainterPath(QPointF(*pts[0]))
    for pt in pts[1:]:
        if len(pt) == 6:
            p.cubicTo(QPointF(pt[0], pt[1]), QPointF(pt[2], pt[3]), QPointF(pt[4], pt[5]))
        else:
            p.lineTo(QPointF(*pt))
    if close:
        p.closeSubpath()
    return p


def _ring(x, y, rx, ry, thickness):
    return _ellipse(x, y, rx, ry).subtracted(_ellipse(x, y, rx - thickness, ry - thickness))


def _draw_touch(_side):
    """Oculus/Meta Touch: Tracking-Ring, Tastenflaeche, Griff, Trigger."""
    body = [_ring(36, 56, 30, 46, 8),
            _poly((60, 62), (70, 58, 84, 56, 90, 62), (110, 128),
                  (114, 142, 102, 154, 90, 152), (80, 151, 76, 144, 74, 136),
                  (58, 80), (56, 72, 56, 66, 60, 62)),
            _ellipse(63, 45, 26, 24)]
    parts = [_circle(54, 31, 8.5), _circle(54, 31, 5),      # Stick
             _circle(70, 49, 5.2), _circle(54, 55, 5.2),    # X / Y
             _circle(72, 39, 2.6),                          # Menue
             _rrect(62, 62, 16, 6, 3),                      # Daumenablage
             _poly((14, 78), (24, 76, 30, 84, 28, 94), (24, 96, 18, 92, 16, 88),
                   (13, 84, 12, 80, 14, 78)),               # Trigger
             _rrect(95, 72, 7, 28, 3.5)]                    # Griff
    return body, parts


def _draw_knuckles(_side):
    """Valve Index: Kopf mit Stick/Trackpad/A/B, langer Griff, Riemen, Finger."""
    head = _poly((8, 24), (12, 12, 34, 10, 42, 18), (48, 26, 48, 44, 42, 52),
                 (36, 58, 18, 58, 12, 52), (6, 44, 4, 32, 8, 24))
    handle = _poly((30, 52), (40, 48, 50, 54, 54, 64), (58, 88),
                   (60, 100, 54, 106, 46, 104), (38, 102, 34, 96, 32, 88),
                   (26, 66), (24, 58, 26, 54, 30, 52))
    strap = _capsule(48, 30, 58, 92, 3.0)
    body = [strap, handle, head]
    parts = [_circle(31, 26, 5.4), _circle(31, 26, 3),      # Thumbstick
             _circle(27, 37, 6.4), _circle(27, 37, 2.2),    # Trackpad / Pinch
             _circle(26, 42, 2.6), _circle(18, 37, 2.6),    # A / B
             _circle(34, 45, 1.8),                          # System
             _poly((6, 54), (13, 53, 17, 60, 15, 67),
                   (11, 69, 7, 66, 6, 62), (4, 58, 4, 56, 6, 54)),   # Trigger
             _rrect(43.5, 74, 7, 24, 3.5),                  # Griff
             _capsule(53, 82, 59, 90, 2.0)]                 # Finger
    return body, parts


def _draw_vive_wand(_side):
    """HTC Vive Wand: Ring oben, runder Trackpad, Trigger vorn, Griffe seitlich."""
    ring = _poly((42, 26), (42, 6, 90, 6, 90, 26), (90, 36, 84, 42, 80, 44),
                 (78, 38), (82, 34, 84, 30, 84, 26), (84, 14, 48, 14, 48, 26),
                 (48, 30, 50, 34, 54, 38), (52, 44), (46, 40, 42, 34, 42, 26))
    body = [ring,
            _poly((50, 36), (58, 30, 74, 30, 82, 36), (86, 48, 86, 70, 80, 80),
                  (78, 128), (78, 136, 58, 136, 58, 128), (52, 80),
                  (46, 70, 46, 48, 50, 36))]
    parts = [_circle(66, 59, 11), _circle(66, 59, 2),       # Trackpad
             _rrect(60, 32.5, 8, 5, 2.5),                   # Menue
             _circle(67, 81, 3),                            # System
             _poly((46, 56), (38, 56, 34, 64, 36, 72),
                   (40, 74, 44, 70, 46, 66)),               # Trigger
             _rrect(49.5, 79, 5, 16, 2.5)]                  # Griff
    return body, parts


def _draw_focus3(side):
    """Vive Focus 3 / Pico: Ring oben, Stick, A/B bzw. X/Y, Griff."""
    head = _ellipse(35, 27, 25, 17)
    ring = _poly((14, 14), (22, 0, 50, 0, 58, 12), (54, 15), (46, 6, 26, 6, 18, 17))
    handle = _poly((16, 36), (26, 38, 32, 42, 30, 50), (25, 66),
                   (22, 74, 10, 72, 10, 64), (11, 46), (11, 40, 12, 36, 16, 36))
    body = [handle, ring, head]
    parts = [_circle(42, 18, 5), _circle(42, 18, 3),        # Joystick
             _circle(55, 33, 2),                            # System
             _poly((30, 3), (36, 1, 44, 2, 46, 6), (42, 9, 34, 9, 30, 7)),   # Trigger
             _rrect(16.5, 47, 7, 12, 3.5)]                  # Griff
    if side == "right":          # vor dem Spiegeln: A/B der rechten Hand
        parts += [_circle(27, 35, 3.6), _circle(20, 23, 3.6)]
    else:                        # X/Y der linken
        parts += [_circle(34, 33, 3.6), _circle(25, 23, 3.6)]
    return body, parts


def _draw_hand(_side):
    """Hand-Tracking: Handflaeche mit fuenf Fingern, Pinch-Punkte an den Spitzen."""
    palm = _poly((22, 34), (34, 30, 56, 28, 62, 34), (64, 48, 62, 62, 56, 70),
                 (46, 76, 32, 76, 26, 70), (20, 60, 18, 46, 22, 34))
    fingers = [_capsule(27, 33, 25, 12, 4.2),    # Zeigefinger (index_point 25,10)
               _capsule(37, 31, 35, 9, 4.4),     # Mittelfinger (35,6)
               _capsule(47, 31, 47, 11, 4.2),    # Ringfinger (47,8)
               _capsule(56, 34, 57, 18, 3.8),    # kleiner Finger (57,15)
               _capsule(24, 52, 16, 28, 4.4)]    # Daumen (index_pinch 15,25)
    body = fingers + [palm]
    parts = [_circle(15, 25, 2.6), _circle(35, 6, 2.6), _circle(47, 8, 2.6),
             _circle(57, 15, 2.6), _circle(25, 10, 2.6),    # Pinch-Punkte
             _ellipse(45, 50, 9, 8),                        # Greifflaeche (grip 45,50)
             _circle(72, 39, 3.2), _circle(72, 39, 1.4)]    # System
    return body, parts


def _draw_gamepad(_side):
    """Gamepad: zwei Griffe, Sticks, Steuerkreuz, ABXY, Schultertasten, Trigger."""
    body = [_poly((40, 34), (70, 28, 156, 28, 186, 34), (206, 42, 214, 92, 212, 118),
                  (210, 138, 186, 142, 176, 128), (160, 104), (68, 104),
                  (52, 128), (42, 142, 16, 138, 14, 118), (12, 92, 20, 42, 40, 34))]
    parts = [_rrect(34, 6, 30, 12, 5), _rrect(161, 6, 30, 12, 5),        # Trigger
             _rrect(32, 23, 36, 9, 4.5), _rrect(159, 23, 36, 9, 4.5),    # Schultertasten
             _circle(52, 84, 11), _circle(52, 84, 6.5),                  # linker Stick
             _circle(145, 114, 11), _circle(145, 114, 6.5),              # rechter Stick
             _rrect(79, 94, 10, 26, 2), _rrect(71, 102, 26, 10, 2),      # Steuerkreuz
             _circle(174, 89, 6.5), _circle(192, 73, 6.5),               # A / B
             _circle(159, 75, 6.5), _circle(175, 60, 6.5),               # X / Y
             _rrect(91, 72, 10, 6, 3), _rrect(127, 72, 10, 6, 3),        # Start / Back
             _circle(113, 52, 7.5)]                                      # Guide
    return body, parts


def _draw_rift(_side):
    """Oculus Rift (HMD-Profil): Brille links, Fernbedienung rechts."""
    visor = _poly((18, 44), (30, 30, 90, 30, 102, 44), (106, 60, 104, 78, 96, 84),
                  (84, 90, 36, 90, 24, 84), (16, 78, 14, 60, 18, 44))
    strap = _capsule(10, 50, 10, 76, 3.5)
    remote = _poly((122, 12), (124, -2, 160, -2, 162, 12), (166, 30, 158, 44, 152, 48),
                   (152, 72), (152, 82, 132, 82, 132, 72), (132, 48),
                   (126, 44, 118, 30, 122, 12))
    body = [strap, visor, remote, _rrect(172, 100, 16, 20, 5)]
    parts = [_ring(142, 25, 19, 19, 7), _circle(142, 25, 6),   # Steuerkreuz + Enter
             _circle(142, 64, 5),                              # Zurueck
             _ellipse(60, 60, 18, 10),                         # Naeherungssensor / Tap
             _circle(180, 110, 3)]                             # System
    return body, parts


# controller_type -> (Zeichenfunktion, Zeichenflaeche in Profil-Koordinaten, Massstab)
DRAWINGS = {
    "oculus_touch": (_draw_touch, QRectF(0, 0, 125, 160), 1.9),
    "knuckles": (_draw_knuckles, QRectF(0, 4, 66, 108), 2.7),
    "vive_controller": (_draw_vive_wand, QRectF(30, 0, 68, 140), 2.2),
    "vive_focus3_controller": (_draw_focus3, QRectF(6, -2, 60, 78), 3.6),
    "svl_hand_interaction_augmented": (_draw_hand, QRectF(8, 0, 70, 82), 3.4),
    "gamepad": (_draw_gamepad, QRectF(8, 2, 210, 142), 1.75),
    "rift": (_draw_rift, QRectF(4, -4, 190, 126), 1.9),
}


# --------------------------------------------------------------------------- #
#  Texturen (austauschbare Bilder statt der Zeichnung)
# --------------------------------------------------------------------------- #
TEXTURE_EXTS = (".png", ".svg", ".webp", ".jpg", ".jpeg")

# Mitgelieferte Bilder: <Projekt>/assets/controls
ASSET_TEXTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "controls")

POINTS_FILE = "points.json"

_TEX_CACHE = {}          # (pfad, gespiegelt) -> (mtime, QPixmap)
_POINTS_CACHE = {}       # pfad der points.json -> (mtime, dict)


def texture_dirs():
    """Ordner, in denen nach Bildern gesucht wird — eigene zuerst."""
    dirs = []
    try:                 # core/paths.py liegt im Suchpfad, wenn die App laeuft
        from paths import config_root
        dirs.append(os.path.join(config_root(), "controls"))
    except Exception:    # Tests / Import ohne core im Pfad: nur die Assets
        pass
    dirs.append(ASSET_TEXTURE_DIR)
    return dirs


def texture_file(controller_type, side):
    """
    Pfad des Bildes fuer diesen Controller — oder None.

    Zuerst das seitenweise Bild (``knuckles_left.png``), dann das allgemeine
    (``knuckles.png``). Zurueck kommt (pfad, gespiegelt): gespiegelt ist nur
    das allgemeine Bild auf der rechten Seite.
    """
    if not controller_type:
        return None
    names = []
    if side in ("left", "right"):
        names.append((f"{controller_type}_{side}", False))
    names.append((controller_type, side == "right"))
    for folder in texture_dirs():
        for name, mirror in names:
            for ext in TEXTURE_EXTS:
                path = os.path.join(folder, name + ext)
                if os.path.isfile(path):
                    return path, mirror
    return None


def _mirror_image(img):
    """Seitenverkehrt. Ab Qt 6.9 heisst das flipped(), mirrored() ist dort
    veraltet — aeltere PySide6-Versionen (>= 6.5) kennen nur mirrored()."""
    if hasattr(img, "flipped"):
        return img.flipped(Qt.Horizontal)
    return img.mirrored(True, False)


def load_texture(path, mirror=False):
    """Bild laden und merken; aendert sich die Datei, wird neu geladen.

    Gemerkt wird je Datei (links und rechts gleichzeitig) — sonst luden die
    beiden Seiten sich bei jedem Neuzeichnen gegenseitig aus dem Cache.
    """
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    key = (path, bool(mirror))
    hit = _TEX_CACHE.get(key)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    pix = QPixmap(path)
    if pix.isNull():
        return None
    if mirror:
        pix = QPixmap.fromImage(_mirror_image(pix.toImage()))
    if len(_TEX_CACHE) > 32:
        _TEX_CACHE.clear()
    _TEX_CACHE[key] = (mtime, pix)
    return pix


def clear_texture_cache():
    """Nach dem Austauschen von Bildern aufrufen (oder beim Sprachwechsel egal)."""
    _TEX_CACHE.clear()
    _POINTS_CACHE.clear()


def _load_points_file(path):
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    hit = _POINTS_CACHE.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    _POINTS_CACHE[path] = (mtime, data)
    return data


def texture_points(path):
    """
    Punkte der Eingaben fuer dieses Bild aus ``points.json`` daneben.

    Rueckgabe: (groesse | None, {eingabe: (x, y)}) in Pixeln des Bildes,
    wie es auf der Platte liegt (ungespiegelt) — oder None ohne Eintrag.
    """
    data = _load_points_file(os.path.join(os.path.dirname(path), POINTS_FILE))
    entry = data.get(os.path.splitext(os.path.basename(path))[0])
    if not isinstance(entry, dict) or not isinstance(entry.get("points"), dict):
        return None
    pts = {}
    for key, val in entry["points"].items():
        try:
            pts[str(key)] = (float(val[0]), float(val[1]))
        except (TypeError, ValueError, IndexError):
            continue
    size = entry.get("size")
    try:
        size = (float(size[0]), float(size[1])) if size else None
    except (TypeError, ValueError, IndexError):
        size = None
    return (size, pts) if pts else None


def texture_layout(controller_type, side):
    """
    Bild mit eigenen Punkten: (pixmap, sichtbarer_teil, {eingabe: (x, y)})
    in Pixeln der (ggf. gespiegelten) Pixmap — oder None.

    None auch dann, wenn das Bild ein anderes Seitenverhaeltnis hat als in
    points.json angegeben: dann passen die Punkte sicher nicht, und das alte
    Verfahren (Profilpunkte) ist die bessere Wahl.
    """
    found = texture_file(controller_type, side)
    if not found:
        return None
    path, mirror = found
    info = texture_points(path)
    if not info:
        return None
    pix = load_texture(path, mirror)
    if pix is None:
        return None
    size, pts = info
    sx = sy = 1.0
    if size and size[0] > 0 and size[1] > 0:
        sx, sy = pix.width() / size[0], pix.height() / size[1]
        if abs(sx - sy) > 0.02 * max(sx, sy):
            return None
    out = {}
    for key, (x, y) in pts.items():
        x, y = x * sx, y * sy
        if mirror:
            x = pix.width() - x
        out[key] = (x, y)
    # Kein automatischer Zuschnitt: die mitgelieferten Bilder sind knapp
    # zugeschnitten und je Paar (links/rechts) gleich gross — so sind beide
    # Controller auf dem Schirm immer exakt gleich gross.
    return pix, QRectF(pix.rect()), out


class ControllerBindingView(QWidget):
    """
    Eine Controllerseite mit Karten und Linien.

    set_data(controller_type, side, views, texts)
      views : [obah_editor.InputView]
      texts : {"modes": {...}, "inputs": {...}, "unbound", "none", "title",
               "hint", "hint_image"}
    """

    card_clicked = Signal(str)        # Profilpfad der Eingabe, z. B. /input/joystick
    layout_changed = Signal(dict)     # {"image": [dx, dy] | None, "order": [...], "compact": [...]}
    tidy_changed = Signal(bool)       # True, wenn ALLE Karten zugeklappt sind
    image_moved = Signal(object, bool)  # [dx, dy], losgelassen? — fuer die Gegenseite

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._controller = ""
        self._side = "left"
        self._views = []
        self._texts = {}
        self._layout = []          # [(QRectF karte, QPointF punkt, InputView, zeilen)]
        self._img_rect = QRectF()
        self._tex = None           # (pixmap, sichtbarer_teil, punkte) aus points.json
        self._tex_k = 0.0          # Massstab Bildpixel -> Schirm
        self._hover = -1
        self._height = 200
        self._centered = False
        self._center_h = None      # gemeinsame Spaltenhoehe beider Seiten (ControllerPair)
        self._column_h = 0.0       # eigene Hoehe der Kartenspalte

        # Eigene Anordnung: Verschiebung der Zeichnung und Reihenfolge der Karten
        self._img_offset = None    # [dx, dy] oder None (automatisch)
        self._order = []           # [profilpfad, ...]
        # Karten in der aeusseren Spalte: {pfad: y ueber der Spaltenoberkante
        # oder None}. Dort stehen Karten frei in der Hoehe (nicht gestapelt).
        self._outer = {}

        # Aufgeraeumter Modus: von diesen Karten steht nur der Name da, nicht
        # mehr, was auf der Taste liegt. Einzeln per Rechtsklick, alle
        # zusammen ueber set_tidy().
        self._compact = set()      # {profilpfad, ...}

        # Ziehen
        self._press = None         # (art, index, startpunkt, start-topleft)
        self._dragging = False
        self._drag_path = None     # Pfad der gezogenen Karte
        self._drag_pos = None      # QPointF: linke obere Ecke der schwebenden Karte
        self._drop_index = -1      # Einfuegestelle in der Spalte
        self._drop_col = 0         # 0 = innere Spalte, 1 = aeussere
        self._col_slots = {0: [0.0], 1: [0.0]}
        self._col_x = {0: 0.0, 1: 0.0}
        self._gap_rect = None      # sichtbare Luecke an der Einfuegestelle
        self._slots = [0.0]        # Oberkanten der moeglichen Einfuegestellen
        self._top = 0.0            # Oberkante der Kartenspalten
        self._card_left = 0.0

        self._f_title = QFont(self.font())
        self._f_title.setPointSizeF(max(self.font().pointSizeF(), 9) + 0.5)
        self._f_title.setBold(True)
        self._f_small = QFont(self.font())
        self._f_small.setPointSizeF(max(self.font().pointSizeF() - 0.5, 8))
        self._f_mode = QFont(self._f_small)
        self._f_mode.setBold(True)
        self._f_head = QFont(self.font())
        self._f_head.setBold(True)

    # ------------------------------------------------------------------ #
    #  Daten
    # ------------------------------------------------------------------ #
    def set_data(self, controller_type, side, views, texts):
        self._controller = controller_type
        self._side = side
        self._views = list(views)
        self._texts = dict(texts or {})
        self._hover = -1
        self._relayout()
        self.updateGeometry()
        self.update()

    def set_layout(self, layout):
        """
        Gemerkte Anordnung setzen ({} = automatisch).

        Aeltere Dateien haben Karten frei positioniert ({"cards": {pfad: [x, y]}}).
        Daraus wird die Reihenfolge von oben nach unten — die Karten stehen
        danach wieder sauber untereinander, in der gewaehlten Folge.
        """
        layout = layout or {}
        self._img_offset = list(layout["image"]) if layout.get("image") else None
        order = list(layout.get("order") or [])
        if not order and layout.get("cards"):
            order = [p for p, _ in sorted(layout["cards"].items(), key=lambda kv: kv[1][1])]
        self._order = order
        self._compact = set(layout.get("compact") or [])
        outer = layout.get("outer") or {}
        if isinstance(outer, list):          # aeltere Form: nur die Pfade
            outer = {p: None for p in outer}
        self._outer = {str(p): (float(y) if isinstance(y, (int, float)) else None)
                       for p, y in outer.items()}
        self._relayout()
        self.update()

    def set_center_height(self, height):
        """Hoehe, zu der der Controller mittig steht (None = eigene Spalte)."""
        if height != self._center_h:
            self._center_h = height
            self._relayout()
            self.update()

    def column_height(self):
        return self._column_h

    def mirror_image_offset(self, offset, notify=False):
        """Versatz der anderen Seite gespiegelt uebernehmen (dx umgedreht)."""
        new = [-offset[0], offset[1]] if offset and any(offset) else None
        if new != self._img_offset:
            self._img_offset = new
            self._relayout()
            self.update()
        if notify:
            self.layout_changed.emit(self.layout_state())

    def layout_state(self):
        return {"image": list(self._img_offset) if self._img_offset else None,
                "order": list(self._order),
                "compact": sorted(self._compact),
                "outer": dict(sorted(self._outer.items()))}

    def has_manual_layout(self):
        return bool(self._img_offset or self._order or self._compact or self._outer)

    # ------------------------------------------------------------------ #
    #  Aufgeraeumter Modus
    # ------------------------------------------------------------------ #
    def is_compact(self, path):
        """Steht von dieser Karte nur der Name da?"""
        return path in self._compact

    def is_tidy(self):
        """Alle Karten zugeklappt? (Ohne Karten: nein — sonst meldet eine
        leere Ansicht 'aufgeraeumt' und schaltet den Knopf um.)"""
        paths = [v.input.path for v in self._views]
        return bool(paths) and all(p in self._compact for p in paths)

    def set_tidy(self, tidy, notify=True):
        """Alle Karten auf einmal zu- oder aufklappen."""
        wanted = {v.input.path for v in self._views} if tidy else set()
        if wanted == self._compact:
            return
        self._compact = wanted
        self._after_compact_change(notify)

    def toggle_compact(self, path, notify=True):
        """Eine einzelne Karte umschalten (Rechtsklick)."""
        if path in self._compact:
            self._compact.discard(path)
        else:
            self._compact.add(path)
        self._after_compact_change(notify)

    def _after_compact_change(self, notify):
        self._relayout()
        self.updateGeometry()
        self.update()
        if notify:
            # Erst der Zustand, dann das Speichern: der Controls-Tab stellt
            # den Knopf nach, bevor die Anordnung auf die Platte geht.
            self.tidy_changed.emit(self.is_tidy())
            self.layout_changed.emit(self.layout_state())

    def set_centered(self, centered):
        """Untereinander (schmales Fenster): Inhalt mittig statt zur Mitte hin."""
        if centered != self._centered:
            self._centered = centered
            self._relayout()
            self.update()

    def card_count(self):
        return len(self._layout)

    def card_lines(self, index):
        """Fuer Tests: die Textzeilen einer Karte als [(art, text, text2)]."""
        return list(self._layout[index][3])

    def point_of(self, index):
        return QPointF(self._layout[index][1])

    def card_rect(self, index):
        return QRectF(self._layout[index][0])

    def card_order(self):
        """Pfade der Karten in der Reihenfolge, in der sie stehen."""
        return [v.input.path for _r, _p, v, _l in self._layout]

    def is_outer(self, path):
        """Steht die Karte in der aeusseren Spalte?"""
        return path in self._outer

    # ------------------------------------------------------------------ #
    #  Layout
    # ------------------------------------------------------------------ #
    def _lines_for(self, view):
        """Zeilen einer Karte: ('mode', ...) / ('row', eingabe, aktion) / ('unbound', ...)."""
        modes = self._texts.get("modes", {})
        inputs = self._texts.get("inputs", {})
        lines = []
        for b in view.bindings:
            lines.append(("mode", modes.get(b.mode, b.mode or "?"), ""))
            for row in b.inputs:
                lines.append(("row", inputs.get(row.input, row.input),
                              row.label or self._texts.get("none", "—")))
            if b.parameters:
                params = ", ".join(f"{k}={v}" for k, v in b.parameters.items())
                lines.append(("param", params, ""))
        if not view.bindings:
            lines.append(("unbound", self._texts.get("unbound", "—"), ""))
        return lines

    def _scale_and_box(self):
        """Massstab und Zeichenflaeche (in Profil-Koordinaten)."""
        art = DRAWINGS.get(self._controller)
        if art:
            return art[2], QRectF(art[1])
        pts = [v.input.point for v in self._views] or [(0, 0)]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        box = QRectF(min(xs) - 14, min(ys) - 14,
                     max(max(xs) - min(xs), 40) + 28, max(max(ys) - min(ys), 60) + 28)
        scale = min(260 / box.width(), 330 / box.height(), 3.0)
        return scale, box

    def _map_point(self, p, scale, box):
        x = (p[0] - box.left()) * scale
        y = (p[1] - box.top()) * scale
        if self._side == "right":
            x = box.width() * scale - x
        return QPointF(self._img_rect.left() + x, self._img_rect.top() + y)

    def _image_size(self):
        """
        Groesse der Zeichenflaeche auf dem Schirm und das Bild mit Punkten
        (oder None). Ein Bild mit Eintrag in points.json bringt sein eigenes
        Seitenverhaeltnis mit; sonst gilt die Flaeche aus DRAWINGS.
        """
        tex = texture_layout(self._controller, self._side)
        if tex is not None:
            crop = tex[1]
            if crop.width() > 0 and crop.height() > 0:
                k = min(TEX_MAX_H / crop.height(), TEX_MAX_W / crop.width())
                return crop.width() * k, crop.height() * k, tex, k
        scale, box = self._scale_and_box()
        return box.width() * scale, box.height() * scale, None, 0.0

    def _point_for(self, view, scale, box):
        """Bildschirmpunkt einer Eingabe: aus points.json, sonst aus dem Profil."""
        tex = self._tex
        if tex is not None:
            _pix, crop, pts = tex
            pt = pts.get(view.input.path)
            if pt is not None:
                return QPointF(self._img_rect.left() + (pt[0] - crop.left()) * self._tex_k,
                               self._img_rect.top() + (pt[1] - crop.top()) * self._tex_k)
            # Eingabe fehlt in points.json: Profilpunkt anteilig aufs Bild
            fx = (view.input.point[0] - box.left()) / max(box.width(), 1)
            fy = (view.input.point[1] - box.top()) / max(box.height(), 1)
            if self._side == "right":
                fx = 1 - fx
            return QPointF(self._img_rect.left() + fx * self._img_rect.width(),
                           self._img_rect.top() + fy * self._img_rect.height())
        return self._map_point(view.input.point, scale, box)

    def _card_height(self, lines):
        return (CARD_PAD * 2 + QFontMetrics(self._f_title).height()
                + len(lines) * (QFontMetrics(self._f_small).height() + 2))

    def _ordered_views(self):
        """
        Karten in ihrer Reihenfolge: erst die gemerkte, dann alles Uebrige in
        der Profilreihenfolge (von oben nach unten am Controller).

        Wichtig: die Reihenfolge haengt NICHT davon ab, wohin die Zeichnung
        geschoben wurde — sonst wuerde ein Verschieben des Controllers die
        Karten durcheinanderbringen.
        """
        by_path = {v.input.path: v for v in self._views}
        # Mit Bildpunkten (points.json) nach deren Hoehe — sonst kreuzen sich
        # die Linien, weil das Bild die Tasten anders anordnet als das Profil.
        tex_pts = self._tex[2] if self._tex is not None else {}

        def key(v):
            pt = tex_pts.get(v.input.path)
            if pt is not None:
                return (pt[1], pt[0], v.input.order)
            return (v.input.point[1], v.input.point[0], v.input.order)

        rest = sorted((v for v in self._views if v.input.path not in self._order), key=key)
        ordered = [by_path[p] for p in self._order if p in by_path]
        ordered += rest
        return ordered

    def _head_height(self):
        return QFontMetrics(self._f_head).height() + 6

    def _relayout(self):
        scale, box = self._scale_and_box()
        img_w, img_h, self._tex, self._tex_k = self._image_size()
        head_h = self._head_height()
        top = head_h + 6

        paths = {v.input.path for v in self._views}
        drag_path = self._drag_path if self._dragging else None
        # Aeussere Spalte: nur wenn Karten drinstehen — oder beim Ziehen,
        # damit man eine Karte ueberhaupt dorthin legen kann.
        has_outer = bool(set(self._outer) & paths)
        use_outer = has_outer or drag_path is not None
        # Platz wird nur fuer eine BELEGTE aeussere Spalte reserviert. Beim
        # blossen Ziehen bleibt alles stehen (nichts springt unter der Maus);
        # die Spalte liegt dann ggf. teils ausserhalb — nach dem Loslassen
        # macht der Kasten Platz (bzw. stapelt die Seiten untereinander).
        extra = CARD_W + COL_GAP if has_outer else 0

        content_w = extra + CARD_W + IMG_MARGIN + img_w + 4   # 4 px zur Mitte
        width = max(self.width(), int(content_w) + 2)
        # Nebeneinander rueckt jede Seite zur Mitte (Controller innen, Karten
        # aussen); untereinander steht der Inhalt mittig.
        if self._centered:
            origin = (width - content_w) / 2
        elif self._side == "right":
            origin = 0
        else:
            origin = width - content_w
        if self._side == "right":
            img_left = origin + 4
            card_left = img_left + img_w + IMG_MARGIN
            outer_left = card_left + CARD_W + COL_GAP
        else:
            card_left = origin + extra
            outer_left = card_left - CARD_W - COL_GAP
            img_left = card_left + CARD_W + IMG_MARGIN
        self._col_x = {0: card_left, 1: outer_left if use_outer else card_left}

        ordered = self._ordered_views()
        # Zugeklappte Karten haben keine Zeilen — dadurch schrumpfen sie von
        # selbst auf die Kopfzeile zusammen, ohne Sonderfall im Zeichnen.
        entries = [(v, [] if v.input.path in self._compact else self._lines_for(v))
                   for v in ordered]
        heights = {v.input.path: self._card_height(lines) for v, lines in entries}

        def col_of(path):
            return 1 if (use_outer and path in self._outer) else 0

        def col_height(c):
            hs = [heights[v.input.path] for v, _l in entries if col_of(v.input.path) == c]
            return sum(hs) + CARD_GAP * max(len(hs) - 1, 0)

        # Standardmaessig sitzt der Controller auf halber Hoehe des Kastens,
        # also mittig zur Kartenspalte — nicht oben. Beim Ziehen zaehlen
        # weiter alle Karten mit, damit die Zeichnung nicht mitwandert.
        # Die innere Spalte bestimmt die Mitte; die aeussere steht frei.
        column_h = col_height(0) or col_height(1)
        self._column_h = column_h
        # Nebeneinander zaehlt die HOEHERE der beiden Spalten — sonst sitzt
        # der Controller mit mehr/laengeren Karten tiefer als der andere.
        center_h = self._center_h if self._center_h else column_h
        img_top = top + max((center_h - img_h) / 2, 0)
        if self._img_offset:
            img_left += self._img_offset[0]
            img_top += self._img_offset[1]
        # Nie ueber den Rand hinaus (die Mitte zum anderen Controller ist
        # eine Wand) — sonst verschwindet er halb und ist schwer zu greifen.
        img_left = min(max(img_left, 0), max(width - img_w, 0))
        img_top = max(img_top, top)
        self._img_rect = QRectF(img_left, img_top, img_w, img_h)

        gap_h = heights.get(drag_path, 0) + CARD_GAP if drag_path else 0
        layout = []
        self._gap_rect = None
        self._col_slots = {}
        self._top = top
        for c in (0, 1):
            x = self._col_x[c]
            column = [e for e in entries
                      if e[0].input.path != drag_path and col_of(e[0].input.path) == c]
            if c == 1:
                self._layout_outer(column, heights, x, top, drag_path, gap_h,
                                   layout, scale, box)
                continue
            gap_at = self._drop_index if (drag_path and self._drop_col == c) else -1
            y = top
            slots = []             # Oberkanten der Einfuegestellen (fuer das Ziehen)
            for i, (v, lines) in enumerate(column):
                if gap_at == i:
                    self._gap_rect = QRectF(x, y, CARD_W, gap_h - CARD_GAP)
                    y += gap_h
                slots.append(y)
                h = heights[v.input.path]
                layout.append((QRectF(x, y, CARD_W, h),
                               self._point_for(v, scale, box), v, lines))
                y += h + CARD_GAP
            if gap_at >= len(column):
                self._gap_rect = QRectF(x, y, CARD_W, gap_h - CARD_GAP)
                y += gap_h
            slots.append(y)
            self._col_slots[c] = slots
        self._slots = self._col_slots.get(self._drop_col if drag_path else 0, [top])

        # gezogene Karte schwebend an ihrer Mausposition
        if drag_path is not None:
            v, lines = next(e for e in entries if e[0].input.path == drag_path)
            pos = self._drag_pos or QPointF(card_left, top)
            layout.append((QRectF(pos.x(), pos.y(), CARD_W, heights[drag_path]),
                           self._point_for(v, scale, box), v, lines))
        self._layout = layout
        self._card_left = card_left

        bottom = max([r.bottom() for r, *_ in layout] + [self._img_rect.bottom(), top])
        new_h = int(bottom + 8)
        changed = new_h != self._height
        self._height = new_h
        self.setMinimumHeight(self._height)
        parent = self.parentWidget()
        if changed and parent is not None and hasattr(parent, "relayout"):
            parent.relayout()

    def _layout_outer(self, column, heights, x, top, drag_path, gap_h, layout, scale, box):
        """
        Aeussere Spalte: jede Karte steht auf ihrer gemerkten Hoehe, nicht
        von oben gestapelt. Ueberlappen darf nichts — eine Karte, die in eine
        andere hineinragen wuerde, rutscht direkt darunter. Beim Ziehen in
        diese Spalte ist die Luecke eine Karte mit der Hoehe der Maus.
        """
        items = []                  # (wunsch_y, reihenfolge, art, eintrag, hoehe)
        for i, (v, lines) in enumerate(column):
            want = self._outer.get(v.input.path)
            items.append(((top + want) if want is not None else None, i, "card",
                          (v, lines), heights[v.input.path]))
        if drag_path and self._drop_col == 1:
            want = self._drag_pos.y() if self._drag_pos is not None else top
            items.append((want, -1, "gap", None, gap_h - CARD_GAP))
        # Karten ohne Hoehe (aeltere Anordnung) zuerst, in ihrer Reihenfolge
        items.sort(key=lambda it: (it[0] is not None, it[0] or 0.0, it[1]))
        y_free = top
        slots = [top]
        for want, _i, kind, entry, h in items:
            y = max(want if want is not None else y_free, y_free, top)
            if kind == "gap":
                self._gap_rect = QRectF(x, y, CARD_W, h)
            else:
                v, lines = entry
                layout.append((QRectF(x, y, CARD_W, h), self._point_for(v, scale, box),
                               v, lines))
            y_free = y + h + CARD_GAP
            slots.append(y_free)
        self._col_slots[1] = slots

    def resizeEvent(self, event):
        self._relayout()
        super().resizeEvent(event)

    def sizeHint(self):
        img_w = self._image_size()[0]
        paths = {v.input.path for v in self._views}
        extra = CARD_W + COL_GAP if (set(self._outer) & paths) else 0
        return QSize(int(extra + CARD_W + IMG_MARGIN + img_w + 10), self._height)

    def minimumSizeHint(self):
        return self.sizeHint()

    # ------------------------------------------------------------------ #
    #  Maus
    # ------------------------------------------------------------------ #
    def _hit(self, pos):
        """('card', i) | ('point', i) | ('image', -1) | (None, -1)"""
        for i in range(len(self._layout) - 1, -1, -1):
            if self._layout[i][0].contains(pos):
                return "card", i
        for i, (_rect, pt, *_rest) in enumerate(self._layout):
            if (QPointF(pos) - pt).manhattanLength() < 12:
                return "point", i
        if self._img_rect.contains(pos):
            return "image", -1
        return None, -1

    def _index_at(self, pos):
        return self._hit(pos)[1]

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        kind, idx = self._hit(event.position())
        if kind is None:
            return super().mousePressEvent(event)
        start_tl = self._layout[idx][0].topLeft() if kind == "card" else self._img_rect.topLeft()
        self._press = (kind, idx, QPointF(event.position()), QPointF(start_tl))
        self._dragging = False

    def _drop_index_for(self, top_y, height):
        """In welche Luecke gehoert eine Karte, deren Oberkante hier liegt?"""
        middle = top_y + height / 2
        count = len(self._slots) - 1          # Slots = Kartenzahl (ohne gezogene) + 1
        best, best_d = 0, None
        for i in range(count + 1):
            # Mitte der Einfuegestelle: zwischen den Nachbarn
            y = self._slots[min(i, len(self._slots) - 1)]
            d = abs(y + height / 2 - middle)
            if best_d is None or d < best_d:
                best, best_d = i, d
        return best

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._press is not None:
            kind, idx, start, start_tl = self._press
            delta = pos - start
            if not self._dragging and delta.manhattanLength() >= DRAG_THRESHOLD \
                    and kind in ("card", "image"):
                self._dragging = True
                if kind == "card":
                    view = self._layout[idx][2]
                    self._drag_path = view.input.path
                    # Reihenfolge festhalten, damit sich beim Ziehen nur die
                    # eine Karte bewegt und der Rest stehen bleibt.
                    self._order = self.card_order()
                    self._drop_col = 1 if self._drag_path in self._outer else 0
                    same = [p for p in self._order
                            if (p in self._outer) == (self._drop_col == 1)]
                    self._drop_index = same.index(self._drag_path)
                self.setCursor(Qt.ClosedHandCursor)
            if self._dragging:
                self._drag_to(kind, idx, start_tl + delta)
            return
        kind, idx = self._hit(pos)
        if kind in ("card", "point"):
            self.setCursor(Qt.PointingHandCursor)
        elif kind == "image":
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.unsetCursor()
        if idx != self._hover:
            self._hover = idx
            if idx >= 0:
                v = self._layout[idx][2]
                tips = [v.input.path]
                for b in v.bindings:
                    for r in b.inputs:
                        if r.action:
                            tips.append(f"{r.input}: {r.action}")
                tips += ["", self._texts.get("hint", "")]
                self.setToolTip("\n".join(t for t in tips if t is not None).strip())
            else:
                self.setToolTip(self._texts.get("hint_image", "") if kind == "image" else "")
            self.update()
        super().mouseMoveEvent(event)

    def _drag_to(self, kind, idx, top_left):
        if kind == "card":
            height = next((r.height() for r, _p, v, _l in self._layout
                           if v.input.path == self._drag_path), 40)
            x = min(max(top_left.x(), 0), max(self.width() - CARD_W, 0))
            y = max(top_left.y(), self._head_height())
            self._drag_pos = QPointF(x, y)
            # Spalte: die, deren Mitte der Karte am naechsten ist
            self._drop_col = min((0, 1), key=lambda c: abs(self._col_x[c] - x))
            self._slots = self._col_slots.get(self._drop_col, [self._head_height()])
            self._drop_index = self._drop_index_for(y, height)
        else:
            base_left = self._img_rect.left() - (self._img_offset[0] if self._img_offset else 0)
            base_top = self._img_rect.top() - (self._img_offset[1] if self._img_offset else 0)
            x = min(max(top_left.x(), 0), max(self.width() - self._img_rect.width(), 0))
            y = max(top_left.y(), self._head_height() + 6)
            self._img_offset = [round(x - base_left, 1), round(y - base_top, 1)]
            self.image_moved.emit(list(self._img_offset), False)
        self._relayout()
        self.updateGeometry()
        self.update()

    def mouseReleaseEvent(self, event):
        press, dragging = self._press, self._dragging
        self._press = None
        self._dragging = False
        if press is None:
            return super().mouseReleaseEvent(event)
        kind, idx = press[0], press[1]
        if dragging:
            if kind == "card" and self._drag_path:
                path = self._drag_path
                order = [p for p in self._order if p != path]
                to_outer = self._drop_col == 1
                if to_outer:
                    # dort bleiben, wo die Luecke war (frei in der Hoehe)
                    y = self._gap_rect.top() if self._gap_rect is not None else self._top
                    self._outer[path] = round(max(y - self._top, 0), 1)
                else:
                    self._outer.pop(path, None)
                # Einfuegen VOR die Karte, die in der Zielspalte an der
                # Einfuegestelle steht — sonst hinter die letzte der Spalte
                col = [p for p in order if (p in self._outer) == to_outer]
                if self._drop_index < len(col):
                    order.insert(order.index(col[self._drop_index]), path)
                elif col:
                    order.insert(order.index(col[-1]) + 1, path)
                else:
                    order.append(path)
                self._order = order
            self._drag_path = None
            self._drag_pos = None
            self._drop_index = -1
            self._relayout()
            # Gemerkte Hoehen = das, was jetzt zu sehen ist (weggeschobene
            # Karten bleiben an ihrer neuen Stelle, statt spaeter zu springen)
            for rect, _pt, v, _l in self._layout:
                if v.input.path in self._outer:
                    self._outer[v.input.path] = round(rect.top() - self._top, 1)
            self.updateGeometry()
            parent = self.parentWidget()
            if parent is not None and hasattr(parent, "relayout"):
                parent.relayout()
            self.update()
            self.setCursor(Qt.OpenHandCursor if kind == "image" else Qt.PointingHandCursor)
            self.layout_changed.emit(self.layout_state())
            if kind == "image":
                self.image_moved.emit(list(self._img_offset or [0, 0]), True)
        elif kind in ("card", "point") and 0 <= idx < len(self._layout):
            self.card_clicked.emit(self._layout[idx][2].input.path)

    def contextMenuEvent(self, event):
        """
        Rechtsklick auf eine Karte: diese eine Karte zu- oder aufklappen,
        oder gleich alle. Trifft der Klick keine Karte, kommt nur
        „alle auf/zu“ — so kommt man auch aus einem komplett
        zugeklappten Controller wieder heraus.
        """
        from PySide6.QtWidgets import QMenu

        texts = self._texts
        kind, idx = self._hit(QPointF(event.pos()))
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background:#21252b; color:#d8dee9; border:1px solid #3b4252; }"
            " QMenu::item { padding:6px 18px; }"
            " QMenu::item:selected { background:#3b4252; color:#88c0d0; }")
        act_one = None
        if kind in ("card", "point") and 0 <= idx < len(self._layout):
            path = self._layout[idx][2].input.path
            act_one = menu.addAction(
                texts.get("menu_show", "Anzeigen") if self.is_compact(path)
                else texts.get("menu_hide", "Verstecken"))
            menu.addSeparator()
        else:
            path = None
        act_all_hide = menu.addAction(texts.get("menu_hide_all", "Alle verstecken"))
        act_all_show = menu.addAction(texts.get("menu_show_all", "Alle anzeigen"))
        chosen = menu.exec(event.globalPos())
        if chosen is None:
            return
        if chosen is act_one and path:
            self.toggle_compact(path)
        elif chosen is act_all_hide:
            self.set_tidy(True)
        elif chosen is act_all_show:
            self.set_tidy(False)

    def leaveEvent(self, event):
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    # ------------------------------------------------------------------ #
    #  Zeichnen
    # ------------------------------------------------------------------ #
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Ueberschrift ("Linker Controller")
        p.setFont(self._f_head)
        p.setPen(C_TITLE)
        title_rect = QRectF(0, 0, self.width(), QFontMetrics(self._f_head).height() + 6)
        if self._centered:
            align = Qt.AlignHCenter
        else:
            align = Qt.AlignLeft if self._side == "right" else Qt.AlignRight
        p.drawText(title_rect.adjusted(6, 0, -6, 0), align | Qt.AlignVCenter,
                   self._texts.get("title", ""))

        # Erst der Controller, dann die Linien darueber — sonst verschwinden
        # sie unter dem Bild und man sieht nicht, wo sie hinfuehren.
        self._paint_body(p)
        for i, (rect, pt, v, _lines) in enumerate(self._layout):
            self._paint_line(p, rect, pt, v, i == self._hover)

        # Einfuegestelle beim Ziehen
        if self._gap_rect is not None:
            pen = QPen(C_DROP, 1.6, Qt.DashLine)
            p.setPen(pen)
            p.setBrush(QColor(94, 129, 172, 40))
            p.drawRoundedRect(self._gap_rect, 6, 6)

        for i, (rect, pt, v, lines) in enumerate(self._layout):
            dragged = self._dragging and v.input.path == self._drag_path
            self._paint_card(p, rect, v, lines, i == self._hover or dragged)
            self._paint_point(p, pt, v, i == self._hover or dragged)
        p.end()

    def _texture(self):
        """(QPixmap, gespiegelt) fuer diesen Controller — oder None."""
        found = texture_file(self._controller, self._side)
        if not found:
            return None
        pix = load_texture(found[0])
        return (pix, found[1]) if pix is not None else None

    def _paint_texture(self, p, pix, mirror):
        """Bild ohne Verzerrung in die Zeichenflaeche einpassen, mittig."""
        box = self._img_rect
        if pix.width() <= 0 or pix.height() <= 0:
            return
        k = min(box.width() / pix.width(), box.height() / pix.height())
        w, h = pix.width() * k, pix.height() * k
        target = QRectF(box.left() + (box.width() - w) / 2,
                        box.top() + (box.height() - h) / 2, w, h)
        p.save()
        if mirror:
            # Um die Mitte der Flaeche spiegeln, damit das Bild an derselben
            # Stelle bleibt und nur seitenverkehrt ist (wie die Zeichnung).
            p.translate(box.center().x(), 0)
            p.scale(-1, 1)
            p.translate(-box.center().x(), 0)
        p.drawPixmap(target, pix, QRectF(pix.rect()))
        p.restore()

    def _paint_body(self, p):
        if self._tex is not None:
            pix, crop, _pts = self._tex
            p.drawPixmap(self._img_rect, pix, crop)
            return
        tex = self._texture()
        if tex is not None:
            self._paint_texture(p, tex[0], tex[1])
            return
        scale, box = self._scale_and_box()
        art = DRAWINGS.get(self._controller)
        p.save()
        p.translate(self._img_rect.topLeft())
        if self._side == "right":
            p.translate(box.width() * scale, 0)
            p.scale(-scale, scale)
        else:
            p.scale(scale, scale)
        p.translate(-box.left(), -box.top())
        if art:
            body, parts = art[0](self._side)
            p.setPen(QPen(C_BODY_EDGE, 2.4 / scale))
            p.setBrush(C_BODY)
            for path in body:
                p.drawPath(path)
            p.setPen(QPen(C_PART_EDGE, 2.0 / scale))
            p.setBrush(C_PART)
            for path in parts:
                p.drawPath(path)
        else:
            # Unbekannter Controller: neutrale Flaeche, die Punkte zeigen alles
            p.setPen(QPen(C_BODY_EDGE, 2.0 / scale, Qt.DashLine))
            p.setBrush(QColor(46, 52, 64, 120))
            p.drawRoundedRect(QRectF(box.left() + 2, box.top() + 2,
                                     box.width() - 4, box.height() - 4), 12, 12)
        p.restore()

    def _paint_line(self, p, rect, pt, v, hover):
        bound = any(r.action for b in v.bindings for r in b.inputs)
        color = C_CARD_HOVER if hover else (C_LINE_BOUND if bound else C_LINE)
        pen = QPen(color, 2.0 if hover else 1.3)
        if not bound and not hover:
            pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        fm_t = QFontMetrics(self._f_title)
        y0 = rect.top() + CARD_PAD + fm_t.height() / 2
        # Von der Kartenkante, die dem Punkt zugewandt ist
        if pt.x() < rect.center().x():
            start = QPointF(rect.left(), y0)
            mid_x = rect.left() - IMG_MARGIN * 0.55
        else:
            start = QPointF(rect.right(), y0)
            mid_x = rect.right() + IMG_MARGIN * 0.55
        path = QPainterPath(start)
        path.lineTo(mid_x, y0)
        path.cubicTo(QPointF((mid_x + pt.x()) / 2, y0), QPointF((mid_x + pt.x()) / 2, pt.y()), pt)
        p.drawPath(path)

    def _paint_point(self, p, pt, v, hover):
        bound = any(r.action for b in v.bindings for r in b.inputs)
        p.setPen(QPen(QColor("#1c1f26"), 1.5))
        p.setBrush(C_CARD_HOVER if (hover or bound) else C_NONE)
        r = 5 if hover else 4
        p.drawEllipse(pt, r, r)

    def _paint_card(self, p, rect, v, lines, hover):
        p.setPen(QPen(C_CARD_HOVER if hover else C_CARD_BORDER, 1.2))
        p.setBrush(C_CARD)
        p.drawRoundedRect(rect, 6, 6)

        fm_t = QFontMetrics(self._f_title)
        fm_s = QFontMetrics(self._f_small)
        x = rect.left() + CARD_PAD
        y = rect.top() + CARD_PAD
        inner_w = rect.width() - 2 * CARD_PAD

        name = v.input.name[:1].upper() + v.input.name[1:]
        p.setFont(self._f_title)
        p.setPen(C_TITLE)
        p.drawText(QRectF(x, y, inner_w, fm_t.height()), Qt.AlignLeft | Qt.AlignVCenter, name)
        p.setFont(self._f_small)
        p.setPen(C_TYPE)
        # Zugeklappt: ein Pfeil hinter dem Typ zeigt, dass da noch etwas ist.
        type_text = v.input.type + ("  ▸" if self.is_compact(v.input.path) else "")
        p.drawText(QRectF(x, y, inner_w, fm_t.height()), Qt.AlignRight | Qt.AlignVCenter,
                   type_text)
        y += fm_t.height()

        col = max((fm_s.horizontalAdvance(t[1]) for t in lines if t[0] == "row"), default=0)
        col = min(col + 14, inner_w * 0.45) if col else 0
        for kind, a, b in lines:
            h = fm_s.height() + 2
            r = QRectF(x, y, inner_w, h)
            if kind == "mode":
                p.setFont(self._f_mode)
                p.setPen(C_MODE)
                p.drawText(r, Qt.AlignLeft | Qt.AlignVCenter, a)
            elif kind == "row":
                p.setFont(self._f_small)
                p.setPen(C_INPUT)
                p.drawText(QRectF(x + 8, y, col, h), Qt.AlignLeft | Qt.AlignVCenter, a)
                p.setPen(C_ACTION if b != self._texts.get("none", "—") else C_NONE)
                text = fm_s.elidedText(b, Qt.ElideRight, int(inner_w - col - 8))
                p.drawText(QRectF(x + 8 + col, y, inner_w - col - 8, h),
                           Qt.AlignLeft | Qt.AlignVCenter, text)
            elif kind == "param":
                p.setFont(self._f_small)
                p.setPen(C_TYPE)
                p.drawText(QRectF(x + 8, y, inner_w - 8, h), Qt.AlignLeft | Qt.AlignVCenter,
                           fm_s.elidedText(a, Qt.ElideRight, int(inner_w - 8)))
            else:
                p.setFont(self._f_small)
                p.setPen(C_NONE)
                p.drawText(r, Qt.AlignLeft | Qt.AlignVCenter, a)
            y += h


class ControllerPair(QWidget):
    """
    Linker und rechter Controller nebeneinander — oder untereinander, wenn
    das Fenster zu schmal ist. So wird nie etwas rechts abgeschnitten.
    """

    SPACING = 9          # schmal: in der Mitte steht nur ein duenner Strich

    def __init__(self, left, right, parent=None):
        super().__init__(parent)
        self.left = left
        self.right = right
        left.setParent(self)
        right.setParent(self)
        # Beide Controller bleiben gleich gross und spiegelbildlich: wer einen
        # verschiebt, verschiebt den anderen gespiegelt mit.
        left.image_moved.connect(lambda off, done: self._mirror(right, off, done))
        right.image_moved.connect(lambda off, done: self._mirror(left, off, done))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._stacked = False

    def _needed_width(self):
        w = self.left.sizeHint().width()
        if self.right.isVisibleTo(self):
            w += self.SPACING + self.right.sizeHint().width()
        return w

    def is_stacked(self):
        return self._stacked

    def _mirror(self, other, offset, done):
        if other.isVisibleTo(self):
            other.mirror_image_offset(offset, notify=done)

    def paintEvent(self, _event):
        """Nebeneinander: ein duenner Strich zwischen links und rechts."""
        if self._stacked or not self.right.isVisibleTo(self):
            return
        p = QPainter(self)
        x = self.left.geometry().right() + self.SPACING / 2 + 0.5
        p.setPen(QPen(C_CARD_BORDER, 1))
        p.drawLine(QPointF(x, 4), QPointF(x, self.height() - 4))
        p.end()

    def sync_mirror(self):
        """Rechts uebernimmt den (gespiegelten) Versatz von links.

        Aeltere Anordnungen haben je Seite einen eigenen Versatz — dann
        stuenden die Controller versetzt. Links gibt den Ton an.
        """
        if self.right.isVisibleTo(self):
            self.right.mirror_image_offset(self.left.layout_state()["image"])

    def relayout(self):
        width = max(self.width(), 1)
        both = self.right.isVisibleTo(self)
        self._stacked = both and width < self._needed_width()
        self.left.set_centered(self._stacked)
        self.right.set_centered(self._stacked)
        # Beide Controller auf dieselbe Hoehe: mittig zur hoeheren Spalte
        if both and not self._stacked:
            common = max(self.left.column_height(), self.right.column_height())
            self.left.set_center_height(common)
            self.right.set_center_height(common)
        else:
            self.left.set_center_height(None)
            self.right.set_center_height(None)
        if not both:
            h = self.left.minimumHeight()
            self.left.setGeometry(0, 0, width, h)
        elif self._stacked:
            hl = self.left.minimumHeight()
            self.left.setGeometry(0, 0, width, hl)
            self.right.setGeometry(0, hl + self.SPACING, width, self.right.minimumHeight())
            h = hl + self.SPACING + self.right.minimumHeight()
        else:
            half = (width - self.SPACING) // 2
            self.left.setGeometry(0, 0, half, self.left.minimumHeight())
            self.right.setGeometry(half + self.SPACING, 0, width - half - self.SPACING,
                                   self.right.minimumHeight())
            h = max(self.left.minimumHeight(), self.right.minimumHeight())
        if self.minimumHeight() != h:
            self.setMinimumHeight(h)
            self.updateGeometry()

    def _layout_outer(self, column, heights, x, top, drag_path, gap_h, layout, scale, box):
        """
        Aeussere Spalte: jede Karte steht auf ihrer gemerkten Hoehe, nicht
        von oben gestapelt. Ueberlappen darf nichts — eine Karte, die in eine
        andere hineinragen wuerde, rutscht direkt darunter. Beim Ziehen in
        diese Spalte ist die Luecke eine Karte mit der Hoehe der Maus.
        """
        items = []                  # (wunsch_y, reihenfolge, art, eintrag, hoehe)
        for i, (v, lines) in enumerate(column):
            want = self._outer.get(v.input.path)
            items.append(((top + want) if want is not None else None, i, "card",
                          (v, lines), heights[v.input.path]))
        if drag_path and self._drop_col == 1:
            want = self._drag_pos.y() if self._drag_pos is not None else top
            items.append((want, -1, "gap", None, gap_h - CARD_GAP))
        # Karten ohne Hoehe (aeltere Anordnung) zuerst, in ihrer Reihenfolge
        items.sort(key=lambda it: (it[0] is not None, it[0] or 0.0, it[1]))
        y_free = top
        slots = [top]
        for want, _i, kind, entry, h in items:
            y = max(want if want is not None else y_free, y_free, top)
            if kind == "gap":
                self._gap_rect = QRectF(x, y, CARD_W, h)
            else:
                v, lines = entry
                layout.append((QRectF(x, y, CARD_W, h), self._point_for(v, scale, box),
                               v, lines))
            y_free = y + h + CARD_GAP
            slots.append(y_free)
        self._col_slots[1] = slots

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.relayout()

    def sizeHint(self):
        return QSize(self.left.sizeHint().width(), self.minimumHeight())

    def minimumSizeHint(self):
        return QSize(self.left.sizeHint().width(), self.minimumHeight())
