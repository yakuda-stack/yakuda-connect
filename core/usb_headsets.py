#!/usr/bin/env python3
"""
core/usb_headsets.py — Headsets am USB-Bus erkennen (ohne Root, ohne adb-Zwang)
==============================================================================
Zwei Fragen beantwortet dieses Modul:

1. **Haengt gerade eine VR-Brille am Kabel?**
   Dafuer wird ``/sys/bus/usb/devices`` gelesen — ein reiner Dateizugriff,
   kein Prozessstart, keine Rechte noetig, kein ``lsusb`` als Abhaengigkeit.
   Jedes USB-Geraet liegt dort als Ordner mit ``idVendor``/``idProduct`` und
   (fast immer) ``product``/``manufacturer`` als Klartext.

2. **Wuerde "Automatisch per USB verbinden" auch wirklich funktionieren?**
   WiVRns Dashboard verbindet ueber USB per **adb** (``adb forward``). Steckt
   die Brille zwar am Kabel, ist aber USB-Debugging aus oder der PC am Headset
   nicht bestaetigt, taucht sie in ``adb devices`` gar nicht bzw. als
   ``unauthorized`` auf — die Automatik greift dann NICHT. Genau das ist der
   Fall, den die Ampel im Dashboard sichtbar macht, statt dass der Nutzer
   raetselt, warum nichts passiert.

``adb`` wird bewusst nur aufgerufen, wenn ueberhaupt ein Headset am Bus
gefunden wurde: der Aufruf startet einen adb-Daemon, und den soll niemand
bekommen, der nur die App offen hat.

Bildwiederholraten
------------------
WiVRn schreibt ``refresh_rate`` in seine ``config.json`` und der Client
uebernimmt den Wert nur, wenn das Headset ihn kann — sonst faellt er auf den
Standard zurueck. Deshalb hat jedes Modell hier ein Profil: die Oberflaeche
zeigt weiterhin alle Raten, sperrt aber die, die das erkannte Headset nicht
beherrscht (Pico: max. 90 Hz), statt den Nutzer eine Zahl waehlen zu lassen,
die stillschweigend ignoriert wird.
"""
import os
import re
import shutil

import proc
from logging_setup import get_logger

log = get_logger("usb_headsets")

SYSFS_USB = "/sys/bus/usb/devices"

# --------------------------------------------------------------------------- #
#  Bekannte Hersteller-IDs (USB Vendor IDs, hexadezimal wie in sysfs)
# --------------------------------------------------------------------------- #
#   2833  Meta / Oculus   (Quest 1-3, 3S, Pro)
#   2d40  Pico Interactive (Pico 4, 4 Ultra, Neo 3)
#   0bb4  HTC             (Vive Focus 3, XR Elite — auch HTC-Telefone!)
#   28de  Valve
# Der angezeigte Name kommt aus dem 'product'-Feld des Geraets, die Vendor-ID
# dient nur der Zuordnung zu einer Familie (und damit zum Raten-Profil).
VENDORS = {
    "2833": ("Meta / Oculus", "quest"),
    "2d40": ("Pico", "pico"),
    "0bb4": ("HTC", "htc"),
    "28de": ("Valve", "valve"),
}

# --------------------------------------------------------------------------- #
#  Raten-Profile je Modell (Reihenfolge = Prueffolge, spezifisch vor allgemein)
# --------------------------------------------------------------------------- #
MODEL_PROFILES = [
    (r"quest\s*3s",        "Meta Quest 3S",      [72, 80, 90, 120]),
    (r"quest\s*3",         "Meta Quest 3",       [72, 80, 90, 120]),
    (r"quest\s*pro",       "Meta Quest Pro",     [72, 80, 90]),
    (r"quest\s*2",         "Meta Quest 2",       [60, 72, 80, 90, 120]),
    (r"quest",             "Meta Quest",         [60, 72]),
    (r"pico\s*4\s*ultra",  "Pico 4 Ultra",       [72, 90]),
    (r"pico\s*4",          "Pico 4",             [72, 90]),
    (r"pico\s*neo\s*3",    "Pico Neo 3",         [72, 90]),
    (r"pico",              "Pico",               [72, 90]),
    (r"focus\s*vision",    "HTC Vive Focus Vision", [75, 90]),
    (r"focus\s*3",         "HTC Vive Focus 3",   [75, 90]),
    (r"xr\s*elite",        "HTC Vive XR Elite",  [72, 90]),
]

# Fallback je Familie, wenn der Produktname nichts Genaueres hergibt.
FAMILY_RATES = {
    "quest": [72, 80, 90, 120],
    "pico":  [72, 90],
    "htc":   [75, 90],
    "valve": [90, 120],
}

# Auswahl im Dashboard. "Auto" = WiVRn entscheidet (schreibt 0 in die Config).
RATE_CHOICES = ["Auto", "60", "72", "80", "90", "120"]

# Solange nichts erkannt wurde, ist nichts gesperrt — der Nutzer darf dann
# alles waehlen (Headset kann ja per WLAN verbunden sein, dann sieht der
# USB-Bus es nicht).
ALL_RATES = [int(r) for r in RATE_CHOICES if r.isdigit()]


# --------------------------------------------------------------------------- #
#  USB-Bus lesen
# --------------------------------------------------------------------------- #
def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def list_usb_headsets():
    """
    Alle als VR-Headset erkannten USB-Geraete.

    Rueckgabe: Liste von Dicts mit ``vendor``, ``product_id``, ``name``,
    ``vendor_name``, ``family``, ``serial``. Leere Liste, wenn nichts passt
    (oder auf Systemen ohne sysfs — dann faellt die Anzeige einfach auf
    "nichts erkannt" zurueck, statt zu scheitern).
    """
    found = []
    if not os.path.isdir(SYSFS_USB):
        return found

    try:
        entries = sorted(os.listdir(SYSFS_USB))
    except OSError as exc:
        log.debug("USB-Bus nicht lesbar: %s", exc)
        return found

    for entry in entries:
        # Namen mit ':' sind Interfaces (z. B. '1-2:1.0'), keine Geraete.
        if ":" in entry:
            continue
        base = os.path.join(SYSFS_USB, entry)
        vendor = _read(os.path.join(base, "idVendor")).lower()
        if vendor not in VENDORS:
            continue

        vendor_name, family = VENDORS[vendor]
        product = _read(os.path.join(base, "product"))
        found.append({
            "vendor": vendor,
            "product_id": _read(os.path.join(base, "idProduct")).lower(),
            "name": product or vendor_name,
            "vendor_name": _read(os.path.join(base, "manufacturer")) or vendor_name,
            "family": family,
            "serial": _read(os.path.join(base, "serial")),
        })

    return found


# --------------------------------------------------------------------------- #
#  adb-Zustand (nur relevant fuer die USB-Automatik von WiVRn)
# --------------------------------------------------------------------------- #
def adb_available():
    return shutil.which("adb") is not None


def adb_devices():
    """
    ``{serial: zustand}`` aus ``adb devices``. Zustaende laut adb:
    ``device`` (bereit), ``unauthorized`` (PC im Headset nicht bestaetigt),
    ``offline``, ``recovery`` ...

    Faellt der Aufruf durch (adb fehlt, Timeout), gibt es ein leeres Dict —
    der Aufrufer behandelt das wie "kein adb".
    """
    if not adb_available():
        return {}
    res = proc.run(["adb", "devices"], timeout=proc.DEFAULT_TIMEOUT)
    if res.returncode != 0:
        return {}

    states = {}
    for line in (res.stdout or "").splitlines():
        line = line.strip()
        if not line or line.lower().startswith("list of devices"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            states[parts[0]] = parts[1]
    return states


# --------------------------------------------------------------------------- #
#  Raten-Profil
# --------------------------------------------------------------------------- #
def profile_for(headset):
    """
    Raten-Profil zu einem erkannten Headset (oder ``None``).

    Rueckgabe: ``{"model": Anzeigename, "rates": [72, 90, ...], "max": 90}``.
    Ohne Erkennung sind alle Raten erlaubt — lieber nichts sperren als das
    Falsche sperren.
    """
    if not headset:
        return {"model": "", "rates": list(ALL_RATES), "max": max(ALL_RATES)}

    text = f"{headset.get('name', '')} {headset.get('vendor_name', '')}".lower()
    for pattern, model, rates in MODEL_PROFILES:
        if re.search(pattern, text):
            return {"model": model, "rates": list(rates), "max": max(rates)}

    rates = FAMILY_RATES.get(headset.get("family"), list(ALL_RATES))
    return {"model": headset.get("name", ""), "rates": list(rates), "max": max(rates)}


# --------------------------------------------------------------------------- #
#  Gesamtbild fuer die Oberflaeche
# --------------------------------------------------------------------------- #
def scan(check_adb=True):
    """
    Ein Aufruf, ein vollstaendiges Bild — laeuft im Hintergrund-Thread.

    ``state`` ist einer von:
      ``none``          nichts am USB gefunden
      ``ready``         Headset da UND per adb erreichbar -> USB-Automatik geht
      ``unauthorized``  Headset da, aber der PC ist im Headset nicht bestaetigt
      ``usb_only``      Headset da, adb sieht es nicht (USB-Debugging aus?)
      ``no_adb``        Headset da, aber adb ist gar nicht installiert
    """
    devices = list_usb_headsets()
    info = {
        "devices": devices,
        "headset": devices[0] if devices else None,
        "state": "none",
        "adb_state": "",
        "profile": profile_for(devices[0] if devices else None),
    }
    if not devices:
        return info

    if not check_adb:
        info["state"] = "usb_only"
        return info

    if not adb_available():
        info["state"] = "no_adb"
        return info

    states = adb_devices()
    values = set(states.values())
    if "device" in values:
        info["state"] = "ready"
        info["adb_state"] = "device"
    elif "unauthorized" in values:
        info["state"] = "unauthorized"
        info["adb_state"] = "unauthorized"
    else:
        info["state"] = "usb_only"
        info["adb_state"] = ",".join(sorted(values))
    return info
