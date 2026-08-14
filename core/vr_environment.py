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
from jsonio import update_json

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
#  OpenVR-Kompatibilität (opencomposite / xrizer)
# --------------------------------------------------------------------------- #
def find_opencomposite():
    for p in ["/opt/opencomposite",                                    # Arch (AUR)
              "/usr/lib64/opencomposite",                              # Fedora (dnf)
              "/usr/lib/opencomposite",
              os.path.join(HOME, ".local/share/opencomposite")]:       # Selbstbau
        if os.path.isdir(p):
            return p
    return "/opt/opencomposite"


def find_xrizer():
    for p in ["/opt/xrizer",                                           # Arch (AUR)
              "/usr/lib64/xrizer",                                     # Fedora (COPR)
              "/usr/lib/xrizer",
              os.path.join(HOME, ".local/share/xrizer")]:              # Selbstbau
        if os.path.isdir(p):
            return p
    return "/opt/xrizer"


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


def openvr_compat_path(choice):
    """
    Wert für 'openvr-compat-path' — immer der native Host-Pfad
    (/opt/opencomposite bzw. /opt/xrizer, mit ~/.local-Fallbacks).
    """
    return find_opencomposite() if choice == "opencomposite" else find_xrizer()

