#!/usr/bin/env python3
"""
core/app_profiles.py — App-Profile: alle Einstellungen speichern und laden
=========================================================================
Ein Profil ist ein Schnappschuss der App-Einstellungen:

  * config.json            ohne die globalen Schluessel (GLOBAL_KEYS)
  * theme.json             Design (Farben, Hintergrund)
  * controls_profiles.json Controls-Tab: gespeicherte Belegungen
  * controls_layout.json   Controls-Tab: Anordnung

Global bleiben (nie im Profil, nie ueberschrieben):

  * Sprache, Merker der Erst-Einrichtung, Installationsstand, AUR-Helfer
  * die Profil-Einstellungen selbst (aktives Profil, Speichern beim Schliessen)
  * die Autostart-Profile im Streaming-Tab — ausser der Schalter
    AUTOSTART_IN_PROFILE_KEY ist an. Dann gehoeren sie zum Profil.

Die Profile liegen in <config_root>/profiles/ und NICHT in config/:
„App zuruecksetzen“ loescht config/, die Profile bleiben, und man kann
danach einfach wieder eins laden.

Laden passiert beim Start (apply_pending): die laufende App merkt sich das
Profil, startet neu, und erst die neue App spielt es ein. So kann die alte
App beim Beenden nichts mehr darueberschreiben.

Kein Qt — mit einfachen Tests pruefbar.
"""
import os
import re
import shutil

import paths
from jsonio import read_json, write_json_atomic
from logging_setup import get_logger

log = get_logger("app_profiles")

FORMAT_VERSION = 1
PROFILE_EXT = ".json"
PENDING_FILE = ".pending"

ACTIVE_KEY = "app_profile_active"
AUTOSAVE_KEY = "app_profile_autosave"
AUTOSTART_IN_PROFILE_KEY = "app_profile_autostart_in_profile"

AUTOSTART_PROFILE_KEYS = ("autostart_profiles", "autostart_profiles_enabled")

GLOBAL_KEYS = {
    ACTIVE_KEY, AUTOSAVE_KEY, AUTOSTART_IN_PROFILE_KEY,
    "language",
    "first_time_vr_setup", "tour_asked", "dashboard_optimize_asked",
    "dashboard_wayvr_asked", "controls_setup_asked",
    "autostart_disconnect_notice_seen",
    "vr_backup_created", "backup_created",
    "runtime_install_method",
    "aur_helper_custom", "arch_helper_choice", "aur_dialog_start_shown",
    "detected_games", "detected_games_untested",
}
GLOBAL_SUFFIXES = ("_asked", "_seen", "_shown")

EXTRA_FILES = ("theme.json", "controls_profiles.json", "controls_layout.json")

_NAME_RE = re.compile(r"^[^/\\\x00-\x1f.][^/\\\x00-\x1f]{0,39}$")


# --------------------------------------------------------------------------- #
#  Orte
# --------------------------------------------------------------------------- #
def profiles_dir():
    return os.path.join(paths.config_root(), "profiles")


def _config_path():
    return paths.config_file("config.json")


def profile_path(name):
    return os.path.join(profiles_dir(), name + PROFILE_EXT)


def valid_name(name):
    """Profilname: 1–40 Zeichen, kein Pfad, kein Punkt am Anfang."""
    if not isinstance(name, str) or name != name.strip():
        return False
    return bool(_NAME_RE.match(name))


def _read_config():
    data = read_json(_config_path(), default={})
    return data if isinstance(data, dict) else {}


def _write_config(data):
    return write_json_atomic(_config_path(), data)


def _set_config_key(key, value):
    data = _read_config()
    data[key] = value
    return _write_config(data)


# --------------------------------------------------------------------------- #
#  Globale Profil-Einstellungen
# --------------------------------------------------------------------------- #
def active_profile():
    name = str(_read_config().get(ACTIVE_KEY, "") or "")
    return name if name and os.path.isfile(profile_path(name)) else ""


def set_active(name):
    return _set_config_key(ACTIVE_KEY, name or "")


def autosave_enabled():
    return bool(_read_config().get(AUTOSAVE_KEY, True))


def set_autosave(on):
    return _set_config_key(AUTOSAVE_KEY, bool(on))


def autostart_in_profile():
    return bool(_read_config().get(AUTOSTART_IN_PROFILE_KEY, False))


def set_autostart_in_profile(on):
    return _set_config_key(AUTOSTART_IN_PROFILE_KEY, bool(on))


def is_global_key(key, autostart_included=None):
    if autostart_included is None:
        autostart_included = autostart_in_profile()
    if key in AUTOSTART_PROFILE_KEYS:
        return not autostart_included
    return key in GLOBAL_KEYS or key.endswith(GLOBAL_SUFFIXES)


# --------------------------------------------------------------------------- #
#  Liste
# --------------------------------------------------------------------------- #
def list_profiles():
    """Namen aller Profile, alphabetisch (Gross/Klein egal)."""
    try:
        names = [f[:-len(PROFILE_EXT)] for f in os.listdir(profiles_dir())
                 if f.endswith(PROFILE_EXT) and not f.startswith(".")]
    except OSError:
        return []
    return sorted(names, key=str.lower)


def exists(name):
    return os.path.isfile(profile_path(name))


# --------------------------------------------------------------------------- #
#  Speichern / Laden
# --------------------------------------------------------------------------- #
def snapshot():
    """Aktuelle Einstellungen als Profil-Daten (ohne globale Schluessel)."""
    include_auto = autostart_in_profile()
    cfg = _read_config()
    settings = {k: v for k, v in cfg.items() if not is_global_key(k, include_auto)}
    files = {}
    for fname in EXTRA_FILES:
        path = paths.config_file(fname)
        if os.path.isfile(path):
            files[fname] = read_json(path, default={})
    return {"format": FORMAT_VERSION, "settings": settings, "files": files,
            "autostart_included": include_auto}


def save_profile(name):
    """Aktuelle Einstellungen unter diesem Namen speichern (ueberschreibt)."""
    if not valid_name(name):
        raise ValueError(f"ungueltiger Profilname: {name!r}")
    os.makedirs(profiles_dir(), exist_ok=True)
    data = snapshot()
    data["name"] = name
    ok = write_json_atomic(profile_path(name), data)
    if ok:
        log.info("Profil gespeichert: %s", name)
    return ok


def _read_profile_file(path):
    data = read_json(path, default=None)
    if not isinstance(data, dict) or not isinstance(data.get("settings"), dict):
        return None
    return data


def load_profile(name):
    """
    Profil in die Einstellungen einspielen. Globale Schluessel der aktuellen
    config.json bleiben erhalten. Rueckgabe: die neue config (dict) oder None.
    """
    data = _read_profile_file(profile_path(name))
    if data is None:
        log.warning("Profil nicht lesbar: %s", name)
        return None
    include_auto = autostart_in_profile()
    current = _read_config()
    new_cfg = {k: v for k, v in current.items() if is_global_key(k, include_auto)}
    for k, v in data["settings"].items():
        if not is_global_key(k, include_auto):
            new_cfg[k] = v
    new_cfg[ACTIVE_KEY] = name
    if not _write_config(new_cfg):
        return None
    files = data.get("files") if isinstance(data.get("files"), dict) else {}
    for fname in EXTRA_FILES:
        target = paths.config_file(fname)
        if fname in files:
            write_json_atomic(target, files[fname])
        elif os.path.isfile(target):
            try:
                os.remove(target)
            except OSError as exc:
                log.warning("%s nicht entfernt: %s", fname, exc)
    log.info("Profil geladen: %s", name)
    return new_cfg


def delete_profile(name):
    try:
        os.remove(profile_path(name))
    except OSError as exc:
        log.warning("Profil %s nicht geloescht: %s", name, exc)
        return False
    if _read_config().get(ACTIVE_KEY) == name:
        set_active("")
    return True


def rename_profile(old, new):
    if not valid_name(new) or exists(new) or not exists(old):
        return False
    data = _read_profile_file(profile_path(old)) or {}
    data["name"] = new
    if not write_json_atomic(profile_path(new), data):
        return False
    os.remove(profile_path(old))
    if _read_config().get(ACTIVE_KEY) == old:
        set_active(new)
    return True


def copy_profile(src, new):
    if not valid_name(new) or exists(new) or not exists(src):
        return False
    data = _read_profile_file(profile_path(src)) or {}
    data["name"] = new
    return write_json_atomic(profile_path(new), data)


def export_profile(name, dest):
    try:
        shutil.copyfile(profile_path(name), dest)
        return True
    except OSError as exc:
        log.warning("Export fehlgeschlagen: %s", exc)
        return False


def import_name(src):
    """Vorgeschlagener Name fuer eine Import-Datei, '' wenn sie kein Profil ist."""
    data = _read_profile_file(src)
    if data is None:
        return ""
    name = str(data.get("name") or os.path.splitext(os.path.basename(src))[0]).strip()
    return name if valid_name(name) else "Import"


def import_profile(src, name):
    data = _read_profile_file(src)
    if data is None or not valid_name(name):
        return False
    os.makedirs(profiles_dir(), exist_ok=True)
    data["name"] = name
    return write_json_atomic(profile_path(name), data)


# --------------------------------------------------------------------------- #
#  Wechsel ueber einen Neustart
# --------------------------------------------------------------------------- #
def _pending_path():
    return os.path.join(profiles_dir(), PENDING_FILE)


def request_switch(name):
    """Beim naechsten Start dieses Profil laden."""
    os.makedirs(profiles_dir(), exist_ok=True)
    return write_json_atomic(_pending_path(), {"name": name})


def apply_pending():
    """
    Beim App-Start aufrufen, BEVOR Einstellungen gelesen werden.
    Rueckgabe: die neue config (dict), wenn ein Profil geladen wurde, sonst None.
    """
    path = _pending_path()
    if not os.path.isfile(path):
        return None
    data = read_json(path, default={})
    try:
        os.remove(path)
    except OSError as exc:
        log.warning("%s nicht entfernt: %s", path, exc)
    name = data.get("name") if isinstance(data, dict) else ""
    if not name or not exists(name):
        return None
    return load_profile(name)
