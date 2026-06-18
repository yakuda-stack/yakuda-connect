#!/usr/bin/env python3
"""
overlay_manager.py — WayVR-Overlay-Verwaltung für yakuda-connect
================================================================
Neuaufbau auf Basis des cubee-Designs:

  Basis-Design   : https://github.com/cubee-cb/linux-vr-compat/tree/master/dotfiles/wayvr
  SlimeVR-Buttons: von sapphire (#wayvr-custom, https://discord.gg/EHAYe3tTYa)

Ablauf:
  * "WayVR-Design aktualisieren" lädt das cubee-Basis-Design herunter (Standard,
    OHNE Performance-Overlay) und entfernt dabei Reste einer früheren
    Performance-Anzeige (hwmon) aus einer bestehenden Installation.
  * Die SlimeVR-Reset-Buttons lassen sich optional einblenden (eine Reihe
    UNTER den normalen Buttons). Sie sind statisch und verursachen keinen
    Dauer-IPC – im Gegensatz zur alten Performance-Anzeige, die WayVR bei
    langen Sessions zum Haengen bringen konnte und deshalb entfernt wurde.

Ziel ist immer ~/.config/wayvr/ .
"""
import os
import shutil
import subprocess
import tempfile
import datetime

from PySide6.QtCore import QThread, Signal
from install_worker import find_terminal

HOME = os.path.expanduser("~")
WAYVR_DIR    = os.path.join(HOME, ".config/wayvr")
THEME_DIR    = os.path.join(WAYVR_DIR, "theme")
GUI_DIR      = os.path.join(THEME_DIR, "gui")
GUI_ASSETS   = os.path.join(GUI_DIR, "assets")
THEME_ASSETS = os.path.join(THEME_DIR, "assets")
WATCH_XML    = os.path.join(GUI_DIR, "watch.xml")
BACKUP_BASE  = os.path.join(HOME, ".config/yakuda-connect/backup")
PRISTINE_BACKUP = os.path.join(BACKUP_BASE, "wayvr_original")
CUBEE_BASE_WATCH = os.path.join(BACKUP_BASE, "cubee_watch_base.xml")

CUBEE_REPO    = "https://github.com/cubee-cb/linux-vr-compat"
CUBEE_TARBALL = "https://codeload.github.com/cubee-cb/linux-vr-compat/tar.gz/refs/heads/master"

_PERF_LEFTOVERS = [
    os.path.join(GUI_ASSETS, "hwmon.sh"),
    os.path.join(GUI_ASSETS, "perf_toggle.sh"),
    os.path.join(GUI_ASSETS, "media", "perf.svg"),
    os.path.join(GUI_DIR, "watch_nohwmon.xml"),
    os.path.join(GUI_DIR, "watch_slimevr.xml"),
    os.path.join(GUI_DIR, "watch_slimevr_nohwmon.xml"),
    os.path.join(WAYVR_DIR, ".hwmon_visible"),
]


def overlay_dir():
    """Findet den mitgelieferten overlay/-Ordner (Entwicklungs-Layout oder AppImage)."""
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(os.path.dirname(here), "overlay"),
        os.path.join(here, "overlay"),
        os.path.join(here, "..", "overlay"),
    ]
    appdir = os.environ.get("APPDIR")
    if appdir:
        candidates += [
            os.path.join(appdir, "overlay"),
            os.path.join(appdir, "usr", "overlay"),
            os.path.join(appdir, "usr", "bin", "overlay"),
            os.path.join(appdir, "usr", "share", "yakuda-connect", "overlay"),
        ]
    try:
        exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        candidates += [
            os.path.join(exe_dir, "overlay"),
            os.path.join(os.path.dirname(exe_dir), "overlay"),
        ]
    except Exception:
        pass
    for c in candidates:
        if os.path.isdir(c):
            return os.path.abspath(c)
    return os.path.abspath(candidates[0])


def _slimevr_watch_src():
    return os.path.join(overlay_dir(), "watch_slimevr.xml")


def _slimevr_assets_src():
    return os.path.join(overlay_dir(), "slimevr", "assets")


def is_design_installed():
    return os.path.exists(WATCH_XML)


def is_slimevr_active():
    """SlimeVR-Buttons aktiv? Erkennbar am eepyxr-Button (nur in der SlimeVR-Watch)."""
    try:
        with open(WATCH_XML, "r", errors="ignore") as f:
            return 'id="btn_eepyxr"' in f.read()
    except Exception:
        return False


def backup_wayvr():
    """Sichert die aktuelle ~/.config/wayvr nach ~/.config/yakuda-connect/backup/."""
    if not os.path.isdir(WAYVR_DIR):
        return None
    os.makedirs(BACKUP_BASE, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(BACKUP_BASE, f"wayvr_{stamp}")
    shutil.copytree(WAYVR_DIR, dest)
    return dest


def backup_wayvr_pristine():
    """Sichert EINMALIG den Original-Zustand von ~/.config/wayvr (vor dem Design)."""
    if os.path.exists(PRISTINE_BACKUP):
        return
    if not os.path.isdir(WAYVR_DIR):
        return
    if is_slimevr_active():
        return
    os.makedirs(BACKUP_BASE, exist_ok=True)
    shutil.copytree(WAYVR_DIR, PRISTINE_BACKUP)


def reset_wayvr_to_default():
    """Setzt WayVR wieder auf Standard zurück ('Design deinstallieren')."""
    try:
        stop_hwmon()
        _clean_performance_artifacts()
        backup_wayvr()
        if os.path.isdir(PRISTINE_BACKUP):
            if os.path.isdir(WAYVR_DIR):
                shutil.rmtree(WAYVR_DIR)
            shutil.copytree(PRISTINE_BACKUP, WAYVR_DIR)
            return True, "restored"
        if os.path.isdir(THEME_DIR):
            shutil.rmtree(THEME_DIR)
        return True, "removed"
    except Exception as e:
        return False, str(e)


def stop_hwmon():
    """Beendet ein evtl. noch laufendes hwmon.sh der alten Performance-Anzeige."""
    subprocess.run(["pkill", "-f", "hwmon.sh"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _clean_performance_artifacts():
    """Entfernt Dateireste der alten Performance-Anzeige aus ~/.config/wayvr."""
    stop_hwmon()
    for p in _PERF_LEFTOVERS:
        try:
            if os.path.isfile(p):
                os.remove(p)
        except Exception:
            pass


def _download_design(tmp):
    """Lädt das cubee-cb Design nach tmp und gibt den Pfad zu dotfiles/wayvr zurück."""
    if shutil.which("git"):
        subprocess.run(
            ["git", "clone", "--depth", "1", CUBEE_REPO, os.path.join(tmp, "repo")],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        path = os.path.join(tmp, "repo", "dotfiles", "wayvr")
        if os.path.isdir(path):
            return path
        raise RuntimeError("dotfiles/wayvr nicht im geklonten Repo gefunden.")

    tar = os.path.join(tmp, "repo.tar.gz")
    if shutil.which("curl"):
        subprocess.run(["curl", "-fL", "-o", tar, CUBEE_TARBALL],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    elif shutil.which("wget"):
        subprocess.run(["wget", "-O", tar, CUBEE_TARBALL],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    else:
        raise RuntimeError("Weder git, curl noch wget gefunden – Design kann nicht geladen werden.")

    subprocess.run(["tar", "xzf", tar, "-C", tmp], check=True)
    for name in os.listdir(tmp):
        path = os.path.join(tmp, name, "dotfiles", "wayvr")
        if os.path.isdir(path):
            return path
    raise RuntimeError("dotfiles/wayvr nicht im heruntergeladenen Archiv gefunden.")


def copy_slimevr_assets():
    """Kopiert die SlimeVR-Reset-Icons (von sapphire) nach ~/.config/wayvr/theme/assets/."""
    src = _slimevr_assets_src()
    os.makedirs(THEME_ASSETS, exist_ok=True)
    for f in os.listdir(src):
        shutil.copy2(os.path.join(src, f), os.path.join(THEME_ASSETS, f))


def install_slimevr_ui():
    """Blendet die SlimeVR-Reset-Buttons ein (cubee-Watch + SlimeVR-Reihe darunter)."""
    try:
        if not is_design_installed():
            return False, "no_design"
        copy_slimevr_assets()
        shutil.copy2(_slimevr_watch_src(), WATCH_XML)
        return True, "ok"
    except Exception as e:
        return False, str(e)


def remove_slimevr_ui():
    """Blendet die SlimeVR-Buttons wieder aus -> zurück zur sauberen cubee-Watch."""
    try:
        if not is_design_installed():
            return False, "no_design"
        if os.path.isfile(CUBEE_BASE_WATCH):
            shutil.copy2(CUBEE_BASE_WATCH, WATCH_XML)
            return True, "ok"
        return False, "no_base"
    except Exception as e:
        return False, str(e)


def set_slimevr_ui(enabled):
    """Schaltet die SlimeVR-UI an (True) oder aus (False)."""
    return install_slimevr_ui() if enabled else remove_slimevr_ui()


def ensure_playerctl():
    """Installiert 'playerctl' per yay, falls es noch nicht vorhanden ist."""
    if shutil.which("playerctl"):
        return True
    terminal, flags = find_terminal()
    if not terminal:
        return False
    bash_cmd = (
        "echo '=== Installiere playerctl (fuer die Media-Buttons der WayVR-Watch) ==='; "
        "yay -S playerctl; "
        "echo ''; echo 'Fertig. Dieses Fenster schliesst sich gleich automatisch...'; "
        "sleep 2"
    )
    cmd = [terminal] + flags + ["bash", "-c", bash_cmd]
    try:
        proc = subprocess.Popen(cmd)
        proc.wait()
    except Exception:
        return False
    return shutil.which("playerctl") is not None


class DesignInstallWorker(QThread):
    status_signal = Signal(str)
    finished_signal = Signal(bool, str)

    def run(self):
        try:
            self.status_signal.emit("backup")
            backup_wayvr_pristine()
            backup_wayvr()

            with tempfile.TemporaryDirectory() as tmp:
                self.status_signal.emit("download")
                dotfiles = _download_design(tmp)

                self.status_signal.emit("install")
                os.makedirs(WAYVR_DIR, exist_ok=True)
                shutil.copytree(dotfiles, WAYVR_DIR, dirs_exist_ok=True)

            self.status_signal.emit("cleanup")
            _clean_performance_artifacts()

            if os.path.isfile(WATCH_XML):
                os.makedirs(BACKUP_BASE, exist_ok=True)
                shutil.copy2(WATCH_XML, CUBEE_BASE_WATCH)

            try:
                copy_slimevr_assets()
            except Exception:
                pass

            self.status_signal.emit("playerctl")
            try:
                ensure_playerctl()
            except Exception:
                pass

            self.finished_signal.emit(True, "")
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode("utf-8", "ignore") if isinstance(e.stderr, (bytes, bytearray)) else (e.stderr or str(e))
            self.finished_signal.emit(False, str(err).strip())
        except Exception as e:
            self.finished_signal.emit(False, str(e))
