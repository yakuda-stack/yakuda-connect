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


class InstallWorker(QThread):
    status_signal = Signal(str)
    finished_signal = Signal(bool)

    def __init__(self, packages):
        super().__init__()
        self.packages = packages

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

            bash_cmd = (
                f"echo '=== Installiere {pkg} ({index}/{total_pkgs}) ==='; "
                f"yay -S {pkg}; "
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
