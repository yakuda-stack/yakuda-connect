#!/usr/bin/env python3
"""
core/advanced_info.py — Was passiert bei einer Aktion wirklich?
==============================================================
Eine einzige Stelle, an der fuer jede Aktion steht:

    * eine kurze Erklaerung, was sie tut
    * welche Dateien/Ordner sie anfasst
    * welche Rechte sie dafuer braucht
    * der entsprechende Terminal-Befehl zum Kopieren

Die Oberflaeche blendet diese Angaben im **Advanced Mode** unter der
jeweiligen Schaltflaeche ein (ui/advanced_panel.py). Im normalen Modus ist
davon nichts zu sehen — die Oberflaeche bleibt unveraendert.

Warum ein eigenes Modul und nicht Text direkt in der UI
-------------------------------------------------------
Die Angaben muessen zum Code passen, nicht zu dem, was mal jemand in einen
Tooltip geschrieben hat. Steht die Pfadermittlung hier neben der Aktion,
faellt beim Aendern auf, dass die Beschreibung mitzupflegen ist. Ausserdem
ist das Modul Qt-frei und damit ohne Bildschirm testbar (tests/test_advanced_info.py).

WICHTIG — der Befehl wird NIE automatisch ausgefuehrt.
Er dient ausschliesslich zum Nachvollziehen und Kopieren. Was die App
tatsaechlich tut, steht im jeweils genannten Modul; die Befehle hier sind
das handgemachte Gegenstueck dazu.

Aufbau eines Eintrags (siehe describe())
----------------------------------------
    {
      "title":    "OpenXR-Runtime reparieren",   # uebersetzt
      "explain":  "Schreibt ...",                # uebersetzt, 1-3 Saetze
      "paths":    ["/home/x/.config/openxr/1/active_runtime.json", ...],
      "perms":    ["Schreibrecht im eigenen Home", "ggf. Root ueber pkexec"],
      "commands": ["cat ~/.config/openxr/1/active_runtime.json", ...],
      "source":   "core/openxr_manager.py",      # wo es im Code steht
    }

``paths`` und ``commands`` werden zur LAUFZEIT ermittelt, damit dort der
Pfad steht, der auf diesem System wirklich benutzt wird (Flatpak-Steam,
XDG_CONFIG_HOME, abweichende Bibliotheksordner) — nicht ein Beispielpfad.
"""
import os

import paths as app_paths
import vr_environment as venv
from logging_setup import get_logger
from translations import tr

log = get_logger("advanced_info")

HOME = os.path.expanduser("~")


# --------------------------------------------------------------------------- #
#  Zustand: ist der Advanced Mode eingeschaltet?
# --------------------------------------------------------------------------- #
# Bewusst nur ein Schalter im Speicher. Gespeichert und geladen wird er in
# core/main.py ueber die normale config.json ("advanced_mode") — dieses Modul
# soll nichts ueber Dateiformate der App wissen muessen.
_enabled = False


def is_enabled() -> bool:
    """True, wenn der Advanced Mode aktiv ist."""
    return _enabled


def set_enabled(value: bool) -> None:
    """Advanced Mode ein-/ausschalten (die UI aktualisiert sich danach selbst)."""
    global _enabled
    _enabled = bool(value)
    log.info("Advanced Mode: %s", "an" if _enabled else "aus")


# --------------------------------------------------------------------------- #
#  Bausteine fuer die Rechte-Angaben (uebersetzt)
# --------------------------------------------------------------------------- #
def _perm_home():
    return tr("adv_perm_home")


def _perm_root():
    return tr("adv_perm_root")


def _perm_root_maybe():
    return tr("adv_perm_root_maybe")


def _perm_none():
    return tr("adv_perm_none")


def _perm_network(host):
    return tr("adv_perm_network").format(host=host)


# --------------------------------------------------------------------------- #
#  Die einzelnen Aktionen
# --------------------------------------------------------------------------- #
def _firewall():
    """
    Ports fuer WiVRn freigeben — siehe core/firewall.py.

    Die Ports stehen dort als Konstanten; sie werden hier importiert statt
    abgeschrieben, damit eine Aenderung nicht an zwei Stellen gepflegt
    werden muss.
    """
    import firewall as fw

    try:
        kind = fw.detect()["kind"]
    except Exception as exc:            # z. B. kein systemctl vorhanden
        log.debug("_firewall: Erkennung fehlgeschlagen — %s", exc)
        kind = None

    if kind:
        commands = list(fw.manual_commands(kind))
    else:
        commands = [tr("adv_fw_no_firewall_cmd")]

    return {
        "title": tr("adv_fw_title"),
        "explain": tr("adv_fw_explain").format(
            port=fw.PORT, mdns=fw.MDNS_PORT, fw=kind or tr("adv_fw_none")),
        "paths": [fw.UFW_PROFILE_PATH] if kind == fw.UFW else [],
        "perms": [_perm_root()] if kind in fw.SUPPORTED else [_perm_none()],
        "commands": commands,
        "source": "core/firewall.py",
    }


def _openxr_fix():
    """Steam-Fix: active_runtime.json mit absoluten Pfaden schreiben."""
    targets = [os.path.join(d, "active_runtime.json")
               for d in venv.openxr_config_dirs()]
    openxr_so, _monado = venv.find_wivrn_libs()
    return {
        "title": tr("adv_oxr_title"),
        "explain": tr("adv_oxr_explain"),
        "paths": targets + ([openxr_so] if openxr_so else []),
        # Normalfall: die Datei liegt im eigenen Home. Gehoert sie root
        # (kommt vor, wenn sie mal von einem Installer angelegt wurde),
        # faellt openxr_manager auf pkexec zurueck.
        "perms": [_perm_home(), _perm_root_maybe()],
        "commands": [f"cat '{targets[0]}'"] if targets else [],
        "source": "core/openxr_manager.py",
    }


def _runtime_switch():
    """OpenXR-Runtime zwischen WiVRn und SteamVR umschalten."""
    targets = [os.path.join(d, "active_runtime.json")
               for d in venv.openxr_config_dirs()]
    wivrn_cfg = venv.wivrn_config_file()
    return {
        "title": tr("adv_rt_title"),
        "explain": tr("adv_rt_explain"),
        "paths": targets + [wivrn_cfg],
        "perms": [_perm_home(), _perm_root_maybe()],
        "commands": [f"cat '{targets[0]}'"] if targets else [],
        "source": "core/openxr_manager.py, core/vr_environment.py",
    }


def _vr_priority():
    """CAP_SYS_NICE auf die wivrn-server-Binary setzen."""
    binary = venv.wivrn_server_binary() or "wivrn-server"
    return {
        "title": tr("adv_prio_title"),
        "explain": tr("adv_prio_explain"),
        "paths": [binary],
        "perms": [_perm_root()],
        "commands": [
            f"getcap '{binary}'",
            f"sudo setcap cap_sys_nice+ep '{binary}'",
        ],
        "source": "ui/vr_runtime_widget.py",
    }


def _wayvr_design():
    """WayVR-Design von cubee-cb installieren."""
    cfg = os.path.join(HOME, ".config/wayvr")
    return {
        "title": tr("adv_wayvr_title"),
        "explain": tr("adv_wayvr_explain"),
        "paths": [cfg],
        "perms": [_perm_home(),
                  _perm_network("github.com")],
        "commands": [f"ls -la '{cfg}'"],
        "source": "core/overlay_manager.py",
    }


def _oscquery():
    """OSCQuery in den Configs unterstuetzter Programme aktivieren."""
    try:
        import queryfix
        entries = [os.path.expanduser(p["path"]) for p in queryfix.PROGRAMS]
        keys = ", ".join(f'{p["name"]}: {p["key"]}' for p in queryfix.PROGRAMS)
    except Exception as exc:
        log.debug("_oscquery: %s", exc)
        entries, keys = [], ""
    return {
        "title": tr("adv_osc_title"),
        "explain": tr("adv_osc_explain").format(keys=keys),
        "paths": entries,
        "perms": [_perm_home()],
        "commands": [f"cat '{p}'" for p in entries],
        "source": "core/queryfix.py",
    }


def _backup_create():
    """VR-Backup anlegen (nur lesend auf dem System, schreibend im Home)."""
    import backup_manager as bm
    sources = [p for group in bm.SOURCES.values() for p in group]
    return {
        "title": tr("adv_backup_title"),
        "explain": tr("adv_backup_explain"),
        "paths": [bm.BACKUP_DIR] + sources,
        "perms": [_perm_home()],
        "commands": [f"ls -la '{bm.BACKUP_DIR}'"],
        "source": "core/backup_manager.py",
    }


def _backup_restore():
    """VR-Backup zurueckspielen — fasst als einziges auch /usr und /opt an."""
    import backup_manager as bm
    return {
        "title": tr("adv_restore_title"),
        "explain": tr("adv_restore_explain"),
        "paths": [os.path.join(HOME, ".config/openxr"),
                  os.path.join(HOME, ".config/openvr"),
                  os.path.join(HOME, ".config/wivrn"),
                  "/usr/share/openxr", "/opt/xrizer", "/opt/opencomposite"],
        "perms": [_perm_home(), _perm_root()],
        "commands": [f"ls -la '{bm.BACKUP_DIR}'"],
        "source": "core/backup_manager.py",
    }


def _server():
    """WiVRn-Server starten/beenden."""
    log_path = app_paths.cache_file("wivrn-server.log")
    return {
        "title": tr("adv_server_title"),
        "explain": tr("adv_server_explain"),
        "paths": [log_path, venv.wivrn_config_file()],
        "perms": [_perm_none()],
        "commands": ["wivrn-server", "pkill wivrn-server"],
        "source": "core/main.py",
    }


def _update_check():
    """Der stille Versions-Check beim Start — der einzige automatische Zugriff."""
    return {
        "title": tr("adv_update_title"),
        "explain": tr("adv_update_explain"),
        "paths": [],
        "perms": [_perm_network("raw.githubusercontent.com")],
        "commands": [
            "curl -s https://raw.githubusercontent.com/yakuda-stack/"
            "yakuda-connect/main/core/main.py | grep -m1 APP_VERSION",
        ],
        "source": "core/install_worker.py",
    }


def _diagnostics():
    """Logdatei und Diagnosebericht."""
    return {
        "title": tr("adv_diag_title"),
        "explain": tr("adv_diag_explain"),
        "paths": [app_paths.log_file(), app_paths.config_file("config.json")],
        "perms": [_perm_home()],
        "commands": [f"tail -n 200 '{app_paths.log_file()}'"],
        "source": "core/logging_setup.py",
    }


# Alle bekannten Aktionen. Der Schluessel ist das, was die UI angibt.
ACTIONS = {
    "firewall":       _firewall,
    "openxr_fix":     _openxr_fix,
    "runtime_switch": _runtime_switch,
    "vr_priority":    _vr_priority,
    "wayvr_design":   _wayvr_design,
    "oscquery":       _oscquery,
    "backup_create":  _backup_create,
    "backup_restore": _backup_restore,
    "server":         _server,
    "update_check":   _update_check,
    "diagnostics":    _diagnostics,
}


# --------------------------------------------------------------------------- #
#  Kurztitel fuer die Kastenueberschrift
# --------------------------------------------------------------------------- #
# Die Oberflaeche schreibt "Technical details: <Kurztitel>" ueber jeden Kasten.
# Ohne den Zusatz stehen auf einer Seite mehrere gleich beschriftete Kaesten
# untereinander (im Dashboard etwa Firewall und Serversteuerung), und man muss
# raten, welcher wozu gehoert.
#
# Bewusst eine EIGENE, flache Tabelle statt eines Felds in describe():
# describe() ermittelt Pfade und ruft dafuer teils Programme auf (die
# Firewall-Erkennung startet systemctl). Die Ueberschrift wird aber schon beim
# Aufbau der Seite gebraucht — sie darf nichts kosten.
SHORT_TITLES = {
    "firewall":       "adv_short_firewall",
    "server":         "adv_short_server",
    "openxr_fix":     "adv_short_openxr",
    "runtime_switch": "adv_short_runtime",
    "vr_priority":    "adv_short_prio",
    "wayvr_design":   "adv_short_wayvr",
    "oscquery":       "adv_short_osc",
    "backup_create":  "adv_short_backup",
    "backup_restore": "adv_short_restore",
    "update_check":   "adv_short_update",
    "diagnostics":    "adv_short_diag",
}


def short_title(action_id: str) -> str:
    """
    Kurzbezeichnung fuer die Kastenueberschrift, uebersetzt. Leer, wenn es
    fuer die Aktion keine gibt — die Oberflaeche zeigt dann nur den
    allgemeinen Text, statt einen Doppelpunkt ins Leere zu setzen.
    """
    key = SHORT_TITLES.get(action_id)
    return tr(key) if key else ""


def describe(action_id: str) -> dict:
    """
    Beschreibung einer Aktion. Unbekannte oder fehlgeschlagene Aktionen geben
    einen leeren, aber vollstaendig geformten Eintrag zurueck — die UI muss
    sich nie mit None herumschlagen.
    """
    empty = {"title": action_id, "explain": "", "paths": [],
             "perms": [], "commands": [], "source": ""}
    builder = ACTIONS.get(action_id)
    if builder is None:
        log.warning("Unbekannte Advanced-Aktion: %s", action_id)
        return empty
    try:
        data = builder()
    except Exception as exc:
        # Die Beschreibung darf NIE die Aktion selbst verhindern. Faellt die
        # Pfadermittlung aus (fehlendes WiVRn, kaputte Config), zeigt die UI
        # eben weniger an, statt dass der Knopf nicht mehr funktioniert.
        log.warning("Advanced-Info fuer '%s' fehlgeschlagen: %s", action_id, exc)
        return empty
    # Fehlende Felder auffuellen, damit Aufrufer sich darauf verlassen koennen.
    result = dict(empty)
    result.update(data)
    return result


def as_text(action_id: str) -> str:
    """
    Dieselbe Beschreibung als reiner Text — fuer den Diagnosebericht und zum
    Kopieren in einen Fehlerbericht.
    """
    d = describe(action_id)
    lines = [d["title"], ""]
    if d["explain"]:
        lines += [d["explain"], ""]
    if d["paths"]:
        lines.append(tr("adv_paths_label"))
        lines += [f"  {p}" for p in d["paths"]]
        lines.append("")
    if d["perms"]:
        lines.append(tr("adv_perms_label"))
        lines += [f"  {p}" for p in d["perms"]]
        lines.append("")
    if d["commands"]:
        lines.append(tr("adv_cmd_label"))
        lines += [f"  {c}" for c in d["commands"]]
        lines.append("")
    if d["source"]:
        lines.append(f"{tr('adv_source_label')} {d['source']}")
    return "\n".join(lines).strip()
