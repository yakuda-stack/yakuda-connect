#!/usr/bin/env python3
"""
core/vr_autotune.py — Einmalige automatische VR-Einrichtung
===========================================================
Zwei Dinge, die bisher Handarbeit waren:

1. **Erst-Backup + Umstellung auf xrizer (genau EINMAL)**

   Sobald erkennbar ist, dass auf diesem Rechner schon einmal wirklich VR
   lief, wird einmalig ein Backup der VR-Laufumgebung angelegt und danach
   die OpenVR-Kompatibilitaet auf **xrizer** gestellt (bessere Leistung als
   OpenComposite). Danach wird das in der App-Config vermerkt und nie wieder
   angefasst — auch dann nicht, wenn der Nutzer spaeter von Hand etwas
   anderes waehlt. Das ist der ganze Sinn des Merkers: die App soll dem
   Nutzer nicht bei jedem Start in seine Einstellungen hineinregieren.

   Woran erkennt man "hier lief schon einmal VR"? Daran, dass ALLE Ordner
   existieren, die auch gesichert werden:

       ~/.config/openvr     legt erst eine OpenVR-Anwendung an
       ~/.config/openxr     legt erst eine OpenXR-Runtime an
       ~/.config/wivrn      legt erst der WiVRn-Server an
       /usr/share/openxr    System-Manifeste (im Backup: usr/openxr)
       das WiVRn-Manifest   darin (System-Installation vorhanden)

   Ein frisch installiertes System hat diese Ordner NICHT. Wer sie alle hat,
   hat die Brille schon einmal aufgehabt — genau dann ist ein Backup
   sinnvoll (es sichert einen erprobten Zustand) und genau dann darf man
   auch die Kompatibilitaets-Auswahl anfassen.

   Geprueft wird OHNE Timer: einmal beim Start der Software und einmal,
   nachdem der WiVRn-Server beendet wurde. Waehrend der Server LAEUFT wird
   nichts geschrieben — WiVRn liest ``openvr-compat-path`` nur beim
   Hochfahren aus (server/active_runtime.cpp). Eine Aenderung mitten in der
   Sitzung waere wirkungslos und wuerde nur eine Meldung erzeugen, die zum
   sichtbaren Zustand nicht passt.

2. **Gedaechtnis fuer die Runtime-Umschaltung**

   Wird die OpenXR-Runtime auf SteamVR gestellt, muss WiVRns OpenVR-
   Kompatibilitaet aus dem Weg — SteamVR bringt sein eigenes OpenVR mit.
   Der vorherige Zustand wird hier gemerkt, damit beim Zurueckschalten auf
   WiVRn genau die vorherige Auswahl wieder angeboten werden kann.

Dieses Modul hat bewusst KEINE Qt-Importe: es soll ohne laufende GUI
testbar sein. Die Meldungen zeigt der Aufrufer (core/main.py bzw.
ui/vr_runtime_widget.py).
"""
import datetime
import os

import backup_manager as backup
import paths
import proc
import vr_environment as venv
from jsonio import read_json, update_json
from logging_setup import get_logger

log = get_logger("vr_autotune")


HOME = os.path.expanduser("~")
APP_CONFIG_FILE = paths.config_file("config.json")

# Merker: die einmalige Umstellung auf xrizer ist erledigt (ISO-Zeitstempel).
KEY_XRIZER_DONE = "openvr_auto_xrizer"
# Zustand der OpenVR-Kompatibilitaet, BEVOR auf SteamVR umgeschaltet wurde.
KEY_PREV_COMPAT = "openvr_compat_before_steamvr"


# --------------------------------------------------------------------------- #
#  App-Config
# --------------------------------------------------------------------------- #
def _read_config():
    data = read_json(APP_CONFIG_FILE, default={})
    return data if isinstance(data, dict) else {}


def _write_config(changes):
    if not update_json(APP_CONFIG_FILE, changes):
        log.warning("App-Config konnte nicht geschrieben werden (%s).", APP_CONFIG_FILE)
        return False
    return True


# --------------------------------------------------------------------------- #
#  "Hier lief schon einmal VR"
# --------------------------------------------------------------------------- #
def openxr_share_dir():
    """
    Der ``openxr``-Ordner, den das Backup unter ``usr/`` sichert.

    Auf Arch/Fedora ist das ``/usr/share/openxr``; bei Selbstbau liegt er
    unter ``/usr/local/share/openxr`` oder im HOME. Abgeleitet wird er aus
    dem gefundenen WiVRn-Manifest (``<share>/openxr/1/openxr_wivrn.json``),
    damit hier kein fester Pfad steht, den es auf halben Distributionen
    nicht gibt.
    """
    manifest = venv.find_wivrn_manifest()
    return os.path.dirname(os.path.dirname(manifest)) or "/usr/share/openxr"


def required_paths():
    """
    Die Pfade, deren Vorhandensein beweist, dass VR schon einmal lief.

    Bewusst genau die Orte, die auch das Backup sichert (siehe
    backup_manager.SOURCES):

        ~/.config/openvr        config/openvr
        ~/.config/openxr        config/openxr
        ~/.config/wivrn         config/wivrn
        /usr/share/openxr       usr/openxr   (siehe openxr_share_dir)

    Dazu das WiVRn-Manifest selbst: der Ordner allein kann auch von einer
    anderen Runtime stammen.
    """
    return [
        os.path.join(HOME, ".config/openvr"),
        os.path.join(HOME, ".config/openxr"),
        venv.wivrn_config_dir(),
        openxr_share_dir(),
        venv.find_wivrn_manifest(),
    ]


def missing_paths():
    """Welche der Pflichtpfade fehlen? (leere Liste = alles da)"""
    return [p for p in required_paths() if not os.path.exists(p)]


def vr_was_used():
    """True, wenn alle Pflichtpfade existieren."""
    return not missing_paths()


def server_is_running():
    """Laeuft gerade ein wivrn-server? (kein Timer, nur eine Momentaufnahme)"""
    return proc.run_ok(["pgrep", "-x", "wivrn-server"])


# --------------------------------------------------------------------------- #
#  Merker der einmaligen xrizer-Umstellung
# --------------------------------------------------------------------------- #
def xrizer_done():
    return bool(_read_config().get(KEY_XRIZER_DONE))


def mark_xrizer_done(path=""):
    """Einmalige Umstellung als erledigt vermerken — danach nie wieder."""
    _write_config({
        KEY_XRIZER_DONE: datetime.datetime.now().isoformat(timespec="seconds"),
        "openvr_auto_xrizer_path": path,
    })


def xrizer_path():
    """Pfad einer vollstaendigen xrizer-Installation — oder ''."""
    return venv.find_openvr_compat("xrizer")


# --------------------------------------------------------------------------- #
#  Gedaechtnis fuer die Runtime-Umschaltung (SteamVR <-> WiVRn)
# --------------------------------------------------------------------------- #
def compat_label(mode, path=""):
    """Lesbarer Name eines Kompatibilitaets-Zustands fuer Meldungen."""
    if mode == venv.OPENVR_DISABLED:
        return "Disabled"
    if mode == venv.OPENVR_PATH and path:
        low = os.path.basename(path.rstrip("/")).lower()
        name = ("xrizer" if "xrizer" in low else
                "OpenComposite" if "opencomposite" in low else
                "VapoR" if "vapor" in low else os.path.basename(path.rstrip("/")))
        return f"{name} ({path})"
    return "Default"


def remember_compat():
    """
    Aktuellen Zustand merken (vor dem Abschalten fuer SteamVR).

    Ein bereits abgeschalteter Zustand wird NICHT gemerkt: sonst wuerde beim
    naechsten Zurueckschalten "Deaktiviert wiederherstellen?" gefragt — eine
    Frage ohne Nutzen.
    """
    mode, path = venv.current_openvr_compat()
    if mode == venv.OPENVR_DISABLED:
        return False
    return _write_config({KEY_PREV_COMPAT: {"mode": mode, "path": path}})


def previous_compat():
    """Gemerkter Zustand als ``(mode, path)`` — oder None."""
    raw = _read_config().get(KEY_PREV_COMPAT)
    if not isinstance(raw, dict):
        return None
    mode = raw.get("mode")
    path = raw.get("path", "") or ""
    if mode == venv.OPENVR_PATH and path:
        return venv.OPENVR_PATH, path
    if mode == venv.OPENVR_DEFAULT:
        return venv.OPENVR_DEFAULT, ""
    return None


def forget_compat():
    _write_config({KEY_PREV_COMPAT: None})


# --------------------------------------------------------------------------- #
#  Der eigentliche Durchlauf (Start der App / nach Server-Stopp)
# --------------------------------------------------------------------------- #
def run_auto_setup(server_running=None):
    """
    Einmal-Automatik: Backup anlegen, danach auf xrizer stellen.

    Rueckgabe (dict), damit der Aufrufer die Meldung bauen kann:
        backup_created  bool   — es wurde jetzt ein Backup angelegt
        switched        bool   — die Kompatibilitaet wurde auf xrizer gesetzt
        path            str    — der eingetragene xrizer-Ordner
        previous        str    — was vorher eingestellt war (lesbar)
        skipped         str    — Grund, falls nichts passiert ist (fuers Log)
    """
    result = {"backup_created": False, "switched": False,
              "path": "", "previous": "", "skipped": ""}

    # 1. Das bisherige Verhalten bleibt unveraendert: fehlt ein Backup, aber
    #    es gibt eine VR-Umgebung, wird eines angelegt. Das prueft der
    #    backup_manager selbst anhand seines Flags.
    try:
        result["backup_created"] = bool(backup.auto_backup_on_start())
    except Exception as exc:                                   # noqa: BLE001
        log.warning("[Autotune] Auto-Backup fehlgeschlagen: %s", exc)

    # 2. Einmalige xrizer-Umstellung — nur wenn sie noch nie lief.
    if xrizer_done():
        result["skipped"] = "already_done"
        return result

    if server_running is None:
        server_running = server_is_running()
    if server_running:
        # WiVRn liest den Pfad nur beim Start des Servers. Waehrend einer
        # laufenden Sitzung waere die Aenderung wirkungslos.
        result["skipped"] = "server_running"
        return result

    missing = missing_paths()
    if missing:
        # Noch nie VR gestartet (oder WiVRn nicht installiert) — dann ist
        # weder ein Backup aussagekraeftig noch eine Umstellung angebracht.
        result["skipped"] = f"missing:{os.path.basename(missing[0])}"
        return result

    target = xrizer_path()
    if not target:
        # xrizer ist nicht installiert. NICHT als erledigt markieren: wird es
        # spaeter nachinstalliert, greift die Automatik dann.
        result["skipped"] = "no_xrizer"
        return result

    # 3. Sicherheitsnetz: an fremder Konfiguration wird erst gedreht, wenn ein
    #    Backup wirklich existiert.
    if not backup.has_backup_flag():
        if not backup.create_vr_backup():
            log.warning("[Autotune] Backup fehlgeschlagen — keine Umstellung.")
            result["skipped"] = "backup_failed"
            return result
        result["backup_created"] = True

    mode, current = venv.current_openvr_compat()

    if mode == venv.OPENVR_DISABLED:
        # Bewusst abgeschaltet (z. B. weil gerade SteamVR die Runtime ist).
        # Nicht ueberfahren und auch nicht abhaken — beim naechsten Durchlauf
        # kann es anders aussehen.
        result["skipped"] = "disabled_by_user"
        return result

    same_as_target = (
        (mode == venv.OPENVR_PATH and current and
         os.path.realpath(current) == os.path.realpath(target)) or
        (mode == venv.OPENVR_DEFAULT and
         os.path.realpath(venv.wivrn_autodetect_path() or "/") == os.path.realpath(target))
    )
    if same_as_target:
        # Es laeuft ohnehin schon ueber xrizer — nichts zu tun, aber erledigt.
        mark_xrizer_done(target)
        result["skipped"] = "already_xrizer"
        return result

    previous_label = compat_label(mode, current)
    if not venv.set_openvr_compat(venv.OPENVR_PATH, target):
        result["skipped"] = "write_failed"
        return result

    mark_xrizer_done(target)
    log.info("[Autotune] OpenVR-Kompatibilitaet automatisch auf xrizer gesetzt (%s, vorher: %s).",
             target, previous_label)
    result.update(switched=True, path=target, previous=previous_label)
    return result
