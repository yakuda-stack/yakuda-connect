#!/usr/bin/env python3
"""
core/app_reset.py — App auf den Stand nach der Installation zuruecksetzen
=========================================================================
Geloescht werden nur die Einstellungen der App (config/) und der Icon-Ordner.
Danach verhaelt sich die App wie beim allerersten Start.

Bewusst NICHT geloescht:

  * backup/     Sicherung der VR-Konfiguration, ohne sie gibt es kein Zurueck
  * tools/      installierte Programme (AppImages, Cargo-Builds)
  * xrbinder/   gebauter OpenXR-Layer, den Spiele weiter laden
  * WiVRn- und Steam-Einstellungen, die gehoeren nicht der App

Kein Qt — mit einfachen Tests pruefbar.
"""
import os
import shutil

import paths
import tool_icons
from logging_setup import get_logger

log = get_logger("app_reset")


def reset_targets():
    """Ordner, die ein Reset loescht."""
    return [paths.config_dir(), tool_icons.icon_dir()]


def reset_app():
    """Einstellungen loeschen. Gibt True zurueck, wenn alles entfernt wurde."""
    ok = True
    for folder in reset_targets():
        if not os.path.isdir(folder):
            continue
        try:
            shutil.rmtree(folder)
            log.info("Zurueckgesetzt: %s", folder)
        except OSError as exc:
            log.warning("%s nicht geloescht: %s", folder, exc)
            ok = False
    return ok
