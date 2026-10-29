#!/usr/bin/env python3
"""
core/vrchat_config.py — VRChats eigene config.json (Cache-Groesse)
==================================================================
VRChat liest beim Start eine optionale config.json aus
``%LocalAppData%Low\\VRChat\\VRChat`` (docs.vrchat.com/docs/configuration-file).
Unter Proton liegt dieser Ordner im Prefix:

    <compatdata/438100>/pfx/drive_c/users/steamuser/AppData/LocalLow/VRChat/VRChat/config.json

Hier nur ``cache_size`` (in GB). VRChat-Standard ist 30, kleiner geht laut
Doku nicht. Alle anderen Schluessel in der Datei bleiben unangetastet.
Die Aenderung wirkt erst beim naechsten Start von VRChat.

Bewusst ohne Qt.
"""
import json
import os

import vr_environment as venv
from jsonio import write_json_atomic
from logging_setup import get_logger

log = get_logger("vrchat_config")

CACHE_MIN = 30
CACHE_MAX = 130
CACHE_DEFAULT = 30

_REL = "AppData/LocalLow/VRChat/VRChat/config.json"


def prefix_exists():
    """Gibt es das VRChat-Prefix? (VRChat lief schon einmal unter Proton.)"""
    return os.path.isdir(venv.vrchat_proton_prefix())


def config_path():
    return os.path.join(venv.vrchat_proton_prefix(), _REL)


def _read():
    """Inhalt als dict. utf-8-sig, weil unter Windows angelegte Dateien
    oft ein BOM haben."""
    try:
        with open(config_path(), encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as exc:                                   # noqa: BLE001
        log.warning("VRChat-config.json nicht lesbar: %s", exc)
        return None


def cache_size():
    """Aktuell eingestellte Cache-Groesse in GB (Standard 30)."""
    data = _read() or {}
    try:
        val = int(data.get("cache_size", CACHE_DEFAULT))
    except (TypeError, ValueError):
        val = CACHE_DEFAULT
    return max(CACHE_MIN, min(CACHE_MAX, val))


def set_cache_size(gb):
    """
    Schreibt ``cache_size``. Beim Standardwert wird der Schluessel entfernt,
    damit die Datei nicht unnoetig waechst. Rueckgabe: True bei Erfolg.

    Ist die vorhandene Datei kaputt, wird NICHT ueberschrieben — sonst
    gingen eigene Einstellungen des Nutzers verloren.
    """
    gb = max(CACHE_MIN, min(CACHE_MAX, int(gb)))
    data = _read()
    if data is None:
        return False
    if gb == CACHE_DEFAULT:
        if "cache_size" not in data:
            return True
        data.pop("cache_size", None)
    else:
        data["cache_size"] = gb
    ok = write_json_atomic(config_path(), data)
    if ok:
        log.info("VRChat cache_size -> %s GB (%s)", gb, config_path())
    return ok
