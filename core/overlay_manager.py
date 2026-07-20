#!/usr/bin/env python3
"""
overlay_manager.py — WayVR-Design von cubee-cb, 1:1 und ohne Veränderungen
==========================================================================
Quelle (GPL-3.0, wie yakuda-connect):
  https://github.com/cubee-cb/linux-vr-compat/tree/master/dotfiles/wayvr

Es gibt genau zwei Aktionen — mehr macht dieses Modul bewusst NICHT:

  Installieren:  Repo laden → ~/.config/wayvr sichern → Ordner leeren →
                 dotfiles/wayvr 1:1 hineinkopieren. KEIN Patchen, KEINE
                 eigenen Dateien, KEINE Pfad-Anpassungen. Was bei cubee im
                 Repo liegt, liegt danach exakt so in ~/.config/wayvr.

  Zurücksetzen:  ~/.config/wayvr sichern und komplett löschen. WayVR legt
                 den Ordner beim nächsten Start mit seinen eingebauten
                 Standardwerten neu an.

Vor JEDER Aktion wird ~/.config/wayvr nach
~/.config/yakuda-connect/backup/wayvr_<zeitstempel>/ gesichert.
"""
import os
import shutil
import subprocess
import datetime
import tempfile

from PySide6.QtCore import QThread, Signal

HOME        = os.path.expanduser("~")
WAYVR_DIR   = os.path.join(HOME, ".config/wayvr")
BACKUP_BASE = os.path.join(HOME, ".config/yakuda-connect/backup")

DESIGN_REPO   = "https://github.com/cubee-cb/linux-vr-compat"
DESIGN_SUBDIR = os.path.join("dotfiles", "wayvr")

# Erkennungsmerkmal fuer "Design ist installiert": cubees Watch-Layout.
# Aktueller Pfad im Repo: theme/gui/watch.xml
_MARKER_FILE = os.path.join(WAYVR_DIR, "theme", "gui", "watch.xml")


def is_design_installed():
    """True, wenn cubees Design in ~/.config/wayvr liegt (theme/gui/watch.xml)."""
    return os.path.isfile(_MARKER_FILE)


def backup_wayvr():
    """
    Sichert ~/.config/wayvr nach ~/.config/yakuda-connect/backup/wayvr_<stamp>/.
    Gibt den Backup-Pfad zurueck, oder None wenn es nichts zu sichern gab.
    """
    if not os.path.isdir(WAYVR_DIR):
        return None
    os.makedirs(BACKUP_BASE, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(BACKUP_BASE, f"wayvr_{stamp}")
    # Zwei Backups in derselben Sekunde (Installieren + gleich Zuruecksetzen):
    # Suffix anhaengen statt an einem schon existierenden Ordner zu scheitern.
    n = 1
    while os.path.exists(dest):
        n += 1
        dest = os.path.join(BACKUP_BASE, f"wayvr_{stamp}_{n}")
    shutil.copytree(WAYVR_DIR, dest)
    return dest


def reset_wayvr_to_default():
    """
    Setzt WayVR auf Werkseinstellung zurueck: sichert und loescht
    ~/.config/wayvr komplett. WayVR legt den Ordner beim naechsten Start
    selbst neu an. Rueckgabe: (ok, backup_pfad_oder_fehlertext).
    """
    try:
        backup = backup_wayvr()
        if os.path.isdir(WAYVR_DIR):
            shutil.rmtree(WAYVR_DIR)
        return True, backup or ""
    except Exception as e:
        return False, str(e)


# --------------------------------------------------------------------------- #
#  Design von GitHub holen
# --------------------------------------------------------------------------- #
def _download_design(tmp):
    """
    Holt cubees Repo nach <tmp> und gibt den Pfad zu dotfiles/wayvr zurueck.
    Zuerst git (flach), sonst Tarball per curl/wget — damit es auch ohne
    installiertes git funktioniert.
    """
    target = os.path.join(tmp, "repo")

    if shutil.which("git"):
        r = subprocess.run(
            ["git", "clone", "--depth", "1", DESIGN_REPO, target],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
        if r.returncode == 0:
            src = os.path.join(target, DESIGN_SUBDIR)
            if os.path.isdir(src):
                return src

    # Fallback ohne git: Tarball des master-Branches
    tar = os.path.join(tmp, "design.tar.gz")
    url = f"{DESIGN_REPO}/archive/refs/heads/master.tar.gz"
    ok = False
    if shutil.which("curl"):
        ok = subprocess.run(["curl", "-fsSL", url, "-o", tar], timeout=180).returncode == 0
    if not ok and shutil.which("wget"):
        ok = subprocess.run(["wget", "-q", url, "-O", tar], timeout=180).returncode == 0
    if not ok:
        raise RuntimeError("Download fehlgeschlagen — git, curl oder wget wird benötigt.")

    ext = os.path.join(tmp, "ext")
    os.makedirs(ext, exist_ok=True)
    subprocess.run(["tar", "-xzf", tar, "-C", ext], check=True, timeout=120)
    for root, dirs, _files in os.walk(ext):
        if (os.path.basename(root) == "wayvr"
                and os.path.basename(os.path.dirname(root)) == "dotfiles"):
            return root
    raise RuntimeError("Im Download war kein dotfiles/wayvr enthalten.")


class DesignInstallWorker(QThread):
    """
    Installiert cubees Design 1:1 nach ~/.config/wayvr.

    Ablauf (status_signal): download → backup → install
      1. dotfiles/wayvr von GitHub laden
      2. ~/.config/wayvr sichern
      3. ~/.config/wayvr leeren und den Repo-Inhalt unveraendert hineinkopieren
         (Leeren + Kopieren statt Drueberkopieren, damit das Ergebnis EXAKT
          dem Repo entspricht und keine alten Dateien uebrig bleiben)
    """
    status_signal = Signal(str)
    finished_signal = Signal(bool, str)

    def run(self):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                # 1. Erst laden — schlaegt der Download fehl, wird an der
                #    bestehenden Config gar nichts angefasst.
                self.status_signal.emit("download")
                src = _download_design(tmp)

                # 2. Sichern
                self.status_signal.emit("backup")
                backup_wayvr()

                # 3. Leeren + 1:1 kopieren
                self.status_signal.emit("install")
                if os.path.isdir(WAYVR_DIR):
                    shutil.rmtree(WAYVR_DIR)
                shutil.copytree(src, WAYVR_DIR)

            self.finished_signal.emit(True, "")
        except Exception as e:
            self.finished_signal.emit(False, str(e))
