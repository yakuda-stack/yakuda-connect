#!/usr/bin/env python3
"""
core/steam_tools.py — Werkzeuge, die ueber Steam installiert werden
===================================================================
tools.json: ``"install_methods": [..., "steam"]`` und ``"steam_appid": "..."``.
Installieren und Entfernen uebernimmt Steam selbst: die App oeffnet nur den
passenden steam://-Link. Ob etwas installiert ist, zeigt die appmanifest-Datei
in einer Steam-Bibliothek.

``"steam_beta"`` nennt einen Beta-Zweig, den man in Steam selbst waehlen muss.

Kein Qt — mit einfachen Tests pruefbar.
"""
import os
import shlex
import shutil
import subprocess

import games as games_db
import vr_environment as venv
from logging_setup import get_logger

log = get_logger("steam_tools")


def _client_cmd():
    """Aufruf des Steam-Clients oder None."""
    if shutil.which("steam"):
        return ["steam"]
    if venv.steam_is_flatpak() and shutil.which("flatpak"):
        return ["flatpak", "run", "com.valvesoftware.Steam"]
    return None


def available():
    return _client_cmd() is not None


def is_installed(appid):
    name = f"appmanifest_{appid}.acf"
    return any(os.path.isfile(os.path.join(d, name)) for d in games_db._steamapps_dirs())


def launch_argv(appid):
    client = _client_cmd()
    return client + ["-applaunch", str(appid)] if client else None


def autostart_command(appid):
    """Startbefehl als Text fuer die Autostart-Liste oder ''."""
    argv = launch_argv(appid)
    return shlex.join(argv) if argv else ""


def _open(url):
    client = _client_cmd()
    if client is None:
        return False
    try:
        subprocess.Popen(client + [url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError as exc:
        log.warning("Steam-Link %s nicht geoeffnet: %s", url, exc)
        return False


def install(appid):
    return _open(f"steam://install/{appid}")


def uninstall(appid):
    return _open(f"steam://uninstall/{appid}")
