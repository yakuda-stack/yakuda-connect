#!/usr/bin/env python3
"""
core/autostart_profiles.py — Autostart-Profile: Regeln ohne Qt
=============================================================
Gemeinsamer Kern fuer die Profil-Tabs der Oberflaeche
(core/tabs/autostart_profiles_mixin.py) und den Terminal-Modus
(core/autostart_runner.py). Beide rufen pro Pruef-Takt ``step()`` auf und
tun, was zurueckkommt — so verhalten sie sich garantiert gleich.

Bedingung eines Profils
-----------------------
    Timer an  UND  Ausloeser laeuft  UND  Headset verbunden

Das Headset gehoert immer dazu: yakuda-connect ist VR-Software, und der
Einweg-Timer des VR-Tabs ist nach dem Start schon wieder aus — die Profile
fragen die Verbindung deshalb selbst ab (billig, siehe
process_watch.headset_connected, und nur, wenn der Ausloeser laeuft).

„Programme starten“ (von Hand) umgeht die Bedingung; so gestartete
Programme beendet ``step()`` nicht, solange der Ausloeser nie lief.
"""
from config_manager import load_saved_settings

PROFILE_KEY = "autostart_profiles"
POLL_S = 3.0             # Pruef-Takt
STOP_AFTER_MISSES = 2    # so viele Takte „Bedingung weg“, bevor beendet wird
MAX_PROFILES = 12
MAX_ROWS = 10
NAME_MAX = 24
GAP_MAX = 60             # Sekunden zwischen zwei Programmen (gestaffelt)
DELAY_MAX = 300


def _int(value, lo, hi, default=0):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def normalize(raw):
    """Gespeicherte Profile defensiv lesen (kaputte Eintraege fallen raus)."""
    out = []
    for p in raw if isinstance(raw, list) else []:
        if not isinstance(p, dict):
            continue
        apps = [a for a in (p.get("apps") or []) if isinstance(a, dict)]
        out.append({
            "name": str(p.get("name") or "")[:NAME_MAX] or "Profil",
            "trigger": str(p.get("trigger") or ""),
            "delay": _int(p.get("delay", 0), 0, DELAY_MAX),
            "gap": _int(p.get("gap", 0), 0, GAP_MAX),
            "stop_with": bool(p.get("stop_with", True)),
            "enabled": bool(p.get("enabled", True)),
            "apps": apps[:MAX_ROWS],
        })
    return out[:MAX_PROFILES]


MASTER_KEY = "autostart_profiles_enabled"


def master_enabled(settings=None):
    """Hauptschalter der Profil-Automatik (Standard: aus)."""
    if settings is None:
        settings = load_saved_settings()
    return bool(settings.get(MASTER_KEY, False))


def set_master_enabled(on):
    from config_manager import CONFIG_FILE
    from jsonio import update_json
    update_json(CONFIG_FILE, {MASTER_KEY: bool(on)})


def load_profiles(settings=None):
    if settings is None:
        settings = load_saved_settings()
    return normalize(settings.get(PROFILE_KEY, []) or [])


def commands(profile):
    """Nicht leere Programmzeilen eines Profils als [{"cmd", "debug"}]."""
    return [{"cmd": a["cmd"].strip(), "debug": bool(a.get("debug"))}
            for a in profile.get("apps", [])
            if isinstance(a.get("cmd"), str) and a["cmd"].strip()]


def armed(profile):
    """Hat das Profil alles, um von selbst zu arbeiten?"""
    return bool(profile.get("enabled") and profile.get("trigger", "").strip()
                and commands(profile))


def new_state():
    return {"launched": False, "seen_since": None, "misses": 0, "manual": False}


def step(state, condition, delay, stop_with, now):
    """
    Ein Pruef-Takt. ``state`` wird veraendert. Rueckgabe:
      "launch" — jetzt starten
      "stop"   — jetzt beenden
      None     — nichts tun
    """
    if condition:
        state["misses"] = 0
        state["manual"] = False          # ab jetzt regelt der Ausloeser
        if state["launched"]:
            return None
        if state["seen_since"] is None:
            state["seen_since"] = now
        if now - state["seen_since"] >= delay:
            state["launched"] = True
            return "launch"
        return None

    if state["manual"]:
        return None                      # von Hand gestartet: bleibt
    if state["seen_since"] is None and not state["launched"]:
        return None
    state["misses"] += 1
    if state["misses"] < STOP_AFTER_MISSES:
        return None                      # kurzer Aussetzer
    action = "stop" if (state["launched"] and stop_with) else None
    state.update(launched=False, seen_since=None, misses=0)
    return action


def schedule(apps, gap, now):
    """Gestaffelter Start: [(faellig_um, app), ...] — erstes sofort."""
    return [(now + i * gap, app) for i, app in enumerate(apps)]
