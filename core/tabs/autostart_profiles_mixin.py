#!/usr/bin/env python3
"""
core/tabs/autostart_profiles_mixin.py — Autostart-Profile mit Bedingung
=======================================================================
Das Dashboard zeigt nur den festen VR-Autostart (startet, sobald das
Headset verbindet; Logik in main.py). Die Profile haben eine eigene Gruppe
UNTEN im Streaming-Tab — damit das Dashboard nicht ueberladen ist:

  * Schalter „Autostart-Profile aktiv“ — Hauptschalter fuer die Automatik
    (gespeichert als ``autostart_profiles_enabled``, Standard: aus). Aus =
    kein Timer, kein Waechter im Terminal-Modus; die Knoepfe gehen trotzdem.
  * „＋ Neues Profil“ — ein Tab je Profil (Doppelklick benennt um, ✕ loescht).
  * Grosse Knoepfe „▶ Programme starten“ / „■ Programme stoppen“, die sich
    auch im Headset (WayVR-Fenster) gut treffen lassen.

Ein Profil = Ausloeser + Programme:
    „Wenn <VRChat.exe> laeuft UND das Headset verbunden ist, starte nach
     <n> s diese Programme (gestaffelt). Faellt das weg, beende sie wieder.“
Die Regeln selbst stehen Qt-frei in core/autostart_profiles.py — der
Terminal-Modus (core/autostart_runner.py) benutzt dieselben.

Performance
-----------
  * EIN Timer fuer alle Profile, alle 3 s. Er laeuft nur, wenn mindestens
    ein Profil mit Timer an, Ausloeser UND Programm existiert. Gibt es nur
    den VR-Tab, laeuft hier gar nichts.
  * Pro Tick genau ein Blick in /proc (process_watch.snapshot) — kein
    pgrep/ps. Das Headset wird nur geprueft, wenn ein Ausloeser laeuft, und
    auch das ohne Subprozess (/proc/net/tcp).
  * Verzoegerung + Abstand zwischen den Programmen: VRChat laedt erst in
    Ruhe, danach kommt ein Programm nach dem anderen.
  * Ende wird entprellt (2 Ticks ≈ 6 s).

Gespeichert wird in config.json unter ``autostart_profiles``. Beim Wechsel
„Im Terminal starten“ uebernimmt der Terminal-Modus laufende Programme und
die Ueberwachung; startet die Oberflaeche wieder, holt sie beides zurueck.
"""
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QCompleter, QDialog,
                               QDialogButtonBox, QGroupBox, QHBoxLayout, QInputDialog,
                               QTabWidget,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox,
                               QPushButton, QSpinBox, QTabBar, QToolButton,
                               QVBoxLayout, QWidget)

import autostart_profiles as engine
import process_watch
from config_manager import CONFIG_FILE, load_saved_settings
from jsonio import read_json, write_json_atomic
from logging_setup import get_logger
from translations import tr

log = get_logger("autostart_profiles")

PROFILE_KEY = engine.PROFILE_KEY
POLL_MS = int(engine.POLL_S * 1000)
MAX_PROFILES = engine.MAX_PROFILES
MAX_ROWS = engine.MAX_ROWS
NAME_MAX = engine.NAME_MAX
NEW_PROFILE_GAP = 3     # neue Profile starten gestaffelt (s)

# Schnellauswahl im Ausloeser-Feld (tippen geht natuerlich immer).
TRIGGER_SUGGESTIONS = ["VRChat.exe", "vrserver", "steam",
                       "ChilloutVR.exe", "Resonite.exe"]


def load_profiles():
    """Gespeicherte Profile (siehe autostart_profiles.normalize)."""
    return engine.load_profiles()


def save_profiles(profiles):
    """Nur den eigenen Schluessel schreiben, Rest der Config bleibt."""
    current = read_json(CONFIG_FILE, default={})
    if not isinstance(current, dict):
        current = {}
    current[PROFILE_KEY] = profiles
    if not write_json_atomic(CONFIG_FILE, current):
        log.error("Autostart-Profile konnten nicht gespeichert werden.")


def game_trigger(entry):
    """Ausloeser-Text fuer ein Spiel aus dem Games-Tab.

    Anzeige = Spielname, verglichen wird nur der Teil in [ ]:
      * Steam-Spiel   -> ``AppId=<id>`` (Steams „reaper“ traegt das beim
                         Start jedes Spiels in seine Kommandozeile)
      * Nicht-Steam / eigenes Spiel -> Name der Programmdatei
    """
    name = (entry.get("name") or "").strip() or entry.get("id", "")
    kind = entry.get("kind")
    exe = (entry.get("exe") or "").strip()
    if kind == "shortcut" and not exe:
        try:
            import steam_shortcuts
            sc = steam_shortcuts.get(entry.get("id"))
            exe = (sc or {}).get("exe", "") or ""
        except Exception as exc:  # noqa: BLE001 — dann eben per AppId
            log.debug("game_trigger: shortcut %s — %s", entry.get("id"), exc)
    if kind in ("local", "shortcut") and exe:
        key = exe.strip().strip('"').replace("\\", "/").rsplit("/", 1)[-1]
        return f"{name} [{key}]"
    return f"{name} [AppId={entry.get('id')}]"


class AutostartProfilesMixin:
    """Wird von VRApp geerbt. Arbeitet auf self.ui.autostart_tabs."""

    # ------------------------------------------------------------------ #
    #  Aufbau
    # ------------------------------------------------------------------ #
    def setup_autostart_profiles(self):
        self._profiles = []             # je Tab ab Index 1 ein Eintrag
        self._profiles_loading = True

        self._profile_timer = QTimer(self)
        self._profile_timer.setInterval(POLL_MS)
        self._profile_timer.timeout.connect(self._profiles_tick)

        # Speichern gebuendelt: beim Tippen nicht bei jedem Zeichen schreiben.
        self._profile_save_timer = QTimer(self)
        self._profile_save_timer.setSingleShot(True)
        self._profile_save_timer.setInterval(600)
        self._profile_save_timer.timeout.connect(self._profiles_save_now)

        self._build_profiles_group()
        tabs = self.ui.autostart_tabs
        self.ui.btn_autostart_add_profile.clicked.connect(self._profile_add_clicked)
        self.ui.toggle_profiles.toggled.connect(self._profiles_master_toggled)
        tabs.tabBarDoubleClicked.connect(self._profile_rename)

        # Austauschbar fuer Tests. Kein Subprozess (siehe process_watch).
        self._profile_headset = process_watch.headset_connected

        self.ui.toggle_profiles.blockSignals(True)
        self.ui.toggle_profiles.setChecked(engine.master_enabled())
        self.ui.toggle_profiles.sync_offset()
        self.ui.toggle_profiles.blockSignals(False)
        for data in load_profiles():
            self._profile_add(data)
        self._profiles_loading = False
        tabs.setCurrentIndex(0)
        self._profiles_update_empty()
        self._profiles_adopt_from_cli()
        self._profiles_update_timer()
        self._refresh_tab_dots()

    def _build_profiles_group(self):
        """Gruppe „Autostart-Profile“ oben in den Streaming-Tab setzen."""
        from ui.ui_main import ToggleSwitch
        ui = self.ui
        group = QGroupBox(tr("autostart_profiles_group"))
        v = QVBoxLayout(group)

        head = QHBoxLayout()
        ui.toggle_profiles = ToggleSwitch()
        ui.lbl_toggle_profiles = QLabel(tr("autostart_profiles_toggle"))
        ui.lbl_toggle_profiles.setStyleSheet("font-weight:bold;")
        ui.btn_autostart_add_profile = QPushButton(tr("autostart_profile_add_btn"))
        ui.btn_autostart_add_profile.setCursor(Qt.PointingHandCursor)
        ui.btn_autostart_add_profile.setStyleSheet(
            "QPushButton { background-color:#a3be8c; color:#2e3440; border:none;"
            " border-radius:6px; font-weight:bold; font-size:13px; padding:8px 16px; }"
            "QPushButton:hover { background-color:#b8d0a2; }")
        head.addWidget(ui.toggle_profiles)
        head.addWidget(ui.lbl_toggle_profiles)
        head.addStretch()
        head.addWidget(ui.btn_autostart_add_profile)
        v.addLayout(head)

        ui.lbl_profiles_hint = QLabel(tr("autostart_profiles_hint"))
        ui.lbl_profiles_hint.setWordWrap(True)
        ui.lbl_profiles_hint.setStyleSheet("color:#7b88a1; font-size:11px;")
        v.addWidget(ui.lbl_profiles_hint)

        ui.autostart_tabs = QTabWidget()
        ui.autostart_tabs.setMovable(False)   # Index == Profil-Reihenfolge
        ui.autostart_tabs.setDocumentMode(True)
        ui.autostart_tabs.setStyleSheet("""
            QTabWidget::pane { border:none; background:transparent; }
            QStackedWidget, QStackedWidget > QWidget { background:transparent; }
            QTabBar { qproperty-drawBase:0; }
            QTabBar::tab {
                background:#21252b; color:#7b88a1; padding:6px 14px;
                border-radius:6px; margin-right:6px; font-size:12px; font-weight:bold;
            }
            QTabBar::tab:selected { background:#5e81ac; color:white; }
            QTabBar::tab:hover:!selected { background:#2e3440; color:#d8dee9; }
        """)
        v.addWidget(ui.autostart_tabs)
        ui.lbl_profiles_empty = QLabel(tr("autostart_profiles_empty"))
        ui.lbl_profiles_empty.setStyleSheet("color:#7b88a1; font-size:12px; padding:10px 0;")
        v.addWidget(ui.lbl_profiles_empty)
        ui.autostart_profiles_group = group
        # Nicht in die Hoehe ziehen lassen (sonst leerer Streifen unter den Knoepfen).
        from PySide6.QtWidgets import QSizePolicy
        ui.autostart_tabs.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        # UNTEN im Streaming-Tab: Kompatibilitaet, Encoder und Grafikkarte
        # sind dort wichtiger und bleiben oben. Eingefuegt vor dem
        # abschliessenden Stretch des Layouts.
        lay = self.streaming_settings.layout()
        lay.insertWidget(lay.count() - 1, group)

    def _profiles_update_empty(self):
        empty = not self._profiles
        self.ui.autostart_tabs.setVisible(not empty)
        self.ui.lbl_profiles_empty.setVisible(empty)

    def _profiles_master_toggled(self, on):
        """Hauptschalter: Automatik fuer ALLE Profile an/aus."""
        engine.set_master_enabled(bool(on))
        log.info("[Profile] Automatik %s.", "an" if on else "aus")
        self._profiles_update_timer()
        for prof in self._profiles:
            self._profile_render_status(prof)

    def _profile_add_clicked(self):
        if len(self._profiles) >= MAX_PROFILES:
            return
        default = tr("autostart_profile_default_name").format(n=len(self._profiles) + 1)
        name, ok = QInputDialog.getText(self, tr("autostart_profile_new_title"),
                                        tr("autostart_profile_name_lbl"), text=default)
        if not ok:
            return
        name = name.strip()[:NAME_MAX] or default
        self._profile_add({"name": name, "trigger": "", "delay": 0,
                           "gap": NEW_PROFILE_GAP,
                           "stop_with": True, "enabled": True, "apps": [{}]})
        self.ui.autostart_tabs.setCurrentIndex(len(self._profiles) - 1)
        self._profiles_update_empty()
        self._profiles_changed()

    def _profile_add(self, data):
        """Tab + Widgets fuer ein Profil bauen."""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 8, 0, 0)
        v.setSpacing(6)

        # Zeile 1: Ausloeser
        r1 = QHBoxLayout()
        lbl_trigger = QLabel()
        lbl_trigger.setFixedWidth(110)
        inp_trigger = QLineEdit(data.get("trigger", ""))
        comp = QCompleter(TRIGGER_SUGGESTIONS, self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        inp_trigger.setCompleter(comp)
        btn_pick = QPushButton()
        btn_pick.setMinimumWidth(110)
        btn_games = QPushButton()
        btn_games.setMinimumWidth(95)
        r1.addWidget(lbl_trigger)
        r1.addWidget(inp_trigger, 1)
        r1.addWidget(btn_pick)
        r1.addWidget(btn_games)
        v.addLayout(r1)

        # Zeile 2: Verzoegerung + Mit beenden
        r2 = QHBoxLayout()
        lbl_delay = QLabel()
        lbl_delay.setFixedWidth(110)
        spin_delay = QSpinBox()
        spin_delay.setRange(0, 300)
        spin_delay.setSuffix(" s")
        spin_delay.setValue(int(data.get("delay", 0)))
        spin_delay.setFixedWidth(90)
        lbl_gap = QLabel()
        spin_gap = QSpinBox()
        spin_gap.setRange(0, engine.GAP_MAX)
        spin_gap.setSuffix(" s")
        spin_gap.setValue(int(data.get("gap", 0)))
        spin_gap.setFixedWidth(80)
        chk_stop = QCheckBox()
        chk_stop.setChecked(data.get("stop_with", True))
        r2.addWidget(lbl_delay)
        r2.addWidget(spin_delay)
        r2.addSpacing(12)
        r2.addWidget(lbl_gap)
        r2.addWidget(spin_gap)
        r2.addSpacing(12)
        r2.addWidget(chk_stop)
        r2.addStretch()
        # Timer an/aus (gespeichert als "enabled"). Checkable Knopf statt
        # Checkbox: gleiche API (isChecked/toggled), aber als Flaeche.
        chk_enabled = QPushButton()
        chk_enabled.setCheckable(True)
        chk_enabled.setChecked(data.get("enabled", True))
        chk_enabled.setCursor(Qt.PointingHandCursor)
        chk_enabled.setMinimumWidth(135)
        r2.addWidget(chk_enabled)
        v.addLayout(r2)

        # Programme
        rows_box = QVBoxLayout()
        rows_box.setSpacing(4)
        v.addLayout(rows_box)

        # Fusszeile: + Programm, Status
        r3 = QHBoxLayout()
        btn_add_row = QPushButton()
        btn_add_row.setCursor(Qt.PointingHandCursor)
        btn_add_row.setStyleSheet(
            "QPushButton { background-color:#434c5e; color:#eceff4; border:none;"
            " font-weight:bold; border-radius:4px; padding:4px 12px; }"
            "QPushButton:hover { background-color:#5e81ac; }")
        lbl_status = QLabel()
        lbl_status.setStyleSheet("color:#7b88a1; font-size:11px;")
        lbl_status.setWordWrap(True)
        r3.addWidget(btn_add_row)
        r3.addSpacing(10)
        r3.addWidget(lbl_status, 1)
        v.addLayout(r3)

        # Grosse Knoepfe — auch mit dem Controller-Laserpointer in WayVR
        # gut zu treffen.
        r4 = QHBoxLayout()
        r4.setSpacing(10)
        btn_start_now = QPushButton()
        btn_stop_now = QPushButton()
        for b, bg, hover, fg in ((btn_start_now, "#a3be8c", "#b8d0a2", "#2e3440"),
                                 (btn_stop_now, "#bf616a", "#d08770", "#eceff4")):
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(52)
            b.setStyleSheet(
                f"QPushButton {{ background-color:{bg}; color:{fg}; border:none;"
                f" font-weight:bold; font-size:16px; border-radius:8px; padding:8px 18px; }}"
                f"QPushButton:hover {{ background-color:{hover}; }}")
            r4.addWidget(b, 1)
        v.addSpacing(4)
        v.addLayout(r4)
        v.addStretch()

        prof = {
            "name": data.get("name", "Profil"),
            "page": page, "rows_box": rows_box, "rows": [],
            "lbl_trigger": lbl_trigger, "inp_trigger": inp_trigger,
            "btn_pick": btn_pick, "btn_games": btn_games,
            "chk_enabled": chk_enabled, "btn_start_now": btn_start_now,
            "btn_stop_now": btn_stop_now,
            "lbl_delay": lbl_delay, "spin_delay": spin_delay,
            "lbl_gap": lbl_gap, "spin_gap": spin_gap,
            "chk_stop": chk_stop, "btn_add_row": btn_add_row,
            "lbl_status": lbl_status,
            # Laufzeit-Zustand
            "procs": [],
            "ext": [],          # [[pgid, startzeit]] vom Terminal-Modus uebernommen
            "gen": 0,           # zaehlt hoch bei Stop -> offene Staffel-Starts verfallen
            "trigger_seen": False, "headset_ok": False,   # nur fuer die Statuszeile
            **engine.new_state(),   # launched, seen_since, misses, manual
        }
        self._profiles.append(prof)

        for app in data.get("apps") or []:
            self._profile_add_row(prof, app)

        inp_trigger.textChanged.connect(self._profiles_changed)
        # Gleicher Ausloeser: erst nach fertiger Eingabe pruefen, sonst
        # wuerde „VRChat“ beim Tippen von „VRChat.exe“ schon zuschlagen.
        inp_trigger.editingFinished.connect(lambda: self._profile_claim_trigger(prof))
        chk_enabled.toggled.connect(
            lambda on: on and self._profile_claim_trigger(prof))
        chk_enabled.toggled.connect(lambda _on: self._profile_style_timer_btn(prof))
        chk_enabled.toggled.connect(self._profiles_changed)
        btn_games.clicked.connect(lambda: self._profile_pick_game(prof))
        btn_start_now.clicked.connect(lambda: self._profile_start_now(prof))
        btn_stop_now.clicked.connect(lambda: self._profile_stop_now(prof))
        spin_delay.valueChanged.connect(self._profiles_changed)
        spin_gap.valueChanged.connect(self._profiles_changed)
        chk_stop.toggled.connect(self._profiles_changed)
        btn_pick.clicked.connect(lambda: self._profile_pick_running(prof))
        btn_add_row.clicked.connect(lambda: (self._profile_add_row(prof, {}),
                                             self._profiles_changed()))

        tabs = self.ui.autostart_tabs
        idx = tabs.addTab(page, prof["name"])
        tabs.tabBar().setTabToolTip(idx, tr("autostart_profile_tab_tip"))
        # Eigenes ✕ statt Qts Standard-Knopf: der klebte am rechten Rand
        # des abgerundeten Tabs. Rechter Rand = Abstand nach innen.
        btn_close = QToolButton()
        btn_close.setText("✕")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setFixedSize(26, 18)   # 18 sichtbar + 8 Abstand rechts
        btn_close.setToolTip(tr("autostart_profile_delete_title"))
        btn_close.setStyleSheet(
            "QToolButton { background:transparent; color:#d8dee9; border:none;"
            " border-radius:9px; font-weight:bold; font-size:11px; margin-right:8px; }"
            "QToolButton:hover { background:#bf616a; color:white; }")
        btn_close.clicked.connect(
            lambda: self._profile_close_requested(tabs.indexOf(page)))
        tabs.tabBar().setTabButton(idx, QTabBar.RightSide, btn_close)
        prof["btn_close"] = btn_close
        self._profile_retranslate(prof)
        self._profile_render_status(prof)
        return prof

    def _profile_add_row(self, prof, app):
        """Programmzeile — gleiche Bedienung wie im VR-Tab, plus ✕."""
        if len(prof["rows"]) >= MAX_ROWS:
            return
        row_w = QWidget()
        h = QHBoxLayout(row_w)
        h.setContentsMargins(0, 0, 0, 0)
        combo = QComboBox()
        combo.addItems(["Custom Path", "CMD"])
        combo.setFixedWidth(110)
        inp = QLineEdit(app.get("cmd", ""))
        completer = QCompleter(self._autostart_command_pool(), self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        inp.setCompleter(completer)
        btn = QPushButton()
        btn.setMinimumWidth(95)
        chk_debug = QCheckBox("Debug")
        chk_debug.setToolTip(tr("autostart_debug_tip"))
        chk_debug.setFixedWidth(65)
        chk_debug.setStyleSheet("color: #ebcb8b; font-size: 11px;")
        chk_debug.setChecked(bool(app.get("debug", False)))
        btn_del = QPushButton("✕")
        btn_del.setFixedWidth(30)
        btn_del.setToolTip(tr("autostart_profile_row_del_tip"))
        btn_del.setStyleSheet(
            "QPushButton { background-color:#2e3440; color:#bf616a; border:1px solid #4c566a;"
            " font-weight:bold; padding:4px; border-radius:4px; }"
            "QPushButton:hover { background-color:#bf616a; color:white; border-color:#bf616a; }")

        combo.setCurrentText(app.get("type", "Custom Path"))
        for w in (combo, inp, btn, chk_debug, btn_del):
            h.addWidget(w)
        h.setStretch(1, 1)
        prof["rows_box"].addWidget(row_w)

        row = {"widget": row_w, "combo": combo, "input": inp,
               "btn": btn, "chk_debug": chk_debug}
        prof["rows"].append(row)

        combo.currentTextChanged.connect(
            lambda text, le=inp, bb=btn: self._autostart_mode_changed(text, le, bb))
        combo.currentTextChanged.connect(self._profiles_changed)
        inp.textChanged.connect(self._profiles_changed)
        chk_debug.toggled.connect(self._profiles_changed)
        btn.clicked.connect(lambda _c=False, le=inp, cb=combo: self._autostart_browse(le, cb))
        btn_del.clicked.connect(lambda: self._profile_remove_row(prof, row))
        self._autostart_mode_changed(combo.currentText(), inp, btn)

    def _profile_remove_row(self, prof, row):
        try:
            prof["rows"].remove(row)
        except ValueError:
            return
        row["widget"].setParent(None)
        row["widget"].deleteLater()
        self._profiles_changed()

    # ------------------------------------------------------------------ #
    #  Umbenennen / Loeschen
    # ------------------------------------------------------------------ #
    def _profile_rename(self, index):
        if index < 0 or index >= len(self._profiles):
            return
        prof = self._profiles[index]
        name, ok = QInputDialog.getText(self, tr("autostart_profile_rename_title"),
                                        tr("autostart_profile_name_lbl"), text=prof["name"])
        name = name.strip()[:NAME_MAX]
        if not ok or not name:
            return
        prof["name"] = name
        self.ui.autostart_tabs.setTabText(index, name)
        self._profiles_changed()

    def _profile_close_requested(self, index):
        if index < 0 or index >= len(self._profiles):
            return
        prof = self._profiles[index]
        answer = QMessageBox.question(
            self, tr("autostart_profile_delete_title"),
            tr("autostart_profile_delete_q").format(name=prof["name"]))
        if answer != QMessageBox.Yes:
            return
        self._profile_stop(prof)
        self._profiles.pop(index)
        self.ui.autostart_tabs.removeTab(index)
        prof["page"].deleteLater()
        self._profiles_update_empty()
        self._profiles_changed()

    # ------------------------------------------------------------------ #
    #  Laufende Programme zur Auswahl
    # ------------------------------------------------------------------ #
    def _profile_pick_running(self, prof):
        names = process_watch.list_programs()
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("autostart_profile_pick_title"))
        dlg.setMinimumSize(360, 420)
        v = QVBoxLayout(dlg)
        info = QLabel(tr("autostart_profile_pick_hint"))
        info.setWordWrap(True)
        info.setStyleSheet("color: #7b88a1; font-size: 11px;")
        v.addWidget(info)
        flt = QLineEdit()
        flt.setPlaceholderText("🔍")
        v.addWidget(flt)
        listw = QListWidget()
        listw.addItems(names)
        v.addWidget(listw)
        flt.textChanged.connect(lambda t: [
            listw.item(i).setHidden(t.lower() not in listw.item(i).text().lower())
            for i in range(listw.count())])
        listw.itemDoubleClicked.connect(lambda _i: dlg.accept())
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        v.addWidget(buttons)
        if dlg.exec() != QDialog.Accepted:
            return
        item = listw.currentItem()
        if item:
            prof["inp_trigger"].setText(item.text())
            self._profile_claim_trigger(prof)

    def _profile_pick_game(self, prof):
        """Alle Spiele aus dem Games-Tab zur Auswahl — ohne Suchen."""
        import games as games_db
        try:
            entries = games_db.games_tab_entries()
        except Exception as exc:  # noqa: BLE001
            log.warning("[Profile] Spieleliste nicht lesbar: %s", exc)
            entries = []
        if not entries:
            QMessageBox.information(self, tr("autostart_profile_games_title"),
                                    tr("autostart_profile_games_none"))
            return
        entries = sorted(entries, key=lambda e: (e.get("name") or "").lower())

        dlg = QDialog(self)
        dlg.setWindowTitle(tr("autostart_profile_games_title"))
        dlg.setMinimumSize(380, 440)
        v = QVBoxLayout(dlg)
        info = QLabel(tr("autostart_profile_games_hint"))
        info.setWordWrap(True)
        info.setStyleSheet("color: #7b88a1; font-size: 11px;")
        v.addWidget(info)
        flt = QLineEdit()
        flt.setPlaceholderText("🔍")
        v.addWidget(flt)
        listw = QListWidget()
        for e in entries:
            item = QListWidgetItem(e.get("name") or e.get("id", ""))
            item.setData(Qt.UserRole, e)
            listw.addItem(item)
        listw.setCurrentRow(0)
        v.addWidget(listw)
        flt.textChanged.connect(lambda t: [
            listw.item(i).setHidden(t.lower() not in listw.item(i).text().lower())
            for i in range(listw.count())])
        listw.itemDoubleClicked.connect(lambda _i: dlg.accept())
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        v.addWidget(buttons)
        if dlg.exec() != QDialog.Accepted:
            return
        item = listw.currentItem()
        if item:
            prof["inp_trigger"].setText(game_trigger(item.data(Qt.UserRole)))
            self._profile_claim_trigger(prof)

    def _profile_start_now(self, prof):
        """„Programme starten“: sofort, ohne auf den Ausloeser zu warten.

        Laufen schon Programme dieses Profils, werden sie vorher beendet
        (nichts doppelt). Von Hand gestartete Programme beendet der Timer
        NICHT, nur weil der Ausloeser (noch) nicht laeuft — dafuer gibt es
        den Besen-Knopf.
        """
        if not any(r["input"].text().strip() for r in prof["rows"]):
            return
        self._profile_stop(prof)
        self._profile_launch(prof)
        prof["manual"] = True
        prof["launched"] = True
        prof["seen_since"] = None
        prof["misses"] = 0
        self._profile_render_status(prof)
        self._profiles_update_timer()

    # ------------------------------------------------------------------ #
    #  Speichern
    # ------------------------------------------------------------------ #
    def _profile_data(self, prof):
        return {
            "name": prof["name"],
            "trigger": prof["inp_trigger"].text().strip(),
            "delay": prof["spin_delay"].value(),
            "gap": prof["spin_gap"].value(),
            "stop_with": prof["chk_stop"].isChecked(),
            "enabled": prof["chk_enabled"].isChecked(),
            "apps": [{"type": r["combo"].currentText(),
                      "cmd": r["input"].text(),
                      "debug": r["chk_debug"].isChecked()} for r in prof["rows"]],
        }

    def _profiles_changed(self, *_args):
        if getattr(self, "_profiles_loading", False):
            return
        self._profile_save_timer.start()
        self._profiles_update_timer()
        for prof in self._profiles:
            self._profile_render_status(prof)

    def _profiles_save_now(self):
        save_profiles([self._profile_data(p) for p in self._profiles])

    # ------------------------------------------------------------------ #
    #  Ueberwachung
    # ------------------------------------------------------------------ #
    def _profile_armed(self, prof):
        """Hat das Profil alles, was es zum Arbeiten braucht?"""
        return engine.armed(self._profile_data(prof))

    def _profile_claim_trigger(self, prof):
        """Nur EIN aktives Profil pro Ausloeser: ist ``prof`` aktiv, wird der
        Timer aller anderen Profile mit demselben Ausloeser ausgeschaltet
        (wie ein Radio-Knopf). Laufende Programme der anderen werden beendet."""
        if getattr(self, "_profiles_loading", False):
            return
        if not prof["chk_enabled"].isChecked():
            return
        key = engine.trigger_key(prof["inp_trigger"].text())
        if not key:
            return
        for other in self._profiles:
            if other is prof or not other["chk_enabled"].isChecked():
                continue
            if engine.trigger_key(other["inp_trigger"].text()) != key:
                continue
            log.info("[Profile] '%s' aktiviert — Timer von '%s' aus (gleicher Ausloeser).",
                     prof["name"], other["name"])
            other["chk_enabled"].setChecked(False)
            if other["launched"] and not other["manual"]:
                self._profile_stop(other)
                other.update(engine.new_state())
            self._profile_render_status(other)

    def _profile_blocked_by(self, prof):
        """Name des Profils, das denselben Ausloeser schon belegt — sonst None.
        Aktiv: das erste aktive Profil gewinnt. Timer aus: irgendein aktives."""
        profiles = getattr(self, "_profiles", [])
        if prof not in profiles:
            return None
        data = [self._profile_data(p) for p in profiles]
        idx = profiles.index(prof)
        if data[idx]["enabled"]:
            owner = engine.blocked_by(data).get(idx)
            return None if owner is None else profiles[owner]["name"]
        key = engine.trigger_key(data[idx]["trigger"])
        if not key:
            return None
        for p, d in zip(profiles, data):
            if p is not prof and engine.armed(d) and engine.trigger_key(d["trigger"]) == key:
                return p["name"]
        return None

    def _profiles_update_timer(self):
        """Timer nur laufen lassen, wenn es etwas zu beobachten gibt."""
        master = bool(getattr(self.ui, "toggle_profiles", None)
                      and self.ui.toggle_profiles.isChecked())
        needed = master and any(self._profile_armed(p) or (p["launched"] and not p["manual"])
                                for p in getattr(self, "_profiles", []))
        if needed and not self._profile_timer.isActive():
            self._profile_timer.start()
            log.info("[Profile] Ueberwachung an (alle %s s).", POLL_MS // 1000)
            QTimer.singleShot(0, self._profiles_tick)   # nicht erst 3 s warten
        elif not needed and self._profile_timer.isActive():
            self._profile_timer.stop()
            log.info("[Profile] Ueberwachung aus — nichts zu beobachten.")

    def _profiles_tick(self):
        if not self._profiles:
            self._profile_timer.stop()
            return
        names = process_watch.snapshot()        # EIN Blick in /proc fuer alle
        now = time.monotonic()
        headset = {}                            # hoechstens einmal pro Tick

        def headset_ok():
            if "v" not in headset:
                headset["v"] = bool(self._profile_headset())
            return headset["v"]

        for prof in self._profiles:
            self._profile_step(prof, names, now, headset_ok)
            self._profile_render_status(prof)
        self._refresh_tab_dots()
        self._profiles_update_timer()

    def _profile_step(self, prof, names, now, headset_ok=None):
        """Ein Takt fuer ein Profil — Regeln aus autostart_profiles.step()."""
        armed = self._profile_armed(prof) and not self._profile_blocked_by(prof)
        trig = armed and process_watch.matches(prof["inp_trigger"].text(), names)
        # Headset nur fragen, wenn der Ausloeser laeuft (spart die Pruefung).
        head = bool(trig) and (headset_ok() if headset_ok else bool(self._profile_headset()))
        prof["trigger_seen"], prof["headset_ok"] = bool(trig), head

        was_seen = prof["seen_since"]
        action = engine.step(prof, trig and head, prof["spin_delay"].value(),
                             prof["chk_stop"].isChecked(), now)
        if was_seen is None and prof["seen_since"] is not None:
            log.info("[Profile] '%s': Ausloeser + Headset erkannt.", prof["name"])
        if action == "launch":
            self._profile_launch(prof)
        elif action == "stop":
            log.info("[Profile] '%s': Bedingung weg — beende Programme.", prof["name"])
            self._profile_stop(prof)

    def _profile_launch(self, prof):
        """Programme starten — mit Abstand dazwischen, falls eingestellt."""
        prof["procs"] = [p for p in prof["procs"] if p.poll() is None]
        prof["launched"] = True
        rows = [(r["input"].text(), r["chk_debug"].isChecked())
                for r in prof["rows"] if r["input"].text().strip()]
        gap = prof["spin_gap"].value()
        gen = prof["gen"]

        def start_one(cmd, debug):
            if prof["gen"] != gen:
                return                 # inzwischen gestoppt -> verfallen lassen
            p = self._spawn_autostart_cmd(cmd, debug)
            if p is not None:
                prof["procs"].append(p)
            self._profile_render_status(prof)
            self._refresh_tab_dots()

        for i, (cmd, debug) in enumerate(rows):
            if i == 0 or gap <= 0:
                start_one(cmd, debug)
            else:
                QTimer.singleShot(i * gap * 1000, lambda c=cmd, d=debug: start_one(c, d))
        log.info("[Profile] '%s': %s Programm(e) gestartet%s.", prof["name"], len(rows),
                 f" (alle {gap} s eins)" if gap and len(rows) > 1 else "")

    def _profile_stop(self, prof):
        prof["gen"] += 1               # noch ausstehende Staffel-Starts verfallen
        if prof["procs"]:
            self._kill_proc_groups(prof["procs"])
            log.info("[Profile] '%s': Programme beendet.", prof["name"])
        prof["procs"] = []
        if prof["ext"]:
            import exit_guard
            exit_guard.stop_groups([(g, st) for g, st in prof["ext"]])
            prof["ext"] = []
        self._refresh_tab_dots()

    def _profile_alive(self, prof):
        """Wie viele Programme dieses Profils laufen gerade?"""
        n = sum(1 for p in prof["procs"] if p.poll() is None)
        if prof["ext"]:
            import exit_guard
            n += sum(1 for g, _st in prof["ext"] if exit_guard._group_alive(int(g)))
        return n

    # ------------------------------------------------------------------ #
    #  Laufanzeige am Tab (gruener Punkt)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _dot_icon():
        pix = QPixmap(10, 10)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#a3be8c"))
        painter.drawEllipse(1, 1, 8, 8)
        painter.end()
        return QIcon(pix)

    def _refresh_tab_dots(self):
        """Gruener Punkt vor jedem Tab, dessen Programme gerade laufen."""
        tabs = getattr(self.ui, "autostart_tabs", None)
        if tabs is None:
            return
        if not hasattr(self, "_dot"):
            self._dot = self._dot_icon()
            self._no_dot = QIcon()
        states = [self._profile_alive(p) > 0 for p in getattr(self, "_profiles", [])]
        for i, on in enumerate(states):
            if i < tabs.count():
                tabs.setTabIcon(i, self._dot if on else self._no_dot)

    # ------------------------------------------------------------------ #
    #  Terminal-Modus: uebergeben / zuruecknehmen
    # ------------------------------------------------------------------ #
    def _profiles_adopt_from_cli(self):
        """Laufende Profil-Programme + Waechter aus dem Terminal-Modus holen."""
        try:
            import autostart_runner as runner
            runner.stop_profile_watcher()
            state = runner.load_state()
            alive = runner.running_profile_apps(state)
            manual = set(state.get("profile_manual", []))
            for pgid, start, idx in alive:
                if 0 <= idx < len(self._profiles):
                    prof = self._profiles[idx]
                    prof["ext"].append([pgid, start])
                    prof["launched"] = True
                    prof["manual"] = idx in manual
            state["profile_apps"], state["profile_manual"] = [], []
            runner.save_state(state)
            if alive:
                log.info("[Profile] %s Programm(e) vom Terminal-Modus uebernommen.", len(alive))
        except Exception as exc:  # noqa: BLE001 — darf den Start nie stoeren
            log.debug("_profiles_adopt_from_cli: %s", exc)

    def profiles_handoff_to_cli(self, launch_argv, env):
        """„Im Terminal starten“: Programme + Ueberwachung abgeben."""
        import autostart_runner as runner
        import exit_guard
        self._profile_timer.stop()
        if self._profile_save_timer.isActive():
            self._profile_save_timer.stop()
            self._profiles_save_now()
        entries, manual = [], []
        for idx, prof in enumerate(self._profiles):
            prof["gen"] += 1           # ausstehende Staffel-Starts nicht mehr hier
            for p in prof["procs"]:
                if p.poll() is None:
                    entries.append([p.pid, exit_guard.process_starttime(p.pid), idx])
            entries += [[g, st, idx] for g, st in prof["ext"]
                        if exit_guard._group_alive(int(g))]
            if prof["manual"] and prof["launched"]:
                manual.append(idx)
            prof["procs"], prof["ext"] = [], []
        runner.remember_profile_apps(entries, manual)
        runner.arm_profiles(load_saved_settings(), launch_argv, env)

    def _profile_stop_now(self, prof):
        """„■ Programme stoppen“: nur dieses Profil. Wie der Besen: laeuft der
        Ausloeser noch, startet es erst beim naechsten Spielstart wieder."""
        self._profile_stop(prof)
        self._profile_render_status(prof)

    def kill_profile_apps(self):
        """Besen-Button: Programme aller Profile schliessen.

        ``launched`` bleibt gesetzt — sonst wuerden sie beim naechsten Tick
        sofort wieder starten, weil VRChat & Co. ja noch laufen.
        """
        for prof in getattr(self, "_profiles", []):
            self._profile_stop(prof)
            self._profile_render_status(prof)

    def stop_profile_watch(self):
        """Beim Schliessen: nur die Ueberwachung anhalten.

        Die Programme laufen in eigenen Sitzungen weiter (wie beim Wechsel
        in den Terminal-Modus). Wer sie weg haben will: Besen-Button.
        """
        for name in ("_profile_timer", "_profile_save_timer"):
            t = getattr(self, name, None)
            if t is not None:
                if name == "_profile_save_timer" and t.isActive():
                    self._profiles_save_now()   # letzte Aenderung nicht verlieren
                t.stop()

    # ------------------------------------------------------------------ #
    #  Texte
    # ------------------------------------------------------------------ #
    def _profile_render_status(self, prof):
        trig = prof["inp_trigger"].text().strip()
        if prof["manual"] and prof["launched"]:
            text = tr("autostart_profile_status_manual").format(count=self._profile_alive(prof))
        elif not self.ui.toggle_profiles.isChecked():
            text = tr("autostart_profile_status_master_off")
        elif (dup := self._profile_blocked_by(prof)):
            text = tr("autostart_profile_status_dup").format(name=dup)
        elif not prof["chk_enabled"].isChecked():
            text = tr("autostart_profile_status_off")
        elif not trig:
            text = tr("autostart_profile_status_no_trigger")
        elif not any(r["input"].text().strip() for r in prof["rows"]):
            text = tr("autostart_profile_status_no_apps")
        elif prof["launched"]:
            text = tr("autostart_profile_status_running").format(
                trigger=trig, count=self._profile_alive(prof))
        elif prof["seen_since"] is not None:
            left = max(0, int(prof["spin_delay"].value() - (time.monotonic() - prof["seen_since"])))
            text = tr("autostart_profile_status_delay").format(trigger=trig, sec=left)
        elif prof["trigger_seen"] and not prof["headset_ok"]:
            text = tr("autostart_profile_status_headset").format(trigger=trig)
        else:
            text = tr("autostart_profile_status_wait").format(trigger=trig)
        prof["lbl_status"].setText(text)

    def _profile_retranslate(self, prof):
        prof["lbl_trigger"].setText(tr("autostart_profile_trigger_lbl"))
        prof["inp_trigger"].setPlaceholderText(tr("autostart_profile_trigger_ph"))
        prof["btn_pick"].setText(tr("autostart_profile_pick_btn"))
        prof["btn_pick"].setToolTip(tr("autostart_profile_pick_tip"))
        prof["btn_games"].setText(tr("autostart_profile_games_btn"))
        prof["btn_games"].setToolTip(tr("autostart_profile_games_tip"))
        prof["btn_start_now"].setText(tr("autostart_profile_start_now"))
        prof["btn_start_now"].setToolTip(tr("autostart_profile_start_now_tip"))
        prof["btn_stop_now"].setText(tr("autostart_profile_stop_now"))
        prof["btn_stop_now"].setToolTip(tr("autostart_profile_stop_now_tip"))
        self._profile_style_timer_btn(prof)
        prof["lbl_delay"].setText(tr("autostart_profile_delay_lbl"))
        prof["spin_delay"].setToolTip(tr("autostart_profile_delay_tip"))
        prof["lbl_gap"].setText(tr("autostart_profile_gap_lbl"))
        prof["spin_gap"].setToolTip(tr("autostart_profile_gap_tip"))
        prof["lbl_gap"].setToolTip(tr("autostart_profile_gap_tip"))
        prof["chk_stop"].setText(tr("autostart_profile_stop_with"))
        prof["chk_stop"].setToolTip(tr("autostart_profile_stop_with_tip"))
        prof["btn_add_row"].setText(tr("autostart_profile_add_row"))
        for r in prof["rows"]:
            r["chk_debug"].setToolTip(tr("autostart_debug_tip"))
            self._autostart_mode_changed(r["combo"].currentText(), r["input"], r["btn"])
        self._profile_render_status(prof)

    def _profile_style_timer_btn(self, prof):
        """Timer-Flaeche: an = „⏸ Timer stoppen“, aus = „▶ Timer starten“."""
        btn = prof["chk_enabled"]
        if btn.isChecked():
            btn.setText(tr("autostart_profile_timer_stop"))
            css = ("QPushButton { background-color:#434c5e; color:#eceff4; border:none;"
                   " font-weight:bold; border-radius:4px; padding:4px 12px; }"
                   "QPushButton:hover { background-color:#bf616a; }")
        else:
            btn.setText(tr("autostart_profile_timer_start"))
            css = ("QPushButton { background-color:#5e81ac; color:white; border:none;"
                   " font-weight:bold; border-radius:4px; padding:4px 12px; }"
                   "QPushButton:hover { background-color:#81a1c1; }")
        btn.setToolTip(tr("autostart_profile_timer_tip"))
        if btn.styleSheet() != css:
            btn.setStyleSheet(css)

    def autostart_profiles_retranslate(self):
        tabs = self.ui.autostart_tabs
        for prof in getattr(self, "_profiles", []):
            if prof.get("btn_close") is not None:
                prof["btn_close"].setToolTip(tr("autostart_profile_delete_title"))
        ui = self.ui
        ui.autostart_profiles_group.setTitle(tr("autostart_profiles_group"))
        ui.lbl_toggle_profiles.setText(tr("autostart_profiles_toggle"))
        ui.lbl_profiles_hint.setText(tr("autostart_profiles_hint"))
        ui.lbl_profiles_empty.setText(tr("autostart_profiles_empty"))
        ui.btn_autostart_add_profile.setText(tr("autostart_profile_add_btn"))
        ui.btn_autostart_add_profile.setToolTip(tr("autostart_profile_add_tip"))
        for i, prof in enumerate(getattr(self, "_profiles", [])):
            tabs.tabBar().setTabToolTip(i, tr("autostart_profile_tab_tip"))
            self._profile_retranslate(prof)
