#!/usr/bin/env python3
"""
core/proc.py — Externe Programme sicher aufrufen
================================================
Die App ruft an rund hundert Stellen fremde Programme auf (pactl, pgrep, ss,
pacman, adb, pkexec, git, ...). Zwei Probleme gab es dabei:

1. KEIN TIMEOUT.
   ``subprocess.run(...)`` wartet ohne Zeitlimit. Haengt ``pacman`` an einer
   Lock-Datei, ist ``adb`` im "starting daemon"-Zustand oder ist das Headset
   im Standby, friert die GUI ein — der Nutzer meldet "Programm reagiert
   nicht" und wir suchen im falschen Code. Hier gibt es jetzt ein
   Standard-Zeitlimit; laeuft ein Aufruf hinein, gibt es eine Logzeile mit
   dem exakten Befehl.

2. shell=True mit eingesetzten Namen.
   ``subprocess.run(f"{method} -Q {pkg}", shell=True)`` startet eine Shell,
   die den String erst interpretiert. Solange ``pkg`` aus unserer eigenen
   Konstante kommt, ist das ungefaehrlich — aber es kostet nichts, es richtig
   zu machen, und ``programs.json`` sowie die Spiele-Datenbank kommen
   inzwischen aus dem Netz. Deshalb ueberall Listenform.

Benutzung:

    from proc import run, run_ok, output_of

    res = run(["pactl", "list", "short", "sources"])   # CompletedProcess
    if run_ok(["pgrep", "wivrn-server"]):              # nur Exitcode 0?
        ...
    text = output_of(["wivrn-server", "--version"])    # stdout oder ""

``run`` wirft NIE eine Ausnahme wegen Timeout oder fehlendem Programm — es
gibt in dem Fall ein CompletedProcess mit returncode != 0 zurueck. Das macht
die Aufrufstellen kurz und verhindert, dass ein fehlendes optionales
Werkzeug (playerctl, adb ...) die App abschiesst.
"""
import subprocess

from logging_setup import get_logger

log = get_logger("proc")

# Standard-Zeitlimit in Sekunden fuer kurze Abfragen (pgrep, pactl, ss, ...).
# Bewusst grosszuegig: auf langsamen Systemen darf ein Aufruf ruhig eine
# Sekunde brauchen, er darf nur nicht EWIG dauern.
DEFAULT_TIMEOUT = 15

# Fuer Aufrufe, die naturgemaess laenger dauern (Paketmanager, git clone,
# adb install). Auch die bekommen eine Obergrenze — nur eine hoehere.
LONG_TIMEOUT = 600

# Exitcode fuer "konnte gar nicht ausgefuehrt werden". 127 ist die Konvention
# der Shell fuer "command not found"; 124 nutzt timeout(1) fuer Zeitueberlauf.
RC_NOT_FOUND = 127
RC_TIMEOUT = 124


def _failed(cmd, rc, stderr=""):
    """Ein CompletedProcess, das wie ein regulaerer Fehlschlag aussieht."""
    return subprocess.CompletedProcess(cmd, rc, stdout="", stderr=stderr)


def run(cmd, timeout=DEFAULT_TIMEOUT, text=True, capture=True,
        check_log=True, **kwargs):
    """
    Sicherer Ersatz fuer ``subprocess.run``.

    cmd:      Liste (empfohlen). Ein String wird NUR akzeptiert, wenn der
              Aufrufer ausdruecklich shell=True setzt — das sollte nirgends
              mehr noetig sein.
    timeout:  Sekunden. None schaltet das Zeitlimit ab (bitte nur mit gutem
              Grund und Kommentar).
    capture:  stdout/stderr einsammeln (Standard). False, wenn die Ausgabe
              den Nutzer nicht interessiert.
    """
    if capture:
        kwargs.setdefault("stdout", subprocess.PIPE)
        kwargs.setdefault("stderr", subprocess.PIPE)
    if text:
        kwargs.setdefault("text", True)

    try:
        result = subprocess.run(cmd, timeout=timeout, **kwargs)
        if check_log and result.returncode != 0:
            log.debug("Befehl endete mit %s: %s", result.returncode, _pretty(cmd))
        return result
    except FileNotFoundError:
        # Optionale Werkzeuge fehlen haeufig — das ist kein Drama, aber es
        # soll im Log stehen, damit "Knopf tut nichts" erklaerbar wird.
        log.info("Programm nicht gefunden: %s", _pretty(cmd))
        return _failed(cmd, RC_NOT_FOUND, "command not found")
    except subprocess.TimeoutExpired:
        log.warning("Zeitlimit (%ss) ueberschritten: %s", timeout, _pretty(cmd))
        return _failed(cmd, RC_TIMEOUT, "timeout")
    except PermissionError as exc:
        log.warning("Keine Ausfuehrrechte (%s): %s", exc, _pretty(cmd))
        return _failed(cmd, RC_NOT_FOUND, str(exc))
    except OSError as exc:
        log.warning("Aufruf fehlgeschlagen (%s): %s", exc, _pretty(cmd))
        return _failed(cmd, RC_NOT_FOUND, str(exc))


def run_ok(cmd, timeout=DEFAULT_TIMEOUT, **kwargs) -> bool:
    """True, wenn der Befehl mit Exitcode 0 endet. Fuer reine Ja/Nein-Fragen
    wie ``pgrep wivrn-server``."""
    return run(cmd, timeout=timeout, **kwargs).returncode == 0


def output_of(cmd, timeout=DEFAULT_TIMEOUT, default="", **kwargs) -> str:
    """
    stdout des Befehls als String — oder ``default``, wenn er fehlschlaegt.
    Spart an jeder Aufrufstelle das ``if res.returncode == 0``-Geruest.
    """
    res = run(cmd, timeout=timeout, **kwargs)
    if res.returncode != 0 or not res.stdout:
        return default
    return res.stdout


def which(program: str) -> bool:
    """Ist ein Programm im PATH? (duenner Wrapper, damit Aufrufstellen nicht
    ueberall shutil importieren muessen)"""
    import shutil
    return shutil.which(program) is not None


def _pretty(cmd) -> str:
    """Befehl fuers Log lesbar machen, ohne ihn ellenlang werden zu lassen."""
    text = " ".join(str(c) for c in cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
    return text if len(text) <= 200 else text[:197] + "..."
