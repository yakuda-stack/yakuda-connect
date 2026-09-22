#!/usr/bin/env python3
"""
core/xrbinder_session.py — laufende OpenXR-Spiele und ihr gespeicherter Stand
=============================================================================
Ein Objekt fuer die ganze App (VRApp._xrbinder). Es

  * haelt den IPC-Thread (core/xrbinder_ipc.py), solange xrBinder aktiv ist,
  * kennt die laufenden Spiele und fragt ein neu gestartetes Spiel sofort
    nach seinen Aktionen (gemerkt in ~/.config/yakuda-connect/xrbinder/),
  * speichert Umbelegungen und uebernimmt sie ins laufende Spiel, wenn das
    gefahrlos geht (siehe xrbinder_ipc.reload_is_safe).

Die Oberflaeche (Karte oben im Controls-Tab, Controller-Ansicht im Bereich
„obah & xrBinder“) haengt sich nur an die Signale.
"""
from PySide6.QtCore import QObject, QTimer, Signal

import xrbinder as xb
import xrbinder_ipc as xipc
from logging_setup import get_logger

log = get_logger("xrbinder_session")


def resolve_app_name(display_name, known):
    """Die Antwort auf unsere Anmeldung traegt nur 12 Zeichen. Kennen wir
    schon ein Spiel, das so anfaengt, ist das der volle Name."""
    if len(display_name) >= xb.DISPLAY_NAME_MAX:
        for name in known:
            if name.startswith(display_name) and len(name) > len(display_name):
                return name
    return display_name


class XrBinderSession(QObject):
    games_changed = Signal()            # Spiel gestartet/beendet oder neu bekannt
    state_updated = Signal(str)         # Name: frische Aktionen vom Spiel
    apply_result = Signal(str, str)     # Name, "live" | "restart" | "no_answer" | "offline"
    bus_changed = Signal(bool)          # IPC-Dienst erreichbar?

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ipc = None
        self.running = {}               # pid -> Name
        self.bus_ok = False

    # ------------------------------------------------------------------ #
    #  Lebenszyklus
    # ------------------------------------------------------------------ #
    @property
    def active(self):
        return self._ipc is not None

    def start(self):
        if self._ipc is not None:
            return
        self._ipc = xipc.make_ipc_thread(xb.DEFAULT_PORT)
        self._ipc.apps_changed.connect(self._on_apps)
        self._ipc.dump_ready.connect(self._on_dump)
        self._ipc.apply_done.connect(self._on_apply)
        self._ipc.bus_state.connect(self._on_bus)
        self._ipc.start()

    def stop(self):
        ipc, self._ipc = self._ipc, None
        if ipc is not None:
            ipc.stop()
            if not ipc.wait(3000):
                ipc.terminate()
                ipc.wait(1000)
        if self.running:
            self.running = {}
            self.games_changed.emit()

    # ------------------------------------------------------------------ #
    #  Spiele
    # ------------------------------------------------------------------ #
    def running_names(self):
        return [n for n in self.running.values() if xb.valid_app_name(n)]

    def pid_of(self, name):
        return next((pid for pid, n in self.running.items() if n == name), 0)

    def games(self):
        """Alle Spiele: laufende zuerst, dann die schon bekannten."""
        return list(dict.fromkeys(self.running_names() + xb.known_apps()))

    def request_dump(self, name):
        pid = self.pid_of(name)
        if pid and self._ipc is not None:
            self._ipc.request_dump(pid)
            return True
        return False

    def _on_apps(self, apps):
        known = xb.known_apps()
        before = set(self.running.values())
        self.running = {pid: resolve_app_name(n, known) for pid, n in apps.items()}
        for pid, name in self.running.items():
            if name not in before and xb.valid_app_name(name):
                self._ipc.request_dump(pid)        # frisch gestartet: Aktionen holen
        self.games_changed.emit()

    def _on_dump(self, pid, data):
        name = self.running.get(pid)
        if not name or not xb.valid_app_name(name) or not data.get("actions"):
            return
        # xrizer unter WiVRn: Runtime nennt keine Tasten -> xrizers feste Belegung
        guessed = xb.fill_known_bindings(data)
        state = xb.load_state(name)
        is_new = not state.get("actions")
        state.update(actions=data["actions"], bindings=data["bindings"], sources=data["sources"],
                     bindings_guessed=guessed)
        state.setdefault("mappings", [])
        xb.save_state(name, state)
        if is_new:
            self.games_changed.emit()
        self.state_updated.emit(name)

    def _on_bus(self, ok):
        self.bus_ok = ok
        self.bus_changed.emit(ok)

    # ------------------------------------------------------------------ #
    #  Speichern
    # ------------------------------------------------------------------ #
    def save(self, name, mappings):
        """
        Umbelegungen schreiben (INI + eigener Stand). Laeuft das Spiel, wird
        danach per IPC geprueft und ggf. live uebernommen — das Ergebnis kommt
        als apply_result. Rueckgabe: True, wenn eine Antwort kommt.
        """
        xb.write_app_config(name, mappings)
        state = xb.load_state(name)
        axis_changed = xb.axis_changed(state.get("mappings") or [], mappings)
        state["mappings"] = list(mappings)
        xb.save_state(name, state)
        pid = self.pid_of(name)
        if pid and self._ipc is not None and axis_changed:
            # Achs-Ausdruecke (Kippen, Deadzone) live aendern stuerzt in
            # xrBinder das Spiel ab (siehe core/xrbinder.py, Grenze 3).
            QTimer.singleShot(0, lambda: self.apply_result.emit(name, "restart_axis"))
            return True
        if pid and self._ipc is not None:
            keys = {(m["action"], m.get("hand", "")) for m in mappings}
            keys |= {(m["action"], "") for m in mappings}     # Fach "ohne Hand" (.any)
            self._ipc.request_apply(pid, keys)
            return True
        self.apply_result.emit(name, "offline")
        return False

    def _on_apply(self, pid, result):
        name = self.running.get(pid)
        if name:
            self.apply_result.emit(name, result)
