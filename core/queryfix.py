#!/usr/bin/env python3
"""
queryfix.py — Quick OSC Query Fix für yakuda-connect
====================================================
Herausgelöst aus OSC-DreamChatbox (portables Modul), angepasst für
yakuda-connect: Die Meldungen sind hier CODES statt fertiger Texte,
damit die UI sie über translations.py (DE/EN) übersetzen kann.

Eine einzige, leicht erweiterbare PROGRAMS-Liste. Der "Fix OSCQuery"-
Button im Settings-Tab schreibt den nötigen Parameter direkt in die
Config-Datei jedes unterstützten Programms (alle anderen Keys der
Datei bleiben erhalten).

Neues Programm hinzufügen: einfach ein Dict an PROGRAMS anhängen —
UI-Liste, Details und Fix-Button ziehen automatisch nach:
    name    Anzeigename in der UI
    path    Pfad zur Config-Datei des Programms (~ wird expandiert)
    key     der zu setzende JSON-Key
    value   der zu schreibende Wert (meist True)

Verhalten (bewusst so gewählt):
  * Es werden NUR existierende Config-Dateien verändert.
  * Fehlt die Datei (Programm nie gestartet), wird das gemeldet statt
    eine halbe Config zu erzeugen — manche Tools (z. B. OSCLeash)
    stürzen bei unvollständigen Configs ab.
  * Idempotent: zweiter Klick meldet "bereits gesetzt".
  * Nach dem Fix müssen die Programme neu gestartet werden.
"""

import json
from pathlib import Path

# ---------------------------------------------------------------- Programme
PROGRAMS = [
    {
        "name": "OSCLeash",
        "path": "~/.config/OSCLeash/Config.json",
        "key": "UseOSCQuery",
        "value": True,
    },
    {
        "name": "OscGoesBrrr",
        "path": "~/.config/OscGoesBrrr/config.json",
        "key": "useOscQuery",
        "value": True,
    },
    # Weitere OSCQuery-fähige Programme hier ergänzen ...
]


def param_str(prog):
    """'"UseOSCQuery": true' — für Detail-Anzeige und Meldungen."""
    return f"\"{prog['key']}\": {json.dumps(prog['value'])}"


def fix_program(prog):
    """
    Wendet den OSCQuery-Fix auf EIN Programm an.
    Rückgabe: (ok: bool, code: str, detail: str)
      code:  'not_found'    -> Config fehlt (Programm nicht installiert/gestartet)
             'unreadable'   -> Config nicht lesbar (detail = Fehlertext)
             'already'      -> Wert war schon gesetzt (detail = Parameter)
             'fixed'        -> Wert geschrieben (detail = Parameter)
             'write_failed' -> Schreiben fehlgeschlagen (detail = Fehlertext)
    """
    cfg_path = Path(prog["path"]).expanduser()
    if not cfg_path.exists():
        return False, "not_found", ""
    try:
        data = json.loads(cfg_path.read_text())
    except Exception as e:
        return False, "unreadable", str(e)
    if data.get(prog["key"]) == prog["value"]:
        return True, "already", param_str(prog)
    data[prog["key"]] = prog["value"]
    try:
        cfg_path.write_text(json.dumps(data, indent=2))
    except Exception as e:
        return False, "write_failed", str(e)
    return True, "fixed", param_str(prog)


def fix_all(log=print):
    """
    Wendet den Fix auf alle unterstützten Programme an.
    Rückgabe: Liste von (name, ok, code, detail).
    """
    results = []
    for prog in PROGRAMS:
        ok, code, detail = fix_program(prog)
        results.append((prog["name"], ok, code, detail))
        log(f"[OSCQuery Fix] {prog['name']}: {code} {detail}".rstrip())
    return results
