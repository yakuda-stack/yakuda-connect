#!/usr/bin/env python3
import os
import json
import shutil
import datetime
import subprocess
from PySide6.QtWidgets import QMessageBox
import vr_environment as venv

HOME = os.path.expanduser("~")
BACKUP_DIR = os.path.join(HOME, ".config/yakuda-connect/backup")
BACKUP_CONFIG_DIR = os.path.join(BACKUP_DIR, "config")
BACKUP_USR_DIR = os.path.join(BACKUP_DIR, "usr")
BACKUP_OPT_DIR = os.path.join(BACKUP_DIR, "opt")
# Separater Ordner für die Configs eines per Flatpak installierten Steam
BACKUP_STEAMFP_DIR = os.path.join(BACKUP_DIR, "steamflatpak")

# App-Config: hier wird gemerkt, OB (und wann) ein Backup erstellt wurde.
APP_CONFIG_FILE = os.path.join(HOME, ".config/yakuda-connect/config/config.json")


# --------------------------------------------------------------------------- #
#  Backup-Flag in der App-Config ("es gibt ein Backup")
# --------------------------------------------------------------------------- #
def _load_app_config():
    try:
        with open(APP_CONFIG_FILE, "r") as f:
            content = f.read().strip()
            return json.loads(content) if content else {}
    except Exception:
        return {}


def _save_app_config(data):
    try:
        os.makedirs(os.path.dirname(APP_CONFIG_FILE), exist_ok=True)
        with open(APP_CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[Backup] Konnte Backup-Flag nicht speichern: {e}")


def mark_backup_created():
    """Schreibt in die Config, dass ein VR-Backup existiert (mit Zeitstempel)."""
    data = _load_app_config()
    data["vr_backup_created"] = datetime.datetime.now().isoformat(timespec="seconds")
    _save_app_config(data)


def has_backup_flag():
    """True, wenn laut Config bereits ein Backup erstellt wurde."""
    return bool(_load_app_config().get("vr_backup_created"))


def auto_backup_on_start():
    """
    Wird beim Programmstart aufgerufen:
      * Backup laut Config vorhanden  -> nichts tun.
      * Kein Backup, aber es existiert bereits eine VR-Umgebung
        (openxr-/wivrn-Ordner — nativ ODER Flatpak-Pfade) -> einmalig
        automatisch ein Backup anlegen und das Flag setzen.
      * Weder Backup noch VR-Umgebung -> nichts tun (frisches System).
    Rückgabe: True, wenn jetzt ein Auto-Backup erstellt wurde.
    """
    if has_backup_flag():
        return False

    # Altbestand: Backup-Ordner existiert schon (ältere Version ohne Flag)
    # -> nur das Flag nachtragen, nichts überschreiben.
    if os.path.isdir(BACKUP_DIR) and os.listdir(BACKUP_DIR):
        mark_backup_created()
        return False

    # Existiert überhaupt schon eine VR-Umgebung? (nativ + Flatpak-Pfade)
    candidates = []
    candidates += venv.openxr_config_dirs()          # ~/.config/openxr/1 (+ Steam-Flatpak)
    candidates += venv.openvr_config_dirs()          # ~/.config/openvr (+ Steam-Flatpak)
    candidates.append(venv.wivrn_config_dir())       # nativ ODER WiVRn-Flatpak-Sandbox
    candidates.append(os.path.join(HOME, ".config/openxr"))
    if not any(os.path.isdir(p) for p in candidates):
        return False

    print("[Backup] Kein Backup vorhanden, VR-Umgebung erkannt — erstelle automatisches Erst-Backup...")
    return create_vr_backup()


SOURCES = {
    "config": [
        os.path.join(HOME, ".config/openvr"),
        os.path.join(HOME, ".config/openxr"),
        os.path.join(HOME, ".config/wivrn")
    ],
    "usr": [
        "/usr/share/openxr"
    ],
    "opt": [
        "/opt/xrizer",
        "/opt/opencomposite"
    ]
}

def create_vr_backup():
    """Erstellt eine saubere Sicherung der aktuellen VR-Laufumgebung."""
    def safe_copy_tree(src, dest_folder):
        if os.path.exists(src):
            folder_name = os.path.basename(src.rstrip("/"))
            target = os.path.join(dest_folder, folder_name)
            if os.path.exists(target):
                shutil.rmtree(target)
            os.makedirs(dest_folder, exist_ok=True)
            shutil.copytree(src, target)

    try:
        for src in SOURCES["config"]: safe_copy_tree(src, BACKUP_CONFIG_DIR)
        for src in SOURCES["usr"]: safe_copy_tree(src, BACKUP_USR_DIR)
        for src in SOURCES["opt"]: safe_copy_tree(src, BACKUP_OPT_DIR)
        # Zusätzlich: Configs eines Flatpak-Steam (eigene Sandbox-Config)
        if venv.steam_is_flatpak():
            base = venv.STEAM_FLATPAK_BASE
            for sub in (".config/openxr", ".config/openvr"):
                safe_copy_tree(os.path.join(base, sub), BACKUP_STEAMFP_DIR)
        # In der Config merken: es gibt jetzt ein Backup.
        mark_backup_created()
        return True
    except Exception as e:
        print(f"[Backup Fehler] Sicherung fehlgeschlagen: {e}")
        return False

def restore_vr_environment(parent_window):
    """
    Klickt der User auf den Button, wird geprüft:
    Gibt es ein Backup? -> Wiederherstellen.
    Gibt es KEINES? -> Erstes Backup jetzt anlegen!
    """
    # Falls noch überhaupt kein Backup-Ordner existiert, legen wir jetzt das erste an!
    if not os.path.exists(BACKUP_DIR) or not os.listdir(BACKUP_DIR):
        print("[Backup] Kein Backup gefunden. Erstelle ersten System-Wiederherstellungspunkt...")
        if create_vr_backup():
            QMessageBox.information(parent_window, "Backup erstellt",
                                    "Es wurde erfolgreich ein erster sauberer System-Wiederherstellungspunkt deiner VR-Laufumgebung angelegt!")
        else:
            QMessageBox.critical(parent_window, "Fehler", "Der Wiederherstellungspunkt konnte nicht angelegt werden.")
        return

    # Wenn ein Backup existiert -> Normale Wiederherstellungsabfrage
    reply = QMessageBox.question(
        parent_window, "Laufumgebung wiederherstellen",
        "Möchtest du alle VR/XR Konfigurationen und Runtimes aus deinem gespeicherten Backup wiederherstellen?<br><br>"
        "<i>Hinweis: Aktuelle Änderungen werden dabei überschrieben.</i>",
        QMessageBox.Yes | QMessageBox.No
    )

    if reply == QMessageBox.No:
        return

    try:
        # 1. User-Configs wiederherstellen
        config_pairs = [
            ("config/openvr", ".config/openvr"),
            ("config/openxr", ".config/openxr"),
            ("config/wivrn", ".config/wivrn")
        ]
        for b_sub, sys_sub in config_pairs:
            src = os.path.join(BACKUP_DIR, b_sub)
            dest = os.path.join(HOME, sys_sub)
            if os.path.exists(src):
                if os.path.exists(dest): shutil.rmtree(dest)
                shutil.copytree(src, dest)

        # 1b. Flatpak-Steam-Configs zurückspielen (falls gesichert)
        if os.path.isdir(BACKUP_STEAMFP_DIR):
            base = venv.STEAM_FLATPAK_BASE
            for name in ("openxr", "openvr"):
                src = os.path.join(BACKUP_STEAMFP_DIR, name)
                dest = os.path.join(base, ".config", name)
                if os.path.exists(src):
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    if os.path.exists(dest): shutil.rmtree(dest)
                    shutil.copytree(src, dest)

        # 2. System-Ordner wiederherstellen via pkexec
        system_pairs = [
            ("usr/openxr", "/usr/share/openxr"),
            ("opt/xrizer", "/opt/xrizer"),
            ("opt/opencomposite", "/opt/opencomposite")
        ]
        for b_sub, dest in system_pairs:
            src = os.path.join(BACKUP_DIR, b_sub)
            if os.path.exists(src):
                subprocess.run(["pkexec", "rm", "-rf", dest], check=True)
                subprocess.run(["pkexec", "cp", "-r", src, dest], check=True)

        QMessageBox.information(parent_window, "Erfolg", "Deine VR-Laufumgebung wurde komplett wiederhergestellt!")
    except Exception as e:
        QMessageBox.critical(parent_window, "Fehler", f"Wiederherstellung fehlgeschlagen: {e}")
