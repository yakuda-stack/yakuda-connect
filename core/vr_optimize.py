#!/usr/bin/env python3
"""
core/vr_optimize.py — "Alles fuer maximale VR-Performance optimieren"
=====================================================================
Einmaliges Angebot beim ersten Oeffnen des Dashboards. Fasst die Fixes
zusammen, die sonst einzeln angeklickt werden muessen:

    firewall    Firewall fixen & Port 9757 freigeben   (core/firewall.py)
    netbuffers  Netzwerkpuffer DAUERHAFT anheben        (core/netbuffers.py)
    runtime     OpenXR-Runtime auf WiVRn + OpenXR-Fix   (core/openxr_manager.py)
    priority    VR-Prioritaet: CAP_SYS_NICE             (setcap auf wivrn-server)

Die Root-Schritte (Firewall, Puffer, setcap) laufen gemeinsam in EINEM
pkexec — der Nutzer sieht genau eine Passwortabfrage. Jeder Schritt laeuft
darin in einer eigenen ``sh -c``, damit ein Fehler die anderen nicht
mitreisst, und meldet sein Ergebnis als ``YK:<name>:<exitcode>``.

Die Firewall-Befehle sind 1:1 die aus firewall._script() — also genau das,
was der Dashboard-Knopf macht (ufw-Profil "wivrn", firewalld-Dienst "wivrn").

Der Runtime-Schritt braucht kein Root und laeuft danach im Benutzerkontext.

Bewusst ohne Qt: testbar ohne Anzeige. Die Dialoge baut
core/tabs/dashboard_optimize_mixin.py.
"""
import datetime
import os
import re

import firewall as fw
import netbuffers as nbuf
import openxr_manager as oxr
import paths
import proc
import vr_autotune as autotune
import vr_environment as venv
from jsonio import read_json, update_json
from logging_setup import get_logger

log = get_logger("vr_optimize")

APP_CONFIG_FILE = paths.config_file("config.json")

# Merker: das Angebot wurde schon einmal gezeigt (ISO-Zeitstempel).
KEY_ASKED = "dashboard_optimize_asked"

FIREWALL = "firewall"
NETBUFFERS = "netbuffers"
RUNTIME = "runtime"
PRIORITY = "priority"

ROOT_STEPS = (FIREWALL, NETBUFFERS, PRIORITY)


# --------------------------------------------------------------------------- #
#  Merker
# --------------------------------------------------------------------------- #
def already_asked():
    data = read_json(APP_CONFIG_FILE, default={})
    return isinstance(data, dict) and bool(data.get(KEY_ASKED))


def mark_asked():
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    if not update_json(APP_CONFIG_FILE, {KEY_ASKED: stamp}):
        log.warning("Merker %s konnte nicht geschrieben werden.", KEY_ASKED)


# --------------------------------------------------------------------------- #
#  Ist ein Fix schon aktiv?
# --------------------------------------------------------------------------- #
def _firewalld_has_wivrn():
    """
    firewalld ohne root pruefen: die Zonen-Datei der Standardzone lesen.

    'firewall-cmd --list-services' kann eine Passwortabfrage ausloesen
    (siehe firewall.already_configured), deshalb nur Dateien. Nicht lesbar
    -> None (unbekannt).
    """
    zone = "public"
    try:
        with open("/etc/firewalld/firewalld.conf", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DefaultZone="):
                    zone = line.split("=", 1)[1].strip() or zone
    except OSError:
        pass
    try:
        with open(f"/etc/firewalld/zones/{zone}.xml", encoding="utf-8") as f:
            xml = f.read()
    except OSError:
        return None
    if re.search(r'<service\s+name="wivrn"', xml):
        return True
    return bool(re.search(rf'<port[^>]+port="{fw.PORT}"', xml))


def firewall_needed():
    """
    (noetig, kind). Nicht noetig, wenn keine Firewall da ist oder nur
    nftables/iptables (die fassen wir nie automatisch an).
    """
    kind = fw.detect()["kind"]
    if kind not in fw.SUPPORTED:
        return False, kind
    if kind == fw.UFW:
        return not fw.already_configured(kind), kind
    return _firewalld_has_wivrn() is not True, kind


def netbuffers_needed():
    return not (nbuf.is_applied() and nbuf.is_persistent())


def priority_binary():
    """wivrn-server-Pfad, wenn setcap dort moeglich ist — sonst ''."""
    if not venv.supports_setcap():
        return ""
    return venv.wivrn_server_binary() or ""


def has_vr_priority(path):
    res = proc.run([venv.capability_tool("getcap"), path], timeout=proc.DEFAULT_TIMEOUT)
    return "cap_sys_nice" in (res.stdout or "").lower()


def priority_needed():
    path = priority_binary()
    return bool(path) and not has_vr_priority(path)


def runtime_needed():
    """WiVRn ist aktive Runtime UND die active_runtime.json ist korrekt."""
    if not oxr.find_wivrn_libs()[0]:
        return False
    return not (oxr.active_runtime_name() == "wivrn" and oxr.is_openxr_fix_applied())


def pending_steps():
    """Liste der noch offenen Fixes (leer = alles schon aktiv)."""
    steps = []
    needed, _kind = firewall_needed()
    if needed:
        steps.append(FIREWALL)
    if netbuffers_needed():
        steps.append(NETBUFFERS)
    if runtime_needed():
        steps.append(RUNTIME)
    if priority_needed():
        steps.append(PRIORITY)
    return steps


# --------------------------------------------------------------------------- #
#  Ausfuehren
# --------------------------------------------------------------------------- #
def _step_scripts(steps):
    """[(name, skript)] fuer die Root-Schritte."""
    out = []
    if FIREWALL in steps:
        _needed, kind = firewall_needed()
        if kind in fw.SUPPORTED:
            out.append((FIREWALL, fw._script(kind)))
    if NETBUFFERS in steps:
        out.append((NETBUFFERS, nbuf._script(True)))
    if PRIORITY in steps:
        path = priority_binary()
        if path:
            out.append((PRIORITY,
                        f"'{venv.capability_tool('setcap')}' cap_sys_nice+ep '{path}'"))
    return out


def _run_root_steps(scripts):
    """
    Alle Root-Schritte in EINEM pkexec. Rueckgabe: {name: (ok, fehler)}.

    Die Skripte gehen als Positionsparameter ($1, $2, ...) hinein — so muss
    nichts verschachtelt gequotet werden.
    """
    if not scripts:
        return {}
    runner = "; ".join(
        f'sh -c "${i}" >&2; echo "YK:{name}:$?"'
        for i, (name, _s) in enumerate(scripts, start=1))
    cmd = ["pkexec", "sh", "-c", runner, "sh"] + [s for _n, s in scripts]
    res = proc.run(cmd, timeout=proc.LONG_TIMEOUT)

    results = {}
    for line in (res.stdout or "").splitlines():
        m = re.match(r"YK:(\w+):(\d+)$", line.strip())
        if m:
            ok = m.group(2) == "0"
            results[m.group(1)] = (ok, "" if ok else f"exit {m.group(2)}")

    err = (res.stderr or "").strip()
    if res.returncode == 126 and not results:
        err = err or "pkexec: cancelled"
    for name, _s in scripts:
        if name not in results:
            results[name] = (False, err or f"exit {res.returncode}")
    return results


def _run_runtime_step():
    """OpenXR-Runtime auf WiVRn + OpenXR-Fix. Rueckgabe: (ok, code)."""
    try:
        broken = oxr.broken_runtime_manifests()
    except Exception:                                          # noqa: BLE001
        broken = []
    if broken:
        ok, code, detail = oxr.repair_runtime_manifests(broken)
        if not ok:
            log.warning("[Optimize] Manifest-Reparatur: %s %s", code, detail)

    ok, code, _detail = oxr.apply_openxr_fix()
    if not ok and code == "write_failed":
        ok, code, _detail = oxr.apply_openxr_fix_elevated()
    if not ok:
        return False, code

    # War die OpenVR-Kompatibilitaet fuer SteamVR abgeschaltet, die vorherige
    # Auswahl zurueckholen — sonst starten OpenVR-Spiele (VRChat) nicht.
    previous = autotune.previous_compat()
    mode, _path = venv.current_openvr_compat()
    if previous and mode == venv.OPENVR_DISABLED:
        if venv.set_openvr_compat(*previous):
            autotune.forget_compat()
    return True, "ok"


def apply_all(steps):
    """
    Fuehrt die angegebenen Fixes aus. Rueckgabe: {name: (ok, fehler)}.
    """
    results = _run_root_steps(_step_scripts(steps))
    if RUNTIME in steps:
        ok, code = _run_runtime_step()
        results[RUNTIME] = (ok, "" if ok else code)
    for name, (ok, err) in results.items():
        log.info("[Optimize] %s: %s %s", name, "ok" if ok else "FEHLER", err)
    return results
