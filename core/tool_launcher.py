#!/usr/bin/env python3
"""
core/tool_launcher.py — installierte Werkzeuge starten
======================================================
Der Tools-Tab und der Controls-Tab starten dieselben Programme, und beide
stehen vor denselben zwei Fragen:

1. WO liegt der Startbefehl?
   Die App erbt den PATH der Desktop-Sitzung. Darin fehlen je nach
   Distribution ``~/.local/bin`` (dorthin verlinkt der AppImage-Installer)
   und ``~/.cargo/bin`` (dorthin baut Cargo). Ein blosses
   ``subprocess.Popen(["wayvr"])`` scheitert dann mit "No such file", obwohl
   das Programm installiert ist.

2. Fenster oder Terminal?
   Die meisten Eintraege sind Programme mit eigenem Fenster — die sollen
   einfach starten. obah ist eine TUI, XR HOTAS und adb schreiben auf die
   Konsole: ohne Terminal sieht man von ihnen gar nichts. Solche Eintraege
   tragen in tools.json ``"terminal": true``.

Reihenfolge beim Suchen: ``~/.local/bin`` (AppImage), ``~/.cargo/bin``
(Cargo), dann PATH. Findet sich nichts und ist das Werkzeug als Flatpak
installiert, wird ``flatpak run <id>`` genommen.

Dieses Modul startet nur — es prueft NICHT, ob etwas installiert ist. Das
weiss der Tools-Tab aus seinem Status-Cache und gibt es als ``status``
herein.
"""
import os
import shlex
import shutil
import subprocess

from logging_setup import get_logger

log = get_logger("tool_launcher")

HOME = os.path.expanduser("~")

# Ordner, die im PATH fehlen koennen, aber unsere eigenen Installationen
# enthalten. Reihenfolge = Vorrang.
EXTRA_BIN_DIRS = (os.path.join(HOME, ".local", "bin"),
                  os.path.join(HOME, ".cargo", "bin"))


def resolve_binary(cmd):
    """
    Vollstaendiger Pfad zum Startbefehl — oder None.

    ``cmd`` darf schon ein Pfad sein; dann wird nur geprueft, ob er
    ausfuehrbar ist.
    """
    cmd = (cmd or "").strip()
    if not cmd:
        return None
    if os.path.sep in cmd:
        return cmd if os.access(cmd, os.X_OK) else None
    for folder in EXTRA_BIN_DIRS:
        cand = os.path.join(folder, cmd)
        if os.access(cand, os.X_OK):
            return cand
    return shutil.which(cmd)


def build_command(tool, status=None):
    """
    Argumentliste zum Starten — oder None, wenn nichts zu finden ist.

    ``status`` ist der Eintrag aus dem Status-Cache des Tools-Tabs
    (appimage_installed, flatpak_installed, ...). Fehlt er, wird nur nach
    dem Startbefehl gesucht.
    """
    status = status if isinstance(status, dict) else {}
    if status.get("steam_installed") and not any(
            status.get(k) for k in ("appimage_installed", "pm_installed",
                                    "flatpak_installed", "cargo_installed")):
        import steam_tools
        argv = steam_tools.launch_argv(tool.get("steam_appid"))
        if argv:
            return argv
    cmd = (tool.get("start_cmd") or tool.get("key") or "").strip()
    binary = resolve_binary(cmd)
    if binary:
        args = []
        # launch_args gelten laut programs.py der AppImage (VRCX:
        # "--no-install --no-desktop"). Einer AUR- oder Flatpak-Fassung
        # dieselben Schalter unterzuschieben, kann sie zum Abbruch bringen.
        if status.get("appimage_installed") and tool.get("launch_args"):
            args = shlex.split(tool["launch_args"])
        return [binary] + args
    if status.get("flatpak_installed") and tool.get("flatpak_id"):
        return ["flatpak", "run", tool["flatpak_id"]]
    return None


def wants_terminal(tool):
    """Kommandozeilenprogramm? (tools.json: "terminal": true)"""
    return bool(tool.get("terminal"))


def terminal_wrapper(argv, exit_text, enter_text):
    """
    Befehl in eine Shell-Zeile fuer ein Terminalfenster packen.

    Das Fenster bleibt am Ende offen (``read``), sonst ist eine
    Fehlermeldung genau so lange zu sehen, wie das Fenster existiert.
    """
    inner = " ".join(shlex.quote(a) for a in argv)
    return (f"{inner}; rc=$?; echo; "
            f"if [ $rc -ne 0 ]; then echo \"{exit_text} $rc\"; fi; "
            f"read -rp \"{enter_text}\" _")


def start(tool, status=None, terminal=None, texts=None):
    """
    Werkzeug starten.

    terminal : (programm, flags) aus install_worker.find_terminal() — nur
               noetig, wenn das Werkzeug ein Terminal will.
    texts    : {"exit_code": ..., "press_enter": ...} fuer die Zeilen im
               Terminalfenster.

    Rueckgabe: der Popen. Ausnahmen:
      FileNotFoundError — Startbefehl nicht gefunden
      RuntimeError      — Terminal noetig, aber keins vorhanden
      OSError           — Start selbst fehlgeschlagen
    """
    argv = build_command(tool, status)
    if not argv:
        raise FileNotFoundError(tool.get("start_cmd") or tool.get("key") or "")
    texts = texts or {}
    if wants_terminal(tool):
        if not terminal or not terminal[0]:
            raise RuntimeError("no terminal")
        program, flags = terminal
        line = terminal_wrapper(argv, texts.get("exit_code", "Exit code"),
                                texts.get("press_enter", "Press enter ... "))
        argv = [program] + list(flags or []) + ["bash", "-c", line]
    log.info("Starte %s: %s", tool.get("key", "?"), " ".join(argv))
    # start_new_session: das Programm haengt danach nicht mehr an der App —
    # wird yakuda-connect beendet, laeuft es weiter.
    return subprocess.Popen(argv, start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
