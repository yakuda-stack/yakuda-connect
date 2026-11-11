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


def installed_apps(software_only=True):
    """Installierte Steam-Apps als [{"appid", "name"}], nach Name sortiert.

    Proton, Steam-Runtimes und SteamVR fallen weg. ``software_only``: nur
    Apps, die Steam selbst als Software fuehrt (``type`` = application, z. B.
    VRCFaceTracking) — keine Spiele. Ist Steams appinfo.vdf nicht lesbar oder
    fehlt eine App darin, bleibt sie in der Liste, statt still zu fehlen.
    """
    apps = {}
    for sa in games_db._steamapps_dirs():
        try:
            fnames = os.listdir(sa)
        except OSError:
            continue
        for fname in fnames:
            if not (fname.startswith("appmanifest_") and fname.endswith(".acf")):
                continue
            info = games_db._parse_acf(os.path.join(sa, fname))
            if not info or not info["appid"] or info["appid"] in apps:
                continue
            if (info["appid"] in games_db._APPID_BLACKLIST
                    or games_db._is_steam_tool(info["name"])):
                continue
            apps[info["appid"]] = {"appid": info["appid"],
                                   "name": info["name"] or f"App {info['appid']}"}
    if software_only and apps:
        import steam_appinfo
        commons, ok = steam_appinfo.commons(apps.keys())
        if ok:
            apps = {a: v for a, v in apps.items()
                    if a not in commons
                    or steam_appinfo.app_type(commons[a]) == "application"}
    return sorted(apps.values(), key=lambda a: a["name"].lower())


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
