#!/usr/bin/env python3
"""
core/wivrn_dashboard.py — Einstellungen des WiVRn-Dashboards lesen/schreiben
===========================================================================
Das WiVRn-Dashboard speichert einen Teil seiner Optionen NICHT in
``~/.config/wivrn/config.json`` (das ist die Server-Konfiguration: Encoder,
Bitrate, Codec ...), sondern als Qt-Einstellungen in einer INI-Datei:

    ~/.config/wivrn/wivrn-dashboard.conf

Belegt am Quelltext von WiVRn:

  * ``dashboard/qml/DashboardSettings.qml`` deklariert ein QtCore-``Settings``-
    Objekt mit u. a. ``property bool auto_connect_usb: false``
  * ``dashboard/main.cpp`` setzt ``setOrganizationName("wivrn")`` und den
    KAboutData-Komponentennamen ``wivrn-dashboard`` — daraus bildet Qt den
    Pfad ``<config>/wivrn/wivrn-dashboard.conf``
  * ``dashboard/qml/SettingsPage.qml`` bindet die Checkbox "Auto connect from
    USB" an ``DashboardSettings.auto_connect_usb``
  * ``dashboard/qml/ConnectUsbDialog.qml`` wertet den Wert aus: ist er gesetzt,
    genau EIN Headset per USB gefunden und noch keines verbunden, verbindet
    das Dashboard automatisch

Da das QML-``Settings``-Objekt keine ``category`` setzt, landen die Werte in
der INI-Standardgruppe ``[General]``.

Wichtig fuer Nutzer (steht so auch im Hinweistext der Oberflaeche):
Das Dashboard liest diese Datei beim Start und schreibt sie beim Beenden.
Aendert man den Wert, waehrend das Dashboard laeuft, ueberschreibt es ihn
beim Schliessen wieder. Deshalb pruefen wir das und warnen.

Bewusst mit ``configparser`` statt QSettings: QSettings wuerde beim Schreiben
die ganze Datei neu formatieren und Kommentare verlieren. Wir fassen nur den
einen Schluessel an und lassen alles andere so, wie das Dashboard es abgelegt
hat.
"""
import configparser
import os
import tempfile

import proc
import vr_environment as venv
from logging_setup import get_logger

log = get_logger("wivrn_dashboard")

# Standardgruppe einer QSettings-INI-Datei
_SECTION = "General"

# Schluesselname exakt wie in DashboardSettings.qml
KEY_AUTO_CONNECT_USB = "auto_connect_usb"


def dashboard_config_file() -> str:
    """
    Pfad der Dashboard-Einstellungen. Liegt im selben Ordner wie WiVRns
    config.json, deshalb wird der bestehende Pfad-Helfer wiederverwendet —
    so gilt eine spaetere Aenderung dort automatisch auch hier.
    """
    return os.path.join(venv.wivrn_config_dir(), "wivrn-dashboard.conf")


def _read_parser() -> configparser.ConfigParser:
    """
    Datei einlesen. ``strict=False`` toleriert doppelte Schluessel, und
    ``optionxform = str`` erhaelt die Gross-/Kleinschreibung — configparser
    wuerde sonst alles kleinschreiben und damit fremde Qt-Schluessel wie
    ``lastRunVersion`` zerstoeren.
    """
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    path = dashboard_config_file()
    if os.path.exists(path):
        try:
            parser.read(path, encoding="utf-8")
        except (OSError, configparser.Error) as exc:
            log.warning("wivrn-dashboard.conf nicht lesbar (%s): %s", path, exc)
    return parser


def get_auto_connect_usb() -> bool:
    """Aktueller Zustand der Option. Fehlt die Datei oder der Eintrag, gilt
    der WiVRn-Standard: aus."""
    parser = _read_parser()
    raw = parser.get(_SECTION, KEY_AUTO_CONNECT_USB, fallback="false")
    return str(raw).strip().lower() in ("true", "1", "yes", "on")


def set_auto_connect_usb(enabled: bool) -> bool:
    """
    Option setzen. Gibt True bei Erfolg zurueck.

    Qt schreibt Wahrheitswerte als ``true``/``false`` in Kleinbuchstaben —
    genau dieses Format wird hier erzeugt, damit das Dashboard den Wert
    beim naechsten Start wiedererkennt.

    Geschrieben wird atomar (Temp-Datei im selben Ordner + ``os.replace``):
    das ist die Konfiguration eines FREMDEN Programms, eine halb geschriebene
    Datei koennte das Dashboard beim Start stolpern lassen.
    """
    path = dashboard_config_file()
    parser = _read_parser()
    if not parser.has_section(_SECTION):
        parser.add_section(_SECTION)
    parser.set(_SECTION, KEY_AUTO_CONNECT_USB, "true" if enabled else "false")

    directory = os.path.dirname(path)
    tmp_path = None
    try:
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix="wivrn-dashboard.conf.",
                                        suffix=".tmp", dir=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            # delimiters ohne Leerzeichen: Qt schreibt "key=value", nicht
            # "key = value". Beides ist lesbar, aber so bleibt die Datei
            # unveraendert im gewohnten Format.
            parser.write(fh, space_around_delimiters=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
        log.info("auto_connect_usb=%s in %s gesetzt", enabled, path)
        return True
    except Exception as exc:  # noqa: BLE001 — Aufrufer bekommt nur True/False
        log.error("wivrn-dashboard.conf konnte nicht geschrieben werden: %s", exc)
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                log.debug("Temporaerdatei blieb liegen: %s", tmp_path)
        return False


def dashboard_is_running() -> bool:
    """
    Laeuft das WiVRn-Dashboard gerade?

    Relevant, weil es seine Einstellungen beim Beenden zurueckschreibt: eine
    Aenderung von hier waere dann wieder weg. Statt das stillschweigend
    passieren zu lassen, weist die Oberflaeche darauf hin.
    """
    return proc.run_ok(["pgrep", "-x", "wivrn-dashboard"])
