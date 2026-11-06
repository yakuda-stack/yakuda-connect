#!/usr/bin/env python3
"""
core/killcmd_suggest.py — Vorschlag fuer den Kill-Befehl einer Autostart-Zeile
=============================================================================
Klickt man ins (leere) Kill-Feld oder setzt den Haken „Kill“, schlaegt die App
einen passenden Befehl vor — abgeleitet aus dem Startbefehl darueber:

    CMD  wayvr                        -> pkill -f wayvr
    CMD  flatpak run io.github.x.App  -> flatpak kill io.github.x.App
    CMD  env FOO=1 gamemoderun vrcx   -> pkill -f vrcx
    Pfad /home/u/Apps/VRCX.AppImage   -> pkill -f VRCX.AppImage
    Pfad "/opt/My App/start.sh"       -> pkill -f 'start.sh'

-f vergleicht mit der ganzen Befehlszeile: AppImages und Electron-Apps (VRCX)
laufen unter anderem Prozessnamen bzw. in mehreren Prozessen, der Dateiname
steht aber immer in der Befehlszeile. Der Name wird fuer die Shell
abgesichert (shlex.quote).

Kein Qt — mit einfachen Tests pruefbar.
"""
import os
import re
import shlex

# Vorangestellte Helfer, die nicht das eigentliche Programm sind
WRAPPERS = {"env", "gamemoderun", "mangohud", "nice", "ionice", "taskset", "prime-run",
            "nohup", "setsid", "exec", "sudo", "pkexec", "stdbuf", "systemd-run"}
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _tokens(cmd):
    try:
        return shlex.split(cmd or "")
    except ValueError:
        return (cmd or "").split()


def program_name(cmd, mode="CMD"):
    """Name, an dem man den laufenden Prozess erkennt — oder ''."""
    if mode != "CMD":
        path = (cmd or "").strip().strip("'\"")
        return os.path.basename(path.rstrip("/"))
    toks = _tokens(cmd)
    i = 0
    while i < len(toks):
        t = toks[i]
        if _ENV_ASSIGN.match(t) or t.startswith("-") or os.path.basename(t) in WRAPPERS:
            i += 1
            continue
        break
    if i >= len(toks):
        return ""
    if os.path.basename(toks[i]) in ("bash", "sh", "zsh") and "-c" in toks[i + 1:]:
        inner = toks[toks.index("-c", i) + 1:]
        return program_name(inner[0], "CMD") if inner else ""
    return os.path.basename(toks[i])


def suggest(cmd, mode="CMD"):
    """Vorschlag fuer den Kill-Befehl oder '' (nichts Sinnvolles erkennbar)."""
    toks = _tokens(cmd) if mode == "CMD" else []
    # Ueber Steam gestartet: ein Vorschlag wuerde Steam selbst beenden.
    if "-applaunch" in toks:
        return ""
    # flatpak run <id> -> flatpak kill <id>
    if toks and os.path.basename(toks[0]) == "flatpak" and "run" in toks:
        rest = [t for t in toks[toks.index("run") + 1:] if not t.startswith("-")]
        if rest:
            return f"flatpak kill {shlex.quote(rest[0])}"
    name = program_name(cmd, mode)
    if not name:
        return ""
    return f"pkill -f {shlex.quote(name)}"
