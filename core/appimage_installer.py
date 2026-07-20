#!/usr/bin/env python3
"""
appimage_installer.py — AppImage-basierte Installation für yakuda-connect
=========================================================================
Alternative zur AUR-/yay-Installation: Tools, die in programs.py mit
``"install_type": "appimage"`` markiert sind, werden NICHT über yay
installiert, sondern als AppImage direkt von GitHub geholt.

Beispiel-Ablauf für OSC Leash (key="oscleash", start_cmd="oscleash_app"):

  1. Ordnerstruktur anlegen (falls noch nicht vorhanden):
        ~/.config/yakuda-connect/tools/
        ~/.config/yakuda-connect/tools/oscleash/
        ~/.config/yakuda-connect/tools/desktop/

  2. AppImage in den Tool-Ordner herunterladen:
        ~/.config/yakuda-connect/tools/oscleash/OSCLeash-x86_64.AppImage

  3. AppImage ausführbar machen (chmod +x).

  4. Terminal-Befehl per Symlink bereitstellen:
        ~/.local/bin/oscleash_app  ->  .../oscleash/OSCLeash-x86_64.AppImage
     (Symlink, weil /usr auf SteamOS read-only ist – ~/.local/bin ist
      beschreibbar und liegt im PATH.)

  5. Icon aus dem Repository laden:
        ~/.config/yakuda-connect/tools/oscleash/icon.png

  6. .desktop-Datei schreiben und per Symlink für KDE/Plasma sichtbar machen:
        ~/.config/yakuda-connect/tools/desktop/oscleash.desktop
        ~/.local/share/applications/yakuda-oscleash.desktop  (Symlink)

Alle Schreibziele liegen unter $HOME und sind daher auch auf SteamOS
beschreibbar.
"""
import os
import json
import stat
import glob
import shutil
import subprocess
import time
import platform
import urllib.request
import urllib.error

from PySide6.QtCore import QThread, Signal

HOME = os.path.expanduser("~")
TOOLS_DIR        = os.path.join(HOME, ".config/yakuda-connect/tools")
DESKTOP_SRC_DIR  = os.path.join(TOOLS_DIR, "desktop")
LOCAL_BIN        = os.path.join(HOME, ".local/bin")
APPLICATIONS_DIR = os.path.join(HOME, ".local/share/applications")


# --------------------------------------------------------------------------- #
#  Pfad-Helfer (pro Tool)
# --------------------------------------------------------------------------- #
def _tool_dir(tool):
    return os.path.join(TOOLS_DIR, tool["key"])


def _appimage_filename(tool):
    # GitHub-Tools: stabiler Dateiname, damit der Symlink beim Update gleich bleibt
    if tool.get("github_repo"):
        return f"{tool['key']}.AppImage"
    url = tool.get("appimage_url", "")
    name = os.path.basename(url.split("?")[0])
    return name or f"{tool['key']}.AppImage"


def _appimage_path(tool):
    return os.path.join(_tool_dir(tool), _appimage_filename(tool))


def _icon_path(tool):
    return os.path.join(_tool_dir(tool), "icon.png")


def _bin_link(tool):
    """Pfad des Terminal-Befehls (z. B. ~/.local/bin/oscleash_app)."""
    cmd = tool.get("start_cmd") or tool["key"]
    return os.path.join(LOCAL_BIN, cmd)


def _desktop_src(tool):
    """Die 'echte' .desktop-Datei im yakuda-Ordner."""
    return os.path.join(DESKTOP_SRC_DIR, f"{tool['key']}.desktop")


def _desktop_link(tool):
    """Symlink im KDE-Anwendungsordner (eindeutiger Name mit yakuda-Präfix)."""
    return os.path.join(APPLICATIONS_DIR, f"yakuda-{tool['key']}.desktop")


def _marker(tool):
    """Kleine Marker-Datei mit der installierten Version."""
    return os.path.join(_tool_dir(tool), ".installed.json")


def _raw_github(url):
    """Wandelt eine GitHub 'blob'-URL in eine raw-URL um (idempotent)."""
    if "github.com" in url and "/blob/" in url:
        url = url.replace("https://github.com/", "https://raw.githubusercontent.com/")
        url = url.replace("/blob/", "/")
    return url


# --------------------------------------------------------------------------- #
#  GitHub-Release-Auflösung (für "immer neueste AppImage")
# --------------------------------------------------------------------------- #
class RateLimited(Exception):
    """GitHub-API hat das Anfragelimit gemeldet (HTTP 403)."""
    pass


_RELEASE_CACHE = {}      # repo -> (timestamp, url, version)
_RELEASE_CACHE_TTL = 900  # 15 Minuten — vermeidet zu viele API-Anfragen


def _api_get(url):
    """GET auf die GitHub-API. Wirft RateLimited bei HTTP 403."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "yakuda-connect",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise RateLimited(
                "GitHub-API-Limit erreicht (zu viele Anfragen pro Stunde). "
                "Bitte etwas warten und erneut versuchen."
            )
        raise


def _arch_tokens():
    """(bevorzugte, zu vermeidende) Architektur-Schlüsselwörter für dieses System."""
    m = (platform.machine() or "").lower()
    if m in ("x86_64", "amd64"):
        return (["x86_64", "amd64", "x64"],
                ["arm64", "aarch64", "armhf", "armv7", "i686", "i386"])
    if m in ("aarch64", "arm64"):
        return (["arm64", "aarch64"],
                ["x86_64", "amd64", "x64", "i686", "i386"])
    return ([m] if m else [], [])


def _pick_appimage_asset(assets, match=".AppImage"):
    """
    Wählt das passende AppImage-Asset.
      * Ist 'match' architektur-spezifisch gesetzt (z. B. '_x64.AppImage' oder
        'x86_64.AppImage'), wird genau das erste passende Asset genommen.
      * Ist 'match' der Standard '.AppImage', wird die Architektur automatisch
        erkannt (x64/x86_64 bevorzugt, arm64 etc. vermieden).
    """
    match_l = (match or ".AppImage").lower()
    cands = [a for a in assets if match_l in a.get("name", "").lower()]
    if not cands:
        return None, None

    # Vom Nutzer fest vorgegebene Endung -> direkt nehmen
    if match_l != ".appimage":
        return cands[0]["browser_download_url"], cands[0]["name"]

    # sonst: automatische Architektur-Erkennung
    prefer, avoid = _arch_tokens()
    for tok in prefer:
        for a in cands:
            if tok in a["name"].lower():
                return a["browser_download_url"], a["name"]

    # kein arch-Treffer: nur Assets ohne fremde Architektur zulassen
    neutral = [a for a in cands if not any(x in a["name"].lower() for x in avoid)]
    if neutral:
        return neutral[0]["browser_download_url"], neutral[0]["name"]

    return None, None


def _resolve_release_uncached(tool):
    repo = tool["github_repo"]
    match = tool.get("asset_match", ".AppImage")
    include_pre = tool.get("include_prerelease", False)

    releases = []
    # Nur stabile Releases? Dann reicht ein einziger API-Aufruf (/releases/latest).
    if not include_pre:
        try:
            rel = _api_get(f"https://api.github.com/repos/{repo}/releases/latest")
            if isinstance(rel, dict) and rel.get("assets") is not None:
                releases = [rel]
        except RateLimited:
            raise
        except Exception:
            releases = []
    # sonst (oder falls latest leer war) die Liste durchsuchen
    if not releases:
        data = _api_get(f"https://api.github.com/repos/{repo}/releases?per_page=15")
        releases = data if isinstance(data, list) else []

    for rel in releases:
        if rel.get("draft"):
            continue
        if rel.get("prerelease") and not include_pre:
            continue
        url, _name = _pick_appimage_asset(rel.get("assets", []), match)
        if url:
            return url, rel.get("tag_name", "")
    return None, ""


def resolve_release(tool):
    """
    Liefert (download_url, version). Bei github_repo wird die neueste passende
    Release per API gesucht (für die aktuelle Architektur). Der AppImage-Name
    darf sich pro Version ändern — es zählt nur das Asset aus der API.
    Wirft RateLimited bei API-Limit; andere Netzfehler werden durchgereicht.
    """
    repo = tool.get("github_repo")
    if not repo:
        return tool.get("appimage_url"), tool.get("version", "")

    now = time.time()
    cached = _RELEASE_CACHE.get(repo)
    if cached and (now - cached[0]) < _RELEASE_CACHE_TTL:
        return cached[1], cached[2]

    url, ver = _resolve_release_uncached(tool)
    if url:
        _RELEASE_CACHE[repo] = (now, url, ver)
    return url, ver


def latest_version(tool):
    """Neueste verfügbare Version/Tag (für den Update-Check). Schluckt Fehler -> ''."""
    repo = tool.get("github_repo")
    if not repo:
        return tool.get("version", "")
    try:
        _url, ver = resolve_release(tool)
        return ver or ""
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
#  Installationsmethoden (AppImage / yay / paru) – distro-abhängig
# --------------------------------------------------------------------------- #
def is_package_managed_install():
    """
    True, wenn yakuda-connect aus einem Distributionspaket läuft (z. B. AUR:
    /usr/share/yakuda-connect). Dann darf sich die App NICHT selbst updaten —
    das würde an pacman vorbei eine zweite Kopie unter /opt anlegen und die
    Paketverwaltung zerschießen. Updates laufen dort über yay/paru.

    False bei install.sh (/opt/yakuda-connect) und beim Start aus dem Quellcode.
    """
    here = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
    return here.startswith("/usr/")


def is_arch_based():
    """True, wenn die Distro auf Arch basiert (pacman/yay/paru-Welt)."""
    try:
        with open("/etc/os-release", "r") as f:
            for line in f:
                low = line.strip().lower()
                if low.startswith("id=") and "arch" in low:
                    return True
                if low.startswith("id_like=") and "arch" in low:
                    return True
    except Exception:
        pass
    return shutil.which("pacman") is not None


def _os_release_ids():
    """(id, id_like) aus /etc/os-release, alles lowercase."""
    osid, idlike = "", ""
    try:
        with open("/etc/os-release", "r") as f:
            for line in f:
                low = line.strip().lower()
                if low.startswith("id="):
                    osid = low[3:].strip('"')
                elif low.startswith("id_like="):
                    idlike = low[8:].strip('"')
    except Exception:
        pass
    return osid, idlike


def is_fedora_based():
    """True auf Fedora und Ableitungen (Nobara, Bazzite, ...)."""
    osid, idlike = _os_release_ids()
    if "fedora" in osid or "fedora" in idlike or "rhel" in idlike:
        return True
    return (not is_arch_based()) and shutil.which("dnf") is not None


def is_debian_based():
    """True auf Ubuntu/Debian und Ableitungen (Mint, Pop!_OS, ...)."""
    osid, idlike = _os_release_ids()
    if osid in ("ubuntu", "debian") or "debian" in idlike or "ubuntu" in idlike:
        return True
    return (not is_arch_based()) and (not is_fedora_based()) \
        and shutil.which("apt") is not None


def available_aur_helpers():
    """Installierte AUR-Helfer (['yay','paru'], yay zuerst) – nur auf Arch-Basis."""
    if not is_arch_based():
        return []
    return [h for h in ("yay", "paru") if shutil.which(h)]


def supported_methods(tool):
    """Abstrakte Methoden, die das Tool unterstützt – Teilmenge von {'appimage','aur'}."""
    m = tool.get("install_methods")
    if m:
        return list(m)
    if tool.get("install_type") == "appimage" or tool.get("github_repo") or tool.get("appimage_url"):
        return ["appimage"]
    return ["aur"]


def detect_install_methods(tool):
    """
    Konkrete, auf diesem System verfügbare Methoden (geordnet).
    Reihenfolge = Vorauswahl-Reihenfolge: appimage zuerst, dann yay, paru, flatpak.
      * Arch-Distros: yay/paru verfügbar (falls installiert).
      * Alle Distros : AppImage und – falls flatpak installiert + flatpak_id gesetzt – Flatpak.
    """
    supported = supported_methods(tool)
    methods = []
    if "appimage" in supported and (tool.get("github_repo") or tool.get("appimage_url")):
        methods.append("appimage")
    if "aur" in supported and tool.get("pkg"):
        methods.extend(available_aur_helpers())   # yay vor paru
    if "flatpak" in supported and tool.get("flatpak_id") and flatpak_available():
        methods.append("flatpak")
    return methods


def flatpak_available():
    """True, wenn 'flatpak' installiert ist (distro-unabhängig)."""
    return shutil.which("flatpak") is not None


def flathub_remote_present():
    """True, wenn das Flathub-Remote in Flatpak eingerichtet ist."""
    if not flatpak_available():
        return False
    try:
        res = subprocess.run(["flatpak", "remotes"],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        return res.returncode == 0 and "flathub" in res.stdout.lower()
    except Exception:
        return False


def add_flathub_remote():
    """Fügt das Flathub-Remote auf User-Ebene hinzu (ohne root). True bei Erfolg."""
    if not flatpak_available():
        return False
    try:
        res = subprocess.run(
            ["flatpak", "remote-add", "--if-not-exists", "--user",
             "flathub", "https://flathub.org/repo/flathub.flatpakrepo"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return res.returncode == 0
    except Exception:
        return False


def is_nixos():
    """True, wenn das System NixOS ist (laut /etc/os-release)."""
    try:
        with open("/etc/os-release", "r") as f:
            for line in f:
                low = line.strip().lower()
                if low.startswith("id=") and "nixos" in low:
                    return True
                if low.startswith("id_like=") and "nixos" in low:
                    return True
    except Exception:
        pass
    return False


def flatpak_query(tool):
    """(installiert, version) per 'flatpak info <id>'."""
    fid = tool.get("flatpak_id")
    if not fid or not flatpak_available():
        return False, ""
    res = subprocess.run(["flatpak", "info", fid],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    if res.returncode != 0:
        return False, ""
    version = ""
    for line in res.stdout.splitlines():
        l = line.strip()
        if l.lower().startswith("version:"):
            version = l.split(":", 1)[1].strip()
            break
    return True, version


def default_method(methods):
    """Vorauswahl-Priorität: AppImage -> yay -> flatpak -> erstes."""
    for pref in ("appimage", "yay", "flatpak"):
        if pref in methods:
            return pref
    return methods[0] if methods else ""


def available_update_methods():
    """
    Verfügbare Methoden für den Installations-Tab (nur noch NATIV, kein Flatpak):
      Arch    -> yay/paru
      Fedora  -> dnf (offizielle Repos: wivrn + opencomposite)
      Ubuntu  -> keine Methode: Install-Knopf zeigt eine Kurzanleitung,
                 Update-Knopf wird komplett ausgeblendet.
      Sonst   -> 'native', falls WiVRn selbst nativ installiert wurde.
    """
    methods = []
    if is_arch_based():
        methods.extend(available_aur_helpers())     # yay vor paru
    elif is_fedora_based():
        if shutil.which("dnf"):
            methods.append("dnf")
    elif is_debian_based():
        pass                                        # Ubuntu/Debian: nur Anleitung
    else:
        # Unbekannte Distro (z. B. NixOS): hat die Person WiVRn selbst installiert?
        if wivrn_native_present():
            methods.append("native")
    return methods


def wivrn_native_present():
    """True, wenn eine native wivrn-server-Binary im PATH liegt (kein Flatpak)."""
    return shutil.which("wivrn-server") is not None


def default_update_method(methods):
    """Vorauswahl: yay -> paru -> dnf -> native -> erstes."""
    for pref in ("yay", "paru", "dnf", "native"):
        if pref in methods:
            return pref
    return methods[0] if methods else ""


def pm_query(tool, helper):
    """(installiert, version, update) per yay/paru -Q. helper: 'yay' oder 'paru'."""
    pkg = tool.get("pkg")
    if not pkg or not shutil.which(helper):
        return False, "", False
    res = subprocess.run(f"{helper} -Q {pkg}", shell=True,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    if res.returncode != 0:
        return False, "", False
    version = res.stdout.strip().split()[-1] if res.stdout.strip() else ""
    res_u = subprocess.run(f"{helper} -Qu {pkg}", shell=True,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    has_update = res_u.returncode == 0 and bool(res_u.stdout.strip())
    return True, version, has_update


def compute_status(tool):
    """
    Voller Statusbericht eines Tools (als dict):
      appimage_installed / appimage_version / appimage_has_update
      pm_installed / pm_helper / pm_version / pm_has_update
      config_present
    """
    st = {
        "appimage_installed": False, "appimage_version": "", "appimage_has_update": False,
        "pm_installed": False, "pm_helper": "", "pm_version": "", "pm_has_update": False,
        "flatpak_installed": False, "flatpak_version": "",
        "config_present": False,
    }
    supported = supported_methods(tool)

    if "appimage" in supported and (tool.get("github_repo") or tool.get("appimage_url")):
        inst, ver = local_status(tool)
        st["appimage_installed"] = inst
        st["appimage_version"] = ver
        if inst:
            latest = latest_version(tool)
            st["appimage_has_update"] = bool(latest and ver and latest != ver)

    if "aur" in supported and tool.get("pkg"):
        for h in available_aur_helpers():   # yay zuerst
            ok, ver, upd = pm_query(tool, h)
            if ok:
                st["pm_installed"] = True
                st["pm_helper"] = h
                st["pm_version"] = ver
                st["pm_has_update"] = upd
                break

    if "flatpak" in supported and tool.get("flatpak_id"):
        ok, ver = flatpak_query(tool)
        st["flatpak_installed"] = ok
        st["flatpak_version"] = ver

    st["config_present"] = native_installed(tool)
    return st


# --------------------------------------------------------------------------- #
#  Bestehende Installation erkennen (distro-unabhängig, KEIN yay/pacman)
# --------------------------------------------------------------------------- #
def _config_dir_candidates(tool):
    """Liste der zu prüfenden Konfigurationsordner unter ~/.config."""
    dirs = tool.get("config_dirs") or []
    if isinstance(dirs, str):
        dirs = [dirs]
    return [os.path.join(HOME, ".config", d) for d in dirs]


def config_path_hint(tool):
    """Gibt den (ersten) Konfigurationspfad als Hinweistext zurück, sonst ''."""
    cands = _config_dir_candidates(tool)
    if cands:
        # mit ~ für die Anzeige
        return cands[0].replace(HOME, "~", 1)
    return ""


def native_installed(tool):
    """
    True, wenn das Programm bereits eingerichtet wirkt – erkannt daran, dass ein
    Konfigurationsordner in ~/.config existiert. Bewusst OHNE yay/pacman, damit
    es auch auf anderen Systemen (Fedora, Ubuntu, ...) funktioniert.
    """
    for p in _config_dir_candidates(tool):
        if os.path.isdir(p):
            return True
    return False


# --------------------------------------------------------------------------- #
#  Status / Deinstallation
# --------------------------------------------------------------------------- #
def status(tool):
    """
    Liefert (installed: bool, version: str, has_update: bool) für ein
    AppImage-Tool – kompatibel zum Signal des ToolsStatusWorker.
    """
    link = _bin_link(tool)
    app = _appimage_path(tool)
    installed = (os.path.islink(link) or os.path.exists(link)) and os.path.exists(app)

    version = ""
    m = _marker(tool)
    if os.path.exists(m):
        try:
            with open(m, "r") as f:
                version = json.load(f).get("version", "")
        except Exception:
            version = ""

    target = tool.get("version", "")
    has_update = bool(installed and target and version and version != target)
    return installed, version, has_update


def is_installed(tool):
    return status(tool)[0]


def local_status(tool):
    """(installed, installed_version) – rein lokal, ohne Netzwerk."""
    link = _bin_link(tool)
    app = _appimage_path(tool)
    installed = (os.path.islink(link) or os.path.exists(link)) and os.path.exists(app)
    version = ""
    m = _marker(tool)
    if os.path.exists(m):
        try:
            with open(m, "r") as f:
                version = json.load(f).get("version", "")
        except Exception:
            version = ""
    return installed, version


def delete_config(tool):
    """Löscht die in config_dirs angegebenen Ordner unter ~/.config (auf Wunsch)."""
    removed = []
    for p in _config_dir_candidates(tool):
        try:
            if os.path.isdir(p):
                shutil.rmtree(p)
                removed.append(p)
        except Exception as e:
            print(f"[AppImage] Config konnte nicht gelöscht werden ({p}): {e}")
    return removed


def uninstall(tool):
    """Entfernt Symlinks/Skripte und den Tool-Ordner wieder (PATH-Eintrag bleibt – harmlos)."""
    for p in (_bin_link(tool), _desktop_link(tool)):
        try:
            if os.path.islink(p) or os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
    # auch vom Programm selbst angelegte Einträge entfernen
    try:
        _remove_foreign_entries(tool)
    except Exception:
        pass
    try:
        if os.path.isdir(_tool_dir(tool)):
            shutil.rmtree(_tool_dir(tool))
    except Exception:
        pass
    try:
        if os.path.exists(_desktop_src(tool)):
            os.remove(_desktop_src(tool))
    except Exception:
        pass


# --------------------------------------------------------------------------- #
#  PATH / .desktop / Symlinks
# --------------------------------------------------------------------------- #
def _ensure_local_bin_on_path():
    """
    Sorgt dafür, dass ~/.local/bin im PATH liegt, damit der Terminal-Befehl
    (z. B. 'oscleash_app') funktioniert. Idempotent – schreibt höchstens
    einmal einen markierten Block in .bashrc/.zshrc.
    """
    if LOCAL_BIN in os.environ.get("PATH", "").split(":"):
        return
    marker = "yakuda-connect: ~/.local/bin in PATH"
    block = (
        f"\n# {marker}\n"
        'export PATH="$HOME/.local/bin:$PATH"\n'
    )
    for rc in (".bashrc", ".zshrc"):
        rc_path = os.path.join(HOME, rc)
        # .bashrc immer (Standard-Shell auf SteamOS), .zshrc nur falls vorhanden
        if rc != ".bashrc" and not os.path.exists(rc_path):
            continue
        try:
            existing = ""
            if os.path.exists(rc_path):
                with open(rc_path, "r", errors="ignore") as f:
                    existing = f.read()
            if marker in existing:
                continue
            with open(rc_path, "a") as f:
                f.write(block)
        except Exception:
            pass


def _force_symlink(src, dst):
    """Erstellt dst -> src; ein vorhandenes dst (Datei/Symlink) wird ersetzt."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        if os.path.islink(dst) or os.path.exists(dst):
            os.remove(dst)
    except Exception:
        pass
    os.symlink(src, dst)


# Starter-Skript: startet die AppImage normal, wenn libfuse2 vorhanden ist –
# sonst mit --appimage-extract-and-run (SteamOS/Steam Deck, Ubuntu ohne
# libfuse2, Fedora, ...). So läuft es ohne Root und ohne Schreibzugriff auf /usr.
_LAUNCHER_TEMPLATE = """#!/usr/bin/env bash
# Automatisch erzeugt von yakuda-connect – AppImage-Starter mit FUSE-Fallback.
APPIMAGE="__APPIMAGE__"
LAUNCH_ARGS=(__LAUNCH_ARGS__)

if [ ! -x "$APPIMAGE" ]; then
    chmod +x "$APPIMAGE" 2>/dev/null
fi

have_fuse() {
    if command -v ldconfig >/dev/null 2>&1; then
        ldconfig -p 2>/dev/null | grep -qi 'libfuse\\.so\\.2' && return 0
    fi
    for d in /usr/lib /usr/lib64 /usr/lib/x86_64-linux-gnu /lib /lib64 /lib/x86_64-linux-gnu; do
        [ -e "$d/libfuse.so.2" ] && return 0
    done
    return 1
}

if have_fuse; then
    exec "$APPIMAGE" "${LAUNCH_ARGS[@]}" "$@"
else
    exec "$APPIMAGE" --appimage-extract-and-run "${LAUNCH_ARGS[@]}" "$@"
fi
"""


def _write_launcher(tool):
    """Schreibt das FUSE-sichere Starter-Skript nach ~/.local/bin/<start_cmd>."""
    link = _bin_link(tool)
    os.makedirs(os.path.dirname(link), exist_ok=True)
    try:
        if os.path.islink(link) or os.path.exists(link):
            os.remove(link)
    except Exception:
        pass
    args = (tool.get("launch_args") or "").strip()
    script = (_LAUNCHER_TEMPLATE
              .replace("__APPIMAGE__", _appimage_path(tool))
              .replace("__LAUNCH_ARGS__", args))
    with open(link, "w") as f:
        f.write(script)
    st = os.stat(link)
    os.chmod(link, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return link


def _remove_foreign_entries(tool):
    """
    Entfernt vom Programm selbst angelegte Desktop-/Autostart-Einträge
    (Pfade aus 'remove_entries', z. B. VRCX.desktop in applications und
    autostart), damit nur unser eigener Eintrag übrig bleibt.
    """
    removed = []
    own = os.path.abspath(_desktop_link(tool))
    for raw in (tool.get("remove_entries") or []):
        pattern = os.path.expanduser(raw)
        for p in glob.glob(pattern):
            if os.path.abspath(p) == own:
                continue  # niemals unseren eigenen Eintrag löschen
            try:
                if os.path.islink(p) or os.path.isfile(p):
                    os.remove(p)
                    removed.append(p)
            except Exception as e:
                print(f"[AppImage] Konnte Eintrag nicht entfernen ({p}): {e}")
    return removed


def _write_desktop_file(tool):
    """Schreibt die .desktop-Datei in den yakuda-Ordner und gibt ihren Pfad zurück."""
    os.makedirs(DESKTOP_SRC_DIR, exist_ok=True)
    name = tool.get("name", tool["key"])
    comment = tool.get("desc_eng") or tool.get("desc", "")
    exec_path = _bin_link(tool)   # Starter-Skript (mit FUSE-Fallback)
    icon = _icon_path(tool)

    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={name}",
    ]
    if comment:
        lines.append(f"Comment={comment}")
    # Exec auf das Starter-Skript -> auch in der KDE-Sitzung FUSE-sicher.
    lines.append(f'Exec="{exec_path}"')
    if os.path.exists(icon):
        lines.append(f"Icon={icon}")
    lines += [
        "Terminal=false",
        "Categories=Utility;Game;",
        f"X-Yakuda-Tool={tool['key']}",
        "",
    ]
    with open(_desktop_src(tool), "w") as f:
        f.write("\n".join(lines))
    return _desktop_src(tool)


def _refresh_desktop_db():
    """Aktualisiert die KDE/XDG-Anwendungsdatenbank, falls das Tool vorhanden ist."""
    if shutil.which("update-desktop-database"):
        try:
            subprocess.run(["update-desktop-database", APPLICATIONS_DIR],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


# --------------------------------------------------------------------------- #
#  Worker
# --------------------------------------------------------------------------- #
class AppImageInstallWorker(QThread):
    """Lädt ein AppImage herunter und richtet Terminal-Befehl + Desktop-Eintrag ein."""
    status_signal   = Signal(str)
    finished_signal = Signal(bool)

    def __init__(self, tool):
        super().__init__()
        self.tool = tool
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _download(self, url, dest, progress=None):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "yakuda-connect"})
        with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length", 0))
            done = 0
            while True:
                if self._cancel:
                    raise RuntimeError("Abgebrochen")
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done, total)

    def run(self):
        tool = self.tool
        try:
            # 0. Download-URL + Version bestimmen (GitHub-neueste oder feste URL)
            self.status_signal.emit("🔎 Suche Download ...")
            try:
                url, version = resolve_release(tool)
            except RateLimited as e:
                self.status_signal.emit(f"Fehler: {e}")
                self.finished_signal.emit(False)
                return
            except Exception as e:
                self.status_signal.emit(f"Fehler beim Abruf der Release: {e}")
                self.finished_signal.emit(False)
                return

            if not url:
                if tool.get("github_repo"):
                    self.status_signal.emit(
                        "Fehler: Kein passendes AppImage für deine Architektur "
                        f"({platform.machine()}) in den Releases gefunden.")
                else:
                    self.status_signal.emit("Fehler: Keine AppImage-URL hinterlegt.")
                self.finished_signal.emit(False)
                return

            # 1. Ordnerstruktur anlegen (tools/, tools/<key>/, tools/desktop/)
            self.status_signal.emit("📁 Erstelle Ordnerstruktur ...")
            os.makedirs(_tool_dir(tool), exist_ok=True)
            os.makedirs(DESKTOP_SRC_DIR, exist_ok=True)
            os.makedirs(LOCAL_BIN, exist_ok=True)
            os.makedirs(APPLICATIONS_DIR, exist_ok=True)

            # 2. AppImage herunterladen (stabiler lokaler Dateiname)
            app = _appimage_path(tool)

            def prog(done, total):
                self.status_signal.emit(
                    f"⬇ Lade AppImage ... {done/1_000_000:.1f} / {total/1_000_000:.1f} MB")

            self.status_signal.emit("⬇ Lade AppImage ...")
            self._download(url, app, prog)

            # 3. ausführbar machen
            self.status_signal.emit("🔧 Mache AppImage ausführbar ...")
            st = os.stat(app)
            os.chmod(app, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

            # 4. Terminal-Befehl als Starter-Skript (~/.local/bin/<start_cmd>)
            #    -> mit FUSE-Fallback (--appimage-extract-and-run), falls libfuse2 fehlt
            self.status_signal.emit("🔗 Richte Terminal-Befehl ein ...")
            _write_launcher(tool)
            _ensure_local_bin_on_path()

            # 5. Icon laden (blob-URL wird automatisch zu raw umgewandelt)
            icon_url = tool.get("icon_url")
            if icon_url:
                self.status_signal.emit("🖼 Lade Icon ...")
                try:
                    self._download(_raw_github(icon_url), _icon_path(tool))
                except Exception as e:
                    print(f"[AppImage] Icon konnte nicht geladen werden: {e}")

            # 6. .desktop schreiben + für KDE verlinken
            self.status_signal.emit("🖥 Erstelle Desktop-Eintrag ...")
            _write_desktop_file(tool)
            _force_symlink(_desktop_src(tool), _desktop_link(tool))

            # 6b. Vom Programm selbst angelegte Einträge entfernen (z. B. VRCX),
            #     damit nur unser Eintrag übrig bleibt
            _remove_foreign_entries(tool)
            _refresh_desktop_db()

            # 7. Versions-Marker schreiben (echte heruntergeladene Version)
            try:
                with open(_marker(tool), "w") as f:
                    json.dump({"version": version or tool.get("version", "")}, f)
            except Exception:
                pass

            self.status_signal.emit("✔ Fertig installiert.")
            self.finished_signal.emit(True)

        except Exception as e:
            self.status_signal.emit(f"Fehler: {e}")
            self.finished_signal.emit(False)
