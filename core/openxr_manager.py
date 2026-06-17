#!/usr/bin/env python3
"""
openxr_manager.py — OpenXR-Runtime-Fix für yakuda-connect
=========================================================
Behebt den Steam-/pressure-vessel-Fehler "invalid Elf handle".

Ursache: Die aktive OpenXR-Runtime-Datei
    ~/.config/openxr/1/active_runtime.json
enthält einen RELATIVEN oder falschen library_path (z. B. zeigt sie auf die
.json statt auf die .so). Steams Container kann den relativen Pfad nicht
auflösen und reicht am Ende die JSON-Datei selbst an capsule-capture-libs
weiter -> "invalid Elf handle".

Fix: Eine korrekte active_runtime.json mit ABSOLUTEN Pfaden zu den
WiVRn-Bibliotheken schreiben. Vorher wird eine eventuell vorhandene Datei
mit Zeitstempel gesichert (es geht also nichts verloren).
"""
import os
import json
import shutil
import datetime

HOME = os.path.expanduser("~")
WIVRN_MANIFEST     = "/usr/share/openxr/1/openxr_wivrn.json"
ACTIVE_RUNTIME_DIR = os.path.join(HOME, ".config/openxr/1")
ACTIVE_RUNTIME     = os.path.join(ACTIVE_RUNTIME_DIR, "active_runtime.json")

# Bekannte Verzeichnisse, in denen die WiVRn-Bibliotheken liegen können
_LIB_DIRS = [
    "/usr/lib/wivrn", "/usr/lib64/wivrn",
    "/usr/lib/x86_64-linux-gnu/wivrn",
    "/usr/lib", "/usr/lib64",
]
_OPENXR_SO = "libopenxr_wivrn.so"
_MONADO_SO = "libmonado_wivrn.so"


# --------------------------------------------------------------------------- #
#  Bibliotheken finden
# --------------------------------------------------------------------------- #
def _resolve_from_manifest():
    """Liest das System-Manifest und löst dessen relative Pfade absolut auf."""
    try:
        with open(WIVRN_MANIFEST, "r") as f:
            data = json.load(f)
        rt = data.get("runtime", {})
        base = os.path.dirname(WIVRN_MANIFEST)
        lib = rt.get("library_path")
        mon = rt.get("MND_libmonado_path")
        lib_abs = os.path.normpath(os.path.join(base, lib)) if lib else None
        mon_abs = os.path.normpath(os.path.join(base, mon)) if mon else None
        return lib_abs, mon_abs
    except Exception:
        return None, None


def _search_dirs():
    """Sucht die Bibliotheken in bekannten Verzeichnissen."""
    openxr = monado = None
    for d in _LIB_DIRS:
        if not os.path.isdir(d):
            continue
        co = os.path.join(d, _OPENXR_SO)
        cm = os.path.join(d, _MONADO_SO)
        if openxr is None and os.path.exists(co):
            openxr = co
        if monado is None and os.path.exists(cm):
            monado = cm
        if openxr and monado:
            break
    return openxr, monado


def _walk_search():
    """Letzter Ausweg: begrenzte Suche unter /usr/lib und /usr/lib64."""
    openxr = monado = None
    for root_dir in ("/usr/lib", "/usr/lib64"):
        if not os.path.isdir(root_dir):
            continue
        for root, _dirs, files in os.walk(root_dir):
            if openxr is None and _OPENXR_SO in files:
                openxr = os.path.join(root, _OPENXR_SO)
            if monado is None and _MONADO_SO in files:
                monado = os.path.join(root, _MONADO_SO)
            if openxr and monado:
                return openxr, monado
    return openxr, monado


def find_wivrn_libs():
    """
    Findet (libopenxr_wivrn.so, libmonado_wivrn.so) als absolute Pfade.
    Reihenfolge: Manifest auflösen -> bekannte Verzeichnisse -> Suche.
    Gibt (openxr_so | None, monado_so | None) zurück.
    """
    o, m = _resolve_from_manifest()
    if o and os.path.exists(o):
        if not (m and os.path.exists(m)):
            # Monado-Lib neben der OpenXR-Lib suchen
            sib = os.path.join(os.path.dirname(o), _MONADO_SO)
            m = sib if os.path.exists(sib) else m
        return o, m

    o, m = _search_dirs()
    if o:
        return o, m

    return _walk_search()


def _is_elf(path):
    """True, wenn die Datei mit der ELF-Signatur beginnt (also eine echte .so)."""
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except Exception:
        return False


# --------------------------------------------------------------------------- #
#  Status
# --------------------------------------------------------------------------- #
def current_status():
    """
    Liefert (state, detail):
      'ok'      -> active_runtime.json zeigt absolut auf eine existierende .so
      'broken'  -> Datei vorhanden, aber Pfad falsch/relativ/zeigt auf .json
      'missing' -> keine eigene active_runtime.json (System-Standard greift)
    """
    if not os.path.exists(ACTIVE_RUNTIME):
        return "missing", ""
    try:
        with open(ACTIVE_RUNTIME, "r") as f:
            data = json.load(f)
        lp = data.get("runtime", {}).get("library_path", "")
    except Exception:
        return "broken", ""
    if not lp or not lp.endswith(".so"):
        return "broken", lp
    if os.path.isabs(lp) and os.path.exists(lp):
        return "ok", lp
    return "broken", lp


def is_openxr_fix_applied():
    state, _ = current_status()
    return state == "ok"


# --------------------------------------------------------------------------- #
#  Fix anwenden
# --------------------------------------------------------------------------- #
def apply_openxr_fix():
    """
    Schreibt eine korrekte active_runtime.json mit absoluten Pfaden.
    Sichert eine vorhandene Datei vorher (Zeitstempel).
    Rückgabe: (erfolg: bool, code: str, detail: str)
      code: 'ok' | 'libs_not_found' | 'not_elf' | 'write_failed'
      detail bei Erfolg: Pfad der Sicherung (oder "")
    """
    openxr_so, monado_so = find_wivrn_libs()
    if not openxr_so or not os.path.exists(openxr_so):
        return False, "libs_not_found", ""
    if not _is_elf(openxr_so):
        return False, "not_elf", openxr_so

    # Vorhandene Datei sichern (nichts kaputt machen)
    backup = ""
    try:
        os.makedirs(ACTIVE_RUNTIME_DIR, exist_ok=True)
        if os.path.exists(ACTIVE_RUNTIME):
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = ACTIVE_RUNTIME + f".bak.{stamp}"
            shutil.copy2(ACTIVE_RUNTIME, backup)
    except Exception:
        backup = ""

    runtime = {
        "file_format_version": "1.0.0",
        "runtime": {
            "name": "Monado",
            "library_path": openxr_so,
        },
    }
    if monado_so and os.path.exists(monado_so):
        runtime["runtime"]["MND_libmonado_path"] = monado_so

    try:
        with open(ACTIVE_RUNTIME, "w") as f:
            json.dump(runtime, f, indent=4)
    except Exception as e:
        return False, "write_failed", str(e)

    return True, "ok", backup
