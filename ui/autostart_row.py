#!/usr/bin/env python3
"""
ui/autostart_row.py — Eine Autostart-Zeile (Dashboard UND Autostart-Profile)
============================================================================
Gleiches Aussehen und Verhalten an beiden Stellen:

  ┌ Karte ──────────────────────────────────────────────────────────────┐
  │ [CMD ▾] [Startbefehl ……………] [Apps] │ ☐ Debug │ ☐ Kill │  ✕         │
  │ [Kill│ Kill-Befehl ……………………………………]  (nur mit Haken „Kill“)       │
  └─────────────────────────────────────────────────────────────────────┘

  * Spaltenkoepfe Debug | Kill einmal darueber (column_header).
  * Kill-Feld mit kleinem Abzeichen; Reinklicken ins leere Feld schlaegt
    einen Befehl aus dem Startbefehl vor (core/killcmd_suggest.py).

Der Gastgeber (VRApp) liefert: _autostart_command_pool, _autostart_mode_changed,
_autostart_browse. Speichern/Loeschen laufen ueber on_change/on_delete.
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QCompleter, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

from translations import tr

CARD_CSS = ("QFrame#autostartRowCard { background:rgba(255,255,255,10);"
            " border:1px solid #3b4252; border-radius:6px; }")
BADGE_CSS = ("QLabel#autostartKillBadge { color:#e5a3a9; font-size:10px; font-weight:bold;"
             " background:rgba(191,97,106,55); border-radius:3px; padding:1px 6px; }")
DEL_CSS = ("QPushButton { background-color:#2e3440; color:#bf616a; border:1px solid #4c566a;"
           " font-weight:bold; padding:4px; border-radius:4px; }"
           "QPushButton:hover { background-color:#bf616a; color:white; border-color:#bf616a; }")
CARD_MARGIN = 8                      # Innenabstand der Karte (links/rechts)


def column_header():
    """Kopfzeile „Debug | Kill“ ueber den Zeilen. Rueckgabe: (layout, labels)."""
    from ui.ui_main import (AUTOSTART_DEL_W, autostart_col_label, autostart_col_sep)
    head = QHBoxLayout()
    head.setContentsMargins(0, 4, 0, 0)
    head.setSpacing(6)
    head.addStretch(1)
    lbl_debug = autostart_col_label(tr("autostart_col_debug"), tr("autostart_debug_tip"), "#ebcb8b")
    lbl_kill = autostart_col_label(tr("autostart_col_kill"), tr("autostart_kill_tip_col"), "#bf616a")
    head.addWidget(autostart_col_sep())
    head.addWidget(lbl_debug)
    head.addWidget(autostart_col_sep())
    head.addWidget(lbl_kill)
    # Qt setzt vor einem Platzhalter keinen Abstand -> selbst mitrechnen;
    # +CARD_MARGIN+1: Innenabstand + Rahmen der Zeilen-Karten.
    head.addSpacing(AUTOSTART_DEL_W + head.spacing() + CARD_MARGIN + 1)
    return head, (lbl_debug, lbl_kill)


def retranslate_header(labels):
    lbl_debug, lbl_kill = labels
    lbl_debug.setText(tr("autostart_col_debug"))
    lbl_debug.setToolTip(tr("autostart_debug_tip"))
    lbl_kill.setText(tr("autostart_col_kill"))
    lbl_kill.setToolTip(tr("autostart_kill_tip_col"))


def offer_kill_suggestion(row):
    """Leeres Kill-Feld: Vorschlag aus dem Startbefehl (markiert, Tippen ersetzt)."""
    import killcmd_suggest
    ki = row["kill_input"]
    if ki.text().strip():
        return                       # Eigenes nie ueberschreiben
    text = killcmd_suggest.suggest(row["input"].text(), row["combo"].currentText())
    if text:
        ki.setText(text)
        ki.selectAll()


def retranslate_row(row):
    row["kill_input"].setPlaceholderText(tr("autostart_kill_placeholder"))
    row["kill_input"].setToolTip(tr("autostart_kill_field_tip"))
    row["kill_label"].setText(tr("autostart_kill_label"))
    row["kill_label"].adjustSize()
    row["kill_input"].setTextMargins(row["kill_label"].width() + 8, 0, 0, 0)
    row["chk_debug"].setToolTip(tr("autostart_debug_tip"))
    row["chk_kill"].setToolTip(tr("autostart_kill_tip_col"))
    row["btn_del"].setToolTip(tr("autostart_profile_row_del_tip"))


def build_row(host, app=None, on_change=None, on_delete=None):
    """Zeile bauen (noch nicht eingehaengt). app: gespeicherte Werte
    {"type", "cmd", "debug", "kill_on", "kill"} oder None."""
    from ui.ui_main import (AUTOSTART_COL_W, AUTOSTART_DEL_W, autostart_col_check,
                            autostart_col_sep)
    app = app or {}
    on_change = on_change or (lambda *_a: None)

    card = QFrame()
    card.setObjectName("autostartRowCard")
    card.setStyleSheet(CARD_CSS)
    v = QVBoxLayout(card)
    v.setContentsMargins(CARD_MARGIN, 6, CARD_MARGIN, 6)
    v.setSpacing(5)

    top = QWidget()
    h = QHBoxLayout(top)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(6)
    combo = QComboBox()
    combo.addItems(["Custom Path", "CMD"])
    combo.setFixedWidth(110)
    inp = QLineEdit(app.get("cmd", ""))
    # Autovervollstaendigung (CMD): installierte Startbefehle + PATH.
    completer = QCompleter(host._autostart_command_pool(), host)
    completer.setCaseSensitivity(Qt.CaseInsensitive)
    completer.setFilterMode(Qt.MatchContains)
    completer.setCompletionMode(QCompleter.PopupCompletion)
    inp.setCompleter(completer)
    btn = QPushButton("Browse...")
    btn.setMinimumWidth(95)
    chk_debug, dbg_cell = autostart_col_check(tr("autostart_debug_tip"))
    chk_kill, kill_cell = autostart_col_check(tr("autostart_kill_tip_col"))
    btn_del = QPushButton("✕")
    btn_del.setFixedWidth(AUTOSTART_DEL_W)
    btn_del.setStyleSheet(DEL_CSS)
    for w in (combo, inp, btn, autostart_col_sep(), dbg_cell, autostart_col_sep(),
              kill_cell, btn_del):
        h.addWidget(w)
    h.setStretch(1, 1)
    v.addWidget(top)

    # Kill-Zeile: beginnt unter dem Dropdown, endet unter „Apps/Browse“
    kill_row = QWidget()
    kl = QHBoxLayout(kill_row)
    kl.setContentsMargins(0, 0, 0, 0)
    kl.setSpacing(6)
    kill_inp = QLineEdit(app.get("kill", ""))
    badge = QLabel(tr("autostart_kill_label"), kill_inp)
    badge.setObjectName("autostartKillBadge")
    badge.setAlignment(Qt.AlignCenter)
    badge.setAttribute(Qt.WA_TransparentForMouseEvents)
    badge.setStyleSheet(BADGE_CSS)
    place = lambda _e=None: badge.move(5, max(0, (kill_inp.height() - badge.height()) // 2))  # noqa: E731
    kill_inp.resizeEvent = lambda e: (QLineEdit.resizeEvent(kill_inp, e), place())
    kl.addWidget(kill_inp, 1)
    kl.addSpacing(2 * (2 + AUTOSTART_COL_W) + AUTOSTART_DEL_W + 5 * 6)
    v.addWidget(kill_row)

    row = {"widget": card, "combo": combo, "input": inp, "btn": btn,
           "chk_debug": chk_debug, "chk_kill": chk_kill, "kill_input": kill_inp,
           "kill_row": kill_row, "kill_label": badge, "btn_del": btn_del,
           "completer": completer}
    retranslate_row(row)
    place()

    combo.setCurrentText(app.get("type", "Custom Path"))
    chk_debug.setChecked(bool(app.get("debug", False)))
    chk_kill.setChecked(bool(app.get("kill_on", False)))
    kill_row.setVisible(chk_kill.isChecked())

    def kill_toggled(on):
        kill_row.setVisible(on)
        if on and not kill_inp.text():
            kill_inp.setFocus()                  # -> Vorschlag (focusInEvent)
        on_change()

    combo.currentTextChanged.connect(
        lambda text: host._autostart_mode_changed(text, inp, btn))
    combo.currentTextChanged.connect(lambda _t: on_change())
    inp.textChanged.connect(lambda _t: on_change())
    chk_debug.toggled.connect(lambda _on: on_change())
    chk_kill.toggled.connect(kill_toggled)
    kill_inp.textChanged.connect(lambda _t: on_change())
    kill_inp.focusInEvent = lambda e: (
        QLineEdit.focusInEvent(kill_inp, e),
        QTimer.singleShot(0, lambda: offer_kill_suggestion(row)))
    btn.clicked.connect(lambda _c=False: host._autostart_browse(inp, combo))
    if on_delete is not None:
        btn_del.clicked.connect(lambda _c=False: on_delete(row))
    host._autostart_mode_changed(combo.currentText(), inp, btn)
    return row


def row_data(row):
    """Gespeicherte Form einer Zeile. Kill-Felder nur, wenn benutzt — alte
    Profile bleiben dadurch unveraendert gespeichert."""
    data = {"type": row["combo"].currentText(),
            "cmd": row["input"].text(),
            "debug": row["chk_debug"].isChecked()}
    if row["chk_kill"].isChecked() or row["kill_input"].text():
        data["kill_on"] = row["chk_kill"].isChecked()
        data["kill"] = row["kill_input"].text()
    return data
