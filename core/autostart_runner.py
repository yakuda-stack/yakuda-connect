#!/usr/bin/env python3
"""
core/autostart_runner.py — Autostart fuer den Terminal-Modus (ohne Qt)
====================================================================
Die Oberflaeche wartet mit einem QTimer aufs Headset und startet dann die
Autostart-Programme als ihre Kinder. Im Terminal-Modus gibt es keinen
Prozess, der dauerhaft laeuft — jeder YC-Befehl ist nach einer Sekunde
fertig. Deshalb uebernimmt hier ein kleiner Waechter im Hintergrund:

    YC-wivrn-toggle (an) / YC-autostart-reset
        -> startet den Waechter abgekoppelt (``--cli _autostart-watch``)
    Waechter
        -> prueft 1x pro Sekunde, ob das Headset verbunden ist
        -> startet dann die Programme EINMAL, merkt sich ihre Prozessgruppen
           in einer Zustandsdatei und beendet sich selbst
           (dasselbe Einweg-Verhalten wie der Timer der Oberflaeche)
    YC-killapps / YC-wivrn-toggle (aus)
        -> lesen die Zustandsdatei und beenden die Programme

Zustandsdatei (~/.cache/yakuda-connect/cli-autostart.json):
    {"watcher": [pid, startzeit] | null, "apps": [[pgid, startzeit], ...]}

PID + Startzeit zusammen benennen einen Prozess eindeutig (siehe
exit_guard.process_starttime) — nach einem Neustart vergebene PIDs werden
so nie versehentlich getroffen.
"""
import os
import signal
import subprocess
import time

import exit_guard
import paths
import wivrn_server
from jsonio import read_json, write_json_atomic
from logging_setup import get_logger

log = get_logger("autostart_cli")

STATE_FILE = paths.cache_file("cli-autostart.json")
POLL_S = 1.0


# --------------------------------------------------------------------------- #
#  Headset erkannt?  (dieselben zwei Signale wie VRApp.is_headset_connected)
# --------------------------------------------------------------------------- #
def headset_connected():
    """
    Ist AKTUELL ein Headset mit dem Server verbunden? Nur Live-Signale, die
    beim Trennen wieder verschwinden:
      A) WiVRns virtuelles Audiogeraet "WiVRn" (pactl)
      B) aktive TCP-Verbindung auf Port 9757 (ss)
    """
    try:
        for kind in ("sinks", "sources"):
            res = subprocess.run(["pactl", "list", "short", kind],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 text=True, timeout=2)
            if "wivrn" in res.stdout.lower():
                return True
    except Exception as exc:  # noqa: BLE001
        log.debug("headset_connected (pactl): %s", exc)
    try:
        res = subprocess.run(["ss", "-Htan"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True, timeout=2)
        for line in res.stdout.splitlines():
            if "ESTAB" in line and ":9757" in line:
                return True
    except Exception as exc:  # noqa: BLE001
        log.debug("headset_connected (ss): %s", exc)
    return False


# --------------------------------------------------------------------------- #
#  Konfiguration
# --------------------------------------------------------------------------- #
def configured_apps(settings):
    """
    Die Autostart-Eintraege, die die Oberflaeche auch starten wuerde:
    die ersten ``autostart_count`` Zeilen mit nicht leerem Befehl.
    """
    try:
        count = int(settings.get("autostart_count", 0) or 0)
    except (TypeError, ValueError):
        count = 0
    apps = settings.get("autostart_apps", []) or []
    result = []
    for app in apps[:count]:
        if isinstance(app, dict) and (app.get("cmd") or "").strip():
            result.append({"cmd": app["cmd"].strip(), "debug": bool(app.get("debug"))})
    return result


# --------------------------------------------------------------------------- #
#  Zustand
# --------------------------------------------------------------------------- #
def load_state():
    data = read_json(STATE_FILE, default={})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("watcher", None)
    data.setdefault("apps", [])
    return data


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    write_json_atomic(STATE_FILE, state)


def _entry(pid):
    return [pid, exit_guard.process_starttime(pid)]


def _alive(entry):
    """Laeuft genau DIESER Prozess (PID + Startzeit) noch?"""
    if not entry:
        return False
    pid, start = entry
    now = exit_guard.process_starttime(pid)
    return now is not None and start is not None and now == start


def watcher_running(state=None):
    state = state or load_state()
    return _alive(state.get("watcher"))


def running_apps(state=None):
    """Gruppen der Autostart-Programme, von denen noch etwas lebt."""
    state = state or load_state()
    alive = []
    for pgid, start in state.get("apps", []):
        if exit_guard.group_is_ours(int(pgid), start) and exit_guard._group_alive(int(pgid)):
            alive.append([pgid, start])
    return alive


def remember_apps(pids):
    """Von aussen gestartete Programme (z. B. der Oberflaeche) uebernehmen."""
    state = load_state()
    state["apps"] = running_apps(state) + [_entry(p) for p in pids]
    save_state(state)


# --------------------------------------------------------------------------- #
#  Aktionen
# --------------------------------------------------------------------------- #
def stop_watcher():
    state = load_state()
    if _alive(state.get("watcher")):
        try:
            os.kill(state["watcher"][0], signal.SIGTERM)
        except OSError as exc:
            log.debug("stop_watcher: %s", exc)
    state["watcher"] = None
    save_state(state)


def kill_apps(settings):
    """
    Wie der Besen-Knopf: eigene Kill-Befehle, dann SIGTERM → SIGKILL an die
    Gruppen. Der Waechter bleibt unangetastet. Rueckgabe: Anzahl beendeter
    Programme.
    """
    exit_guard.run_kill_commands(settings.get("custom_kill_commands", []) or [])
    state = load_state()
    groups = running_apps(state)
    exit_guard.stop_groups([(g, s) for g, s in groups])
    state["apps"] = []
    save_state(state)
    log.info("[CLI-Autostart] %s Programm(e) beendet.", len(groups))
    return len(groups)


def arm(settings, launch_argv, env=None):
    """
    Waechter (neu) scharfschalten. ``launch_argv``: Startbefehl des
    Waechters (siehe cli_install.cli_argv). Rueckgabe: "armed" | "no_apps".
    """
    stop_watcher()
    if not configured_apps(settings):
        return "no_apps"
    proc = subprocess.Popen(launch_argv, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True, env=env)
    state = load_state()
    state["watcher"] = _entry(proc.pid)
    save_state(state)
    log.info("[CLI-Autostart] Waechter gestartet (PID %s).", proc.pid)
    return "armed"


def _clean_env():
    """
    Umgebung fuer die Programme: ohne die Zusaetze der AppImage (sonst
    finden fremde Python-Programme das gebundelte PySide6 & Co.).
    """
    env = dict(os.environ)
    appdir = env.get("APPDIR", "")
    if env.get("APPIMAGE"):
        for key in ("PYTHONPATH", "PYTHONHOME", "LD_LIBRARY_PATH"):
            env.pop(key, None)
        if appdir:
            env["PATH"] = ":".join(p for p in env.get("PATH", "").split(":")
                                   if p and not p.startswith(appdir))
    return env


def launch_apps(apps, terminal_command=None):
    """Programme starten wie launch_autostart_apps in main.py. Gibt PIDs zurueck."""
    env = _clean_env()
    pids = []
    for app in apps:
        cmd = app["cmd"]
        try:
            argv = None
            if app.get("debug") and terminal_command:
                argv = terminal_command(["bash", "-c", f"{cmd}; echo ''; "
                                         "echo '[Debug] Prozess beendet.'; read"])
            if argv:
                p = subprocess.Popen(argv, start_new_session=True, env=env)
            else:
                p = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, start_new_session=True,
                                     env=env)
            pids.append(p.pid)
        except Exception as exc:  # noqa: BLE001 — ein Programm darf den Rest nicht stoppen
            log.warning("[CLI-Autostart] Konnte '%s' nicht starten: %s", cmd, exc)
    return pids


def watch(settings, terminal_command=None, _sleep=time.sleep, _connected=headset_connected):
    """
    Der Waechter selbst (laeuft im Hintergrund). Einweg: startet hoechstens
    einmal und beendet sich danach — genau wie der Timer der Oberflaeche.
    """
    apps = configured_apps(settings)
    while True:
        if not wivrn_server.is_running():
            log.info("[CLI-Autostart] Server aus — Waechter beendet sich.")
            break
        if _connected():
            pids = launch_apps(apps, terminal_command)
            state = load_state()
            state["apps"] = running_apps(state) + [_entry(p) for p in pids]
            state["watcher"] = None
            save_state(state)
            log.info("[CLI-Autostart] Headset verbunden — %s Programm(e) gestartet.", len(pids))
            return 0
        _sleep(POLL_S)
    state = load_state()
    state["watcher"] = None
    save_state(state)
    return 0
