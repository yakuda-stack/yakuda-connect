#!/usr/bin/env python3
"""
core/xrbinder.py — Tastenbelegung fuer OpenXR-Spiele per xrBinder
=================================================================
OpenVR-Spiele (SteamVR-Bindings) bearbeitet der Controls-Tab mit obah.
Spiele, die OpenXR DIREKT benutzen (Unreal, viele Proton-Spiele), haben keine
Binding-Datei. Dort hilft xrBinder (https://gitlab.com/mittorn/xrBinder, MIT):
ein implizites OpenXR-API-Layer, das die Aktionen eines Spiels auf andere
Tasten umlegen kann.

Dieses Modul ist die Logik ohne Oberflaeche:

  * Bauen:     xrBinder aus dem Quellcode (git + cmake) nach
               ~/.config/yakuda-connect/tools/xrbinder/ — im sichtbaren
               Terminal, wie bei den Cargo-Tools.
  * Aktivieren: Manifest nach ~/.local/share/openxr/1/api_layers/implicit.d/
               (dann laedt der OpenXR-Loader das Layer in jedes Spiel), dazu
               die Grundkonfiguration ~/.config/xrBinder/xrBinder.ini und der
               IPC-Dienst (ipc_server) als systemd-User-Dienst.
  * Belegen:   je Spiel ~/.config/xrBinder/app_<Name>.ini, erzeugt aus einer
               einfachen Liste "Aktion + Hand -> Taste".

Wie xrBinder umlegt
-------------------
Das Layer legt ein eigenes Action-Set mit "Quellen" an (je eine OpenXR-Aktion
pro Taste, z. B. x_click) und haengt deren Bindings an die Vorschlaege des
Spiels an. Liest das Spiel eine umgelegte Aktion, bekommt es den Zustand der
Quelle statt des Originals. Die Originaltaste behaelt also ihre eigene
Funktion — soll sie nichts mehr tun, bekommt ihre Aktion "Aus".

Die Quellen erzeugen wir SELBST aus einer Tabelle der Kern-Profile der
OpenXR-Spezifikation (PROFILES), statt die mitgelieferten Vorlagen
zusammenzukippen. Grund: Ein einziger Pfad, den die Runtime fuer ein Profil
nicht kennt, laesst xrSuggestInteractionProfileBindings fuer das GANZE
Profil scheitern — und das Layer verschweigt den Fehler. Das Spiel haette
dann gar keine Tasten mehr.

Bekannte Grenzen von xrBinder (nachgestellt mit Monado + Testspiel)
------------------------------------------------------------------
  1. Leerer [bindings.*]-Abschnitt = Abschnitt existiert nicht. Ohne
     startupProfile stuerzt das Spiel bei "resetAction" ab. Deshalb steht in
     jedem Profil mindestens die Platzhalter-Zeile PLACEHOLDER_ACTION.
  2. Eine Umbelegung live ENTFERNEN (reloadConfig ohne sie) laesst das Spiel
     abstuerzen: Die Aktion zeigt weiter auf eine geleerte Quellenliste.
     Deshalb prueft die IPC-Seite vorher, welche Aktionen gerade umgelegt
     sind, und laedt nur neu, wenn keine davon wegfaellt (siehe
     xrbinder_ipc.py). Sonst gilt die Aenderung ab dem naechsten Spielstart.
  3. Achsen-Ausdruecke (axis1 = ...) haben dasselbe Problem schon beim
     Aendern. Wir benutzen ausschliesslich direkte Zuordnungen (map = ...);
     "Aus" ist eine Quelle ohne Bindings.
  4. Mit gesetztem XDG_CONFIG_HOME liest xrBinder nur die App-Datei (Bug in
     LoadConfig). Unsere App-Dateien sind deshalb vollstaendig: Wurzelwerte,
     Quellen und Profil stehen in jeder Datei.
  5. reloadConfig sucht die App-Datei unter dem auf 12 Zeichen gekuerzten
     Namen. Bei laengeren Namen schreiben wir beide Dateien.
  6. Unreal (und andere) legen Aktionen MIT Haenden an, fragen sie aber OHNE
     Hand ab (subactionPath = XR_NULL_PATH). Dieses Fach aktualisiert xrBinder
     nur bei Aktionen ganz ohne Haende — die Umbelegung kam im Spiel nie an.
     Beim Bauen patchen wir deshalb eine Zeile (build_script) und schreiben je
     Umbelegung zusaetzlich "aktion.any" (render_config). Nachgestellt mit
     Monado + Testspiel, das beide Abfragearten benutzt.
"""
import errno
import os
import shlex
import shutil
import socket
import subprocess
import time
from collections import OrderedDict

from appimage_installer import TOOLS_DIR
from logging_setup import get_logger

log = get_logger("xrbinder")

GIT_URL = "https://gitlab.com/mittorn/xrBinder.git"
LAYER_NAME = "XR_APILAYER_NOVENDOR_xr_binder"
DEFAULT_PORT = 9011
PROFILE = "yakuda"
PLACEHOLDER_ACTION = "__yakuda_placeholder"
MANAGED_MARK = "# yakuda-connect: managed"
SERVICE_NAME = "yakuda-xrbinder-ipc.service"
MANIFEST_NAME = "yakuda-xrbinder.json"
DISPLAY_NAME_MAX = 12       # EventHeader.displayName[13] im Layer
# Endung fuer das "ohne Hand"-Fach: jede unbekannte Endung ergibt in xrBinder
# USER_INVALID (PathIndexFromSuffix in config_shared.h).
ANY_HAND = "any"

TYPES = ("bool", "float", "vector2")
_ACTION_TYPE_KEYS = {"bool": "action_bool", "float": "action_float", "vector2": "action_vector2"}
# XrActionType -> unser Typname (Pose/Vibration koennen nicht umgelegt werden)
XR_ACTION_TYPES = {1: "bool", 2: "float", 3: "vector2"}
OFF_SOURCE = {t: f"yc_off_{t}" for t in TYPES}


# --------------------------------------------------------------------------- #
#  Pfade
# --------------------------------------------------------------------------- #
def _home():
    return os.path.expanduser("~")


def _xdg(var, default_rel):
    base = os.environ.get(var, "").strip()
    return base if base and os.path.isabs(base) else os.path.join(_home(), default_rel)


def tool_root():
    return os.path.join(TOOLS_DIR, "xrbinder")


def src_dir():
    return os.path.join(tool_root(), "src")


def build_dir():
    return os.path.join(tool_root(), "build")


def out_dir():
    return os.path.join(build_dir(), LAYER_NAME)


def library_path():
    return os.path.join(out_dir(), "libxrBinder_module.so")


def ipc_server_path():
    return os.path.join(out_dir(), "ipc_server")


def log_path():
    return os.path.join(tool_root(), "install.log")


def implicit_dir():
    return os.path.join(_xdg("XDG_DATA_HOME", ".local/share"), "openxr/1/api_layers/implicit.d")


def manifest_path():
    return os.path.join(implicit_dir(), MANIFEST_NAME)


def config_dir():
    """Genau der Ordner, den xrBinder liest (config_shared.h, LoadConfig)."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return os.path.join(xdg, "xrBinder") if xdg else os.path.join(_home(), ".config", "xrBinder")


def base_config_path():
    return os.path.join(config_dir(), "xrBinder.ini")


def app_config_path(app_name):
    base = os.path.realpath(config_dir())
    path = os.path.join(config_dir(), f"app_{app_name}.ini")
    if not os.path.realpath(path).startswith(base + os.sep):
        raise ValueError(f"invalid app name: {app_name!r}")
    return path


def state_dir():
    import paths
    return os.path.join(paths.config_root(), "xrbinder")


def state_path(app_name):
    return os.path.join(state_dir(), f"{safe_file_part(app_name)}.json")


def safe_file_part(name):
    """Name als Dateiname — nur fuer UNSERE json, nicht fuer xrBinder."""
    return "".join(c if c.isalnum() or c in "-_ ." else "_" for c in name).strip() or "_"


def valid_app_name(name):
    """
    xrBinder baut den Dateinamen ungefiltert: app_<name>.ini. Namen mit '/'
    kommen wirklich vor — xrizer meldet Unreal-Spiele als Pfad
    ("GalGun2/Binaries/Win64/GalGun2-Win64-Shipping") — und ergeben dann
    Unterordner. Das ist in Ordnung, solange nichts aus dem Ordner fuehrt.
    """
    if not name or "\0" in name or name.startswith("/"):
        return False
    return all(part not in ("", ".", "..") for part in name.split("/"))


def display_app_name(name):
    """Fuer die Oberflaeche: nur der letzte Teil eines Pfad-Namens."""
    return (name or "").rstrip("/").rsplit("/", 1)[-1] or name


APPREG_NAME_MAX = 31        # AppReg.name[32] — laengere Namen kommen gekuerzt an


def _xrizer_style_names(cmdline):
    """Namen, wie xrizer sie aus argv[0] bildet (Teil nach dem letzten '\\',
    ohne .exe), plus alle Argumente — fuer die Suche nach dem vollen Namen."""
    out = []
    for tok in cmdline:
        cands = [tok]
        if "\\" in tok:
            cands.insert(0, tok.rsplit("\\", 1)[1])
        for c in cands:
            out.append(c[:-4] if c.lower().endswith(".exe") else c)
    return out


def _proc_cmdline(pid):
    try:
        with open(f"/proc/{int(pid)}/cmdline", "rb") as fh:
            raw = fh.read()
    except (OSError, ValueError):
        return []
    return [t.decode("utf-8", "replace") for t in raw.split(b"\0") if t]


def expand_app_name(name, pid=0):
    """
    Vollen Namen zu einem gekuerzten (31 Zeichen) finden: erst die
    Befehlszeile des Spiels (pid), sonst alle Prozesse. Der Layer laedt
    app_<voller Name>.ini — mit dem gekuerzten wuerde die Belegung beim
    naechsten Start nicht greifen. Nichts gefunden: Name unveraendert.
    """
    if not name or len(name) < APPREG_NAME_MAX:
        return name
    pids = [pid] if pid else []
    try:
        pids += [int(p) for p in os.listdir("/proc") if p.isdigit() and int(p) != pid]
    except OSError:
        pass
    for p in pids:
        for cand in _xrizer_style_names(_proc_cmdline(p)):
            if cand.startswith(name) and len(cand) > len(name) and valid_app_name(cand):
                return cand
    return name


def valid_action_name(name):
    """Der Schluessel 'aktion.hand' wird am ERSTEN Punkt getrennt; '#'/';' sind Kommentare."""
    return bool(name) and not any(c in name for c in ".#;=[] \t\n")


# --------------------------------------------------------------------------- #
#  Status
# --------------------------------------------------------------------------- #
def is_built():
    return os.path.isfile(library_path()) and os.access(ipc_server_path(), os.X_OK)


# Stand unserer kleinen Korrektur am xrBinder-Quellcode (siehe build_script).
# Erhoehen, wenn sich der Patch aendert — dann meldet die UI "neu bauen".
PATCH_LEVEL = "4"
PATCH_FILE = ".yakuda-patch"
PATCH3_NAME = "yakuda-patch3.pl"
PATCH3_REPORT = ".yakuda-patch3"
DEBUG_LOG_NAME = "yakuda-debug.log"
DEBUG_LOG_MAX = 2 * 1024 * 1024


def needs_rebuild():
    """Gebaut, aber ohne (aktuellen) Patch — z. B. von einer frueheren Version."""
    if not is_built():
        return False
    try:
        with open(os.path.join(tool_root(), PATCH_FILE), encoding="utf-8") as fh:
            return fh.read().strip() != PATCH_LEVEL
    except OSError:
        return True


def debug_log_path():
    """Diagnose-Log des gepatchten Layers (Patch 3) — liegt neben der Config."""
    return os.path.join(config_dir(), DEBUG_LOG_NAME)


def rotate_debug_log():
    """Zu grosses Log nach .old verschieben (das Layer haengt nur an)."""
    path = debug_log_path()
    try:
        if os.path.getsize(path) > DEBUG_LOG_MAX:
            os.replace(path, path + ".old")
            return True
    except OSError:
        pass
    return False


def patch3_report():
    """Ergebnis von Patch 3 beim letzten Bau: {teil: "ok"|"skip"|"miss"|"off"}."""
    out = {}
    try:
        with open(os.path.join(tool_root(), PATCH3_REPORT), encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) == 2:
                    out[parts[1]] = parts[0]
    except OSError:
        pass
    return out


def installed_revision():
    try:
        res = subprocess.run(["git", "-C", src_dir(), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        return res.stdout.strip() if res.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def layer_enabled():
    import json
    try:
        with open(manifest_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("api_layer", {}).get("library_path") == library_path()
    except (OSError, ValueError, AttributeError):
        return False


def _manifest_dirs():
    """Alle Orte, an denen der Loader implizite Layer sucht (Linux)."""
    dirs = [implicit_dir()]
    cfg = os.environ.get("XDG_CONFIG_DIRS") or "/etc/xdg"
    data = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    xdg_cfg = _xdg("XDG_CONFIG_HOME", ".config")
    for base in [xdg_cfg] + cfg.split(":") + ["/etc"] + data.split(":"):
        if base:
            d = os.path.join(base, "openxr/1/api_layers/implicit.d")
            if d not in dirs:
                dirs.append(d)
    return dirs


def foreign_manifests():
    """Andere Manifeste fuer xrBinder (z. B. von Hand kopiert). Laedt der
    Loader beide, liefe das Layer doppelt — das melden wir."""
    import json
    found = []
    own = os.path.realpath(manifest_path())
    for d in _manifest_dirs():
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for name in names:
            path = os.path.join(d, name)
            if not name.endswith(".json") or os.path.realpath(path) == own:
                continue
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError):
                continue
            if isinstance(data, dict) and data.get("api_layer", {}).get("name") == LAYER_NAME:
                found.append(path)
    return found


MANUAL_COPY_FILES = ("libxrBinder_module.so", "ipc_server", "client_gui", "client_simple")


def cleanup_manual_copy(manifest):
    """Eine von Hand kopierte xrBinder-Installation (Manifest + .so + Programme
    im selben Ordner) in einen Sicherungsordner verschieben. Nur im
    Benutzerordner — Systemdateien fassen wir nicht an. Gibt den Zielordner
    zurueck oder '' wenn nichts verschoben wurde."""
    folder = os.path.dirname(os.path.realpath(manifest))
    if not folder.startswith(_home() + os.sep):
        return ""
    target = os.path.join(state_dir(), "manual-copy-" + time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(target, exist_ok=True)
    moved = []
    for name in (os.path.basename(manifest),) + MANUAL_COPY_FILES:
        src = os.path.join(folder, name)
        if os.path.lexists(src):
            shutil.move(src, os.path.join(target, name))
            moved.append(name)
    log.info("Handkopie von xrBinder verschoben nach %s: %s", target, moved)
    return target if moved else ""


# --------------------------------------------------------------------------- #
#  Quellen (Tasten) aus den Kern-Profilen der OpenXR-Spezifikation
# --------------------------------------------------------------------------- #
# Profil -> {Hand: [Komponenten unter /user/hand/<hand>/input/]}
_BOTH = "both"
PROFILES = OrderedDict([
    ("/interaction_profiles/khr/simple_controller", {
        _BOTH: ["select/click", "menu/click"]}),
    ("/interaction_profiles/oculus/touch_controller", {
        "left": ["x/click", "x/touch", "y/click", "y/touch", "menu/click"],
        "right": ["a/click", "a/touch", "b/click", "b/touch", "system/click"],
        _BOTH: ["squeeze/value", "trigger/value", "trigger/touch", "thumbstick",
                "thumbstick/x", "thumbstick/y", "thumbstick/click", "thumbstick/touch",
                "thumbrest/touch"]}),
    ("/interaction_profiles/valve/index_controller", {
        _BOTH: ["system/click", "system/touch", "a/click", "a/touch", "b/click", "b/touch",
                "squeeze/value", "squeeze/force", "trigger/click", "trigger/value",
                "trigger/touch", "thumbstick", "thumbstick/x", "thumbstick/y",
                "thumbstick/click", "thumbstick/touch", "trackpad", "trackpad/x",
                "trackpad/y", "trackpad/force", "trackpad/touch"]}),
    ("/interaction_profiles/htc/vive_controller", {
        _BOTH: ["system/click", "squeeze/click", "menu/click", "trigger/click",
                "trigger/value", "trackpad", "trackpad/x", "trackpad/y", "trackpad/click",
                "trackpad/touch"]}),
    ("/interaction_profiles/microsoft/motion_controller", {
        _BOTH: ["menu/click", "squeeze/click", "trigger/value", "thumbstick", "thumbstick/x",
                "thumbstick/y", "thumbstick/click", "trackpad", "trackpad/x", "trackpad/y",
                "trackpad/click", "trackpad/touch"]}),
])

def _component_types(component):
    """[(Quellname, Typ)] fuer eine Komponente. Zusaetzliche Varianten nur, wo
    sie Sinn ergeben: Knopf auch als Wert (0/1) fuer Float-Aktionen, Trigger/
    Griff auch als Knopf (Schwelle der Runtime) fuer Bool-Aktionen."""
    if "/" not in component:                       # thumbstick, trackpad
        return [(component, "vector2")]
    base, kind = component.split("/", 1)
    name = f"{base}_{kind}"
    if kind == "click":
        return [(name, "bool"), (name + "_f", "float")]
    if kind == "touch":
        return [(name, "bool")]
    if kind in ("value", "force"):
        return [(name, "float"), (name + "_b", "bool")]
    if kind in ("x", "y"):
        return [(name, "float")]
    return []


def build_sources():
    """OrderedDict Quellname -> {"type": ..., "bindings": ["profil:pfad", ...]}"""
    sources = OrderedDict()
    for profile, hands in PROFILES.items():
        for hand, components in hands.items():
            for comp in components:
                for name, typ in _component_types(comp):
                    entry = sources.setdefault(name, {"type": typ, "bindings": []})
                    for h in (("left", "right") if hand == _BOTH else (hand,)):
                        b = f"{profile}:/user/hand/{h}/input/{comp}"
                        if b not in entry["bindings"]:
                            entry["bindings"].append(b)
    for typ in TYPES:
        sources[OFF_SOURCE[typ]] = {"type": typ, "bindings": []}
    return sources


# --------------------------------------------------------------------------- #
#  Konfiguration schreiben
# --------------------------------------------------------------------------- #
def _root_block(port):
    return [f"serverPort = {int(port)}", "ipcMode = bus", f"startupProfile = {PROFILE}"]


def _sources_block(sources):
    lines = []
    for name, src in sources.items():
        lines.append(f"[source.{name}]")
        lines.append(f"actionType = {_ACTION_TYPE_KEYS[src['type']]}")
        if src["bindings"]:
            lines.append("bindings = " + ",".join(src["bindings"]))
    return lines


def mapping_key(action, hand):
    return f"{action}.{hand}" if hand else action


# „Kippen = Druecken“: Stick-Klick zaehlt auch, wenn der Stick nur gekippt
# wird (wie die Community-Bindings „dpad im Touch-Modus“ unter SteamVR).
TILT_SOURCE = "thumbstick_click"
TILT_THRESHOLD = 0.5
TILT_MIN, TILT_MAX = 0.2, 0.95      # Regler im Tasten-Dialog (gegen Stick-Drift)


def clamp_threshold(value):
    """Schwelle aus der Datei/UI in den erlaubten Bereich bringen."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return TILT_THRESHOLD
    if v != v:                                  # NaN
        return TILT_THRESHOLD
    return round(min(TILT_MAX, max(TILT_MIN, v)), 2)


def tilt_expression(source, hand, threshold=TILT_THRESHOLD):
    """Achs-Ausdruck fuer xrBinder (axis1) oder None.

    Ergebnis ist genau 0 oder 1: gedrueckt ODER Stick weiter als die Schwelle
    gekippt (Abstand von der Mitte, also auch schraeg). Absichtlich nur step,
    sqrt, + und * — in xrBinder sind max() und min() vertauscht (max liefert
    das Minimum), darauf soll sich nichts verlassen.
    """
    if source != TILT_SOURCE or hand not in ("left", "right"):
        return None
    x, y = f"thumbstick_x.{hand}", f"thumbstick_y.{hand}"
    t = clamp_threshold(threshold)
    return (f"step(0.5, {source}.{hand} + "
            f"step({t:g}, sqrt({x} * {x} + {y} * {y})))")


# Deadzone fuer Sticks (gegen Drift): kleiner Ausschlag -> Spiel bekommt 0.
DEADZONE_SOURCE = "thumbstick"
DEADZONE_DEFAULT = 0.15
DEADZONE_MIN, DEADZONE_MAX = 0.05, 0.5


def clamp_deadzone(value):
    """Deadzone aus Datei/UI in den erlaubten Bereich bringen."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return DEADZONE_DEFAULT
    if v != v:                                  # NaN
        return DEADZONE_DEFAULT
    return round(min(DEADZONE_MAX, max(DEADZONE_MIN, v)), 2)


def deadzone_expressions(source, hand, deadzone=DEADZONE_DEFAULT):
    """(axis1, axis2) fuer xrBinder oder None.

    Radiale Deadzone: Liegt der Stick naeher an der Mitte als die Schwelle,
    bekommt das Spiel x = y = 0, sonst die unveraenderten Werte. Wie beim
    Kippen nur step, sqrt, + und * (max/min sind in xrBinder vertauscht,
    Division ist nicht belegt).
    """
    if source != DEADZONE_SOURCE or hand not in ("left", "right"):
        return None
    x, y = f"thumbstick_x.{hand}", f"thumbstick_y.{hand}"
    d = clamp_deadzone(deadzone)
    gate = f"step({d:g}, sqrt({x} * {x} + {y} * {y}))"
    return f"{x} * {gate}", f"{y} * {gate}"


_AXIS_KEYS = ("tilt", "tilt_threshold", "deadzone")


def axis_changed(old, new):
    """Aendern sich Achs-Ausdruecke (Kippen/Deadzone) zwischen zwei Listen?"""
    def axes(lst):
        out = {}
        for m in lst or []:
            vals = tuple(m.get(k) for k in _AXIS_KEYS)
            if any(v is not None for v in vals):
                out[(m.get("action"), m.get("hand", ""))] = vals
        return out
    return axes(old) != axes(new)


def render_config(mappings, port=DEFAULT_PORT, app_name=""):
    """
    Vollstaendige xrBinder-INI. mappings: Liste von Dicts
        {"action": "menu", "hand": "left"|"right"|"", "source": "x_click", "source_hand": "left"|"",
         "tilt": True (optional, nur thumbstick_click: Kippen = Druecken),
         "tilt_threshold": 0.5 (optional, ab welchem Ausschlag Kippen zaehlt),
         "deadzone": 0.15 (optional, nur thumbstick: Deadzone gegen Drift)}
    Wurzelwerte MUESSEN vor dem ersten Abschnitt stehen, sonst landen sie im
    vorherigen Abschnitt (INI-Parser von xrBinder).
    """
    sources = build_sources()
    head = [MANAGED_MARK,
            "# Automatisch erzeugt — Aenderungen in yakuda-connect (Controls-Tab) machen.",
            "# Generated automatically — edit in yakuda-connect (Controls tab)."]
    if app_name:
        head.append(f"# Spiel / game: {app_name}")
    lines = head + _root_block(port)
    lines.append(f"[bindings.{PROFILE}]")
    lines.append(f"{PLACEHOLDER_ACTION} = yc_placeholder")
    body = []
    per_action = OrderedDict()          # Aktion -> [(Hand, Abschnitt, Quelle)]
    for i, m in enumerate(mappings, 1):
        src = m["source"]
        if src not in sources or not valid_action_name(m["action"]):
            log.warning("Umbelegung uebersprungen: %s", m)
            continue
        section = f"yc_{i}"
        hand = m.get("hand", "")
        lines.append(f"{mapping_key(m['action'], hand)} = {section}")
        target = f"{src}.{m['source_hand']}" if m.get("source_hand") else src
        body += [f"[actionmap.{section}]", f"map = {target}"]
        expr = (tilt_expression(src, m.get("source_hand", ""),
                                m.get("tilt_threshold", TILT_THRESHOLD))
                if m.get("tilt") else None)
        if expr:
            body.append(f"axis1 = {expr}")
        dz = (deadzone_expressions(src, m.get("source_hand", ""), m["deadzone"])
              if m.get("deadzone") is not None else None)
        if dz:
            body += [f"axis1 = {dz[0]}", f"axis2 = {dz[1]}"]
        per_action.setdefault(m["action"], []).append((hand, section, src))
    # Viele Spiele (Unreal!) legen Aktionen MIT Haenden an, fragen den Zustand
    # aber OHNE Hand ab (subactionPath = XR_NULL_PATH). Das landet bei xrBinder
    # in einem eigenen Fach, das die Zeilen "aktion.left/right" nicht treffen.
    # Deshalb zusaetzlich "aktion.any" (unbekannte Endung = dieses Fach).
    for action, entries in per_action.items():
        if any(h == "" for h, _s, _src in entries):
            continue                    # Schluessel ohne Hand gilt schon fuer alle
        chosen = next((e for e in entries if e[2] not in OFF_SOURCE.values()), entries[0])
        lines.append(f"{action}.{ANY_HAND} = {chosen[1]}")
    lines += ["[actionmap.yc_placeholder]", f"map = {OFF_SOURCE['bool']}"]
    lines += body
    lines += _sources_block(sources)
    return "\n".join(lines) + "\n"


def _write_text_atomic(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _is_managed(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.readline().strip() == MANAGED_MARK
    except OSError:
        return False


def _backup_foreign(path):
    """Eine fremde (von Hand angelegte) Datei einmal sichern, bevor wir sie
    ersetzen. Gibt den Sicherungspfad zurueck oder ''."""
    if os.path.exists(path) and not _is_managed(path):
        backup = path + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, backup)
        log.info("Eigene xrBinder-Datei gesichert: %s", backup)
        return backup
    return ""


def write_base_config(port=DEFAULT_PORT):
    path = base_config_path()
    backup = _backup_foreign(path)
    _write_text_atomic(path, render_config([], port))
    return backup


def app_config_names(app_name):
    """Dateinamen fuer ein Spiel: voller Name und — falls laenger als 12
    Zeichen — zusaetzlich der gekuerzte, den reloadConfig benutzt."""
    names = [app_name]
    if len(app_name) > DISPLAY_NAME_MAX:
        names.append(app_name[:DISPLAY_NAME_MAX])
    return names


def write_app_config(app_name, mappings, port=DEFAULT_PORT):
    if not valid_app_name(app_name):
        raise ValueError(f"invalid app name: {app_name!r}")
    text = render_config(mappings, port, app_name)
    written = []
    for name in app_config_names(app_name):
        path = app_config_path(name)
        _backup_foreign(path)
        _write_text_atomic(path, text)
        written.append(path)
    return written


BAD_HAND_PATH = "/user/hand/both/"


def _has_bad_paths(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return BAD_HAND_PATH in fh.read()
    except OSError:
        return False


def _fix_both_line(line):
    """'bindings = p:/user/hand/both/input/x,...' -> je Eintrag links + rechts."""
    if not line.startswith("bindings =") or BAD_HAND_PATH not in line:
        return line
    key, _sep, value = line.partition("=")
    out = []
    for item in value.strip().split(","):
        if BAD_HAND_PATH in item:
            for hand in ("left", "right"):
                fixed = item.replace(BAD_HAND_PATH, f"/user/hand/{hand}/")
                if fixed not in out:
                    out.append(fixed)
        elif item not in out:
            out.append(item)
    return f"{key.rstrip()} = " + ",".join(out)


def repair_file(path):
    """Nur die kaputten Pfade in UNSERER Datei ersetzen — Umbelegungen und
    alles andere bleiben Zeichen fuer Zeichen erhalten. True = geaendert."""
    if not (_is_managed(path) and _has_bad_paths(path)):
        return False
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    _write_text_atomic(path, "\n".join(_fix_both_line(ln) for ln in lines))
    return True


def repair_configs(port=DEFAULT_PORT):
    """
    Dateien aus 1.3.3-Testbuilds reparieren: dort standen Tasten fuer beide
    Haende als /user/hand/both/... (ungueltig -> Runtime lehnt alle
    Layer-Tasten ab). Geht alle unsere INI-Dateien im xrBinder-Ordner durch
    (auch Unterordner). Rueckgabe: Liste der reparierten Dateien.
    """
    fixed = []
    for root, _dirs, files in os.walk(config_dir()):
        for name in files:
            if name.endswith(".ini"):
                path = os.path.join(root, name)
                try:
                    if repair_file(path):
                        fixed.append(path)
                except OSError as exc:
                    log.warning("Reparatur fehlgeschlagen (%s): %s", path, exc)
    if fixed:
        log.info("xrBinder-Dateien repariert (both-Pfade): %s", fixed)
    return fixed


def write_manifest():
    import json
    data = {
        "file_format_version": "1.0.0",
        "api_layer": {
            "name": LAYER_NAME,
            "disable_environment": LAYER_NAME + "_DISABLE",
            "api_version": "1.0",
            "implementation_version": "1",
            "description": "xrBinder (managed by yakuda-connect)",
            "library_path": library_path(),
        },
    }
    _write_text_atomic(manifest_path(), json.dumps(data, indent=2) + "\n")


def remove_manifest():
    try:
        os.remove(manifest_path())
        return True
    except FileNotFoundError:
        return False


# --------------------------------------------------------------------------- #
#  Gemerkter Stand je Spiel (Aktionen aus dem letzten Abruf + Umbelegungen)
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
#  Bekannte Standardbelegung (wenn die Runtime nichts verraet)
# --------------------------------------------------------------------------- #
# Bei xrizer (OpenVR -> OpenXR) unter WiVRn meldet die Runtime fuer die
# Knoepfe keine gebundenen Quellen, obwohl sie im Spiel funktionieren. Die
# Legacy-Belegung von xrizer ist fest im Quellcode (src/input/profiles/*.rs,
# legacy_bindings) — die tragen wir dann selbst ein. Nur Anzeige: umgelegt
# wird ueber den Aktionsnamen, nicht ueber diese Pfade.
XRIZER_LEGACY_SET = "xrizer-legacy-set"
# Eigener Name! Frueher hiess das auch _BOTH und hat das "both" oben
# ueberschrieben -> build_sources schrieb /user/hand/both/... (ungueltig,
# die Runtime lehnte ALLE Layer-Bindings ab).
_LR = ("left", "right")
XRIZER_LEGACY = {
    "oculus_touch": {
        "trigger-click": [(h, "trigger/value") for h in _LR],
        "trigger": [(h, "trigger/value") for h in _LR],
        "squeeze": [(h, "squeeze/value") for h in _LR],
        "grip-click": [(h, "squeeze/value") for h in _LR],
        "app-menu": [("left", "y/click"), ("right", "b/click")],
        "a": [("left", "x/click"), ("right", "a/click")],
        "main-joystick": [(h, "thumbstick") for h in _LR],
        "main-joystick-click": [(h, "thumbstick/click") for h in _LR],
        "main-joystick-touch": [(h, "thumbstick/touch") for h in _LR],
    },
    "knuckles": {
        "trigger-click": [(h, "trigger/click") for h in _LR],
        "trigger": [(h, "trigger/value") for h in _LR],
        "squeeze": [(h, "squeeze/value") for h in _LR],
        "grip-click": [(h, "squeeze/value") for h in _LR],
        "app-menu": [(h, "b/click") for h in _LR],
        "a": [(h, "a/click") for h in _LR],
        "main-joystick": [(h, "thumbstick") for h in _LR],
        "main-joystick-click": [(h, "thumbstick/click") for h in _LR],
        "main-joystick-touch": [(h, "thumbstick/touch") for h in _LR],
    },
    "vive_controller": {
        "trigger-click": [(h, "trigger/click") for h in _LR],
        "trigger": [(h, "trigger/value") for h in _LR],
        "squeeze": [(h, "squeeze/click") for h in _LR],
        "grip-click": [(h, "squeeze/click") for h in _LR],
        "app-menu": [(h, "menu/click") for h in _LR],
        "main-joystick": [(h, "trackpad") for h in _LR],
        "main-joystick-click": [(h, "trackpad/click") for h in _LR],
        "main-joystick-touch": [(h, "trackpad/touch") for h in _LR],
    },
}


def fill_known_bindings(data, controller="oculus_touch"):
    """
    Dump ohne jede Tastenzuordnung, aber mit xrizers Legacy-Aktionen: die
    bekannte Standardbelegung eintragen. Rueckgabe: True, wenn ergaenzt.
    Liefert die Runtime echte Zuordnungen, bleibt alles unberuehrt.
    """
    if any(data.get("bindings", {}).values()):
        return False
    names = {a["name"] for a in data.get("actions", []) if a.get("set") == XRIZER_LEGACY_SET}
    table = XRIZER_LEGACY.get(controller) or XRIZER_LEGACY["oculus_touch"]
    filled = {name: [f"/user/hand/{h}/input/{comp}" for h, comp in paths]
              for name, paths in table.items() if name in names}
    if not filled:
        return False
    data["bindings"] = filled
    data["bindings_guessed"] = True
    return True


def load_state(app_name):
    from jsonio import read_json
    data = read_json(state_path(app_name), default={})
    return data if isinstance(data, dict) else {}


def save_state(app_name, state):
    from jsonio import write_json_atomic
    state = dict(state)
    state["app"] = app_name
    return write_json_atomic(state_path(app_name), state)


def known_apps():
    """Namen aller Spiele, fuer die wir schon Aktionen kennen."""
    from jsonio import read_json
    names = []
    try:
        files = sorted(os.listdir(state_dir()))
    except OSError:
        return names
    for f in files:
        if f.endswith(".json"):
            data = read_json(os.path.join(state_dir(), f), default={})
            if isinstance(data, dict) and data.get("app") and data.get("actions"):
                names.append(data["app"])
    return names


# --------------------------------------------------------------------------- #
#  Beschriftungen
# --------------------------------------------------------------------------- #
_LABELS = {
    "de": {"left": "Links", "right": "Rechts", "x": "X", "y": "Y", "a": "A", "b": "B",
           "menu": "Menü", "system": "System", "select": "Auswahl", "trigger": "Trigger",
           "squeeze": "Griff", "thumbstick": "Stick", "trackpad": "Trackpad",
           "thumbrest": "Daumenablage",
           "click": "drücken", "touch": "berühren", "value": "Stärke", "force": "Druck",
           "ax": "X-Achse", "ay": "Y-Achse", "dir": "Richtung",
           "as_value": "(als Wert)", "as_button": "(als Knopf)"},
    "en": {"left": "Left", "right": "Right", "x": "X", "y": "Y", "a": "A", "b": "B",
           "menu": "Menu", "system": "System", "select": "Select", "trigger": "Trigger",
           "squeeze": "Grip", "thumbstick": "Stick", "trackpad": "Trackpad",
           "thumbrest": "Thumb rest",
           "click": "press", "touch": "touch", "value": "strength", "force": "force",
           "ax": "X axis", "ay": "Y axis", "dir": "direction",
           "as_value": "(as value)", "as_button": "(as button)"},
}


def hand_of_path(path):
    for h in ("left", "right"):
        if path.startswith(f"/user/hand/{h}/"):
            return h
    return ""


def path_label(path, lang="de"):
    """'/user/hand/left/input/x/click' -> 'Links · X · drücken'"""
    t = _LABELS.get(lang, _LABELS["en"])
    hand = hand_of_path(path)
    rest = path.split("/input/", 1)[1] if "/input/" in path else path
    parts = rest.split("/")
    comp = t.get(parts[0], parts[0])
    if len(parts) == 1:
        kind = t["dir"]
    else:
        k = parts[1]
        kind = t["ax"] if k == "x" else t["ay"] if k == "y" else t.get(k, k)
    return " · ".join(p for p in (t.get(hand, ""), comp, kind) if p)


def source_label(source_name, hand, lang="de"):
    """Beschriftung einer Quelle fuer eine Hand, z. B. 'Links · X · drücken (als Wert)'."""
    t = _LABELS.get(lang, _LABELS["en"])
    name = source_name
    suffix = ""
    if name.endswith("_f"):
        name, suffix = name[:-2], " " + t["as_value"]
    elif name.endswith("_b"):
        name, suffix = name[:-2], " " + t["as_button"]
    comp = name.replace("_", "/", 1)
    path = f"/user/hand/{hand}/input/{comp}" if hand else f"/input/{comp}"
    return path_label(path, lang) + suffix


# --------------------------------------------------------------------------- #
#  IPC-Dienst (ipc_server)
# --------------------------------------------------------------------------- #
def port_in_use(port=DEFAULT_PORT):
    """Ist der UDP-Port schon belegt (= ipc_server laeuft)?"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("127.0.0.1", int(port)))
        return False
    except OSError as exc:
        return exc.errno == errno.EADDRINUSE
    finally:
        s.close()


def service_unit_path():
    return os.path.join(_xdg("XDG_CONFIG_HOME", ".config"), "systemd", "user", SERVICE_NAME)


def service_unit_text(port=DEFAULT_PORT):
    return (
        "# Automatisch erzeugt von yakuda-connect\n"
        "[Unit]\n"
        "Description=xrBinder IPC bus (yakuda-connect)\n\n"
        "[Service]\n"
        f"ExecStart={shlex.quote(ipc_server_path())} {int(port)}\n"
        "Restart=on-failure\n"
        "RestartSec=2\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def _systemctl(*args, timeout=10):
    try:
        res = subprocess.run(["systemctl", "--user", *args],
                             capture_output=True, text=True, timeout=timeout)
        return res.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def ensure_service(port=DEFAULT_PORT):
    """
    Sorgt dafuer, dass ipc_server laeuft — und zwar schon BEVOR ein Spiel
    startet: Das Layer meldet sich nur beim Start beim Dienst an.
    Bevorzugt als systemd-User-Dienst (startet mit der Anmeldung), sonst als
    losgeloester Prozess. Rueckgabe: "running" | "systemd" | "process" | "".
    """
    if port_in_use(port):
        return "running"
    if not is_built():
        return ""
    if shutil.which("systemctl"):
        try:
            _write_text_atomic(service_unit_path(), service_unit_text(port))
            if _systemctl("daemon-reload") and _systemctl("enable", "--now", SERVICE_NAME):
                for _ in range(20):
                    if port_in_use(port):
                        return "systemd"
                    time.sleep(0.1)
        except OSError as exc:
            log.debug("systemd-Dienst nicht einrichtbar: %s", exc)
    try:
        logf = open(os.path.join(tool_root(), "ipc_server.log"), "ab")
        subprocess.Popen([ipc_server_path(), str(int(port))], stdout=logf, stderr=logf,
                         stdin=subprocess.DEVNULL, start_new_session=True)
        for _ in range(20):
            if port_in_use(port):
                return "process"
            time.sleep(0.1)
    except OSError as exc:
        log.warning("ipc_server nicht startbar: %s", exc)
    return ""


def stop_service():
    if os.path.exists(service_unit_path()):
        _systemctl("disable", "--now", SERVICE_NAME)
        try:
            os.remove(service_unit_path())
        except OSError:
            pass
        _systemctl("daemon-reload")
    # Ein von uns als Prozess gestarteter Dienst: gezielt ueber den Pfad beenden
    try:
        subprocess.run(["pkill", "-f", "^" + ipc_server_path()], timeout=5,
                       capture_output=True)
    except (OSError, subprocess.TimeoutExpired):
        pass


def enable(port=DEFAULT_PORT):
    """Layer aktivieren. Rueckgabe: (Dienst-Status, Sicherung der alten Grundkonfig)."""
    backup = write_base_config(port)
    write_manifest()
    return ensure_service(port), backup


def disable():
    remove_manifest()
    stop_service()


# --------------------------------------------------------------------------- #
#  Bauen (Skript fuers Terminal)
# --------------------------------------------------------------------------- #
SCRIPT_NAME = "install.sh"
STATUS_NAME = ".yakuda-status"
PID_NAME = ".yakuda-pid"

_TEXTS = {
    "de": {
        "title": "xrBinder bauen (OpenXR-Tastenbelegung)",
        "step_tools": "Werkzeuge: git, cmake, make, C++-Compiler",
        "step_src": "Quellcode von GitLab holen",
        "step_build": "Bauen (dauert etwa eine Minute)",
        "found": "gefunden",
        "missing": "fehlt — wird installiert (sudo-Passwort noetig)",
        "no_pm": "Unbekannte Distribution — bitte git, cmake, make und g++ von Hand installieren.",
        "err_tools": "Die Werkzeuge konnten nicht installiert werden.",
        "err_src": "Quellcode konnte nicht geladen werden (Internet?).",
        "err_build": "Bauen fehlgeschlagen (Fehlermeldung siehe oben).",
        "patch_warn": "Warnung: Patch passt nicht mehr (xrBinder geaendert) — Umbelegen klappt evtl. nicht bei allen Spielen.",
        "patch3_ok": "Patch 3: Sync-Korrektur + Diagnose-Log",
        "patch3_warn": "Hinweis: Patch 3 (Diagnose) passt nicht zu dieser xrBinder-Version — baue ohne ihn.",
        "failed": "Installation fehlgeschlagen",
        "logfile": "Komplettes Protokoll:",
        "enter": "Enter druecken zum Schliessen ... ",
        "done": "Fertig! xrBinder ist gebaut.",
        "closing": "Dieses Fenster schliesst sich gleich automatisch ...",
    },
    "en": {
        "title": "Building xrBinder (OpenXR button remapping)",
        "step_tools": "Tools: git, cmake, make, C++ compiler",
        "step_src": "Fetching source code from GitLab",
        "step_build": "Building (takes about a minute)",
        "found": "found",
        "missing": "missing — installing (sudo password required)",
        "no_pm": "Unknown distribution — please install git, cmake, make and g++ manually.",
        "err_tools": "Could not install the build tools.",
        "err_src": "Could not fetch the source code (internet?).",
        "err_build": "Build failed (see error above).",
        "patch_warn": "Warning: patch no longer applies (xrBinder changed) — remapping may not work in every game.",
        "patch3_ok": "Patch 3: sync fix + diagnostic log",
        "patch3_warn": "Note: patch 3 (diagnostics) does not fit this xrBinder version — building without it.",
        "failed": "Installation failed",
        "logfile": "Full log:",
        "enter": "Press Enter to close ... ",
        "done": "Done! xrBinder is built.",
        "closing": "This window will close automatically ...",
    },
}


# Patch 3 (Perl, laeuft auf src/layer_shims.cpp) — siehe Kopf des Skripts.
PATCH3_PERL = r'''#!/usr/bin/env perl
# yakuda-connect Patch 3 fuer xrBinder (src/layer_shims.cpp)
#  a) xrSyncActions: memcpy kopiert "count + sizeof" statt "count * sizeof"
#     Bytes -> ab dem 2. Action-Set des Spiels Datenmuell (xrizer: 2 Sets).
#  b) Vector2-Quellen: Typ wurde im Float-Feld gesetzt.
#  c) Scheitert der zusammengefuehrte Suggest, Spiel-Belegung allein nochmal
#     vorschlagen (sonst hat das Spiel fuer das Profil gar keine Tasten).
#  d) Diagnose-Log: xrBinder/yakuda-debug.log (Suggest/Attach/Sync-Ergebnis,
#     Zustandswechsel der Layer-Knoepfe).
# Ausgabe je Teil: "ok <name>" / "skip <name>" (schon behoben) / "miss <name>".
use strict;
use warnings;

my $fixes_only = (@ARGV && $ARGV[0] eq '--fixes-only') ? shift : 0;
my $file = shift or die "usage: $0 [--fixes-only] layer_shims.cpp\n";
open(my $in, '<', $file) or die "$file: $!\n";
local $/;
my $s = <$in>;
close $in;

if ($s =~ /yc_log\(/) { print "skip all (already patched)\n"; exit 0; }

my @report;
sub mark { my ($name, $n, $already) = @_;
    push @report, ($n ? "ok" : ($already ? "skip" : "miss")) . " $name"; }

# a) Sync-Kopie
my $n = ($s =~ s/(countActiveActionSets)\s*\+\s*(sizeof\s*\(\s*XrActiveActionSet\s*\))/$1 * $2/g);
mark("syncfix", $n, $s =~ /countActiveActionSets\s*\*\s*sizeof\s*\(\s*XrActiveActionSet\s*\)/);

# b) Vector2-Typ
$n = ($s =~ s/mLayerActionsFloat(\[i\]\.typedState\[hand\]\.type\s*=\s*XR_TYPE_ACTION_STATE_VECTOR2F)/mLayerActionsVec2$1/g);
mark("vec2fix", $n, $s !~ /mLayerActionsFloat\[i\]\.typedState\[hand\]\.type\s*=\s*XR_TYPE_ACTION_STATE_VECTOR2F/);

if ($fixes_only) {
    open(my $out, '>', $file) or die "$file: $!\n";
    print $out $s;
    close $out;
    print "$_\n" for @report;
    print "off log\n";
    exit 0;
}

# d) Log-Helfer nach dem ersten #include
my $helper = <<'CPP';
// ---- yakuda-connect: Diagnose-Log ----
#include <stdio.h>
#include <stdarg.h>
#include <unistd.h>
#include <stdlib.h>
static int yc_log_lines = 0;
static void yc_log(const char *fmt, ...)
{
	static FILE *f = nullptr;
	if(yc_log_lines > 4000) return;
	if(!f)
	{
		char p[1024];
		const char *x = getenv("XDG_CONFIG_HOME");
		const char *h = getenv("HOME");
		if(x && *x) snprintf(p, sizeof(p), "%s/xrBinder/yakuda-debug.log", x);
		else snprintf(p, sizeof(p), "%s/.config/xrBinder/yakuda-debug.log", h ? h : "/tmp");
		f = fopen(p, "a");
		if(!f) { yc_log_lines = 1 << 30; return; }
		setvbuf(f, nullptr, _IOLBF, 0);
		fprintf(f, "=== yakuda xrBinder log, pid %d ===\n", (int)getpid());
	}
	va_list ap;
	va_start(ap, fmt);
	vfprintf(f, fmt, ap);
	va_end(ap);
	if(++yc_log_lines > 4000) fprintf(f, "(log limit reached)\n");
}
// ---- /yakuda-connect ----
CPP
$n = ($s =~ s/^(#include\s*"layer_shims\.hpp"[^\n]*\n)/$1$helper/m);
if (!$n) { $n = ($s =~ s/^(#include[^\n]*\n)/$1$helper/m); }
mark("loghelper", $n, 0);
my $have_log = $n;

# c)+d) Suggest mit Layer-Bindings
my $sug_merged = <<'CPP';
{
			XrResult yc_r = nextLayer_xrSuggestInteractionProfileBindings(instance, &newSuggestedBindings);
			char yc_p[256] = "?"; uint32_t yc_len = 0;
			nextLayer_xrPathToString(instance, suggestedBindings->interactionProfile, sizeof(yc_p), &yc_len, yc_p);
			yc_log("suggest %s: game=%u layer=%u -> %d\n", yc_p, (unsigned)suggestedBindings->countSuggestedBindings,
				(unsigned)(newSuggestedBindings.countSuggestedBindings - suggestedBindings->countSuggestedBindings), (int)yc_r);
			if(yc_r != XR_SUCCESS)
			{
				for(uint32_t yc_i = suggestedBindings->countSuggestedBindings; yc_i < newSuggestedBindings.countSuggestedBindings; yc_i++)
				{
					char yc_b[256] = "?"; uint32_t yc_bl = 0;
					nextLayer_xrPathToString(instance, bindings[yc_i].binding, sizeof(yc_b), &yc_bl, yc_b);
					yc_log("  layer binding %s\n", yc_b);
				}
				XrResult yc_r2 = nextLayer_xrSuggestInteractionProfileBindings(instance, suggestedBindings);
				yc_log("  retry without layer bindings -> %d\n", (int)yc_r2);
			}
		}
CPP
chomp $sug_merged;
$n = $have_log && ($s =~ s/nextLayer_xrSuggestInteractionProfileBindings\(\s*instance\s*,\s*&newSuggestedBindings\s*\)\s*;/$sug_merged/);
mark("log-suggest", $n, 0);

my $sug_plain = <<'CPP';
{
			XrResult yc_r = nextLayer_xrSuggestInteractionProfileBindings(instance, suggestedBindings);
			char yc_p[256] = "?"; uint32_t yc_len = 0;
			nextLayer_xrPathToString(instance, suggestedBindings->interactionProfile, sizeof(yc_p), &yc_len, yc_p);
			yc_log("suggest %s: game=%u layer=0 -> %d\n", yc_p, (unsigned)suggestedBindings->countSuggestedBindings, (int)yc_r);
		}
CPP
chomp $sug_plain;
$n = $have_log && ($s =~ s/(\belse\s*\n?\s*)nextLayer_xrSuggestInteractionProfileBindings\(\s*instance\s*,\s*suggestedBindings\s*\)\s*;/$1$sug_plain/);
mark("log-suggest-plain", $n, 0);

# d) Attach
$n = $have_log && ($s =~ s/(XrResult\s+(\w+)\s*=\s*nextLayer_xrAttachSessionActionSets\(\s*session\s*,\s*&newInfo\s*\)\s*;)/$1\n\t\tyc_log("attach session=%llx sets=%u (incl. layer) -> %d\\n", (unsigned long long)session, (unsigned)newInfo.countActionSets, (int)$2);/);
mark("log-attach", $n, 0);

# d) Sync (nur erste Aufrufe und Wechsel des Ergebnisses)
$n = $have_log && ($s =~ s/(XrResult\s+(\w+)\s*=\s*nextLayer_xrSyncActions\(\s*session\s*,\s*&nsyncInfo\s*\)\s*;)/$1\n\t\t{ static int yc_sn = 0; static int yc_last = 1; if(yc_sn < 3 || (int)$2 != yc_last) yc_log("sync #%d sets=%u+layer -> %d\\n", yc_sn, (unsigned)syncInfo->countActiveActionSets, (int)$2); yc_last = (int)$2; yc_sn++; }/);
mark("log-sync", $n, 0);

# d) Zustandswechsel der Layer-Knoepfe (active/state je Hand)
my $bool_log = <<'CPP';
XrResult yc_g = $1;
				{
					static int yc_prev[512][2];
					XrActionStateBoolean &yc_s = mpActiveSession->mLayerActionsBoolean[i].typedState[hand];
					int yc_v = 1 + (yc_g != XR_SUCCESS ? 4 : 0) + (yc_s.isActive ? 2 : 0) + (yc_s.currentState ? 1 : 0);
					if(i < 512 && yc_prev[i][hand] != yc_v)
					{
						const char *yc_name = "?";
						for(int yc_k = 0; yc_k < (int)mLayerActionSet.mActions.count; yc_k++)
							if(mLayerActionSet.mActions[yc_k].action == mpActiveSession->mLayerActionsBoolean[i].action)
								yc_name = mLayerActionSet.mActions[yc_k].info.actionName;
						yc_log("source %s.%s: result=%d active=%d state=%d\n", yc_name, hand ? "right" : "left",
							(int)yc_g, (int)yc_s.isActive, (int)yc_s.currentState);
						yc_prev[i][hand] = yc_v;
					}
				}
CPP
chomp $bool_log;
$n = $have_log && ($s =~ s/(nextLayer_xrGetActionStateBoolean\(\s*session\s*,\s*&getInfo\s*,\s*&mpActiveSession->mLayerActionsBoolean\[i\]\.typedState\[hand\]\s*\))\s*;/my $x = $bool_log; my $c = $1; $x =~ s|\$1|$c|; $x . ";"/e);
# (das ";" landet hinter dem Block — harmlos)
mark("log-sources", $n, 0);

# Patch 4: Stick-/Achswerte (nur bei Aenderung, auf 0.25 gerundet)
my $axis_log = <<'CPP';
{
					static int yc_pf[512][2][2];
					auto &yc_st = mpActiveSession->__ARR__[i].typedState[hand];
					int yc_q0 = 9 + (int)lrintf(__X__ * 4.0f), yc_q1 = 9 + (int)lrintf(__Y__ * 4.0f) + (yc_st.isActive ? 100 : 0);
					if(i < 512 && (yc_pf[i][hand][0] != yc_q0 || yc_pf[i][hand][1] != yc_q1))
					{
						const char *yc_name = "?";
						for(int yc_k = 0; yc_k < (int)mLayerActionSet.mActions.count; yc_k++)
							if(mLayerActionSet.mActions[yc_k].action == mpActiveSession->__ARR__[i].action)
								yc_name = mLayerActionSet.mActions[yc_k].info.actionName;
						yc_log("source %s.%s: active=%d x=%.2f y=%.2f\n", yc_name, hand ? "right" : "left",
							(int)yc_st.isActive, (double)(__X__), (double)(__Y__));
						yc_pf[i][hand][0] = yc_q0; yc_pf[i][hand][1] = yc_q1;
					}
				}
CPP
chomp $axis_log;
for my $spec (["Float", "yc_st.currentState", "0.0f"], ["Vector2f", "yc_st.currentState.x", "yc_st.currentState.y"]) {
    my ($fn, $x, $y) = @$spec;
    my $arr = $fn eq "Float" ? "mLayerActionsFloat" : "mLayerActionsVec2";
    my $blk = $axis_log; $blk =~ s/__ARR__/$arr/g; $blk =~ s/__X__/$x/g; $blk =~ s/__Y__/$y/g;
    $n = $have_log && ($s =~ s/(nextLayer_xrGetActionState$fn\(\s*session\s*,\s*&getInfo\s*,\s*&mpActiveSession->$arr\[i\]\.typedState\[hand\]\s*\)\s*;)/$1\n\t\t\t\t$blk/);
    mark("log-axis-" . lc($fn), $n, 0);
}

# Patch 4: was das Spiel fuer umgelegte Sticks bekommt
my $app_vec = <<'CPP';
*state = a->typedState[handPath];
					{
						static const void *yc_ka[64]; static int yc_kv[64];
						int yc_slot = (int)((((unsigned long long)(size_t)a) >> 4) + handPath) & 63;
						int yc_v = 1 + (state->isActive ? 1000000 : 0) + (9 + (int)lrintf(state->currentState.x * 4.0f)) * 100 + (9 + (int)lrintf(state->currentState.y * 4.0f));
						if(yc_ka[yc_slot] != (const void *)a || yc_kv[yc_slot] != yc_v)
						{
							yc_log("game %s.%d: active=%d x=%.2f y=%.2f\n", a->info.actionName, handPath,
								(int)state->isActive, (double)state->currentState.x, (double)state->currentState.y);
							yc_ka[yc_slot] = a; yc_kv[yc_slot] = yc_v;
						}
					}
CPP
chomp $app_vec;
$n = $have_log && ($s =~ s/(ActionVec2\s*\*a\s*=\s*mpActiveSession->mActionsVec2\.GetPtr\(getInfo->action\);.*?)\*state\s*=\s*a->typedState\[handPath\];/$1$app_vec/s);
mark("log-game-vec2", $n, 0);

open(my $out, '>', $file) or die "$file: $!\n";
print $out $s;
close $out;
print "$_\n" for @report;
'''


def build_script(lang="de"):
    t = _TEXTS.get(lang, _TEXTS["en"])
    q = shlex.quote
    return f"""#!/usr/bin/env bash
# Automatisch erzeugt von yakuda-connect — baut xrBinder aus dem Quellcode.
# Kann jederzeit von Hand erneut gestartet werden:  bash {SCRIPT_NAME}

ROOT={q(tool_root())}
SRC={q(src_dir())}
BUILD={q(build_dir())}
LIB={q(library_path())}
URL={q(GIT_URL)}
LOG="$ROOT/install.log"
STATUS="$ROOT/{STATUS_NAME}"

mkdir -p "$ROOT" && cd "$ROOT" || exit 1
rm -f "$STATUS"
echo $$ > "$ROOT/{PID_NAME}"
trap 'rm -f "$ROOT/{PID_NAME}"' EXIT
exec > >(tee "$LOG") 2>&1

step() {{ echo; printf '\\033[1;36m=== %s ===\\033[0m\\n' "$1"; }}
ok()   {{ printf '\\033[1;32m✔\\033[0m %s\\n' "$1"; }}
fail() {{
    echo
    printf '\\033[1;31m✖ %s\\033[0m\\n' {q(t["failed"])}
    echo "  $1"
    echo
    echo {q(t["logfile"])} "$LOG"
    echo fail > "$STATUS"
    echo
    read -rp {q(t["enter"])} _
    exit 1
}}

OS_IDS=""
if [ -r /etc/os-release ]; then . /etc/os-release; OS_IDS="$ID $ID_LIKE"; fi
is_arch()   {{ [[ "$OS_IDS" == *arch* ]] || command -v pacman >/dev/null; }}
is_fedora() {{ [[ "$OS_IDS" == *fedora* || "$OS_IDS" == *rhel* ]] || command -v dnf >/dev/null; }}
is_debian() {{ [[ "$OS_IDS" == *debian* || "$OS_IDS" == *ubuntu* ]] || command -v apt-get >/dev/null; }}
is_suse()   {{ [[ "$OS_IDS" == *suse* ]] || command -v zypper >/dev/null; }}

printf '\\033[1m%s\\033[0m\\n' {q(t["title"])}
echo "→ $ROOT"

step {q("1/3  " + t["step_tools"])}
if command -v git >/dev/null && command -v cmake >/dev/null && command -v make >/dev/null && command -v c++ >/dev/null; then
    ok {q(t["found"])}
else
    echo {q(t["missing"])}
    if   is_arch;   then sudo pacman -S --needed --noconfirm git cmake make gcc
    elif is_fedora; then sudo dnf install -y git cmake make gcc-c++
    elif is_debian; then sudo apt-get update; sudo apt-get install -y git cmake make g++
    elif is_suse;   then sudo zypper install -y git cmake make gcc-c++
    else fail {q(t["no_pm"])}
    fi || fail {q(t["err_tools"])}
    command -v cmake >/dev/null && command -v c++ >/dev/null || fail {q(t["err_tools"])}
    ok "git cmake make c++"
fi

step {q("2/3  " + t["step_src"])}
if [ -d "$SRC/.git" ]; then
    git -C "$SRC" fetch --depth 1 origin HEAD && git -C "$SRC" reset --hard FETCH_HEAD || fail {q(t["err_src"])}
else
    rm -rf "$SRC"
    git clone --depth 1 "$URL" "$SRC" || fail {q(t["err_src"])}
fi
# Nur das OpenXR-SDK (Header) — imgui braucht man ohne GUI nicht.
git -C "$SRC" submodule update --init --depth 1 OpenXR-SDK \\
  || git -C "$SRC" submodule update --init OpenXR-SDK || fail {q(t["err_src"])}
ok "$(git -C "$SRC" log -1 --format='%h %cs %s')"

# yakuda-connect-Patch: Das Fach "ohne Hand" (subactionPath = XR_NULL_PATH)
# immer mitfuehren. Sonst kommt eine Umbelegung bei Spielen, die ihre Tasten
# ohne Hand abfragen (z. B. Unreal), nie an.
F="$SRC/src/layer_shims.cpp"
sed -i 's/^\\(\\s*\\)if(a.subactionMask == 0)$/\\1if(1) \\/\\/ yakuda-connect: Fach ohne Hand immer mitfuehren/; s/^\\(\\s*\\)a.subactionMask = 1U << USER_INVALID;$/\\1a.subactionMask |= 1U << USER_INVALID;/' "$F"
if grep -q 'a.subactionMask |= 1U << USER_INVALID;' "$F"; then
    PATCHED=1; ok "Patch: Abfrage ohne Hand"
else
    PATCHED=0; echo {q(t["patch_warn"])}
fi
# yakuda-connect-Patch 2: Achs-Umbelegungen (z. B. „Kippen = Druecken“) melden
# eine Aenderung nur, wenn sich der Wert wirklich aendert — sonst sieht das
# Spiel jedes Bild einen neuen Tastendruck.
perl -0pi -e 's/(\\n\\t\\tbool hasAxisMapping = false;)/$1 float yakudaLast[2] = {{0.0f, 0.0f}};/; s|// todo: detect change\\n(\\t+)state\\.changedSinceLastSync = true;\\n\\t+state\\.lastChangeTime = mPredictedTime;|// yakuda-connect: nur echte Aenderungen melden\\n$1float yx = a.Get(handPath, 0), yy = a.Get(handPath, 1);\\n$1state.changedSinceLastSync = (yx != hand.yakudaLast[0] \\|\\| yy != hand.yakudaLast[1]);\\n$1if(state.changedSinceLastSync) state.lastChangeTime = mPredictedTime;\\n$1hand.yakudaLast[0] = yx; hand.yakudaLast[1] = yy;|' "$F"
if grep -q 'hand.yakudaLast\\[0\\] = yx' "$F"; then
    ok "Patch: Achs-Umbelegung"
else
    PATCHED=0; echo {q(t["patch_warn"])}
fi
# yakuda-connect-Patch 3: Sync-Korrektur (memcpy ab dem 2. Action-Set) und
# Diagnose-Log {DEBUG_LOG_NAME} neben der Config. Passt er nicht (neuere
# xrBinder-Version), wird ohne ihn gebaut — Patch 1+2 bleiben.
P3="$ROOT/{PATCH3_NAME}"
P3REP="$ROOT/{PATCH3_REPORT}"
cat > "$P3" <<'YC_PATCH3_EOF'
{PATCH3_PERL}YC_PATCH3_EOF
cp "$F" "$F.yc-p2"
if perl "$P3" "$F" > "$P3REP"; then
    ok {q(t["patch3_ok"])}; sed 's/^/    /' "$P3REP"
else
    cp "$F.yc-p2" "$F"; echo "off all" > "$P3REP"; echo {q(t["patch3_warn"])}
fi

step {q("3/3  " + t["step_build"])}
JOBS="$(nproc 2>/dev/null || echo 2)"
cmake -S "$SRC" -B "$BUILD" -DENABLE_GUI=OFF -DCMAKE_BUILD_TYPE=Release || fail {q(t["err_build"])}
if ! cmake --build "$BUILD" -j"$JOBS"; then
    cmp -s "$F" "$F.yc-p2" && fail {q(t["err_build"])}
    echo; echo {q(t["patch3_warn"])}
    # erst nur die Korrekturen (ohne Log), dann ganz ohne Patch 3
    cp "$F.yc-p2" "$F"
    if perl "$P3" --fixes-only "$F" > "$P3REP" && cmake --build "$BUILD" -j"$JOBS"; then
        sed 's/^/    /' "$P3REP"
    else
        cp "$F.yc-p2" "$F"; echo "off all" > "$P3REP"
        cmake --build "$BUILD" -j"$JOBS" || fail {q(t["err_build"])}
    fi
fi
[ -f "$LIB" ] || fail {q(t["err_build"])}" $LIB"

[ "$PATCHED" = 1 ] && echo {PATCH_LEVEL} > "$ROOT/{PATCH_FILE}"
echo ok > "$STATUS"
echo
ok {q(t["done"])}
echo {q(t["closing"])}
sleep 3
"""


def _build_worker_class():
    """QThread-Klasse erst bei Bedarf bauen: die Logik oben bleibt ohne Qt testbar."""
    from PySide6.QtCore import QThread, Signal

    class XrBinderBuildWorker(QThread):
        """Schreibt install.sh und fuehrt es im Terminal aus (wie CargoInstallWorker)."""
        status_signal = Signal(str)
        finished_signal = Signal(bool)

        def __init__(self, lang="de"):
            super().__init__()
            self.lang = lang

        def run(self):
            from cargo_installer import MAX_WAIT_S, _pid_alive, _read, terminal_command
            from install_worker import find_terminal
            from translations import tr

            root = tool_root()
            script = os.path.join(root, SCRIPT_NAME)
            status_file = os.path.join(root, STATUS_NAME)
            pid_file = os.path.join(root, PID_NAME)
            terminal, flags = find_terminal()
            if terminal is None:
                self.status_signal.emit(tr("tools_cargo_no_terminal"))
                self.finished_signal.emit(False)
                return
            try:
                os.makedirs(root, exist_ok=True)
                for p in (status_file, pid_file):
                    if os.path.exists(p):
                        os.remove(p)
                with open(script, "w", encoding="utf-8") as fh:
                    fh.write(build_script(self.lang))
                os.chmod(script, 0o755)
            except OSError as exc:
                self.status_signal.emit(f"{tr('tools_install_error')}: {exc}")
                self.finished_signal.emit(False)
                return
            started = time.time()
            try:
                subprocess.Popen(terminal_command(terminal, flags, script)).wait()
            except OSError as exc:
                self.status_signal.emit(f"{tr('tools_install_error')}: {exc}")
                self.finished_signal.emit(False)
                return
            while not os.path.exists(status_file) and time.time() - started < MAX_WAIT_S:
                pid = _read(pid_file)
                if pid.isdigit() and _pid_alive(int(pid)):
                    time.sleep(1)
                    continue
                if not pid and time.time() - started < 15:
                    time.sleep(0.5)
                    continue
                break
            self.finished_signal.emit(_read(status_file) == "ok" and is_built())

    return XrBinderBuildWorker


def make_build_worker(lang="de"):
    return _build_worker_class()(lang)
