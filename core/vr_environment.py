#!/usr/bin/env python3
"""
vr_environment.py — Zentrale Pfad-/Umgebungs-Auflösung für yakuda-connect
=========================================================================
Eine einzige Wahrheit für alle install-methoden-abhängigen Pfade, damit das
Tool nicht nur auf Arch (yay/paru), sondern auch mit Flatpak- und Nix-
Installationen funktioniert.

Grundprinzip:
  * Native/Arch-Pfade sind der bewährte Standard (Verhalten bleibt gleich).
  * Für Flatpak/Nix wird per Discovery (Dateisuche) der passende Pfad gefunden.
  * Steam als Flatpak wird erkannt; OpenXR/OpenVR-Configs werden dann ZUSÄTZLICH
    in das Steam-Flatpak-Verzeichnis geschrieben, damit auch das gesandboxte
    Steam die WiVRn-Runtime findet ("OpenXR-SteamFix").

Installationsmethode wird in der App-Config gespeichert
(~/.config/yakuda-connect/config/config.json -> "runtime_install_method") und
hier nur als Hinweis genutzt; die Discovery funktioniert auch ohne.
"""
import os
import json
import shutil

from logging_setup import get_logger
from jsonio import read_json, update_json, write_json_atomic

log = get_logger("vr_environment")


HOME = os.path.expanduser("~")
APP_CONFIG = os.path.join(HOME, ".config/yakuda-connect/config/config.json")

STEAM_FLATPAK_BASE = os.path.join(HOME, ".var/app/com.valvesoftware.Steam")


# --------------------------------------------------------------------------- #
#  Installationsmethode (in Config gemerkt)
# --------------------------------------------------------------------------- #
def get_runtime_method():
    """Gemerkte Methode der WiVRn-Runtime: 'yay'|'paru'|'flatpak'|'nix'|''."""
    try:
        with open(APP_CONFIG) as f:
            return json.load(f).get("runtime_install_method", "") or ""
    except Exception:
        return ""


def set_runtime_method(method):
    """Speichert die Methode der WiVRn-Runtime in der App-Config."""
    if not update_json(APP_CONFIG, {"runtime_install_method": method}):
        log.warning("runtime_install_method konnte nicht gespeichert werden.")


# --------------------------------------------------------------------------- #
#  Steam-Erkennung (nativ vs. Flatpak)
# --------------------------------------------------------------------------- #
def steam_is_flatpak():
    return os.path.isdir(STEAM_FLATPAK_BASE)


def steam_data_roots():
    """Mögliche Steam-Datenverzeichnisse (enthalten 'steamapps'), nativ + Flatpak."""
    roots = []
    if steam_is_flatpak():
        roots += [
            os.path.join(STEAM_FLATPAK_BASE, ".local/share/Steam"),
            os.path.join(STEAM_FLATPAK_BASE, ".steam/steam"),
        ]
    roots += [
        os.path.join(HOME, ".local/share/Steam"),
        os.path.join(HOME, ".steam/steam"),
        os.path.join(HOME, ".steam/root"),
    ]
    existing = [r for r in roots if os.path.isdir(r)]
    return existing or roots


# --------------------------------------------------------------------------- #
#  OpenXR / OpenVR Config-Verzeichnisse (wo active_runtime / openvrpaths liegen)
# --------------------------------------------------------------------------- #
def openxr_config_dirs():
    """
    Alle Verzeichnisse, in die active_runtime.json geschrieben werden soll.
    Host-Config immer; bei Steam-Flatpak zusätzlich dessen Sandbox-Config,
    damit das gesandboxte Steam die WiVRn-Runtime findet.
    """
    dirs = [os.path.join(HOME, ".config/openxr/1")]
    if steam_is_flatpak():
        dirs.append(os.path.join(STEAM_FLATPAK_BASE, ".config/openxr/1"))
    return dirs


def openvr_config_dirs():
    dirs = [os.path.join(HOME, ".config/openvr")]
    if steam_is_flatpak():
        dirs.append(os.path.join(STEAM_FLATPAK_BASE, ".config/openvr"))
    return dirs


def primary_active_runtime():
    """Host-Pfad der active_runtime.json (für Statusanzeigen)."""
    return os.path.join(HOME, ".config/openxr/1/active_runtime.json")


# --------------------------------------------------------------------------- #
#  WiVRn OpenXR-Manifest + Bibliotheken (methoden-/distro-unabhängig)
# --------------------------------------------------------------------------- #
def _manifest_candidates():
    c = [
        "/usr/share/openxr/1/openxr_wivrn.json",                                  # nativ (Arch/Fedora)
        os.path.join(HOME, ".local/share/openxr/1/openxr_wivrn.json"),            # Selbstbau (Ubuntu)
        "/usr/local/share/openxr/1/openxr_wivrn.json",                            # make install
    ]
    return c


def find_wivrn_manifest():
    """Pfad zum openxr_wivrn.json (nativ/selbstgebaut). Fällt auf Arch-Default zurück."""
    for p in _manifest_candidates():
        if os.path.exists(p):
            return p
    return "/usr/share/openxr/1/openxr_wivrn.json"


# --------------------------------------------------------------------------- #
#  ELF-Klasse einer .so bestimmen (32/64 Bit)
# --------------------------------------------------------------------------- #
def elf_class(path):
    """
    Liefert 32, 64 oder None (keine ELF-Datei / nicht lesbar).

    Wichtig fuer Steam: pressure-vessel laesst 'capsule-capture-libs' ueber
    JEDES Manifest in /usr/share/openxr/1 laufen. Zeigt ein 64-Bit-Manifest
    auf eine 32-Bit-.so (oder umgekehrt), bricht Steam mit
    "gelf_getehdr(...): invalid `Elf' handle" ab.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(5)
        if head[:4] != b"\x7fELF":
            return None
        return 32 if head[4] == 1 else 64
    except Exception:
        return None


def is_elf64(path):
    return elf_class(path) == 64


def find_wivrn_libs():
    """
    (libopenxr_wivrn.so, libmonado_wivrn.so) als absolute Pfade.
    Erst aus dem Manifest auflösen, sonst in bekannten Verzeichnissen suchen.
    """
    man = find_wivrn_manifest()
    try:
        with open(man) as f:
            data = json.load(f)
        rt = data.get("runtime", {})
        base = os.path.dirname(man)
        lib = rt.get("library_path")
        mon = rt.get("MND_libmonado_path")
        lib_abs = os.path.normpath(os.path.join(base, lib)) if lib else None
        mon_abs = os.path.normpath(os.path.join(base, mon)) if mon else None
        # Nur uebernehmen, wenn es wirklich eine 64-Bit-.so ist. Ein aus einem
        # fremden Backup stammendes Manifest kann auf eine 32-Bit-Bibliothek
        # zeigen (z. B. Arch-Pfad /usr/lib/wivrn auf Fedora = 32 Bit) - das
        # wuerde den Steam-Fix genau den Fehler schreiben, den er beheben soll.
        if lib_abs and os.path.exists(lib_abs) and is_elf64(lib_abs):
            if not (mon_abs and os.path.exists(mon_abs) and is_elf64(mon_abs)):
                sib = os.path.join(os.path.dirname(lib_abs), "libmonado_wivrn.so")
                mon_abs = sib if os.path.exists(sib) else None
            return lib_abs, mon_abs
    except Exception as exc:
        log.debug("find_wivrn_libs: ignoriert — %s", exc)

    # Reihenfolge bewusst: lib64 zuerst (Fedora/openSUSE), dann Arch/Debian.
    lib_dirs = [
        "/usr/lib64/wivrn", "/usr/lib/wivrn", "/usr/lib/x86_64-linux-gnu/wivrn",
        "/usr/lib64", "/usr/lib", "/usr/lib/x86_64-linux-gnu",
        "/usr/local/lib64/wivrn", "/usr/local/lib/wivrn",
    ]
    openxr = monado = None
    for d in lib_dirs:
        if not os.path.isdir(d):
            continue
        co = os.path.join(d, "libopenxr_wivrn.so")
        cm = os.path.join(d, "libmonado_wivrn.so")
        if openxr is None and is_elf64(co):
            openxr = co
        if monado is None and is_elf64(cm):
            monado = cm
        if openxr and monado:
            break
    return openxr, monado


def find_wivrn_libs32():
    """
    32-Bit-Gegenstuecke (fuer die *.i686.json-Manifeste). Arch legt sie nach
    /usr/lib32/wivrn, Fedora nach /usr/lib/wivrn, Debian nach
    /usr/lib/i386-linux-gnu/wivrn.
    """
    lib_dirs = [
        "/usr/lib32/wivrn", "/usr/lib/wivrn", "/usr/lib/i386-linux-gnu/wivrn",
        "/usr/lib32", "/usr/lib", "/usr/lib/i386-linux-gnu",
    ]
    openxr = monado = None
    for d in lib_dirs:
        if not os.path.isdir(d):
            continue
        co = os.path.join(d, "libopenxr_wivrn.so")
        cm = os.path.join(d, "libmonado_wivrn.so")
        if openxr is None and elf_class(co) == 32:
            openxr = co
        if monado is None and elf_class(cm) == 32:
            monado = cm
        if openxr and monado:
            break
    return openxr, monado


# --------------------------------------------------------------------------- #
#  OpenVR-Kompatibilität (xrizer / OpenComposite / VapoR)
# --------------------------------------------------------------------------- #
# Diese Liste ist KEINE eigene Erfindung, sondern exakt WiVRns
# OVR_COMPAT_SEARCH_PATH aus dessen CMakeLists.txt — in derselben Reihenfolge:
#
#   /opt/xrizer:/usr/local/lib/OpenComposite:/usr/lib/OpenComposite:
#   /opt/OpenComposite:/opt/opencomposite:/opt/VapoR:/usr/local/lib/VapoR
#
# Warum das wichtig ist: Steht in WiVRns config.json KEIN
# 'openvr-compat-path', sucht WiVRn genau diese Orte ab und nimmt den ersten,
# der existiert (server/active_runtime.cpp). Wer wissen will, was "Standard"
# bedeutet, muss also dieselbe Liste in derselben Reihenfolge kennen.
#
# Hinweis: Distributionen können die Liste beim Bauen überschreiben
# (CACHE STRING). Deshalb ist sie hier nur die Grundlage der Anzeige, nie eine
# Garantie — gesetzt wird immer ein absoluter Pfad.
WIVRN_OVR_SEARCH_PATH = (
    "/opt/xrizer",
    "/usr/local/lib/OpenComposite",
    "/usr/lib/OpenComposite",
    "/opt/OpenComposite",
    "/opt/opencomposite",
    "/opt/VapoR",
    "/usr/local/lib/VapoR",
)

# Orte, die WiVRn NICHT von sich aus absucht, an denen Distributionen die
# Bibliotheken aber trotzdem ablegen. Wird hier etwas gefunden, ist es
# auswählbar — aber nur, weil wir den Pfad dann explizit eintragen. Genau das
# sagt die Oberfläche dazu auch.
#
# ACHTUNG Fedora: dort liegt die Bibliothek eine Ebene TIEFER, naemlich unter
# ``<ordner>/runtime/bin/linux64/vrclient.so`` (belegt am Dateilisting des
# offiziellen RPMs opencomposite: /usr/lib64/opencomposite/runtime/bin/...).
# Deshalb reicht es nicht, den Basisordner zu kennen — siehe
# resolve_compat_root() weiter unten.
EXTRA_OVR_PATHS = (
    "/usr/lib64/xrizer/runtime",                      # Fedora COPR (Sollpfad)
    "/usr/lib64/xrizer",                              # Fedora (COPR @xr-sig/xrizer)
    "/usr/lib/xrizer",
    "/usr/lib64/opencomposite/runtime",               # Fedora RPM (Sollpfad)
    "/usr/lib64/opencomposite",                       # Fedora (offizielle Repos)
    "/usr/lib/opencomposite",
    "/usr/lib64/OpenComposite",
    os.path.join(HOME, ".local/share/xrizer"),        # Selbstbau / GitHub-Release
    os.path.join(HOME, ".local/share/opencomposite"),
)

# Unterordner, in denen Distributionen die eigentliche Runtime verstecken.
# "runtime" ist das Fedora-Layout; die Liste wird VOR dem allgemeinen Scan
# geprueft, damit der haeufige Fall ohne Verzeichnis-Durchlauf auskommt.
NESTED_COMPAT_SUBDIRS = ("runtime",)


def openvr_lib_file(path):
    """
    Pfad der vrclient.so, die WiVRn in einem Kompatibilitäts-Ordner erwartet.

    WiVRn prüft (server/active_runtime.cpp) auf x86_64 genau
    ``<ordner>/bin/linux64/vrclient.so`` und schreibt sonst eine Warnung in
    sein Log. Dieselbe Prüfung hier — damit die App genau das anzeigt, was
    WiVRn später auch bemängeln würde.
    """
    return os.path.join(path, "bin", "linux64", "vrclient.so")


def looks_like_openvr_compat(path):
    """
    Enthält der Ordner wirklich eine OpenVR-Ersatzbibliothek?

    Ein leerer Ordner (Paket entfernt, Reste geblieben) darf nicht als
    "installiert" durchgehen — WiVRn würde sonst auf einen Pfad zeigen, unter
    dem kein Spiel startet, und im Log steht nur eine Zeile, die niemand liest.
    """
    if not path or not os.path.isdir(path):
        return False
    if os.path.exists(openvr_lib_file(path)):
        return True
    # Andere Architektur (arm64) oder ungewöhnliches Layout: WiVRn prüft dort
    # gar nicht erst, deshalb hier großzügiger — irgendeine vrclient.so reicht.
    for rel in ("bin/vrclient.so", "bin/linux32/vrclient.so"):
        if os.path.exists(os.path.join(path, rel)):
            return True
    return False


def resolve_compat_root(path):
    """
    Der Ordner, den WiVRn wirklich braucht — also der, unter dem
    ``bin/linux64/vrclient.so`` liegt.

    Hintergrund: Arch (AUR) packt die Bibliothek direkt nach
    ``/opt/opencomposite/bin/linux64/vrclient.so``. Fedora legt sie eine Ebene
    tiefer ab: ``/usr/lib64/opencomposite/runtime/bin/linux64/vrclient.so``.
    Wer nur den Basisordner prueft, meldet auf Fedora fuer eine voellig
    intakte Installation "no vrclient.so" — und traegt bei Auswahl auch noch
    einen Pfad in WiVRns config.json ein, unter dem kein Spiel startet.

    Gesucht wird in dieser Reihenfolge:
      1. der Ordner selbst
      2. die bekannten Zwischenordner (NESTED_COMPAT_SUBDIRS, z. B. "runtime")
      3. eine Ebene tiefer, alphabetisch — fuer Layouts, die wir noch nicht
         kennen

    Wird nirgends etwas gefunden, kommt der Ausgangspfad unveraendert zurueck.
    Der Aufrufer entscheidet dann ueber looks_like_openvr_compat(), ob der
    Ordner unvollstaendig ist.
    """
    if not path or not os.path.isdir(path):
        return path
    if looks_like_openvr_compat(path):
        return path
    for sub in NESTED_COMPAT_SUBDIRS:
        candidate = os.path.join(path, sub)
        if looks_like_openvr_compat(candidate):
            return candidate
    try:
        # Nur EINE Ebene, und sortiert: das Ergebnis darf nicht davon
        # abhaengen, in welcher Reihenfolge das Dateisystem liefert.
        for name in sorted(os.listdir(path)):
            candidate = os.path.join(path, name)
            if os.path.isdir(candidate) and looks_like_openvr_compat(candidate):
                return candidate
    except OSError as exc:
        log.debug("resolve_compat_root(%s): %s", path, exc)
    return path


def normalize_compat_path(path):
    """
    Räumt einen vom Nutzer gewählten Ordner auf.

    Wer im Dateidialog sucht, landet fast zwangsläufig eine oder zwei Ebenen
    zu tief — die interessante Datei liegt ja in ``bin/linux64``. WiVRns
    eigenes Dashboard schneidet genau diese beiden Endungen wieder ab
    (dashboard/qml/SettingsPage.qml), hier passiert dasselbe.
    """
    cleaned = (path or "").rstrip("/")
    for suffix in ("/linux64", "/linux32", "/bin"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
    # Wer auf Fedora /usr/lib64/opencomposite auswaehlt, meint den Ordner
    # darunter — sonst zeigt der Eintrag ins Leere.
    return resolve_compat_root(cleaned)


def openvr_compat_candidates():
    """
    Alle gefundenen Kompatibilitäts-Ordner, in WiVRns Suchreihenfolge.

    Rückgabe je Eintrag:
        path        absoluter Pfad
        label       Anzeigename (xrizer / OpenComposite / VapoR + Pfad)
        autodetect  True, wenn WiVRn diesen Ordner auch ohne Eintrag fände
        complete    True, wenn bin/linux64/vrclient.so existiert

    Wie WiVRns Dashboard werden nur EXISTIERENDE Orte gelistet — eine
    Auswahl, die es nicht gibt, hilft niemandem.
    """
    seen = set()
    result = []
    for path, autodetect in ([(p, True) for p in WIVRN_OVR_SEARCH_PATH] +
                             [(p, False) for p in EXTRA_OVR_PATHS]):
        if not os.path.isdir(path):
            continue
        # Fedora & Co. verschachteln eine Ebene tiefer. Gelistet wird der
        # Ordner, der die Bibliothek WIRKLICH enthaelt — denn genau der landet
        # bei Auswahl in WiVRns config.json.
        resolved = resolve_compat_root(path)
        real = os.path.realpath(resolved)
        if real in seen:
            continue
        seen.add(real)
        result.append({
            "path": resolved,
            "label": _compat_label(path),
            # Musste erst umgebogen werden? Dann findet WiVRn den Ordner ohne
            # ausdruecklichen Eintrag nicht — auch wenn der Basisordner in der
            # Suchliste steht.
            "autodetect": autodetect and resolved == path,
            "complete": looks_like_openvr_compat(resolved),
        })
    return result


def _compat_label(path):
    """Klarname aus dem Pfad ableiten (xrizer / OpenComposite / VapoR)."""
    low = os.path.basename(path.rstrip("/")).lower()
    if "xrizer" in low:
        return "xrizer"
    if "opencomposite" in low:
        return "OpenComposite"
    if "vapor" in low:
        return "VapoR"
    return os.path.basename(path.rstrip("/")) or path


def wivrn_autodetect_path():
    """
    Welchen Ordner nähme WiVRn ohne Eintrag in der config.json?

    Bildet server/active_runtime.cpp nach: der erste EXISTIERENDE Eintrag aus
    WIVRN_OVR_SEARCH_PATH gewinnt. "" heißt: WiVRn fände von selbst nichts.
    """
    for path in WIVRN_OVR_SEARCH_PATH:
        if os.path.exists(path):
            return path
    return ""


def find_openvr_compat(name):
    """
    Erster gefundener Ordner eines bestimmten Werkzeugs ("xrizer",
    "opencomposite", "vapor") oder "" — nur wenn dort auch wirklich eine
    vrclient.so liegt.
    """
    wanted = name.lower().replace(" ", "")
    for entry in openvr_compat_candidates():
        if entry["label"].lower() == wanted and entry["complete"]:
            return entry["path"]
    return ""


def find_opencomposite():
    """Alter Name — bleibt für backup_manager.py & Co. erhalten."""
    return find_openvr_compat("opencomposite") or "/opt/opencomposite"


def find_xrizer():
    """Alter Name — bleibt für main.py (Fedora-COPR-Hinweis) erhalten."""
    return find_openvr_compat("xrizer") or "/opt/xrizer"


# --------------------------------------------------------------------------- #
#  SteamVR-Manifest (für Runtime-Umschaltung)
# --------------------------------------------------------------------------- #
def find_steamvr_manifest():
    for root in steam_data_roots():
        p = os.path.join(root, "steamapps/common/SteamVR/steamxr_linux64.json")
        if os.path.exists(p):
            return p
    # Default (nativ)
    return os.path.join(HOME, ".local/share/Steam/steamapps/common/SteamVR/steamxr_linux64.json")


def resolve_manifest_libs(manifest):
    """
    ``(library_path, MND_libmonado_path)`` eines Runtime-Manifests, absolut.

    Relative Angaben werden auf den Ordner des Manifests bezogen — genau so,
    wie es die OpenXR-Spezifikation vorsieht. SteamVRs eigenes
    ``steamxr_linux64.json`` enthaelt z. B. ``./bin/linux64/steamxr_linux64.so``.
    Nicht existierende oder nicht-64-Bit-Dateien werden als ``None`` gemeldet.
    """
    try:
        with open(manifest) as f:
            data = json.load(f)
        rt = data.get("runtime", {})
    except Exception as exc:
        log.debug("resolve_manifest_libs (%s): %s", manifest, exc)
        return None, None

    base = os.path.dirname(manifest)

    def _abs(value):
        if not value:
            return None
        path = value if os.path.isabs(value) else os.path.normpath(os.path.join(base, value))
        return path if os.path.exists(path) and is_elf64(path) else None

    return _abs(rt.get("library_path")), _abs(rt.get("MND_libmonado_path"))


def find_steamvr_lib():
    """
    Absoluter Pfad zu SteamVRs OpenXR-Bibliothek (``steamxr_linux64.so``) —
    oder "" , wenn SteamVR nicht (vollstaendig) installiert ist.

    Warum ueberhaupt: in ``active_runtime.json`` gehoert der Pfad einer
    Bibliothek, KEIN Pfad auf ein weiteres Manifest. Steht dort eine .json,
    versucht der Loader sie als Bibliothek zu oeffnen — das ist genau der
    Fehler "invalid `Elf' handle", an dem Steams pressure-vessel scheitert.
    """
    manifest = find_steamvr_manifest()
    lib, _mon = resolve_manifest_libs(manifest)
    if lib:
        return lib
    # Fallback: fester Ort innerhalb der SteamVR-Installation
    cand = os.path.join(os.path.dirname(manifest), "bin", "linux64", "steamxr_linux64.so")
    return cand if os.path.exists(cand) and is_elf64(cand) else ""


# --------------------------------------------------------------------------- #
#  wivrn-server-Binary + CAP_SYS_NICE-Tauglichkeit
# --------------------------------------------------------------------------- #
def wivrn_server_binary():
    p = shutil.which("wivrn-server")
    return os.path.realpath(p) if p else None


def supports_setcap():
    """
    setcap (CAP_SYS_NICE) ist nur bei einer beschreibbaren, nativen Binary sinnvoll.
    Bei Nix (/nix/store, read-only) und Flatpak (Sandbox) funktioniert es nicht.
    """
    b = wivrn_server_binary()
    if not b:
        return False
    if b.startswith("/nix/store") or "/flatpak/" in b or "/.var/app/" in b:
        return False
    return True


# --------------------------------------------------------------------------- #
#  VRChat Proton-Prefix (für den Bilder-Symlink) — nativ + Flatpak-Steam
# --------------------------------------------------------------------------- #
def vrchat_proton_prefix():
    """Findet das VRChat-Proton-Prefix (AppID 438100), nativ oder Flatpak-Steam."""
    rel = "steamapps/compatdata/438100/pfx/drive_c/users/steamuser"
    for root in steam_data_roots():
        p = os.path.join(root, rel)
        if os.path.isdir(p):
            return p
    # Default: nativ
    return os.path.join(HOME, ".local/share/Steam", rel)


# --------------------------------------------------------------------------- #
#  WiVRn-Config-Datei (Sandbox-bewusst!)
# --------------------------------------------------------------------------- #
def wivrn_config_dir():
    """
    Verzeichnis der WiVRn-config.json — immer der native Host-Pfad.
    (WiVRn-Flatpak wird nicht mehr unterstützt: nativ = schlanker + schneller.)
    """
    return os.path.join(HOME, ".config/wivrn")


def wivrn_config_file():
    return os.path.join(wivrn_config_dir(), "config.json")


# --------------------------------------------------------------------------- #
#  'openvr-compat-path' in WiVRns config.json lesen/schreiben
# --------------------------------------------------------------------------- #
# WiVRn kennt für diesen Schlüssel DREI Zustände (server/driver/configuration.h:
# std::variant<std::monostate, std::string, std::nullptr_t>):
#
#   Schlüssel fehlt   -> Standard: WiVRn sucht selbst (OVR_COMPAT_SEARCH_PATH)
#   Schlüssel = Text  -> genau dieser Ordner wird benutzt
#   Schlüssel = null  -> WiVRn fasst die OpenVR-Konfiguration gar nicht an
#
# Ein LEERER Text ist kein vorgesehener Zustand. Er wirkt zwar zufällig wie
# "aus" (der zusammengesetzte Pfad ist leer), steht aber in keiner
# Dokumentation und kann sich jederzeit ändern — deshalb wird für "aus"
# echtes JSON-null geschrieben, genau wie WiVRns eigenes Dashboard es tut
# (dashboard/settings.cpp: set_openvr).
OPENVR_DEFAULT = "default"     # Schlüssel entfernen
OPENVR_DISABLED = "disabled"   # null schreiben
OPENVR_PATH = "path"           # Ordner eintragen


def current_openvr_compat():
    """
    Aktueller Zustand aus WiVRns config.json als ``(modus, pfad)``:

        ("default", "")      Schlüssel fehlt — WiVRn entscheidet selbst
        ("disabled", "")     null — WiVRn lässt OpenVR in Ruhe
        ("path", "/opt/...") fester Ordner
    """
    data = read_json(wivrn_config_file(), default=None)
    if not isinstance(data, dict) or "openvr-compat-path" not in data:
        return OPENVR_DEFAULT, ""
    value = data.get("openvr-compat-path")
    if value is None:
        return OPENVR_DISABLED, ""
    if isinstance(value, str) and value:
        return OPENVR_PATH, value
    # Leerer String: Altbestand aus früheren Versionen dieser App.
    return OPENVR_DISABLED, ""


def set_openvr_compat(mode, path=""):
    """
    Schreibt den Zustand in WiVRns config.json.

    Das ist die Konfiguration eines FREMDEN Programms: sie wird gelesen, an
    genau dieser Stelle geändert und atomar zurückgeschrieben — niemals neu
    aufgebaut.

    Wirksam wird die Änderung erst beim nächsten Start des WiVRn-Servers:
    der Pfad wird in active_runtime beim Hochfahren einmal ausgewertet.
    """
    file_path = wivrn_config_file()
    data = read_json(file_path, default={})
    if not isinstance(data, dict):
        log.warning("WiVRn-config.json enthält kein Objekt — wird neu aufgebaut.")
        data = {}

    if mode == OPENVR_DEFAULT:
        data.pop("openvr-compat-path", None)
    elif mode == OPENVR_DISABLED:
        data["openvr-compat-path"] = None
    else:
        data["openvr-compat-path"] = normalize_compat_path(path)

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    if write_json_atomic(file_path, data):
        log.info("openvr-compat-path -> %s", {
            OPENVR_DEFAULT: "entfernt (WiVRn entscheidet)",
            OPENVR_DISABLED: "null (abgeschaltet)",
        }.get(mode, f"'{path}'"))
        return True
    log.warning("WiVRn-config.json konnte nicht geschrieben werden (%s).", file_path)
    return False


# --------------------------------------------------------------------------- #
#  WiVRn-Version (entscheidet über das Format der config.json)
# --------------------------------------------------------------------------- #
def wivrn_version():
    """
    Version des installierten wivrn-server als Tupel, z. B. (25, 12) — oder
    ``None``, wenn sie sich nicht ermitteln lässt.

    ``wivrn-server --version`` gibt "WiVRn version 25.12" aus; bei
    Zwischenständen aus Git steht dort ein git-describe wie "25.12-30-gabc123".
    Beides wird auf die führenden Zahlen reduziert.
    """
    import re

    from proc import output_of

    out = output_of(["wivrn-server", "--version"], timeout=10)
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", out or "")
    if not m:
        return None
    return tuple(int(g) for g in m.groups() if g is not None)


def wivrn_at_least(major, minor):
    """
    Ist der installierte Server mindestens so neu? ``None`` (unbekannt) gilt
    als "ja" — neue Versionen sind der Normalfall, und das neue Format ist
    für alte Server bloß ein unbekannter Schlüssel, den sie ignorieren.
    """
    version = wivrn_version()
    if version is None:
        return True
    return version[:2] >= (major, minor)

