#!/usr/bin/env python3
"""
core/xr_openvr_link.py — OpenVR-Spiel (obah) <-> xrBinder-Name finden
=====================================================================
Die Stick-Deadzone wirkt nur ueber xrBinder (OpenXR). OpenVR-Spiele laufen
per xrizer aber auch ueber OpenXR — xrBinder kennt sie unter dem Namen, den
xrizer aus der .exe bildet (z. B. "VRChat" oder bei Unreal ein Pfad wie
"GalGun2/Binaries/Win64/GalGun2-Win64-Shipping").

Damit der Deadzone-Regler auch in der OpenVR-Ansicht geht, suchen wir zum
gewaehlten Spiel den passenden xrBinder-Namen:

  1. schon einmal gefunden -> links.json
  2. Spiel laeuft gerade   -> SteamAppId in /proc/<pid>/environ
  3. Datei im Spielordner  -> <name>.exe (bzw. <name>) existiert dort

Kein Qt — mit einfachen Tests pruefbar.
"""
import os

import xrbinder as xb
from jsonio import read_json, update_json

MAX_DEPTH = 6
MAX_DIRS = 3000


def _links_path():
    return os.path.join(xb.state_dir(), "openvr_links.json")


def _remembered(ident, app_names):
    data = read_json(_links_path(), default={})
    name = data.get(ident) if isinstance(data, dict) else None
    return name if name in app_names else None


def remember(ident, app_name):
    update_json(_links_path(), {ident: app_name})


def _steam_appid_of(pid):
    try:
        with open(f"/proc/{int(pid)}/environ", "rb") as fh:
            raw = fh.read()
    except (OSError, ValueError):
        return ""
    for entry in raw.split(b"\0"):
        if entry.startswith(b"SteamAppId=") or entry.startswith(b"SteamGameId="):
            return entry.split(b"=", 1)[1].decode("utf-8", "replace")
    return ""


def _match_running(appid, app_names, pid_of):
    if not appid or pid_of is None:
        return None
    for name in app_names:
        pid = pid_of(name)
        if pid and _steam_appid_of(pid) == str(appid):
            return name
    return None


def _wanted(name):
    """Dateinamen (klein), die zu diesem xrBinder-Namen passen."""
    base = xb.display_app_name(name).lower()
    return {base + ".exe", base}


def _match_files(folder, app_names):
    if not folder or not os.path.isdir(folder):
        return None
    for name in app_names:
        if "/" in name:
            for cand in (name + ".exe", name):
                if os.path.isfile(os.path.join(folder, cand)):
                    return name
    wanted = {}
    for name in app_names:
        for w in _wanted(name):
            wanted.setdefault(w, name)
    root_depth = folder.rstrip(os.sep).count(os.sep)
    seen = 0
    for root, dirs, files in os.walk(folder):
        seen += 1
        if seen > MAX_DIRS:
            break
        if root.count(os.sep) - root_depth >= MAX_DEPTH:
            dirs[:] = []
        for f in files:
            hit = wanted.get(f.lower())
            if hit:
                return hit
    return None


def find_app(game, app_names, pid_of=None):
    """xrBinder-Name zum obah-Spiel oder None. app_names: alle bekannten Namen."""
    names = [n for n in app_names if xb.valid_app_name(n)]
    if game is None or not names:
        return None
    name = _remembered(game.ident, names)
    if name:
        return name
    name = (_match_running(game.appid, names, pid_of)
            or _match_files(game.game_folder, names))
    if name:
        remember(game.ident, name)
    return name


# --------------------------------------------------------------------------- #
#  Haken „nicht xrizer“ im Deadzone-Tab: dann deadzone_pct (SteamVR) statt
#  xrBinder. Vorauswahl: WiVRn laesst OpenVR in Ruhe (= SteamVR). Hat der
#  Nutzer den Haken einmal gesetzt/entfernt, gilt seine Wahl.
# --------------------------------------------------------------------------- #
KEY_STEAMVR = "obah_deadzone_steamvr"


def _app_config():
    import paths
    return paths.config_file("config.json")


def steamvr_mode():
    data = read_json(_app_config(), default={})
    if isinstance(data, dict) and KEY_STEAMVR in data:
        return bool(data[KEY_STEAMVR])
    try:
        import vr_environment as venv
        return venv.current_openvr_compat()[0] == venv.OPENVR_DISABLED
    except Exception:                                      # noqa: BLE001
        return False


def set_steamvr_mode(on):
    """Nur aufrufen, wenn der Nutzer den Haken selbst umgestellt hat."""
    update_json(_app_config(), {KEY_STEAMVR: bool(on)})
