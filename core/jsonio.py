#!/usr/bin/env python3
"""
core/jsonio.py — Sicheres Lesen und Schreiben von JSON-Dateien
=============================================================
Warum es das gibt:

Ein ``json.dump(daten, open(pfad, "w"))`` kuerzt die Datei ZUERST auf null
Bytes und schreibt dann. Faellt in diesem Moment der Strom aus, stuerzt die
App ab oder ist die Platte voll, bleibt eine leere oder halbe Datei zurueck —
und die Einstellungen des Nutzers sind weg.

Besonders heikel ist das bei ``~/.config/wivrn/config.json``: das ist die
Konfiguration eines FREMDEN Programms. Zerlegen wir die, startet WiVRn nicht
mehr, und der Nutzer sucht den Fehler bei WiVRn statt bei uns.

``write_json_atomic`` schreibt deshalb in eine Nebendatei im selben Ordner,
erzwingt das Schreiben auf die Platte (fsync) und benennt sie erst dann um.
``os.replace`` ist auf POSIX atomar: es existiert immer entweder die alte
oder die neue Datei — nie eine kaputte Mischung.
"""
import json
import os
import tempfile

from logging_setup import get_logger

log = get_logger("jsonio")


def read_json(path: str, default=None):
    """
    JSON laden. Bei fehlender, leerer oder kaputter Datei wird ``default``
    zurueckgegeben (Standard: leeres dict) und der Grund geloggt.
    """
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as fh:
            content = fh.read().strip()
        if not content:
            log.debug("JSON leer, nutze Standardwerte: %s", path)
            return default
        return json.loads(content)
    except json.JSONDecodeError as exc:
        log.warning("JSON defekt (%s): %s", path, exc)
        _quarantine(path)
        return default
    except OSError as exc:
        log.warning("JSON nicht lesbar (%s): %s", path, exc)
        return default


def write_json_atomic(path: str, data, indent: int = 4) -> bool:
    """
    JSON atomar schreiben. Gibt True bei Erfolg zurueck.

    Die Temporaerdatei liegt bewusst IM ZIELORDNER — ``os.replace`` ist nur
    innerhalb desselben Dateisystems atomar. /tmp kann eine eigene tmpfs sein.
    """
    directory = os.path.dirname(path) or "."
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as exc:
        log.error("Zielordner nicht anlegbar (%s): %s", directory, exc)
        return False

    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            prefix=os.path.basename(path) + ".", suffix=".tmp", dir=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=indent, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())        # wirklich auf die Platte, nicht nur in den Cache
        os.chmod(tmp_path, 0o600)        # Configs koennen Pairing-Codes enthalten
        os.replace(tmp_path, path)       # atomar
        return True
    except Exception as exc:  # noqa: BLE001 — Aufrufer soll nur True/False sehen
        log.error("Schreiben fehlgeschlagen (%s): %s", path, exc)
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                log.debug("Temporaerdatei blieb liegen: %s", tmp_path)
        return False


def update_json(path: str, changes: dict, indent: int = 4) -> bool:
    """
    Lesen -> gezielt aendern -> atomar zurueckschreiben.

    Das ist der Unterschied zum frueheren Vorgehen: dort wurde das Dict NEU
    aufgebaut und alte Schluessel ueber eine handgepflegte Liste "gerettet".
    Jeder Schluessel, der in dieser Liste fehlte, ging beim naechsten
    Speichern still verloren. Hier bleibt Unbekanntes automatisch erhalten.
    """
    data = read_json(path, default={})
    if not isinstance(data, dict):
        log.warning("Erwartet wurde ein JSON-Objekt, gefunden %s: %s",
                    type(data).__name__, path)
        data = {}
    data.update(changes)
    return write_json_atomic(path, data, indent=indent)


def _quarantine(path: str) -> None:
    """
    Kaputte Datei zur Seite legen statt sie zu ueberschreiben. So kann man
    im Supportfall noch nachsehen, was drinstand — und der Nutzer verliert
    seine Daten nicht endgueltig, falls sie doch rettbar sind.
    """
    broken = path + ".broken"
    try:
        os.replace(path, broken)
        log.warning("Defekte Datei gesichert unter: %s", broken)
    except OSError as exc:
        log.debug("Konnte defekte Datei nicht sichern: %s", exc)
