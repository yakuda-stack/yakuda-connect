#!/usr/bin/env python3
import os
import json
import vr_environment as venv

CONFIG_DIR = os.path.expanduser("~/.config/yakuda-connect/config")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
# Fallback-Konstante (nativ). Der tatsächliche Pfad wird zur Laufzeit
# methoden-abhängig über venv.wivrn_config_file() bestimmt.
WIVRN_CONFIG_FILE = os.path.expanduser("~/.config/wivrn/config.json")

# Pfad eines früher von WiVRn benutzten Autostart-Launcher-Skripts.
# Wird nicht mehr erzeugt — nur noch aufgeräumt, falls es aus einer älteren
# Version übrig ist (Autostart läuft jetzt über main.py).
AUTOSTART_LAUNCHER = os.path.expanduser("~/.config/yakuda-connect/autostart-launcher.sh")


def load_saved_settings():
    if not os.path.exists(CONFIG_FILE):
        return {
            "hand_tracking": False,
            "full_body_tracking": False,
            "steam_tracker": False,
            "refresh_rate": "90",
            "autostart_count": "0",
            "autostart_apps": [],
            "first_time_vr_setup": 0,
            "language": "en",
            "streaming_data": {
                "openvr_compat": "Auto",
                "render_resolution": 100,
                "foveated_encoding": 50,
                "encoder": "Auto",
                "codec": "Automatic",
                "bitrate": 100
            }
        }

    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Config Fehler] Konnte Einstellungen nicht lesen: {e}")
        return {}


def save_all_settings(hand, fbt, steam, refresh, count, apps_data, streaming_data=None, setup_state=None):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    current_data = load_saved_settings()

    existing_setup_state = current_data.get("first_time_vr_setup", 0)
    if setup_state is not None:
        first_start_val = setup_state
    else:
        first_start_val = existing_setup_state

    new_settings = {
        "hand_tracking": hand,
        "full_body_tracking": fbt,
        "steam_tracker": steam,
        "refresh_rate": refresh,
        "autostart_count": count,
        "autostart_apps": apps_data,
        "first_time_vr_setup": first_start_val
    }

    # Sonstige Keys aus der bestehenden Config NICHT verlieren
    # (z. B. Backup-Flag, Sprache, gemerkte Installationsmethode).
    for extra_key in ("vr_backup_created", "language", "runtime_install_method"):
        if extra_key in current_data:
            new_settings[extra_key] = current_data[extra_key]

    if streaming_data:
        new_settings.update(streaming_data)
    else:
        for key in ["openvr_compat", "render_resolution", "foveated_encoding", "encoder", "codec", "bitrate"]:
            if key in current_data:
                new_settings[key] = current_data[key]

    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(new_settings, f, indent=4)
        print(f"[Config Manager] Einstellungen erfolgreich gespeichert.")
        sync_with_wivrn(new_settings)
    except Exception as e:
        print(f"[Config Fehler] Konnte Einstellungen nicht schreiben: {e}")


def sync_with_wivrn(config_data):
    """
    Schreibt die Werte im korrekten Format laut WiVRn-Dokumentation:
    https://github.com/WiVRn/WiVRn/blob/master/docs/configuration.md
    """
    wivrn_data = {}
    wivrn_path = venv.wivrn_config_file()
    if os.path.exists(wivrn_path):
        try:
            with open(wivrn_path, 'r') as f:
                content = f.read().strip()
                if content:
                    wivrn_data = json.loads(content)
        except Exception as e:
            print(f"WiVRn-Config konnte nicht gelesen werden: {e}")

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
    except Exception:
        pass

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

    try:
        os.makedirs(os.path.dirname(wivrn_path), exist_ok=True)
        with open(wivrn_path, 'w') as f:
            json.dump(wivrn_data, f, indent=4)
        print(f"[WiVRn Sync] config.json erfolgreich aktualisiert ({wivrn_path}).")
    except Exception as e:
        print(f"Fehler beim Schreiben der wivrn.json: {e}")
