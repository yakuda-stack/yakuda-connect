#!/usr/bin/env python3
"""
core/tabs/controls_mixin.py — Controls-Tab
==========================================
Je Werkzeug ein Schalter (XR HOTAS, obah). Wird er eingeschaltet:

  1. Ist das Tool installiert?  -> Schalter bleibt an, fertig.
  2. Nicht installiert          -> Rueckfrage: WIE installieren?
                                   (Methoden wie im Tools-Tab: Cargo, yay, ...)
  3. Gewaehlte Methode          -> die Installation des Tools-Tabs laeuft,
                                   mit demselben sichtbaren Terminal.
  4. Ergebnis                   -> Erfolg: Schalter bleibt an.
                                   Fehler/Abbruch: Schalter geht wieder aus.

Es gibt bewusst KEINEN eigenen Installationsweg: alles laeuft ueber
ToolsTabMixin.install_tool(). So sieht die Tool-Karte im Tools-Tab denselben
Stand, und Fehlerbehandlung/Update/Loeschen existieren nur einmal.

Der Zustand der Schalter wird in config.json gemerkt (controls_<key>).

Auch das ist ein MIXIN — self.ui und die Worker stammen aus VRApp.
"""
import os
import shutil
import subprocess

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QMessageBox

import obah_bindings as ob
import obah_editor as oe
from translations import get_language

import appimage_installer as appimg
import paths
import xrbinder as xb
from jsonio import read_json, update_json
from translations import tr

from logging_setup import get_logger

log = get_logger("controls_tab")

# Anzeigenamen der Methoden — wie im Methoden-Dropdown des Tools-Tabs.
METHOD_LABELS = {"appimage": "AppImage", "yay": "yay (AUR)", "paru": "paru (AUR)",
                 "flatpak": "Flatpak", "rpm": "RPM (dnf)", "cargo": "Cargo"}


# Kurzerklaerung je Methode in der Rueckfrage. Ausgeschrieben statt
# zusammengesetzt, damit die Schluesselpruefung (tests/smoke.py) sie findet.
METHOD_HINT_KEYS = {
    "cargo": "controls_method_cargo", "yay": "controls_method_yay",
    "paru": "controls_method_paru", "appimage": "controls_method_appimage",
    "flatpak": "controls_method_flatpak", "rpm": "controls_method_rpm",
}


def _config_key(key):
    return "controls_" + key.replace("-", "_")


class ObahGameScanWorker(QThread):
    """Sucht im Hintergrund alle Steam-Spiele mit OpenVR-Action-Manifest.

    Kann bei grossen Bibliotheken einige Sekunden dauern (je Spiel eine
    Ordnersuche, wie in obah) — deshalb nicht im UI-Thread.
    """
    result = Signal(list)

    def __init__(self):
        super().__init__()
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            games = ob.list_games(cancelled=lambda: self._cancel)
        except Exception as exc:  # noqa: BLE001 — leere Liste statt Absturz
            log.warning("obah-Spielesuche fehlgeschlagen: %s", exc)
            games = []
        self.result.emit(games)


# Beschriftung der Bindings-Quellen (Schritt 3)
SOURCE_LABEL_KEYS = {
    ob.SOURCE_DEFAULT: "obah_source_default",
    ob.SOURCE_XRIZER: "obah_source_xrizer",
    ob.SOURCE_VAPOR: "obah_source_vapor",
    ob.SOURCE_OPENCOMPOSITE: "obah_source_opencomposite",
    ob.SOURCE_SCRATCH: "obah_source_scratch",
}
# Voreinstellung beim ersten Oeffnen (solange der Nutzer nichts anderes waehlt)
PREFERRED_GAME = "vrchat"
PREFERRED_CONTROLLER = "oculus_touch"
PREFERRED_SOURCE = ob.SOURCE_XRIZER

# Beschriftungen in der Bindings-Ansicht. SteamVR sagt "Use as ...";
# die Eingabenamen sind die aus der Binding-Datei.
MODE_TEXTS = {
    "de": {"button": "Als Knopf", "toggle_button": "Als Umschalt-Knopf",
           "trigger": "Als Trigger", "joystick": "Als Joystick", "trackpad": "Als Trackpad",
           "dpad": "Als Steuerkreuz (D-Pad)", "grab": "Als Greifen", "scroll": "Als Scrollen",
           "scalar_constant": "Als Konstante"},
    "en": {"button": "Use as button", "toggle_button": "Use as toggle button",
           "trigger": "Use as trigger", "joystick": "Use as joystick", "trackpad": "Use as trackpad",
           "dpad": "Use as D-pad", "grab": "Use as grab", "scroll": "Use as scroll",
           "scalar_constant": "Use as constant"},
}
INPUT_TEXTS = {
    "de": {"click": "Klick", "touch": "Berührung", "pull": "Ziehen", "position": "Position",
           "value": "Wert", "force": "Kraft", "grab": "Greifen", "toggle": "Umschalten",
           "north": "Oben", "south": "Unten", "east": "Rechts", "west": "Links",
           "center": "Mitte", "x": "X", "y": "Y"},
    "en": {"click": "Click", "touch": "Touch", "pull": "Pull", "position": "Position",
           "value": "Value", "force": "Force", "grab": "Grab", "toggle": "Toggle",
           "north": "North", "south": "South", "east": "East", "west": "West",
           "center": "Center", "x": "X", "y": "Y"},
}

# Kurzname im Controller-Dropdown ("✓ Default, xrizer")
SOURCE_SHORT = {ob.SOURCE_DEFAULT: "Default", ob.SOURCE_XRIZER: "xrizer",
                ob.SOURCE_VAPOR: "VapoR", ob.SOURCE_OPENCOMPOSITE: "OpenComposite"}


class ControlsTabMixin:
    """Alles rund um den Controls-Tab. Wird von VRApp geerbt."""

    # ------------------------------------------------------------------ #
    #  Aufbau
    # ------------------------------------------------------------------ #
    def setup_controls_tab_logic(self):
        """Signale verbinden und gemerkten Zustand wiederherstellen.

        Muss NACH dem Tools-Tab laufen: die Installation benutzt dessen
        Karten (Methoden-Dropdown, Worker, Statusanzeige).
        """
        self._controls_pending = set()   # Keys, deren Installation gerade laeuft
        saved = read_json(paths.config_file("config.json"), default={})
        if not isinstance(saved, dict):
            saved = {}

        for key, row in self.ui.controls_rows.items():
            row["toggle"].toggled.connect(
                lambda checked, k=key: self.on_control_toggled(k, checked))
            row["btn_start"].clicked.connect(
                lambda _=False, k=key: self.start_control_tool(k))

            # Gemerkt 'an' zaehlt nur, wenn das Tool noch da ist — wurde es
            # inzwischen entfernt, startet der Schalter aus (und fragt nicht
            # schon beim Programmstart nach einer Installation).
            want = bool(saved.get(_config_key(key), False))
            installed = self._control_installed(key)
            self._set_control_toggle(key, want and installed)
            if want and not installed:
                self._save_control_state(key, False)
            self._render_control(key, installed)

        self.setup_obah_panel()
        # OpenXR-Spiele (xrBinder): Karte oben + XR-Modus im obah-Bereich
        self.setup_xr_controls()
        # Hinweis „obah/xrBinder fehlt“ im Bereich
        self.ui.obah_notice_rows["obah"]["button"].clicked.connect(self._notice_install_obah)
        self.ui.obah_notice_rows["xrbinder"]["button"].clicked.connect(
            self.ui.xrbinder_card.request_on)
        self.ui.xrbinder_card.rendered.connect(self.update_controls_notice)
        self.update_controls_notice()

    # ------------------------------------------------------------------ #
    #  Einklappbarer Bereich „Controls per obah“
    # ------------------------------------------------------------------ #
    def setup_obah_panel(self):
        ui = self.ui
        self._obah_games = []          # [ObahGame]
        self._obah_bindings = None     # GameBindings des gewaehlten Spiels
        self._obah_scan_worker = None
        self._obah_scanned = False
        self._obah_edit = None
        self._obah_first_open = True
        self._obah_user_controller = PREFERRED_CONTROLLER
        self._obah_user_source = None
        self._obah_manifest_cache = {}
        self._obah_editor_ready = False    # Editor hat Daten (unabhaengig vom Zuklappen)
        ui.btn_obah_expand.toggled.connect(self.on_obah_panel_toggled)
        ui.btn_obah_aux_expand.toggled.connect(self.on_obah_aux_toggled)
        ui.obah_set_tabs.currentChanged.connect(lambda _i: self._render_obah_views())
        self._obah_dirty = False
        for side, view in (("left", ui.obah_view_left), ("right", ui.obah_view_right)):
            view.card_clicked.connect(lambda path, v=view: self.open_obah_binding_dialog(v, path))
            view.layout_changed.connect(lambda state, v=view: self._save_obah_layout(v, state))
            view.tidy_changed.connect(lambda _t: self._sync_obah_tidy_button())
        ui.btn_obah_tidy.toggled.connect(self.on_obah_tidy_toggled)
        ui.btn_obah_save.clicked.connect(lambda: self.save_obah_binding(None))
        for kind, key in (("xrizer", "obah_save_xrizer"), ("vapor", "obah_save_vapor"),
                          ("opencomposite", "obah_save_opencomposite")):
            act = ui.menu_obah_save.addAction(tr(key))
            act.setData(kind)
            act.triggered.connect(lambda _=False, k=kind: self.save_obah_binding(k))
        ui.btn_obah_discard.clicked.connect(self.discard_obah_changes)
        ui.btn_obah_layout_reset.clicked.connect(self.reset_obah_layout)
        ui.btn_obah_profile_save.clicked.connect(self.save_obah_profile)
        ui.btn_obah_profile_load.clicked.connect(self.load_obah_profile)
        ui.btn_obah_profile_delete.clicked.connect(self.delete_obah_profile)
        ui.combo_obah_profile.currentIndexChanged.connect(self._update_obah_profile_buttons)
        self._fill_obah_profiles()
        ui.btn_obah_refresh.clicked.connect(self.start_obah_game_scan)
        ui.btn_obah_pick_manifest.clicked.connect(self.pick_obah_manifest)
        ui.btn_obah_clear_manifest.clicked.connect(self.clear_obah_manifest)
        ui.combo_obah_game.currentIndexChanged.connect(self._on_obah_game_changed)
        ui.combo_obah_controller.currentIndexChanged.connect(self._on_obah_controller_changed)
        ui.combo_obah_source.currentIndexChanged.connect(self._on_obah_source_picked)

    # ------------------------------------------------------------------ #
    #  Aufgeraeumter Modus (nur die Namen der Tasten)
    # ------------------------------------------------------------------ #
    def _obah_visible_views(self):
        """Die Ansichten, die gerade gezeigt werden (rechts fehlt bei Gamepad)."""
        ui = self.ui
        views = [ui.obah_view_left]
        if ui.obah_view_right.isVisibleTo(ui.obah_editor):
            views.append(ui.obah_view_right)
        return views

    def on_obah_tidy_toggled(self, tidy):
        """Knopf gedrueckt: beide Haende auf einmal zu- oder aufklappen."""
        for view in self._obah_visible_views():
            # notify=False: sonst meldet jede Ansicht ihren Zwischenstand
            # zurueck und stellt den Knopf mitten im Umschalten wieder um.
            view.set_tidy(tidy, notify=False)
            self._save_obah_layout(view, view.layout_state())
        self.ui.obah_hands.relayout()

    def _sync_obah_tidy_button(self):
        """
        Knopf an den Karten ausrichten.

        Wer per Rechtsklick die letzte Karte versteckt, hat aufgeraeumt —
        dann rastet der Knopf von selbst ein. Holt er eine wieder hervor,
        springt er wieder heraus.
        """
        btn = self.ui.btn_obah_tidy
        views = self._obah_visible_views()
        tidy = bool(views) and all(v.is_tidy() for v in views)
        if btn.isChecked() != tidy:
            btn.blockSignals(True)
            btn.setChecked(tidy)
            btn.blockSignals(False)
        self.ui.obah_hands.relayout()

    def _show_obah_editor(self, ready):
        """
        Editor zeigen oder verstecken.

        ``ready`` sagt, ob es ueberhaupt etwas zu zeigen gibt. Zugeklappt
        bleibt trotzdem alles geladen — Auswahl, Aenderungen und der
        Speichern-Zustand ueberleben das Zuklappen, es wird nur nichts
        angezeigt.
        """
        self._obah_editor_ready = bool(ready)
        self.ui.obah_editor.setVisible(
            bool(ready) and self.ui.btn_obah_expand.isChecked())

    def on_obah_panel_toggled(self, expanded):
        ui = self.ui
        ui.obah_body.setVisible(expanded)
        ui.btn_obah_refresh.setVisible(expanded)
        # Alles darunter (Action Sets, beide Controller, die unteren Kaesten)
        # geht mit zu — sonst steht die halbe Seite offen, obwohl der Bereich
        # eingeklappt ist.
        ui.obah_editor.setVisible(expanded and getattr(self, "_obah_editor_ready", False))
        ui.btn_obah_expand.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        # Erst beim ersten Aufklappen suchen: wer den Bereich nie oeffnet,
        # soll nicht bei jedem Start die ganze Bibliothek durchsuchen lassen.
        if expanded and not self._obah_scanned:
            self.start_obah_game_scan()

    def on_obah_aux_toggled(self, expanded):
        """Unterer Abschnitt (Posen/Vibration/Chords) auf oder zu."""
        ui = self.ui
        ui.obah_aux_body.setVisible(expanded)
        ui.btn_obah_aux_expand.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)

    def start_obah_game_scan(self):
        worker = self._obah_scan_worker
        if worker is not None and worker.isRunning():
            return
        ui = self.ui
        ui.btn_obah_refresh.setEnabled(False)
        for combo in (ui.combo_obah_game, ui.combo_obah_controller, ui.combo_obah_source):
            combo.blockSignals(True)
            combo.clear()
            combo.setEnabled(False)
            combo.blockSignals(False)
        ui.combo_obah_game.addItem(tr("obah_scanning"))
        ui.lbl_obah_hint.setText("")
        self._obah_scan_worker = ObahGameScanWorker()
        self._obah_scan_worker.result.connect(self._on_obah_games_found)
        self._obah_scan_worker.start()

    def _on_obah_games_found(self, games):
        ui = self.ui
        self._obah_scanned = True
        # Reihenfolge: OpenVR-Spiele mit Action-Datei, dann OpenXR-Spiele
        # (xrBinder, eingefuegt von xr_append_games), ganz unten die ohne
        # Action-Datei (grau). Die obah-Eintraege stehen im Dropdown in genau
        # dieser Reihenfolge (Schluessel koennen doppelt sein, deshalb zaehlt
        # die Position — siehe _obah_combo_index).
        self._obah_games = sorted(games, key=lambda g: not g.has_manifest)
        ui.btn_obah_refresh.setEnabled(True)
        previous = getattr(self, "_obah_last_game", None)

        combo = ui.combo_obah_game
        combo.blockSignals(True)
        combo.clear()
        if not games and not self.xr_game_names():
            self._update_manifest_buttons(None)
            combo.addItem(tr("obah_no_games"))
            combo.setEnabled(False)
            combo.blockSignals(False)
            ui.lbl_obah_hint.setText(tr("obah_no_games_hint"))
            self._obah_bindings = None
            self._fill_obah_controllers()
            return
        for g in self._obah_games:
            combo.addItem(self._game_label(g), g.key)
            i = combo.count() - 1
            tip = g.actions_json or g.game_folder or tr("obah_no_folder")
            if not g.has_manifest:
                # grau wie Controller ohne Bindings — waehlbar, aber mit Hinweis
                combo.setItemData(i, QColor("#7b88a1"), Qt.ForegroundRole)
            combo.setItemData(i, tip, Qt.ToolTipRole)
        self.xr_append_games(combo)
        combo.setEnabled(True)
        idx = combo.findData(previous) if previous else -1
        if idx < 0:
            # Voreinstellung: VRChat, wenn installiert — sonst das erste
            # Spiel, das sich auch bearbeiten laesst
            j = next((j for j, g in enumerate(self._obah_games)
                      if g.name.strip().lower() == PREFERRED_GAME and g.has_manifest), -1)
            idx = self._obah_combo_index(j)
        if idx < 0:
            j = next((j for j, g in enumerate(self._obah_games) if g.has_manifest), 0)
            idx = max(0, self._obah_combo_index(j))
        combo.setCurrentIndex(idx)
        combo.blockSignals(False)
        self._on_obah_game_changed(combo.currentIndex())

    def _current_obah_game(self):
        combo = self.ui.combo_obah_game
        idx = combo.currentIndex()
        if idx < 0 or not combo.isEnabled() or self._is_xr_item(idx):
            return None
        n = sum(1 for i in range(idx) if not self._is_xr_item(i))
        return self._obah_games[n] if n < len(self._obah_games) else None

    def _is_xr_item(self, i):
        data = self.ui.combo_obah_game.itemData(i)
        return isinstance(data, str) and data.startswith("xr:")

    def _obah_combo_index(self, j):
        """Dropdown-Zeile des j-ten obah-Spiels (OpenXR-Eintraege uebersprungen)."""
        if j < 0:
            return -1
        n = -1
        for i in range(self.ui.combo_obah_game.count()):
            if not self._is_xr_item(i):
                n += 1
                if n == j:
                    return i
        return -1

    def _on_obah_game_changed(self, _index):
        if self.xr_on_game_changed():
            return
        game = self._current_obah_game()
        self._obah_last_game = game.key if game else None
        self._update_manifest_buttons(game)
        if game is not None and not game.has_manifest:
            # Spiel aus dem Games-Tab ohne OpenVR-Action-Datei: steht in der
            # Liste, aber ohne Aktionen gibt es nichts zu belegen.
            self._obah_bindings = None
            self._fill_obah_controllers()
            self.ui.lbl_obah_hint.setText(
                tr("obah_no_manifest_hint").format(
                    folder=self._short_home(game.game_folder) if game.game_folder
                    else tr("obah_no_folder")) + "\n" + tr("xrb_obah_hint_xr"))
            return
        try:
            self._obah_bindings = ob.scan_bindings(game) if game else None
        except Exception as exc:  # noqa: BLE001
            log.warning("obah-Bindings nicht lesbar (%s): %s", game and game.name, exc)
            self._obah_bindings = None
        self._fill_obah_controllers()

    # ------------------------------------------------------------------ #
    #  Action-Datei von Hand waehlen
    # ------------------------------------------------------------------ #
    def _update_manifest_buttons(self, game):
        ui = self.ui
        ui.btn_obah_pick_manifest.setEnabled(game is not None)
        ui.btn_obah_clear_manifest.setVisible(bool(game and game.manual))
        ui.btn_obah_clear_manifest.setEnabled(bool(game and game.manual))

    def pick_obah_manifest(self, path=None):
        """
        Action-Datei fuer das gewaehlte Spiel selbst aussuchen. Gemerkt wird
        sie in controls_manifests.json und gewinnt danach immer.
        path: fuer Tests — sonst oeffnet sich ein Dateidialog.
        """
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        game = self._current_obah_game()
        if game is None:
            return False
        if not path:
            start = ""
            for cand in [os.path.dirname(game.actions_json) if game.actions_json else "",
                         game.game_folder] + ob.prefix_dirs(game.appid):
                if cand and os.path.isdir(cand):
                    start = cand
                    break
            path, _flt = QFileDialog.getOpenFileName(
                self, tr("obah_pick_manifest_title").format(name=game.name),
                start or os.path.expanduser("~"), "JSON (*.json);;* (*)")
            if not path:
                return False
        if not ob.is_action_manifest(path):
            QMessageBox.warning(self, tr("obah_pick_manifest_title").format(name=game.name),
                                tr("obah_pick_manifest_invalid").format(path=path))
            return False
        if not ob.set_manual_manifest(game.ident, path):
            log.warning("Action-Datei nicht gemerkt: %s", path)
        log.info("Action-Datei fuer %s von Hand gesetzt: %s", game.name, path)
        game.actions_json = path
        game.manual = True
        if not game.game_folder:
            game.game_folder = os.path.dirname(path)
        self._refresh_game_item(game)
        self._on_obah_game_changed(self.ui.combo_obah_game.currentIndex())
        return True

    def clear_obah_manifest(self):
        """Von Hand gewaehlte Datei vergessen und neu suchen."""
        game = self._current_obah_game()
        if game is None:
            return
        ob.set_manual_manifest(game.ident, None)
        self._obah_last_game = game.key
        self.start_obah_game_scan()

    def _refresh_game_item(self, game):
        """Dropdown-Eintrag eines Spiels nach Aenderung neu beschriften."""
        combo = self.ui.combo_obah_game
        idx = combo.currentIndex()
        if idx < 0:
            return
        combo.blockSignals(True)
        combo.setItemText(idx, self._game_label(game))
        combo.setItemData(idx, game.key)
        combo.setItemData(idx, None, Qt.ForegroundRole)
        combo.setItemData(idx, game.actions_json, Qt.ToolTipRole)
        combo.blockSignals(False)

    @staticmethod
    def _game_label(game):
        kind_keys = {ob.KIND_SHORTCUT: "obah_game_shortcut", ob.KIND_LOCAL: "obah_game_local"}
        label = game.name
        if game.kind in kind_keys:
            label += "   · " + tr(kind_keys[game.kind])
        if game.manual:
            label += "   · " + tr("obah_manifest_manual")
        elif not game.has_manifest:
            label += "   — " + tr("obah_no_manifest_short")
        return label

    @staticmethod
    def _short_home(path):
        home = os.path.expanduser("~")
        return "~" + path[len(home):] if path.startswith(home) else path

    def _fill_obah_controllers(self, keep_source=False):
        """Schritt 2: alle obah-Profile, mit Haekchen, was es schon gibt.

        Vorauswahl: der Controller, den der Nutzer zuletzt SELBST gewaehlt hat
        (wer Index-Controller hat, will beim Spielwechsel nicht jedes Mal neu
        waehlen) — anfangs Oculus/Meta Touch.
        """
        combo = self.ui.combo_obah_controller
        previous = getattr(self, "_obah_user_controller", None)
        combo.blockSignals(True)
        combo.clear()
        gb = self._obah_bindings
        if gb is None:
            combo.setEnabled(False)
            combo.blockSignals(False)
            self._fill_obah_sources(keep_source)
            return
        first_with_bindings = -1
        for i, ct in enumerate(ob.CONTROLLER_TYPES):
            avail = gb.controllers[ct]
            have = [SOURCE_SHORT[s] for s in avail.sources() if s in SOURCE_SHORT]
            suffix = ("   ✓ " + ", ".join(have)) if have else "   — " + tr("obah_no_bindings")
            combo.addItem(ob.controller_label(ct) + suffix, ct)
            if not have:
                # grau wie in obah, aber waehlbar (Start from scratch geht immer)
                combo.setItemData(i, QColor("#7b88a1"), Qt.ForegroundRole)
            elif first_with_bindings < 0:
                first_with_bindings = i
        combo.setEnabled(True)
        idx = combo.findData(previous) if previous else -1
        if idx < 0:
            idx = max(first_with_bindings, 0)
        combo.setCurrentIndex(idx)
        combo.blockSignals(False)
        self._fill_obah_sources(keep_source)

    def _on_obah_controller_changed(self, _index):
        # Nur hier (echte Nutzeraktion) merken — nicht bei der Vorauswahl.
        self._obah_user_controller = self.ui.combo_obah_controller.currentData()
        self._fill_obah_sources()

    def _fill_obah_sources(self, keep_source=False):
        """Schritt 3: ladbare Bindings in obahs Reihenfolge + 'Start from scratch'.

        Vorauswahl: was der Nutzer selbst gewaehlt hat, sonst xrizer, sonst
        der erste Eintrag (wie obah). Eine AUTOMATISCH getroffene Wahl wird
        nicht mitgenommen — sonst wuerde ein erzwungenes 'Start from scratch'
        (Spiel ohne Bindings) in jedes weitere Spiel mitgeschleppt.
        """
        combo = self.ui.combo_obah_source
        previous = combo.currentData() if keep_source else None
        combo.blockSignals(True)
        combo.clear()
        gb = self._obah_bindings
        ct = self.ui.combo_obah_controller.currentData()
        if gb is None or not ct:
            combo.setEnabled(False)
            combo.blockSignals(False)
            self._on_obah_source_changed(-1)
            return
        for src in gb.controllers[ct].sources():
            combo.addItem(tr(SOURCE_LABEL_KEYS[src]), src)
        combo.setEnabled(True)
        idx = -1
        for want in (previous, self._obah_user_source, PREFERRED_SOURCE):
            if want:
                idx = combo.findData(want)
                if idx >= 0:
                    break
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)
        self._on_obah_source_changed(combo.currentIndex())

    def _on_obah_source_picked(self, index):
        """Nur echte Nutzeraktion (beim Befuellen sind die Signale gesperrt)."""
        self._obah_user_source = self.ui.combo_obah_source.currentData()
        self._on_obah_source_changed(index)

    def _on_obah_source_changed(self, _index):
        self._update_obah_hint()
        self._refresh_obah_editor()

    def _update_obah_hint(self):
        """Hinweiszeile: welche Datei obah laden wuerde."""
        ui = self.ui
        gb = self._obah_bindings
        ct = ui.combo_obah_controller.currentData()
        src = ui.combo_obah_source.currentData()
        if gb is None or not ct or not src:
            if gb is None and self._obah_games:
                ui.lbl_obah_hint.setText("")
            return
        if src == ob.SOURCE_SCRATCH:
            ui.lbl_obah_hint.setText(tr("obah_hint_scratch"))
            return
        home = os.path.expanduser("~")

        def short(p):
            return "~" + p[len(home):] if p.startswith(home) else p

        path = ob.binding_file(gb.game, ct, src)
        if path:
            ui.lbl_obah_hint.setText(tr("obah_hint_file").format(path=short(path)))
        else:
            expected = ob.binding_file(gb.game, ct, src, must_exist=False) or ""
            ui.lbl_obah_hint.setText(tr("obah_hint_missing").format(path=short(expected)))

    # ------------------------------------------------------------------ #
    #  Bindings-Ansicht (Action Sets + beide Controller)
    # ------------------------------------------------------------------ #
    def _obah_manifest(self, path):
        cache = self._obah_manifest_cache
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
        hit = cache.get(path)
        if hit and hit[0] == mtime:
            return hit[1]
        manifest = oe.load_manifest(path)
        cache[path] = (mtime, manifest)
        return manifest

    def _refresh_obah_editor(self):
        """Nach jeder Auswahl-Aenderung: Manifest + Binding laden, Tabs setzen."""
        ui = self.ui
        if getattr(self, "_xr_mode", False):
            self.xr_refresh_editor()
            return
        if getattr(self, "_obah_dirty", False):
            self._ask_save_before_leaving()
        sel = self.obah_selection()
        self._obah_edit = None
        self._set_obah_dirty(False)
        if not sel:
            self._show_obah_editor(False)
            return
        game, ct, src = sel
        lang = get_language()
        try:
            manifest = self._obah_manifest(game.actions_json)
            path = ob.binding_file(game, ct, src)
            binding = oe.load_binding(path)
        except ValueError as exc:
            self._show_obah_editor(True)
            ui.obah_set_tabs.setVisible(False)
            ui.obah_view_left.setVisible(False)
            ui.obah_view_right.setVisible(False)
            ui.lbl_obah_editor_status.setText("⚠ " + str(exc))
            ui.lbl_obah_editor_status.setStyleSheet("color:#bf616a; font-size:11px;")
            return

        self._obah_edit = {"manifest": manifest, "binding": binding, "controller": ct,
                           "lang": lang, "path": path, "game": game, "source": src}
        self._show_obah_editor(True)
        ui.obah_set_tabs.setVisible(True)
        ui.lbl_obah_editor_status.setStyleSheet("color:#7b88a1; font-size:11px;")

        tabs = ui.obah_set_tabs
        prev = tabs.tabData(tabs.currentIndex()) if tabs.count() else None
        tabs.blockSignals(True)
        while tabs.count():
            tabs.removeTab(0)
        for aset in manifest.action_sets:
            i = tabs.addTab(oe.set_label(manifest, aset, lang))
            tabs.setTabData(i, aset.name)
            tabs.setTabToolTip(i, aset.name)
        idx = next((i for i in range(tabs.count()) if tabs.tabData(i) == prev), 0)
        tabs.setCurrentIndex(idx)
        tabs.blockSignals(False)
        self._render_obah_views()

    def _render_obah_views(self):
        if getattr(self, "_xr_mode", False):
            self.xr_render_views()
            return
        ui = self.ui
        edit = getattr(self, "_obah_edit", None)
        if not edit or ui.obah_set_tabs.count() == 0:
            return
        set_name = ui.obah_set_tabs.tabData(ui.obah_set_tabs.currentIndex())
        lang = edit["lang"] if edit["lang"] in MODE_TEXTS else "en"
        base = {"modes": MODE_TEXTS[lang], "inputs": INPUT_TEXTS[lang],
                "unbound": tr("obah_unbound"), "none": "—",
                "menu_show": tr("obah_menu_show"), "menu_hide": tr("obah_menu_hide"),
                "menu_show_all": tr("obah_menu_show_all"),
                "menu_hide_all": tr("obah_menu_hide_all")}
        ct = edit["controller"]
        total = bound = 0
        if oe.is_handed(ct):
            sides = (("left", ui.obah_view_left, "obah_left"),
                     ("right", ui.obah_view_right, "obah_right"))
            ui.obah_view_right.setVisible(True)
        else:
            sides = (("single", ui.obah_view_left, "obah_single"),)
            ui.obah_view_right.setVisible(False)
        ui.obah_view_left.setVisible(True)
        for side, view, title_key in sides:
            views = oe.build_view(edit["manifest"], edit["binding"], ct, set_name, side, lang)
            total += len(views)
            bound += sum(1 for v in views if v.bound)
            view.set_layout(self._load_obah_layout(ct, side))
            view.set_data(ct, side, views, dict(base, title=tr(title_key),
                                                hint=tr("obah_card_hint"),
                                                hint_image=tr("obah_image_hint")))
        if oe.is_handed(ct):
            ui.obah_hands.sync_mirror()
        ui.obah_hands.relayout()
        self._sync_obah_tidy_button()
        ui.btn_obah_layout_reset.setEnabled(
            ui.obah_view_left.has_manual_layout() or ui.obah_view_right.has_manual_layout())

        path = edit["path"]
        if path:
            home = os.path.expanduser("~")
            shown = "~" + path[len(home):] if path.startswith(home) else path
            origin = tr("obah_editor_loaded").format(file=os.path.basename(shown))
        else:
            origin = tr("obah_editor_empty")
        text = f"{origin}  ·  " + tr("obah_editor_count").format(bound=bound, total=total)
        if self._obah_dirty:
            text = "● " + tr("obah_unsaved") + "  ·  " + text
        ui.lbl_obah_editor_status.setText(text)
        ui.lbl_obah_editor_status.setStyleSheet(
            "color:#ebcb8b; font-size:11px;" if self._obah_dirty else "color:#7b88a1; font-size:11px;")
        self._render_obah_aux()
        self._update_obah_save_button()
        self._update_obah_profile_buttons()

    # ------------------------------------------------------------------ #
    #  Posen, Haptik, Skelett und Chords
    # ------------------------------------------------------------------ #
    def _obah_aux_sources(self):
        edit = self._obah_edit
        return oe.aux_sources(edit["controller"], edit["binding"])

    def _clear_rows(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _aux_row_button(self, text, tooltip, handler, dashed=False):
        from PySide6.QtWidgets import QPushButton
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(tooltip)
        if dashed:
            btn.setStyleSheet(
                "QPushButton { background:transparent; color:#88c0d0; border:1px dashed #3b4252;"
                " border-radius:5px; padding:5px 10px; font-size:11px; text-align:left; }"
                "QPushButton:hover { border-color:#88c0d0; background:#232a33; }")
        else:
            btn.setStyleSheet(
                "QPushButton { background:#1c1f26; color:#d8dee9; border:1px solid #2e3440;"
                " border-radius:5px; padding:6px 10px; font-size:12px; text-align:left; }"
                "QPushButton:hover { border-color:#5e81ac; background:#232a33; }")
        btn.clicked.connect(handler)
        return btn

    def _render_obah_aux(self):
        """Beide Listen neu aufbauen (obah: 'Other' und 'Chords')."""
        from ui.binding_dialog import chord_kind_name, path_kind_name

        ui = self.ui
        edit = getattr(self, "_obah_edit", None)
        paths_rows = ui.obah_aux_lists["paths"]["rows"]
        chord_rows = ui.obah_aux_lists["chords"]["rows"]
        self._clear_rows(paths_rows)
        self._clear_rows(chord_rows)
        if not edit or ui.obah_set_tabs.count() == 0:
            return
        set_name = ui.obah_set_tabs.tabData(ui.obah_set_tabs.currentIndex())
        manifest, binding = edit["manifest"], edit["binding"]
        lang = edit["lang"]
        sources, chord_sources = self._obah_aux_sources()
        by_path = {s["path"].lower(): s["name"] for s in sources}
        chord_names = {s["path"].lower(): s["name"] for s in chord_sources}

        empty = True
        for kind in oe.PATH_KINDS:
            for i, draft in enumerate(oe.path_bindings(binding, set_name, kind)):
                empty = False
                src = by_path.get((draft.get("path") or "").lower(), draft.get("path", ""))
                act = oe.localized(manifest, draft.get("output", ""), lang)
                paths_rows.addWidget(self._aux_row_button(
                    f"{path_kind_name(kind)}  ·  {src}  →  {act}",
                    draft.get("path", ""),
                    lambda _=False, k=kind, n=i: self.edit_obah_path_binding(k, n)))
            if oe.can_add_path_binding(manifest, set_name, kind, sources):
                paths_rows.addWidget(self._aux_row_button(
                    "＋  " + tr("obah_aux_add").format(kind=path_kind_name(kind)), "",
                    lambda _=False, k=kind: self.edit_obah_path_binding(k, None), dashed=True))
        if empty and paths_rows.count() == 0:
            paths_rows.addWidget(self._aux_hint(tr("obah_aux_none")))

        chords = oe.chord_bindings(binding, set_name)
        for i, draft in enumerate(chords):
            parts = " + ".join(
                f"{chord_names.get(p.lower(), p)} ({chord_kind_name(k)})"
                for p, k in oe.chord_inputs(draft))
            act = oe.localized(manifest, draft.get("output", ""), lang)
            chord_rows.addWidget(self._aux_row_button(
                f"{parts}  →  {act}", "",
                lambda _=False, n=i: self.edit_obah_chord_binding(n)))
        if chord_sources and oe.action_choices(manifest, set_name, "boolean", "in"):
            chord_rows.addWidget(self._aux_row_button(
                "＋  " + tr("obah_chord_add"), "",
                lambda _=False: self.edit_obah_chord_binding(None), dashed=True))
        elif not chords:
            chord_rows.addWidget(self._aux_hint(tr("obah_chords_none")))

    def _aux_hint(self, text):
        from PySide6.QtWidgets import QLabel
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color:#4c566a; font-size:11px; font-style:italic;")
        return lbl

    def edit_obah_path_binding(self, kind, index):
        """Pose / Vibration / Skelett bearbeiten oder anlegen (index=None)."""
        from ui.binding_dialog import PathBindingDialog

        edit = getattr(self, "_obah_edit", None)
        if not edit:
            return
        ui = self.ui
        set_name = ui.obah_set_tabs.tabData(ui.obah_set_tabs.currentIndex())
        set_label = ui.obah_set_tabs.tabText(ui.obah_set_tabs.currentIndex())
        sources, _chords = self._obah_aux_sources()
        if index is None:
            draft = oe.new_path_draft(edit["manifest"], set_name, kind, sources)
            if draft is None:
                return
        else:
            items = oe.path_bindings(edit["binding"], set_name, kind)
            if not 0 <= index < len(items):
                return
            draft = items[index]
        dlg = PathBindingDialog(self, manifest=edit["manifest"], set_name=set_name,
                                set_label=set_label, kind=kind, sources=sources,
                                draft=draft, is_new=index is None)
        self._obah_open_dialog = dlg
        accepted = dlg.exec() == PathBindingDialog.Accepted
        self._obah_open_dialog = None
        if not accepted:
            return
        if dlg.deleted:
            oe.remove_path_binding(edit["binding"], set_name, kind, index)
        else:
            new = dlg.result_draft()
            if index is not None and new == draft:
                return
            oe.set_path_binding(edit["binding"], set_name, kind, index, new)
        self._set_obah_dirty(True)
        self._render_obah_views()

    def edit_obah_chord_binding(self, index):
        """Chord bearbeiten oder anlegen (index=None)."""
        from ui.binding_dialog import ChordBindingDialog

        edit = getattr(self, "_obah_edit", None)
        if not edit:
            return
        ui = self.ui
        set_name = ui.obah_set_tabs.tabData(ui.obah_set_tabs.currentIndex())
        set_label = ui.obah_set_tabs.tabText(ui.obah_set_tabs.currentIndex())
        _paths, chord_sources = self._obah_aux_sources()
        if index is None:
            draft = oe.new_chord_draft(edit["manifest"], set_name, chord_sources)
            if draft is None:
                return
        else:
            items = oe.chord_bindings(edit["binding"], set_name)
            if not 0 <= index < len(items):
                return
            draft = items[index]
        dlg = ChordBindingDialog(self, manifest=edit["manifest"], set_name=set_name,
                                 set_label=set_label, sources=chord_sources,
                                 draft=draft, is_new=index is None)
        self._obah_open_dialog = dlg
        accepted = dlg.exec() == ChordBindingDialog.Accepted
        self._obah_open_dialog = None
        if not accepted:
            return
        if dlg.deleted:
            oe.remove_chord_binding(edit["binding"], set_name, index)
        else:
            new = dlg.result_draft()
            if index is not None and new == draft:
                return
            oe.set_chord_binding(edit["binding"], set_name, index, new)
        self._set_obah_dirty(True)
        self._render_obah_views()

    # ------------------------------------------------------------------ #
    #  Bearbeiten (Popup) + Speichern
    # ------------------------------------------------------------------ #
    def _obah_side_of(self, view):
        edit = self._obah_edit or {}
        if not oe.is_handed(edit.get("controller", "")):
            return "single"
        return "left" if view is self.ui.obah_view_left else "right"

    def open_obah_binding_dialog(self, view, input_path):
        """Klick auf eine Karte: Bindings dieser Eingabe bearbeiten (wie obah)."""
        from ui.binding_dialog import BindingDialog

        if getattr(self, "_xr_mode", False):
            self.xr_open_dialog(view, input_path)
            return
        edit = getattr(self, "_obah_edit", None)
        if not edit:
            return
        ui = self.ui
        side = self._obah_side_of(view)
        ct = edit["controller"]
        d = next((x for x in oe.inputs_for_side(ct, side) if x.path == input_path), None)
        if d is None:
            return
        set_name = ui.obah_set_tabs.tabData(ui.obah_set_tabs.currentIndex())
        set_label = ui.obah_set_tabs.tabText(ui.obah_set_tabs.currentIndex())
        before = oe.source_drafts(edit["binding"], set_name, d, side)
        dlg = BindingDialog(self, manifest=edit["manifest"], binding=edit["binding"],
                            controller_type=ct, set_name=set_name, set_label=set_label,
                            input_def=d, side=side, drafts=before)
        self._obah_open_dialog = dlg            # fuer Tests erreichbar
        accepted = dlg.exec() == BindingDialog.Accepted
        self._obah_open_dialog = None
        if not accepted or dlg.drafts == before:
            return
        oe.apply_drafts(edit["binding"], set_name, d, side, dlg.drafts)
        self._set_obah_dirty(True)
        self._render_obah_views()

    def _set_obah_dirty(self, dirty):
        self._obah_dirty = bool(dirty)
        self.ui.btn_obah_discard.setEnabled(self._obah_dirty)

    def _obah_save_target_label(self):
        if getattr(self, "_xr_mode", False):
            return "xrBinder"
        return {"xrizer": "xrizer", "vapor": "VapoR",
                "opencomposite": "OpenComposite"}[self._default_save_kind()]

    def _default_save_kind(self):
        """Speicherziel: die geladene Quelle, wenn sie beschreibbar ist, sonst xrizer."""
        src = (self._obah_edit or {}).get("source")
        return src if src in oe.SAVE_KINDS else "xrizer"

    def _update_obah_save_button(self):
        if getattr(self, "_xr_mode", False):
            self.xr_update_save_button()
            return
        for act in self.ui.menu_obah_save.actions():
            act.setEnabled(True)
        kind = self._default_save_kind()
        label = {"xrizer": "xrizer", "vapor": "VapoR", "opencomposite": "OpenComposite"}[kind]
        self.ui.btn_obah_save.setText("💾  " + tr("obah_save_as").format(target=label))
        self.ui.btn_obah_save.setEnabled(bool(self._obah_edit) and self._obah_dirty)

    def save_obah_binding(self, kind=None, edit=None, rescan=True):
        """
        Datei schreiben (obah: save_binding_to). Eine vorhandene Datei wird
        vorher als .bak gesichert. Danach wird die gespeicherte Quelle
        geladen — so sieht man, was jetzt wirklich auf der Platte steht.
        """
        if getattr(self, "_xr_mode", False):
            return self.xr_save()
        edit = edit or self._obah_edit
        if not edit:
            return False
        kind = kind or self._default_save_kind()
        ct = edit["controller"]
        try:
            path = oe.save_path(edit["game"], ct, kind)
            existed = os.path.isfile(path)
            oe.save_binding(edit["binding"], path, ct)
        except (OSError, ValueError) as exc:
            log.warning("Binding nicht gespeichert: %s", exc)
            QMessageBox.warning(self, tr("obah_save_failed_title"),
                                tr("obah_save_failed_text").format(error=exc))
            return False
        log.info("Binding gespeichert: %s", path)
        self._set_obah_dirty(False)
        self._obah_last_saved = path
        if rescan:
            # neue Quelle (z. B. erste xrizer-Datei) in die Dropdowns holen
            self._obah_user_source = kind
            self._on_obah_game_changed(self.ui.combo_obah_game.currentIndex())
            home = os.path.expanduser("~")
            shown = "~" + path[len(home):] if path.startswith(home) else path
            msg = tr("obah_saved").format(path=shown)
            if existed:
                msg += "  " + tr("obah_saved_backup")
            self.ui.lbl_obah_editor_status.setText("✔ " + msg)
            self.ui.lbl_obah_editor_status.setStyleSheet("color:#a3be8c; font-size:11px;")
        return True

    def discard_obah_changes(self):
        if not self._obah_dirty:
            return
        if getattr(self, "_xr_mode", False):
            self.xr_discard()
            return
        self._set_obah_dirty(False)
        self._refresh_obah_editor()

    def confirm_obah_close(self):
        """Beim Schliessen der App mit ungespeicherten Bindings.

        True = weiter schliessen, False = abbrechen (Fenster bleibt offen).
        """
        edit = self._obah_edit
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(tr("obah_unsaved_title"))
        box.setText(tr("obah_close_text"))
        btn_save = box.addButton(tr("obah_unsaved_save").format(
            target=self._obah_save_target_label()), QMessageBox.AcceptRole)
        btn_discard = box.addButton(tr("obah_unsaved_discard"), QMessageBox.DestructiveRole)
        box.addButton(tr("bd_cancel"), QMessageBox.RejectRole)
        box.setDefaultButton(btn_save)
        box.exec()
        clicked = box.clickedButton()
        if clicked is btn_save:
            # Schlaegt das Speichern fehl, bleibt die App offen — sonst waere
            # die Arbeit weg, obwohl der Nutzer "Speichern" gewaehlt hat.
            return bool(edit) and self.save_obah_binding(None, edit=edit, rescan=False)
        if clicked is btn_discard:
            self._set_obah_dirty(False)
            return True
        return False

    def _ask_save_before_leaving(self):
        """Auswahl gewechselt, waehrend es ungespeicherte Aenderungen gibt."""
        edit = self._obah_edit
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(tr("obah_unsaved_title"))
        box.setText(tr("obah_unsaved_text"))
        btn_save = box.addButton(tr("obah_unsaved_save").format(
            target=self._obah_save_target_label()), QMessageBox.AcceptRole)
        box.addButton(tr("obah_unsaved_discard"), QMessageBox.DestructiveRole)
        box.setDefaultButton(btn_save)
        box.exec()
        if box.clickedButton() is btn_save and edit:
            self.save_obah_binding(None, edit=edit, rescan=False)
        self._set_obah_dirty(False)

    # ------------------------------------------------------------------ #
    #  Profile: Anordnung UND Belegung unter eigenem Namen
    # ------------------------------------------------------------------ #
    # Gespeichert wird beides zusammen, weil beides zusammengehoert: die
    # Belegung (was auf Klick, Position, Ziehen liegt) und die Anordnung
    # (Reihenfolge der Karten, Position der Controller). So kann man mehrere
    # Einrichtungen nebeneinander haben und hin- und herschalten, ohne die
    # Dateien der Spiele anzufassen — geschrieben wird erst mit „Speichern“.
    def _obah_profiles_file(self):
        return paths.config_file("controls_profiles.json")

    def _load_obah_profiles(self):
        data = read_json(self._obah_profiles_file(), default={})
        profiles = data.get("profiles") if isinstance(data, dict) else None
        return profiles if isinstance(profiles, dict) else {}

    def _fill_obah_profiles(self, select=None):
        combo = self.ui.combo_obah_profile
        previous = select or combo.currentData()
        profiles = self._load_obah_profiles()
        combo.blockSignals(True)
        combo.clear()
        if not profiles:
            combo.addItem(tr("obah_profile_none"), None)
        for name in sorted(profiles, key=str.lower):
            entry = profiles[name] or {}
            ct = entry.get("controller", "")
            label = f"{name}   ·   {ob.controller_label(ct)}" if ct else name
            combo.addItem(label, name)
        idx = combo.findData(previous) if previous else -1
        combo.setCurrentIndex(max(idx, 0))
        combo.blockSignals(False)
        self._update_obah_profile_buttons()

    def _selected_obah_profile(self):
        return self.ui.combo_obah_profile.currentData()

    def _update_obah_profile_buttons(self, *_args):
        # Beim Aufbau gibt es noch keine Auswahl — dann sind Laden/Speichern aus.
        edit = bool(getattr(self, "_obah_edit", None)) and not getattr(self, "_xr_mode", False)
        has = bool(self._selected_obah_profile())
        self.ui.btn_obah_profile_load.setEnabled(has and edit)
        self.ui.btn_obah_profile_delete.setEnabled(has)
        self.ui.btn_obah_profile_save.setEnabled(edit)

    def _current_obah_layouts(self):
        """Anordnung beider Seiten des aktuellen Controllers."""
        edit = self._obah_edit or {}
        ct = edit.get("controller", "")
        out = {}
        for view in (self.ui.obah_view_left, self.ui.obah_view_right):
            out[f"{ct}:{self._obah_side_of(view)}"] = view.layout_state()
        return out

    def save_obah_profile(self):
        """Aktuelle Belegung + Anordnung unter einem Namen sichern."""
        from PySide6.QtWidgets import QInputDialog

        edit = getattr(self, "_obah_edit", None)
        if not edit or edit.get("xr"):
            return
        profiles = self._load_obah_profiles()
        suggestion = self._selected_obah_profile() or edit["game"].name
        name, ok = QInputDialog.getText(self, tr("obah_profile_save_title"),
                                        tr("obah_profile_save_text"), text=suggestion)
        name = (name or "").strip()
        if not ok or not name:
            return
        if name in profiles:
            reply = QMessageBox.question(
                self, tr("obah_profile_overwrite_title"),
                tr("obah_profile_overwrite_text").format(name=name),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        import copy
        import datetime
        profiles[name] = {
            "saved": datetime.datetime.now().isoformat(timespec="minutes"),
            "controller": edit["controller"],
            "game": edit["game"].name,
            "source": edit.get("source", ""),
            "layout": self._current_obah_layouts(),
            "binding": copy.deepcopy(edit["binding"]),
        }
        if not update_json(self._obah_profiles_file(), {"profiles": profiles}):
            QMessageBox.warning(self, tr("obah_profile_failed_title"),
                                tr("obah_profile_failed_text"))
            return
        log.info("Controls-Profil gespeichert: %s", name)
        self._fill_obah_profiles(select=name)
        self.ui.lbl_obah_editor_status.setText("✔ " + tr("obah_profile_saved").format(name=name))
        self.ui.lbl_obah_editor_status.setStyleSheet("color:#a3be8c; font-size:11px;")

    def load_obah_profile(self):
        """Profil anwenden: Anordnung sofort, Belegung als ungespeicherte Änderung."""
        import copy

        edit = getattr(self, "_obah_edit", None)
        name = self._selected_obah_profile()
        if not edit or not name or edit.get("xr"):
            return
        entry = self._load_obah_profiles().get(name) or {}
        binding = entry.get("binding")
        other = entry.get("controller") and entry["controller"] != edit["controller"]
        if other:
            # Eine Belegung gehoert zu EINEM Controllertyp. Die Anordnung laesst
            # sich trotzdem uebernehmen, die Belegung besser nicht.
            reply = QMessageBox.question(
                self, tr("obah_profile_other_title"),
                tr("obah_profile_other_text").format(
                    profile=ob.controller_label(entry["controller"]),
                    current=ob.controller_label(edit["controller"])),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            binding = None

        for key, state in (entry.get("layout") or {}).items():
            if not isinstance(state, dict):
                continue
            update_json(self._obah_layout_file(), {key: state})
        if binding is not None:
            edit["binding"] = copy.deepcopy(binding)
            self._set_obah_dirty(True)
        self._render_obah_views()
        msg = tr("obah_profile_loaded").format(name=name)
        if binding is None:
            msg += "  " + tr("obah_profile_layout_only")
        self.ui.lbl_obah_editor_status.setText("✔ " + msg)
        self.ui.lbl_obah_editor_status.setStyleSheet("color:#a3be8c; font-size:11px;")

    def delete_obah_profile(self):
        name = self._selected_obah_profile()
        if not name:
            return
        reply = QMessageBox.question(
            self, tr("obah_profile_delete_title"),
            tr("obah_profile_delete_text").format(name=name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        profiles = self._load_obah_profiles()
        profiles.pop(name, None)
        update_json(self._obah_profiles_file(), {"profiles": profiles})
        self._fill_obah_profiles()

    # ------------------------------------------------------------------ #
    #  Eigene Anordnung (Karten + Controller verschoben)
    # ------------------------------------------------------------------ #
    def _obah_layout_file(self):
        return paths.config_file("controls_layout.json")

    def _load_obah_layout(self, controller_type, side):
        data = read_json(self._obah_layout_file(), default={})
        if not isinstance(data, dict):
            return {}
        entry = data.get(f"{controller_type}:{side}")
        return entry if isinstance(entry, dict) else {}

    def _save_obah_layout(self, view, state):
        edit = self._obah_edit or {}
        ct = edit.get("controller")
        if not ct:
            return
        key = f"{ct}:{self._obah_side_of(view)}"
        if not update_json(self._obah_layout_file(), {key: state}):
            log.warning("Controller-Anordnung konnte nicht gespeichert werden.")
        self.ui.btn_obah_layout_reset.setEnabled(True)

    def reset_obah_layout(self):
        """Nur die Anordnung des aktuellen Controllers zuruecksetzen."""
        edit = self._obah_edit or {}
        ct = edit.get("controller")
        if not ct:
            return
        data = read_json(self._obah_layout_file(), default={})
        if isinstance(data, dict):
            changes = {k: None for k in data if k.startswith(ct + ":")}
            if changes:
                update_json(self._obah_layout_file(), changes)
        for view in (self.ui.obah_view_left, self.ui.obah_view_right):
            view.set_layout({})
        self._render_obah_views()

    def obah_selection(self):
        """(ObahGame, controller_type, source) der aktuellen Auswahl oder None."""
        game = self._current_obah_game()
        ct = self.ui.combo_obah_controller.currentData()
        src = self.ui.combo_obah_source.currentData()
        if game and ct and src:
            return game, ct, src
        return None

    def obah_retranslate(self):
        """Nach Sprachwechsel: Dropdown-Texte neu, Auswahl bleibt."""
        self.update_controls_notice()
        if not getattr(self, "_obah_scanned", False):
            return
        if not self._obah_games:
            self._on_obah_games_found([])
            return
        self._fill_obah_controllers(keep_source=True)
        self._refresh_obah_editor()

    def refresh_controls_status(self):
        """Beim Oeffnen des Tabs: Status frisch pruefen (kann sich aussen geaendert haben).

        Beim ersten Oeffnen wird der obah-Bereich aufgeklappt, damit die
        Voreinstellung (VRChat / Touch / xrizer) gleich zu sehen ist.
        """
        if getattr(self, "_obah_first_open", False):
            self._obah_first_open = False
            if not self.ui.btn_obah_expand.isChecked():
                self.ui.btn_obah_expand.setChecked(True)
        for key in self.ui.controls_rows:
            if key in self._controls_pending:
                continue
            installed = self._control_installed(key)
            if not installed and self.ui.controls_rows[key]["toggle"].isChecked():
                self._set_control_toggle(key, False)
                self._save_control_state(key, False)
            self._render_control(key, installed)

    # ------------------------------------------------------------------ #
    #  Hilfen
    # ------------------------------------------------------------------ #
    def _control_tool(self, key):
        card = self.ui.tool_cards.get(key)
        return card.get("tool", {}) if card else {}

    def _control_installed(self, key):
        tool = self._control_tool(key)
        if not tool:
            return False
        try:
            return appimg.installed_locally(tool)
        except Exception as exc:  # noqa: BLE001 — Pruefung darf den Tab nie sprengen
            log.debug("Installationspruefung %s: %s", key, exc)
            return False

    def _set_control_toggle(self, key, checked):
        """Schalter setzen, OHNE on_control_toggled auszuloesen."""
        toggle = self.ui.controls_rows[key]["toggle"]
        toggle.blockSignals(True)
        toggle.setChecked(bool(checked))
        toggle.sync_offset()
        toggle.blockSignals(False)

    def _save_control_state(self, key, on):
        if not update_json(paths.config_file("config.json"), {_config_key(key): bool(on)}):
            log.warning("Controls-Zustand (%s) konnte nicht gespeichert werden.", key)

    def _render_control(self, key, installed, installing=False):
        row = self.ui.controls_rows[key]
        lbl = row["lbl_status"]
        if installing:
            lbl.setText(tr("controls_installing"))
            lbl.setStyleSheet("color: #ebcb8b; font-size: 12px;")
        elif installed:
            lbl.setText(tr("controls_installed"))
            lbl.setStyleSheet("color: #a3be8c; font-size: 12px; font-weight: bold;")
        else:
            lbl.setText(tr("controls_not_installed"))
            lbl.setStyleSheet("color: #7b88a1; font-size: 12px; font-style: italic;")
        row["toggle"].setEnabled(not installing)
        row["btn_start"].setVisible(installed and not installing)
        self.update_controls_notice()

    def update_controls_notice(self):
        """
        Hinweis oben im Bereich „Controls per obah & xrBinder“: fehlt obah
        oder xrBinder, steht dort, was dann nicht geht, mit Knopf zum
        Installieren/Einschalten (gleicher Weg wie der Schalter der Karte).
        """
        ui = self.ui
        rows = getattr(ui, "obah_notice_rows", None)
        if not rows:
            return
        shown = False
        # obah
        if "obah" in ui.controls_rows:
            pending = "obah" in getattr(self, "_controls_pending", set())
            missing = pending or not self._control_installed("obah")
            r = rows["obah"]
            r["row"].setVisible(missing)
            if missing:
                shown = True
                r["label"].setText("⚠  " + tr("notice_obah_missing"))
                r["button"].setText(tr("controls_installing") if pending else tr("notice_install"))
                r["button"].setEnabled(not pending)
        # xrBinder
        card = getattr(ui, "xrbinder_card", None)
        r = rows["xrbinder"]
        if card is None:
            r["row"].setVisible(False)
        else:
            building = card.is_building()
            if building:
                text, btn = "notice_xrb_missing", "xrb_building"
            elif not xb.is_built():
                text, btn = "notice_xrb_missing", "notice_install"
            elif xb.needs_rebuild():
                text, btn = "notice_xrb_rebuild", "xrb_rebuild"
            elif not card.is_enabled():
                text, btn = "notice_xrb_off", "notice_enable"
            else:
                text = btn = None
            r["row"].setVisible(text is not None)
            if text:
                shown = True
                r["label"].setText("⚠  " + tr(text))
                r["button"].setText(tr(btn))
                r["button"].setEnabled(not building)
        ui.obah_notice.setVisible(shown)

    def _notice_install_obah(self):
        toggle = self.ui.controls_rows["obah"]["toggle"]
        if toggle.isChecked() and not self._control_installed("obah"):
            # Schalter steht schon an (z. B. abgebrochene Installation): neu anstossen
            self._set_control_toggle("obah", False)
        toggle.setChecked(True)

    # ------------------------------------------------------------------ #
    #  Schalter
    # ------------------------------------------------------------------ #
    def on_control_toggled(self, key, checked):
        if not checked:
            self._save_control_state(key, False)
            return

        if self._control_installed(key):
            self._save_control_state(key, True)
            self._render_control(key, True)
            return

        # Nicht installiert -> fragen, wie.
        method = self._ask_install_method(key)
        if not method:
            self._set_control_toggle(key, False)
            return
        self._start_control_install(key, method)

    def _ask_install_method(self, key):
        """Rueckfrage mit einem Knopf je verfuegbarer Methode. None = Abbruch."""
        tool = self._control_tool(key)
        card = self.ui.tool_cards.get(key) or {}
        name = tool.get("name", key)
        methods = card.get("methods") or appimg.detect_install_methods(tool)

        if not methods:
            QMessageBox.information(self, tr("controls_install_title").format(name=name),
                                    tr("tools_no_method"))
            return None

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(tr("controls_install_title").format(name=name))
        box.setText(tr("controls_install_text").format(name=name))
        hints = []
        for m in methods:
            hint_key = METHOD_HINT_KEYS.get(m)
            if hint_key:
                hints.append(f"• {METHOD_LABELS.get(m, m)}: {tr(hint_key)}")
        if hints:
            box.setInformativeText("\n".join(hints))
        buttons = {}
        default = appimg.default_method(methods)
        for m in methods:
            btn = box.addButton(METHOD_LABELS.get(m, m), QMessageBox.AcceptRole)
            buttons[btn] = m
            if m == default:
                box.setDefaultButton(btn)
        box.addButton(tr("controls_cancel"), QMessageBox.RejectRole)
        box.exec()
        return buttons.get(box.clickedButton())

    def _start_control_install(self, key, method):
        """Installation ueber den Tools-Tab anstossen (gleicher Weg wie dort)."""
        worker = getattr(self, "tool_worker", None)
        if worker is not None and worker.isRunning():
            QMessageBox.information(self, tr("controls_busy_title"), tr("controls_busy_text"))
            self._set_control_toggle(key, False)
            return

        card = self.ui.tool_cards.get(key)
        if not card:
            self._set_control_toggle(key, False)
            return
        combo = card.get("combo_method")
        if combo is not None:
            idx = combo.findData(method)
            if idx >= 0:
                combo.setCurrentIndex(idx)

        before = worker
        self._controls_pending.add(key)
        self._render_control(key, False, installing=True)
        self.install_tool(key)

        # install_tool kann vorher aussteigen (z. B. Nutzer lehnt die
        # Konfigurations-Warnung ab) — dann laeuft nichts, und der Schalter
        # darf nicht ewig auf "wird installiert" haengen bleiben.
        started = getattr(self, "tool_worker", None)
        if started is before or started is None:
            self._controls_pending.discard(key)
            self._set_control_toggle(key, False)
            self._render_control(key, self._control_installed(key))

    def on_control_install_finished(self, key, success):
        """Vom Tools-Tab aufgerufen, wenn eine Installation fertig ist."""
        if key not in getattr(self, "_controls_pending", set()):
            return
        self._controls_pending.discard(key)
        installed = bool(success) and self._control_installed(key)
        self._set_control_toggle(key, installed)
        self._save_control_state(key, installed)
        self._render_control(key, installed)
        if not installed:
            name = self._control_tool(key).get("name", key)
            QMessageBox.warning(self, tr("controls_failed_title"),
                                tr("controls_failed_text").format(name=name))

    def on_control_tool_status(self, key, status):
        """Vom Tools-Tab bei jeder neuen Statusmeldung (Update-Check, Loeschen)."""
        rows = getattr(self.ui, "controls_rows", {})
        if key not in rows or not status or key in getattr(self, "_controls_pending", set()):
            return
        installed = bool(status.get("appimage_installed") or status.get("pm_installed")
                         or status.get("flatpak_installed") or status.get("cargo_installed"))
        if not installed:
            # Z. B. im Tools-Tab geloescht -> Schalter aus. Aber nur, wenn es
            # auch lokal nicht mehr da ist (von Hand gebaut, im PATH, ...).
            installed = self._control_installed(key)
        if not installed and rows[key]["toggle"].isChecked():
            self._set_control_toggle(key, False)
            self._save_control_state(key, False)
        self._render_control(key, installed)

    # ------------------------------------------------------------------ #
    #  Starten
    # ------------------------------------------------------------------ #
    def start_control_tool(self, key):
        """
        Startet das Tool in einem Terminal. Beides sind Kommandozeilen-
        programme (obah ist eine TUI, XR HOTAS schreibt Log-Meldungen) —
        und wenn etwas schiefgeht, soll man die Meldung lesen koennen.
        """
        from install_worker import find_terminal

        tool = self._control_tool(key)
        cmd = tool.get("start_cmd") or key
        # Die App hat ~/.local/bin bzw. ~/.cargo/bin nicht immer im PATH.
        for cand in (os.path.join(appimg.LOCAL_BIN, cmd),
                     os.path.join(os.path.expanduser("~"), ".cargo", "bin", cmd)):
            if os.access(cand, os.X_OK):
                cmd = cand
                break
        else:
            cmd = shutil.which(cmd) or cmd

        terminal, flags = find_terminal()
        if terminal is None:
            QMessageBox.warning(self, tool.get("name", key), tr("tools_cargo_no_terminal"))
            return
        bash_cmd = (f"'{cmd}'; rc=$?; echo; "
                    f"if [ $rc -ne 0 ]; then echo \"{tr('controls_exit_code')} $rc\"; fi; "
                    f"read -rp \"{tr('controls_press_enter')}\" _")
        try:
            subprocess.Popen([terminal] + list(flags or []) + ["bash", "-c", bash_cmd],
                             start_new_session=True)
        except OSError as exc:
            log.warning("Start von %s fehlgeschlagen: %s", key, exc)
            QMessageBox.warning(self, tool.get("name", key), str(exc))
