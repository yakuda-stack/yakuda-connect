#!/usr/bin/env python3
"""
core/process_watch.py — Laeuft ein bestimmtes Programm? (ohne Qt)
=================================================================
Grundlage fuer die Autostart-Profile im Dashboard („Wenn VRChat laeuft,
starte auch X und Y“).

Performance
-----------
Es wird KEIN ``pgrep``/``ps`` gestartet. Ein Durchlauf liest direkt
``/proc/<pid>/comm`` und ``/proc/<pid>/cmdline`` — das sind reine
Kernel-Pseudodateien, kein Plattenzugriff. Bei ~500 Prozessen dauert das
wenige Millisekunden. ``snapshot()`` laeuft pro Timer-Tick genau EINMAL,
egal wie viele Profile es gibt.

Namensvergleich
---------------
Verglichen wird der Programmname ohne Pfad, ohne Gross/Klein und ohne
``.exe``. „VRChat“, „vrchat.exe“ und „Z:\\...\\VRChat.exe“ passen also alle
zueinander. Bewusst KEIN Teilstring-Vergleich: sonst wuerde „vrchat“ auch
auf „vrchat-osc-tool“ oder einen Texteditor mit „vrchat.log“ anspringen.
"""
import os
import re

PROC_ROOT = "/proc"

# comm ist im Kernel auf 15 Zeichen gekuerzt.
_COMM_MAX = 15
# Mehr Argumente schaut sich niemand an — begrenzt den Aufwand bei
# Prozessen mit riesigen Kommandozeilen (Electron & Co.).
_MAX_ARGS = 48


def norm(name):
    """Programmname vergleichbar machen: ohne Pfad, klein, ohne .exe."""
    s = (name or "").strip().strip('"').replace("\\", "/")
    s = s.rsplit("/", 1)[-1].lower()
    if s.endswith(".exe"):
        s = s[:-4]
    return s


def _read(path, limit=8192):
    try:
        with open(path, "rb") as f:
            return f.read(limit)
    except OSError:
        return b""


def _pids(proc_root):
    try:
        with os.scandir(proc_root) as it:
            for entry in it:
                if entry.name.isdigit():
                    yield entry
    except OSError:
        return


def snapshot(proc_root=PROC_ROOT):
    """Menge aller normierten Programmnamen, die gerade laufen.

    Pro Prozess: der Kernel-Name (comm) und die Dateinamen aus der
    Kommandozeile. Letzteres braucht es fuer Proton/Wine-Spiele: dort
    steht „VRChat.exe“ als Argument hinter wine/reaper.
    """
    names = set()
    own = str(os.getpid())
    for entry in _pids(proc_root):
        if entry.name == own:
            continue
        comm = _read(os.path.join(entry.path, "comm"), 64)
        if comm:
            names.add(norm(comm.decode("utf-8", "replace").strip()))
        raw = _read(os.path.join(entry.path, "cmdline"))
        if not raw:
            continue          # Kernel-Threads haben keine Kommandozeile
        for arg in raw.split(b"\0")[:_MAX_ARGS]:
            if arg:
                names.add(norm(arg.decode("utf-8", "replace")))
    names.discard("")
    return names


# „VRChat [AppId=438100]“ -> verglichen wird nur, was in der Klammer steht.
# So kann das Feld einen lesbaren Namen zeigen (Auswahl aus dem Games-Tab).
_KEY_RE = re.compile(r"\[([^\]]+)\]\s*$")


def match_key(trigger):
    """Der Teil des Ausloesers, der wirklich verglichen wird."""
    m = _KEY_RE.search(trigger or "")
    return m.group(1) if m else (trigger or "")


def matches(trigger, names):
    """Laeuft ``trigger`` laut ``snapshot()``-Ergebnis?

    Steam-Spiele laufen unter Steams „reaper“ mit dem Argument
    ``AppId=<id>`` — ``VRChat [AppId=438100]`` trifft deshalb genau dieses
    Spiel, egal wie seine .exe heisst.
    """
    t = norm(match_key(trigger))
    if not t:
        return False
    if t in names:
        return True
    # Lange Namen stehen in comm nur gekuerzt.
    return len(t) > _COMM_MAX and t[:_COMM_MAX] in names


def is_running(trigger, proc_root=PROC_ROOT):
    """Einzelabfrage — fuer mehrere Profile lieber snapshot()+matches()."""
    return matches(trigger, snapshot(proc_root))


def list_programs(proc_root=PROC_ROOT):
    """Laufende Programme des eigenen Nutzers fuer die Auswahlliste.

    Liefert Namen in Originalschreibweise (fuer die Anzeige), sortiert.
    Kernel-Threads und fremde Nutzer (root-Dienste) fehlen, damit die
    Liste nicht voller System-Kram ist. Windows-Programme (Proton) tauchen
    mit ihrem .exe-Namen auf.
    """
    uid = os.getuid()
    own = str(os.getpid())
    seen = {}
    for entry in _pids(proc_root):
        if entry.name == own:
            continue
        try:
            if entry.stat().st_uid != uid:
                continue
        except OSError:
            continue
        raw = _read(os.path.join(entry.path, "cmdline"))
        if not raw:
            continue
        comm = _read(os.path.join(entry.path, "comm"), 64).decode("utf-8", "replace").strip()
        candidates = [comm] if comm else []
        for arg in raw.split(b"\0")[:_MAX_ARGS]:
            a = arg.decode("utf-8", "replace")
            if a.lower().endswith(".exe"):
                candidates.append(a.replace("\\", "/").rsplit("/", 1)[-1])
        for c in candidates:
            key = norm(c)
            if key and key not in seen:
                seen[key] = c
    return sorted(seen.values(), key=str.lower)


# --------------------------------------------------------------------------- #
#  Headset verbunden?  (ohne Subprozess)
# --------------------------------------------------------------------------- #
# WiVRn haelt waehrend einer Sitzung eine TCP-Verbindung auf Port 9757.
# autostart_runner.headset_connected() fragt dafuer ``ss`` und ``pactl`` —
# drei Prozessstarts pro Pruefung. Hier steht dieselbe Information direkt
# aus /proc/net/tcp{,6}: Spalte 2 = lokale Adresse "IP:PORT" (hex),
# Spalte 4 = Zustand, 01 = ESTABLISHED. Der WiVRn-Flatpak teilt das Netz mit
# dem Host (--share=network), seine Verbindung steht also auch hier.
WIVRN_PORT = 9757


def headset_connected(proc_root=PROC_ROOT, port=WIVRN_PORT):
    """True, wenn eine WiVRn-Sitzung (TCP, Port 9757) aufgebaut ist."""
    want = f"{port:04X}"
    for name in ("tcp", "tcp6"):
        try:
            with open(os.path.join(proc_root, "net", name)) as fh:
                next(fh, None)                       # Kopfzeile
                for line in fh:
                    parts = line.split()
                    if len(parts) < 4 or parts[3] != "01":
                        continue
                    if parts[1].rsplit(":", 1)[-1] == want:
                        return True
        except OSError:
            continue
    return False
