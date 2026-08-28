#!/usr/bin/env python3
"""
core/wivrn_server.py — den WiVRn-Server finden und zuverlaessig beenden
======================================================================
Bis v1.2.4 lief das Beenden so:

    if self.server_process: self.server_process.terminate()
    else: proc.run(["pkill", "wivrn-server"])
    self.server_process = None

Beides zusammen ergab den Fehler "Server geht erst beim dritten Mal aus":

1. KEIN WARTEN, KEIN NACHFASSEN.
   ``terminate()`` schickt SIGTERM und kehrt SOFORT zurueck. Nach einer
   VR-Sitzung braucht wivrn-server aber einen Moment (Encoder abbauen,
   Audiogeraet abmelden, Client-Socket schliessen). In der Zwischenzeit galt
   er in der App bereits als beendet — geprueft wurde nie nach.

2. DER ZOMBIE.
   Direkt nach dem SIGTERM wurde ``self.server_process = None`` gesetzt. Damit
   war die einzige Referenz auf das Kind weg, und niemand hat es je mit
   ``wait()``/``poll()`` geerntet. Ein beendetes, aber nicht geerntetes Kind
   bleibt als Zombie (Zustand ``Z``) im Prozessbaum stehen — MIT seinem Namen.
   ``pgrep wivrn-server`` filtert Zombies nicht heraus und meldete deshalb
   weiterhin "laeuft". Genau das sah man beim Klick auf "Server-Status
   pruefen": Schalter springt zurueck auf AN, obwohl der Server laengst tot
   war. Der naechste Stopp-Klick lief dann in den ``else``-Zweig und schickte
   ein pkill an einen Zombie — das tut nichts, denn ein Zombie laesst sich
   nicht noch einmal beenden. Erst wenn Python irgendwann beilaeufig aufraeumt
   (das passiert beim Anlegen des naechsten Popen-Objekts), verschwand er.
   Daher "zwei-, dreimal beenden, dann geht es".

Dieses Modul loest beides:

  * ``server_pids()`` liest /proc direkt und laesst Zombies aus. Damit gibt es
    keine falschen "laeuft noch"-Meldungen mehr — und ganz nebenbei keinen
    Subprozess pro Statusabfrage.
  * ``request_stop()`` / ``force_stop()`` sind die zwei Stufen der Eskalation,
    ``reap()`` erntet das eigene Kind. Das Warten dazwischen macht der
    Aufrufer per Timer, damit die Oberflaeche bedienbar bleibt.

Bewusst nicht ueber ``pkill``: ein eigener Prozessaufruf pro Signal, dessen
Exitcode nur "irgendwas getroffen" heisst, und der bei Zombies luegt. os.kill
auf die selbst ermittelten PIDs sagt genau, was passiert ist.
"""
import os
import signal

import proc
from logging_setup import get_logger

log = get_logger("wivrn")

# Name, wie ihn der Kernel in /proc/<pid>/comm fuehrt (max. 15 Zeichen —
# "wivrn-server" hat 12, wird also nicht abgeschnitten).
PROC_NAME = "wivrn-server"

# Manche Distributionen starten den Server als systemd-Nutzerdienst. Ein
# SIGTERM allein bringt dann nichts: systemd startet ihn je nach Unit sofort
# neu. Deshalb wird in der zweiten Stufe geprueft, ob es diesen Dienst
# ueberhaupt gibt und ob er aktiv ist.
SERVICE_UNIT = "wivrn-server.service"


# --------------------------------------------------------------------------- #
#  /proc lesen
# --------------------------------------------------------------------------- #
def _comm(pid):
    """Prozessname aus /proc/<pid>/comm (oder "", wenn der Prozess weg ist)."""
    try:
        with open(f"/proc/{pid}/comm") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _state(pid):
    """
    Zustandsbuchstabe aus /proc/<pid>/stat: R/S/D laufend, Z = Zombie.

    Feld 2 ist der Prozessname in Klammern und darf selbst Leerzeichen und
    Klammern enthalten — deshalb wird ab der LETZTEN Klammer weitergelesen und
    nicht stumpf an Leerzeichen zerlegt.
    """
    try:
        with open(f"/proc/{pid}/stat") as fh:
            data = fh.read()
    except OSError:
        return ""
    end = data.rfind(")")
    if end < 0:
        return ""
    rest = data[end + 1:].split()
    return rest[0] if rest else ""


def server_pids(include_zombies=False):
    """
    PIDs aller laufenden wivrn-server-Prozesse.

    Zombies bleiben aussen vor: sie tragen zwar noch den Namen, sind aber
    beendet. Wer sie mitzaehlt, zeigt dem Nutzer einen Server an, den es nicht
    mehr gibt (siehe Modul-Kopf).
    """
    pids = []
    try:
        entries = os.listdir("/proc")
    except OSError:                       # /proc nicht da (Container, BSD)
        return pids
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        if _comm(pid) != PROC_NAME:
            continue
        if not include_zombies and _state(pid) == "Z":
            continue
        pids.append(pid)
    return sorted(pids)


def is_running(process=None):
    """
    Laeuft ein Server?

    ``process`` ist das eigene Popen-Objekt, falls die App ihn gestartet hat.
    Der ``poll()``-Aufruf darauf ist kein Beiwerk, sondern der eigentliche
    Punkt: er erntet ein beendetes Kind und raeumt damit den Zombie weg, BEVOR
    /proc durchsucht wird.
    """
    if process is not None and process.poll() is None:
        return True
    return bool(server_pids())


def reap(process):
    """Beendetes Kind ernten. Gibt True zurueck, wenn es wirklich weg ist."""
    if process is None:
        return True
    return process.poll() is not None


# --------------------------------------------------------------------------- #
#  Beenden
# --------------------------------------------------------------------------- #
def _signal_all(sig, process=None):
    """Signal an alle gefundenen Server-Prozesse. Gibt die Trefferzahl zurueck."""
    if process is not None:
        process.poll()                    # erst ernten, dann zaehlen
    sent = 0
    for pid in server_pids():
        try:
            os.kill(pid, sig)
            sent += 1
        except ProcessLookupError:
            pass                          # war schneller weg als wir
        except PermissionError:
            # Fremder Server unter einem anderen Benutzer — nicht unser Bier.
            log.warning("[Server] PID %s gehoert einem anderen Benutzer.", pid)
        except OSError as exc:
            log.debug("[Server] kill(%s, %s): %s", pid, sig, exc)
    return sent


def request_stop(process=None):
    """Stufe 1: hoeflich bitten (SIGTERM). Der Server raeumt dann selbst auf."""
    count = _signal_all(signal.SIGTERM, process)
    log.info("[Server] SIGTERM an %s Prozess(e).", count)
    return count


def force_stop(process=None):
    """Stufe 2: SIGKILL. Kein Aufraeumen mehr, aber garantiert Schluss."""
    count = _signal_all(signal.SIGKILL, process)
    log.warning("[Server] SIGKILL an %s Prozess(e).", count)
    return count


def stop_user_service():
    """
    Den systemd-Nutzerdienst stoppen — aber nur, wenn es ihn gibt und er
    laeuft.

    Ohne diesen Schritt kann das Beenden aussichtslos sein: hat die Unit ein
    ``Restart=``, startet systemd den Server nach jedem Kill sofort neu, und
    die App wuerde ewig gegen ihn ankaempfen.
    """
    if not proc.which("systemctl"):
        return False
    if not proc.run_ok(["systemctl", "--user", "is-active", "--quiet",
                        SERVICE_UNIT], timeout=5, check_log=False):
        return False
    log.info("[Server] %s laeuft als systemd-Dienst — wird gestoppt.", SERVICE_UNIT)
    return proc.run_ok(["systemctl", "--user", "stop", SERVICE_UNIT], timeout=20)
