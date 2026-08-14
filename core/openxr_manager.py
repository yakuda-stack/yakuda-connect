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

from logging_setup import get_logger

log = get_logger("openxr_manager")


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
        with open(WIVRN_MANIFEST) as f:
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
        with open(ACTIVE_RUNTIME) as f:
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
            log.warning(f"[OpenXR] Konnte {target} nicht schreiben: {e}")

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
        except Exception as exc:
            log.debug("apply_openxr_fix_elevated: ignoriert — %s", exc)

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        # returncode 126/127 = Passwortdialog abgebrochen
        if result.returncode in (126, 127):
            return False, "cancelled", err
        return False, "write_failed", err

    backup = ACTIVE_RUNTIME + f".bak.{stamp}" if os.path.exists(ACTIVE_RUNTIME + f".bak.{stamp}") else ""
    return True, "ok", backup


# --------------------------------------------------------------------------- #
#  Manifest-Doktor: System-Manifeste pruefen und reparieren
# --------------------------------------------------------------------------- #
#  Hintergrund (GitHub-Issue "Steam startet nicht mehr", Nobara 44):
#  Steam startet seine Prozesse in einem pressure-vessel-Container und laesst
#  dabei 'capsule-capture-libs' ueber JEDES Runtime-Manifest in
#  /usr/share/openxr/1/ laufen. Zeigt dort ein Manifest auf eine Bibliothek,
#  die nicht existiert oder die falsche Bitness hat, bricht der Start ab:
#      x86_64-linux-gnu-capsule-capture-libs: error: code 0:
#      gelf_getehdr(...): invalid `Elf' handle
#      pressure-vessel-wrap: E: Child process exited with code 1
#  -> steamwebhelper-Endlosschleife, Steam laesst sich nicht mehr starten.
#
#  Typischer Ausloeser: ein auf Arch erstelltes Manifest landet auf Fedora.
#  Dort ist /usr/lib/wivrn 32-Bit (64-Bit liegt in /usr/lib64), und
#  /usr/lib32 gibt es gar nicht. Die Pfade "passen" also syntaktisch,
#  zeigen aber auf die falsche Architektur.
# --------------------------------------------------------------------------- #

MANIFEST_DIRS = [
    "/usr/share/openxr/1",
    "/usr/local/share/openxr/1",
    os.path.join(HOME, ".local/share/openxr/1"),
    "/etc/xdg/openxr/1",
]


def _expected_bits(filename):
    """32, wenn der Dateiname ein 32-Bit-Manifest kennzeichnet, sonst 64."""
    low = os.path.basename(filename).lower()
    for marker in (".i686.", ".i386.", ".x86.", ".32.", "_i686", "_i386", "_32", "32bit"):
        if marker in low:
            return 32
    return 64


def _resolve_lib(manifest_path, lib_value):
    """Relativen library_path relativ zum Manifest-Ordner absolut machen."""
    if not lib_value:
        return None
    if os.path.isabs(lib_value):
        return os.path.normpath(lib_value)
    return os.path.normpath(os.path.join(os.path.dirname(manifest_path), lib_value))


def scan_runtime_manifests():
    """
    Prueft alle OpenXR-Runtime-Manifeste in den bekannten System-Ordnern.

    Rueckgabe: Liste von dicts
        {path, library_path, resolved, expected_bits, found_bits, state}
    state:
        'ok'            -> Bibliothek existiert und hat die richtige Bitness
        'missing_lib'   -> Datei hinter library_path existiert nicht
        'arch_mismatch' -> existiert, aber falsche Bitness (Steam-Killer!)
        'no_path'       -> Manifest ohne library_path
        'unreadable'    -> JSON kaputt
    """
    results = []
    for d in MANIFEST_DIRS:
        if not os.path.isdir(d):
            continue
        try:
            names = sorted(os.listdir(d))
        except Exception:
            continue
        for name in names:
            if not name.endswith(".json"):
                continue
            path = os.path.join(d, name)
            if not os.path.isfile(path):
                continue
            entry = {"path": path, "library_path": "", "resolved": "",
                     "expected_bits": _expected_bits(name), "found_bits": None,
                     "state": "ok"}
            try:
                with open(path) as f:
                    data = json.load(f)
            except Exception:
                entry["state"] = "unreadable"
                results.append(entry)
                continue

            rt = data.get("runtime")
            if not isinstance(rt, dict):
                # api_layer-Dateien u. a. -> keine Runtime, nicht unser Thema
                continue

            lib = rt.get("library_path", "")
            entry["library_path"] = lib
            resolved = _resolve_lib(path, lib)
            entry["resolved"] = resolved or ""
            if not resolved:
                entry["state"] = "no_path"
            elif not os.path.exists(resolved):
                entry["state"] = "missing_lib"
            else:
                bits = venv.elf_class(resolved)
                entry["found_bits"] = bits
                if bits != entry["expected_bits"]:
                    entry["state"] = "arch_mismatch"
            results.append(entry)
    return results


def broken_runtime_manifests():
    """Nur die Manifeste, die Steam zum Absturz bringen koennen."""
    return [m for m in scan_runtime_manifests() if m["state"] != "ok"]


def _replacement_libs(bits):
    """(openxr_so, monado_so) passend zur gewuenschten Bitness — oder (None, None)."""
    if bits == 32:
        return venv.find_wivrn_libs32()
    o, m = venv.find_wivrn_libs()
    return o, m


def plan_manifest_repair(entries=None):
    """
    Legt fuer jedes defekte Manifest fest, was passieren soll:
      ('rewrite', entry, runtime_dict) -> Pfade auf die lokal gefundenen .so umbiegen
      ('disable', entry, None)         -> nach '<name>.disabled' umbenennen,
                                          damit Steam es nicht mehr einliest
    Rueckgabe: (actions, needs_root)
    """
    if entries is None:
        entries = broken_runtime_manifests()

    actions = []
    needs_root = False
    for e in entries:
        so, mon = _replacement_libs(e["expected_bits"])
        if so:
            runtime = {"file_format_version": "1.0.0",
                       "runtime": {"name": "Monado", "library_path": so}}
            if mon:
                runtime["runtime"]["MND_libmonado_path"] = mon
            actions.append(("rewrite", e, runtime))
        else:
            actions.append(("disable", e, None))
        if not os.access(os.path.dirname(e["path"]), os.W_OK):
            needs_root = True
    return actions, needs_root


def repair_runtime_manifests(entries=None, use_root=None):
    """
    Fuehrt den Reparaturplan aus. Vorhandene Dateien werden vorher mit
    Zeitstempel gesichert (<datei>.bak.JJJJMMTT_HHMMSS), es geht nichts verloren.

    Rueckgabe: (erfolg, code, detail)
      code: 'ok' | 'nothing_to_do' | 'cancelled' | 'write_failed'
      detail: kurze Zusammenfassung der geaenderten Dateien
    """
    import tempfile
    import subprocess

    actions, needs_root = plan_manifest_repair(entries)
    if not actions:
        return True, "nothing_to_do", ""

    if use_root is None:
        use_root = needs_root

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    changed = []

    if not use_root:
        try:
            for kind, e, runtime in actions:
                target = e["path"]
                shutil.copy2(target, f"{target}.bak.{stamp}")
                if kind == "rewrite":
                    with open(target, "w") as f:
                        json.dump(runtime, f, indent=4)
                    changed.append(f"{target} -> {runtime['runtime']['library_path']}")
                else:
                    shutil.move(target, f"{target}.disabled")
                    changed.append(f"{target} (deaktiviert)")
        except Exception as ex:
            return False, "write_failed", str(ex)
        return True, "ok", "\n".join(changed)

    # --- Root-Weg: alles in EINEM pkexec-Aufruf ---------------------------- #
    tmpdir = tempfile.mkdtemp(prefix="yakuda-oxr-")
    parts = []
    try:
        for idx, (kind, e, runtime) in enumerate(actions):
            target = e["path"]
            parts.append(f"cp -a '{target}' '{target}.bak.{stamp}'")
            if kind == "rewrite":
                tmp_file = os.path.join(tmpdir, f"m{idx}.json")
                with open(tmp_file, "w") as f:
                    json.dump(runtime, f, indent=4)
                os.chmod(tmp_file, 0o644)
                parts.append(f"cp '{tmp_file}' '{target}'")
                parts.append(f"chmod 644 '{target}'")
                changed.append(f"{target} -> {runtime['runtime']['library_path']}")
            else:
                parts.append(f"mv '{target}' '{target}.disabled'")
                changed.append(f"{target} (deaktiviert)")

        script = " && ".join(parts)
        result = subprocess.run(["pkexec", "bash", "-c", script],
                                capture_output=True, text=True, timeout=180)
    except Exception as ex:
        return False, "write_failed", str(ex)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        if result.returncode in (126, 127):
            return False, "cancelled", err
        return False, "write_failed", err

    return True, "ok", "\n".join(changed)
