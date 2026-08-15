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
    "openvr_compat_custom": "",
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

    # --- hand_tracking: wird bewusst NICHT mehr geschrieben --------------
    # Seit v1.1.6 gibt es dafuer keinen Schalter mehr im Dashboard (Hand- und
    # Full-Body-Tracking muessen im Headset selbst aktiviert werden). Wuerden
    # wir den Wert trotzdem weiter bei jedem Speichern in WiVRns config.json
    # schreiben, wuerden wir eine Einstellung ueberschreiben, die der Nutzer
    # nur noch in WiVRn selbst setzen kann. Der Schluessel bleibt in UNSERER
    # Config erhalten, damit alte Konfigurationen unveraendert bleiben.

    # --- refresh_rate: WiVRn kennt diesen Schluessel NICHT ---------------
    # Nachgesehen in WiVRns Quelltext: server/driver/configuration.cpp liest
    # aus der config.json genau diese Schluessel — grip-surface, encoder,
    # application, hid-forwarding, debug-gui, use-steamvr-lh,
    # lh-stick-deadzone, bit-depth, tcp-only, port, hostname,
    # publish-service, openvr-compat-path. Ein "refresh_rate" ist in KEINER
    # Version dabei (geprueft bis zurueck zu v0.22), es stand auch nie in
    # docs/configuration.md.
    #
    # Die Bildwiederholrate kommt vom Headset: der Client schickt sie als
    # 'settings_changed' (preferred_refresh_rate) an den Server. Seit WiVRn
    # 25.12 sind alle Video-Einstellungen dorthin umgezogen ("Moved video
    # settings from dashboard to headset").
    #
    # Frueher hat diese App den Schluessel trotzdem geschrieben — er lag
    # wirkungslos in der Datei und erweckte den Eindruck, die Einstellung
    # greife. Er wird jetzt nicht mehr geschrieben und einmalig aufgeraeumt.
    wivrn_data.pop("refresh_rate", None)

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

    # --- Encoder: Schlüsselname hängt an der WiVRn-Version ----------------
    # Bis einschließlich WiVRn 25.11 hieß der Schlüssel "encoders" (Liste),
    # dazu gab es "scale" und "bitrate" auf oberster Ebene.
    #
    # Seit 25.12 heißt er "encoder" (String, Objekt oder Liste), und "scale"
    # sowie "bitrate" gibt es nicht mehr — die Video-Einstellungen werden im
    # Headset gesetzt (Release-Notes 25.12: "Moved video settings from
    # dashboard to headset"). Nachzulesen in server/driver/configuration.cpp.
    #
    # Bisher schrieb diese App IMMER "encoders" und löschte dabei sogar
    # "encoder" — auf aktuellen Versionen wurde die Encoder-Auswahl also
    # doppelt wirkungslos. Jetzt entscheidet die erkannte Serverversion.
    encoder_name = config_data.get("encoder", "Auto").lower()
    codec_name = config_data.get("codec", "Automatic")

    # Codec-Name normalisieren
    if "av1" in codec_name.lower():
        codec = "av1"
    elif "h265" in codec_name.lower() or "265" in codec_name:
        codec = "h265"
    elif "h264" in codec_name.lower() or "264" in codec_name:
        codec = "h264"
    else:
        codec = None  # auto — kein codec-Key setzen

    encoder_obj = None
    if encoder_name != "auto":
        encoder_obj = {"encoder": encoder_name}
        if codec:
            encoder_obj["codec"] = codec

    if venv.wivrn_at_least(25, 12):
        # Neues Format: ein einzelnes Objekt unter "encoder".
        if encoder_obj:
            wivrn_data["encoder"] = encoder_obj
        else:
            wivrn_data.pop("encoder", None)   # Auto: WiVRn wählt selbst
        # "encoders"/"scale"/"bitrate" werden von dieser Version ignoriert.
        # Sie bleiben unangetastet stehen, falls jemand zurückwechselt —
        # gelöscht wird fremde Konfiguration hier grundsätzlich nicht.
    else:
        # Altes Format (<= 25.11)
        res_percent = config_data.get("render_resolution", 100)
        wivrn_data["scale"] = round(res_percent / 100.0, 2)
        wivrn_data["bitrate"] = int(config_data.get("bitrate", 100)) * 1_000_000
        if encoder_obj:
            wivrn_data["encoders"] = [encoder_obj]
        else:
            wivrn_data.pop("encoders", None)

    # --- openvr-compat-path (setzt streaming_tab.py direkt) ---------------
    # Hier bewusst nicht anfassen.

    # --- Ungültige Keys aus alten Versionen entfernen ---
    # "encoder" steht NICHT mehr in dieser Liste: seit 25.12 ist das der
    # gültige Schlüssel.
    for old_key in ["codec", "scale_percent", "foveated_factor",
                    "openvr_runtime", "apps"]:
        wivrn_data.pop(old_key, None)

    if write_json_atomic(wivrn_path, wivrn_data):
        log.info("WiVRn-config.json aktualisiert (%s).", wivrn_path)
    else:
        log.warning("WiVRn-config.json konnte nicht geschrieben werden (%s).", wivrn_path)
