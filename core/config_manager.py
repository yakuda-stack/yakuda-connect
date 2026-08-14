#!/usr/bin/env python3
import os

import paths
import vr_environment as venv
from jsonio import read_json, write_json_atomic

from logging_setup import get_logger

log = get_logger("config_manager")


CONFIG_DIR = paths.config_dir()
CONFIG_FILE = paths.config_file("config.json")
# Fallback-Konstante (nativ). Der tatsächliche Pfad wird zur Laufzeit
# methoden-abhängig über venv.wivrn_config_file() bestimmt.
WIVRN_CONFIG_FILE = os.path.expanduser("~/.config/wivrn/config.json")

# Pfad eines früher von WiVRn benutzten Autostart-Launcher-Skripts.
# Wird nicht mehr erzeugt — nur noch aufgeräumt, falls es aus einer älteren
# Version übrig ist (Autostart läuft jetzt über main.py).
AUTOSTART_LAUNCHER = os.path.join(paths.config_root(), "autostart-launcher.sh")


# Werte, die eine frisch angelegte Config bekommt. Sie werden beim Laden
# UNTER die vorhandenen Werte gelegt — fehlt ein Schlüssel in einer alten
# Config, greift der Standard, statt dass der Aufrufer None bekommt.
DEFAULT_SETTINGS = {
    "hand_tracking": False,
    "full_body_tracking": False,
    "steam_tracker": False,
    "refresh_rate": "90",
    "autostart_count": "0",
    "autostart_apps": [],
    "first_time_vr_setup": 0,
    "language": "en",
    "openvr_compat": "Auto",
    "render_resolution": 100,
    "foveated_encoding": 50,
    "encoder": "Auto",
    "codec": "Automatic",
    "bitrate": 100,
}


def load_saved_settings():
    """
    Einstellungen laden. Fehlende Schlüssel werden aus DEFAULT_SETTINGS
    ergänzt, sodass Aufrufer sich auf ihr Vorhandensein verlassen können.
    Eine defekte Datei wird von jsonio zur Seite gelegt (.broken) statt
    überschrieben — dann startet die App mit Standardwerten.
    """
    data = read_json(CONFIG_FILE, default={})
    if not isinstance(data, dict):
        log.warning("config.json enthält kein Objekt — nutze Standardwerte.")
        data = {}
    merged = dict(DEFAULT_SETTINGS)
    merged.update(data)
    return merged


def save_all_settings(hand, fbt, steam, refresh, count, apps_data, streaming_data=None, setup_state=None):
    """
    Einstellungen speichern.

    Früher wurde hier ein NEUES Dict gebaut und alte Schlüssel über eine von
    Hand gepflegte Liste ("vr_backup_created", "language", ...) hinüber-
    gerettet. Jeder Schlüssel, den jemand anderswo schrieb und hier zu
    ergänzen vergaß, verschwand beim nächsten Speichern stillschweigend.

    Jetzt gilt umgekehrt: die vorhandene Config ist die Basis, und es werden
    nur die Felder überschrieben, die diese Funktion wirklich verantwortet.
    Unbekannte Schlüssel bleiben automatisch erhalten.
    """
    current = read_json(CONFIG_FILE, default={})
    if not isinstance(current, dict):
        current = {}

    current.update({
        "hand_tracking": hand,
        "full_body_tracking": fbt,
        "steam_tracker": steam,
        "refresh_rate": refresh,
        "autostart_count": count,
        "autostart_apps": apps_data,
    })

    # first_time_vr_setup nur anfassen, wenn der Aufrufer einen Wert vorgibt.
    if setup_state is not None:
        current["first_time_vr_setup"] = setup_state
    else:
        current.setdefault("first_time_vr_setup", 0)

    if streaming_data:
        current.update(streaming_data)

    if not write_json_atomic(CONFIG_FILE, current):
        # Nicht weiter mit WiVRn synchronisieren, wenn schon unsere eigene
        # Datei nicht geschrieben werden konnte — dann stimmt etwas
        # Grundlegendes nicht (volle Platte, Rechte).
        log.error("Einstellungen konnten nicht gespeichert werden.")
        return

    log.info("Einstellungen gespeichert (%s).", CONFIG_FILE)
    sync_with_wivrn(current)


def sync_with_wivrn(config_data):
    """
    Schreibt die Werte im korrekten Format laut WiVRn-Dokumentation:
    https://github.com/WiVRn/WiVRn/blob/master/docs/configuration.md

    ACHTUNG: Das ist die Konfiguration eines FREMDEN Programms. Sie wird
    gelesen, gezielt ergänzt und atomar zurückgeschrieben — niemals neu
    aufgebaut. Zerlegen wir diese Datei, startet WiVRn nicht mehr, und der
    Nutzer sucht den Fehler zu Recht erst einmal bei WiVRn.
    """
    wivrn_path = venv.wivrn_config_file()
    wivrn_data = read_json(wivrn_path, default={})
    if not isinstance(wivrn_data, dict):
        log.warning("WiVRn-config.json enthält kein Objekt — wird neu aufgebaut.")
        wivrn_data = {}

    # --- hand_tracking (bool) ---
    wivrn_data["hand_tracking"] = config_data.get("hand_tracking", False)

    # --- refresh_rate (int, 0 = auto) ---
    refresh_rate = config_data.get("refresh_rate", "Auto")
    if refresh_rate == "72":
        wivrn_data["refresh_rate"] = 72
    elif refresh_rate == "90":
        wivrn_data["refresh_rate"] = 90
    else:
        wivrn_data["refresh_rate"] = 0  # 0 = automatisch laut WiVRn

    # --- application (Autostart) ---
    # Autostart läuft NICHT mehr über WiVRn.
    #
    # Grund: Programme, die WiVRn über den 'application'-Key startet, laufen in
    # der Umgebung des Servers und erben NICHT die Variablen der Desktop-Sitzung
    # (DISPLAY/WAYLAND_DISPLAY, XDG_RUNTIME_DIR, DBus-Adresse, ...). Dadurch
    # starten WayVR, OSC Leash & Co. unzuverlässig oder gar nicht.
    #
    # Stattdessen startet yakuda-connect die Programme jetzt selbst direkt aus
    # der laufenden Sitzung heraus (siehe main.py: Einweg-Timer, der auf
    # is_headset_connected() wartet). So erben sie alle nötigen Umgebungs-
    # variablen. Hier wird der 'application'-Key daher entfernt und ein evtl.
    # vorhandenes altes Launcher-Skript aufgeräumt.
    wivrn_data.pop("application", None)
    try:
        if os.path.exists(AUTOSTART_LAUNCHER):
            os.remove(AUTOSTART_LAUNCHER)
    except Exception as exc:
        log.debug("sync_with_wivrn: ignoriert — %s", exc)

    # --- scale (float, render resolution) ---
    # 100% -> 1.0, 150% -> 1.5
    res_percent = config_data.get("render_resolution", 100)
    wivrn_data["scale"] = round(res_percent / 100.0, 2)

    # --- encoders (Liste von Objekten laut WiVRn-Doku) ---
    # Format: [{"encoder": "vaapi", "codec": "h265"}, ...]
    # Bitrate: in Bits/s angeben (100 Mbps = 100_000_000)
    encoder_name = config_data.get("encoder", "Auto").lower()
    codec_name = config_data.get("codec", "Automatic")
    bitrate_mbps = config_data.get("bitrate", 100)

    # Codec-Name normalisieren
    if "av1" in codec_name.lower():
        codec = "av1"
    elif "h265" in codec_name.lower() or "265" in codec_name:
        codec = "h265"
    elif "h264" in codec_name.lower() or "264" in codec_name:
        codec = "h264"
    else:
        codec = None  # auto — kein codec-Key setzen

    # Bitrate in Bits/s (WiVRn erwartet das so)
    bitrate_bps = int(bitrate_mbps) * 1_000_000
    wivrn_data["bitrate"] = bitrate_bps

    # Encoder-Objekt aufbauen
    if encoder_name != "auto":
        encoder_obj = {"encoder": encoder_name}
        if codec:
            encoder_obj["codec"] = codec
        wivrn_data["encoders"] = [encoder_obj]
    else:
        # Auto: WiVRn wählt selbst — kein "encoders" key setzen
        wivrn_data.pop("encoders", None)

    # --- openvr-compat-path (wird von streaming_tab.py direkt gesetzt, hier nicht überschreiben) ---
    # Nicht anfassen — streaming_tab.py schreibt das direkt

    # --- Ungültige Keys aus alten Versionen entfernen ---
    for old_key in ["encoder", "codec", "scale_percent", "foveated_factor",
                     "openvr_runtime", "apps"]:
        wivrn_data.pop(old_key, None)

    if write_json_atomic(wivrn_path, wivrn_data):
        log.info("WiVRn-config.json aktualisiert (%s).", wivrn_path)
    else:
        log.warning("WiVRn-config.json konnte nicht geschrieben werden (%s).", wivrn_path)
