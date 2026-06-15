#!/usr/bin/env python3
import os
import json

CONFIG_DIR = os.path.expanduser("~/.config/yakuda-connect/config")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
# FIX: Pfad für die offizielle WiVRn Config definiert
WIVRN_CONFIG_FILE = os.path.expanduser("~/.config/wivrn/config.json")

def load_saved_settings():
    """Lädt die Einstellungen aus dem globalen .config-Verzeichnis."""
    # Falls die Datei noch gar nicht existiert, geben wir sichere Standardwerte zurück
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
    """Speichert alle Werte und sorgt dafür, dass der First-Start-Parameter erhalten bleibt."""

    # 1. Sicherstellen, dass die Ordnerstruktur existiert
    os.makedirs(CONFIG_DIR, exist_ok=True)

    # 2. Bestehende Daten einlesen
    current_data = load_saved_settings()

    # Robustheits-Fix: Wenn in der Datei bereits eine 1 steht, darf sie nicht mehr auf 0 fallen,
    # außer setup_state wird explizit als 0 übergeben.
    existing_setup_state = current_data.get("first_time_vr_setup", 0)

    if setup_state is not None:
        first_start_val = setup_state
    else:
        first_start_val = existing_setup_state

    # 3. Das neue Daten-Layout aufbauen
    new_settings = {
        "hand_tracking": hand,
        "full_body_tracking": fbt,
        "steam_tracker": steam,
        "refresh_rate": refresh,
        "autostart_count": count,
        "autostart_apps": apps_data,
        "first_time_vr_setup": first_start_val
    }

    # 4. Streaming-Daten einpflegen
    if streaming_data:
        new_settings.update(streaming_data)
    else:
        for key in ["openvr_compat", "render_resolution", "foveated_encoding", "encoder", "codec", "bitrate"]:
            if key in current_data:
                new_settings[key] = current_data[key]

    # 5. In die Datei schreiben
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(new_settings, f, indent=4)
        print(f"[Config Manager] Einstellungen erfolgreich gespeichert.")

        # JETZT AUCH DIREKT MIT WIVRN SYNCHRONISIEREN!
        sync_with_wivrn(new_settings)

    except Exception as e:
        print(f"[Config Fehler] Konnte Einstellungen nicht schreiben: {e}")


def sync_with_wivrn(config_data):
    """Schreibt die Werte direkt im korrekten Format in die offizielle wivrn.json."""
    wivrn_data = {}
    if os.path.exists(WIVRN_CONFIG_FILE):
        try:
            with open(WIVRN_CONFIG_FILE, 'r') as f:
                content = f.read().strip()
                if content:
                    wivrn_data = json.loads(content)
        except Exception as e:
            print(f"WiVRn-Config konnte nicht gelesen werden: {e}")

    # 1. Dashboard-Optionen synchronisieren
    wivrn_data["hand_tracking"] = config_data.get("hand_tracking", False)

    refresh_rate = config_data.get("refresh_rate", "Auto")
    if refresh_rate == "72":
        wivrn_data["refresh_rate"] = 72
    elif refresh_rate == "90":
        wivrn_data["refresh_rate"] = 90
    else:
        wivrn_data["refresh_rate"] = 0

    autostart_apps = config_data.get("autostart_apps", [])
    wivrn_apps = [app["cmd"] for app in autostart_apps if app["cmd"].strip()]
    wivrn_data["apps"] = wivrn_apps

    # 2. ERWEITERTE STREAMING PARAMETER SYNCHRONISIEREN

    # OpenVR Kompatibilität (wird oft als env oder string von WiVRn genutzt)
    openvr = config_data.get("openvr_compat", "Auto").lower()
    wivrn_data["openvr_runtime"] = openvr if openvr != "auto" else "default"

    # Render Resolution (Prozent zu Faktor konvertieren: 100% -> 1.0, 200% -> 2.0)
    res_percent = config_data.get("render_resolution", 100)
    wivrn_data["scale"] = round(res_percent / 100.0, 2)

    # Foveated Encoding (Prozent zu Faktor konvertieren: 50% -> 0.5)
    fov_percent = config_data.get("foveated_encoding", 50)
    wivrn_data["foveated_factor"] = round(fov_percent / 100.0, 2)

    # Encoder (nvenc, vaapi, vulkan, x264, auto)
    encoder = config_data.get("encoder", "Auto")
    wivrn_data["encoder"] = encoder.lower() if encoder != "Auto" else "auto"

    # Codec (av1, h265, h264, auto)
    codec = config_data.get("codec", "Automatic")
    if "av1" in codec.lower():
        wivrn_data["codec"] = "av1"
    elif codec == "Automatic":
        wivrn_data["codec"] = "auto"
    else:
        wivrn_data["codec"] = codec.lower()

    # Bitrate (0 = Auto)
    bitrate = config_data.get("bitrate", 100)
    wivrn_data["bitrate"] = int(bitrate)

    try:
        os.makedirs(os.path.dirname(WIVRN_CONFIG_FILE), exist_ok=True)
        with open(WIVRN_CONFIG_FILE, 'w') as f:
            json.dump(wivrn_data, f, indent=4)
    except Exception as e:
        print(f"Fehler beim Schreiben der wivrn.json: {e}")
