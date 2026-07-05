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

import vr_environment as venv

HOME = os.path.expanduser("~")
WIVRN_MANIFEST     = venv.find_wivrn_manifest()
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
    Erst zentraler Resolver (nativ/flatpak/nix), dann Manifest -> Verzeichnisse -> Suche.
    """
    o, m = venv.find_wivrn_libs()
    if o and os.path.exists(o):
        return o, m

    o, m = _resolve_from_manifest()
    if o and os.path.exists(o):
        if not (m and os.path.exists(m)):
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

    runtime = {
        "file_format_version": "1.0.0",
        "runtime": {
            "name": "Monado",
            "library_path": openxr_so,
        },
    }
    if monado_so and os.path.exists(monado_so):
        runtime["runtime"]["MND_libmonado_path"] = monado_so

    # In alle relevanten Verzeichnisse schreiben: Host-Config IMMER, und bei
    # Steam-Flatpak zusätzlich dessen Sandbox-Config (sonst findet das
    # gesandboxte Steam die WiVRn-Runtime nicht) -> "OpenXR-SteamFix".
    backup = ""
    wrote_any = False
    for d in venv.openxr_config_dirs():
        target = os.path.join(d, "active_runtime.json")
        try:
            os.makedirs(d, exist_ok=True)
            if os.path.exists(target):
                stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                bak = target + f".bak.{stamp}"
                shutil.copy2(target, bak)
                if target == ACTIVE_RUNTIME:
                    backup = bak
            with open(target, "w") as f:
                json.dump(runtime, f, indent=4)
            wrote_any = True
        except Exception as e:
            if target == ACTIVE_RUNTIME:
                return False, "write_failed", str(e)
            print(f"[OpenXR] Konnte {target} nicht schreiben: {e}")

    if not wrote_any:
        return False, "write_failed", ""

    return True, "ok", backup


# --------------------------------------------------------------------------- #
#  Fallback: Fix mit Root-Rechten (pkexec)
# --------------------------------------------------------------------------- #
def apply_openxr_fix_elevated():
    """
    Fallback, wenn der normale Schreibzugriff scheitert (z. B. weil die
    active_runtime.json oder ihr Ordner root gehört): schreibt die Datei
    über pkexec (grafische Passwortabfrage) und gibt den Ordner danach
    wieder dem Benutzer, damit künftige Fixes OHNE Root funktionieren.
    Rückgabe wie apply_openxr_fix: (erfolg, code, detail).
    """
    import tempfile
    import subprocess

    openxr_so, monado_so = find_wivrn_libs()
    if not openxr_so or not os.path.exists(openxr_so):
        return False, "libs_not_found", ""
    if not _is_elf(openxr_so):
        return False, "not_elf", openxr_so

    runtime = {
        "file_format_version": "1.0.0",
        "runtime": {
            "name": "Monado",
            "library_path": openxr_so,
        },
    }
    if monado_so and os.path.exists(monado_so):
        runtime["runtime"]["MND_libmonado_path"] = monado_so

    # Fertige JSON in eine Temp-Datei schreiben (die kopiert Root dann nur noch).
    try:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(runtime, tmp, indent=4)
        tmp.close()
    except Exception as e:
        return False, "write_failed", str(e)

    uid, gid = os.getuid(), os.getgid()
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    parts = []
    for d in venv.openxr_config_dirs():
        target = os.path.join(d, "active_runtime.json")
        parts.append(f"mkdir -p '{d}'")
        # Vorhandene Datei mit Zeitstempel sichern (nichts geht verloren)
        parts.append(f"if [ -f '{target}' ]; then cp '{target}' '{target}.bak.{stamp}'; fi")
        parts.append(f"cp '{tmp.name}' '{target}'")
        # Ordner + Datei zurück an den Benutzer, damit es künftig ohne Root geht
        parts.append(f"chown -R {uid}:{gid} '{d}'")
    script = " && ".join(parts)

    try:
        result = subprocess.run(["pkexec", "bash", "-c", script],
                                capture_output=True, text=True, timeout=180)
    except Exception as e:
        return False, "write_failed", str(e)
    finally:
        try:
            os.remove(tmp.name)
        except Exception:
            pass

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        # returncode 126/127 = Passwortdialog abgebrochen
        if result.returncode in (126, 127):
            return False, "cancelled", err
        return False, "write_failed", err

    backup = ACTIVE_RUNTIME + f".bak.{stamp}" if os.path.exists(ACTIVE_RUNTIME + f".bak.{stamp}") else ""
    return True, "ok", backup
