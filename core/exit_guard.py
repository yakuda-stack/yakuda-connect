#!/usr/bin/env python3
"""
core/exit_guard.py — WiVRn mit der App beenden, egal WIE die App endet
======================================================================
Einstellung: Einstellungen → Erweitert / System → „WiVRn-Server mit der App
beenden" (Standard AN, Schluessel ``stop_server_with_app`` in config.json).

Bis v1.2.9 lief der Server einfach weiter, wenn man yakuda-connect schloss.
Die App kann auf sehr verschiedene Arten enden, und jede braucht einen
eigenen Weg, damit trotzdem aufgeraeumt wird:

  ┌───────────────────────────────┬──────────┬───────────────────────────┐
  │ Wie endet die App?            │ Signal   │ Wer raeumt auf?           │
  ├───────────────────────────────┼──────────┼───────────────────────────┤
  │ X am Fenster, Taskleiste      │ —        │ closeEvent (main.py)      │
  │ pkill, Taskmanager „Beenden"  │ SIGTERM  │ Signal → closeEvent       │
  │ Strg+C im Terminal            │ SIGINT   │ Signal → closeEvent       │
  │ Terminal geschlossen          │ SIGHUP   │ Signal → closeEvent       │
  │ Taskmanager „Kill", pkill -9, │ SIGKILL  │ Waechter-Prozess          │
  │ Absturz, OOM-Killer           │          │ (dieses Modul, unten)     │
  └───────────────────────────────┴──────────┴───────────────────────────┘

1. SIGTERM/SIGINT/SIGHUP
------------------------
Python-Signal-Handler laufen erst, wenn der Interpreter wieder dran ist. In
``app.exec()`` rechnet aber Qt in C++ — ohne Nachhilfe bliebe ein SIGTERM
liegen, bis zufaellig der naechste Timer feuert (beim USB-Timer bis zu 4 s,
im Hintergrund ohne Timer nie). ``signal.set_wakeup_fd`` schreibt deshalb
bei jedem Signal ein Byte in ein Socket-Paar, ein ``QSocketNotifier`` weckt
Qt auf, und damit kommt Python sofort an die Reihe. Der Handler schliesst
dann die Fenster — der Rest ist derselbe Weg wie beim Klick aufs X.

2. SIGKILL
----------
SIGKILL laesst sich nicht abfangen: der Prozess ist weg, ohne dass eine
einzige Zeile Python laeuft. Das kann nur ein ZWEITER Prozess bemerken.

Der Waechter ist ein kleiner Python-Prozess, den die App startet, sobald es
etwas zu bewachen gibt (Server laeuft UND Einstellung an). Er haengt an einer
Pipe, deren Schreibende nur die App besitzt. Stirbt die App — gleich wie —,
schliesst der Kernel das Schreibende, der Waechter liest EOF und beendet
Server, Autostart-Programme und eigene Kill-Befehle genau so, wie es das
Ausschalten des Server-Schalters im Dashboard tut.

Ueber dieselbe Pipe schickt die App ihm laufend den Stand (scharf ja/nein,
welche Autostart-Prozessgruppen). Beim sauberen Beenden hat die App schon
selbst aufgeraeumt und schickt „bye" — dann tut der Waechter nichts.

Warum der Waechter SIGTERM ignoriert
------------------------------------
``pkill -f yakuda-connect`` trifft auch ihn: der Pfad zu dieser Datei steht
in seiner Kommandozeile. Wuerde er mitsterben, bliebe genau der Fall
unbewacht, fuer den es ihn gibt. Er haengt trotzdem nie herum: er endet,
sobald die App endet (EOF oder „bye"), spaetestens nach dem Aufraeumen.

Warum er am Anfang ALLES importiert
-----------------------------------
Im AppImage liegt der Projektcode in einem FUSE-Mount, der verschwindet,
sobald der Hauptprozess endet — also genau dann, wenn der Waechter loslegt.
Ein ``import`` erst zu diesem Zeitpunkt wuerde ins Leere greifen. Die
Standardbibliothek ist unkritisch (AppRun nutzt das System-Python).

WICHTIG: Kein PySide6-Import auf Modulebene. Der Waechter laedt diese Datei
auch, und ein Qt-Import wuerde ihn um ~100 MB und eine Sekunde Start
verteuern.
"""
import json
import os
import select
import signal
import subprocess
import sys
import time

# Als Skript gestartet (Waechter) liegt nur core/ im Pfad — das reicht fuer
# die Geschwistermodule. Als Modul importiert (App) ist core/ ohnehin drin.
import paths
import proc              # noqa: F401 — vorab laden, siehe Modul-Kopf (AppImage)
import wivrn_server
from logging_setup import get_logger, setup_logging

log = get_logger("exit_guard")

SETTING_KEY = "stop_server_with_app"
SETTING_DEFAULT = True

# Schaltet das ganze Feature ab (kein Stopp beim Schliessen, kein Waechter).
# Nur fuer Tests: smoke.py baut ein echtes Fenster mit der echten Config —
# auf einem Entwicklerrechner mit laufendem Server wuerde sonst jeder
# Testlauf den Server abschiessen und einen Waechter hinterlassen.
DISABLE_ENV = "YAKUDA_NO_EXIT_GUARD"

_GUARD_COMM = b"yakuda-guard"     # Name im Taskmanager (max. 15 Zeichen)
_PARENT_CHECK_S = 2.0             # Nachschau, falls die Pipe doch offen bleibt
_GROUP_TERM_S = 3.0               # wie stop_autostart_apps in main.py
_KILLCMD_TIMEOUT_S = 5            # wie _run_custom_kill_commands in main.py


def disabled_by_env():
    return os.environ.get(DISABLE_ENV, "").strip() not in ("", "0")


def enabled_in(settings):
    """Liest den Schalter aus einem Settings-Dict (auch alte Text-Werte)."""
    value = settings.get(SETTING_KEY, SETTING_DEFAULT) if isinstance(settings, dict) else SETTING_DEFAULT
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in ("0", "false", "off", "no", "")


# --------------------------------------------------------------------------- #
#  Gemeinsame Bausteine (App UND Waechter)
# --------------------------------------------------------------------------- #
def run_kill_commands(entries):
    """Eigene Kill-Befehle als Shell ausfuehren — best effort, je 5 s Zeit."""
    for entry in entries or []:
        if isinstance(entry, dict):
            cmd = entry.get("cmd") or ""
        elif isinstance(entry, str):
            cmd = entry
        else:
            cmd = ""
        cmd = cmd.strip()
        if not cmd:
            continue
        try:
            subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=_KILLCMD_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            log.info("[Kill-Befehl] brauchte zu lange: %s", cmd)
        except Exception as exc:  # noqa: BLE001 — ein Befehl darf den Rest nicht stoppen
            log.warning("[Kill-Befehl] fehlgeschlagen (%s): %s", cmd, exc)


def process_starttime(pid):
    """
    Startzeitpunkt aus /proc/<pid>/stat (Feld 22, in Ticks seit Boot).

    PID + Startzeit zusammen benennen einen Prozess eindeutig. Die PID allein
    nicht: sie wird nach dem Ende eines Prozesses irgendwann neu vergeben.
    """
    try:
        with open(f"/proc/{pid}/stat") as fh:
            data = fh.read()
    except OSError:
        return None
    end = data.rfind(")")          # Name darf Klammern enthalten, siehe wivrn_server._state
    rest = data[end + 1:].split() if end >= 0 else []
    # rest[0] ist Feld 3 (Zustand) → Feld 22 liegt bei Index 19
    try:
        return int(rest[19])
    except (IndexError, ValueError):
        return None


def group_is_ours(pgid, starttime):
    """
    Gehoert die Prozessgruppe noch zu dem Autostart-Programm, das wir kennen?

    Die Autostart-Programme laufen mit ``start_new_session=True`` — die
    Gruppen-ID ist also die PID des Startprozesses. Drei Faelle:

    * Startprozess lebt, Startzeit passt      → unsere Gruppe.
    * Es gibt keinen Prozess mit dieser PID   → der Startprozess ist weg. Eine
      noch existierende Gruppe kann trotzdem nur UNSERE sein: der Kernel
      vergibt eine PID nicht neu, solange sie als Gruppen-ID benutzt wird.
    * Prozess mit dieser PID, andere Startzeit → PID neu vergeben. Finger weg.
    """
    now = process_starttime(pgid)
    if now is None:
        return True
    return starttime is not None and now == starttime


def _group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return False


def stop_groups(groups, term_timeout=_GROUP_TERM_S, _sleep=time.sleep,
                _clock=time.monotonic):
    """SIGTERM an alle eigenen Gruppen, kurz warten, Reste per SIGKILL."""
    targets = [int(g) for g, st in groups if group_is_ours(int(g), st)]
    for pgid in targets:
        try:
            os.killpg(pgid, signal.SIGTERM)
        except OSError as exc:
            log.debug("killpg(%s, TERM): %s", pgid, exc)
    deadline = _clock() + term_timeout
    while _clock() < deadline and any(_group_alive(g) for g in targets):
        _sleep(0.1)
    for pgid in targets:
        if _group_alive(pgid):
            try:
                os.killpg(pgid, signal.SIGKILL)
            except OSError as exc:
                log.debug("killpg(%s, KILL): %s", pgid, exc)


def _read_settings():
    """config.json direkt lesen — ohne config_manager und seine Importe."""
    try:
        with open(paths.config_file("config.json")) as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 — fehlende/defekte Datei = Standardwerte
        return {}


# --------------------------------------------------------------------------- #
#  App-Seite: den Waechter fuehren
# --------------------------------------------------------------------------- #
class ExitGuard:
    """
    Haelt den Waechter-Prozess und schickt ihm den aktuellen Stand.

    Gestartet wird er erst, wenn es etwas zu bewachen gibt. Wer die App nur
    fuer Einstellungen oeffnet, bekommt keinen zusaetzlichen Prozess.
    """

    def __init__(self, popen=subprocess.Popen):
        self._popen = popen
        self._proc = None
        self._last = None

    @property
    def running(self):
        return self._proc is not None and self._proc.poll() is None

    def update(self, armed, groups=()):
        """
        armed:  Soll bei einem harten Ende aufgeraeumt werden?
        groups: PIDs der Autostart-Prozessgruppen.
        """
        if disabled_by_env():
            return
        state = {
            "armed": bool(armed),
            "groups": [[int(pid), process_starttime(pid)] for pid in groups],
        }
        if state == self._last and self.running:
            return
        if not self.running:
            if not state["armed"]:
                self._last = state      # nichts zu bewachen → nichts starten
                return
            if not self._spawn():
                return
        self._send(json.dumps(state))
        self._last = state

    def release(self):
        """Sauberes Ende: Aufgeraeumt ist schon — Waechter entlassen."""
        if self._proc is None:
            return
        self._send("bye")
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
        except OSError:
            pass
        try:
            self._proc.wait(timeout=2)
        except Exception:  # noqa: BLE001
            log.warning("[Waechter] reagiert nicht auf 'bye' — wird beendet.")
            try:
                self._proc.kill()
                self._proc.wait(timeout=1)
            except Exception as exc:  # noqa: BLE001
                log.debug("[Waechter] kill: %s", exc)
        self._proc = None
        self._last = None

    # -- intern ------------------------------------------------------------ #
    def _spawn(self):
        try:
            self._proc = self._popen(
                [sys.executable, os.path.abspath(__file__), "--watch", str(os.getpid())],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                # Eigene Sitzung: Strg+C oder ein geschlossenes Terminal
                # trifft die ganze Vordergrund-Gruppe — der Waechter soll
                # davon nichts abbekommen.
                start_new_session=True,
                # Nicht im Programmordner stehen bleiben: im AppImage ist der
                # nach dem Ende der App nicht mehr da.
                cwd="/",
            )
            log.info("[Waechter] gestartet (PID %s).", self._proc.pid)
            return True
        except Exception as exc:  # noqa: BLE001 — Waechter ist Zusatzschutz
            log.warning("[Waechter] konnte nicht gestartet werden: %s", exc)
            self._proc = None
            return False

    def _send(self, line):
        try:
            self._proc.stdin.write((line + "\n").encode())
            self._proc.stdin.flush()
        except (OSError, ValueError, AttributeError) as exc:
            # Waechter weg (z. B. selbst per SIGKILL beendet). Beim naechsten
            # update() wird ein neuer gestartet.
            log.warning("[Waechter] nicht erreichbar: %s", exc)
            self._proc = None
            self._last = None


# --------------------------------------------------------------------------- #
#  App-Seite: SIGTERM & Co. in einen normalen Fenster-Schluss verwandeln
# --------------------------------------------------------------------------- #
_signal_refs = []    # Socket-Paar + Notifier muessen am Leben bleiben

# True, sobald ein Signal (Abmelden, Herunterfahren, kill) das Beenden
# ausgeloest hat. Dann darf closeEvent keine Rueckfrage mehr zeigen — ein
# modaler Dialog wuerde das Abmelden blockieren, und der Sitzungsmanager
# wartet nicht.
quit_requested_by_signal = False


def install_quit_signals(app):
    """SIGTERM/SIGINT/SIGHUP → alle Fenster schliessen (= closeEvent) → quit."""
    import socket
    from PySide6.QtCore import QSocketNotifier
    from PySide6.QtWidgets import QApplication

    rsock, wsock = socket.socketpair()
    rsock.setblocking(False)
    wsock.setblocking(False)
    try:
        signal.set_wakeup_fd(wsock.fileno())
    except ValueError as exc:            # nicht im Haupt-Thread
        log.warning("Signal-Weckruf nicht moeglich: %s", exc)
        return False

    notifier = QSocketNotifier(rsock.fileno(), QSocketNotifier.Read)

    def _drain():
        try:
            while rsock.recv(64):
                pass
        except (BlockingIOError, OSError):
            pass

    notifier.activated.connect(_drain)

    def _handler(signum, _frame):
        global quit_requested_by_signal
        quit_requested_by_signal = True
        log.info("Signal %s empfangen — App wird geordnet beendet.",
                 signal.Signals(signum).name)
        QApplication.closeAllWindows()
        app.quit()

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, _handler)
    _signal_refs.extend([rsock, wsock, notifier, _handler])
    return True


# --------------------------------------------------------------------------- #
#  Waechter-Seite
# --------------------------------------------------------------------------- #
def cleanup_after_hard_exit(state, settings=None):
    """Das, was der Server-Schalter im Dashboard beim Ausschalten tut — ohne App."""
    if settings is None:
        settings = _read_settings()
    log.warning("[Waechter] yakuda-connect ist ohne Aufraeumen beendet worden "
                "— WiVRn wird wie ueber den Dashboard-Schalter gestoppt.")
    # Reihenfolge wie in stop_wivrn_server → stop_autostart_apps:
    # eigene Kill-Befehle, Autostart-Programme, dann der Server.
    import killcmd_migrate
    run_kill_commands(killcmd_migrate.all_kill_commands(settings))
    stop_groups(state.get("groups") or [])
    stopped = wivrn_server.stop_blocking(None)
    if stopped:
        log.info("[Waechter] WiVRn beendet.")
    else:
        log.error("[Waechter] WiVRn laeuft trotz SIGKILL weiter: PIDs %s",
                  wivrn_server.server_pids())
    return stopped


def watch(parent_pid, fd=0, cleanup=cleanup_after_hard_exit):
    """Hauptschleife des Waechters. Rueckgabe: 'bye', 'cleaned' oder 'idle'."""
    state = {"armed": False, "groups": []}
    buf = b""
    while True:
        ready, _, _ = select.select([fd], [], [], _PARENT_CHECK_S)
        if ready:
            chunk = os.read(fd, 4096)
            if not chunk:
                break                                  # EOF → App ist weg
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if line == b"bye":
                    return "bye"
                if line:
                    try:
                        new = json.loads(line)
                        if isinstance(new, dict):
                            state = new
                    except ValueError:
                        pass
        elif os.getppid() != parent_pid:
            # Umgehaengt an init/Subreaper → App ist tot, obwohl die Pipe
            # noch offen ist (irgendein Kind hat das Schreibende geerbt).
            break
    if not state.get("armed"):
        return "idle"
    try:
        setup_logging(to_console=False)
    except Exception:  # noqa: BLE001
        pass
    cleanup(state)
    return "cleaned"


def _main(argv):
    if len(argv) < 3 or argv[1] != "--watch":
        print("Aufruf: exit_guard.py --watch <app-pid>", file=sys.stderr)
        return 2
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, signal.SIG_IGN)
    try:
        import ctypes
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(15, _GUARD_COMM, 0, 0, 0)
    except Exception:  # noqa: BLE001 — nur Kosmetik im Taskmanager
        pass
    watch(int(argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
