#!/usr/bin/env python3
"""
core/translations.py — Sprachen laden
=====================================
Die Texte selbst stehen NICHT mehr hier, sondern als JSON in ``locales/``:

    locales/en.json     Englisch (Standard, Referenz)
    locales/de.json     Deutsch

Warum umgezogen: vorher war das ein 850-Zeilen-Dict mitten im Python-Code.
Wer eine Sprache ergaenzen wollte, musste eine Python-Datei bearbeiten und
konnte dabei die App zerlegen (ein fehlendes Komma = Startfehler). Eine
JSON-Datei kann jeder bearbeiten, und ein Fehler darin faengt der Loader ab.

Neue Sprache beitragen
----------------------
1. ``locales/en.json`` kopieren, z. B. nach ``locales/fr.json``
2. Nur die Werte rechts uebersetzen, die Schluessel links unveraendert lassen
3. Platzhalter wie ``{name}``, ``{path}``, ``{version}`` muessen erhalten
   bleiben — sie werden zur Laufzeit ersetzt
4. Pull Request. Der Smoke-Test prueft automatisch, ob Schluessel fehlen.

Fehlt ein Schluessel in einer Sprache, greift automatisch der englische Text
— die Oberflaeche bleibt also benutzbar, statt Platzhalter anzuzeigen.
"""
import json
import os

from logging_setup import get_logger

log = get_logger("translations")

# locales/ liegt neben core/, also eine Ebene ueber dieser Datei.
_LOCALES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "locales")

DEFAULT_LANG = "en"

TRANSLATIONS = {}


def _load_all():
    """
    Laedt jede *.json aus locales/. Eine kaputte Datei wird uebersprungen
    und geloggt — sie darf nicht den Start der App verhindern.
    """
    if not os.path.isdir(_LOCALES_DIR):
        log.error("Sprachordner nicht gefunden: %s", _LOCALES_DIR)
        return

    for name in sorted(os.listdir(_LOCALES_DIR)):
        if not name.endswith(".json"):
            continue
        code = name[:-5]
        path = os.path.join(_LOCALES_DIR, name)
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                log.warning("Sprachdatei enthaelt kein Objekt: %s", path)
                continue
            TRANSLATIONS[code] = data
        except json.JSONDecodeError as exc:
            # Typischer Fehler bei Beitraegen aus der Community: ein Komma
            # zu viel oder zu wenig. Zeile und Spalte nennen, damit es
            # schnell zu finden ist.
            log.error("Sprachdatei %s ist fehlerhaft (Zeile %s, Spalte %s): %s",
                      name, exc.lineno, exc.colno, exc.msg)
        except OSError as exc:
            log.warning("Sprachdatei %s nicht lesbar: %s", name, exc)

    if DEFAULT_LANG not in TRANSLATIONS:
        # Ohne Englisch gibt es keinen Rueckfall — das ist ein Auslieferungs-
        # fehler und soll laut scheitern, nicht in einer leeren UI enden.
        raise RuntimeError(
            f"Pflicht-Sprachdatei locales/{DEFAULT_LANG}.json fehlt oder ist defekt "
            f"(gesucht in: {_LOCALES_DIR})")

    log.info("Sprachen geladen: %s",
             ", ".join(f"{k} ({len(v)})" for k, v in sorted(TRANSLATIONS.items())))


_load_all()

_current_lang = DEFAULT_LANG


def available_languages():
    """Codes aller gefundenen Sprachen, z. B. ['de', 'en']."""
    return sorted(TRANSLATIONS.keys())


def set_language(lang: str):
    global _current_lang
    if lang in TRANSLATIONS:
        _current_lang = lang
    else:
        log.warning("Unbekannte Sprache '%s' — bleibe bei '%s'.", lang, _current_lang)


def get_language() -> str:
    return _current_lang


def tr(key: str) -> str:
    """
    Text zum Schluessel. Reihenfolge: aktuelle Sprache -> Englisch -> der
    Schluessel selbst. So bleibt die Oberflaeche auch bei einer unvollstaendigen
    Uebersetzung benutzbar.
    """
    lang_dict = TRANSLATIONS.get(_current_lang, TRANSLATIONS[DEFAULT_LANG])
    if key in lang_dict:
        return lang_dict[key]
    return TRANSLATIONS[DEFAULT_LANG].get(key, key)


def tr_amp(key: str) -> str:
    """Wie tr(), aber fuer Widgets, die '&' als Tastenkuerzel deuten.

    QPushButton, QCheckBox, QGroupBox-Titel und Reiterbeschriftungen
    verschlucken ein einzelnes '&' und unterstreichen stattdessen den
    folgenden Buchstaben. Aus "Tracking & Display & Connect Options" wurde
    so sichtbar "Tracking  Display Options" — der Text war schlicht weg.
    Verdoppeln ist die von Qt vorgesehene Schreibweise fuer ein echtes '&'.

    Bewusst NICHT in tr() selbst: QLabel und Meldungsfenster deuten '&'
    nicht, dort wuerde ein verdoppeltes Zeichen als "&&" dastehen.
    """
    return tr(key).replace("&", "&&")
