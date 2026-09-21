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

import glob
import os
import re
import json
import shlex
import shutil
import subprocess

import vr_environment as venv
import steam_appinfo
import steam_shortcuts

from logging_setup import get_logger
from jsonio import update_json
import proc

log = get_logger("games")


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


def game(name, protons, launch_params=None, fixes=None, toggles=None, default_on=None):
    """Ein Eintrag für die GAMES-Tabelle.

    toggles     : Spiel-eigene Zusatz-Schalter (zusätzlich zu den globalen
                  LAUNCH_TOGGLES), z. B. VRChats --enable-hw-video-decoding.
                  Jeder Eintrag über game_toggle(...) gebaut.
    default_on  : Liste von Toggle-Keys (global ODER spiel-eigen), die beim
                  ERSTEN Öffnen des Spiels vorausgewählt sind — solange der
                  Nutzer nichts anderes gespeichert hat. Danach kann er sie
                  ganz normal ab-/anschalten (z. B. gamemoderun bei VRChat).
    """
    return {
        "name": name,
        "protons": protons,
        "launch_params": launch_params or {},
        "fixes": fixes or [],
        "toggles": toggles or [],
        "default_on": list(default_on or []),
    }


def game_toggle(key, arg, position="after", default=False):
    """Ein spiel-spezifischer Startparameter-Schalter (wie LAUNCH_TOGGLES).
      position "before" -> Wrapper (vor %command%), "after" -> Spiel-Argument,
                           "wrap"   -> umschliesst die ganze restliche Zeile
                                       (endet auf '--', danach folgt alles
                                       Weitere als Argumentliste)
      default           -> beim ersten Oeffnen des Spiels bereits an.
    Beschriftung/Tooltip kommen ueber tr("games_toggle_<key>") / _tip.
    """
    return {"key": key, "arg": arg, "position": position, "default": default}


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
# --------------------------------------------------------------------------- #
#  Spiele-Datenbank aus config/games.json (JSON = Datenquelle)
# --------------------------------------------------------------------------- #
# Die getesteten Spiele stehen jetzt in config/games.json (leicht editier- und
# per Update-Button aktualisierbar). Diese Datei wird eingelesen und in exakt
# die interne Struktur übersetzt, die der Rest der App schon nutzt (protons-
# Liste mit role/version/protonplus_runner/desc, launch_params amd/nvidia,
# fixes, toggles, default_on) — die restliche UI-Logik bleibt unverändert.
#
# Reihenfolge der Quellen (höchste info.version gewinnt):
#   1. ~/.config/yakuda-connect/config/games.json  (heruntergeladenes Update)
#   2. <App-Ordner>/config/games.json              (mitgeliefert)

APP_DIR             = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES_JSON_BUNDLED  = os.path.join(APP_DIR, "config", "games.json")
GAMES_JSON_USER     = os.path.join(HOME, ".config/yakuda-connect/config/games.json")
GAMES_JSON_REMOTE   = ("https://raw.githubusercontent.com/yakuda-stack/"
                       "yakuda-connect/main/config/games.json")


def _ver_tuple(v):
    """'1.2.10' -> (1, 2, 10). Für Versionsvergleiche der games.json."""
    parts = re.findall(r"\d+", str(v or "0"))
    return tuple(int(x) for x in parts) if parts else (0,)


def _read_json_file(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _infer_protonplus_runner(version):
    """Leitet aus dem Versionsnamen den ProtonPlus-Runner ab (für Install/Use
    per Klick). None = Steams eingebautes Proton (bringt Steam selbst mit)."""
    s = (version or "").lower()
    if "cachyos" in s:
        return "proton-cachyos"
    if "rtsp" in s:
        return "proton-ge-rtsp"
    if "ge" in s:                       # "Proton-GE"
        return "proton-ge"
    return None                          # Valve / "Proton 11"


def _norm_desc(desc):
    """desc darf String (für beide Sprachen) ODER {'de':..,'en':..} sein."""
    if isinstance(desc, dict):
        de = desc.get("de", "") or desc.get("en", "")
        en = desc.get("en", "") or de
        return {"de": de, "en": en}
    return {"de": desc or "", "en": desc or ""}


def _proton_entry(pv_map, pd_map, key, role, desc=None, cachyos_only=False,
                  hide_on_cachyos=False, meta=None):
    version = pv_map.get(key, key)
    meta = meta or {}
    # Beschreibung: per-Spiel-Override (desc) hat Vorrang, sonst die zentrale
    # Standardbeschreibung der Proton-Version aus proton_descriptions.
    if not desc:
        desc = pd_map.get(key, "")

    # ProtonPlus-Runner: ein EXPLIZITER Eintrag in proton_versions gewinnt,
    # auch wenn er null ist. Deshalb "key in meta" statt meta.get(...) —
    # null ("kommt nicht ueber ProtonPlus") und "nicht angegeben" (ableiten)
    # sind zwei verschiedene Aussagen, die ein .get() zusammenwerfen wuerde.
    # Ohne diese Unterscheidung bekaeme Proton-RTSP-Wayland-GE von
    # _infer_protonplus_runner() faelschlich "proton-ge-rtsp" verpasst
    # (der Name enthaelt "rtsp") und der Install-Knopf wuerde etwas ganz
    # anderes installieren als die Karte verspricht.
    if "protonplus_runner" in meta:
        runner = meta.get("protonplus_runner")
    else:
        runner = _infer_protonplus_runner(version)

    entry = {
        "version": version,
        "role": role,
        "protonplus_runner": runner,
        "desc": _norm_desc(desc),
    }
    # Manuell installierbare Builds (nicht in AUR/ProtonPlus): Ordner-Praefix
    # zum Erkennen + URLs fuer den Download-Knopf an der Karte.
    for field in ("tool_prefix", "download_url", "checksum_url",
                  "release_url", "manual"):
        if meta.get(field):
            entry[field] = meta[field]
    if cachyos_only:
        # Nur auf CachyOS anzeigen (Nicht-CachyOS sieht nur Default + Alternative).
        entry["cachyos_only"] = True
    if hide_on_cachyos:
        entry["hide_on_cachyos"] = True
    return entry


def build_games_from_config(cfg):
    """Übersetzt eine games.json in die interne GAMES-Struktur."""
    if not isinstance(cfg, dict):
        return {}
    pv_raw = cfg.get("proton_versions", {}) or {}
    pv = {k: (v if isinstance(v, str) else (v or {}).get("version", ""))
          for k, v in pv_raw.items()}
    # Die dict-Form eines proton_versions-Eintrags darf ausser "version" noch
    # Metadaten tragen (tool_prefix, protonplus_runner, download_url, ...).
    # Die gehoeren an die VERSION, nicht ans Spiel: dieselbe Proton-Version
    # wird bei mehreren Spielen eingetragen und muesste sonst mehrfach
    # gepflegt werden.
    pv_meta = {k: (v if isinstance(v, dict) else {}) for k, v in pv_raw.items()}
    # Zentrale Standardbeschreibungen der Proton-Versionen (per-Spiel überschreibbar).
    pd = cfg.get("proton_descriptions", {}) or {}
    # Zentrales Bild-Template ({appid} wird ersetzt); per-Spiel via "picture" überschreibbar.
    pic_tmpl = cfg.get("picture_template", "") or ""

    out = {}
    for appid, g in (cfg.get("games", {}) or {}).items():
        appid = str(appid)
        p = g.get("proton", {}) or {}
        protons = []
        # Empfiehlt ein Spiel auf CachyOS DIESELBE Version wie ueberall sonst
        # (bei VRChat seit 1.1.9 der Fall: RTSP-Proton, weil proton-cachyos die
        # MediaFoundation-Patches fuer AVPro nicht hat), stuende sie doppelt in
        # der Liste. Der Default-Eintrag wird auf CachyOS dann ausgeblendet —
        # sichtbar bleibt der main_cachyos-Eintrag, der dort auch das
        # "Empfohlen"-Badge traegt.
        same_on_cachyos = bool(p.get("cachyos")) and p.get("cachyos") == p.get("default")

        if p.get("cachyos"):
            protons.append(_proton_entry(pv, pd, p["cachyos"], "main_cachyos",
                                         p.get("cachyos_desc"), cachyos_only=True,
                                         meta=pv_meta.get(p["cachyos"])))
        if p.get("default"):
            protons.append(_proton_entry(pv, pd, p["default"], "main",
                                         p.get("default_desc"),
                                         hide_on_cachyos=same_on_cachyos,
                                         meta=pv_meta.get(p["default"])))
        # Die Alternative wird NUR ausgeblendet, wenn es fuer genau diesen
        # Slot ein CachyOS-Gegenstueck gibt. Frueher stand hier
        # bool(p.get("alternative_cachyos")) — was zufaellig richtig war,
        # solange es nur einen Zusatz-Slot gab. Mit dem "safe"-Slot darunter
        # waere es falsch geworden: ein safe_cachyos-Eintrag haette die
        # Alternative auf CachyOS mit verschwinden lassen.
        if p.get("alternative"):
            protons.append(_proton_entry(pv, pd, p["alternative"], "alternative",
                                         p.get("alt_desc"),
                                         hide_on_cachyos=bool(p.get("alternative_cachyos")),
                                         meta=pv_meta.get(p["alternative"])))
        # Optionale eigene Alternative fuer CachyOS: dort ist die
        # "Performance statt Kompatibilitaet"-Option proton-cachyos, nicht
        # Valves Proton. Ohne diesen Slot muesste man sich fuer einen der
        # beiden entscheiden und der jeweils andere Nutzerkreis saehe Unsinn.
        if p.get("alternative_cachyos"):
            protons.append(_proton_entry(pv, pd, p["alternative_cachyos"], "alternative",
                                         p.get("alt_cachyos_desc"), cachyos_only=True,
                                         meta=pv_meta.get(p["alternative_cachyos"])))
        # Dritter Slot "safe": die risikoarme Wahl OHNE Video-/Codec-Extras.
        # Bewusst getrennt von "alternative": bei VRChat ist die Alternative
        # ein zweiter Medien-Build (RTSP), waehrend "safe" gerade der Verzicht
        # darauf ist. Beide in einen Slot zu quetschen haette bedeutet, dem
        # Nutzer zwei gegensaetzliche Empfehlungen unter einem Label zu zeigen.
        if p.get("safe"):
            protons.append(_proton_entry(pv, pd, p["safe"], "safe",
                                         p.get("safe_desc"),
                                         hide_on_cachyos=bool(p.get("safe_cachyos")),
                                         meta=pv_meta.get(p["safe"])))
        if p.get("safe_cachyos"):
            protons.append(_proton_entry(pv, pd, p["safe_cachyos"], "safe",
                                         p.get("safe_cachyos_desc"), cachyos_only=True,
                                         meta=pv_meta.get(p["safe_cachyos"])))

        launch = {}
        if g.get("amd_start") or g.get("nvidia_start"):
            amd = g.get("amd_start") or g.get("nvidia_start")
            nv  = g.get("nvidia_start") or g.get("amd_start")
            launch = {"amd": amd, "nvidia": nv}

        toggles = []
        if g.get("toggle_enable_hardware_decoding"):
            toggles.append(game_toggle("vrc_hw_video_decoding",
                                       "--enable-hw-video-decoding",
                                       position="after", default=True))
        if g.get("toggle_proton_log"):
            # Umgebungsvariable, kein Spiel-Argument -> muss VOR %command%
            # stehen. Schreibt ~/steam-<appid>.log mit den Wine-/GStreamer-
            # Meldungen; die einzige Stelle, an der man sieht, WORAN ein
            # Videoplayer scheitert. Standardmaessig aus, weil das Log bei
            # laengeren Sitzungen schnell dreistellige MB erreicht.
            toggles.append(game_toggle("proton_log", "PROTON_LOG=1",
                                       position="before", default=False))
        if g.get("toggle_proton_use_wayland"):
            # Umgebungsvariable wie PROTON_LOG -> muss VOR %command% stehen.
            # Schaltet den nativen Wayland-Pfad eines Proton-Builds ein, der
            # ihn mitbringt (Proton-RTSP-Wayland-GE). Builds ohne die
            # WineWayland-Patches ignorieren die Variable einfach, der
            # Schalter kann dort also nichts kaputtmachen — er bringt nur
            # nichts.
            toggles.append(game_toggle("proton_use_wayland",
                                       "PROTON_USE_WAYLAND=1",
                                       position="before", default=False))
        if g.get("toggle_vrcvideocacher"):
            # Startet VRCVideoCacher zusammen mit dem Spiel und beendet es
            # wieder mit. Der Befehl bleibt hier LEER und wird erst in
            # resolved_toggles() gefuellt: diese Tabelle entsteht beim Import,
            # da waere ein einmal gesuchter Pfad fuer die ganze Laufzeit
            # eingefroren. So genuegt es, das Panel neu zu oeffnen, nachdem
            # man VRCVideoCacher installiert hat.
            toggles.append(game_toggle("vrcvideocacher", "",
                                       position="wrap", default=False))
        default_on = []
        if g.get("toggle_gamemoderun"):
            default_on.append("gamemoderun")

        picture = g.get("picture") or (pic_tmpl.format(appid=appid) if pic_tmpl else "")

        out[appid] = {
            "name": g.get("name", appid),
            "picture": picture,
            "protons": protons,
            "launch_params": launch,
            "fixes": g.get("fixes", []) or [],
            "toggles": toggles,
            "default_on": default_on,
        }
    return out


def load_games_config():
    """Liest die beste verfügbare games.json (höchste info.version gewinnt,
    Gleichstand -> User-Kopie)."""
    best = None
    for path in (GAMES_JSON_BUNDLED, GAMES_JSON_USER):   # User zuletzt -> gewinnt Gleichstand
        c = _read_json_file(path)
        if not isinstance(c, dict):
            continue
        if (best is None or
                _ver_tuple((c.get("info", {}) or {}).get("version")) >=
                _ver_tuple((best.get("info", {}) or {}).get("version"))):
            best = c
    return best or {}


GAMES_CONFIG = load_games_config()
GAMES = build_games_from_config(GAMES_CONFIG)


def reload_games_config():
    """games.json neu einlesen und GAMES neu aufbauen (nach einem Update)."""
    global GAMES_CONFIG, GAMES
    GAMES_CONFIG = load_games_config()
    GAMES = build_games_from_config(GAMES_CONFIG)
    return GAMES


def games_config_version():
    """Version der aktuell geladenen games.json (z. B. '1.0.0')."""
    return (GAMES_CONFIG.get("info", {}) or {}).get("version", "0.0.0")


def fetch_remote_games_config(timeout=8):
    """Lädt die entfernte games.json (Rohtext, geparste Config). Netzwerk!"""
    import urllib.request
    req = urllib.request.Request(GAMES_JSON_REMOTE,
                                 headers={"User-Agent": "yakuda-connect"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8")
    return raw, json.loads(raw)          # json.loads validiert gleich mit


def remote_games_update_available(timeout=8):
    """(update_verfügbar: bool, remote_version: str). Im Worker aufrufen."""
    try:
        _, cfg = fetch_remote_games_config(timeout)
        rv = (cfg.get("info", {}) or {}).get("version", "0.0.0")
        return (_ver_tuple(rv) > _ver_tuple(games_config_version()), rv)
    except Exception:
        return (False, "")


def apply_remote_games_config(raw_text):
    """Speichert eine (bereits geladene) games.json in den User-Config-Ordner
    und lädt sie neu ein. Wirft bei ungültigem JSON. Rückgabe: neue Version."""
    json.loads(raw_text)                 # muss valide sein
    os.makedirs(os.path.dirname(GAMES_JSON_USER), exist_ok=True)
    with open(GAMES_JSON_USER, "w", encoding="utf-8") as f:
        f.write(raw_text)
    reload_games_config()
    return games_config_version()

# --------------------------------------------------------------------------- #
#  VRCVideoCacher (Steam-AppID 4296960) — Autostart zusammen mit VRChat
# --------------------------------------------------------------------------- #
# VRCVideoCacher ersetzt VRChats abgespecktes yt-dlp beim Start durch ein
# vollwertiges und stellt es beim Beenden wieder her. Damit das greift, muss
# es LAUFEN, bevor VRChat ein Video anfordert. Statt es jedes Mal von Hand zu
# starten, haengen wir es an VRChats Startparameter.
VRCVIDEOCACHER_APPID = "4296960"


def find_vrcvideocacher():
    """Pfad zur VRCVideoCacher-Binary oder "" wenn nicht gefunden.

    Gesucht wird in dieser Reihenfolge:
      1. Eigene Installation (Knopf "Videoplayer Fix" -> Installieren)
      2. PATH             (manuelle Installation, z. B. ~/.bin)
      3. Steam-Bibliotheken (steamapps/common/VRCVideoCacher)

    Die eigene Installation zuerst: hat der Nutzer sie ueber die App
    eingerichtet, ist das die Fassung, die die App auch aktuell haelt.

    Der gefundene Pfad wird fest in die Startparameter geschrieben. Das ist
    Absicht: die Startparameter sind ein statischer Text in Steams Config,
    dort kann nichts zur Laufzeit nachschauen. Verschiebt der Nutzer das
    Programm, muss der Schalter einmal aus- und wieder eingeschaltet werden —
    der Tooltip sagt das.
    """
    from shutil import which
    try:
        import vrcvideocacher_install as vci
        if vci.is_installed():
            return vci.BINARY_PATH
    except Exception:
        pass

    found = which("VRCVideoCacher")
    if found:
        return found

    for sa in _steamapps_dirs():
        for name in ("VRCVideoCacher/VRCVideoCacher",
                     "VRCVideoCacher/VRCVideoCacher.exe"):
            path = os.path.join(sa, "common", name)
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
    return ""


# Gefundener VRCVideoCacher-Pfad, gemerkt fuer die Laufzeit des Panels.
# Ohne den Cache wuerde bei JEDEM Tastendruck im Feld fuer eigene Parameter
# erneut die PATH-Suche und das Einlesen aller libraryfolders.vdf anlaufen —
# _update_final_params haengt an textEdited.
_VC_PATH_CACHE = None


def refresh_vrcvideocacher_path():
    """Cache verwerfen. Aufrufen, wenn das Detailpanel neu aufgebaut wird —
    dann genuegt Panel zu, Panel auf, nachdem man das Programm installiert
    hat, statt die ganze App neu zu starten."""
    global _VC_PATH_CACHE
    _VC_PATH_CACHE = None


_LEGACY_WRAPPER_RE = re.compile(
    r"""bash\s+-c\s+'[^']*VRCVideoCacher[^']*'\s+--\s*""")


def strip_legacy_vrcvideocacher_wrapper(text):
    """Entfernt den Autostart-Wrapper aus v1.1.9-Vorabstaenden.

    Der Wrapper startete VRCVideoCacher ueber VRChats Startparameter. In der
    Praxis war das unzuverlaessig — Steams Quoting und das Zeitfenster, bis
    der yt-dlp-Austausch steht. Ersetzt wurde er durch einen Knopf im
    Dashboard.

    Wer den Schalter schon gesetzt hatte, hat den Wrapper aber in Steams
    Config stehen, und dort verschwindet er nicht von selbst: die
    Startparameter sind gespeicherter Text, kein Schalter, den wir einfach
    nicht mehr anbieten. Ohne diese Bereinigung startete VRChat weiterhin
    ueber den kaputten Wrapper — mit einem Programm, dessen Pfad womoeglich
    gar nicht mehr stimmt.
    """
    if not text or "VRCVideoCacher" not in text:
        return text
    return _LEGACY_WRAPPER_RE.sub("", text).strip()


def resolved_toggles(game):
    """Die Toggles eines Spiels mit zur Laufzeit aufgeloesten Befehlen.

    Aktuell hat kein Schalter einen dynamischen Befehl — der einzige, der
    einen hatte (VRCVideoCacher-Autostart), ist entfernt. Die Funktion
    bleibt als eine Stelle bestehen, an der solche Faelle behandelt werden,
    damit die UI nicht an zwei Orten zwischen game["toggles"] und einer
    aufgeloesten Fassung unterscheiden muss.
    """
    return list(game.get("toggles", []))


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
                with open(vdf, errors="ignore") as f:
                    content = f.read()
                # "path"  "/mnt/spiele/SteamLibrary"
                for m in re.finditer(r'"path"\s+"([^"]+)"', content):
                    extra = os.path.join(m.group(1), "steamapps")
                    if os.path.isdir(extra):
                        dirs.append(extra)
            except Exception as exc:
                log.debug("_steamapps_dirs: ignoriert — %s", exc)
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

# Zusätzlicher Filter über den NAMEN — fängt alle Proton-Versionen (auch neue
# wie "Proton 10.0", "Proton 9.0 (Beta)") und Steam-Runtimes ab, ohne dass man
# jede appid einzeln pflegen muss. Proton-Installationen enthalten OpenVR-
# Dateien und würden sonst als VR-"Spiel" im Games-Tab auftauchen.
_TOOL_NAME_RE = re.compile(
    r"^\s*("
    r"proton\s+(experimental|hotfix|next|\d|easyanticheat|battleye)"
    r"|steam\s+linux\s+runtime"
    r"|steamworks\s+common"
    r"|steamvr"
    r")",
    re.IGNORECASE,
)


def _is_steam_tool(name):
    """True für Proton-Versionen/Steam-Runtimes (keine echten Spiele)."""
    return bool(name and _TOOL_NAME_RE.match(name))

# Dateien, an denen wir ein VR-Spiel erkennen (OpenVR-/OpenXR-Loader im
# Installationsordner). Funktioniert komplett offline.
_VR_MARKER_FILES = {
    # OpenVR / SteamVR
    "openvr_api.dll", "libopenvr_api.so", "openvr_api64.dll",
    # OpenXR
    "openxr_loader.dll", "libopenxr_loader.so",
    # Unity XR-Plugins (manche Spiele liefern nur diese aus)
    "unityopenxr.dll", "libunityopenxr.so",
    "openvr_api.dll.meta", "unityopenvr.dll",
    # Oculus/Meta-Plugins (native Oculus-Spiele ohne OpenXR-Loader)
    "libovrplatform.so", "ovrplugin.dll", "libovrplugin.so",
}

# Bekannte Ablageorte des Loaders — werden ZUERST direkt geprüft (ohne Walk).
# Wichtig für Unreal Engine: dort liegt der Loader tief in Engine/Binaries/...,
# was ein flacher Walk niemals findet.
_VR_MARKER_GLOBS = [
    # Unreal Engine 4/5
    "Engine/Binaries/ThirdParty/OpenXR/*/openxr_loader.dll",
    "Engine/Binaries/ThirdParty/OpenXR/*/*/openxr_loader.dll",
    "Engine/Binaries/ThirdParty/OpenVR/*/*/openvr_api.dll",
    "Engine/Plugins/Runtime/OpenXR/*",
    "Engine/Plugins/Runtime/Oculus/*",
    "*/Binaries/Win64/openxr_loader.dll",
    "*/Plugins/*/Binaries/ThirdParty/OpenXR/*/openxr_loader.dll",
    # Unity
    "*_Data/Plugins/x86_64/openvr_api.dll",
    "*_Data/Plugins/x86_64/UnityOpenXR.dll",
    "*_Data/Plugins/x86_64/openxr_loader.dll",
    "*_Data/Plugins/openvr_api.dll",
    "*_Data/Plugins/x86_64/OVRPlugin.dll",
    # Godot / sonstige, die den Loader neben die Binary legen
    "openxr_loader.dll",
    "openvr_api.dll",
]

# Ordner, die beim Walk übersprungen werden: dort liegen nie Loader-Dateien,
# sie fressen aber das Scan-Budget auf (UE-'Content' hat gern 10.000+ Ordner).
_VR_SCAN_SKIP_DIRS = {
    "content", "contents", "saved", "intermediate", "derivedatacache",
    "streamingassets", "movies", "videos", "audio", "sounds", "music",
    "textures", "localization", "paks", "cache", "logs", "screenshots",
}

_VR_SCAN_MAX_DIRS = 6000   # großzügig: UE-Spiele haben sehr viele Ordner
_VR_SCAN_MAX_DEPTH = 7     # UE: Engine/Binaries/ThirdParty/OpenXR/win64/... = 5+


def _parse_acf(path):
    """Liest appid, name und installdir aus einer appmanifest_<id>.acf."""
    try:
        with open(path, errors="ignore") as f:
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


def _looks_like_vr_game(steamapps_dir, installdir, quick=False):
    """
    True, wenn der Installationsordner OpenVR-/OpenXR-Loader enthält.

    Zwei Stufen:
      1. Gezielte Prüfung bekannter Engine-Pfade (_VR_MARKER_GLOBS) — schnell
         und findet vor allem Unreal-Engine-Spiele, bei denen der Loader tief
         unter Engine/Binaries/ThirdParty/OpenXR/<platform>/ liegt.
      2. Fallback: begrenzter Walk. Uninteressante Riesenordner (Content, Saved,
         ...) werden übersprungen, damit das Budget für die Binaries reicht.

    ``quick=True`` laesst Stufe 2 aus — fuer Faelle, in denen die Dauer
    wichtiger ist als die Vollstaendigkeit. Im Scan selbst wird das nicht
    mehr gebraucht (dort faengt der Ergebnis-Cache die Dauer ab), der
    Schalter bleibt aber fuer Aufrufer, die schnell eine grobe Antwort
    wollen.
    """
    if not installdir:
        return False
    root = os.path.join(steamapps_dir, "common", installdir)
    if not os.path.isdir(root):
        return False

    # --- Stufe 1: bekannte Engine-Pfade direkt abklopfen ------------------- #
    for pattern in _VR_MARKER_GLOBS:
        try:
            if glob.glob(os.path.join(root, pattern)):
                return True
        except Exception as exc:
            log.debug("_looks_like_vr_game: ignoriert — %s", exc)

    if quick:
        return False

    # --- Stufe 2: begrenzter Walk als Fallback ---------------------------- #
    root_depth = root.rstrip(os.sep).count(os.sep)
    visited = 0
    try:
        for cur, dirs, files in os.walk(root):
            visited += 1
            if visited > _VR_SCAN_MAX_DIRS:
                break          # Budget alle -> abbrechen, aber NICHT als "kein VR"
                               # werten; Stufe 1 hat die üblichen Pfade schon geprüft.
            if cur.count(os.sep) - root_depth >= _VR_SCAN_MAX_DEPTH:
                dirs[:] = []   # nicht tiefer absteigen
            else:
                # Content-/Asset-Ordner überspringen: dort liegen nie Loader.
                dirs[:] = [d for d in dirs if d.lower() not in _VR_SCAN_SKIP_DIRS]
            for f in files:
                if f.lower() in _VR_MARKER_FILES:
                    return True
    except Exception as exc:
        log.debug("_looks_like_vr_game: ignoriert — %s", exc)
    return False


def installed_steam_apps():
    """
    Alle installierten Steam-Apps aus den appmanifest_<id>.acf.

    Rückgabe: Liste von {"appid", "name", "installdir", "steamapps"} —
    ohne Proton-Versionen und Steam-Runtimes, aber sonst ungefiltert.
    Doppelte AppIDs (dieselbe App in zwei Bibliotheken) erscheinen einmal.
    """
    apps = {}
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
            if appid in apps:
                continue
            if appid in _APPID_BLACKLIST or _is_steam_tool(info["name"]):
                continue
            apps[appid] = {
                "appid": appid,
                "name": info["name"] or f"App {appid}",
                "installdir": info["installdir"],
                "steamapps": sa,
            }
    return list(apps.values())


def scan_all_steam_games():
    """
    ALLE installierten Steam-Spiele — unabhängig davon, ob Steam sie als VR
    kennzeichnet. Das ist die Auswahlliste im "Spiel hinzufügen"-Dialog:
    findet der VR-Scan ein Spiel nicht, trägt der Nutzer es hier von Hand ein.

    Rückgabe: [{"appid", "name"}, ...] nach Name sortiert.
    """
    apps = installed_steam_apps()
    data, _ok = steam_appinfo.commons([a["appid"] for a in apps])
    out = []
    for app in apps:
        common = data.get(app["appid"])
        # Werkzeuge, DLC und Soundtracks gehören nicht in eine Spieleauswahl.
        # Steam schreibt den Typ selbst hin, wir müssen ihn nicht raten.
        if common is not None and not steam_appinfo.is_playable_type(common):
            continue
        out.append({"appid": app["appid"], "name": app["name"]})
    # Nicht-Steam-Spiele ("Ein Nicht-Steam-Spiel hinzufügen" in Steam). Sie
    # stehen nicht in den appmanifests, haben aber eine echte AppID — und
    # bekommen damit im Panel dieselben Einstellungen wie Steam-Spiele.
    for sc in steam_shortcuts.list_shortcuts():
        out.append({"appid": sc["appid"], "name": sc["name"], "shortcut": True})
    out.sort(key=lambda g: g["name"].lower())
    return out


# --------------------------------------------------------------------------- #
#  Ergebnis-Cache der Dateierkennung
# --------------------------------------------------------------------------- #
# Die Dateierkennung aus v1.2.8 ist gruendlich, aber teuer: pro Spiel ein
# Verzeichnis-Durchlauf ueber bis zu 6000 Ordner. Genau deshalb konnte sie nie
# automatisch beim Oeffnen des Tabs laufen.
#
# Sie muss aber laufen, denn Steams Kennzeichnung ist nicht lueckenlos —
# Spiele mit nachtraeglich ergaenztem VR-Modus stehen dort oft gar nicht.
# Ohne den Rueckfall waere die Liste kuerzer als in v1.2.8, und das ist aus
# Sicht des Nutzers schlicht ein Rueckschritt.
#
# Der Ausweg ist der Cache hier: der teure Durchlauf passiert EINMAL pro
# Spiel, das Ergebnis haelt, bis sich der Installationsordner aendert. Der
# erste Scan nach dem Update dauert also wie frueher, jeder weitere ist
# wieder sofort da.
_VR_FILECHECK_VERSION = 2       # hochzaehlen, wenn sich die Erkennung aendert


def _install_stamp(steamapps_dir, installdir):
    """Kennung des Installationsordners — aendert sie sich, wird neu geprueft.

    Genommen wird die Aenderungszeit des Ordners selbst. Die springt, wenn
    Steam Dateien darin anlegt, loescht oder ersetzt, also bei jedem Update
    und jeder Neuinstallation. Ein Durchlauf durch den ganzen Baum waere
    genauer, koestete aber wieder genau das, was der Cache einsparen soll.
    """
    if not installdir:
        return None
    path = os.path.join(steamapps_dir, "common", installdir)
    try:
        st = os.stat(path)
    except OSError:
        return None
    return f"{st.st_mtime_ns}:{path}"


def load_vr_filecheck_cache():
    """Gemerkte Ergebnisse der Dateierkennung: {appid: {"stamp", "vr"}}."""
    data = _load_app_config().get("games_vr_filecheck", {})
    if not isinstance(data, dict):
        return {}
    # Aendert sich die Erkennung, ist jedes alte Ergebnis wertlos — dann
    # lieber einmal neu pruefen als dauerhaft eine veraltete Antwort geben.
    if data.get("version") != _VR_FILECHECK_VERSION:
        return {}
    apps = data.get("apps")
    return apps if isinstance(apps, dict) else {}


def save_vr_filecheck_cache(entries):
    if not update_json(APP_CONFIG, {"games_vr_filecheck": {
            "version": _VR_FILECHECK_VERSION, "apps": entries}}):
        log.warning("Cache der Dateierkennung konnte nicht gespeichert werden.")


def scan_installed_games():
    """
    Scannt alle Steam-Bibliotheken und liefert die VR-Spiele.

    Zwei Quellen, ODER-verknüpft — die Liste kann dadurch nie kürzer sein
    als in v1.2.8:

      1. **Steams eigene Kennzeichnung** (steam_appinfo.py): die
         ``*vrsupport``-Felder, Valves Kategorien 31/53/54 und
         ``playareavr``. Kommt aus appcache/appinfo.vdf, kostet
         Millisekunden, ist aber nicht lückenlos — Spiele mit nachträglich
         ergänztem VR-Modus fehlen dort häufig.
      2. **Die Dateierkennung aus v1.2.8**: OpenVR-/OpenXR-Loader im
         Spielordner. Gründlich, aber teuer — deshalb wird jedes Ergebnis
         gecacht und nur neu ermittelt, wenn sich der Installationsordner
         geändert hat.

    Rückgabe: (tested, untested)
      tested   : AppIDs mit kuratiertem Profil in GAMES (nach Name sortiert)
      untested : [{"appid", "name"}] aller übrigen VR-Spiele (nach Name)
    """
    apps = installed_steam_apps()
    manual = set(load_manual_steam_appids())
    tags, tags_ok = steam_appinfo.commons([a["appid"] for a in apps])
    if not tags_ok:
        log.info("Steams appinfo.vdf nicht verfügbar — nur Dateierkennung.")

    cache = load_vr_filecheck_cache()
    fresh = {}
    tested, untested = set(), {}
    by_source = {"manual": 0, "steam": 0, "files": 0}

    hidden = set(load_hidden_games())
    for app in apps:
        appid, name = app["appid"], app["name"]
        if appid in hidden:
            continue                          # vom Nutzer entfernt
        common = tags.get(appid)
        source = ""

        if appid in manual:
            # Vom Nutzer selbst eingetragen: gilt immer, ohne weitere Prüfung.
            source = "manual"
        else:
            if common is not None and not steam_appinfo.is_playable_type(common):
                continue                      # Werkzeug/DLC/Soundtrack
            if common and steam_appinfo.common_says_vr(common):
                source = "steam"
            else:
                # Steam sagt nichts (oder nicht genug) -> nachsehen. Der
                # Durchlauf ist der teure aus v1.2.8, aber nur beim ersten
                # Mal je Spiel.
                stamp = _install_stamp(app["steamapps"], app["installdir"])
                hit = cache.get(appid)
                if stamp and isinstance(hit, dict) and hit.get("stamp") == stamp:
                    is_vr = bool(hit.get("vr"))
                else:
                    is_vr = _looks_like_vr_game(app["steamapps"], app["installdir"])
                if stamp:
                    fresh[appid] = {"stamp": stamp, "vr": is_vr}
                if is_vr:
                    source = "files"

        if not source:
            continue
        by_source[source] += 1
        if appid in GAMES:
            tested.add(appid)                 # kuratiertes Profil -> "getestet"
        else:
            untested[appid] = name

    # Nicht-Steam-Spiele kommen NUR ueber einen Handeintrag in die Liste. Eine
    # automatische VR-Erkennung gibt es fuer sie nicht: Steam fuehrt keine
    # Kategorie, und der Programmpfad zeigt bei Heroic/Lutris nur auf einen
    # Starter. Raten wuerde jeden Emulator mit einsammeln.
    manual_shortcuts = [a for a in manual if steam_shortcuts.is_shortcut_id(a)]
    if manual_shortcuts:
        present = {sc["appid"]: sc["name"] for sc in steam_shortcuts.list_shortcuts()}
        for appid in manual_shortcuts:
            if appid in hidden or appid not in present:
                continue                      # entfernt oder in Steam geloescht
            untested[appid] = present[appid]
            by_source["manual"] += 1

    if fresh:
        save_vr_filecheck_cache(fresh)
    log.info("VR-Scan: %d Spiele geprüft, erkannt über Steam: %d, über "
             "Dateien: %d, von Hand: %d", len(apps), by_source["steam"],
             by_source["files"], by_source["manual"])

    tested_list = sorted(tested, key=lambda a: GAMES[a]["name"].lower())
    untested_list = sorted(
        ({"appid": a, "name": n} for a, n in untested.items()),
        key=lambda g: g["name"].lower())
    return tested_list, untested_list


def vr_sources(apps=None):
    """
    Welches Signal bei welchem Spiel angeschlagen hat — für das
    Diagnose-Skript und für Fehlerberichte.

    Rückgabe: {appid: "manual" | "steam" | "files" | ""}. Nutzt denselben
    Cache wie der Scan, kostet also nach dem ersten Durchlauf nichts.
    """
    apps = apps if apps is not None else installed_steam_apps()
    manual = set(load_manual_steam_appids())
    tags, _ok = steam_appinfo.commons([a["appid"] for a in apps])
    cache = load_vr_filecheck_cache()

    out = {}
    for app in apps:
        appid = app["appid"]
        common = tags.get(appid)
        if appid in manual:
            out[appid] = "manual"
            continue
        if common is not None and not steam_appinfo.is_playable_type(common):
            out[appid] = ""
            continue
        if common and steam_appinfo.common_says_vr(common):
            out[appid] = "steam"
            continue
        stamp = _install_stamp(app["steamapps"], app["installdir"])
        hit = cache.get(appid)
        if stamp and isinstance(hit, dict) and hit.get("stamp") == stamp:
            is_vr = bool(hit.get("vr"))
        else:
            is_vr = _looks_like_vr_game(app["steamapps"], app["installdir"])
        out[appid] = "files" if is_vr else ""
    return out


# --------------------------------------------------------------------------- #
#  Cache in der App-Config ("nicht jedes Mal neu scannen")
# --------------------------------------------------------------------------- #
def _load_app_config():
    try:
        with open(APP_CONFIG) as f:
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
        name = g.get("name") or f"App {appid}"
        if appid in _APPID_BLACKLIST or _is_steam_tool(name):
            continue          # alte Caches mit "Proton 10.0" o. Ä. selbst heilen
        if appid in GAMES:
            tested.add(appid)   # inzwischen kuratiert -> hochstufen
        else:
            untested.append({"appid": appid, "name": name})
    tested_list = sorted(tested, key=lambda a: GAMES[a]["name"].lower())
    untested.sort(key=lambda g: g["name"].lower())
    return tested_list, untested, True


def games_tab_entries():
    """
    Genau die Spiele, die der Games-Tab zeigt — für andere Tabs (Controls).

    Rückgabe: [{"id", "name", "kind", "exe"}] mit kind =
      "steam"    : Steam-Spiel (getestet oder ungetestet)
      "shortcut" : Nicht-Steam-Spiel aus Steam (hat eine AppID)
      "local"    : eigener Eintrag ohne Steam (id = 'local:<n>', exe gesetzt)

    Nutzt den Cache des Games-Tabs. Wurde dort noch nie gescannt, wird
    einmal gescannt (schnell, siehe scan_installed_games) — gespeichert wird
    dabei nichts, das bleibt Sache des Games-Tabs.
    """
    tested, untested, scanned = load_cached_games()
    if not scanned:
        try:
            tested, untested = scan_installed_games()
        except Exception as exc:  # noqa: BLE001 — lieber leer als Absturz
            log.warning("games_tab_entries: Scan fehlgeschlagen — %s", exc)
            tested, untested = [], []
    hidden = set(load_hidden_games())
    out = []
    for appid in tested:
        if appid not in hidden and appid in GAMES:
            out.append({"id": appid, "name": GAMES[appid]["name"], "kind": "steam", "exe": ""})
    for g in untested:
        appid = g["appid"]
        if appid in hidden:
            continue
        kind = "shortcut" if steam_shortcuts.is_shortcut_id(appid) else "steam"
        out.append({"id": appid, "name": g["name"], "kind": kind, "exe": ""})
    for entry in load_local_games():
        out.append({"id": entry["id"], "name": entry["name"], "kind": "local",
                    "exe": entry["exe"]})
    return out


# --------------------------------------------------------------------------- #
#  Auto-Scan beim Öffnen des Games-Tabs
# --------------------------------------------------------------------------- #
# Viele Nutzer haben den "Spiele scannen"-Knopf schlicht übersehen und
# standen vor einer leeren Liste. Der Tab scannt deshalb beim Öffnen selbst
# — abschaltbar in den Einstellungen, aber standardmäßig AN.
#
# Dass das überhaupt geht, hängt am neuen Scanner: mit Steams eigener
# VR-Kennzeichnung dauert ein Durchlauf Millisekunden statt Sekunden.
AUTO_SCAN_DEFAULT = True


def auto_scan_enabled():
    """True, wenn der Games-Tab beim Öffnen selbst scannen soll."""
    value = _load_app_config().get("games_auto_scan", AUTO_SCAN_DEFAULT)
    if isinstance(value, bool):
        return value
    # Ältere Configs könnten "1"/"true" als Text enthalten.
    return str(value).strip().lower() not in ("0", "false", "off", "no", "")


def set_auto_scan(enabled):
    """Merkt den Auto-Scan-Schalter dauerhaft."""
    if not update_json(APP_CONFIG, {"games_auto_scan": bool(enabled)}):
        log.warning("Auto-Scan-Einstellung konnte nicht gespeichert werden.")


# --------------------------------------------------------------------------- #
#  Von Hand ergänzte STEAM-Spiele
# --------------------------------------------------------------------------- #
# Steams VR-Kennzeichnung ist gut, aber nicht lückenlos: Beta-Zweige,
# Spiele mit nachgerüstetem VR-Modus und Mod-Loader stehen dort oft nicht.
# Statt die Erkennung mit Sonderfällen aufzuweichen (und damit wieder
# Flachbildschirm-Spiele einzusammeln), darf der Nutzer gezielt nachhelfen.
def load_manual_steam_appids():
    """AppIDs, die der Nutzer selbst in die VR-Liste geholt hat."""
    data = _load_app_config().get("games_manual_steam", [])
    if not isinstance(data, list):
        return []
    return [str(a) for a in data if str(a).isdigit()]


def add_manual_steam_appid(appid):
    """Trägt ein Steam-Spiel fest in die VR-Liste ein. True = war neu."""
    appid = str(appid)
    if not appid.isdigit():
        return False
    # Wer ein entferntes Spiel von Hand wieder einträgt, will es sehen —
    # sonst legt er den Eintrag an und die Liste bleibt trotzdem leer.
    unhide_game(appid)
    current = load_manual_steam_appids()
    if appid in current:
        return False
    current.append(appid)
    if not update_json(APP_CONFIG, {"games_manual_steam": current}):
        log.warning("Manuelles Steam-Spiel konnte nicht gespeichert werden.")
        return False
    if steam_shortcuts.is_shortcut_id(appid):
        remember_shortcut_base(appid)
    return True


# --------------------------------------------------------------------------- #
#  Nicht-Steam-Spiele: die Startparameter, die der Eintrag schon hatte
# --------------------------------------------------------------------------- #
# Bei Nicht-Steam-Spielen sind die Startparameter oft TRAGEND: ein
# Heroic-Eintrag startet ueber "heroic://launch/...", ein Lutris-Eintrag ueber
# "lutris:rungameid/12". Der Play-Knopf schreibt die Parameter aus dem Panel
# zurueck — ohne diese Sicherung waeren sie beim ersten Klick weg und das
# Spiel startete nie wieder.
#
# Gemerkt wird der Stand BEIM EINTRAGEN, und zwar nur einmal. Spaeter aus der
# Datei gelesen, stuenden dort schon unsere eigenen Schalter (gamemoderun
# ...) — und ein abgeschalteter Schalter liesse sich nie mehr entfernen.
# Der Wert wird im Panel als Basis-Parameter verwendet, genau wie die
# hinterlegten Parameter eines kuratierten Spiels.
def remember_shortcut_base(appid):
    appid = str(appid)
    bases = _load_app_config().get("games_shortcut_base", {})
    if not isinstance(bases, dict):
        bases = {}
    if appid in bases:
        return bases[appid]
    sc = steam_shortcuts.get(appid)
    base = (sc or {}).get("launch_options", "") or ""
    bases[appid] = base
    if not update_json(APP_CONFIG, {"games_shortcut_base": bases}):
        log.warning("Startparameter des Nicht-Steam-Spiels konnten nicht gemerkt werden.")
    return base


def shortcut_base_options(appid):
    """Gemerkte Original-Startparameter (merkt sie beim ersten Aufruf)."""
    bases = _load_app_config().get("games_shortcut_base", {})
    if isinstance(bases, dict) and str(appid) in bases:
        return bases[str(appid)] or ""
    return remember_shortcut_base(appid)


def remove_manual_steam_appid(appid):
    """Nimmt den Handeintrag zurück. Das Spiel kann danach trotzdem noch in
    der Liste stehen — nämlich dann, wenn Steam es ohnehin als VR führt."""
    appid = str(appid)
    current = load_manual_steam_appids()
    if appid not in current:
        return False
    current.remove(appid)
    if not update_json(APP_CONFIG, {"games_manual_steam": current}):
        log.warning("Manuelles Steam-Spiel konnte nicht entfernt werden.")
        return False
    return True


# --------------------------------------------------------------------------- #
#  Aus der Liste entfernte Spiele
# --------------------------------------------------------------------------- #
# Die Erkennung liegt manchmal daneben: ein Flachbildschirm-Spiel mit einer
# mitgelieferten VR-Bibliothek, ein Titel, dessen VR-Modus man nie benutzt.
# Bisher konnte man so einen Eintrag nur ansehen — jedes Ausblenden hätte
# beim nächsten Scan wieder von vorn begonnen.
#
# Das "Entfernen" im Detail-Panel schreibt die AppID deshalb dauerhaft hierher.
# Zwei Wege zurück, beide ausdrücklich vom Nutzer:
#   * das Spiel über "+ Spiel hinzufügen" wieder eintragen
#   * Einstellungen -> Spiele -> "Games-Tab zurücksetzen"
#
# Bewusst NUR eine Liste von AppIDs und keine Kopie der Spieldaten: was
# entfernt ist, soll nach dem Zurücksetzen wieder genau so auftauchen, wie der
# Scan es findet — nicht so, wie es beim Entfernen einmal aussah.
def load_hidden_games():
    """AppIDs, die der Nutzer aus der Liste entfernt hat."""
    data = _load_app_config().get("games_hidden", [])
    if not isinstance(data, list):
        return []
    return [str(a) for a in data if str(a)]


def hide_game(appid):
    """Entfernt ein Spiel dauerhaft aus der Liste. True = war noch drin.

    Ein vorhandener Handeintrag wird dabei mit gelöscht. Sonst stünden zwei
    gegensätzliche Wünsche in der Config ("immer zeigen" und "nie zeigen"),
    und welcher gewinnt, wäre eine Frage der Auswertungsreihenfolge statt
    einer Entscheidung des Nutzers.
    """
    appid = str(appid)
    current = load_hidden_games()
    if appid in current:
        return False
    remove_manual_steam_appid(appid)
    current.append(appid)
    if not update_json(APP_CONFIG, {"games_hidden": current}):
        log.warning("Entfernte Spiele konnten nicht gespeichert werden.")
        return False
    return True


def unhide_game(appid):
    """Holt ein einzelnes entferntes Spiel zurück."""
    appid = str(appid)
    current = load_hidden_games()
    if appid not in current:
        return False
    current.remove(appid)
    if not update_json(APP_CONFIG, {"games_hidden": current}):
        log.warning("Entfernte Spiele konnten nicht gespeichert werden.")
        return False
    return True


def clear_hidden_games():
    """"Games-Tab zurücksetzen": alle entfernten Spiele wieder anzeigen.
    Rückgabe: wie viele zurückgeholt wurden."""
    current = load_hidden_games()
    if not current:
        return 0
    if not update_json(APP_CONFIG, {"games_hidden": []}):
        log.warning("Entfernte Spiele konnten nicht zurückgesetzt werden.")
        return 0
    return len(current)


# --------------------------------------------------------------------------- #
#  Eigene Spiele (alles, was NICHT über Steam läuft)
# --------------------------------------------------------------------------- #
# Itch.io, GOG, selbst gebaute Builds, AppImages, eine entpackte Demo — dafür
# gibt es keine AppID und damit auch kein Steam-Startkommando. Solche
# Einträge tragen deshalb eine eigene Kennung "local:<n>" und werden direkt
# als Prozess gestartet.
#
# Die Kennung ist bewusst ein STRING mit Präfix und keine fortlaufende Zahl:
# im Games-Tab liegen eigene Einträge und Steam-Spiele im selben Verzeichnis
# (Kacheln, aufgeklapptes Panel, gemerkte Startparameter). Mit dem Präfix
# kann keine Stelle die beiden je verwechseln — steam_appinfo.is_steam_appid()
# entscheidet das an einer Stelle für alle.
LOCAL_PREFIX = "local:"


def is_local_id(value):
    """True für die Kennung eines eigenen Spiels ('local:3')."""
    return str(value or "").startswith(LOCAL_PREFIX)


def load_local_games():
    """
    Die eigenen Spiele des Nutzers.
    Rückgabe: [{"id", "name", "exe", "launch_options"}] nach Name sortiert.
    """
    data = _load_app_config().get("games_local", [])
    if not isinstance(data, list):
        return []
    out = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        gid = str(entry.get("id", "") or "")
        name = str(entry.get("name", "") or "").strip()
        exe = str(entry.get("exe", "") or "").strip()
        if not gid or not name or not exe:
            continue
        out.append({
            "id": gid,
            "name": name,
            "exe": exe,
            "launch_options": str(entry.get("launch_options", "") or "").strip(),
            "image": str(entry.get("image", "") or "").strip(),
        })
    out.sort(key=lambda g: g["name"].lower())
    return out


def _save_local_games(entries):
    if not update_json(APP_CONFIG, {"games_local": entries}):
        log.warning("Eigene Spiele konnten nicht gespeichert werden.")
        return False
    return True


def _next_local_id(entries):
    """Kleinste freie Nummer. Nach dem Löschen eines Eintrags werden Nummern
    wiederverwendet — die Kennung ist eine Verknüpfung, kein Verlauf."""
    used = set()
    for e in entries:
        m = re.match(re.escape(LOCAL_PREFIX) + r"(\d+)$", e.get("id", ""))
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return f"{LOCAL_PREFIX}{n}"


def validate_game_input(name, exe, image=""):
    """
    Prueft Name, Programmdatei und (optionales) Bild.
    Rückgabe: (ok, fehlerschlüssel, exe_absolut)
      Fehlerschlüssel: "no_name" | "no_exe" | "not_found" | "bad_image"
    Gemeinsam fuer „Hinzufügen" und „In Steam eintragen" — beide sollen
    dieselben Fehler gleich melden.
    """
    name = (name or "").strip()
    exe = (exe or "").strip()
    if not name:
        return False, "no_name", ""
    if not exe:
        return False, "no_exe", ""
    exe = os.path.abspath(os.path.expanduser(exe))
    if not os.path.isfile(exe):
        return False, "not_found", exe
    image = (image or "").strip()
    if image and (not os.path.isfile(os.path.expanduser(image))
                  or os.path.splitext(image)[1].lower() not in IMAGE_EXTS):
        return False, "bad_image", exe
    return True, "", exe


def is_windows_exe(path):
    """Windows-Programm? Die laufen fuer VR nur ueber Steam+Proton sinnvoll."""
    return str(path or "").strip().lower().endswith(".exe")


def add_local_game(name, exe, launch_options="", image=""):
    """
    Legt ein eigenes Spiel an.
    Rückgabe: (ok, kennung_oder_fehlerschlüssel)
      Fehlerschlüssel: "no_name" | "no_exe" | "not_found" | "bad_image" |
                       "save_failed"
    Die Schlüssel sind absichtlich keine fertigen Sätze — die Oberfläche
    übersetzt sie, damit die Meldung in der eingestellten Sprache erscheint.
    """
    ok, err, exe = validate_game_input(name, exe, image)
    if not ok:
        return False, err

    entries = load_local_games()
    gid = _next_local_id(entries)
    stored = _store_local_image(image) if (image or "").strip() else ""
    entries.append({"id": gid, "name": name.strip(), "exe": exe,
                    "launch_options": (launch_options or "").strip(),
                    "image": stored})
    if not _save_local_games(entries):
        _delete_local_image(stored)
        return False, "save_failed"
    return True, gid


# --------------------------------------------------------------------------- #
#  Bilder eigener Spiele
# --------------------------------------------------------------------------- #
# Das gewaehlte Bild wird KOPIERT, nicht nur verlinkt: ein Bild aus dem
# Download-Ordner ist sonst nach dem naechsten Aufraeumen weg, und die Kachel
# faellt still auf den Platzhalter zurueck.
#
# Der Dateiname ist zufaellig und nicht an die Kennung ("local:3") gebunden.
# Kennungen werden nach dem Loeschen wiederverwendet — ein neues Spiel mit
# derselben Nummer bekaeme sonst das Bild des alten.
IMAGE_EXTS = steam_shortcuts.IMAGE_EXTS


def local_images_dir():
    return os.path.join(os.path.dirname(APP_CONFIG), "covers")


def _store_local_image(source):
    import uuid
    source = os.path.expanduser((source or "").strip())
    ext = os.path.splitext(source)[1].lower()
    if ext not in IMAGE_EXTS or not os.path.isfile(source):
        return ""
    dest_dir = local_images_dir()
    dest = os.path.join(dest_dir, f"local-{uuid.uuid4().hex[:12]}{ext}")
    try:
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copyfile(source, dest)
    except OSError as exc:
        log.warning("Bild konnte nicht uebernommen werden: %s", exc)
        return ""
    return dest


def _delete_local_image(path):
    """Nur Kopien im eigenen Ordner loeschen — nie ein Bild des Nutzers."""
    if not path:
        return
    real = os.path.realpath(path)
    if os.path.dirname(real) != os.path.realpath(local_images_dir()):
        return
    try:
        os.remove(real)
    except OSError:
        pass


def set_local_game_image(gid, source):
    """Bild eines eigenen Spiels setzen. Rückgabe: (ok, fehlerschlüssel)."""
    source = os.path.expanduser((source or "").strip())
    if os.path.splitext(source)[1].lower() not in IMAGE_EXTS:
        return False, "bad_type"
    if not os.path.isfile(source):
        return False, "not_found"
    entries = _raw_local_entries()
    for entry in entries:
        if str(entry.get("id")) != str(gid):
            continue
        stored = _store_local_image(source)
        if not stored:
            return False, "write_failed"
        old = entry.get("image", "")
        entry["image"] = stored
        if not _save_local_games(entries):
            _delete_local_image(stored)
            return False, "write_failed"
        _delete_local_image(old)
        return True, ""
    return False, "not_found"


def clear_local_game_image(gid):
    entries = _raw_local_entries()
    for entry in entries:
        if str(entry.get("id")) == str(gid) and entry.get("image"):
            old = entry["image"]
            entry["image"] = ""
            if _save_local_games(entries):
                _delete_local_image(old)
                return True
    return False


def _raw_local_entries():
    """Die Eintraege so, wie sie in der Config stehen (fuer Aenderungen)."""
    return [dict(e) for e in load_local_games()]


# --------------------------------------------------------------------------- #
#  Bilder von Nicht-Steam-Spielen
# --------------------------------------------------------------------------- #
def set_shortcut_image(appid, source):
    """Bild in Steams grid-Ordner — sieht dann auch Steam selbst."""
    return steam_shortcuts.set_grid_image(appid, os.path.expanduser((source or "").strip()))


def clear_shortcut_image(appid):
    return steam_shortcuts.clear_grid_image(appid)


# --------------------------------------------------------------------------- #
#  „In Steam eintragen"
# --------------------------------------------------------------------------- #
def register_in_steam(name, exe, launch_options="", image=""):
    """
    Traegt ein Programm als Nicht-Steam-Spiel in Steam ein und holt es
    sofort in die VR-Liste. STEAM DARF NICHT LAUFEN (siehe steam_close.py).

    Rückgabe: (appid, fehlerschlüssel)
      Fehlerschlüssel: wie validate_game_input, dazu die aus
      steam_shortcuts.add_shortcut ("no_account", "unreadable",
      "write_failed"). "exists" gilt als Erfolg: das Spiel steht schon in
      Steam und wird nur (wieder) in die Liste geholt.
    """
    ok, err, exe = validate_game_input(name, exe, image)
    if not ok:
        return None, err
    appid, err = steam_shortcuts.add_shortcut(name.strip(), exe, launch_options or "")
    if err not in ("", "exists"):
        return None, err
    add_manual_steam_appid(appid)
    if (image or "").strip():
        img_ok, img_err = set_shortcut_image(appid, image)
        if not img_ok:
            log.warning("Bild fuer %s nicht gesetzt: %s", appid, img_err)
    return appid, err


def update_local_game(gid, **fields):
    """Ändert Felder eines eigenen Spiels (name/exe/launch_options)."""
    entries = load_local_games()
    changed = False
    for entry in entries:
        if entry["id"] != str(gid):
            continue
        for key in ("name", "exe", "launch_options"):
            if key in fields and fields[key] is not None:
                entry[key] = str(fields[key]).strip()
                changed = True
    return _save_local_games(entries) if changed else False


def remove_local_game(gid):
    """Löscht ein eigenes Spiel. Die Datei auf der Platte bleibt unberührt —
    nur die von uns angelegte Bildkopie verschwindet mit dem Eintrag."""
    entries = load_local_games()
    rest = [e for e in entries if e["id"] != str(gid)]
    if len(rest) == len(entries):
        return False
    gone = next(e for e in entries if e["id"] == str(gid))
    if not _save_local_games(rest):
        return False
    _delete_local_image(gone.get("image", ""))
    return True


def local_game(gid):
    """Ein einzelner eigener Eintrag oder None."""
    for entry in load_local_games():
        if entry["id"] == str(gid):
            return entry
    return None


def local_launch_cmd(entry):
    """
    Startbefehl für ein eigenes Spiel.
    Rückgabe: (befehl_als_liste, fehlerschlüssel)
      Fehlerschlüssel: "" | "not_found" | "no_wine" | "not_executable"

    Unterstützt wird, was auf einem Linux-Desktop vorkommt: native Binaries,
    *.x86_64 aus Unity-Builds, AppImages, Start-Skripte (*.sh) und
    Windows-Programme (*.exe) über Wine.

    Windows-Programme laufen bewusst über wine und NICHT über Proton: Proton
    braucht ein von Steam verwaltetes Prefix samt AppID, und genau die hat
    ein eigener Eintrag ja nicht. Wer Proton möchte, trägt das Spiel in Steam
    als Nicht-Steam-Spiel ein — dann taucht es hier ohnehin mit AppID auf.
    """
    exe = (entry or {}).get("exe", "")
    exe = os.path.expanduser(exe or "")
    if not exe or not os.path.isfile(exe):
        return None, "not_found"

    try:
        args = shlex.split(entry.get("launch_options", "") or "")
    except ValueError:
        # Unpaarige Anführungszeichen: lieber roh zerlegen als gar nicht
        # starten. Der Nutzer sieht das Ergebnis im Feld und kann es richten.
        args = (entry.get("launch_options", "") or "").split()

    if exe.lower().endswith(".exe"):
        wine = shutil.which("wine")
        if not wine:
            return None, "no_wine"
        return [wine, exe] + args, ""

    if not os.access(exe, os.X_OK):
        # Ein *.sh ohne Ausführungsrecht ist der Normalfall bei entpackten
        # Archiven. Über den Interpreter zu starten ist freundlicher, als den
        # Nutzer erst chmod nachschlagen zu lassen.
        if exe.lower().endswith(".sh"):
            return ["sh", exe] + args, ""
        return None, "not_executable"

    return [exe] + args, ""


def save_cached_games(tested, untested):
    """Schreibt beide Scan-Ergebnisse fest in die Config
    (Keys 'detected_games' + 'detected_games_untested')."""
    # update_json liest, aendert gezielt und schreibt atomar zurueck — so
    # geht kein fremder Schluessel der config.json verloren, auch wenn eine
    # andere Stelle sie parallel erweitert hat.
    ok = update_json(APP_CONFIG, {
        "detected_games": list(tested),
        "detected_games_untested": [
            {"appid": g["appid"], "name": g["name"]} for g in untested],
    })
    if not ok:
        log.warning("Spiele-Cache konnte nicht gespeichert werden.")


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
    except Exception as exc:
        log.debug("detect_gpu_vendor: ignoriert — %s", exc)
    # Fallback: lspci
    try:
        out = subprocess.run(["lspci"], capture_output=True, text=True,
                             timeout=5).stdout.lower()
        if "nvidia" in out:
            return "nvidia"
        if "amd" in out or "radeon" in out or "advanced micro devices" in out:
            return "amd"
    except Exception as exc:
        log.debug("detect_gpu_vendor: ignoriert — %s", exc)
    return "unknown"


def is_cachyos():
    """True auf CachyOS (bestimmt, welche Proton-Empfehlung 'main' ist)."""
    try:
        with open("/etc/os-release") as f:
            content = f.read().lower()
        return bool(re.search(r'^id=.*cachyos', content, re.MULTILINE)) or \
            "cachyos" in "".join(re.findall(r'^id_like=(.*)$', content, re.MULTILINE))
    except Exception:
        return False


def recommended_role(game=None):
    """Welche 'role' auf diesem System die Haupt-Empfehlung ist.

    Ohne ``game`` die alte Bedeutung (fuer Aufrufer, die kein Spiel zur Hand
    haben). Mit ``game`` zusaetzlich ein Rueckfall: hat ein Spiel gar keinen
    eigenen CachyOS-Eintrag, weil dort dieselbe Version empfohlen wird wie
    ueberall — bei VRChat seit 1.1.9 der Fall —, dann traegt der normale
    'main'-Eintrag die Empfehlung. Ohne diesen Rueckfall stuende auf CachyOS
    ueberhaupt kein "Empfohlen" an der Liste, weil die gesuchte Rolle
    schlicht nicht vorkommt.
    """
    if not is_cachyos():
        return "main"
    if game is None:
        return "main_cachyos"
    has_cachy = any(p.get("role") == "main_cachyos" for p in game.get("protons", []))
    return "main_cachyos" if has_cachy else "main"


def visible_protons(game):
    """
    Die auf DIESEM System anzuzeigenden Proton-Einträge eines Spiels.
    Einträge mit "hide_on_cachyos": True werden auf CachyOS ausgeblendet
    (z. B. Valves normales Proton — dort reichen cachyos + rtsp völlig).
    Die Empfehlung für dieses System steht immer zuerst.
    """
    cachy = is_cachyos()
    rec = recommended_role(game)
    protons = [p for p in game.get("protons", [])
               if not (cachy and p.get("hide_on_cachyos"))
               and not ((not cachy) and p.get("cachyos_only"))]
    # Empfehlung zuerst, danach feste Rollen-Reihenfolge: Alternative (Backup)
    # vor "safe". Vorher entschied allein die Reihenfolge in der games.json,
    # was bei mehreren Slots pro Rolle nicht mehr vorhersagbar ist.
    order = {"main": 0, "main_cachyos": 0, "alternative": 1, "safe": 2}
    return sorted(protons, key=lambda p: (0 if p.get("role") == rec else 1,
                                          order.get(p.get("role"), 9)))


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
# Steam-CDN: Bilder fuer JEDES Spiel, auch fuer nie gestartete/ungetestete.
# <appid> wird eingesetzt. Reihenfolge = Vorliebe:
#   library_600x900.jpg -> Hochkant, passt exakt in die Kachel
#   header.jpg          -> Querformat, gibt es praktisch immer (Fallback)
STEAM_CDN_BASE = "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps"
STEAM_CDN_NAMES = ["library_600x900.jpg", "header.jpg"]

COVER_CACHE_DIR = os.path.join(HOME, ".cache/yakuda-connect/covers")


def cached_cover_path(appid):
    """Pfad im lokalen Cover-Cache (existiert evtl. noch nicht)."""
    return os.path.join(COVER_CACHE_DIR, f"{appid}.jpg")


def download_cover(appid, timeout=8):
    """
    Laedt das Coverbild vom Steam-CDN in den lokalen Cache.
    Probiert erst das Hochkant-Bild, dann header.jpg als Fallback.
    Rueckgabe: Pfad oder None. Schlaegt NIE laut fehl (offline = None).
    """
    import urllib.request

    dest = cached_cover_path(appid)
    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
        return dest

    os.makedirs(COVER_CACHE_DIR, exist_ok=True)

    # Eine in games.json hinterlegte Bild-URL gewinnt. Notwendig, weil Steams
    # Bildpfade nicht durchgaengig nach dem Muster .../<appid>/header.jpg
    # aufgebaut sind: neuere Titel haben einen Hash im Pfad (Thief VR ist so
    # ein Fall). Fuer die raten wir sonst zweimal daneben und die Kachel
    # bleibt beim Platzhalter.
    urls = []
    entry = GAMES.get(str(appid))
    if entry and entry.get("picture"):
        urls.append(entry["picture"])
    urls += [f"{STEAM_CDN_BASE}/{appid}/{name}" for name in STEAM_CDN_NAMES]

    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "yakuda-connect"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    continue
                data = resp.read()
            # Plausibilitaet: JPEG-Magic + nicht bloss eine Fehlerseite
            if len(data) < 1024 or not data.startswith(b"\xff\xd8"):
                continue
            tmp = dest + ".part"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)      # atomar: nie eine halbe Datei im Cache
            return dest
        except Exception:
            continue
    return None


def get_game_cover(appid, allow_download=True):
    """
    Coverbild fuer ein Spiel — die EINE Funktion, die die UI benutzen sollte.
    Reihenfolge:
      1. lokaler Steam-Cache (sofort da, kein Netz)
      2. eigener Download-Cache (~/.cache/yakuda-connect/covers)
      3. Download vom Steam-CDN (nur wenn allow_download=True)
    Rueckgabe: Pfad oder None.
    """
    # Eigene Spiele haben keine AppID und damit auch kein Steam-Cover. Ohne
    # diese Abfrage wuerde die Kachel eines eigenen Eintrags einen Download
    # auf https://.../store_item_assets/steam/apps/local:3/... ausloesen —
    # ein Netzwerkaufruf, der nur scheitern kann. Ihr Bild kommt, wenn der
    # Nutzer eines gesetzt hat, aus der Config.
    if is_local_id(appid):
        entry = local_game(appid)
        image = (entry or {}).get("image", "")
        return image if image and os.path.isfile(image) else None
    if not steam_appinfo.is_steam_appid(appid):
        return None
    local = find_game_cover(appid)
    if local:
        return local
    # Nicht-Steam-Spiele gibt es auf Steams Bildserver nicht. Ihr Bild kommt
    # nur aus dem Grid-Ordner (von Hand oder per SteamGridDB gesetzt).
    if steam_shortcuts.is_shortcut_id(appid):
        return None
    cached = cached_cover_path(appid)
    if os.path.isfile(cached) and os.path.getsize(cached) > 0:
        return cached
    if allow_download:
        return download_cover(appid)
    return None


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
                    # Hochkant zuerst; Nicht-Steam-Spiele haben oft nur
                    # das Querformat (<appid>.png) oder das Hero-Bild.
                    for stem in (f"{appid}p", f"{appid}", f"{appid}_hero"):
                        for ext in ("png", "jpg", "jpeg"):
                            p = os.path.join(grid, f"{stem}.{ext}")
                            if os.path.isfile(p):
                                return p
            except Exception as exc:
                log.debug("find_game_cover: ignoriert — %s", exc)
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
# Danach reicht ein `steam -applaunch <appid>`. Vor jedem Schreiben wird
# eine .bak-Sicherung mit Zeitstempel angelegt.
#
# Läuft Steam, hält es seine VDFs im Speicher und schreibt sie beim Beenden
# zurück — eine Änderung von außen ist danach weg, auch nach einem
# "Neustart". "Use" beendet Steam deshalb vorher (games_mixin._use_proton).

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
    except Exception as exc:
        log.debug("_backup_file: ignoriert — %s", exc)


def steam_is_running():
    """True, wenn ein Steam-Client-Prozess läuft (Änderungen an den VDFs
    greifen dann erst nach einem Steam-Neustart)."""
    try:
        r = subprocess.run(["pgrep", "-x", "steam"], capture_output=True, timeout=proc.DEFAULT_TIMEOUT)
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


# Von Distributionspaketen installierte Tools (CachyOS: proton-cachyos aus
# dem Repo, Arch/AUR: proton-ge-custom-bin). Steam liest diese Ordner
# zusaetzlich zu seinem eigenen compatibilitytools.d. Installiert wird dort
# nie etwas — compat_tools_install_dir() schaut sie deshalb nicht an.
SYSTEM_COMPAT_TOOLS_DIRS = [
    "/usr/share/steam/compatibilitytools.d",
    "/usr/local/share/steam/compatibilitytools.d",
]


def system_compat_tools_dirs():
    return [d for d in SYSTEM_COMPAT_TOOLS_DIRS if os.path.isdir(d)]


def compat_tools_install_dir():
    """Das compatibilitytools.d, in das ein manueller Build entpackt wird.

    Bewusst NICHT hartkodiert: auf CachyOS/Arch laeuft Steam fast immer
    nativ (~/.local/share/Steam), bei Flatpak-Steam liegt es unter
    ~/.var/app/com.valvesoftware.Steam/. steam_data_roots() kennt beide
    Faelle und liefert die real existierenden zuerst. Existiert noch gar
    kein compatibilitytools.d, wird es im ersten Steam-Datenverzeichnis
    angelegt — Steam liest es beim naechsten Start.
    """
    existing = compat_tools_dirs()
    if existing:
        return existing[0]
    roots = venv.steam_data_roots()
    if not roots:
        return None
    target = os.path.join(roots[0], "compatibilitytools.d")
    try:
        os.makedirs(target, exist_ok=True)
    except Exception as exc:
        log.warning("compat_tools_install_dir: %s nicht anlegbar — %s", target, exc)
        return None
    return target


def _natural_key(name):
    return tuple(int(n) for n in re.findall(r"\d+", name))


# Welche Ordner-Präfixe in compatibilitytools.d zu welchem Runner gehören
_TOOL_PREFIXES = {
    "proton-ge":      ["GE-Proton", "Proton-GE"],
    "proton-cachyos": ["proton-cachyos", "Proton-CachyOS"],
    "proton-ge-rtsp": ["proton-rtsp", "GE-Proton-RTSP", "proton-ge-rtsp"],
}

# Praefixe, die trotz Treffer NICHT zum Runner gehoeren.
# "Proton-RTSP-Wayland-GE-Beta3" faengt auf "proton-rtsp" an und wuerde sonst
# als RTSP-Upstream-Build durchgehen. Hat jemand nur den Wayland-Fork
# installiert, behauptete die RTSP-Karte dann "installiert" und ein Klick auf
# "Use" traege den falschen Ordner in Steams CompatToolMapping ein.
_TOOL_EXCLUDES = {
    "proton-ge-rtsp": ["proton-rtsp-wayland"],
}


def installed_builds(proton):
    """Alle installierten Ordner in compatibilitytools.d, die zu diesem
    Proton-Eintrag gehoeren — neueste zuletzt. Leere Liste = nicht da."""
    runner = proton.get("protonplus_runner")
    # Ein explizites tool_prefix aus der games.json gewinnt: manuell
    # installierte Builds (Proton-RTSP-Wayland-GE) haben gar keinen Runner,
    # sind aber sehr wohl vorhanden und auswaehlbar.
    prefixes = proton.get("tool_prefix") or []
    if not prefixes:
        if runner is None:
            return []
        version = proton.get("version", "")
        prefixes = _TOOL_PREFIXES.get(runner, [version])
    excludes = _TOOL_EXCLUDES.get(runner, []) if runner else []
    found = []
    for d in compat_tools_dirs() + system_compat_tools_dirs():
        try:
            names = os.listdir(d)
        except Exception:
            continue
        for name in names:
            if not os.path.isdir(os.path.join(d, name)):
                continue
            low = name.lower()
            if any(x and low.startswith(x.lower()) for x in excludes):
                continue
            if any(p and low.startswith(p.lower()) for p in prefixes):
                if name not in found:
                    found.append(name)
    found.sort(key=_natural_key)
    return found


def resolve_steam_tool(proton):
    """
    Übersetzt einen Proton-Eintrag in den Tool-Namen für Steams
    CompatToolMapping (= Ordnername in compatibilitytools.d).
    Rückgabe: (tool_name_oder_None, gefunden: bool, art: str)
      tool None + gefunden True  -> Valves Proton (Steam bringt es selbst mit;
                                    welcher Name in CompatToolMapping gehoert,
                                    klaert compat_mapping_name)
      gefunden False             -> Version nicht installiert

    Es gewinnt immer die NEUESTE installierte passende Version, nicht die in
    der games.json eingetragene. Die Datenbank nennt zwangslaeufig einen
    Stand von gestern — proton-rtsp und GE erscheinen im Wochentakt. Wuerde
    die eingetragene Version bevorzugt, bliebe man auf ihr sitzen, obwohl
    laengst eine neuere daneben liegt. Der Eintrag in der games.json dient
    damit nur noch als Hinweis, WELCHE Sorte gemeint ist.
    """
    runner = proton.get("protonplus_runner")
    if runner is None and not proton.get("tool_prefix"):
        # Valves Proton / "Proton 11 (Standard)": bringt Steam selbst mit ->
        # Mapping entfernen, Steam nutzt seinen Standard.
        #
        # ACHTUNG: die tool_prefix-Bedingung ist wesentlich. Manuell
        # installierte Builds haben ebenfalls runner=None, sind aber ein
        # echtes Compat-Tool. Ohne den Zusatz laege hier "Steam-Standard"
        # und ein Klick auf "Use" wuerde VRChat still auf Stock-Proton
        # zuruecksetzen, waehrend die Karte Wayland-GE anzeigt.
        return None, True, "steam_default"

    builds = installed_builds(proton)
    if builds:
        newest = builds[-1]
        kind = "exact" if newest == proton.get("version", "") else "newer"
        return newest, True, kind
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
        with open(path, errors="ignore") as f:
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


def get_steam_compat_tool(appid):
    """Der Tool-Name, der fuer dieses Spiel in CompatToolMapping steht, oder None.

    Genau dieser Eintrag ist der Haken „Die Verwendung eines bestimmten
    Kompatibilitaetswerkzeugs erzwingen" in Steams Eigenschaften: steht dort
    ein Name, den Steam kennt, ist der Haken gesetzt.
    """
    path = _config_vdf_path()
    if not path:
        return None
    try:
        with open(path, errors="ignore") as f:
            text = f.read()
    except OSError:
        return None
    steam_span = (_vdf_descend(text, ["InstallConfigStore", "Software", "Valve", "Steam"])
                  or _vdf_descend(text, ["Software", "Valve", "Steam"]))
    if steam_span is None:
        return None
    mapping = _vdf_find_block(text, "CompatToolMapping", steam_span[0] + 1, steam_span[1])
    if mapping is None:
        return None
    app_span = _vdf_find_block(text, str(appid), mapping[0] + 1, mapping[1])
    if app_span is None:
        return None
    m = re.search(r'"name"\s+"((?:[^"\\]|\\.)*)"', text[app_span[0]:app_span[1]], re.IGNORECASE)
    return m.group(1) if m and m.group(1) else None


# --------------------------------------------------------------------------- #
#  Welcher Name gehoert in CompatToolMapping?
# --------------------------------------------------------------------------- #
# Steam kennt ein Tool nicht unter seinem Ordnernamen, sondern unter dem
# internen Namen aus seiner compatibilitytool.vdf. Meist ist beides gleich
# (GE-Proton10-26), aber nicht immer — Distributionspakete benennen den
# Ordner gern schlicht "proton-cachyos". Steht in CompatToolMapping ein
# Name, den Steam nicht kennt, bleibt der Haken in Steam AUS und das Spiel
# laeuft ohne Proton.
def _compat_tool_internal_name(folder):
    for d in compat_tools_dirs() + system_compat_tools_dirs():
        vdf = os.path.join(d, folder, "compatibilitytool.vdf")
        if not os.path.isfile(vdf):
            continue
        try:
            with open(vdf, errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        # Kommentare entfernen: GE schreibt hinter den Namen
        # '// Internal name of this tool' — zwischen Name und '{' haette die
        # Suche unten sonst nichts gefunden und still den Ordnernamen genommen.
        text = re.sub(r"//[^\n]*", "", text)
        span = _vdf_find_block(text, "compat_tools")
        if span is None:
            continue
        m = re.search(r'"([^"]+)"\s*\{', text[span[0] + 1:span[1]])
        if m:
            return m.group(1)
    return folder


# Valves eigene Proton-Versionen sind Steam-Apps (steamapps/common/Proton
# 10.0) und haben keine compatibilitytool.vdf. Ihre internen Namen folgen
# einem festen Schema: "Proton 10.0" -> proton_10, "Proton 5.13" ->
# proton_513, dazu proton_experimental und proton_hotfix.
_VALVE_SPECIAL = {"proton - experimental": "proton_experimental",
                  "proton experimental": "proton_experimental",
                  "proton hotfix": "proton_hotfix"}
_VALVE_NUMBERED = re.compile(r"^proton (\d+)\.(\d+)$", re.IGNORECASE)


def _valve_internal_name(folder):
    low = folder.strip().lower()
    if low in _VALVE_SPECIAL:
        return _VALVE_SPECIAL[low]
    m = _VALVE_NUMBERED.match(low)
    if not m:
        return None
    major, minor = m.groups()
    return f"proton_{major}" if minor == "0" else f"proton_{major}{minor}"


def installed_valve_protons():
    """[(interner Name, Hauptversion oder None)] aller installierten Valve-Protons."""
    found = []
    for sa in _steamapps_dirs():
        common = os.path.join(sa, "common")
        try:
            names = os.listdir(common)
        except OSError:
            continue
        for name in names:
            internal = _valve_internal_name(name)
            if not internal or not os.path.isfile(
                    os.path.join(common, name, "toolmanifest.vdf")):
                continue
            m = _VALVE_NUMBERED.match(name.strip())
            major = int(m.group(1)) if m else None
            if all(internal != f[0] for f in found):
                found.append((internal, major))
    return found


def valve_proton_mapping_name(proton):
    """
    Interner Name fuer „Proton N (Standard)" — oder None, wenn kein
    Valve-Proton installiert ist.

    Bevorzugt die Hauptversion aus dem Eintrag (Proton 11 → proton_11),
    sonst die neueste installierte nummerierte, sonst Experimental.
    """
    installed = installed_valve_protons()
    if not installed:
        return None
    m = re.search(r"(\d+)", proton.get("version", "") or "")
    wanted = int(m.group(1)) if m else None
    numbered = sorted((f for f in installed if f[1] is not None), key=lambda f: f[1])
    for internal, major in numbered:
        if major == wanted:
            return internal
    if numbered:
        return numbered[-1][0]
    names = [f[0] for f in installed]
    return "proton_experimental" if "proton_experimental" in names else names[0]


def compat_mapping_name(proton):
    """
    Was „Use" in CompatToolMapping schreibt. Rueckgabe: (name, fehler)
      name   : interner Tool-Name — der Haken in Steam ist damit IMMER gesetzt
      fehler : "not_installed" | "valve_missing" | ""

    Frueher bedeutete „Proton N (Standard)": Eintrag entfernen, Steam nimmt
    sein Standard-Proton. Fuer Windows-Spiele aus dem Store stimmt das, fuer
    Nicht-Steam-Spiele nicht — ohne Eintrag startet Steam die .exe ganz ohne
    Proton. Deshalb wird jetzt auch Valves Proton ausdruecklich eingetragen.
    """
    folder, found, kind = resolve_steam_tool(proton)
    if not found:
        return None, "not_installed"
    if kind == "steam_default":
        name = valve_proton_mapping_name(proton)
        return (name, "") if name else (None, "valve_missing")
    return _compat_tool_internal_name(folder), ""


def steam_shutdown_cmd():
    """Befehl, um den laufenden Steam-Client sauber zu beenden."""
    if shutil.which("steam"):
        return ["steam", "-shutdown"]
    if venv.steam_is_flatpak() and shutil.which("flatpak"):
        return ["flatpak", "run", "com.valvesoftware.Steam", "-shutdown"]
    return None


def set_steam_launch_options(appid, options):
    """
    Schreibt die Startparameter eines Spiels in ALLE gefundenen
    localconfig.vdf (userdata/<uid>/config) -> apps/<appid>/LaunchOptions.
    Rückgabe: (ok: bool, fehlertext: str) — ok, wenn mindestens eine
    Datei geschrieben wurde.
    """
    appid = str(appid)
    if steam_shortcuts.is_shortcut_id(appid):
        # Nicht-Steam-Spiele: das Feld steht in shortcuts.vdf (binaer).
        return steam_shortcuts.set_launch_options(appid, options)
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
                with open(path, errors="ignore") as f:
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
    if steam_shortcuts.is_shortcut_id(appid):
        # -applaunch kennt nur echte Steam-Spiele. Nicht-Steam-Spiele startet
        # Steam ausschliesslich ueber die 64-Bit-Spiel-ID.
        url = f"steam://rungameid/{steam_shortcuts.game_id(appid)}"
        if shutil.which("steam"):
            return ["steam", url]
        if venv.steam_is_flatpak() and shutil.which("flatpak"):
            return ["flatpak", "run", "com.valvesoftware.Steam", url]
        if shutil.which("xdg-open"):
            return ["xdg-open", url]
        return None
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
    sel = _load_app_config().get("games_selected_proton", {})
    if not isinstance(sel, dict):
        sel = {}
    sel[str(appid)] = version
    if not update_json(APP_CONFIG, {"games_selected_proton": sel}):
        log.warning("Proton-Auswahl konnte nicht gespeichert werden.")


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
        # Feral GameMode-Wrapper. Wie mullvad-exclude ein Wrapper -> "before".
        # Spiele, die gamemoderun schon in ihren Basis-Parametern haben (z. B.
        # VRChat), bekommen es durch die Dublettenprüfung in
        # compose_launch_options nicht doppelt.
        "key": "gamemoderun",
        "arg": "gamemoderun",
        "position": "before",
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


def compose_launch_options(base, enabled_keys, custom="", extra_toggles=None):
    """
    Baut den finalen Steam-Startparameter-String aus:
      base          : hinterlegte Parameter des Spiels (z. B. VRChat) oder ""
      enabled_keys  : Menge/Liste der aktiven Toggle-Keys
      custom        : eigene Zusatz-Parameter des Nutzers
      extra_toggles : spiel-eigene Toggle-Definitionen (game_toggle(...)),
                      zusätzlich zu den globalen LAUNCH_TOGGLES

    Wrapper landen vor %command%, Spiel-Argumente dahinter — egal in welcher
    Reihenfolge sie zugeschaltet werden. Doppelte Parameter werden vermieden.
    Enthält 'custom' selbst ein %command%, wird es korrekt auf beide Seiten
    aufgeteilt (so lassen sich auch eigene Wrapper wie 'mangohud' setzen).
    """
    enabled = set(enabled_keys or ())
    prefix, suffix = _split_command(base)

    # Wrapper, die die GANZE restliche Zeile umschliessen (position "wrap"),
    # z. B. der VRCVideoCacher-Autostart. Sie sind kein normaler Prefix-Token:
    # sie muessen VOR gamemoderun & Co. stehen, weil hinter ihrem '--' alles
    # Weitere als Argumentliste landet.
    wraps = []

    for t in list(LAUNCH_TOGGLES) + list(extra_toggles or ()):
        if t["key"] not in enabled:
            continue
        if t["position"] == "wrap":
            if t["arg"] and t["arg"] not in wraps:
                wraps.append(t["arg"])
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

    # Reihenfolge: Umgebungsvariablen, dann die umschliessenden Wrapper,
    # dann die normalen Wrapper, dann %command% und die Spiel-Argumente.
    # Env-Zuweisungen ganz nach vorne, damit sie fuer alles darunter gelten.
    env = [p for p in prefix if _is_env_assignment(p)]
    rest = [p for p in prefix if not _is_env_assignment(p)]
    return " ".join(env + wraps + rest + [COMMAND_TOKEN] + suffix)


def _is_env_assignment(token):
    """True fuer 'PROTON_LOG=1', False fuer 'gamemoderun' oder '--flag=wert'.
    Ein Gleichheitszeichen allein reicht nicht: Optionen wie '--foo=bar'
    sind Argumente, keine Zuweisungen. Shell-Regel: der Name vor dem '='
    besteht aus Buchstaben, Ziffern und Unterstrich und faengt nicht mit
    einer Ziffer an."""
    name, sep, _ = (token or "").partition("=")
    return bool(sep) and bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name))


def has_saved_launch_toggles(appid):
    """True, wenn für dieses Spiel schon einmal eine Toggle-Auswahl gespeichert
    wurde. Solange False, greifen die Spiel-Vorgaben (game['default_on'] und
    game_toggle(default=True))."""
    data = _load_app_config().get("games_launch_toggles", {})
    return isinstance(data, dict) and str(appid) in data


def load_launch_toggles(appid, extra_toggles=None):
    """
    Gemerkte Einstellung eines Spiels.
    Rückgabe: (aktive_toggle_keys: list, custom: str)
    extra_toggles: spiel-eigene Toggle-Defs, damit deren Keys nicht als
                   unbekannt herausgefiltert werden.
    """
    data = _load_app_config().get("games_launch_toggles", {})
    entry = data.get(str(appid), {}) if isinstance(data, dict) else {}
    if not isinstance(entry, dict):
        return [], ""
    known = {t["key"] for t in LAUNCH_TOGGLES} | {t["key"] for t in (extra_toggles or ())}
    keys = [k for k in entry.get("toggles", []) if k in known]
    # Den Autostart-Wrapper aus Vorabstaenden herausnehmen. Der Schalter
    # selbst faellt schon durch den known-Filter oben weg, aber wer ihn
    # ueber das Feld fuer eigene Parameter uebernommen hatte, haette ihn
    # sonst dauerhaft drin.
    custom = strip_legacy_vrcvideocacher_wrapper(entry.get("custom", "") or "")
    return keys, custom


def save_launch_toggles(appid, enabled_keys, custom):
    """Merkt Toggles + eigene Parameter eines Spiels dauerhaft in der Config."""
    all_t = _load_app_config().get("games_launch_toggles", {})
    if not isinstance(all_t, dict):
        all_t = {}
    all_t[str(appid)] = {"toggles": list(enabled_keys),
                         "custom": (custom or "").strip()}
    if not update_json(APP_CONFIG, {"games_launch_toggles": all_t}):
        log.warning("Startparameter-Toggles konnten nicht gespeichert werden.")
