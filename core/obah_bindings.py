#!/usr/bin/env python3
"""
obah_bindings.py — die Auswahl-Schritte von obah, ohne obah zu starten
======================================================================
obah (https://github.com/galister/obah) fuehrt durch drei Bildschirme:

  1. Spiel waehlen        — alle Steam-Spiele MIT OpenVR-Action-Manifest
  2. Controller waehlen   — feste Liste von Eingabeprofilen, je Profil mit
                            Haekchen, welche Bindings es schon gibt
  3. Bindings laden       — "Game default bindings", "xrizer bindings",
                            "VapoR bindings", "OpenComposite bindings" (nur
                            die, die es gibt) oder "Start from scratch"

Dieses Modul liest dieselben Daten nach denselben Regeln (Stand obah 0.1.1,
src/steam.rs, src/sources.rs, src/input_profiles.rs,
src/screens/controller_type.rs), damit der Controls-Tab sie als Dropdowns
anbieten kann. Es wird nur GELESEN — geschrieben wird hier nichts.

Eine Abweichung, bewusst: obah sucht den Spielordner unter
'steamapps/common/<Name aus der .acf>'. Steam legt ihn aber unter
'installdir' ab, und der weicht beim Namen oft ab (Doppelpunkte,
Markenzeichen, ...). Wir nehmen 'installdir' und fallen auf den Namen
zurueck — so tauchen hier auch Spiele auf, die obah uebersieht.

Zweite Abweichung (seit v1.3.2): Die Spieleliste enthaelt zusaetzlich ALLE
Spiele aus dem Games-Tab — auch Nicht-Steam-Spiele und eigene Eintraege.
Deren Ordner kommt aus Startordner bzw. Programmpfad. Spiele ohne
Action-Datei stehen mit in der Liste, sind aber nicht bearbeitbar
(ObahGame.has_manifest == False) — obah braucht die Datei fuer die Aktionen.
"""
import json
import os
from collections import deque
from dataclasses import dataclass, field

from logging_setup import get_logger

log = get_logger("obah_bindings")

# src/steam.rs: MANIFEST_NAMES
MANIFEST_NAMES = ("actions.json", "action_manifest.json",
                  "vr_actions.json", "steamvr_actions.json")
# Zusaetzlich (nicht in obah): Unreals SteamVR-Input-Plugin nennt seine
# Datei so und legt sie unter Config/SteamVRBindings/ ab — ohne diesen Namen
# fehlen alle Unreal-Spiele mit SteamVR-Eingabe.
EXTRA_MANIFEST_NAMES = ("steamvr_manifest.json",)
SEARCH_NAMES = MANIFEST_NAMES + EXTRA_MANIFEST_NAMES
# src/steam.rs: find_actions_json -> 'depth > 8' bricht ab
MAX_DEPTH = 8
# Proton-Prefix: dort schreiben manche Spiele die Datei erst beim Start hin
PREFIX_SUBDIRS = ("AppData/Local", "AppData/LocalLow", "AppData/Roaming",
                  "Documents", "Saved Games")
PREFIX_MAX_DIRS = 8000

# src/input_profiles.rs: INPUT_PROFILES_BYTES — Reihenfolge wie in obah.
# (pico_controller liegt in obahs profiles/, ist aber nicht eingetragen und
# damit in obah nicht waehlbar — hier deshalb auch nicht.)
CONTROLLER_TYPES = (
    "gamepad",
    "knuckles",
    "oculus_touch",
    "rift",
    "svl_hand_interaction_augmented",
    "vive_controller",
    "vive_focus3_controller",
)

# Lesbare Namen. obah zeigt nur den umformatierten Schluessel
# ("Oculus Touch"); fuer ein Dropdown darf es etwas sprechender sein.
CONTROLLER_LABELS = {
    "gamepad": "Gamepad",
    "knuckles": "Valve Index (Knuckles)",
    "oculus_touch": "Oculus / Meta Touch",
    "rift": "Oculus Rift",
    "svl_hand_interaction_augmented": "Hand-Tracking (SVL Hand Interaction)",
    "vive_controller": "HTC Vive Controller",
    "vive_focus3_controller": "HTC Vive Focus 3 Controller",
}

# Bindings-Quellen (src/screens/mod.rs: BindingSourceSelection)
SOURCE_DEFAULT = "default"
SOURCE_XRIZER = "xrizer"
SOURCE_VAPOR = "vapor"
SOURCE_OPENCOMPOSITE = "opencomposite"
SOURCE_SCRATCH = "scratch"
SOURCE_ORDER = (SOURCE_DEFAULT, SOURCE_XRIZER, SOURCE_VAPOR,
                SOURCE_OPENCOMPOSITE, SOURCE_SCRATCH)


def format_name(controller_type):
    """obahs InputProfile::format_name_str: 'oculus_touch' -> 'Oculus Touch'."""
    return " ".join(w[:1].upper() + w[1:] for w in controller_type.split("_"))


def controller_label(controller_type):
    return CONTROLLER_LABELS.get(controller_type, format_name(controller_type))


# Art eines Spiels (wie im Games-Tab)
KIND_STEAM = "steam"
KIND_SHORTCUT = "shortcut"      # Nicht-Steam-Spiel in Steam
KIND_LOCAL = "local"            # eigener Eintrag ohne Steam


@dataclass
class ObahGame:
    name: str
    appid: str
    game_folder: str
    actions_json: str
    kind: str = KIND_STEAM

    @property
    def has_manifest(self):
        """Nur mit Action-Datei lassen sich Bindings anzeigen und bearbeiten."""
        return bool(self.actions_json)

    manual: bool = False     # Action-Datei vom Nutzer selbst gewaehlt

    @property
    def key(self):
        """Eindeutige Kennung fuer Dropdowns — auch ohne Spielordner."""
        return self.game_folder or f"{self.kind}:{self.appid}"

    @property
    def ident(self):
        """Feste Kennung (aendert sich nicht, wenn eine Datei gewaehlt wird)."""
        return f"{self.kind}:{self.appid}"


@dataclass
class Availability:
    default: bool = False
    xrizer: bool = False
    vapor: bool = False
    opencomposite: bool = False

    def any(self):
        return self.default or self.xrizer or self.vapor or self.opencomposite

    def sources(self):
        """Ladbare Quellen in obahs Reihenfolge; 'Start from scratch' immer zuletzt."""
        out = [s for s in (SOURCE_DEFAULT, SOURCE_XRIZER, SOURCE_VAPOR, SOURCE_OPENCOMPOSITE)
               if getattr(self, s)]
        out.append(SOURCE_SCRATCH)
        return out


@dataclass
class GameBindings:
    """Ergebnis fuer ein Spiel: je Controller, welche Bindings es gibt."""
    game: ObahGame
    controllers: dict = field(default_factory=dict)   # {controller_type: Availability}


# --------------------------------------------------------------------------- #
#  1. Spiele
# --------------------------------------------------------------------------- #
def find_actions_json(game_folder, max_depth=MAX_DEPTH, max_dirs=None):
    """
    Pfad des OpenVR-Action-Manifests im Spielordner, sonst None.

    Breitensuche statt obahs Tiefensuche: gleiche Namen, gleiche Tiefe, aber
    ein Manifest weiter oben gewinnt. Bei Unity liegt es typischerweise
    unter <Spiel>_Data/StreamingAssets/SteamVR/actions.json.
    """
    if not game_folder or not os.path.isdir(game_folder):
        return None
    queue = deque([(game_folder, 0)])
    seen = 0
    while queue:
        current, depth = queue.popleft()
        seen += 1
        if max_dirs is not None and seen > max_dirs:
            return None
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for e in entries:
            if e.name in SEARCH_NAMES and e.is_file():
                # obahs Namen ungeprueft (wie obah), die zusaetzlichen nur,
                # wenn wirklich Aktionen drinstehen
                if e.name in MANIFEST_NAMES or is_action_manifest(e.path):
                    return e.path
        if depth >= max_depth:
            continue
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    queue.append((e.path, depth + 1))
            except OSError:
                pass
    return None


def is_action_manifest(path):
    """Sieht die Datei aus wie ein OpenVR-Action-Manifest (Liste 'actions')?"""
    try:
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and isinstance(data.get("actions"), list) \
        and isinstance(data.get("action_sets", []), list)


def prefix_dirs(appid):
    """Ordner im Proton-Prefix des Spiels, in denen gesucht wird."""
    if not str(appid or "").isdigit():
        return []
    try:
        import vr_environment as venv
        roots = venv.steam_data_roots()
    except Exception:  # noqa: BLE001 — Tests / ohne Steam
        return []
    out = []
    rel = f"steamapps/compatdata/{appid}/pfx/drive_c/users/steamuser"
    for root in roots:
        user = os.path.join(root, rel)
        for sub in PREFIX_SUBDIRS:
            path = os.path.join(user, sub)
            if os.path.isdir(path):
                out.append(path)
    return out


def find_prefix_manifest(appid, dirs=None):
    """Action-Datei im Proton-Prefix (nur Dateien mit echten Aktionen)."""
    for base in (dirs if dirs is not None else prefix_dirs(appid)):
        path = find_actions_json(base, max_depth=7, max_dirs=PREFIX_MAX_DIRS)
        if path and is_action_manifest(path):
            return path
    return None


def _game_folder(app):
    common = os.path.join(app["steamapps"], "common")
    for sub in (app.get("installdir"), app.get("name")):
        if sub:
            path = os.path.join(common, sub)
            if os.path.isdir(path):
                return path
    return ""


# Ordner, die sicher kein Spielordner sind. Zeigt der Startordner eines
# Nicht-Steam-Spiels dorthin (Heroic/Lutris-Starter, /usr/bin, ...), wird
# gar nicht erst gesucht — sonst liefe die Suche durchs halbe System.
_NO_SEARCH = {"/", "/usr", "/usr/bin", "/usr/local", "/usr/local/bin", "/bin",
              "/opt", "/home", "/tmp", "/var", "/etc", "/mnt", "/media", "/run"}
# Obergrenze fuer die Suche in Ordnern ausserhalb von Steam
LIBRARY_MAX_DIRS = 4000


def _unquote(text):
    text = (text or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    return text


def library_folder(start_dir="", exe=""):
    """
    Spielordner eines Nicht-Steam- oder eigenen Spiels: der Startordner,
    sonst der Ordner der Programmdatei. "" wenn keiner taugt.
    """
    home = os.path.realpath(os.path.expanduser("~"))
    candidates = [_unquote(start_dir)]
    exe = _unquote(exe)
    if exe:
        candidates.append(os.path.dirname(exe))
    for cand in candidates:
        if not cand:
            continue
        path = os.path.realpath(os.path.expanduser(cand))
        if path in _NO_SEARCH or path == home or not os.path.isdir(path):
            continue
        return path
    return ""


def _library_entries():
    """Spiele des Games-Tabs; leer, wenn das Modul nicht geht (Tests)."""
    try:
        import games
        return games.games_tab_entries()
    except Exception as exc:  # noqa: BLE001
        log.warning("Spiele aus dem Games-Tab nicht lesbar: %s", exc)
        return []


def _shortcut_map():
    try:
        import steam_shortcuts
        return {s["appid"]: s for s in steam_shortcuts.list_shortcuts()}
    except Exception as exc:  # noqa: BLE001
        log.warning("Nicht-Steam-Spiele nicht lesbar: %s", exc)
        return {}


def list_games(apps=None, cancelled=None, library=None, shortcuts=None, manual=None,
               search_prefix=True):
    """
    Alle Spiele fuer Schritt 1, alphabetisch (ohne Gross-/Kleinschreibung):

      * jedes installierte Steam-Spiel mit Action-Manifest (wie obah)
      * dazu jedes Spiel aus dem Games-Tab — Steam, Nicht-Steam und eigene.
        Ohne Action-Datei steht es trotzdem da (has_manifest == False).

    apps      : Liste wie games.installed_steam_apps() (fuer Tests)
    library   : Liste wie games.games_tab_entries() (fuer Tests); fehlt sie
                und fehlt auch apps, wird der Games-Tab gelesen
    shortcuts : {appid: Eintrag wie steam_shortcuts.list_shortcuts()}
    manual    : {ObahGame.ident: pfad} — vom Nutzer gewaehlte Action-Dateien;
                fehlt es, wird controls_manifests.json gelesen
    search_prefix : ohne Datei im Spielordner auch im Proton-Prefix suchen
    """
    if manual is None:
        manual = load_manual_manifests() if apps is None else {}
    if apps is None:
        import games
        apps = games.installed_steam_apps()
        if library is None:
            library = _library_entries()
    library = library or []
    found = {}                       # key -> ObahGame
    by_appid = {}
    for app in apps:
        if cancelled and cancelled():
            break
        folder = _game_folder(app)
        appid = str(app.get("appid", ""))
        by_appid[appid] = (app, folder)
        if not folder:
            continue
        manifest = find_actions_json(folder)
        if manifest:
            g = ObahGame(name=app.get("name") or folder, appid=appid,
                         game_folder=folder, actions_json=manifest)
            found[g.key] = g

    steam_ids = {g.appid for g in found.values()}
    if any(e.get("kind") == KIND_SHORTCUT for e in library) and shortcuts is None:
        shortcuts = _shortcut_map()
    shortcuts = shortcuts or {}

    for entry in library:
        if cancelled and cancelled():
            break
        kind = entry.get("kind") or KIND_STEAM
        gid = str(entry.get("id", ""))
        name = entry.get("name") or gid
        if kind == KIND_STEAM:
            if gid in steam_ids:
                continue                        # schon oben (mit Manifest)
            _app, folder = by_appid.get(gid, (None, ""))
            manifest = ""                       # oben schon gesucht: keins
        else:
            if kind == KIND_SHORTCUT:
                sc = shortcuts.get(gid) or {}
                folder = library_folder(sc.get("start_dir", ""), sc.get("exe", ""))
            else:
                folder = library_folder("", entry.get("exe", ""))
            manifest = find_actions_json(folder, max_dirs=LIBRARY_MAX_DIRS) or "" \
                if folder else ""
        if not manifest and search_prefix:
            # Unreal & Co. schreiben die Datei teils erst beim Start in den
            # Proton-Prefix (AppData/Local/<Spiel>/Saved/...)
            manifest = find_prefix_manifest(gid) or ""
        g = ObahGame(name=name, appid=gid, game_folder=folder,
                     actions_json=manifest, kind=kind)
        if g.key in found:
            continue                            # gleicher Ordner wie ein Steam-Spiel
        found[g.key] = g

    # Von Hand gewaehlte Dateien gewinnen immer (auch ueber eine gefundene)
    for g in found.values():
        path = manual.get(g.ident)
        if path and os.path.isfile(path):
            g.actions_json = path
            g.manual = True
            if not g.game_folder:
                # xrizer-/OpenComposite-Dateien brauchen einen Ordner
                g.game_folder = os.path.dirname(path)

    return sorted(found.values(), key=lambda g: g.name.lower())


# --------------------------------------------------------------------------- #
#  Von Hand gewaehlte Action-Dateien
# --------------------------------------------------------------------------- #
def manual_manifests_file():
    import paths
    return paths.config_file("controls_manifests.json")


def load_manual_manifests():
    """{ObahGame.ident: pfad}; leer, wenn es nichts gibt."""
    try:
        from jsonio import read_json
        data = read_json(manual_manifests_file(), default={})
    except Exception as exc:  # noqa: BLE001
        log.warning("controls_manifests.json nicht lesbar: %s", exc)
        return {}
    games = data.get("games") if isinstance(data, dict) else None
    return {str(k): str(v) for k, v in (games or {}).items() if v}


def set_manual_manifest(ident, path):
    """Datei merken (path) oder vergessen (None). True bei Erfolg."""
    from jsonio import update_json
    games = load_manual_manifests()
    if path:
        games[ident] = path
    else:
        games.pop(ident, None)
    return bool(update_json(manual_manifests_file(), {"games": games}))


# --------------------------------------------------------------------------- #
#  2./3. Controller und Bindings-Quellen
# --------------------------------------------------------------------------- #
def xrizer_path(game_folder, controller_type):
    """src/sources.rs: <Spiel>/xrizer/<typ ohne Unterstriche>.json"""
    return os.path.join(game_folder, "xrizer", controller_type.replace("_", "") + ".json")


def opencomposite_path(game_folder, controller_type):
    return os.path.join(game_folder, "OpenComposite", controller_type + ".json")


def vapor_path(game_folder):
    return os.path.join(game_folder, "vapor_binding.json")


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def default_bindings(actions_json):
    """{controller_type: Pfad} aus 'default_bindings' des Manifests."""
    data = _read_json(actions_json)
    out = {}
    if not isinstance(data, dict):
        return out
    base = os.path.dirname(actions_json)
    for b in data.get("default_bindings") or []:
        if isinstance(b, dict) and b.get("controller_type") and b.get("binding_url"):
            out[b["controller_type"]] = os.path.normpath(os.path.join(base, b["binding_url"]))
    return out


def scan_bindings(game):
    """Je Controller aus CONTROLLER_TYPES: welche Bindings gibt es fuer dieses Spiel?"""
    avail = {ct: Availability() for ct in CONTROLLER_TYPES}
    if not game.has_manifest or not game.game_folder:
        return GameBindings(game=game, controllers=avail)

    for ct in default_bindings(game.actions_json):
        if ct in avail:
            avail[ct].default = True

    # xrizer: Dateiname ohne Unterstriche, Vergleich ebenfalls ohne
    xdir = os.path.join(game.game_folder, "xrizer")
    if os.path.isdir(xdir):
        stripped = {ct.replace("_", ""): ct for ct in CONTROLLER_TYPES}
        for fname in os.listdir(xdir):
            stem, ext = os.path.splitext(fname)
            if ext == ".json" and stem.replace("_", "") in stripped:
                avail[stripped[stem.replace("_", "")]].xrizer = True

    odir = os.path.join(game.game_folder, "OpenComposite")
    if os.path.isdir(odir):
        for fname in os.listdir(odir):
            stem, ext = os.path.splitext(fname)
            if ext == ".json" and stem in avail:
                avail[stem].opencomposite = True

    vapor = _read_json(vapor_path(game.game_folder))
    if isinstance(vapor, dict) and vapor.get("controller_type") in avail:
        avail[vapor["controller_type"]].vapor = True

    return GameBindings(game=game, controllers=avail)


def binding_file(game, controller_type, source, must_exist=True):
    """
    Datei, die obah fuer diese Quelle laden wuerde (src/main.rs:
    resolve_binding_path). None bei 'Start from scratch' oder — mit
    must_exist — wenn es sie nicht gibt. Das kommt vor: manche Manifeste
    verweisen auf Dateien, die das Spiel gar nicht mitliefert. obah startet
    dann ohne Meldung mit einer leeren Belegung.
    """
    if source == SOURCE_DEFAULT:
        path = default_bindings(game.actions_json).get(controller_type)
    elif source == SOURCE_XRIZER:
        path = xrizer_path(game.game_folder, controller_type)
    elif source == SOURCE_VAPOR:
        path = vapor_path(game.game_folder)
    elif source == SOURCE_OPENCOMPOSITE:
        path = opencomposite_path(game.game_folder, controller_type)
    else:
        return None
    if not path:
        return None
    return path if (not must_exist or os.path.isfile(path)) else None
