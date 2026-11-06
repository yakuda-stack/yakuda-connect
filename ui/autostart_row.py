#!/usr/bin/env python3
"""
ui/autostart_row.py — Eine Autostart-Zeile (Dashboard UND Autostart-Profile)
============================================================================
Gleiches Aussehen und Verhalten an beiden Stellen:

  ┌ Karte ──────────────────────────────────┐
  │ ▣ WayVR                [Debug] [Kill] ⚙ ✕│
  └─────────────────────────────────────────┘

Der Rest liegt im Zahnrad-Fenster: Name, Art, Startbefehl, Debug, Kill-Befehl.
Diese Felder gehoeren die ganze Zeit zur Zeile (``panel``), sind aber nur
sichtbar, solange das Fenster offen ist. Darum lesen und setzen Speichern und
Starten sie wie zuvor, und Aenderungen gelten sofort.

"+ Programm" laeuft ueber add_program: zuerst die Auswahl, die Zeile entsteht
erst danach. Abbrechen hinterlaesst deshalb keine leere Zeile.

Icon der Zeile, in dieser Reihenfolge: eigenes Icon, Icon-Ordner
(core/tool_icons.py), Icon des Systems, Standard-Icon.

Der Gastgeber (VRApp) liefert: _autostart_command_pool, _autostart_mode_changed,
_autostart_browse, fetch_tool_icon. Speichern/Loeschen laufen ueber
on_change/on_delete.
"""
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QCompleter, QDialog,
                               QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QStyle, QVBoxLayout, QWidget)

import autostart_name
import killcmd_suggest
import programs
import tool_icons
from translations import get_language, tr

CARD_CSS = ("QFrame#autostartRowCard { background:rgba(255,255,255,10);"
            " border:1px solid #3b4252; border-radius:6px; }")
BADGE_CSS = ("QLabel#autostartKillBadge { color:#e5a3a9; font-size:10px; font-weight:bold;"
             " background:rgba(191,97,106,55); border-radius:3px; padding:1px 6px; }")
DEBUG_BADGE_CSS = ("QLabel { color:#ebcb8b; font-size:10px; font-weight:bold;"
                   " background:rgba(235,203,139,40); border-radius:3px; padding:1px 6px; }")
DEL_CSS = ("QPushButton { background-color:#2e3440; color:#bf616a; border:1px solid #4c566a;"
           " font-weight:bold; padding:4px; border-radius:4px; }"
           "QPushButton:hover { background-color:#bf616a; color:white; border-color:#bf616a; }")
GEAR_CSS = ("QPushButton { background-color:#2e3440; color:#d8dee9; border:1px solid #4c566a;"
            " font-weight:bold; padding:4px; border-radius:4px; }"
            "QPushButton:hover { background-color:#434c5e; }")
CARD_MARGIN = 8                      # Innenabstand der Karte (links/rechts)
BUTTON_W = 30                        # Breite von Zahnrad und ✕
ROW_ICON = 20                        # Icon in der Zeile (Pixel)
PREVIEW_ICON = 32                    # Vorschau im Zahnrad-Fenster


class ModeCombo(QComboBox):
    """Zeigt uebersetzte Namen. mode() ist die Auswahl im Fenster, currentText()
    der gespeicherte Typ: "Programm" ist ein Befehl und wird als "CMD" gespeichert."""

    def __init__(self):
        super().__init__()
        self.addItem(tr("autostart_mode_cmd"), "CMD")
        self.addItem(tr("autostart_mode_path"), "Custom Path")
        self.addItem(tr("autostart_mode_app"), "App")

    def mode(self):
        return self.currentData() or "Custom Path"

    def currentText(self):
        return "CMD" if self.mode() == "App" else self.mode()

    def setCurrentText(self, mode):
        index = self.findData(mode)
        self.setCurrentIndex(index if index >= 0 else self.findData("Custom Path"))

    def retranslate(self):
        self.setItemText(0, tr("autostart_mode_cmd"))
        self.setItemText(1, tr("autostart_mode_path"))
        self.setItemText(2, tr("autostart_mode_app"))


def offer_kill_suggestion(row):
    """Leeres Kill-Feld: Vorschlag aus dem Startbefehl (markiert, Tippen ersetzt)."""
    ki = row["kill_input"]
    if ki.text().strip():
        return                       # Eigenes nie ueberschreiben
    text = killcmd_suggest.suggest(row["input"].text(), row["combo"].currentText())
    if text:
        ki.setText(text)
        ki.selectAll()


def apply_saved_mode(row):
    """Gespeicherter Befehl eines Tools-Tab-Programms -> Auswahl "Programm"."""
    if (row["combo"].mode() == "CMD"
            and autostart_name.is_tool_command(row["input"].text(), programs.all_tools())):
        row["combo"].setCurrentText("App")


def row_tool(row):
    """Eintrag aus dem Tools-Tab zu dieser Zeile oder None."""
    return autostart_name.find_tool(row["input"].text(), row["combo"].currentText(),
                                    programs.all_tools())


def resolve_icon(row):
    """Icon der Zeile. Rueckgabe: (QIcon, ist_Standard-Icon)."""
    if row["icon"] and os.path.isfile(row["icon"]):
        return QIcon(row["icon"]), False
    tool = row_tool(row)
    names = [killcmd_suggest.program_name(row["input"].text(), row["combo"].currentText()).lower()]
    if tool:
        path = tool_icons.local_icon(tool)
        if path:
            return QIcon(path), False
        names = [tool.get("pkg"), tool.get("key"), tool.get("start_cmd")] + names
    for name in names:
        if name and QIcon.hasThemeIcon(name):
            return QIcon.fromTheme(name), False
    return QApplication.style().standardIcon(QStyle.SP_FileIcon), True


def row_tooltip(row):
    """Beschreibung aus dem Tools-Tab, darunter der Befehl."""
    tool = row_tool(row)
    desc = programs.tool_text(tool, "desc", get_language()) if tool else ""
    return "\n\n".join(part for part in (desc, row["input"].text()) if part)


def row_title(row):
    """Name der Zeile oder '', solange kein Programm eingetragen ist."""
    return autostart_name.display_name(row["input"].text(), row["combo"].currentText(),
                                       row["name_input"].text(), programs.all_tools())


def refresh_row(row):
    """Sichtbare Zeile an die Felder im Zahnrad-Fenster angleichen."""
    title = row_title(row)
    label = row["lbl_name"]
    label.setText(title or tr("autostart_row_empty"))
    tooltip = row_tooltip(row)
    label.setToolTip(tooltip)
    row["lbl_icon"].setToolTip(tooltip)
    label.setStyleSheet("font-weight:bold; color:#eceff4;" if title else "color:#7b88a1;")
    row["name_input"].setPlaceholderText(
        autostart_name.display_name(row["input"].text(), row["combo"].currentText(),
                                    "", programs.all_tools()))
    icon, is_default = resolve_icon(row)
    show = getattr(row["host"], "_show_autostart_icons", True)
    row["lbl_icon"].setVisible(show)
    row["lbl_icon"].setPixmap(icon.pixmap(ROW_ICON, ROW_ICON))
    row["lbl_preview"].setPixmap(icon.pixmap(PREVIEW_ICON, PREVIEW_ICON))
    tool = row_tool(row)
    fetchable = bool(tool) and tool_icons.has_url(tool)
    row["btn_icon_fetch"].setVisible(bool(tool) and is_default)
    row["btn_icon_fetch"].setEnabled(fetchable)
    row["btn_icon_fetch"].setToolTip(tr("autostart_icon_fetch_tip" if fetchable
                                        else "autostart_icon_no_url"))
    row["btn_icon_reset"].setVisible(bool(row["icon"]))
    row["badge_debug"].setVisible(row["chk_debug"].isChecked())
    row["badge_kill"].setVisible(row["chk_kill"].isChecked()
                                 and bool(row["kill_input"].text().strip()))


def retranslate_row(row):
    row["combo"].retranslate()
    row["host"]._autostart_mode_changed(row["combo"].mode(), row["input"], row["btn"])
    row["kill_input"].setPlaceholderText(tr("autostart_kill_placeholder"))
    row["kill_input"].setToolTip(tr("autostart_kill_field_tip"))
    row["kill_label"].setText(tr("autostart_kill_label"))
    row["kill_label"].adjustSize()
    row["kill_input"].setTextMargins(row["kill_label"].width() + 8, 0, 0, 0)
    row["chk_debug"].setText(tr("autostart_col_debug"))
    row["chk_debug"].setToolTip(tr("autostart_debug_tip"))
    row["chk_kill"].setText(tr("autostart_col_kill"))
    row["chk_kill"].setToolTip(tr("autostart_kill_tip_col"))
    row["btn_del"].setToolTip(tr("autostart_profile_row_del_tip"))
    row["btn_settings"].setToolTip(tr("autostart_row_settings_tip"))
    row["lbl_name_field"].setText(tr("autostart_row_name"))
    row["lbl_cmd_field"].setText(tr("autostart_row_start"))
    row["lbl_icon_field"].setText(tr("autostart_row_icon"))
    row["btn_icon_fetch"].setText(tr("autostart_icon_fetch"))
    row["btn_icon_pick"].setText(tr("autostart_icon_pick"))
    row["btn_icon_reset"].setText(tr("autostart_icon_reset"))
    row["badge_debug"].setText(tr("autostart_col_debug"))
    row["badge_kill"].setText(tr("autostart_col_kill"))
    refresh_row(row)


def _build_panel(host, app, card):
    """Felder des Zahnrad-Fensters. Sie bleiben Kinder der Karte."""
    panel = QWidget(card)
    panel.setMinimumWidth(520)
    panel.hide()
    v = QVBoxLayout(panel)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(8)

    lbl_name = QLabel()
    name_input = QLineEdit(app.get("name", ""))
    v.addWidget(lbl_name)
    v.addWidget(name_input)

    lbl_icon = QLabel()
    v.addWidget(lbl_icon)
    icons = QHBoxLayout()
    icons.setSpacing(6)
    lbl_preview = QLabel()
    lbl_preview.setFixedSize(PREVIEW_ICON, PREVIEW_ICON)
    btn_fetch = QPushButton()
    btn_pick = QPushButton()
    btn_reset = QPushButton()
    icons.addWidget(lbl_preview)
    icons.addWidget(btn_fetch)
    icons.addWidget(btn_pick)
    icons.addWidget(btn_reset)
    icons.addStretch()
    v.addLayout(icons)

    lbl_cmd = QLabel()
    v.addWidget(lbl_cmd)
    line = QHBoxLayout()
    line.setSpacing(6)
    combo = ModeCombo()
    combo.setFixedWidth(160)
    inp = QLineEdit(app.get("cmd", ""))
    # Autovervollstaendigung (CMD): installierte Startbefehle + PATH.
    completer = QCompleter(host._autostart_command_pool(), host)
    completer.setCaseSensitivity(Qt.CaseInsensitive)
    completer.setFilterMode(Qt.MatchContains)
    completer.setCompletionMode(QCompleter.PopupCompletion)
    inp.setCompleter(completer)
    btn = QPushButton()
    btn.setMinimumWidth(95)
    line.addWidget(combo)
    line.addWidget(inp, 1)
    line.addWidget(btn)
    v.addLayout(line)

    checks = QHBoxLayout()
    checks.setSpacing(16)
    chk_debug = QCheckBox()
    chk_debug.setCursor(Qt.PointingHandCursor)
    chk_kill = QCheckBox()
    chk_kill.setCursor(Qt.PointingHandCursor)
    checks.addWidget(chk_debug)
    checks.addWidget(chk_kill)
    checks.addStretch()
    v.addLayout(checks)

    kill_row = QWidget()
    kl = QHBoxLayout(kill_row)
    kl.setContentsMargins(0, 0, 0, 0)
    kill_inp = QLineEdit(app.get("kill", ""))
    badge = QLabel(tr("autostart_kill_label"), kill_inp)
    badge.setObjectName("autostartKillBadge")
    badge.setAlignment(Qt.AlignCenter)
    badge.setAttribute(Qt.WA_TransparentForMouseEvents)
    badge.setStyleSheet(BADGE_CSS)
    place = lambda _e=None: badge.move(5, max(0, (kill_inp.height() - badge.height()) // 2))  # noqa: E731
    kill_inp.resizeEvent = lambda e: (QLineEdit.resizeEvent(kill_inp, e), place())
    kl.addWidget(kill_inp, 1)
    v.addWidget(kill_row)
    place()

    return {"panel": panel, "name_input": name_input, "lbl_name_field": lbl_name,
            "lbl_cmd_field": lbl_cmd, "lbl_icon_field": lbl_icon, "lbl_preview": lbl_preview,
            "btn_icon_fetch": btn_fetch, "btn_icon_pick": btn_pick, "btn_icon_reset": btn_reset,
            "combo": combo, "input": inp, "btn": btn,
            "chk_debug": chk_debug, "chk_kill": chk_kill, "kill_input": kill_inp,
            "kill_row": kill_row, "kill_label": badge, "completer": completer}


def build_row(host, app=None, on_change=None, on_delete=None):
    """Zeile bauen (noch nicht eingehaengt). app: gespeicherte Werte
    {"type", "cmd", "name", "debug", "kill_on", "kill"} oder None."""
    app = app or {}
    on_change = on_change or (lambda *_a: None)

    card = QFrame()
    card.setObjectName("autostartRowCard")
    card.setStyleSheet(CARD_CSS)
    h = QHBoxLayout(card)
    h.setContentsMargins(CARD_MARGIN, 6, CARD_MARGIN, 6)
    h.setSpacing(6)

    lbl_app_icon = QLabel()
    lbl_app_icon.setFixedSize(ROW_ICON, ROW_ICON)
    lbl_name = QLabel()
    badge_debug = QLabel()
    badge_debug.setStyleSheet(DEBUG_BADGE_CSS)
    badge_kill = QLabel()
    badge_kill.setObjectName("autostartKillBadge")
    badge_kill.setStyleSheet(BADGE_CSS)
    btn_settings = QPushButton("⚙")
    btn_settings.setFixedWidth(BUTTON_W)
    btn_settings.setCursor(Qt.PointingHandCursor)
    btn_settings.setStyleSheet(GEAR_CSS)
    btn_del = QPushButton("✕")
    btn_del.setFixedWidth(BUTTON_W)
    btn_del.setCursor(Qt.PointingHandCursor)
    btn_del.setStyleSheet(DEL_CSS)
    h.addWidget(lbl_app_icon)
    h.addWidget(lbl_name, 1)
    for w in (badge_debug, badge_kill, btn_settings, btn_del):
        h.addWidget(w)

    row = _build_panel(host, app, card)
    row.update({"widget": card, "host": host, "lbl_name": lbl_name, "lbl_icon": lbl_app_icon,
                "icon": app.get("icon", ""),
                "badge_debug": badge_debug, "badge_kill": badge_kill,
                "btn_settings": btn_settings, "btn_del": btn_del})
    combo, inp, btn = row["combo"], row["input"], row["btn"]
    chk_debug, chk_kill = row["chk_debug"], row["chk_kill"]
    kill_inp, kill_row = row["kill_input"], row["kill_row"]

    combo.setCurrentText(app.get("type", "Custom Path"))
    apply_saved_mode(row)
    chk_debug.setChecked(bool(app.get("debug", False)))
    chk_kill.setChecked(bool(app.get("kill_on", False)))
    kill_row.setVisible(chk_kill.isChecked())
    retranslate_row(row)

    def changed(*_a):
        refresh_row(row)
        on_change()

    def kill_toggled(on):
        kill_row.setVisible(on)
        if on and not kill_inp.text():
            kill_inp.setFocus()
            QTimer.singleShot(0, lambda: offer_kill_suggestion(row))
        changed()

    def mode_changed(_index):
        host._autostart_mode_changed(combo.mode(), inp, btn)
        changed()

    combo.currentIndexChanged.connect(mode_changed)
    inp.textChanged.connect(changed)
    row["name_input"].textChanged.connect(changed)
    chk_debug.toggled.connect(changed)
    chk_kill.toggled.connect(kill_toggled)
    kill_inp.textChanged.connect(changed)
    kill_inp.focusInEvent = lambda e: (
        QLineEdit.focusInEvent(kill_inp, e),
        QTimer.singleShot(0, lambda: offer_kill_suggestion(row)))
    btn.clicked.connect(lambda _c=False: host._autostart_browse(inp, combo))
    btn_settings.clicked.connect(lambda _c=False: open_row_settings(host, row))

    def pick_icon(_checked=False):
        path, _ = QFileDialog.getOpenFileName(row["panel"], tr("autostart_icon_pick"), "",
                                              tr("autostart_icon_filter"))
        stored = tool_icons.import_file(path) if path else ""
        if stored:
            row["icon"] = stored
            changed()

    def reset_icon(_checked=False):
        row["icon"] = ""
        changed()

    def fetch_icon(_checked=False):
        tool = row_tool(row)
        if tool:
            host.fetch_tool_icon(tool["key"], manual=True)

    row["btn_icon_pick"].clicked.connect(pick_icon)
    row["btn_icon_reset"].clicked.connect(reset_icon)
    row["btn_icon_fetch"].clicked.connect(fetch_icon)
    if on_delete is not None:
        btn_del.clicked.connect(lambda _c=False: on_delete(row))
    return row


def open_row_settings(host, row, focus_command=False):
    """Zahnrad-Fenster: zeigt das Feld-Panel der Zeile, Aenderungen gelten sofort."""
    dialog = QDialog(host)
    dialog.setWindowTitle(row_title(row) or tr("autostart_row_settings_title"))
    v = QVBoxLayout(dialog)
    panel = row["panel"]
    v.addWidget(panel)
    panel.show()
    buttons = QDialogButtonBox(QDialogButtonBox.Close)
    buttons.button(QDialogButtonBox.Close).setText(tr("autostart_row_settings_done"))
    buttons.rejected.connect(dialog.reject)
    v.addWidget(buttons)
    if focus_command:
        row["input"].setFocus()
    dialog.exec()
    panel.hide()
    panel.setParent(row["widget"])


def pick_program(host):
    """Auswahl fuer "+ Programm". Rueckgabe: Zeilenwerte oder None."""
    from PySide6.QtWidgets import QListWidget, QListWidgetItem

    dialog = QDialog(host)
    dialog.setWindowTitle(tr("autostart_apps_title"))
    dialog.setMinimumSize(420, 380)
    v = QVBoxLayout(dialog)
    hint = QLabel(tr("autostart_pick_hint"))
    hint.setWordWrap(True)
    hint.setStyleSheet("color: #7b88a1; font-size: 11px;")
    v.addWidget(hint)

    listw = QListWidget()
    for text, value in ((tr("autostart_pick_custom_cmd"), "custom_cmd"),
                        (tr("autostart_pick_custom_file"), "custom_file")):
        item = QListWidgetItem(text)
        item.setData(Qt.UserRole, value)
        listw.addItem(item)
    tools = host._installed_tool_commands()
    for tool in tools:
        item = QListWidgetItem(tool["name"])
        item.setToolTip(tool["cmd"])
        item.setData(Qt.UserRole, tool["cmd"])
        listw.addItem(item)
    listw.setCurrentRow(2 if tools else 0)
    listw.itemDoubleClicked.connect(lambda _i: dialog.accept())
    v.addWidget(listw)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Cancel).setText(tr("cancel"))
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    v.addWidget(buttons)

    if dialog.exec() != QDialog.Accepted or listw.currentItem() is None:
        return None
    value = listw.currentItem().data(Qt.UserRole)
    if value == "custom_cmd":
        return {"type": "CMD", "cmd": ""}
    if value == "custom_file":
        path, _ = QFileDialog.getOpenFileName(host, tr("dlg_choose_program"), "/usr/bin",
                                              tr("dlg_all_files"))
        return {"type": "Custom Path", "cmd": path} if path else None
    return {"type": "CMD", "cmd": value}


def add_program(host, append):
    """Ablauf von "+ Programm". append(app) legt die Zeile an und gibt sie zurueck."""
    app = pick_program(host)
    if app is None:
        return None
    row = append(app)
    if row is not None and not app["cmd"]:
        open_row_settings(host, row, focus_command=True)
        if not row["input"].text().strip():
            row["btn_del"].click()
            return None
    return row


def row_data(row):
    """Gespeicherte Form einer Zeile. Name und Kill-Felder nur, wenn benutzt —
    alte Profile bleiben dadurch unveraendert gespeichert."""
    data = {"type": row["combo"].currentText(),
            "cmd": row["input"].text(),
            "debug": row["chk_debug"].isChecked()}
    if row["name_input"].text().strip():
        data["name"] = row["name_input"].text().strip()
    if row["icon"]:
        data["icon"] = row["icon"]
    if row["chk_kill"].isChecked() or row["kill_input"].text():
        data["kill_on"] = row["chk_kill"].isChecked()
        data["kill"] = row["kill_input"].text()
    return data
