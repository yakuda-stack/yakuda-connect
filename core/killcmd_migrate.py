#!/usr/bin/env python3
"""
core/killcmd_migrate.py — Eigene Kill-Befehle an die Autostart-Zeilen haengen
=============================================================================
Frueher standen eigene Kill-Befehle als lose Liste unter Einstellungen →
Erweitert (custom_kill_commands). Jetzt hat jede Autostart-Zeile im
Dashboard einen Haken „Kill“ und ein eigenes Feld dafuer
(autostart_apps[i]["kill_on"] / ["kill"]).

Einmalig beim Laden: passende alte Eintraege wandern an „ihre“ Zeile.
Was nicht passt, bleibt in custom_kill_commands und laeuft weiter wie bisher
(Erweitert zeigt die Liste dann noch an).

Kein Qt — mit einfachen Tests pruefbar.
"""
import os
import shlex

MIGRATED_KEY = "killcmd_migrated"


def _words(text):
    try:
        parts = shlex.split(text or "")
    except ValueError:
        parts = (text or "").split()
    return [os.path.basename(p).lower() for p in parts if p and not p.startswith("-")]


def _matches(entry, app):
    target = (app.get("cmd") or "").lower()
    if not target:
        return False
    label = (entry.get("label") or "").strip().lower()
    if label and label in target:
        return True
    kill_words = [w for w in _words(entry.get("cmd")) if w not in
                  ("pkill", "killall", "kill", "sudo", "flatpak")]
    app_words = _words(app.get("cmd"))
    return any(w and (w in app_words or any(w in a for a in app_words)) for w in kill_words)


def migrate(settings):
    """Verschiebt passende alte Kill-Befehle an die Zeilen. Aendert settings.
    Rueckgabe: True, wenn sich etwas geaendert hat (dann speichern)."""
    if not isinstance(settings, dict) or settings.get(MIGRATED_KEY):
        return False
    apps = settings.get("autostart_apps") or []
    rest = []
    for entry in settings.get("custom_kill_commands") or []:
        if isinstance(entry, str):
            entry = {"label": "", "cmd": entry}
        if not isinstance(entry, dict) or not (entry.get("cmd") or "").strip():
            continue
        app = next((a for a in apps if isinstance(a, dict) and not a.get("kill")
                    and _matches(entry, a)), None)
        if app is None:
            rest.append(entry)
            continue
        app["kill_on"] = True
        app["kill"] = entry["cmd"].strip()
    settings["custom_kill_commands"] = rest
    settings[MIGRATED_KEY] = True
    return True


def row_kill_commands(settings):
    """Kill-Befehle der Autostart-Zeilen (Haken an, Feld nicht leer)."""
    out = []
    for app in (settings or {}).get("autostart_apps") or []:
        if isinstance(app, dict) and app.get("kill_on") and (app.get("kill") or "").strip():
            out.append({"label": app.get("cmd", ""), "cmd": app["kill"].strip()})
    return out


def all_kill_commands(settings):
    """Alles, was vor dem Beenden der Autostart-Programme laufen soll."""
    legacy = list((settings or {}).get("custom_kill_commands") or [])
    return legacy + row_kill_commands(settings)
