#!/usr/bin/env python3
import os
import json
import shlex

CONFIG_DIR = os.path.expanduser("~/.config/yakuda-connect/config")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
WIVRN_CONFIG_FILE = os.path.expanduser("~/.config/wivrn/config.json")

# Launcher-Skript, das WiVRn über den 'application'-Key beim Verbinden startet.
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


def write_autostart_launcher(apps_data):
    """
    Erzeugt ein Bash-Skript, das alle aktiven Autostart-Programme startet.
    Wird von WiVRn über den 'application'-Key aufgerufen, sobald das Headset
    verbindet — dadurch braucht unser Tool dafür kein Sekunden-Polling mehr.

      - CMD (ohne Debug)  -> startet still im Hintergrund.
      - CMD mit Debug     -> startet in einem sichtbaren Terminal.
      - Custom Path       -> wie CMD, nur dass der ganze Eintrag ein Pfad ist.
      - 'setsid' löst die Programme vom Launcher, damit sie weiterlaufen,
        wenn er endet (gewollt: sie sollen die Session über laufen).

    Sicherheit: Vor dem Start wird geprüft, ob der Befehl bzw. Pfad überhaupt
    existiert. Fehlt er, wird der Eintrag übersprungen und eine Warnung auf
    stderr ausgegeben (taucht im WiVRn-Server-Log auf), statt still zu scheitern.

    Gibt den Skript-Pfad zurück, oder None wenn keine Programme aktiv sind.
    """
    active = [a for a in (apps_data or []) if a.get("cmd", "").strip()]

    # Keine aktiven Einträge -> evtl. altes Skript entfernen
    if not active:
        try:
            if os.path.exists(AUTOSTART_LAUNCHER):
                os.remove(AUTOSTART_LAUNCHER)
        except Exception:
            pass
        return None

    # Terminal nur ermitteln, wenn überhaupt ein Debug-Eintrag dabei ist
    terminal, flags = (None, None)
    if any(a.get("debug") for a in active):
        try:
            from install_worker import find_terminal
            terminal, flags = find_terminal()
        except Exception:
            terminal, flags = None, None

    lines = [
        "#!/usr/bin/env bash",
        "# Automatisch erzeugt von yakuda-connect — NICHT von Hand bearbeiten.",
        "# Startet die Autostart-Programme, sobald WiVRn das Headset verbindet.",
        "",
    ]

    for a in active:
        cmd = a["cmd"].strip().replace("\n", " ")
        is_path = (a.get("type") == "Custom Path")

        # --- Existenz-Prüfung je nach Typ ---
        if is_path:
            # Der ganze Eintrag ist ein Dateipfad -> prüfen, ob die Datei da ist.
            check = f"[ -e {shlex.quote(cmd)} ]"
        else:
            # CMD -> erstes Token ist das Programm, im PATH suchen.
            try:
                binary = shlex.split(cmd)[0]
            except Exception:
                binary = cmd.split()[0] if cmd.split() else cmd
            check = f"command -v {shlex.quote(binary)} >/dev/null 2>&1"

        # --- Startbefehl ---
        if a.get("debug") and terminal:
            term_part = " ".join([terminal] + (flags or []))
            inner = (f"{cmd}; echo ''; "
                     f"echo '[Debug] Prozess beendet. Fenster schliessen zum Beenden.'; read")
            launch = f"setsid {term_part} bash -c {shlex.quote(inner)} &"
        else:
            launch = f"setsid bash -c {shlex.quote(cmd)} >/dev/null 2>&1 &"

        warn = "echo " + shlex.quote(
            f"[yakuda-connect] Uebersprungen (nicht gefunden): {cmd}") + " >&2"

        lines += [
            f"# Eintrag: {cmd}",
            f"if {check}; then",
            f"    {launch}",
            "else",
            f"    {warn}",
            "fi",
            "",
        ]

    lines.append("exit 0")

    try:
        os.makedirs(os.path.dirname(AUTOSTART_LAUNCHER), exist_ok=True)
        with open(AUTOSTART_LAUNCHER, "w") as f:
            f.write("\n".join(lines) + "\n")
        os.chmod(AUTOSTART_LAUNCHER, 0o755)
        return AUTOSTART_LAUNCHER
    except Exception as e:
        print(f"[Autostart] Launcher konnte nicht geschrieben werden: {e}")
        return None


def sync_with_wivrn(config_data):
    """
    Schreibt die Werte im korrekten Format laut WiVRn-Dokumentation:
    https://github.com/WiVRn/WiVRn/blob/master/docs/configuration.md
    """
    wivrn_data = {}
    if os.path.exists(WIVRN_CONFIG_FILE):
        try:
            with open(WIVRN_CONFIG_FILE, 'r') as f:
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
    # WiVRn startet beim Verbinden EIN Programm. Wir geben ihm ein kleines
    # Launcher-Skript, das ALLE aktiven Autostart-Zeilen startet. Der Pfad
    # bleibt immer gleich — nur der Inhalt des Skripts ändert sich.
    # WICHTIG: In main.py darf der Timer die Programme NICHT zusätzlich
    # starten (sonst doppelte Instanzen). Die Zeile
    #   self.status_timer.timeout.connect(self.check_headset_autostart)
    # muss daher entfernt werden.
    apps_data = config_data.get("autostart_apps", [])
    launcher = write_autostart_launcher(apps_data)
    if launcher:
        wivrn_data["application"] = ["bash", launcher]
    else:
        wivrn_data.pop("application", None)

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
        os.makedirs(os.path.dirname(WIVRN_CONFIG_FILE), exist_ok=True)
        with open(WIVRN_CONFIG_FILE, 'w') as f:
            json.dump(wivrn_data, f, indent=4)
        print(f"[WiVRn Sync] config.json erfolgreich aktualisiert.")
    except Exception as e:
        print(f"Fehler beim Schreiben der wivrn.json: {e}")
