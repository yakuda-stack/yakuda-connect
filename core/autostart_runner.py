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
    {"watcher": [pid, startzeit] | null, "apps": [[pgid, startzeit], ...],
     "profile_watcher": [pid, startzeit] | null,
     "profile_apps": [[pgid, startzeit, profil-index], ...],
     "profile_manual": [profil-index, ...]}

Autostart-Profile (Tabs neben „VR“) haben einen EIGENEN Waechter
(``--cli _profile-watch``): der laeuft, solange der Server laeuft, prueft
alle 3 s und startet/beendet nach denselben Regeln wie die Oberflaeche
(core/autostart_profiles.py).

PID + Startzeit zusammen benennen einen Prozess eindeutig (siehe
exit_guard.process_starttime) — nach einem Neustart vergebene PIDs werden
so nie versehentlich getroffen.
"""
import os
import signal
import subprocess
import time

import autostart_profiles as engine
import exit_guard
import paths
import process_watch
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
    data.setdefault("profile_watcher", None)
    data.setdefault("profile_apps", [])
    data.setdefault("profile_manual", [])
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
    # Profil-Programme gehoeren dazu (wie der Besen-Knopf der Oberflaeche).
    # Ihr Waechter bleibt: die Profile gelten als „ausgeloest“ und starten
    # erst wieder, wenn der Ausloeser neu startet.
    groups += [[g, st] for g, st, _i in running_profile_apps(state)]
    exit_guard.stop_groups([(g, s) for g, s in groups])
    state["apps"] = []
    state["profile_apps"] = []
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


# --------------------------------------------------------------------------- #
#  Autostart-Profile im Terminal-Modus
# --------------------------------------------------------------------------- #
def running_profile_apps(state=None):
    """[[pgid, startzeit, profil-index], ...] — nur, was noch lebt."""
    state = state or load_state()
    alive = []
    for entry in state.get("profile_apps", []):
        try:
            pgid, start, idx = entry
        except (TypeError, ValueError):
            continue
        if exit_guard.group_is_ours(int(pgid), start) and exit_guard._group_alive(int(pgid)):
            alive.append([pgid, start, int(idx)])
    return alive


def profile_watcher_running(state=None):
    state = state or load_state()
    return _alive(state.get("profile_watcher"))


def stop_profile_watcher():
    state = load_state()
    if _alive(state.get("profile_watcher")):
        try:
            os.kill(state["profile_watcher"][0], signal.SIGTERM)
        except OSError as exc:
            log.debug("stop_profile_watcher: %s", exc)
    state["profile_watcher"] = None
    save_state(state)


def remember_profile_apps(entries, manual=()):
    """Von der Oberflaeche uebergebene Profil-Programme merken."""
    state = load_state()
    state["profile_apps"] = running_profile_apps(state) + [list(e) for e in entries]
    state["profile_manual"] = sorted(set(state.get("profile_manual", [])) | set(manual))
    save_state(state)


def arm_profiles(settings, launch_argv, env=None):
    """Profil-Waechter (neu) starten. Rueckgabe: "armed" | "no_profiles"."""
    stop_profile_watcher()
    profiles = engine.load_profiles(settings)
    # Hauptschalter aus (Streaming-Tab): keine Automatik, kein Waechter.
    # Uebergebene Programme bleiben in der Zustandsdatei (YC-killapps).
    if not engine.master_enabled(settings):
        return "no_profiles"
    if not any(engine.armed(p) for p in profiles) and not running_profile_apps():
        return "no_profiles"
    proc = subprocess.Popen(launch_argv, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True, env=env)
    state = load_state()
    state["profile_watcher"] = _entry(proc.pid)
    save_state(state)
    log.info("[CLI-Profile] Waechter gestartet (PID %s).", proc.pid)
    return "armed"


def profile_watch(settings, terminal_command=None, _sleep=time.sleep, _now=time.monotonic,
                  _snapshot=process_watch.snapshot, _headset=process_watch.headset_connected,
                  _server_running=wivrn_server.is_running, _max_ticks=None):
    """
    Der Profil-Waechter (laeuft im Hintergrund, solange der Server laeuft).
    Gleiche Regeln wie die Oberflaeche: autostart_profiles.step().
    """
    profiles = engine.load_profiles(settings)
    if not engine.master_enabled(settings):
        profiles = []          # Automatik aus -> nichts tun (Schleife endet gleich)
    states = [engine.new_state() for _ in profiles]
    groups = {i: [] for i in range(len(profiles))}      # idx -> [[pgid, start]]
    pending = []                                        # [(faellig, idx, app)]

    # Uebernommen (von der Oberflaeche oder einem frueheren Waechter)
    state = load_state()
    manual = set(state.get("profile_manual", []))
    for pgid, start, idx in running_profile_apps(state):
        if idx in groups:
            groups[idx].append([pgid, start])
            states[idx]["launched"] = True
            states[idx]["manual"] = idx in manual

    def persist():
        st = load_state()
        st["profile_apps"] = [[g, s_, i] for i, lst in groups.items() for g, s_ in lst]
        st["profile_manual"] = sorted(i for i, s_ in enumerate(states)
                                      if s_["manual"] and s_["launched"])
        save_state(st)

    off_ticks = 0
    ticks = 0
    while True:
        ticks += 1
        now = _now()
        server_on = _server_running()
        off_ticks = 0 if server_on else off_ticks + 1
        names = _snapshot()
        cache = {}

        def headset_ok():
            if "v" not in cache:
                cache["v"] = bool(server_on and _headset())
            return cache["v"]

        changed = False
        for i, prof in enumerate(profiles):
            ok = engine.armed(prof) and process_watch.matches(prof["trigger"], names)
            ok = ok and headset_ok()
            action = engine.step(states[i], ok, prof["delay"], prof["stop_with"], now)
            if action == "launch":
                pending += [(due, i, app) for due, app in
                            engine.schedule(engine.commands(prof), prof["gap"], now)]
                log.info("[CLI-Profile] '%s': starte Programme.", prof["name"])
            elif action == "stop":
                pending = [x for x in pending if x[1] != i]
                exit_guard.stop_groups([(g, s_) for g, s_ in groups[i]])
                groups[i] = []
                changed = True
                log.info("[CLI-Profile] '%s': Bedingung weg — Programme beendet.", prof["name"])

        due_now = [x for x in pending if x[0] <= now]
        pending = [x for x in pending if x[0] > now]
        for _due, i, app in due_now:
            for pid in launch_apps([app], terminal_command):
                groups[i].append(_entry(pid))
            changed = True
        if changed:
            persist()

        # Server aus und nichts mehr zu tun -> Schluss. (Manuell Gestartetes
        # bleibt stehen und in der Zustandsdatei — YC-killapps raeumt es.)
        busy = pending or any(s_["launched"] and not s_["manual"] for s_ in states)
        if off_ticks >= engine.STOP_AFTER_MISSES and not busy:
            break
        if _max_ticks is not None and ticks >= _max_ticks:
            break
        wait = engine.POLL_S
        if pending:
            wait = max(0.2, min(wait, min(x[0] for x in pending) - now))
        _sleep(wait)

    st = load_state()
    st["profile_watcher"] = None
    save_state(st)
    persist()
    log.info("[CLI-Profile] Waechter beendet.")
    return 0
