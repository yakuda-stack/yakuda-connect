#!/usr/bin/env python3
"""
tests/test_wivrn_server.py — Server finden und beenden
======================================================
Der Fehler, der hier abgesichert wird, hat Nutzer zwei Versionen lang
begleitet: "der Server geht erst beim dritten Beenden aus".

Ursache war ein Zombie. Ein beendetes, aber nie geerntetes Kind steht mit
seinem Namen weiter im Prozessbaum; ``pgrep`` filtert das nicht heraus und
meldete deshalb einen Server, den es nicht mehr gab.

Der Test baut genau diese Lage nach — mit einem echten Zombie, nicht mit einer
nachgestellten Antwort. Deshalb wird ``PROC_NAME`` auf 'sleep' umgebogen: dann
sucht das Modul nach den Testprozessen statt nach einem echten WiVRn-Server,
und die Pruefung laeuft ohne installiertes WiVRn.
"""
import os
import pathlib
import signal
import subprocess
import sys
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT))

import wivrn_server as ws  # noqa: E402


def _wait_until(predicate, timeout=3.0):
    """Kurz pollen statt fest schlafen — sonst wird der Test langsam ODER flaky."""
    ende = time.monotonic() + timeout
    while time.monotonic() < ende:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def als_sleep(monkeypatch):
    """Das Modul soll im Test nach 'sleep'-Prozessen suchen."""
    monkeypatch.setattr(ws, "PROC_NAME", "sleep")
    return ws


# --------------------------------------------------------------------------- #
#  1. Finden
# --------------------------------------------------------------------------- #
def test_findet_laufenden_prozess(als_sleep):
    p = subprocess.Popen(["sleep", "30"])
    try:
        assert _wait_until(lambda: p.pid in als_sleep.server_pids())
        assert als_sleep.is_running() is True
    finally:
        p.kill()
        p.wait()


def test_eigener_prozessname_wird_erkannt(monkeypatch):
    """Gegenprobe ohne Kindprozess: der Testlauf selbst muss auffindbar sein."""
    with open("/proc/self/comm") as fh:
        monkeypatch.setattr(ws, "PROC_NAME", fh.read().strip())
    assert os.getpid() in ws.server_pids()


def test_ohne_treffer_keine_pids(monkeypatch):
    monkeypatch.setattr(ws, "PROC_NAME", "gibt-es-nicht-xyz")
    assert ws.server_pids() == []
    assert ws.is_running() is False


# --------------------------------------------------------------------------- #
#  2. Der Zombie — der eigentliche Fehler
# --------------------------------------------------------------------------- #
def test_zombie_zaehlt_nicht_als_laufend(als_sleep):
    """
    Ein beendetes, nicht geerntetes Kind darf NICHT als laufender Server
    gelten. Genau daran ist die alte pgrep-Pruefung gescheitert.
    """
    p = subprocess.Popen(["sleep", "0.05"])
    # Bewusst kein wait(): so entsteht der Zombie, um den es geht.
    assert _wait_until(lambda: als_sleep._state(p.pid) == "Z")

    assert p.pid in als_sleep.server_pids(include_zombies=True)
    assert p.pid not in als_sleep.server_pids()
    p.wait()


def test_is_running_erntet_das_eigene_kind(als_sleep):
    """
    Mit dem Popen-Objekt in der Hand muss der Zombie sogar VERSCHWINDEN:
    is_running() ruft poll() auf, und damit ist das Kind geerntet.
    """
    p = subprocess.Popen(["sleep", "0.05"])
    assert _wait_until(lambda: als_sleep._state(p.pid) == "Z")

    assert als_sleep.is_running(p) is False
    assert p.pid not in als_sleep.server_pids(include_zombies=True)
    assert als_sleep.reap(p) is True


def test_laufendes_kind_gilt_als_laufend(als_sleep):
    p = subprocess.Popen(["sleep", "30"])
    try:
        assert als_sleep.is_running(p) is True
        assert als_sleep.reap(p) is False
    finally:
        p.kill()
        p.wait()


def test_reap_ohne_prozess_ist_harmlos():
    assert ws.reap(None) is True


# --------------------------------------------------------------------------- #
#  3. Beenden
# --------------------------------------------------------------------------- #
def test_request_stop_beendet_und_meldet_die_zahl(als_sleep):
    p = subprocess.Popen(["sleep", "30"])
    try:
        assert _wait_until(lambda: p.pid in als_sleep.server_pids())
        assert als_sleep.request_stop(p) >= 1
        assert _wait_until(lambda: not als_sleep.is_running(p))
    finally:
        if p.poll() is None:
            p.kill()
        p.wait()


def test_force_stop_wirkt_auch_bei_ignoriertem_sigterm(als_sleep, tmp_path):
    """
    Der Fall, fuer den die zweite Stufe existiert: ein Prozess, der SIGTERM
    einfach wegsteckt. Ohne SIGKILL wuerde die App ewig warten.
    """
    # Der Prozess setzt seinen Kernel-Namen selbst um. Ohne das hiesse er
    # "python3" — genauso wie der Testlauf, der sich dann selbst abschiessen
    # wuerde (einmal passiert, deshalb steht es hier).
    skript = tmp_path / "stur.py"
    skript.write_text(
        "import ctypes, signal, time\n"
        "ctypes.CDLL('libc.so.6').prctl(15, b'yk-stur-test', 0, 0, 0)\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "print('bereit', flush=True)\n"
        "time.sleep(60)\n")
    p = subprocess.Popen([sys.executable, str(skript)], stdout=subprocess.PIPE, text=True)
    try:
        p.stdout.readline()                       # warten, bis SIGTERM ignoriert wird
        with open(f"/proc/{p.pid}/comm") as fh:
            name = fh.read().strip()
        assert name == "yk-stur-test", f"Umbenennung fehlgeschlagen: {name}"
        # Das Modul soll genau diesen Prozess als "Server" ansehen.
        als_sleep.PROC_NAME = name

        als_sleep.request_stop(p)
        time.sleep(0.3)
        assert als_sleep.is_running(p) is True    # SIGTERM allein reicht nicht

        assert als_sleep.force_stop(p) >= 1
        assert _wait_until(lambda: not als_sleep.is_running(p))
    finally:
        if p.poll() is None:
            p.kill()
        p.wait()


def test_signal_an_fremden_prozess_bricht_nicht_ab(als_sleep, monkeypatch):
    """
    Laeuft ein wivrn-server unter einem anderen Benutzer, scheitert das Signal
    mit PermissionError. Das muss geschluckt werden — sonst reisst ein fremder
    Prozess die ganze Beenden-Routine mit, und der EIGENE Server bleibt an.
    """
    def verboten(pid, sig):
        raise PermissionError("Operation not permitted")

    monkeypatch.setattr(als_sleep, "server_pids", lambda include_zombies=False: [4242])
    monkeypatch.setattr(als_sleep.os, "kill", verboten)
    assert als_sleep._signal_all(signal.SIGTERM) == 0


def test_verschwundene_pid_bricht_nicht_ab(als_sleep, monkeypatch):
    p = subprocess.Popen(["sleep", "0.01"])
    p.wait()
    monkeypatch.setattr(als_sleep, "server_pids", lambda include_zombies=False: [p.pid])
    assert als_sleep._signal_all(signal.SIGTERM) == 0


# --------------------------------------------------------------------------- #
#  4. systemd-Dienst
# --------------------------------------------------------------------------- #
def test_dienst_stopp_ohne_systemctl(monkeypatch):
    monkeypatch.setattr(ws.proc, "which", lambda name: False)
    assert ws.stop_user_service() is False


def test_dienst_stopp_nur_wenn_der_dienst_laeuft(monkeypatch):
    aufrufe = []

    monkeypatch.setattr(ws.proc, "which", lambda name: True)
    monkeypatch.setattr(ws.proc, "run_ok",
                        lambda cmd, **kw: aufrufe.append(cmd) or False)
    assert ws.stop_user_service() is False
    # Nur die Nachfrage, kein Stopp: ein fremder Dienst darf nicht angefasst
    # werden, bloss weil der Nutzer hier auf "Stop" geklickt hat.
    assert len(aufrufe) == 1
    assert "is-active" in aufrufe[0]
