#!/usr/bin/env python3
"""
games.py — Zentrale VR-Spieleliste + Steam-Scanner für yakuda-connect
=====================================================================
Aufbau wie programs.py: EINE Quelle der Wahrheit für alle bekannten
VR-Spiele. Der Schlüssel ist die Steam-AppID (damit im Script nie ein
Spielname falsch geschrieben werden kann) — dem Nutzer wird in der UI
aber immer der NAME angezeigt, nie die ID.

Felder pro Spiel:
  name           : Anzeigename (das sieht der Nutzer)
  launch_params  : Startparameter je GPU-Hersteller {"amd": ..., "nvidia": ...}
  protons        : Liste empfohlener Proton-Versionen, jede mit:
      version           : exakter Versionsname (so wie er in Steam erscheint)
      role              : "main"          -> Empfehlung für normale Nutzer
                          "main_cachyos"  -> Empfehlung für CachyOS-Nutzer
                          "alternative"   -> Alternative
      protonplus_runner : runner_id für die ProtonPlus-CLI
                          (protonplus install <launcher_id> <runner_id>).
                          None = kommt nicht über ProtonPlus (z. B. Valves
                          offizielles Proton, das Steam selbst mitbringt).
      desc              : Beschreibung {"de": ..., "en": ...}

Neues Spiel hinzufügen: einfach einen Eintrag an GAMES anhängen —
Scan, Karte und ProtonPlus-Knopf ziehen automatisch nach.

Der Scanner (scan_installed_games) liest die appmanifest_<id>.acf-Dateien
aus allen Steam-Bibliotheken (nativ + Flatpak + zusätzliche Bibliotheken
aus libraryfolders.vdf). Das Ergebnis wird in der App-Config gecacht
(Key "detected_games"), damit nicht bei jedem Tab-Besuch neu gescannt
werden muss — der "Spiele scannen"-Button erzwingt einen Neu-Scan.
"""

import os
import re
import json
import shutil
import subprocess

import vr_environment as venv

HOME = os.path.expanduser("~")
APP_CONFIG = os.path.join(HOME, ".config/yakuda-connect/config/config.json")

PROTONPLUS_FLATPAK_ID = "com.vysp3r.ProtonPlus"

# --------------------------------------------------------------------------- #
#  Bausteine für die Spieldatenbank
# --------------------------------------------------------------------------- #
#  NEUES SPIEL HINZUFÜGEN — Kurzanleitung
#  --------------------------------------
#  In GAMES einen Eintrag ergänzen: Schlüssel ist die Steam-AppID (String),
#  Wert ist ein game(...)-Aufruf. Der Nutzer sieht immer nur den Namen.
#
#    "1234567": game("Mein VR-Spiel", protons_valve_main()),
#
#  Mehr Möglichkeiten:
#
#    "1234567": game(
#        "Mein VR-Spiel",
#        protons_ge_main(),                      # GE statt Valve als Empfehlung
#        launch_params=all_gpus("gamemoderun %command%"),   # gleiche Parameter
#        # launch_params={"amd": "...", "nvidia": "..."},   # oder je GPU
#        fixes=["vrchat_pictures"],              # spielspezifische Fix-Buttons
#    ),
#
#  Braucht ein Spiel eigene Proton-Versionen/Texte (wie VRChat), baust du die
#  Liste mit proton(...) selbst:
#
#    protons=[
#        proton(P_GE, "main", de="...", en="..."),
#        proton(P_CACHYOS, "main_cachyos", de="...", en="..."),
#        proton(P_VALVE, "alternative", de="...", en="...", hide_on_cachyos=True),
#    ]
#
#  Rollen:  "main"         -> Empfehlung auf Standard-Distros
#           "main_cachyos" -> Empfehlung auf CachyOS
#           "alternative"  -> alles Weitere
#  hide_on_cachyos=True blendet den Eintrag auf CachyOS komplett aus.

# Bekannte Proton-Quellen: (version, protonplus_runner)
# runner None = bringt Steam selbst mit; sonst der Runner der ProtonPlus-CLI.
P_VALVE   = ("Proton 11 (Standard)",  None)
P_CACHYOS = ("proton-cachyos-11.x",   "proton-cachyos")
P_GE      = ("Proton-GE",             "proton-ge")
P_RTSP    = ("Proton-GE RTSP",        "proton-ge-rtsp")   # GE mit RTSP-Codecs (VRChat)


def proton(source, role, de="", en="", hide_on_cachyos=False, version=None):
    """
    Ein Proton-Eintrag für die "protons"-Liste eines Spiels.
      source          : eine der P_*-Konstanten (version, runner)
      role            : "main" | "main_cachyos" | "alternative"
      de / en         : Beschreibung, die im Panel unter der Version steht
      hide_on_cachyos : Eintrag auf CachyOS ausblenden
      version         : überschreibt den Versionsnamen (für angepinnte Builds)
    """
    ver, runner = source
    entry = {
        "version": version or ver,
        "role": role,
        "protonplus_runner": runner,
        "desc": {"de": de, "en": en},
    }
    if hide_on_cachyos:
        entry["hide_on_cachyos"] = True
    return entry


def game(name, protons, launch_params=None, fixes=None):
    """Ein Eintrag für die GAMES-Tabelle."""
    return {
        "name": name,
        "protons": protons,
        "launch_params": launch_params or {},
        "fixes": fixes or [],
    }


def all_gpus(params):
    """Dieselben Startparameter für AMD und NVIDIA."""
    return {"amd": params, "nvidia": params}


# --------------------------------------------------------------------------- #
#  Fertige Proton-Sets (decken die meisten Spiele ab)
# --------------------------------------------------------------------------- #
# Unterschied ist nur, WELCHE Version auf Standard-Distros die Empfehlung ist.
# Auf CachyOS ist es in beiden Fällen proton-cachyos. Die Funktionen liefern
# jedes Mal frische Dicts, damit sich die Spiele keine Objekte teilen.

_D_REC_DE = "Getestete Empfehlung für dieses Spiel."
_D_REC_EN = "Tested recommendation for this game."
_D_CACHY_DE = "Getestete Empfehlung für CachyOS-Nutzer (beste Performance/Latenz)."
_D_CACHY_EN = "Tested recommendation for CachyOS users (best performance/latency)."
_D_ALT_GE_DE = ("Alternative — empfohlen, falls es zu Problemen mit In-Game-Videos "
                "oder Audio-Codecs kommt (GE bringt zusätzliche Media-Codecs mit).")
_D_ALT_GE_EN = ("Alternative — recommended if you run into problems with in-game "
                "videos or audio codecs (GE ships extra media codecs).")
_D_ALT_VALVE_DE = "Alternative — Steams normales Proton, falls Proton-GE Probleme macht."
_D_ALT_VALVE_EN = "Alternative — Steam's default Proton, in case Proton-GE causes trouble."


def protons_valve_main():
    """Proton 11 (Standard) = Empfehlung, CachyOS-Proton auf CachyOS, GE = Alternative."""
    return [
        proton(P_VALVE,   "main",         de=_D_REC_DE,     en=_D_REC_EN),
        proton(P_CACHYOS, "main_cachyos", de=_D_CACHY_DE,   en=_D_CACHY_EN),
        proton(P_GE,      "alternative",  de=_D_ALT_GE_DE,  en=_D_ALT_GE_EN),
    ]


def protons_ge_main():
    """Proton-GE = Empfehlung, CachyOS-Proton auf CachyOS, Valve-Proton = Alternative."""
    return [
        proton(P_GE,      "main",         de=_D_REC_DE,        en=_D_REC_EN),
        proton(P_CACHYOS, "main_cachyos", de=_D_CACHY_DE,      en=_D_CACHY_EN),
        proton(P_VALVE,   "alternative",  de=_D_ALT_VALVE_DE,  en=_D_ALT_VALVE_EN),
    ]


# --------------------------------------------------------------------------- #
#  Spieldatenbank (Schlüssel = Steam-AppID als String)
# --------------------------------------------------------------------------- #
GAMES = {
    # VRChat pinnt bewusst konkrete Builds und hat eigene Beschreibungen.
    "438100": game(
        "VRChat",
        protons=[
            proton(P_RTSP, "main", version="proton-rtsp-11.0-20260609-1",
                   de=("Alle Videoplayer funktionieren, aber Social-Liste und Invites "
                       "sowie die Performance sind ein bisschen schlechter."),
                   en=("All video players work, but the social list and invites "
                       "as well as performance are slightly worse.")),
            proton(P_CACHYOS, "main_cachyos", version="proton-cachyos-11.0-20260602",
                   de=("Alle Videoplayer funktionieren außer dem alten Unity-Player. "
                       "Maximale Performance/Latenz, Social-Liste und Invites funktionieren."),
                   en=("All video players work except the old Unity player. "
                       "Maximum performance/latency, social list and invites work.")),
            # Auf CachyOS überflüssig (bricht dort nur die Videoplayer):
            # proton-cachyos + proton-rtsp reichen völlig -> ausblenden.
            proton(P_VALVE, "alternative", version="proton-11.0-1", hide_on_cachyos=True,
                   de="Maximale Performance, aber keine Videoplayer funktionieren.",
                   en="Maximum performance, but no video players work."),
        ],
        launch_params=all_gpus(
            "gamemoderun %command% --enable-avpro-in-prose "
            "--enable-hardware-decoding --fps=90 --disable-amd-stutter-workaround"),
        fixes=["vrchat_pictures"],
    ),

    "1540210": game("Arizona Sunshine 2",         protons_valve_main()),
    "2897700": game("Arizona Sunshine Remake",    protons_valve_main()),
    "2669410": game("Metro Awakening",            protons_ge_main()),
    "2800080": game("Thief VR: Legacy of Shadow", protons_valve_main()),
    "620980":  game("Beat Saber",                 protons_valve_main()),

    # Weitere VR-Spiele hier ergänzen ...
}

# --------------------------------------------------------------------------- #
#  Steam-Bibliotheken finden + installierte Spiele scannen
# --------------------------------------------------------------------------- #
def _steamapps_dirs():
    """
    Alle steamapps-Ordner: Standard-Bibliotheken (nativ + Flatpak) und
    zusätzliche Bibliotheken aus libraryfolders.vdf (z. B. zweite Platte).
    """
    dirs = []
    for root in venv.steam_data_roots():
        sa = os.path.join(root, "steamapps")
        if os.path.isdir(sa):
            dirs.append(sa)
        # Zusätzliche Bibliotheken aus libraryfolders.vdf
        vdf = os.path.join(sa, "libraryfolders.vdf")
        if os.path.isfile(vdf):
            try:
                with open(vdf, "r", errors="ignore") as f:
                    content = f.read()
                # "path"  "/mnt/spiele/SteamLibrary"
                for m in re.finditer(r'"path"\s+"([^"]+)"', content):
                    extra = os.path.join(m.group(1), "steamapps")
                    if os.path.isdir(extra):
                        dirs.append(extra)
            except Exception:
                pass
    # Duplikate entfernen, Reihenfolge erhalten
    seen, unique = set(), []
    for d in dirs:
        real = os.path.realpath(d)
        if real not in seen:
            seen.add(real)
            unique.append(d)
    return unique


# Steam-eigene Tools, die zwar VR-Bibliotheken enthalten, aber keine Spiele
# sind (würden die Heuristik sonst täuschen).
_APPID_BLACKLIST = {
    "250820",    # SteamVR
    "228980",    # Steamworks Common Redistributables
    "1493710",   # Proton Experimental
    "1070560",   # Steam Linux Runtime
    "1391110",   # Steam Linux Runtime - Soldier
    "1628350",   # Steam Linux Runtime - Sniper
}

# Dateien, an denen wir ein VR-Spiel erkennen (OpenVR-/OpenXR-Loader im
# Installationsordner). Funktioniert komplett offline.
_VR_MARKER_FILES = {
    "openvr_api.dll", "libopenvr_api.so",
    "openxr_loader.dll", "libopenxr_loader.so",
}
_VR_SCAN_MAX_DIRS = 400   # Sicherheitslimit pro Spiel (große Spiele!)
_VR_SCAN_MAX_DEPTH = 4


def _parse_acf(path):
    """Liest appid, name und installdir aus einer appmanifest_<id>.acf."""
    try:
        with open(path, "r", errors="ignore") as f:
            content = f.read()
    except Exception:
        return None
    def field(key):
        m = re.search(r'"%s"\s+"([^"]*)"' % key, content)
        return m.group(1) if m else ""
    appid = field("appid")
    if not appid:
        m = re.match(r"appmanifest_(\d+)\.acf$", os.path.basename(path))
        appid = m.group(1) if m else ""
    return {"appid": appid, "name": field("name"),
            "installdir": field("installdir")}


def _looks_like_vr_game(steamapps_dir, installdir):
    """
    True, wenn der Installationsordner OpenVR-/OpenXR-Loader enthält.
    Begrenzte Tiefensuche, damit der Scan auch bei riesigen Spielen
    schnell bleibt.
    """
    if not installdir:
        return False
    root = os.path.join(steamapps_dir, "common", installdir)
    if not os.path.isdir(root):
        return False
    root_depth = root.rstrip(os.sep).count(os.sep)
    visited = 0
    try:
        for cur, dirs, files in os.walk(root):
            visited += 1
            if visited > _VR_SCAN_MAX_DIRS:
                return False
            if cur.count(os.sep) - root_depth >= _VR_SCAN_MAX_DEPTH:
                dirs[:] = []   # nicht tiefer absteigen
            for f in files:
                if f.lower() in _VR_MARKER_FILES:
                    return True
    except Exception:
        pass
    return False


def scan_installed_games():
    """
    Scannt alle Steam-Bibliotheken nach appmanifest_<id>.acf und liest
    JEDES gefundene VR-Spiel ein (kein Profil-Filter mehr!).
    Rückgabe: (tested, untested)
      tested   : AppIDs mit vordefiniertem Profil in GAMES (sortiert nach Name)
      untested : Liste von {"appid", "name"} für alle übrigen erkannten
                 VR-Spiele (Erkennung: OpenVR-/OpenXR-Loader im Spielordner),
                 sortiert nach Name.
    """
    tested = set()
    untested = {}
    for sa in _steamapps_dirs():
        try:
            fnames = os.listdir(sa)
        except Exception:
            continue
        for fname in fnames:
            if not re.match(r"appmanifest_\d+\.acf$", fname):
                continue
            info = _parse_acf(os.path.join(sa, fname))
            if not info or not info["appid"]:
                continue
            appid = info["appid"]
            if appid in _APPID_BLACKLIST:
                continue
            if appid in GAMES:
                tested.add(appid)          # kuratiertes Profil -> "getestet"
            elif appid not in untested and _looks_like_vr_game(sa, info["installdir"]):
                untested[appid] = info["name"] or f"App {appid}"

    tested_list = sorted(tested, key=lambda a: GAMES[a]["name"].lower())
    untested_list = sorted(
        ({"appid": a, "name": n} for a, n in untested.items()),
        key=lambda g: g["name"].lower())
    return tested_list, untested_list


# --------------------------------------------------------------------------- #
#  Cache in der App-Config ("nicht jedes Mal neu scannen")
# --------------------------------------------------------------------------- #
def _load_app_config():
    try:
        with open(APP_CONFIG, "r") as f:
            content = f.read().strip()
            return json.loads(content) if content else {}
    except Exception:
        return {}


def load_cached_games():
    """
    Gecachte Scan-Ergebnisse aus der Config.
    Rückgabe: (tested, untested, wurde_schon_gescannt: bool)
    Getestete AppIDs nur, wenn es sie noch in GAMES gibt; ist ein früher
    ungetestetes Spiel inzwischen in GAMES kuratiert, wandert es beim Laden
    automatisch in die getestete Sektion.
    """
    data = _load_app_config()
    if "detected_games" not in data:
        return [], [], False
    tested = {str(a) for a in data.get("detected_games", []) if str(a) in GAMES}
    untested = []
    for g in data.get("detected_games_untested", []):
        appid = str(g.get("appid", ""))
        if not appid:
            continue
        if appid in GAMES:
            tested.add(appid)   # inzwischen kuratiert -> hochstufen
        else:
            untested.append({"appid": appid, "name": g.get("name") or f"App {appid}"})
    tested_list = sorted(tested, key=lambda a: GAMES[a]["name"].lower())
    untested.sort(key=lambda g: g["name"].lower())
    return tested_list, untested, True


def save_cached_games(tested, untested):
    """Schreibt beide Scan-Ergebnisse fest in die Config
    (Keys 'detected_games' + 'detected_games_untested')."""
    try:
        data = _load_app_config()
        data["detected_games"] = list(tested)
        data["detected_games_untested"] = [
            {"appid": g["appid"], "name": g["name"]} for g in untested]
        os.makedirs(os.path.dirname(APP_CONFIG), exist_ok=True)
        with open(APP_CONFIG, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[Games] Konnte Spiele-Cache nicht speichern: {e}")


# --------------------------------------------------------------------------- #
#  System-Erkennung: GPU-Hersteller + CachyOS
# --------------------------------------------------------------------------- #
def detect_gpu_vendor():
    """'amd' | 'nvidia' | 'unknown' — für die Vorauswahl der Startparameter."""
    # NVIDIA: proprietärer Treiber legt /proc/driver/nvidia an
    if os.path.isdir("/proc/driver/nvidia"):
        return "nvidia"
    # Kernel-Treiber der aktiven GPUs prüfen (amdgpu/radeon vs. nvidia/nouveau)
    try:
        import glob
        for link in glob.glob("/sys/class/drm/card*/device/driver"):
            drv = os.path.basename(os.path.realpath(link)).lower()
            if "amdgpu" in drv or "radeon" in drv:
                return "amd"
            if "nvidia" in drv or "nouveau" in drv:
                return "nvidia"
    except Exception:
        pass
    # Fallback: lspci
    try:
        out = subprocess.run(["lspci"], capture_output=True, text=True,
                             timeout=5).stdout.lower()
        if "nvidia" in out:
            return "nvidia"
        if "amd" in out or "radeon" in out or "advanced micro devices" in out:
            return "amd"
    except Exception:
        pass
    return "unknown"


def is_cachyos():
    """True auf CachyOS (bestimmt, welche Proton-Empfehlung 'main' ist)."""
    try:
        with open("/etc/os-release", "r") as f:
            content = f.read().lower()
        return bool(re.search(r'^id=.*cachyos', content, re.MULTILINE)) or \
            "cachyos" in "".join(re.findall(r'^id_like=(.*)$', content, re.MULTILINE))
    except Exception:
        return False


def recommended_role():
    """Welche 'role' auf diesem System die Haupt-Empfehlung ist."""
    return "main_cachyos" if is_cachyos() else "main"


def visible_protons(game):
    """
    Die auf DIESEM System anzuzeigenden Proton-Einträge eines Spiels.
    Einträge mit "hide_on_cachyos": True werden auf CachyOS ausgeblendet
    (z. B. Valves normales Proton — dort reichen cachyos + rtsp völlig).
    Die Empfehlung für dieses System steht immer zuerst.
    """
    cachy = is_cachyos()
    rec = recommended_role()
    protons = [p for p in game.get("protons", [])
               if not (cachy and p.get("hide_on_cachyos"))]
    return sorted(protons, key=lambda p: 0 if p.get("role") == rec else 1)


def dynamic_protons():
    """
    Automatisch generierte Proton-Empfehlungen für UNGETESTETE Spiele
    (Spiele ohne kuratiertes Profil in GAMES). Struktur wie die
    "protons"-Einträge der getesteten Spiele, plus "untested": True
    (die UI hängt dann das "(ungetestet)"-Suffix an).

      Option 1 (Top-Empfehlung, systemabhängig):
        CachyOS       -> proton-cachyos-11.x (über ProtonPlus installierbar)
        Standard-Distro -> Proton 11 (Standard) (bringt Steam selbst mit)
      Option 2 (immer): Proton-GE als universelle Alternative — empfohlen
        bei Problemen mit In-Game-Videos oder Audio-Codecs.
    """
    if is_cachyos():
        primary = {
            "version": "proton-cachyos-11.x",
            "role": "main_cachyos",
            "untested": True,
            "protonplus_runner": "proton-cachyos",
            "desc": {
                "de": ("Automatische Empfehlung für CachyOS — für dieses Spiel "
                       "noch nicht von uns getestet."),
                "en": ("Automatic recommendation for CachyOS — not yet tested "
                       "by us for this game."),
            },
        }
    else:
        primary = {
            "version": "Proton 11 (Standard)",
            "role": "main",
            "untested": True,
            "protonplus_runner": None,   # bringt Steam selbst mit
            "desc": {
                "de": ("Automatische Empfehlung — Steams Standard-Proton, für "
                       "dieses Spiel noch nicht von uns getestet."),
                "en": ("Automatic recommendation — Steam's default Proton, not "
                       "yet tested by us for this game."),
            },
        }
    ge = {
        "version": "Proton-GE",
        "role": "alternative_ge",
        "protonplus_runner": "proton-ge",
        "desc": {
            "de": ("Universelle Alternative für alle Systeme — empfohlen, falls "
                   "es zu Problemen mit In-Game-Videos oder Audio-Codecs kommt "
                   "(GE bringt zusätzliche Media-Codecs mit)."),
            "en": ("Universal alternative for all systems — recommended if you "
                   "run into problems with in-game videos or audio codecs "
                   "(GE ships extra media codecs)."),
        },
    }
    return [primary, ge]


# --------------------------------------------------------------------------- #
#  Spiel-Coverbild aus dem lokalen Steam-Cache
# --------------------------------------------------------------------------- #
def find_game_cover(appid):
    """
    Pfad zum vertikalen Coverbild (Library-Capsule 600x900) eines Spiels aus
    dem lokalen Steam-Cache — kein Download nötig, Steam hat die Bilder schon.
    Sucht in allen Steam-Wurzeln (nativ + Flatpak):
      * neues Layout : appcache/librarycache/<appid>/library_600x900.jpg
      * altes Layout : appcache/librarycache/<appid>_library_600x900.jpg
      * eigenes Grid : userdata/<uid>/config/grid/<appid>p.{png,jpg}
    Fallback auf das Querformat (header/library_hero), wenn kein Hochkant-
    Cover da ist. Rückgabe: Pfad oder None.
    """
    portrait_names = ["library_600x900.jpg", "library_600x900_2x.jpg"]
    landscape_names = ["header.jpg", "library_hero.jpg"]

    for root in venv.steam_data_roots():
        cache = os.path.join(root, "appcache", "librarycache")
        # Neues Layout: Unterordner pro AppID
        sub = os.path.join(cache, str(appid))
        if os.path.isdir(sub):
            for name in portrait_names + landscape_names:
                p = os.path.join(sub, name)
                if os.path.isfile(p):
                    return p
        # Altes Layout: flache Dateien mit AppID-Präfix
        for name in portrait_names + landscape_names:
            p = os.path.join(cache, f"{appid}_{name}")
            if os.path.isfile(p):
                return p
        # Vom Nutzer gesetztes Custom-Artwork (Steam-Grid)
        userdata = os.path.join(root, "userdata")
        if os.path.isdir(userdata):
            try:
                for uid in os.listdir(userdata):
                    grid = os.path.join(userdata, uid, "config", "grid")
                    for ext in ("png", "jpg", "jpeg"):
                        p = os.path.join(grid, f"{appid}p.{ext}")
                        if os.path.isfile(p):
                            return p
            except Exception:
                pass
    return None


# --------------------------------------------------------------------------- #
#  ProtonPlus-Erkennung + CLI-Befehl
# --------------------------------------------------------------------------- #
def find_protonplus():
    """
    Rückgabe: Befehls-Präfix (Liste) für die ProtonPlus-CLI oder None.
      nativ (AUR/COPR): ["protonplus"]
      Flatpak:          ["flatpak", "run", "com.vysp3r.ProtonPlus"]
    """
    if shutil.which("protonplus"):
        return ["protonplus"]
    base = os.path.join(HOME, ".var/app", PROTONPLUS_FLATPAK_ID)
    if shutil.which("flatpak") and os.path.isdir(base):
        return ["flatpak", "run", PROTONPLUS_FLATPAK_ID]
    return None


def protonplus_launcher_id():
    """
    launcher_id für die ProtonPlus-CLI (Schema: '<launcher>-<installart>').
    Flatpak-Steam -> 'steam-flatpak', sonst 'steam-system'.
    """
    return "steam-flatpak" if venv.steam_is_flatpak() else "steam-system"


def protonplus_install_cmd(runner_id):
    """
    Kompletter CLI-Befehl (Liste) für die interaktive Installation eines
    Runners, z. B.: protonplus install steam-system proton-ge-rtsp
    (Ohne 'latest' zeigt ProtonPlus im Terminal eine Versionsauswahl —
    dort wählt der Nutzer die empfohlene Version aus.)
    Rückgabe: None, wenn ProtonPlus nicht installiert ist.
    """
    pp = find_protonplus()
    if not pp or not runner_id:
        return None
    return pp + ["install", protonplus_launcher_id(), runner_id]


# --------------------------------------------------------------------------- #
#  Steam-Integration: Proton setzen ("Use") + Spiel starten ("Play")
# --------------------------------------------------------------------------- #
# Ein Spiel per CLI mit einer BESTIMMTEN Proton-Version und Startparametern
# zu starten geht nur über Steams eigene Konfiguration (gleicher Weg wie
# ProtonPlus/ProtonUp-Qt):
#   * Proton-Version : config/config.vdf        -> CompatToolMapping
#   * Startparameter : userdata/<uid>/config/localconfig.vdf -> LaunchOptions
# Danach reicht ein `steam -applaunch <appid>`. Läuft Steam gerade, greifen
# die Änderungen erst nach einem Steam-Neustart (Steam überschreibt seine
# VDFs beim Beenden) — die UI weist darauf hin. Vor jedem Schreiben wird
# eine .bak-Sicherung mit Zeitstempel angelegt.

def _vdf_find_block(text, key, start=0, end=None):
    """
    Findet den Block  "key" { ... }  ab Position start (case-insensitive).
    Rückgabe: (open_brace_idx, close_brace_idx) oder None.
    """
    if end is None:
        end = len(text)
    m = re.search(r'"%s"\s*\{' % re.escape(key), text[start:end], re.IGNORECASE)
    if not m:
        return None
    open_i = start + m.end() - 1
    depth = 0
    for i in range(open_i, end):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return (open_i, i)
    return None


def _vdf_descend(text, keys):
    """Steigt verschachtelt durch die Blöcke (z. B. Software>Valve>Steam).
    Rückgabe: (open_idx, close_idx) des letzten Blocks oder None."""
    start, end = 0, len(text)
    span = None
    for key in keys:
        span = _vdf_find_block(text, key, start, end)
        if span is None:
            return None
        start, end = span[0] + 1, span[1]
    return span


def _vdf_escape(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _vdf_set_string(text, block_span, key, value):
    """Setzt "key" "value" innerhalb eines Blocks (ersetzen oder einfügen)."""
    o, c = block_span
    inner = text[o + 1:c]
    pat = re.compile(r'("%s"\s*")((?:[^"\\]|\\.)*)(")' % re.escape(key), re.IGNORECASE)
    m = pat.search(inner)
    esc = _vdf_escape(value)
    if m:
        new_inner = inner[:m.start(2)] + esc + inner[m.end(2):]
    else:
        new_inner = f'\n\t"{key}"\t\t"{esc}"' + inner
    return text[:o + 1] + new_inner + text[c:]


def _backup_file(path):
    try:
        stamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(path, f"{path}.bak.{stamp}")
    except Exception:
        pass


def steam_is_running():
    """True, wenn ein Steam-Client-Prozess läuft (Änderungen an den VDFs
    greifen dann erst nach einem Steam-Neustart)."""
    try:
        r = subprocess.run(["pgrep", "-x", "steam"], capture_output=True)
        return r.returncode == 0
    except Exception:
        return False


def compat_tools_dirs():
    """Alle compatibilitytools.d-Verzeichnisse (dort liegen GE, RTSP, CachyOS...)."""
    dirs = []
    for root in venv.steam_data_roots():
        d = os.path.join(root, "compatibilitytools.d")
        if os.path.isdir(d):
            dirs.append(d)
    return dirs


def _natural_key(name):
    return tuple(int(n) for n in re.findall(r"\d+", name))


# Welche Ordner-Präfixe in compatibilitytools.d zu welchem Runner gehören
_TOOL_PREFIXES = {
    "proton-ge":      ["GE-Proton", "Proton-GE"],
    "proton-cachyos": ["proton-cachyos", "Proton-CachyOS"],
    "proton-ge-rtsp": ["proton-rtsp", "GE-Proton-RTSP", "proton-ge-rtsp"],
}


def resolve_steam_tool(proton):
    """
    Übersetzt einen Proton-Eintrag in den Tool-Namen für Steams
    CompatToolMapping (= Ordnername in compatibilitytools.d).
    Rückgabe: (tool_name_oder_None, gefunden: bool, art: str)
      tool None + gefunden True  -> Steam-Standard (Mapping entfernen)
      gefunden False             -> Version nicht installiert
    """
    runner = proton.get("protonplus_runner")
    if runner is None:
        # Valves Proton / "Proton 11 (Standard)": bringt Steam selbst mit ->
        # Mapping entfernen, Steam nutzt seinen Standard.
        return None, True, "steam_default"

    version = proton.get("version", "")
    # 1) Exakter Ordner (kuratierte Profile nennen den Ordnernamen direkt)
    for d in compat_tools_dirs():
        if version and os.path.isdir(os.path.join(d, version)):
            return version, True, "exact"
    # 2) Präfix-Suche (dynamische Einträge wie "Proton-GE"): neueste Version
    candidates = []
    for d in compat_tools_dirs():
        try:
            for name in os.listdir(d):
                if not os.path.isdir(os.path.join(d, name)):
                    continue
                for pref in _TOOL_PREFIXES.get(runner, [version]):
                    if pref and name.lower().startswith(pref.lower()):
                        candidates.append(name)
                        break
        except Exception:
            continue
    if candidates:
        candidates.sort(key=_natural_key)
        return candidates[-1], True, "prefix"
    return None, False, "not_installed"


def _config_vdf_path():
    for root in venv.steam_data_roots():
        p = os.path.join(root, "config", "config.vdf")
        if os.path.isfile(p):
            return p
    return None


def set_steam_compat_tool(appid, tool_name):
    """
    Setzt (oder entfernt bei tool_name=None) die Proton-Version eines Spiels
    in Steams config.vdf -> CompatToolMapping. Gleicher Mechanismus wie in
    ProtonPlus/ProtonUp-Qt. Rückgabe: (ok: bool, fehlertext: str)
    """
    appid = str(appid)
    path = _config_vdf_path()
    if not path:
        return False, "config.vdf nicht gefunden"
    try:
        with open(path, "r", errors="ignore") as f:
            text = f.read()

        steam_span = (_vdf_descend(text, ["InstallConfigStore", "Software", "Valve", "Steam"])
                      or _vdf_descend(text, ["Software", "Valve", "Steam"]))
        if steam_span is None:
            return False, "Steam-Block in config.vdf nicht gefunden"

        mapping = _vdf_find_block(text, "CompatToolMapping",
                                  steam_span[0] + 1, steam_span[1])
        if mapping is None:
            if tool_name is None:
                return True, ""     # nichts zu entfernen
            insert = ('\n\t\t\t\t"CompatToolMapping"\n\t\t\t\t{\n\t\t\t\t}')
            text = text[:steam_span[0] + 1] + insert + text[steam_span[0] + 1:]
            steam_span = (_vdf_descend(text, ["InstallConfigStore", "Software", "Valve", "Steam"])
                          or _vdf_descend(text, ["Software", "Valve", "Steam"]))
            mapping = _vdf_find_block(text, "CompatToolMapping",
                                      steam_span[0] + 1, steam_span[1])

        app_span = _vdf_find_block(text, appid, mapping[0] + 1, mapping[1])

        if tool_name is None:
            # Eintrag entfernen -> Steam-Standard
            if app_span:
                pre = text.rfind('"%s"' % appid, mapping[0], app_span[0])
                text = text[:pre].rstrip("\t") + text[app_span[1] + 1:]
        elif app_span:
            text = _vdf_set_string(text, app_span, "name", tool_name)
        else:
            block = ('\n\t\t\t\t\t"%s"\n\t\t\t\t\t{\n'
                     '\t\t\t\t\t\t"name"\t\t"%s"\n'
                     '\t\t\t\t\t\t"config"\t\t""\n'
                     '\t\t\t\t\t\t"priority"\t\t"250"\n'
                     '\t\t\t\t\t}' % (appid, _vdf_escape(tool_name)))
            text = text[:mapping[0] + 1] + block + text[mapping[0] + 1:]

        _backup_file(path)
        with open(path, "w") as f:
            f.write(text)
        return True, ""
    except Exception as e:
        return False, str(e)


def set_steam_launch_options(appid, options):
    """
    Schreibt die Startparameter eines Spiels in ALLE gefundenen
    localconfig.vdf (userdata/<uid>/config) -> apps/<appid>/LaunchOptions.
    Rückgabe: (ok: bool, fehlertext: str) — ok, wenn mindestens eine
    Datei geschrieben wurde.
    """
    appid = str(appid)
    wrote, last_err = False, "localconfig.vdf nicht gefunden"
    for root in venv.steam_data_roots():
        userdata = os.path.join(root, "userdata")
        if not os.path.isdir(userdata):
            continue
        try:
            uids = os.listdir(userdata)
        except Exception:
            continue
        for uid in uids:
            path = os.path.join(userdata, uid, "config", "localconfig.vdf")
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "r", errors="ignore") as f:
                    text = f.read()
                apps = (_vdf_descend(text, ["UserLocalConfigStore", "Software",
                                            "Valve", "Steam", "apps"])
                        or _vdf_descend(text, ["Software", "Valve", "Steam", "apps"]))
                if apps is None:
                    last_err = "apps-Block nicht gefunden"
                    continue
                app_span = _vdf_find_block(text, appid, apps[0] + 1, apps[1])
                if app_span:
                    text = _vdf_set_string(text, app_span, "LaunchOptions", options)
                else:
                    block = ('\n\t\t\t\t\t"%s"\n\t\t\t\t\t{\n'
                             '\t\t\t\t\t\t"LaunchOptions"\t\t"%s"\n'
                             '\t\t\t\t\t}' % (appid, _vdf_escape(options)))
                    text = text[:apps[0] + 1] + block + text[apps[0] + 1:]
                _backup_file(path)
                with open(path, "w") as f:
                    f.write(text)
                wrote = True
            except Exception as e:
                last_err = str(e)
    return (True, "") if wrote else (False, last_err)


def steam_launch_cmd(appid):
    """Befehl (Liste), um ein Spiel über den Steam-Client zu starten."""
    appid = str(appid)
    if shutil.which("steam"):
        return ["steam", "-applaunch", appid]
    if venv.steam_is_flatpak() and shutil.which("flatpak"):
        return ["flatpak", "run", "com.valvesoftware.Steam", "-applaunch", appid]
    if shutil.which("xdg-open"):
        return ["xdg-open", f"steam://rungameid/{appid}"]
    return None


# --------------------------------------------------------------------------- #
#  Gemerkte Proton-Auswahl pro Spiel ("Use"-Button)
# --------------------------------------------------------------------------- #
def load_selected_protons():
    """{appid: version} — die per 'Use' gewählte Version je Spiel."""
    data = _load_app_config().get("games_selected_proton", {})
    return {str(k): v for k, v in data.items()} if isinstance(data, dict) else {}


def save_selected_proton(appid, version):
    """Merkt die per 'Use' gewählte Version dauerhaft in der App-Config."""
    try:
        data = _load_app_config()
        sel = data.get("games_selected_proton", {})
        if not isinstance(sel, dict):
            sel = {}
        sel[str(appid)] = version
        data["games_selected_proton"] = sel
        os.makedirs(os.path.dirname(APP_CONFIG), exist_ok=True)
        with open(APP_CONFIG, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[Games] Konnte Proton-Auswahl nicht speichern: {e}")


# --------------------------------------------------------------------------- #
#  Startparameter-Toggles (+ eigene Parameter)
# --------------------------------------------------------------------------- #
# Optionale Zusatz-Parameter, die im Spiel-Panel per Schalter zugeschaltet
# werden. Entscheidend ist die POSITION relativ zu %command%:
#
#   position "before" -> Wrapper, der Steam's Befehl umschließt und deshalb
#                        VOR %command% stehen muss (z. B. mullvad-exclude,
#                        genau wie gamemoderun).
#   position "after"  -> Argument, das an das SPIEL geht und deshalb HINTER
#                        %command% stehen muss (z. B. --force-openxr).
#
# Ein neuer Schalter braucht nur einen weiteren Eintrag hier — Panel,
# Zusammenbau und Speicherung ziehen automatisch nach. Die Beschriftungen
# kommen über tr("games_toggle_<key>") aus translations.py.
LAUNCH_TOGGLES = [
    {
        "key": "force_openxr",
        "arg": "--force-openxr",
        "position": "after",
    },
    {
        "key": "mullvad_exclude",
        "arg": "mullvad-exclude",
        "position": "before",
    },
]

COMMAND_TOKEN = "%command%"


def _split_command(text):
    """Zerlegt einen Parameter-String in (Teile vor %command%, Teile danach).
    Fehlt %command%, gilt alles als Argument HINTER dem Befehl."""
    prefix, sep, suffix = (text or "").partition(COMMAND_TOKEN)
    if not sep:
        return [], (text or "").split()
    return prefix.split(), suffix.split()


def compose_launch_options(base, enabled_keys, custom=""):
    """
    Baut den finalen Steam-Startparameter-String aus:
      base         : hinterlegte Parameter des Spiels (z. B. VRChat) oder ""
      enabled_keys : Menge/Liste der aktiven Toggle-Keys
      custom       : eigene Zusatz-Parameter des Nutzers

    Wrapper landen vor %command%, Spiel-Argumente dahinter — egal in welcher
    Reihenfolge sie zugeschaltet werden. Doppelte Parameter werden vermieden.
    Enthält 'custom' selbst ein %command%, wird es korrekt auf beide Seiten
    aufgeteilt (so lassen sich auch eigene Wrapper wie 'mangohud' setzen).
    """
    enabled = set(enabled_keys or ())
    prefix, suffix = _split_command(base)

    for t in LAUNCH_TOGGLES:
        if t["key"] not in enabled:
            continue
        target = prefix if t["position"] == "before" else suffix
        if t["arg"] not in target:
            target.append(t["arg"])

    custom = (custom or "").strip()
    if custom:
        c_prefix, c_suffix = _split_command(custom)
        for p in c_prefix:
            if p not in prefix:
                prefix.append(p)
        for s in c_suffix:
            if s not in suffix:
                suffix.append(s)

    return " ".join(prefix + [COMMAND_TOKEN] + suffix)


def load_launch_toggles(appid):
    """
    Gemerkte Einstellung eines Spiels.
    Rückgabe: (aktive_toggle_keys: list, custom: str)
    """
    data = _load_app_config().get("games_launch_toggles", {})
    entry = data.get(str(appid), {}) if isinstance(data, dict) else {}
    if not isinstance(entry, dict):
        return [], ""
    keys = [k for k in entry.get("toggles", [])
            if any(t["key"] == k for t in LAUNCH_TOGGLES)]
    return keys, entry.get("custom", "") or ""


def save_launch_toggles(appid, enabled_keys, custom):
    """Merkt Toggles + eigene Parameter eines Spiels dauerhaft in der Config."""
    try:
        data = _load_app_config()
        all_t = data.get("games_launch_toggles", {})
        if not isinstance(all_t, dict):
            all_t = {}
        all_t[str(appid)] = {"toggles": list(enabled_keys),
                             "custom": (custom or "").strip()}
        data["games_launch_toggles"] = all_t
        os.makedirs(os.path.dirname(APP_CONFIG), exist_ok=True)
        with open(APP_CONFIG, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[Games] Konnte Startparameter-Toggles nicht speichern: {e}")
