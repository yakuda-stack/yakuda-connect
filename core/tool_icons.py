#!/usr/bin/env python3
"""
core/tool_icons.py — Icons der Tools-Tab-Programme
==================================================
Alle Icons liegen in einem Ordner:

    ~/.config/yakuda-connect/icons/<tool-key>.png
    ~/.config/yakuda-connect/icons/custom-<pruefsumme>.<endung>

Geladen wird nur bei einer Installation ueber den Tools-Tab oder per Klick auf
"Icon holen" — nie beim Start. Eine AppImage-Installation legt ihr Icon schon
unter tools/<key>/icon.png ab, das wird hierher kopiert.

Kein Qt — mit einfachen Tests pruefbar.
"""
import hashlib
import os
import shutil
import urllib.request

import paths
from logging_setup import get_logger

log = get_logger("tool_icons")

MAX_BYTES = 5 * 1024 * 1024
_MAGIC = (b"\x89PNG", b"\xff\xd8")           # PNG, JPEG


def icon_dir():
    return os.path.join(paths.config_root(), "icons")


def icon_path(key):
    return os.path.join(icon_dir(), f"{key}.png")


def _raw_url(url):
    """GitHub-blob-Adresse in die Adresse der Rohdatei umschreiben."""
    if "github.com" in url and "/blob/" in url:
        url = url.replace("https://github.com/", "https://raw.githubusercontent.com/")
        url = url.replace("/blob/", "/")
    return url


def has_url(tool):
    return (tool.get("icon_url") or "").startswith("https://")


def local_icon(tool):
    """Pfad des Icons im Icon-Ordner oder '', wenn es noch keines gibt."""
    key = tool.get("key", "")
    target = icon_path(key)
    if os.path.isfile(target):
        return target
    appimage_icon = os.path.join(paths.config_root(), "tools", key, "icon.png")
    if os.path.isfile(appimage_icon):
        try:
            os.makedirs(icon_dir(), exist_ok=True)
            shutil.copyfile(appimage_icon, target)
            return target
        except OSError as exc:
            log.debug("Icon %s nicht kopiert: %s", key, exc)
            return appimage_icon
    return ""


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def download(tool):
    """Icon aus ``icon_url`` in den Icon-Ordner laden. Gibt True bei Erfolg zurueck."""
    if not has_url(tool):
        return False
    request = urllib.request.Request(_raw_url(tool["icon_url"]),
                                     headers={"User-Agent": "yakuda-connect"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES or not data.startswith(_MAGIC):
            log.warning("Icon %s ist kein gueltiges Bild.", tool.get("key"))
            return False
        _write(icon_path(tool["key"]), data)
        return True
    except OSError as exc:
        log.warning("Icon %s nicht geladen: %s", tool.get("key"), exc)
        return False


def import_file(source):
    """Eigenes Bild in den Icon-Ordner kopieren. Rueckgabe: neuer Pfad oder ''."""
    try:
        with open(source, "rb") as fh:
            data = fh.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            return ""
        digest = hashlib.sha256(data).hexdigest()[:16]
        ext = os.path.splitext(source)[1].lower() or ".png"
        target = os.path.join(icon_dir(), f"custom-{digest}{ext}")
        _write(target, data)
        return target
    except OSError as exc:
        log.warning("Eigenes Icon nicht uebernommen: %s", exc)
        return ""
