#!/usr/bin/env python3
"""
core/tabs/controls_setup_mixin.py — Controls einrichten (Einmal-Frage + Installation)
=====================================================================================
Beim ERSTEN Besuch im Controls-Tab fragt die App, welche Werkzeuge sie
installieren soll (ui/controls_setup_dialog.py). Antworten:

  * Installieren      → ausgewaehlte Werkzeuge nacheinander installieren,
                        xrBinder zuletzt bauen/aktivieren; nicht mehr fragen
  * Spaeter           → in dieser Sitzung nicht mehr, beim naechsten Start wieder
  * Nicht mehr fragen → nie wieder (Merker controls_setup_asked)

Kein Konflikt mit der Tour oder der Erst-Einrichtung:
  * Laeuft eine Tour (sie wechselt selbst auf den Controls-Tab), die
    Erst-Einrichtung oder eine Installation, wird NICHT gefragt und auch
    nichts gemerkt — beim naechsten echten Besuch kommt die Frage.
  * Die Frage wartet, bis kein anderes Fenster offen ist; verlaesst der
    Nutzer den Tab vorher, entfaellt sie.
  * „Alles installieren“ in der Tour nutzt denselben Weg (controls_install)
    und gilt als beantwortet.

Ist schon alles installiert und eingeschaltet, kommt keine Frage.
"""
import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import appimage_installer as appimg
import games as games_db
import vr_optimize as vopt
from jsonio import read_json, update_json
from logging_setup import get_logger
from translations import tr

log = get_logger("controls_setup")

KEY_ASKED = "controls_setup_asked"
XRBINDER = "xrbinder"
TOOL_KEYS = ("xr-hotas", "obah")                 # Schalter oben im Controls-Tab
ORDER = (XRBINDER, "obah", "xr-hotas")           # Reihenfolge im Dialog
# Spiele, fuer die XR HOTAS (Schubhebel/Joystick) Sinn ergibt
HOTAS_GAMES = ("elite dangerous", "dcs", "star citizen", "x-plane", "flight simulator",
               "il-2", "war thunder", "ace combat", "no man's sky")
RETRY_MS = 500


class ControlsSetupMixin:

    # ------------------------------------------------------------------ #
    #  Einmal-Frage
    # ------------------------------------------------------------------ #
    def _controls_tab_index(self):
        return self.ui.pages.indexOf(self.ui.tab_controls)

    def _controls_setup_blocked(self):
        """Tour, Erst-Einrichtung oder Installation laufen → jetzt nicht fragen."""
        return (getattr(self, "_tour", None) is not None
                or getattr(self, "_first_run_busy", False)
                or self.installation_running()
                or self.controls_install_running())

    def maybe_offer_controls_setup(self):
        """Aus on_tab_changed (Controls-Tab)."""
        if getattr(self, "_controls_setup_checked", False) or self._controls_setup_asked():
            return
        if self._controls_setup_blocked():
            return                                   # nichts merken
        self._controls_setup_checked = True          # diese Sitzung nur einmal
        QTimer.singleShot(300, self._controls_setup_when_ready)

    def _controls_setup_when_ready(self):
        try:
            on_tab = self.ui.pages.currentIndex() == self._controls_tab_index()
        except RuntimeError:
            return
        if not on_tab or self._controls_setup_blocked():
            self._controls_setup_checked = False     # beim naechsten Besuch wieder
            return
        if not self.isVisible() or QApplication.activeModalWidget() is not None:
            QTimer.singleShot(RETRY_MS, self._controls_setup_when_ready)
            return
        self._offer_controls_setup()

    def _controls_setup_asked(self):
        data = read_json(vopt.APP_CONFIG_FILE, default={})
        return isinstance(data, dict) and bool(data.get(KEY_ASKED))

    def _mark_controls_setup_asked(self):
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        update_json(vopt.APP_CONFIG_FILE, {KEY_ASKED: stamp})

    def _hotas_games_found(self):
        tested, untested, _scanned = games_db.load_cached_games()
        names = [games_db.GAMES.get(a, {}).get("name", "") for a in tested]
        names += [g.get("name", "") for g in untested]
        return any(h in n.lower() for n in names for h in HOTAS_GAMES)

    def controls_setup_items(self):
        """[(key, name, beschreibung, installiert, vorausgewaehlt)]"""
        hotas = self._hotas_games_found()
        items = []
        for key in ORDER:
            if key == XRBINDER:
                name, installed, pre = "xrBinder", self._xrbinder_ready(), True
            elif key in getattr(self.ui, "controls_rows", {}):
                name = self._control_tool(key).get("name", key)
                installed = self._control_installed(key)
                pre = key == "obah" or hotas
            else:
                continue
            items.append((key, name, tr(f"ctlsetup_desc_{key.replace('-', '_')}"),
                          installed, pre))
        return items

    def _offer_controls_setup(self):
        from ui.controls_setup_dialog import INSTALL, NEVER, ControlsSetupDialog
        items = self.controls_setup_items()
        if all(installed for _k, _n, _d, installed, _p in items):
            self._mark_controls_setup_asked()        # alles da — nie fragen
            return
        dlg = ControlsSetupDialog(self, items)
        dlg.exec()
        if dlg.choice == NEVER:
            self._mark_controls_setup_asked()
        elif dlg.choice == INSTALL:
            self._mark_controls_setup_asked()
            self.controls_install(dlg.selected())

    # ------------------------------------------------------------------ #
    #  Installation (auch fuer „Alles installieren“ in der Tour)
    # ------------------------------------------------------------------ #
    def controls_install_running(self):
        return (getattr(self, "_install_all_queue", None) is not None
                or bool(getattr(self, "_controls_pending", set()))
                or bool(getattr(self.ui, "xrbinder_card", None)
                        and self.ui.xrbinder_card.is_building()))

    def controls_install(self, keys):
        """Werkzeuge nacheinander installieren (Standard-Installationsart),
        schon installierte nur einschalten; xrBinder zuletzt bauen/aktivieren."""
        keys = list(keys)
        rows = getattr(self.ui, "controls_rows", {})
        missing = []
        for k in TOOL_KEYS:
            if k not in keys or k not in rows:
                continue
            if self._control_installed(k):
                self._set_control_toggle(k, True)
                self._save_control_state(k, True)
                self._render_control(k, True)
            else:
                missing.append(k)
        self._install_all_xrb = XRBINDER in keys
        self._install_all_queue = missing
        self._install_all_next()

    def _install_all_next(self):
        """Naechstes Werkzeug starten; am Ende xrBinder. Aus on_control_install_finished."""
        queue = getattr(self, "_install_all_queue", None)
        if queue is None:
            return
        while queue:
            key = queue.pop(0)
            tool = self._control_tool(key)
            card = (getattr(self.ui, "tool_cards", {}) or {}).get(key) or {}
            methods = card.get("methods") or appimg.detect_install_methods(tool)
            method = appimg.default_method(methods)
            if not method:
                log.info("[Controls] %s: keine Installationsart.", key)
                continue
            self._set_control_toggle(key, True)
            self._start_control_install(key, method)
            if key in getattr(self, "_controls_pending", set()):
                return                       # laeuft — weiter, wenn fertig
        self._install_all_queue = None
        if getattr(self, "_install_all_xrb", False):
            self._install_all_xrb = False
            self._install_all_xrbinder()

    def _xrbinder_ready(self):
        import xrbinder as xb
        card = getattr(self.ui, "xrbinder_card", None)
        return bool(card is not None and xb.is_built() and card.is_enabled())

    def _install_all_xrbinder(self):
        import xrbinder as xb
        card = getattr(self.ui, "xrbinder_card", None)
        if card is None or self._xrbinder_ready():
            return
        if not xb.is_built() or xb.needs_rebuild():
            card._set_toggle(True)           # nach dem Bau automatisch aktivieren
            card.start_build()
        elif not card.is_enabled():
            card.toggle.setChecked(True)
