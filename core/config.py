import os
import pathlib

# Bestimmung des Konfigurations-Ordners (XDG Standard)
# Falls der Ordner nicht existiert, wird er beim ersten Start erstellt
CONFIG_DIR = pathlib.Path.home() / ".config" / "yakuda-connect"
CONFIG_FILE = CONFIG_DIR / "config.json"

def ensure_config_dir():
    """Stellt sicher, dass der Konfigurationsordner existiert."""
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Konfigurationsordner erstellt unter: {CONFIG_DIR}")

# Beim Start des Programms einmal aufrufen
ensure_config_dir()
