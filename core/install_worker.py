import subprocess
import shutil
import time
from PySide6.QtCore import QThread, Signal

# Terminalemulatoren nach Priorität — erster gefundener wird benutzt.
# Jeder Eintrag: (binary, argument_um_befehl_auszuführen)
# Die meisten benutzen "-e", kitty/foot benutzen direkt den Befehl ohne Flag.
TERMINAL_CANDIDATES = [
    # KDE
    ("konsole",      ["-e"]),
    # GNOME / GTK
    ("gnome-terminal", ["--"]),
    # Hyprland / wlroots
    ("kitty",        []),
    ("foot",         []),
    ("alacritty",    ["-e"]),
    ("wezterm",      ["start", "--"]),
    # XFCE
    ("xfce4-terminal", ["-e"]),
    # Weitere verbreitete
    ("xterm",        ["-e"]),
    ("lxterminal",   ["-e"]),
    ("tilix",        ["-e"]),
    ("urxvt",        ["-e"]),
]

def find_terminal():
    """Gibt (binary, exec_flag_list) des ersten verfügbaren Terminals zurück."""
    for binary, flags in TERMINAL_CANDIDATES:
        if shutil.which(binary):
            return binary, flags
    return None, None


class UpdateWorker(QThread):
    """Führt ein System-/Ökosystem-Update über die gewählte Methode im Terminal aus."""
    status_signal = Signal(str)
    finished_signal = Signal(bool)

    def __init__(self, method):
        super().__init__()
        self.method = method

    def run(self):
        terminal, exec_flags = find_terminal()
        if terminal is None:
            self.status_signal.emit("Fehler: Kein unterstütztes Terminal gefunden!")
            self.finished_signal.emit(False)
            return

        cmds = {
            "yay":     "yay -Syu",
            "paru":    "paru -Syu",
            "flatpak": "flatpak update",
        }
        update_cmd = cmds.get(self.method, "yay -Syu")
        self.status_signal.emit(f"Update läuft ({self.method}) ...")

        bash_cmd = (
            f"echo '=== System-Update ({self.method}) ==='; "
            f"{update_cmd}; "
            f"echo ''; "
            f"echo 'Fertig. Dieses Fenster schließt sich gleich automatisch...'; "
            f"sleep 2"
        )
        cmd = [terminal] + exec_flags + ["bash", "-c", bash_cmd]
        try:
            proc = subprocess.Popen(cmd)
            proc.wait()
            self.status_signal.emit("Update abgeschlossen.")
            self.finished_signal.emit(proc.returncode == 0)
        except Exception as e:
            self.status_signal.emit(f"Fehler beim Update: {e}")
            self.finished_signal.emit(False)


class InstallWorker(QThread):
    status_signal = Signal(str)
    finished_signal = Signal(bool)

    def __init__(self, packages, helper="yay"):
        super().__init__()
        self.packages = packages
        self.helper = helper if helper in ("yay", "paru", "flatpak") else "yay"

    def run(self):
        if not self.packages:
            self.finished_signal.emit(True)
            return

        terminal, exec_flags = find_terminal()
        if terminal is None:
            self.status_signal.emit("Fehler: Kein unterstütztes Terminal gefunden (konsole, kitty, foot, alacritty ...)!")
            self.finished_signal.emit(False)
            return

        total_pkgs = len(self.packages)
        success = True

        for index, pkg in enumerate(self.packages, start=1):
            self.status_signal.emit(f"Installiere Paket {index} von {total_pkgs}: {pkg}...")

            if self.helper == "flatpak":
                bash_cmd = (
                    f"echo '=== Installiere {pkg} (Flatpak) ==='; "
                    f"flatpak install -y flathub {pkg}; "
                    f"echo ''; "
                    f"echo 'Fertig. Dieses Fenster schließt sich gleich automatisch...'; "
                    f"sleep 2"
                )
            else:
                bash_cmd = (
                    f"echo '=== Installiere {pkg} ({index}/{total_pkgs}) mit {self.helper} ==='; "
                    f"{self.helper} -S {pkg}; "
                    f"echo ''; "
                    f"echo 'Fertig. Dieses Fenster schließt sich gleich automatisch...'; "
                    f"sleep 2"
                )

            # Befehlsaufbau je nach Terminal-Syntax
            cmd = [terminal] + exec_flags + ["bash", "-c", bash_cmd]

            try:
                process = subprocess.Popen(cmd)
                process.wait()

                if process.returncode != 0:
                    print(f"Fehler oder Abbruch bei Paket: {pkg} (Terminal: {terminal})")
                    success = False
            except Exception as e:
                print(f"Fehler beim Öffnen von '{terminal}' für {pkg}: {e}")
                success = False

            time.sleep(0.5)

        if success:
            self.status_signal.emit("Alle ausgewählten Programme erfolgreich installiert!")
            self.finished_signal.emit(True)
        else:
            self.status_signal.emit("Installation abgeschlossen (einige Pakete wurden übersprungen oder abgebrochen).")
            self.finished_signal.emit(False)


# --------------------------------------------------------------------------- #
#  Selbst-Update von yakuda-connect
# --------------------------------------------------------------------------- #
# Quelle der Wahrheit für die Version ist self.APP_VERSION in core/main.py.
# Der Prüf-Worker liest genau diese Zeile aus der main.py auf GitHub und
# vergleicht sie mit der lokal laufenden Version. Der Update-Worker führt das
# vorhandene install.sh aus (das ist zugleich der Updater).
APP_RAW_MAIN_URL   = "https://raw.githubusercontent.com/yakuda-stack/yakuda-connect/main/core/main.py"
APP_INSTALL_SH_URL = "https://raw.githubusercontent.com/yakuda-stack/yakuda-connect/main/install.sh"


def _version_tuple(v):
    """'v1.0.7-alpha' -> (1, 0, 7). Nicht-Zahlen werden ignoriert."""
    import re
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums) if nums else ()


def is_remote_newer(local, remote):
    """
    True, wenn 'remote' eine neuere Version als 'local' ist.
    Erst numerischer Vergleich (1.0.7 > 1.0.6). Sind die Zahlen gleich, wird
    ein reiner Suffix-Unterschied (z. B. alpha -> beta) als Update gewertet.
    Lässt sich gar nichts parsen, gilt: ungleich == Update.
    """
    lt, rt = _version_tuple(local), _version_tuple(remote)
    if lt and rt:
        if rt != lt:
            return rt > lt
        return (remote or "").strip() != (local or "").strip()
    return (remote or "").strip() != (local or "").strip()


class AppUpdateCheckWorker(QThread):
    """Prüft im Hintergrund, ob auf GitHub eine neuere yakuda-connect-Version liegt."""
    # (update_verfügbar: bool, remote_version: str)
    result_signal = Signal(bool, str)

    def __init__(self, local_version):
        super().__init__()
        self.local_version = local_version

    def run(self):
        import re
        import urllib.request
        try:
            req = urllib.request.Request(
                APP_RAW_MAIN_URL, headers={"User-Agent": "yakuda-connect"})
            with urllib.request.urlopen(req, timeout=10) as r:
                text = r.read().decode("utf-8", "ignore")
            m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
            if not m:
                self.result_signal.emit(False, "")
                return
            remote = m.group(1).strip()
            self.result_signal.emit(is_remote_newer(self.local_version, remote), remote)
        except Exception:
            # Kein Netz / GitHub nicht erreichbar -> still, kein Pfeil.
            self.result_signal.emit(False, "")


class AppUpdateWorker(QThread):
    """
    Führt das Selbst-Update im Terminal aus, indem es das vorhandene install.sh
    holt und startet (es ersetzt /opt/yakuda-connect durch den aktuellen Stand).
    Ein Terminal ist nötig, weil install.sh 'sudo' verwendet (Passwort-Eingabe).
    Erfolg wird über eine Sentinel-Datei erkannt (Terminal-Exitcodes sind
    je nach Emulator unzuverlässig).
    """
    status_signal   = Signal(str)
    finished_signal = Signal(bool)

    def run(self):
        import os
        import tempfile

        terminal, exec_flags = find_terminal()
        if terminal is None:
            self.status_signal.emit("Fehler: Kein unterstütztes Terminal gefunden!")
            self.finished_signal.emit(False)
            return

        sentinel = os.path.join(tempfile.gettempdir(), f"yakuda_update_ok_{os.getpid()}")
        try:
            if os.path.exists(sentinel):
                os.remove(sentinel)
        except Exception:
            pass

        self.status_signal.emit("yakuda-connect Update läuft ...")

        # install.sh via curl ODER wget beziehen und mit bash ausführen.
        fetch = (
            "if command -v curl >/dev/null 2>&1; then "
            f"  bash <(curl -fsSL {APP_INSTALL_SH_URL}); "
            "elif command -v wget >/dev/null 2>&1; then "
            f"  bash <(wget -qO- {APP_INSTALL_SH_URL}); "
            "else "
            "  echo 'Fehler: weder curl noch wget installiert.'; exit 1; "
            "fi"
        )
        bash_cmd = (
            "echo '=== yakuda-connect Update ==='; "
            f"{fetch}; "
            "rc=$?; echo ''; "
            f"if [ $rc -eq 0 ]; then touch '{sentinel}'; "
            "echo 'Fertig. Dieses Fenster schließt sich gleich automatisch...'; "
            "else echo 'Update fehlgeschlagen (Details siehe oben).'; fi; "
            "sleep 3"
        )
        cmd = [terminal] + exec_flags + ["bash", "-c", bash_cmd]

        try:
            proc = subprocess.Popen(cmd)
            proc.wait()
        except Exception as e:
            self.status_signal.emit(f"Fehler beim Update: {e}")
            self.finished_signal.emit(False)
            return

        ok = os.path.exists(sentinel)
        try:
            if ok:
                os.remove(sentinel)
        except Exception:
            pass

        if ok:
            self.status_signal.emit("Update abgeschlossen.")
        self.finished_signal.emit(ok)
