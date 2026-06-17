#!/usr/bin/env python3
"""
overlay_manager.py — WayVR-Overlay-Verwaltung für yakuda-connect
================================================================
Stellt die Logik für die beiden Settings-Buttons bereit:

  * "WayVR-Design aktualisieren"  -> install_design (Worker, lädt cubee-cb Design,
                                     legt Backup an, aktiviert Performance-Overlay)
  * "WayVR SlimeVR-UI hinzufügen"  -> install_slimevr_ui (fügt Reset-Buttons hinzu)

Die mitgelieferten Dateien liegen im Repo-Unterordner "overlay/" (neben "core/").
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
PRISTINE_BACKUP = os.path.join(BACKUP_BASE, "wayvr_original")  # einmalige Sicherung des Original-Zustands

CUBEE_REPO    = "https://github.com/cubee-cb/linux-vr-compat"
CUBEE_TARBALL = "https://codeload.github.com/cubee-cb/linux-vr-compat/tar.gz/refs/heads/master"


# --------------------------------------------------------------------------- #
#  Pfade / Status
# --------------------------------------------------------------------------- #
def overlay_dir():
    """
    Findet den mitgelieferten overlay/-Ordner.
    Funktioniert sowohl im Entwicklungs-Layout (overlay/ neben core/) als auch
    in einem gepackten AppImage (überall dort, wo der Ordner mitgeliefert wird).
    """
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(os.path.dirname(here), "overlay"),   # <repo>/overlay  (core/ ist Geschwister)
        os.path.join(here, "overlay"),                    # core/overlay
        os.path.join(here, "..", "overlay"),
    ]
    # AppImage: $APPDIR zeigt auf das gemountete Wurzelverzeichnis
    appdir = os.environ.get("APPDIR")
    if appdir:
        candidates += [
            os.path.join(appdir, "overlay"),
            os.path.join(appdir, "usr", "overlay"),
            os.path.join(appdir, "usr", "bin", "overlay"),
            os.path.join(appdir, "usr", "share", "yakuda-connect", "overlay"),
        ]
    # Relativ zum gestarteten Programm (Fallback)
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


def is_design_installed():
    return os.path.exists(WATCH_XML)


def is_performance_active():
    try:
        with open(WATCH_XML, "r", errors="ignore") as f:
            return 'id="hwmon"' in f.read()
    except Exception:
        return False


def is_slimevr_active():
    try:
        with open(WATCH_XML, "r", errors="ignore") as f:
            return "YAKUDA_SLIMEVR" in f.read()
    except Exception:
        return False


# --------------------------------------------------------------------------- #
#  Backup
# --------------------------------------------------------------------------- #
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
    """
    Sichert EINMALIG den Original-Zustand von ~/.config/wayvr (vor dem Design).
    Wird nur angelegt, wenn es noch keine Original-Sicherung gibt UND der aktuelle
    Zustand noch nicht nach unserem Design aussieht – sonst würden wir versehentlich
    das bereits angepasste Design als 'Original' sichern.
    """
    if os.path.exists(PRISTINE_BACKUP):
        return
    if not os.path.isdir(WAYVR_DIR):
        return
    if is_performance_active():
        return  # sieht schon nach unserem Design aus -> nicht als Original sichern
    os.makedirs(BACKUP_BASE, exist_ok=True)
    shutil.copytree(WAYVR_DIR, PRISTINE_BACKUP)


def reset_wayvr_to_default():
    """
    Setzt WayVR wieder auf Standard zurück ('Design deinstallieren').
    1) Existiert eine Original-Sicherung -> diese wiederherstellen.
    2) Sonst: die vom Launcher installierten Design-Dateien (theme/) entfernen,
       dann nutzt WayVR seine EINGEBAUTEN Standardwerte.
    Vorher wird der aktuelle Zustand sicherheitshalber gesichert.
    Rückgabe: (erfolg: bool, code_oder_fehler: str)  code = 'restored' | 'removed'
    """
    try:
        stop_hwmon()
        backup_wayvr()  # Sicherheitskopie des aktuellen (angepassten) Zustands

        if os.path.isdir(PRISTINE_BACKUP):
            if os.path.isdir(WAYVR_DIR):
                shutil.rmtree(WAYVR_DIR)
            shutil.copytree(PRISTINE_BACKUP, WAYVR_DIR)
            return True, "restored"

        # Keine Original-Sicherung vorhanden -> Custom-Theme entfernen
        if os.path.isdir(THEME_DIR):
            shutil.rmtree(THEME_DIR)
        return True, "removed"
    except Exception as e:
        return False, str(e)


# --------------------------------------------------------------------------- #
#  Download des cubee-cb Designs
# --------------------------------------------------------------------------- #
def _download_design(tmp):
    """Lädt das cubee-cb Design nach tmp und gibt den Pfad zu dotfiles/wayvr zurück."""
    # 1) Bevorzugt: git clone
    if shutil.which("git"):
        subprocess.run(
            ["git", "clone", "--depth", "1", CUBEE_REPO, os.path.join(tmp, "repo")],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        path = os.path.join(tmp, "repo", "dotfiles", "wayvr")
        if os.path.isdir(path):
            return path
        raise RuntimeError("dotfiles/wayvr nicht im geklonten Repo gefunden.")

    # 2) Fallback: Tarball via curl/wget
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


# --------------------------------------------------------------------------- #
#  Overlay anwenden
# --------------------------------------------------------------------------- #
def apply_performance_overlay(with_slimevr=False):
    """
    Kopiert die Performance-Overlay-Dateien in die WayVR-Theme und setzt die
    passende watch.xml. with_slimevr=True nutzt die kombinierte Variante
    (Performance + SlimeVR-Buttons).
    """
    perf = os.path.join(overlay_dir(), "performance")
    os.makedirs(GUI_ASSETS, exist_ok=True)

    # Assets (hwmon.sh, songname.sh, media/) kopieren
    shutil.copytree(os.path.join(perf, "assets"), GUI_ASSETS, dirs_exist_ok=True)

    # watch.xml setzen
    watch_src = "watch_slimevr.xml" if with_slimevr else "watch.xml"
    shutil.copy2(os.path.join(perf, watch_src), WATCH_XML)
    # nohwmon-Variante als Fallback mitliefern
    nohwmon = os.path.join(perf, "watch_nohwmon.xml")
    if os.path.exists(nohwmon):
        shutil.copy2(nohwmon, os.path.join(GUI_DIR, "watch_nohwmon.xml"))

    # Shell-Skripte ausführbar machen
    for f in os.listdir(GUI_ASSETS):
        if f.endswith(".sh"):
            try:
                os.chmod(os.path.join(GUI_ASSETS, f), 0o755)
            except Exception:
                pass


def copy_slimevr_assets():
    """Kopiert die SlimeVR-Reset-Icons nach ~/.config/wayvr/theme/assets/."""
    src = os.path.join(overlay_dir(), "slimevr", "assets")
    os.makedirs(THEME_ASSETS, exist_ok=True)
    for f in os.listdir(src):
        shutil.copy2(os.path.join(src, f), os.path.join(THEME_ASSETS, f))


# --------------------------------------------------------------------------- #
#  hwmon-Hintergrundskript (Performance-Werte)
# --------------------------------------------------------------------------- #
def stop_hwmon():
    subprocess.run(["pkill", "-f", "hwmon.sh"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_hwmon():
    """
    Startet hwmon.sh im Hintergrund (speist die Performance-Anzeige).
    Benötigt ein laufendes WayVR (wegen wayvrctl). Läuft sonst einfach ins Leere.
    """
    script = os.path.join(GUI_ASSETS, "hwmon.sh")
    if not os.path.exists(script):
        return False
    stop_hwmon()
    try:
        subprocess.Popen(["bash", script],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
#  SlimeVR-UI aktivieren
# --------------------------------------------------------------------------- #
def install_slimevr_ui():
    """
    Aktiviert die SlimeVR-Reset-Buttons in der WayVR-Watch.
    Setzt ein installiertes Design voraus (erst 'Design aktualisieren').
    Rückgabe: (erfolg: bool, code_oder_fehler: str)
    """
    try:
        if not is_design_installed():
            return False, "no_design"
        copy_slimevr_assets()
        # watch.xml auf die kombinierte Variante umstellen (Performance bleibt erhalten)
        apply_performance_overlay(with_slimevr=True)
        start_hwmon()
        return True, "ok"
    except Exception as e:
        return False, str(e)


def remove_slimevr_ui():
    """
    Entfernt die SlimeVR-Buttons wieder. Das Performance-Overlay bleibt erhalten.
    Rückgabe: (erfolg: bool, code_oder_fehler: str)
    """
    try:
        if not is_design_installed():
            return False, "no_design"
        # Zurück auf die reine Performance-watch.xml (ohne SlimeVR-Block)
        apply_performance_overlay(with_slimevr=False)
        start_hwmon()
        return True, "ok"
    except Exception as e:
        return False, str(e)


def set_slimevr_ui(enabled):
    """Schaltet die SlimeVR-UI an (True) oder aus (False)."""
    return install_slimevr_ui() if enabled else remove_slimevr_ui()


# --------------------------------------------------------------------------- #
#  playerctl sicherstellen (für die Media-Buttons der Watch)
# --------------------------------------------------------------------------- #
def ensure_playerctl():
    """
    Installiert 'playerctl' per yay, falls es noch nicht vorhanden ist.
    Öffnet dafür ein Terminal (yay braucht sudo-Passwort/Bestätigung).
    Rückgabe: True wenn playerctl danach vorhanden ist (oder schon war).
    """
    if shutil.which("playerctl"):
        return True  # schon installiert

    terminal, flags = find_terminal()
    if not terminal:
        return False  # kein Terminal gefunden -> Nutzer muss manuell installieren

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


# --------------------------------------------------------------------------- #
#  Worker: Design installieren (Netzwerk -> eigener Thread)
# --------------------------------------------------------------------------- #
class DesignInstallWorker(QThread):
    status_signal = Signal(str)        # "backup" | "download" | "install" | "overlay" | "playerctl"
    finished_signal = Signal(bool, str)  # (erfolg, fehlertext)

    def run(self):
        try:
            self.status_signal.emit("backup")
            backup_wayvr_pristine()   # einmalige Original-Sicherung (nur falls noch kein Design da)
            backup_wayvr()

            with tempfile.TemporaryDirectory() as tmp:
                self.status_signal.emit("download")
                dotfiles = _download_design(tmp)

                self.status_signal.emit("install")
                os.makedirs(WAYVR_DIR, exist_ok=True)
                shutil.copytree(dotfiles, WAYVR_DIR, dirs_exist_ok=True)

                self.status_signal.emit("overlay")
                apply_performance_overlay(with_slimevr=False)

            # playerctl für die Media-Buttons sicherstellen (Fehler hier sind nicht kritisch)
            self.status_signal.emit("playerctl")
            try:
                ensure_playerctl()
            except Exception:
                pass

            start_hwmon()
            self.finished_signal.emit(True, "")
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode("utf-8", "ignore") if isinstance(e.stderr, (bytes, bytearray)) else (e.stderr or str(e))
            self.finished_signal.emit(False, str(err).strip())
        except Exception as e:
            self.finished_signal.emit(False, str(e))
