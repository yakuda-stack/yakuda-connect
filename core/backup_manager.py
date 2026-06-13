#!/usr/bin/env python3
import os
import shutil
import subprocess
from PySide6.QtWidgets import QMessageBox

HOME = os.path.expanduser("~")
BACKUP_DIR = os.path.join(HOME, ".config/yakuda-connect/backup")
BACKUP_CONFIG_DIR = os.path.join(BACKUP_DIR, "config")
BACKUP_USR_DIR = os.path.join(BACKUP_DIR, "usr")
BACKUP_OPT_DIR = os.path.join(BACKUP_DIR, "opt")

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
