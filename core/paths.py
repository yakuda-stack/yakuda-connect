#!/usr/bin/env python3
"""
core/paths.py — Zentrale Pfad-Ermittlung (XDG-konform)
======================================================
Bisher stand ``os.path.expanduser("~/.config/yakuda-connect/...")`` an ueber
einem Dutzend Stellen im Code. Das hatte zwei Nachteile:

  1. XDG_CONFIG_HOME / XDG_CACHE_HOME wurden ignoriert. Nutzer, die ihre
     Konfiguration woanders hinlegen (haeufig bei Atomic-Distros oder
     verschluesselten Home-Setups), bekamen trotzdem ~/.config.
  2. Aendert sich ein Pfad, muss man ihn ueberall suchen.

WICHTIG — Rueckwaertskompatibilitaet:
    Existiert bereits ein alter Ordner unter ~/.config/yakuda-connect, wird
    WEITER DIESER benutzt, auch wenn XDG_CONFIG_HOME auf etwas anderes zeigt.
    Sonst waeren die Einstellungen bestehender Nutzer nach einem Update
    scheinbar verschwunden. Der XDG-Pfad greift also nur bei Neuinstallation.

Dieses Modul hat bewusst KEINE Importe aus dem Projekt — es muss von jedem
anderen Modul importierbar sein, ohne Ringimporte zu erzeugen.
"""
import os

APP_NAME = "yakuda-connect"

_HOME = os.path.expanduser("~")

# Historische Pfade (vor der XDG-Umstellung). Diese haben Vorrang, falls sie
# existieren — siehe Modul-Docstring.
_LEGACY_CONFIG_ROOT = os.path.join(_HOME, ".config", APP_NAME)
_LEGACY_CACHE_ROOT = os.path.join(_HOME, ".cache", APP_NAME)


def _xdg(env_var: str, default_rel: str) -> str:
    """Basisordner laut XDG-Spezifikation, mit Rueckfall auf den Standard."""
    base = os.environ.get(env_var, "").strip()
    if not base or not os.path.isabs(base):
        base = os.path.join(_HOME, default_rel)
    return base


def config_root() -> str:
    """Wurzelordner fuer Einstellungen (~/.config/yakuda-connect)."""
    if os.path.isdir(_LEGACY_CONFIG_ROOT):
        return _LEGACY_CONFIG_ROOT
    return os.path.join(_xdg("XDG_CONFIG_HOME", ".config"), APP_NAME)


def cache_root() -> str:
    """Wurzelordner fuer Zwischenspeicher (~/.cache/yakuda-connect)."""
    if os.path.isdir(_LEGACY_CACHE_ROOT):
        return _LEGACY_CACHE_ROOT
    return os.path.join(_xdg("XDG_CACHE_HOME", ".cache"), APP_NAME)


def config_dir() -> str:
    """Unterordner 'config', in dem die JSON-Dateien liegen."""
    return os.path.join(config_root(), "config")


def config_file(name: str) -> str:
    """Vollstaendiger Pfad einer Konfigurationsdatei im config-Unterordner."""
    return os.path.join(config_dir(), name)


def cache_file(name: str) -> str:
    """Vollstaendiger Pfad einer Datei im Zwischenspeicher."""
    return os.path.join(cache_root(), name)


def log_file() -> str:
    """Pfad der Programm-Logdatei (wird vom Logging-Setup benutzt)."""
    return os.path.join(cache_root(), "app.log")


def ensure_dirs() -> None:
    """Legt Konfig- und Cache-Ordner an. Fehler werden bewusst nicht
    verschluckt: ohne schreibbares HOME kann die App nichts speichern, und
    das soll frueh und sichtbar scheitern statt spaeter still."""
    os.makedirs(config_dir(), exist_ok=True)
    os.makedirs(cache_root(), exist_ok=True)
