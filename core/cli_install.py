#!/usr/bin/env python3
"""
core/cli_install.py — Kurzbefehle (YC-*) einrichten, Terminal oeffnen
====================================================================
Ohne Qt, damit auch der Terminal-Modus es nutzen kann.

Die Kurzbefehle sind winzige Shell-Skripte, die den richtigen Startbefehl
mit ``--cli <befehl>`` aufrufen. Welcher das ist, haengt an der
Installationsart:

    AUR       /usr/bin/yakuda-connect        (Kurzbefehle liefert das Paket mit)
    curl      /usr/local/bin/yakuda-connect  (Kurzbefehle legt install.sh an)
    AppImage  $APPIMAGE                      (Pfad der .AppImage-Datei)
    Quellcode python3 <ordner>/starter.py

Fuer AppImage und Quellcode legt der Knopf in den Einstellungen die Skripte
in ~/.local/bin an — ohne root. Beim AppImage steht der Pfad der Datei fest
im Skript; wird sie verschoben oder aktualisiert (neuer Dateiname), einfach
den Knopf noch einmal druecken.
"""
import os
import shlex
import shutil
import subprocess
import sys

from logging_setup import get_logger

log = get_logger("cli_install")

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Kurzbefehl -> Befehl im CLI
SHIMS = {
    "YC-help": "help",
    "YC-status": "status",
    "YC-wivrn-toggle": "wivrn-toggle",
    "YC-openvr": "openvr",
    "YC-encoder": "encoder",
    "YC-GPU": "gpu",
    "YC-killapps": "killapps",
    "YC-autostart-reset": "autostart-reset",
    "YC-pairing": "pairing",
}

# Erkennungszeile: nur Dateien mit dieser Markierung werden ueberschrieben
# oder geloescht — nie ein fremdes Programm gleichen Namens.
MARKER = "# yakuda-connect cli shim"

USER_BIN = os.path.join(os.path.expanduser("~"), ".local", "bin")


# --------------------------------------------------------------------------- #
#  Installationsart
# --------------------------------------------------------------------------- #
def install_kind():
    """'appimage' | 'aur' | 'curl' | 'source'"""
    if os.environ.get("APPIMAGE"):
        return "appimage"
    real = os.path.realpath(APP_DIR)
    if real == "/usr/share/yakuda-connect":
        return "aur"
    if real == "/opt/yakuda-connect":
        return "curl"
    return "source"


def launcher_argv(kind=None):
    """Befehl, der yakuda-connect startet (ohne Argumente)."""
    kind = kind or install_kind()
    if kind == "appimage":
        return [os.environ["APPIMAGE"]]
    if kind == "aur" and os.path.exists("/usr/bin/yakuda-connect"):
        return ["/usr/bin/yakuda-connect"]
    if kind == "curl" and os.path.exists("/usr/local/bin/yakuda-connect"):
        return ["/usr/local/bin/yakuda-connect"]
    return [sys.executable or "python3", os.path.join(APP_DIR, "starter.py")]


def cli_argv(command=None):
    """Befehl fuer den Terminal-Modus, z. B. [..., '--cli', 'gpu']."""
    argv = launcher_argv() + ["--cli"]
    return argv + [command] if command else argv


# --------------------------------------------------------------------------- #
#  Kurzbefehle
# --------------------------------------------------------------------------- #
def shim_text(command, launcher):
    return (f"#!/bin/sh\n{MARKER}\n"
            f"exec {shlex.join(launcher)} --cli {command} \"$@\"\n")


def system_shims_present():
    """Hat das Paket (AUR/curl) die Kurzbefehle schon systemweit angelegt?"""
    return any(os.path.exists(os.path.join(d, "YC-help"))
               for d in ("/usr/bin", "/usr/local/bin"))


def _is_ours(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return MARKER in fh.read(512)
    except OSError:
        return False


def install_user_shims(target_dir=USER_BIN, launcher=None):
    """
    Legt die YC-*-Skripte an. Rueckgabe: (angelegt, uebersprungen).
    Uebersprungen wird eine fremde Datei gleichen Namens.
    """
    launcher = launcher or launcher_argv()
    os.makedirs(target_dir, exist_ok=True)
    written, skipped = [], []
    for name, command in SHIMS.items():
        path = os.path.join(target_dir, name)
        if os.path.exists(path) and not _is_ours(path):
            skipped.append(name)
            continue
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(shim_text(command, launcher))
        os.chmod(path, 0o755)
        written.append(name)
    log.info("CLI-Kurzbefehle in %s: %s (uebersprungen: %s)",
             target_dir, written, skipped)
    return written, skipped


def remove_user_shims(target_dir=USER_BIN):
    removed = []
    for name in SHIMS:
        path = os.path.join(target_dir, name)
        if os.path.exists(path) and _is_ours(path):
            os.remove(path)
            removed.append(name)
    return removed


def user_bin_in_path():
    parts = [os.path.realpath(p) for p in os.environ.get("PATH", "").split(":") if p]
    return os.path.realpath(USER_BIN) in parts


def setup_commands():
    """
    Das, was der Knopf tut. Rueckgabe: dict fuer die Meldung.

        kind       Installationsart
        system     True, wenn das Paket die Befehle schon mitbringt
        written    angelegte Kurzbefehle
        skipped    fremde Dateien, nicht angefasst
        path_ok    liegt ~/.local/bin im PATH?
    """
    kind = install_kind()
    result = {"kind": kind, "system": False, "written": [], "skipped": [],
              "path_ok": True, "dir": USER_BIN}
    if kind in ("aur", "curl") and system_shims_present():
        result["system"] = True
        return result
    result["written"], result["skipped"] = install_user_shims()
    result["path_ok"] = user_bin_in_path()
    return result


# --------------------------------------------------------------------------- #
#  Terminal oeffnen
# --------------------------------------------------------------------------- #
# (Programm, Argumente vor dem Befehl). Reihenfolge: gaengige Desktops zuerst.
_TERMINALS = [
    ("x-terminal-emulator", ["-e"]),
    ("konsole", ["-e"]),
    ("gnome-terminal", ["--"]),
    ("kgx", ["--"]),
    ("ptyxis", ["--"]),
    ("xfce4-terminal", ["-x"]),
    ("mate-terminal", ["-x"]),
    ("lxterminal", ["-e"]),
    ("tilix", ["-e"]),
    ("alacritty", ["-e"]),
    ("kitty", []),
    ("foot", []),
    ("wezterm", ["start", "--"]),
    ("xterm", ["-e"]),
]


def terminal_command(inner):
    """Befehlszeile, die ``inner`` in einem neuen Terminalfenster startet."""
    custom = os.environ.get("TERMINAL", "").strip()
    if custom and shutil.which(custom.split()[0]):
        return shlex.split(custom) + ["-e"] + inner
    for program, args in _TERMINALS:
        if shutil.which(program):
            return [program] + args + inner
    return None


def open_terminal():
    """Terminal mit dem CLI-Menue oeffnen. True bei Erfolg."""
    cmd = terminal_command(cli_argv())
    if not cmd:
        log.warning("Kein Terminalprogramm gefunden.")
        return False
    # Die AppImage-Umgebung (PYTHONPATH, PATH ins eingehaengte Abbild) nicht
    # an das Terminal vererben — der Startbefehl richtet sie selbst neu ein.
    env = dict(os.environ)
    if install_kind() == "appimage":
        for key in ("PYTHONPATH", "PYTHONHOME", "LD_LIBRARY_PATH"):
            env.pop(key, None)
    try:
        subprocess.Popen(cmd, env=env, start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError as exc:
        log.warning("Terminal konnte nicht gestartet werden: %s", exc)
        return False
    log.info("Terminal-Modus geoeffnet: %s", cmd)
    return True
