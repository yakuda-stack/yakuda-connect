#!/usr/bin/env python3
import sys
import subprocess
import shutil
import re
import os
import json
import datetime
import platform
from PySide6.QtWidgets import (QApplication, QMainWindow, QLabel, QMessageBox,
                               QHBoxLayout, QVBoxLayout, QComboBox, QLineEdit,
                               QPushButton, QFileDialog, QWidget)
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import (QDesktopServices)

import webbrowser

# --------------------------------------------------------------------------- #
#  Versions-Anker — BITTE NICHT ENTFERNEN
# --------------------------------------------------------------------------- #
# Gepflegt wird die Version in core/version.py (per scripts/bump_version.py).
# Die Zeile unten ist eine ZUSAETZLICHE Kopie und existiert aus einem einzigen
# Grund: Der Update-Checker aller bereits ausgelieferten Versionen (bis v1.1.4)
# laedt diese Datei von GitHub und sucht darin per regulaerem Ausdruck nach
# dem Bezeichner APP_VERSION, gefolgt von der Version in Anfuehrungszeichen.
#
# Faellt die Zeile weg, findet der Ausdruck nichts, und JEDE bereits
# installierte Version meldet fuer immer "du bist aktuell" — die Nutzer
# bekommen nie wieder ein Update angeboten. Deshalb bleibt sie stehen, auch
# wenn sie doppelt aussieht.
#
# ACHTUNG, hier stand bis v1.2.1 eine Falle: Der Kommentar oben nannte das
# gesuchte Muster frueher AUSGESCHRIEBEN, also inklusive Gleichheitszeichen
# und Anfuehrungszeichen. Damit war er selbst der ERSTE Treffer im Text —
# und weil bump_version.py, der Smoke-Test und der Update-Checker alter
# Clients allesamt nur den ersten Treffer auswerten (re.search bzw.
# re.subn(count=1)), wurde jahrelang der KOMMENTAR hochgezaehlt, waehrend die
# echte Zeile unten auf v1.1.4 stehen blieb. Aufgefallen ist es nie, weil der
# Kommentar zufaellig die richtige Nummer trug. Deshalb ist das Muster oben
# jetzt umschrieben: die Zeile unten ist der einzige Treffer.
#
# scripts/bump_version.py haelt sie automatisch mit core/version.py gleich,
# und der Smoke-Test bricht ab, falls beide auseinanderlaufen oder das Muster
# mehr als einmal vorkommt.
APP_VERSION = "v1.2.4"

# Community-Links (Settings -> "Community & Updates")
DISCORD_URL = "https://discord.gg/X5TaN4A47h"
KOFI_URL    = "https://ko-fi.com/yakuda_"

# Ubuntu/Debian: WiVRn ist nicht in den Repos. Diese Befehle bauen es nativ —
# schlanker und schneller als ein Flatpak, dafür einmalig etwas Handarbeit.
UBUNTU_BUILD_COMMANDS = """# 1) Build-Werkzeuge und Abhängigkeiten
sudo apt update
sudo apt install -y git cmake build-essential ninja-build pkg-config \\
    libvulkan-dev glslang-tools libavcodec-dev libavutil-dev libavfilter-dev \\
    libx264-dev libva-dev libeigen3-dev nlohmann-json3-dev libcli11-dev \\
    libudev-dev libwayland-dev libx11-dev libxrandr-dev libgl1-mesa-dev \\
    libbsd-dev libsystemd-dev libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \\
    libpulse-dev libopenxr-dev libavdevice-dev

# 2) WiVRn holen und bauen
git clone https://github.com/WiVRn/WiVRn.git
cd WiVRn
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DWIVRN_BUILD_CLIENT=OFF
cmake --build build

# 3) Installieren (legt /usr/local/share/openxr/1/openxr_wivrn.json an)
sudo cmake --install build

# 4) OpenComposite fuer OpenVR-Spiele (z. B. VRChat)
git clone https://gitlab.com/znixian/OpenOVR.git ~/opencomposite
cd ~/opencomposite
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
sudo mkdir -p /opt/opencomposite
sudo cp -r build/bin/linux64 /opt/opencomposite/"""

# Korrektur des Pfads für das UI, da main.py jetzt in core/ liegt
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui.ui_main import Ui_MainWindow

# Tab-Logik (Mixins, siehe core/tabs/)
from tabs.games_mixin import GamesTabMixin
from tabs.tools_mixin import ToolsTabMixin

# Interne Importe (liegen im selben Ordner 'core')
from install_worker import (InstallWorker, UpdateWorker, AppUpdateCheckWorker,
                            AppUpdateWorker, XrizerGithubWorker)
import appimage_installer as appimg
import vr_environment as venv
import wivrn_dashboard as wivrn_dash
import usb_headsets as usbhs
from config_manager import load_saved_settings, save_all_settings
from streaming_tab import StreamingTab
from backup_manager import (create_vr_backup, restore_vr_environment,
                            sync_backup_from_github)
import vr_autotune as autotune
from programs import (INSTALL_PACKAGES, INSTALL_DNF, INSTALL_DNF_COPR,
                      INSTALL_APT, APT_BINARY_FALLBACK, UBUNTU_WIVRN_PPA,
                      apt_github_groups, DNF_BINARY_FALLBACK, SOURCE_LABELS,
                      SOURCE_COPR, SOURCE_GITHUB, SOURCE_PPA, SOURCE_FLATPAK,
                      WIVRN_FLATPAK_ID,
                      component_sources, dnf_copr_groups, dnf_copr_for_package,
                      TOOLS_APPS, TOOLS_OSC)
import games as games_db
import openxr_manager as oxr
import overlay_manager as ovl
import paths
import proc
import firewall as fw
import advanced_info as adv
from jsonio import update_json
import version as version_mod
from ui import theme
from translations import tr, tr_amp, set_language, get_language
from PySide6.QtCore import QThread, Signal as QtSignal

from logging_setup import get_logger, read_log_tail

log = get_logger("main")



class PackageCheckWorker(QThread):
    """
    Ermittelt im Hintergrund, welche Pakete installiert sind und fuer welche
    ein Update bereitliegt.

    Der Trick: die Paketlisten werden EINMAL komplett geholt und danach im
    Speicher nachgeschlagen — statt je Paket einen eigenen Prozess zu starten.
    Aus bis zu zwoelf Aufrufen werden so zwei, unabhaengig von der Anzahl der
    geprueften Pakete.

    Signal: result_signal(results, updates_available)
        results = {"WiVRn / Monado": {"installed": bool, "has_update": bool}, ...}
    """
    result_signal = QtSignal(dict, bool)

    def __init__(self, method, groups):
        super().__init__()
        self.method = method
        self.groups = dict(groups)

    def _installed_and_updatable(self):
        """
        (installierte Pakete, Pakete mit Update) als Mengen von Namen.

        'yay -Qu' braucht laenger als 'yay -Q', weil es das AUR abfragt.
        Schlaegt es fehl (kein Netz, Spiegelserver weg), gilt einfach
        "keine Updates bekannt" — der Paketstatus bleibt trotzdem korrekt,
        statt dass die ganze Anzeige leer bleibt.
        """
        if self.method == "dnf":
            # rpm -qa listet alle Pakete; Zeilen sind "name-version-release.arch".
            # Fuer den Abgleich reicht der Anfang des Namens.
            out = proc.output_of(["rpm", "-qa", "--qf", "%{NAME}\\n"],
                                 timeout=proc.LONG_TIMEOUT)
            installed = {line.strip() for line in out.splitlines() if line.strip()}
            return installed, set()

        if self.method == "apt":
            # dpkg-query listet auch entfernte Pakete, deren Konfiguration noch
            # da ist ("rc"). Nur 'installed' zaehlt — sonst gilt ein
            # deinstalliertes WiVRn weiter als vorhanden.
            out = proc.output_of(["dpkg-query", "-W",
                                  "-f=${binary:Package} ${db:Status-Status}\\n"],
                                 timeout=proc.LONG_TIMEOUT)
            installed = set()
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "installed":
                    installed.add(parts[0].split(":")[0])   # ':amd64' abschneiden
            # 'apt list --upgradable' braucht keine Root-Rechte und keinen
            # vorherigen update-Lauf; ohne frische Paketlisten meldet es nur
            # weniger, statt zu scheitern.
            upgradable = set()
            out = proc.output_of(["apt", "list", "--upgradable"],
                                 timeout=proc.LONG_TIMEOUT)
            for line in out.splitlines():
                if "/" in line:
                    upgradable.add(line.split("/")[0].split(":")[0])
            return installed, upgradable

        if self.method == "native" or not self.method:
            return None, set()          # wird ueber shutil.which geprueft

        if not shutil.which(self.method):
            return set(), set()

        # pacman/yay/paru: "name version" je Zeile
        out = proc.output_of([self.method, "-Q"], timeout=proc.LONG_TIMEOUT)
        installed = {line.split()[0] for line in out.splitlines() if line.strip()}

        out_up = proc.output_of([self.method, "-Qu"], timeout=proc.LONG_TIMEOUT)
        updatable = {line.split()[0] for line in out_up.splitlines() if line.strip()}
        return installed, updatable

    def run(self):
        try:
            installed, updatable = self._installed_and_updatable()
        except Exception:
            log.exception("Paketpruefung fehlgeschlagen")
            self.result_signal.emit({}, False)
            return

        results = {}
        updates_available = False
        for name, idents in self.groups.items():
            if installed is None:
                # 'native': es gibt keine Paketverwaltung — nur schauen, ob
                # die Binary im PATH liegt.
                state = {"installed": shutil.which("wivrn-server") is not None,
                         "has_update": False}
            else:
                is_installed = all(pkg in installed for pkg in idents)
                if not is_installed and self.method in ("dnf", "apt"):
                    # Selbst gebaut oder aus einem fremden Repo: kein RPM, aber
                    # das Programm ist da. Frueher stand hier trotzdem "fehlt",
                    # und ein Klick auf Installieren waere ins Leere gelaufen.
                    fallback = (DNF_BINARY_FALLBACK if self.method == "dnf"
                                else APT_BINARY_FALLBACK)
                    binary = fallback.get(name)
                    if binary and shutil.which(binary):
                        is_installed = True
                    # Der Flatpak legt keine Binary in den PATH und taucht in
                    # keiner Paketliste auf — ohne diese Abfrage stuende in der
                    # Zeile "fehlt", obwohl WiVRn laeuft.
                    elif (self.method == "apt" and name in INSTALL_APT
                          and appimg.flatpak_app_installed(WIVRN_FLATPAK_ID)):
                        is_installed = True
                state = {"installed": is_installed,
                         "has_update": any(pkg in updatable for pkg in idents)}
            if state["has_update"]:
                updates_available = True
            results[name] = state

        self.result_signal.emit(results, updates_available)


class ApkWorker(QThread):
    """Lädt die neueste WiVRn APK von GitHub und installiert sie per adb."""
    status_signal  = QtSignal(str)   # Statustext
    finished_signal = QtSignal(bool) # Erfolg/Fehler

    GITHUB_API = "https://api.github.com/repos/WiVRn/WiVRn/releases/latest"
    APK_CACHE  = os.path.expanduser("~/.cache/yakuda-connect/wivrn-latest.apk")

    def __init__(self):
        super().__init__()
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        import urllib.request
        import urllib.error

        try:
            # 1. Neueste Release-Info von GitHub holen
            self.status_signal.emit("Find the latest version of WiVRn...")
            req = urllib.request.Request(self.GITHUB_API,
                headers={"User-Agent": "yakuda-connect"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())

            # APK-Asset finden (endet auf -release.apk)
            apk_url = None
            tag = data.get("tag_name", "unbekannt")
            for asset in data.get("assets", []):
                if asset["name"].endswith("-release.apk"):
                    apk_url = asset["browser_download_url"]
                    break

            if not apk_url:
                self.status_signal.emit("Fehler: No APK found in the current release.")
                self.finished_signal.emit(False)
                return

            self.status_signal.emit(f"found: WiVRn {tag} — starting Download...")

            # 2. APK herunterladen
            os.makedirs(os.path.dirname(self.APK_CACHE), exist_ok=True)
            with urllib.request.urlopen(apk_url, timeout=60) as r, \
                 open(self.APK_CACHE, "wb") as f:
                total = int(r.headers.get("Content-Length", 0))
                downloaded = 0
                while True:
                    if self._cancel:
                        self.status_signal.emit("Download interrupted.")
                        self.finished_signal.emit(False)
                        return
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        mb_done = downloaded / 1_000_000
                        mb_total = total / 1_000_000
                        self.status_signal.emit(
                            f"Lade herunter... {mb_done:.1f} MB / {mb_total:.1f} MB")

            # 3. ADB-Gerät suchen
            self.status_signal.emit("Search for a USB-connected headset...")
            res = subprocess.run(["adb", "devices"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=proc.LONG_TIMEOUT)

            devices = [l.split()[0] for l in res.stdout.splitlines()
                       if l.strip() and not l.startswith("List") and "device" in l]

            if not devices:
                self.status_signal.emit(
                    "No headset found! Enable USB debugging and check the cable.")
                self.finished_signal.emit(False)
                return

            serial = devices[0]
            self.status_signal.emit(f"Headset found: {serial} — install APK...")

            # 4. APK installieren
            res = subprocess.run(
                ["adb", "-s", serial, "install", "-r", self.APK_CACHE],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=proc.LONG_TIMEOUT)

            if res.returncode == 0:
                self.status_signal.emit(f"✔ WiVRn {tag} successfully installed!")
                self.finished_signal.emit(True)
            else:
                self.status_signal.emit(f"Error during adb install going to tools and install android tools:\n{res.stderr.strip()}")
                self.finished_signal.emit(False)

        except Exception as e:
            self.status_signal.emit(f"Fehler: {e}")
            self.finished_signal.emit(False)


class UsbHeadsetWorker(QThread):
    """
    Sucht im Hintergrund nach einer per USB angeschlossenen Brille.

    Warum ein eigener Thread: der Teil ueber sysfs ist zwar sofort fertig,
    der anschliessende ``adb devices``-Aufruf kann aber Sekunden brauchen —
    adb startet dabei ggf. erst seinen Daemon. Im GUI-Thread wuerde das
    Fenster genau so lange haengen, und zwar alle paar Sekunden erneut.
    """
    result_signal = QtSignal(dict)

    def run(self):
        try:
            info = usbhs.scan()
            # Gleich mitnehmen: laeuft das WiVRn-Dashboard? Das ist ein
            # pgrep-Aufruf, der im GUI-Thread nichts verloren hat, und der
            # Tooltip des USB-Hakens haengt davon ab.
            info["dashboard_running"] = wivrn_dash.dashboard_is_running()
            self.result_signal.emit(info)
        except Exception as exc:  # noqa: BLE001 — Anzeige darf nie abstuerzen
            log.debug("USB-Erkennung fehlgeschlagen: %s", exc)
            self.result_signal.emit({"devices": [], "headset": None,
                                     "state": "none", "adb_state": "",
                                     "dashboard_running": False,
                                     "profile": usbhs.profile_for(None)})


class VRApp(GamesTabMixin, ToolsTabMixin, QMainWindow):
    """
    Hauptfenster.

    Der Games- und der Tools-Tab liegen als Mixins in core/tabs/ — sie
    arbeiten auf demselben self, sind hier also ganz normal als Methoden
    verfuegbar. In dieser Datei bleiben: Fenster-Aufbau, Installation,
    Dashboard, Streaming, OpenXR, Autostart und Server-Steuerung.
    """
    def __init__(self):
        super().__init__()
        #loading initliserung
        self.is_loading = True
        # UI Instanziieren und anwenden
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # === ORDNERSTRUKTUR FIX ===
        PROJEKT_CONFIG_DIR = paths.config_dir()
        paths.ensure_dirs()
        log.info(f"[System] Folder structure checked/created under: {PROJEKT_CONFIG_DIR}")

        # Aus core/version.py — der einen Quelle der Wahrheit. Der Anker oben
        # in dieser Datei ist nur fuer den Update-Check ALTER Clients da.
        self.APP_VERSION = version_mod.APP_VERSION
        self.server_process = None
        self.pairing_process = None

        # --- Games-Tab ---
        self._games_scan_worker = None       # laufender Scan-Thread
        self._pp_worker = None               # laufender ProtonPlus-Install-Thread
        self._vrc_check_worker = None        # laufende VRChat-Videoplayer-Diagnose
        self._vci_worker = None              # laufende VRCVideoCacher-Installation
        self._games_tab_visited = False      # erster Klick auf den Tab -> Auto-Scan
        self._games_untested_names = {}      # appid -> Anzeigename (ungetestete Spiele)
        self._games_tile_pos = {}            # appid -> (grid, zeile, spalte) fürs Inline-Panel
        self._games_detail_widget = None     # aktuell ausgeklapptes Inline-Panel
        self._detail_params_edit = None      # Feld mit den FINALEN Parametern (für "Play")
        self._detail_status_lbl = None       # Statuszeile des offenen Panels
        self._detail_toggles = {}            # toggle_key -> QCheckBox des offenen Panels
        self._detail_custom_edit = None      # Feld für eigene Parameter
        self._detail_base_params = ""        # hinterlegte Basis-Parameter des Spiels
        self._selected_proton = games_db.load_selected_protons()  # appid -> per "Use" gewählte Version

        # Gemerkter Server-Zustand — die Anzeige liest nur noch diese Variable,
        # statt jede Sekunde per Subprozess zu prüfen. Der manuelle Check-Knopf
        # gleicht sie bei Bedarf mit der Realität ab.
        self._server_running = False
        self._syncing_toggle = False         # True während der Schalter nur angeglichen wird

        # --- Autostart: Apps folgen der Headset-Verbindung ---
        # Starten, sobald ein Spieler verbindet; beenden bei Trennung oder Server-Stopp.
        self._headset_connected = False      # zuletzt erkannter Verbindungszustand
        self._disconnect_count = 0           # aufeinanderfolgende "getrennt"-Messungen (Entprellung)
        self._autostart_procs = []           # laufende Autostart-Prozesse (zum Beenden)
        self._server_log_fh = None           # Datei-Handle für die Server-Ausgabe
        self._server_log_path = os.path.expanduser("~/.cache/yakuda-connect/wivrn-server.log")

        # Wie viele Sekunden "getrennt" am Stück, bevor die Apps beendet werden
        # (verhindert, dass kurze Aussetzer die Programme killen).
        self._disconnect_grace = 3

        # --- Einweg-Autostart-Timer ---
        # Wird beim Server-Start scharfgeschaltet, prüft im Sekundentakt
        # is_headset_connected() und BEENDET SICH SELBST, sobald er die Programme
        # einmal gestartet hat. Danach läuft kein Polling mehr (schont CPU),
        # bis er per Button / Server-Neustart neu scharfgeschaltet wird.
        self._autostart_launched = False     # In diesem Zyklus bereits gestartet?
        self.autostart_timer = QTimer(self)
        self.autostart_timer.setInterval(1000)   # 1x pro Sekunde
        self.autostart_timer.timeout.connect(self._poll_headset_for_autostart)

        # --- USB-Ampel im Dashboard ---
        # Laeuft NUR, solange der Dashboard-Tab offen ist (siehe
        # on_tab_changed). Im Games- oder Tools-Tab braucht niemand die
        # Anzeige, und ein adb-Aufruf alle paar Sekunden waere reine
        # Beschaeftigung fuer die Platte.
        self._usb_worker = None
        self._usb_last_info = None           # zuletzt erkannter Zustand
        # Gespeicherter refresh_rate-Wert ohne Bedienelement (siehe
        # apply_loaded_settings) — wird beim Speichern unveraendert
        # weitergereicht.
        self._stored_refresh_rate = "Auto"
        self.usb_poll_timer = QTimer(self)
        self.usb_poll_timer.setInterval(4000)
        self.usb_poll_timer.timeout.connect(self.check_usb_headset)

        self.is_loading = True  # Verhindert das Speichern während des Ladens

        self.required_packages = INSTALL_PACKAGES

        # Paket-Status-Labels werden methoden-abhängig erzeugt (_rebuild_package_rows)
        self.prog_labels = {}

        self.init_logic_connections()
        # Farbthema anwenden, sobald die Oberflaeche steht. Vorher hat noch
        # kein Widget ein Stylesheet, das sich umfaerben liesse.
        self.apply_theme()
        if hasattr(self.ui, "customization_widget"):
            self.ui.customization_widget.changed.connect(self.apply_theme)
        self._rebuild_package_rows()
        self.check_system_packages()

        # Start-Tab Sperren-Logik (Lock)
        if self.are_critical_packages_missing():
            self.ui.sidebar.setCurrentRow(0)
            QMessageBox.warning(
                self,
                tr("msg_components_title"),
                tr("msg_components_text")
            )
        else:
            self.ui.sidebar.setCurrentRow(1)

        # Kein Sekunden-Timer mehr: Der Server-Status wird gemerkt (Toggle) und
        # nur auf Knopfdruck wirklich nachgeprüft. Beim Start einmal abgleichen,
        # falls der Server bereits läuft (z. B. aus einer früheren Sitzung).
        self.manual_server_check()

        self.apply_loaded_settings()
        self.is_loading = False

# Erststart- / Willkommenstext für den Nutzer setzen
        self._set_welcome_text()

        # --- Selbst-Update (yakuda-connect) ---
        # Versions-Label aus der EINEN Quelle der Wahrheit (APP_VERSION) setzen
        # und kurz nach dem Start still im Hintergrund nach einem Update schauen.
        self._app_update_available = False
        self._app_remote_version = ""
        self._app_update_check_worker = None

        # --- Spiel-Cover ---
        # Kacheln, deren Bild noch fehlt: {appid: QLabel}. Werden nach dem
        # Aufbau des Games-Tabs im Hintergrund vom Steam-CDN nachgeladen.
        self._pending_covers = {}
        self._cover_worker = None
        self._app_update_worker = None
        self._refresh_app_version_label()
        QTimer.singleShot(1500, self.check_app_update)
        # Beim Start prüfen: gibt es laut Config schon ein VR-Backup?
        # Falls nein, aber eine VR-Umgebung existiert (openxr/wivrn — nativ
        # oder Flatpak-Pfade), wird EINMALIG automatisch ein Backup angelegt.
        # Läuft im Hintergrund-Thread, damit die UI nicht blockiert
        # (/opt/opencomposite & Co. können größer sein).
        self._auto_backup_worker = None
        QTimer.singleShot(2500, self._start_auto_backup_check)
        # Steam-Schutz: System-OpenXR-Manifeste (/usr/share/openxr/1) pruefen.
        # Ein Manifest mit falschem Bibliothekspfad laesst Steam gar nicht mehr
        # starten (pressure-vessel: "invalid `Elf' handle").
        self._oxr_health_worker = None
        self._oxr_health_asked = False
        QTimer.singleShot(4000, self._start_openxr_health_check)

    def _set_welcome_text(self):
        """Setzt den Willkommenstext je nach aktiver Sprache."""
        lang = get_language()
        if lang == "de":
            html = """
            <p style='color: #88c0d0; font-weight: bold; font-size: 15px; margin-bottom: 8px;'>
                Willkommen bei Linux VR Central!
            </p>
            <p style='margin-bottom: 12px;'>
                Wenn du die Software zum ersten Mal startest, vergewissere dich, dass dein Headset eingeschaltet und im selben Netzwerk ist.
                <b>Wichtig:</b> Bitte lies dir die folgenden Backup-Hinweise durch. Weiter unten findest du zudem wichtige Informationen zur Performance.
            </p>
            <hr style='border: none; border-top: 1px solid #3b4252; margin-bottom: 12px;' />
            <p style='color: #d08770; font-weight: bold; margin-bottom: 4px;'>⚠️ WICHTIG: Erster Start & OpenXR-Backups</p>
            <ul style='margin-top: 0px; margin-bottom: 14px; padding-left: 20px;'>
                <li style='margin-bottom: 4px;'>Bitte starte diesen Launcher <b>einmal komplett neu</b>, nachdem du das erste Mal ein Spiel in VR gestartet hast.</li>
                <li>Nach dem Neustart erscheinen hier darüber <b>zwei neue Buttons</b>. Damit kannst du ein Backup deiner OpenXR/OpenVR-Umgebung erstellen.</li>
            </ul>
            <p style='color: #ebcb8b; font-weight: bold; margin-bottom: 4px;'>ℹ️ Info: Erststart, Performance & OpenVR-Kompatibilität</p>
            <ul style='margin-top: 0px; padding-left: 20px;'>
                <li style='margin-bottom: 4px;'>Die OpenVR-Kompatibilität wird beim ersten Mal automatisch auf <b>OpenComposite</b> gestellt.</li>
                <li>Nach dem ersten erfolgreichen Verbinden kannst du die Runtime für mehr Performance auf <b>xrizer</b> umstellen.</li>
            </ul>"""
        else:
            html = """
            <p style='color: #88c0d0; font-weight: bold; font-size: 15px; margin-bottom: 8px;'>
                Welcome to Linux VR Central!
            </p>
            <p style='margin-bottom: 12px;'>
                When starting the software for the first time, make sure your headset is powered on and connected to the same network.
                <b>Important:</b> Please read the backup notes below. You will also find important performance information further down.
            </p>
            <hr style='border: none; border-top: 1px solid #3b4252; margin-bottom: 12px;' />
            <p style='color: #d08770; font-weight: bold; margin-bottom: 4px;'>⚠️ IMPORTANT: First Launch & OpenXR Backups</p>
            <ul style='margin-top: 0px; margin-bottom: 14px; padding-left: 20px;'>
                <li style='margin-bottom: 4px;'>Please restart this launcher <b>once</b> after launching a VR game for the first time.</li>
                <li>After restarting, <b>two new buttons</b> will appear above. Use them to create a backup of your OpenXR/OpenVR environment.</li>
            </ul>
            <p style='color: #ebcb8b; font-weight: bold; margin-bottom: 4px;'>ℹ️ Info: First Launch, Performance & OpenVR Compatibility</p>
            <ul style='margin-top: 0px; padding-left: 20px;'>
                <li style='margin-bottom: 4px;'>OpenVR compatibility is automatically set to <b>OpenComposite</b> on first launch.</li>
                <li>After successfully connecting, you can switch the runtime to <b>xrizer</b> for better performance.</li>
            </ul>"""
        self.ui.txt_free_info.setHtml(html)

    # ------------------------------------------------------------------ #
    #  Selbst-Update von yakuda-connect (kleiner Pfeil neben der Version)
    # ------------------------------------------------------------------ #
    def _refresh_app_version_label(self):
        """Setzt das App-Versions-Label aus APP_VERSION und pflegt den Pfeil-Tooltip."""
        self.ui.lbl_app_ver.setText(f"<b>{tr('app_version_label')}</b> {self.APP_VERSION}")
        # Auch die Community-Box in den Settings zeigt die aktuelle Version an.
        if hasattr(self.ui, "lbl_community_version"):
            self.ui.lbl_community_version.setText(
                tr("community_version").format(version=self.APP_VERSION))
        if getattr(self, "_app_update_available", False) and self._app_remote_version:
            self.ui.btn_app_update.setToolTip(
                tr("app_update_tooltip").format(version=self._app_remote_version))

    def check_app_update(self):
        """Startet den stillen Versions-Check im Hintergrund."""
        if self._app_update_check_worker is not None and self._app_update_check_worker.isRunning():
            return
        self._app_update_check_worker = AppUpdateCheckWorker(self.APP_VERSION)
        self._app_update_check_worker.result_signal.connect(self._on_app_update_checked)
        self._app_update_check_worker.start()

    def _on_app_update_checked(self, available, remote_version):
        """Blendet den Update-Pfeil ein/aus — je nach Ergebnis des Checks."""
        self._app_update_available = bool(available)
        self._app_remote_version = remote_version or ""
        # Paketinstallation (AUR): niemals den Selbst-Update-Pfeil zeigen —
        # Updates laufen dort ausschließlich über yay/paru.
        if appimg.is_package_managed_install():
            self.ui.btn_app_update.setVisible(False)
            return
        if available:
            self.ui.btn_app_update.setToolTip(
                tr("app_update_tooltip").format(version=self._app_remote_version))
            self.ui.btn_app_update.setVisible(True)
        else:
            self.ui.btn_app_update.setVisible(False)

    def start_app_self_update(self):
        """Klick auf den Pfeil: nachfragen, dann install.sh im Terminal ausführen."""
        # AUR/Distro-Paket: install.sh würde eine zweite Kopie unter /opt anlegen
        # und pacman aushebeln -> stattdessen den korrekten Weg nennen.
        if appimg.is_package_managed_install():
            QMessageBox.information(self, tr("app_update_title"),
                                    tr("app_update_pkg_managed"))
            return

        ver = self._app_remote_version or "?"
        reply = QMessageBox.question(
            self, tr("app_update_title"),
            tr("app_update_confirm").format(version=ver),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        self.ui.btn_app_update.setEnabled(False)
        self._app_update_worker = AppUpdateWorker()
        self._app_update_worker.finished_signal.connect(self._on_app_self_update_done)
        self._app_update_worker.start()

    def _on_app_self_update_done(self, ok):
        self.ui.btn_app_update.setEnabled(True)
        if ok:
            r = QMessageBox.question(
                self, tr("app_update_title"), tr("app_update_restart"),
                QMessageBox.Yes | QMessageBox.No)
            if r == QMessageBox.Yes:
                self._restart_app()
            else:
                # Nutzer will später neu starten -> Pfeil ausblenden (schon aktualisiert)
                self._app_update_available = False
                self.ui.btn_app_update.setVisible(False)
        else:
            QMessageBox.warning(self, tr("app_update_title"), tr("app_update_failed"))

    def _restart_app(self):
        """Startet yakuda-connect neu, um den frisch installierten Code zu laden."""
        try:
            subprocess.Popen(["yakuda-connect"])
        except Exception:
            # Aus dem Quellcode gestartet (kein Wrapper) -> gleiches Skript neu starten
            try:
                os.execv(sys.executable, [sys.executable] + sys.argv)
                return
            except Exception as exc:
                log.debug("_restart_app: ignoriert — %s", exc)
        QApplication.quit()

    # ------------------------------------------------------------------ #
    #  Community & Updates (Settings, ganz oben)
    # ------------------------------------------------------------------ #
    def manual_check_app_update(self):
        """Klick auf 'Nach Updates suchen': Check starten und Ergebnis melden."""
        if self._app_update_check_worker is not None and self._app_update_check_worker.isRunning():
            return
        self.ui.btn_community_check.setEnabled(False)
        self.ui.lbl_community_version.setText(tr("community_checking"))
        self._app_update_check_worker = AppUpdateCheckWorker(self.APP_VERSION)
        self._app_update_check_worker.result_signal.connect(self._on_manual_update_checked)
        self._app_update_check_worker.start()

    def _on_manual_update_checked(self, available, remote_version):
        """Ergebnis des manuellen Checks: Dialog anzeigen + Pfeil pflegen."""
        self.ui.btn_community_check.setEnabled(True)
        self._refresh_app_version_label()
        # Pfeil im Dashboard mitpflegen (gleiche Logik wie der stille Check)
        self._on_app_update_checked(available, remote_version)

        if available:
            # Direkt das bestehende Update-Verfahren anbieten (install.sh im Terminal)
            self.start_app_self_update()
        elif remote_version:
            QMessageBox.information(
                self, tr("app_update_title"),
                tr("community_uptodate").format(version=self.APP_VERSION))
        else:
            QMessageBox.warning(
                self, tr("app_update_title"), tr("community_check_failed"))

    def open_discord_link(self):
        QDesktopServices.openUrl(QUrl(DISCORD_URL))

    def open_kofi_link(self):
        QDesktopServices.openUrl(QUrl(KOFI_URL))

    # ------------------------------------------------------------------ #
    #  Diagnose: Logdatei                                                 #
    # ------------------------------------------------------------------ #
    # ------------------------------------------------------------------ #
    #  Auto-Connect per USB (WiVRn-Dashboard-Einstellung)                 #
    # ------------------------------------------------------------------ #
    def load_usb_autoconnect(self):
        """
        Zustand aus wivrn-dashboard.conf uebernehmen. Bewusst NICHT aus
        unserer eigenen Konfiguration: die Datei des Dashboards ist die
        Wahrheit — der Nutzer kann die Option ja auch dort umstellen.
        """
        self.ui.check_usb_autoconnect.blockSignals(True)
        self.ui.check_usb_autoconnect.setChecked(wivrn_dash.get_auto_connect_usb())
        self.ui.check_usb_autoconnect.blockSignals(False)
        self._update_usb_tooltip()

    def _update_usb_tooltip(self, running=None):
        """
        Tooltip des Hakens "Automatisch per USB verbinden".

        Laeuft das WiVRn-Dashboard gerade, wird der Hinweis angehaengt, dass
        es seine Einstellungen beim Beenden zurueckschreibt und diese
        Aenderung damit wieder kassieren kann. Frueher stand das als
        dauerhafte gelbe Zeile im Dashboard — fuer einen Sonderfall zu viel
        Platz. Im Tooltip steht es genau dort, wo man ohnehin hinschaut,
        bevor man den Haken setzt.

        ``running=None`` heisst "selbst nachsehen". Der Aufrufer kann das
        Ergebnis auch mitgeben, wenn er es (etwa aus dem Hintergrund-Thread)
        schon hat — dann laeuft hier kein zweites pgrep.
        """
        if running is None:
            running = wivrn_dash.dashboard_is_running()
        tip = tr("streaming_usb_autoconnect_tip")
        if running:
            # Der uebersetzte Text bringt sein Warnzeichen selbst mit.
            tip = f"{tip}\n\n{tr('streaming_usb_dashboard_running')}"
        self.ui.check_usb_autoconnect.setToolTip(tip)

    def on_usb_autoconnect_toggled(self, checked):
        """Schreibt die Option direkt in die Dashboard-Konfiguration."""
        if not wivrn_dash.set_auto_connect_usb(checked):
            # Zurueckstellen, damit der Haken nicht etwas anzeigt, was nicht
            # gespeichert wurde.
            self.ui.check_usb_autoconnect.blockSignals(True)
            self.ui.check_usb_autoconnect.setChecked(not checked)
            self.ui.check_usb_autoconnect.blockSignals(False)
            QMessageBox.warning(self, tr("streaming_usb_autoconnect"),
                                tr("streaming_usb_write_failed").format(
                                    path=wivrn_dash.dashboard_config_file()))
            return
        self._update_usb_tooltip()

    # ------------------------------------------------------------------ #
    #  USB-Ampel: haengt eine Brille am Kabel — und wuerde sie verbinden?  #
    # ------------------------------------------------------------------ #
    def check_usb_headset(self):
        """
        Startet einen Erkennungslauf im Hintergrund. Laeuft noch einer, wird
        NICHT nachgelegt — sonst stapeln sich bei langsamem adb die Threads.
        """
        if self._usb_worker is not None and self._usb_worker.isRunning():
            return
        self._usb_worker = UsbHeadsetWorker()
        self._usb_worker.result_signal.connect(self._on_usb_scan_done)
        self._usb_worker.start()

    def _on_usb_scan_done(self, info):
        self._render_usb_state(info)

    def _render_usb_state(self, info):
        """
        Zeichnet die kompakte USB-Zeile unter den gekoppelten Headsets.

        Sichtbar wird sie NUR, wenn es etwas zu tun gibt: Kabel steckt, aber
        WiVRn kaeme per adb nicht dran. Laeuft alles (gruen) oder haengt gar
        nichts am Kabel (grau), bleibt die Zeile weg — dass eine Brille per
        USB da ist, steht dann schon als "· USB" an ihrem Listeneintrag.

        Bewusst getrennt vom Scan: nach einem Sprachwechsel wird nur neu
        gezeichnet, ohne erneut zu suchen — dafuer merkt sich diese Methode
        den zuletzt gezeichneten Zustand.
        """
        vorher = self._usb_device_names()
        if info:
            self._usb_last_info = info

        info = self._usb_last_info
        state = (info or {}).get("state", "none")
        headset = (info or {}).get("headset") or {}
        name = headset.get("name", "")

        if state == "unauthorized":
            color, text = "#ebcb8b", tr("usb_state_unauthorized").format(name=name)
        elif state == "usb_only":
            color, text = "#ebcb8b", tr("usb_state_usb_only").format(name=name)
        elif state == "no_adb":
            color, text = "#ebcb8b", tr("usb_state_no_adb").format(name=name)
        elif state == "ready":
            color, text = "#a3be8c", ""
        else:
            color, text = "#4c566a", ""

        self.ui.lbl_usb_led.setStyleSheet(f"color:{color}; font-size:14px;")
        self.ui.lbl_usb_state.setText(text)
        self.ui.usb_state_widget.setVisible(bool(text))

        self._apply_refresh_profile((info or {}).get("profile"))
        # Tooltip des USB-Hakens aktuell halten (Dashboard kann zwischendurch
        # gestartet oder beendet worden sein).
        if info is not None and "dashboard_running" in info:
            self._update_usb_tooltip(info["dashboard_running"])

        # Liste nur dann neu einlesen, wenn sich am Kabel wirklich etwas
        # geaendert hat — sonst liefe alle vier Sekunden ein wivrnctl-Aufruf
        # ins Leere.
        if self._usb_device_names() != vorher:
            self.refresh_headset_list()

    def _usb_device_names(self):
        """Namen der aktuell per USB erkannten Brillen (klein geschrieben)."""
        info = self._usb_last_info or {}
        return tuple(sorted(
            (d.get("name") or "").strip().lower()
            for d in info.get("devices", []) if d.get("name")))

    def _apply_refresh_profile(self, profile):
        """
        Zeigt, welche Bildwiederholraten die erkannte Brille beherrscht.

        Bewusst nur eine Anzeige: Die Rate laesst sich vom PC aus gar nicht
        setzen — WiVRns Server-Konfiguration hat dafuer keinen Schluessel,
        der Client im Headset bestimmt sie (siehe core/config_manager.py).
        Frueher stand hier ein Auswahlfeld, dessen Wert wirkungslos in WiVRns
        config.json landete.
        """
        rates = (profile or {}).get("rates") or usbhs.ALL_RATES
        model = (profile or {}).get("model", "")

        if model:
            self.ui.lbl_refresh_value.setText(
                tr("refresh_supported").format(
                    name=model,
                    rates=", ".join(f"{r}" for r in rates)))
        else:
            self.ui.lbl_refresh_value.setText(tr("refresh_no_headset"))
        self.ui.lbl_refresh_hint.setText(tr("refresh_where"))

    def open_log_file(self):
        """Oeffnet die Logdatei im Standardprogramm des Systems."""
        path = paths.log_file()
        if not os.path.exists(path):
            QMessageBox.information(self, tr("diag_title"), tr("diag_no_log"))
            return
        # openUrl waehlt den vom Desktop registrierten Texteditor. Schlaegt
        # das fehl (z. B. minimale Umgebung ohne xdg-open), bekommt der
        # Nutzer wenigstens den Pfad genannt, statt dass nichts passiert.
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            QMessageBox.warning(self, tr("diag_title"),
                                tr("diag_open_failed").format(path=path))

    def copy_log_to_clipboard(self):
        """
        Kopiert das Ende des Logs in die Zwischenablage — gedacht zum
        Einfuegen in Discord oder einen Fehlerbericht.

        Bewusst nur der Schluss (read_log_tail begrenzt auf ~200 KB): bei
        einer lange laufenden Sitzung waere die ganze Datei mehrere Megabyte
        gross und in einer Chatnachricht ohnehin nicht brauchbar.
        """
        text = read_log_tail()
        QApplication.clipboard().setText(text)
        QMessageBox.information(
            self, tr("diag_title"),
            tr("diag_copied").format(lines=len(text.splitlines())))

    def save_diagnostics_file(self):
        """
        Schreibt einen Diagnosebericht in eine Datei, die der Nutzer an einen
        Fehlerbericht anhaengen kann.

        Warum nicht einfach die Logdatei kopieren: fuer eine Fehlersuche
        fehlen darin die Randbedingungen (Version, Distribution, welche
        OpenXR-Runtime aktiv ist). Die stehen hier oben drueber — und zwar
        genau die, die auch die Oberflaeche anzeigt. Persoenliche Daten sind
        nicht dabei; der Home-Pfad taucht allerdings in Pfadangaben auf, was
        im Dialogtext auch so gesagt wird.
        """
        default_name = os.path.join(
            os.path.expanduser("~"),
            f"yakuda-connect-diagnose-{datetime.datetime.now():%Y%m%d_%H%M}.txt")
        path, _filter = QFileDialog.getSaveFileName(
            self, tr("diag_save_title"), default_name, "Text (*.txt)")
        if not path:
            return          # Abbruch im Dateidialog ist kein Fehler

        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self._build_diagnostics_report())
        except OSError as exc:
            log.warning("Diagnosebericht konnte nicht geschrieben werden: %s", exc)
            QMessageBox.warning(self, tr("diag_title"),
                                tr("diag_save_failed").format(err=exc))
            return

        log.info("Diagnosebericht gespeichert: %s", path)
        QMessageBox.information(self, tr("diag_title"),
                                tr("diag_saved").format(path=path))

    def _build_diagnostics_report(self):
        """Kopfzeilen mit Systemangaben + das Ende der Logdatei."""
        lines = [
            "yakuda-connect diagnostics",
            "=" * 60,
            f"App version   : {self.APP_VERSION}",
            f"Date          : {datetime.datetime.now().isoformat(timespec='seconds')}",
            f"Python        : {sys.version.split()[0]}",
            f"Platform      : {platform.platform()}",
        ]
        # Jede Angabe einzeln absichern: faellt eine aus (WiVRn nicht
        # installiert, kein Headset), soll der Bericht trotzdem entstehen —
        # er wird ja gerade dann gebraucht, wenn etwas kaputt ist.
        try:
            lines.append(f"Desktop       : {os.environ.get('XDG_CURRENT_DESKTOP', '?')} "
                         f"({os.environ.get('XDG_SESSION_TYPE', '?')})")
        except Exception as exc:
            log.debug("_build_diagnostics_report: Desktop — %s", exc)
        try:
            lines.append(f"WiVRn server  : {venv.wivrn_server_binary() or '-'}")
            lines.append(f"OpenXR runtime: {venv.primary_active_runtime()}")
        except Exception as exc:
            log.debug("_build_diagnostics_report: VR — %s", exc)
        try:
            lines.append(f"Firewall      : {fw.detect().get('kind') or '-'}")
        except Exception as exc:
            log.debug("_build_diagnostics_report: Firewall — %s", exc)

        lines += ["", "-" * 60, "log tail:", "-" * 60, read_log_tail()]
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    #  Advanced Mode (Schalter unten links in der Seitenleiste)
    # ------------------------------------------------------------------ #
    def on_advanced_mode_toggled(self, checked):
        """
        Schaltet die technischen Zusatzangaben ein oder aus.

        Es aendert sich NUR die Sichtbarkeit dieser Kaesten — keine Funktion
        der App verhaelt sich im Advanced Mode anders. Der Zustand wird in
        der Config gemerkt, damit er den Neustart ueberlebt.
        """
        adv.set_enabled(bool(checked))
        self._refresh_advanced_boxes()
        if not update_json(paths.config_file("config.json"),
                           {"advanced_mode": bool(checked)}):
            log.warning("Advanced Mode konnte nicht gespeichert werden.")

    def _refresh_advanced_boxes(self):
        """Alle Technik-Kaesten an den aktuellen Zustand angleichen."""
        try:
            from ui.advanced_panel import refresh_all
            refresh_all()
        except Exception as exc:
            # Die Kaesten sind Beiwerk. Klemmt hier etwas, darf das die App
            # nicht am Starten hindern.
            log.warning("Advanced-Kaesten konnten nicht aktualisiert werden: %s", exc)

    # ------------------------------------------------------------------ #
    #  Automatisches Erst-Backup beim Start (siehe backup_manager.py)
    # ------------------------------------------------------------------ #
    def _start_auto_backup_check(self):
        """
        Startet den stillen Auto-Check im Hintergrund-Thread.

        Er macht zweierlei (siehe core/vr_autotune.py): das automatische
        Erst-Backup wie bisher — und danach EINMALIG die Umstellung der
        OpenVR-Kompatibilitaet auf xrizer, sofern erkennbar ist, dass auf
        diesem Rechner schon einmal VR lief.

        Aufgerufen wird das an genau zwei Stellen, ohne Timer:
          * kurz nach dem Start der App,
          * nachdem der WiVRn-Server beendet wurde.
        Waehrend der Server laeuft, wird nichts geschrieben — WiVRn liest den
        Pfad nur beim Hochfahren.
        """
        worker = getattr(self, "_auto_backup_worker", None)
        if worker is not None and worker.isRunning():
            return      # laeuft schon — nicht zweimal parallel

        class _AutoBackupWorker(QThread):
            done = QtSignal(dict)

            def run(self):
                try:
                    result = autotune.run_auto_setup()
                except Exception as e:
                    log.warning(f"[Backup] Auto-Check fehlgeschlagen: {e}")
                    result = {}
                self.done.emit(result or {})

        self._auto_backup_worker = _AutoBackupWorker()
        self._auto_backup_worker.done.connect(self._on_auto_backup_done)
        self._auto_backup_worker.start()

    def _on_auto_backup_done(self, result):
        if result.get("backup_created"):
            log.info("[Backup] Automatisches Erst-Backup der VR-Umgebung wurde angelegt.")
        if result.get("skipped"):
            log.debug("[Autotune] xrizer-Umstellung uebersprungen: %s", result["skipped"])
        if result.get("switched"):
            # Die Auswahl im Streaming-Tab zeigt sonst noch den alten Wert.
            self.refresh_openvr_ui()
            QMessageBox.information(
                self, tr("autotune_xrizer_title"),
                tr("autotune_xrizer_text").format(path=result.get("path", ""),
                                                  previous=result.get("previous", "")))

    def refresh_openvr_ui(self):
        """Liest die OpenVR-Auswahl im Streaming-Tab neu aus WiVRns config.json.
        Wird von der Runtime-Umschaltung (ui/vr_runtime_widget.py) und von der
        xrizer-Automatik aufgerufen."""
        tab = getattr(self, "streaming_settings", None)
        if tab is not None and hasattr(tab, "refresh_openvr_from_system"):
            tab.refresh_openvr_from_system()

    # ------------------------------------------------------------------ #
    #  Steam-Schutz: defekte System-OpenXR-Manifeste erkennen
    # ------------------------------------------------------------------ #
    def _start_openxr_health_check(self):
        """Prueft im Hintergrund, ob ein Manifest in /usr/share/openxr/1 auf
        eine fehlende oder falsch-bittige Bibliothek zeigt. Genau das bringt
        Steams pressure-vessel beim Start zum Absturz."""
        class _OxrHealthWorker(QThread):
            done = QtSignal(list)

            def run(self):
                try:
                    broken = oxr.broken_runtime_manifests()
                except Exception as e:
                    log.warning(f"[OpenXR] Manifest-Check fehlgeschlagen: {e}")
                    broken = []
                self.done.emit(broken)

        self._oxr_health_worker = _OxrHealthWorker()
        self._oxr_health_worker.done.connect(self._on_openxr_health_done)
        self._oxr_health_worker.start()

    def _on_openxr_health_done(self, broken):
        if not broken or self._oxr_health_asked:
            return
        self._oxr_health_asked = True
        self.offer_manifest_repair(broken)

    def offer_manifest_repair(self, broken=None):
        """Zeigt die gefundenen defekten Manifeste und bietet die Reparatur an."""
        if broken is None:
            try:
                broken = oxr.broken_runtime_manifests()
            except Exception:
                broken = []
        if not broken:
            return False

        lines = []
        for e in broken:
            detail = {
                "missing_lib": tr("oxr_doc_missing"),
                "arch_mismatch": tr("oxr_doc_arch").format(
                    expected=e["expected_bits"], found=e["found_bits"] or "?"),
                "no_path": tr("oxr_doc_nopath"),
                "unreadable": tr("oxr_doc_unreadable"),
            }.get(e["state"], e["state"])
            lines.append(f"• {e['path']}\n   {e['library_path'] or '—'}\n   {detail}")

        reply = QMessageBox.question(
            self, tr("oxr_doc_title"),
            tr("oxr_doc_text").format(items="\n\n".join(lines)),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return False

        ok, code, detail = oxr.repair_runtime_manifests(broken)
        if ok and code == "ok":
            QMessageBox.information(self, tr("oxr_doc_title"),
                                    tr("oxr_doc_done").format(details=detail))
        elif code == "nothing_to_do":
            QMessageBox.information(self, tr("oxr_doc_title"), tr("oxr_doc_none"))
        elif code == "cancelled":
            QMessageBox.information(self, tr("oxr_doc_title"), tr("openxr_fix_cancelled"))
        else:
            QMessageBox.critical(self, tr("oxr_doc_title"),
                                 f"{tr('oxr_doc_error')}\n{detail}")
        self.refresh_openxr_status()
        self.fill_openxr_fields()
        return ok

    # ------------------------------------------------------------------ #
    #  OpenXR-Runtime (Steam-Fix): automatischer Fix + manueller Bereich
    # ------------------------------------------------------------------ #
    def refresh_openxr_status(self):
        """Zeigt an, ob die active_runtime.json ok / kaputt / nicht vorhanden ist."""
        try:
            state, _detail = oxr.current_status()
            which = oxr.active_runtime_name()
        except Exception:
            state, which = "missing", "none"
        if state == "ok" and which == "steamvr":
            # Gueltig, aber eben nicht WiVRn. Ohne diesen Fall stand hier
            # "bereit fuer Steam" — richtig, aber nicht die Information, die
            # jemand sucht, der gerade auf SteamVR umgestellt hat.
            self.ui.lbl_openxr_status.setText(tr("openxr_status_steamvr"))
            self.ui.lbl_openxr_status.setStyleSheet(
                "color: #81a1c1; font-size: 11px; font-weight: bold;")
        elif state == "ok":
            self.ui.lbl_openxr_status.setText(tr("openxr_status_ok"))
            self.ui.lbl_openxr_status.setStyleSheet(
                "color: #a3be8c; font-size: 11px; font-weight: bold;")
        elif state == "broken":
            self.ui.lbl_openxr_status.setText(tr("openxr_status_broken"))
            self.ui.lbl_openxr_status.setStyleSheet(
                "color: #bf616a; font-size: 11px; font-weight: bold;")
        else:
            self.ui.lbl_openxr_status.setText(tr("openxr_status_missing"))
            self.ui.lbl_openxr_status.setStyleSheet(
                "color: #ebcb8b; font-size: 11px; font-weight: bold;")

    def apply_openxr_fix_clicked(self):
        """Schreibt die korrekte active_runtime.json (mit automatischem Backup).
        Scheitert der normale Schreibzugriff (Rechteproblem), wird der Fix per
        pkexec mit Root-Passwortabfrage wiederholt."""
        # Der Fix schreibt IMMER WiVRn als aktive Runtime. Steht dort gerade
        # bewusst SteamVR, wuerde ein Klick hier die Auswahl stillschweigend
        # rueckgaengig machen — deshalb vorher fragen.
        if oxr.active_runtime_name() == "steamvr":
            reply = QMessageBox.question(
                self, tr("openxr_group"), tr("openxr_fix_steamvr_ask"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        # Zuerst die System-Manifeste pruefen: solange dort ein Manifest auf
        # eine fehlende/falsch-bittige .so zeigt, startet Steam gar nicht erst.
        try:
            broken = oxr.broken_runtime_manifests()
        except Exception:
            broken = []
        if broken:
            self.offer_manifest_repair(broken)

        ok, code, detail = oxr.apply_openxr_fix()

        # Rechteproblem? -> Root-Fallback anbieten (pkexec-Passwortdialog)
        if not ok and code == "write_failed":
            reply = QMessageBox.question(
                self, tr("openxr_group"), tr("openxr_fix_root_ask"),
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                ok, code, detail = oxr.apply_openxr_fix_elevated()

        if ok:
            msg = tr("openxr_fix_done").format(path=venv.primary_active_runtime())
            if detail:
                msg += "\n\n" + tr("openxr_fix_backup").format(backup=detail)
            QMessageBox.information(self, tr("openxr_group"), msg)
        elif code == "libs_not_found":
            QMessageBox.warning(self, tr("openxr_group"), tr("openxr_fix_no_libs"))
        elif code == "not_elf":
            QMessageBox.warning(self, tr("openxr_group"),
                                tr("openxr_fix_not_elf").format(path=detail))
        elif code == "cancelled":
            QMessageBox.information(self, tr("openxr_group"), tr("openxr_fix_cancelled"))
        else:
            QMessageBox.critical(self, tr("openxr_group"),
                                 f"{tr('openxr_fix_error')}\n{detail}")
        self.refresh_openxr_status()
        self.fill_openxr_fields()
        # Die Runtime-Anzeige unter VR & OpenXR steht jetzt auf WiVRn.
        if hasattr(self.ui, "vr_runtime_widget"):
            self.ui.vr_runtime_widget.refresh()

    def toggle_openxr_manual(self):
        """Klappt den manuellen Fix-Bereich ein/aus."""
        visible = not self.ui.openxr_manual_widget.isVisible()
        self.ui.openxr_manual_widget.setVisible(visible)
        self.ui.btn_openxr_manual_toggle.setText(
            tr("openxr_manual_hide") if visible else tr("openxr_manual_show"))

    # ------------------------------------------------------------------ #
    #  WayVR Design (Settings): cubee-cb-Design installieren / zurücksetzen
    #  Logik in core/overlay_manager.py — Design kommt 1:1 aus dem Repo,
    #  ohne jede Veränderung. Hier nur UI-Zustand & Dialoge.
    # ------------------------------------------------------------------ #
    def start_wayvr_design_install(self):
        """Lädt cubees dotfiles/wayvr von GitHub und kopiert sie 1:1 nach ~/.config/wayvr."""
        if self._wayvr_worker and self._wayvr_worker.isRunning():
            return
        self.ui.btn_wayvr_install.setEnabled(False)
        self.ui.btn_wayvr_reset.setEnabled(False)
        self.ui.lbl_wayvr_status.setText(tr("wayvr_status_download"))
        self._wayvr_worker = ovl.DesignInstallWorker()
        self._wayvr_worker.status_signal.connect(self._on_wayvr_status)
        self._wayvr_worker.finished_signal.connect(self._on_wayvr_install_done)
        self._wayvr_worker.start()

    def _on_wayvr_status(self, key):
        """Fortschrittstext aus dem Worker (backup/download/install/patch/...)."""
        self.ui.lbl_wayvr_status.setText(tr(f"wayvr_status_{key}"))

    def _on_wayvr_install_done(self, ok, info):
        self.ui.btn_wayvr_install.setEnabled(True)
        self.ui.btn_wayvr_reset.setEnabled(True)
        if ok:
            self.ui.lbl_wayvr_status.setText(tr("wayvr_installed_hint"))
            QMessageBox.information(self, tr("success"), tr("wayvr_install_ok"))
        else:
            self.ui.lbl_wayvr_status.setText("")
            QMessageBox.warning(self, tr("error"), tr("wayvr_install_fail").format(err=info))

    def reset_wayvr_design(self):
        """Löscht ~/.config/wayvr komplett (Backup vorher) — Werkseinstellung."""
        answer = QMessageBox.question(
            self, tr("wayvr_reset_confirm_title"), tr("wayvr_reset_confirm_text"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        ok, info = ovl.reset_wayvr_to_default()
        if ok:
            self.ui.lbl_wayvr_status.setText("")
            msg = tr("wayvr_reset_ok")
            if info:
                msg += "\n\n" + tr("wayvr_reset_backup_at").format(path=info)
            QMessageBox.information(self, tr("success"), msg)
        else:
            QMessageBox.warning(self, tr("error"), tr("wayvr_reset_fail").format(err=info))

    def init_logic_connections(self):
        """Verknüpft die UI-Komponenten aus ui_main.py mit den Logik-Funktionen."""
        # Navigation
        self.ui.sidebar.currentRowChanged.connect(self.on_tab_changed)

        # Games-Tab
        self.ui.btn_games_scan.clicked.connect(self.start_games_scan)
        self.ui.btn_games_info.clicked.connect(self.show_games_info)
        self.ui.btn_games_db_update.clicked.connect(self.start_games_db_update)
        self._refresh_games_db_version()
        # Im Hintergrund prüfen, ob eine neuere Spiele-DB (games.json) vorliegt.
        QTimer.singleShot(1500, self._check_games_db_update)

        # Installation / Update
        self.ui.btn_install.clicked.connect(self.start_package_installation)
        self.ui.btn_update.clicked.connect(self.start_system_update)
        self._populate_install_method_combo()
        self.ui.combo_install_method.currentIndexChanged.connect(self._on_install_method_changed)
        # Ubuntu/Debian: Update-Knopf ausblenden (kein Paket in den Repos)
        QTimer.singleShot(400, self._apply_distro_ui_rules)
        self.ui.btn_vr_backup.clicked.connect(self.trigger_vr_backup)
        self.ui.btn_vr_restore.clicked.connect(self.trigger_vr_restore)
        self.ui.btn_vr_restore_github.clicked.connect(self.trigger_vr_restore_github)
        self.ui.btn_openxr_copy_path.clicked.connect(self.copy_openxr_path)
        self.ui.btn_openxr_copy_content.clicked.connect(self.copy_openxr_content)
        # OpenXR: automatischer Fix + Ein-/Ausklappen des manuellen Bereichs
        self.ui.btn_openxr_fix.clicked.connect(self.apply_openxr_fix_clicked)
        self.ui.btn_vrcvideocacher.clicked.connect(self.toggle_vrcvideocacher)
        # Beschriftung beim Start an den tatsaechlichen Zustand anpassen
        self.refresh_vrcvideocacher_button()
        self.ui.btn_openxr_manual_toggle.clicked.connect(self.toggle_openxr_manual)
        # Community & Updates (Settings, ganz oben)
        self.ui.btn_community_check.clicked.connect(self.manual_check_app_update)
        self.ui.btn_community_discord.clicked.connect(self.open_discord_link)
        # Auto-Connect per USB (Dashboard-Tab). Der Zustand kommt aus WiVRns
        # eigener Einstellungsdatei, nicht aus unserer Config.
        self.ui.check_usb_autoconnect.clicked.connect(self.on_usb_autoconnect_toggled)
        self.load_usb_autoconnect()
        # USB-Erkennung: einmal beim Start pruefen. Der Dauerlauf startet
        # erst, wenn der Dashboard-Tab sichtbar ist. Einen eigenen Knopf gibt
        # es nicht mehr — "Liste aktualisieren" bei den gekoppelten Headsets
        # prueft beides.
        self._render_usb_state(None)
        QTimer.singleShot(800, self.check_usb_headset)
        self.ui.btn_log_open.clicked.connect(self.open_log_file)
        self.ui.btn_log_copy.clicked.connect(self.copy_log_to_clipboard)
        self.ui.btn_log_save.clicked.connect(self.save_diagnostics_file)
        self.ui.toggle_advanced.toggled.connect(self.on_advanced_mode_toggled)
        self.ui.btn_community_donate.clicked.connect(self.open_kofi_link)
        # WayVR Design (Settings): cubee-cb-Design installieren / Config löschen
        self._wayvr_worker = None
        self.ui.btn_wayvr_install.clicked.connect(self.start_wayvr_design_install)
        self.ui.btn_wayvr_reset.clicked.connect(self.reset_wayvr_design)
        if ovl.is_design_installed():
            self.ui.lbl_wayvr_status.setText(tr("wayvr_installed_hint"))
        self.fill_openxr_fields()
        self.refresh_openxr_status()

        # Custom-Kill-Befehle (Settings, ganz unten):
        # Add/Save verdrahten und gespeicherte Einträge laden.
        self.ui.btn_killcmd_add.clicked.connect(lambda: self._killcmd_add_row("", ""))
        self.ui.btn_killcmd_save.clicked.connect(self._killcmd_save)
        self._killcmd_load_from_config()

        # Mikrofon / Audio-Quelle (Settings): Standard-Source setzen/zurücksetzen.
        # Beim Start einmal die Quellen einlesen und den aktuellen Zustand zeigen.
        self.ui.btn_mic_refresh.clicked.connect(self.refresh_mic_sources)
        self.ui.btn_mic_set.clicked.connect(self.apply_mic_source)
        self.ui.btn_mic_reset.clicked.connect(self.reset_mic_source)
        self.refresh_mic_sources()

        # Dashboard Steuerung — Schiebeschalter statt Start/Stop-Buttons
        self.ui.toggle_server.toggled.connect(self.on_server_toggled)
        self.ui.btn_server_check.clicked.connect(self.manual_server_check)
        self.ui.btn_port_status.clicked.connect(self.open_port_9757_firewall)
        # Sprung ins Einstellungen-Unterregister "VR & OpenXR"
        self.ui.btn_openxr_shortcut.clicked.connect(self.open_vr_settings)
        self.ui.combo_language.currentIndexChanged.connect(self.on_language_changed)
        # Selbst-Update: kleiner Pfeil neben der App-Version
        self.ui.btn_app_update.clicked.connect(self.start_app_self_update)

        # APK Installation
        self.ui.btn_apk_install.clicked.connect(self.start_apk_install)
        self.ui.btn_apk_cancel.clicked.connect(self.cancel_apk_install)
        self._apk_worker = None

        # Autosave Trigger
        self.ui.chk_steamvr_tracker.clicked.connect(self.trigger_auto_save)
        self.ui.chk_pairing.toggled.connect(self.toggle_pairing_mode)

        # Autostart Zeilen-Generierung
        self.ui.num_apps.returnPressed.connect(self.update_autostart_fields)
        self.ui.num_apps.editingFinished.connect(self.update_autostart_fields)
        # Manueller Reset des Einweg-Autostart-Timers
        self.ui.btn_autostart_reset.clicked.connect(self.reset_autostart_readiness)
        # Besen-Button: laufende Autostart-Apps sofort beenden
        self.ui.btn_autostart_kill.clicked.connect(self.kill_autostart_apps)

        # Headset Management
        # "Liste aktualisieren" prueft beides: gekoppelte Headsets UND das
        # USB-Kabel — der frueher eigene USB-Knopf ist damit ueberfluessig.
        self.ui.btn_refresh_list.clicked.connect(self.refresh_headset_list)
        self.ui.btn_refresh_list.clicked.connect(self.check_usb_headset)
        self.ui.btn_remove_headset.clicked.connect(self.remove_selected_headset)
        self.ui.btn_disconnect_headset.clicked.connect(self.disconnect_current_headset)

        self.autostart_rows = []
        self.update_autostart_fields()

        # Streaming Tab dynamisch einbetten
        stream_layout = QVBoxLayout(self.ui.tab_streaming)
        stream_layout.setContentsMargins(0, 0, 0, 0)
        self.streaming_settings = StreamingTab(self)
        stream_layout.addWidget(self.streaming_settings)

        # Tools Tab — Buttons verknüpfen (Dispatcher: Installieren/Aktualisieren/Löschen)
        for key, card in self.ui.tool_cards.items():
            card["btn_install"].clicked.connect(
                lambda checked=False, k=key: self.on_tool_action(k)
            )
            self._populate_method_combo(card)
        self.ui.btn_tools_check.clicked.connect(self.start_tools_update_check)

        # Settings Tab
        # HINWEIS: btn_vrchat_symlink wird NICHT mehr hier verbunden — der
        # VRChat Picture Folder Fix lebt jetzt als dynamischer Button im
        # ausgeklappten VRChat-Bereich des Games-Tabs (siehe _build_game_detail).

    def get_wivrn_version(self):
        # Immer nativ: Version direkt aus der wivrn-server-Binary lesen
        try:
            res = subprocess.run(["wivrn-server", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=proc.DEFAULT_TIMEOUT)
            if res.returncode == 0:
                version_match = re.search(r'[\d\.]+', res.stdout)
                return version_match.group(0) if version_match else "Unbekannt"
        except Exception as exc:
            log.debug("get_wivrn_version: ignoriert — %s", exc)
        return tr("tools_not_installed")

    def _runtime_installed(self):
        """Ist die WiVRn-Runtime für die aktuell gewählte Methode installiert?"""
        method = self._install_method()
        if not method:
            return False
        if method in ("dnf", "native"):
            return shutil.which("wivrn-server") is not None
        # yay/paru: WiVRn/Monado-Pakete vorhanden?
        if not shutil.which(method):
            return False
        for pkg in INSTALL_PACKAGES.get("WiVRn / Monado", []):
            # Listenform statt shell=True: der Paketname wandert nicht mehr
            # durch eine Shell, die ihn interpretieren koennte.
            res = proc.run([method, "-Q", pkg],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=proc.DEFAULT_TIMEOUT)
            if res.returncode != 0:
                return False
        return True

    def are_critical_packages_missing(self):
        return not self._runtime_installed()

    def on_tab_changed(self, index):
        if index != 0 and self.are_critical_packages_missing():
            self.ui.sidebar.blockSignals(True)
            self.ui.sidebar.setCurrentRow(0)
            self.ui.pages.setCurrentIndex(0)
            self.ui.sidebar.blockSignals(False)
            QMessageBox.critical(self, tr("msg_locked_title"), tr("msg_locked_text"))
            return
        self.ui.pages.setCurrentIndex(index)
        # Installations-Tab: Status frisch pruefen. Was hier steht, kann sich
        # ausserhalb der App geaendert haben (dnf/pacman im Terminal, ein
        # System-Update, ein selbst gebautes xrizer). Bisher wurde nur beim
        # Programmstart geprueft — wer nach einer Installation zurueckkam, sah
        # weiter den alten Stand.
        if index == 0:
            self.check_system_packages()
        # USB-Ampel nur im Dashboard mitlaufen lassen (spart adb-Aufrufe).
        if index == 1:
            self.check_usb_headset()
            self.usb_poll_timer.start()
        else:
            self.usb_poll_timer.stop()
        if index == 1: self.refresh_headset_list()
        # Die OpenVR-Auswahl kann sich ausserhalb dieses Tabs geaendert haben
        # (Runtime-Umschaltung, xrizer-Automatik, WiVRn-Dashboard).
        if index == 2: self.refresh_openvr_ui()
        if index == 3: self.check_tools_status()
        if index == 4: self.on_games_tab_opened()
        # Runtime/Prioritaet koennen sich ausserhalb der App geaendert haben
        if index == 5 and hasattr(self.ui, "vr_runtime_widget"):
            self.ui.vr_runtime_widget.refresh()

    # ------------------------------------------------------------------ #
    #  Games-Tab
    # ------------------------------------------------------------------ #
    def fill_openxr_fields(self):
        """Füllt das Pfad-Feld und das Inhalt-Feld für die manuelle OpenXR-Reparatur."""
        try:
            self.ui.txt_openxr_path.setText(venv.primary_active_runtime())
            openxr_so, monado_so = venv.find_wivrn_libs()
            if openxr_so:
                runtime = {"file_format_version": "1.0.0",
                           "runtime": {"name": "Monado", "library_path": openxr_so}}
                if monado_so:
                    runtime["runtime"]["MND_libmonado_path"] = monado_so
            else:
                # Bibliotheken nicht gefunden -> Vorlage mit den ueblichen Standardpfaden
                runtime = {"file_format_version": "1.0.0",
                           "runtime": {"name": "Monado",
                                       "library_path": "/usr/lib/wivrn/libopenxr_wivrn.so",
                                       "MND_libmonado_path": "/usr/lib/wivrn/libmonado_wivrn.so"}}
            self.ui.txt_openxr_content.setPlainText(json.dumps(runtime, indent=4))
        except Exception as exc:
            log.debug("fill_openxr_fields: ignoriert — %s", exc)

    def copy_openxr_path(self):
        QApplication.clipboard().setText(self.ui.txt_openxr_path.text())
        self.ui.btn_openxr_copy_path.setText(tr("openxr_copied"))
        QTimer.singleShot(1500, lambda: self.ui.btn_openxr_copy_path.setText(tr("openxr_copy_btn")))

    def copy_openxr_content(self):
        QApplication.clipboard().setText(self.ui.txt_openxr_content.toPlainText())
        self.ui.btn_openxr_copy_content.setText(tr("openxr_copied"))
        QTimer.singleShot(1500, lambda: self.ui.btn_openxr_copy_content.setText(tr("openxr_copy_btn")))

    def start_apk_install(self):
        """Startet Download und Installation der WiVRn APK."""
        if self._apk_worker and self._apk_worker.isRunning():
            return

        # Prüfen ob adb verfügbar ist
        if not shutil.which("adb"):
            self.ui.lbl_apk_status.setText(
                "⚠ android-tools nicht installiert — gehe zu Tools und installiere es zuerst.")
            self.ui.lbl_apk_status.setStyleSheet("color: #ebcb8b; font-size: 11px; font-weight: bold;")
            return

        self.ui.btn_apk_install.setEnabled(False)
        self.ui.btn_apk_cancel.setVisible(True)
        self.ui.lbl_apk_status.setText(tr("apk_starting"))
        self.ui.lbl_apk_status.setStyleSheet("color: #88c0d0; font-size: 11px;")

        self._apk_worker = ApkWorker()
        self._apk_worker.status_signal.connect(self.ui.lbl_apk_status.setText)
        self._apk_worker.finished_signal.connect(self._on_apk_finished)
        self._apk_worker.start()

    def cancel_apk_install(self):
        if self._apk_worker:
            self._apk_worker.cancel()

    def _on_apk_finished(self, success):
        self.ui.btn_apk_install.setEnabled(True)
        self.ui.btn_apk_cancel.setVisible(False)
        if success:
            self.ui.lbl_apk_status.setStyleSheet(
                "color: #a3be8c; font-size: 11px; font-weight: bold;")
        else:
            self.ui.lbl_apk_status.setStyleSheet(
                "color: #bf616a; font-size: 11px;")
        self._apk_worker = None

    def on_language_changed(self, index):
        lang = "en" if index == 0 else "de"
        set_language(lang)
        self.apply_translations()
        data = load_saved_settings()
        data["language"] = lang
        # update_json statt json.dump: liest, aendert nur die Sprache und
        # schreibt atomar zurueck. Vorher wurde die komplette Datei neu
        # geschrieben — ein Absturz mitten im Sprachwechsel haette alle
        # Einstellungen gekostet.
        if not update_json(paths.config_file("config.json"), {"language": lang}):
            log.warning("Sprache konnte nicht gespeichert werden.")

    def apply_translations(self):
        """Aktualisiert alle UI-Texte nach Sprachwechsel."""
        lang = get_language()
        all_tools = {t["key"]: t for t in TOOLS_APPS + TOOLS_OSC}

        # 1) Alle STATISCHEN Texte zentral neu setzen (Sidebar, alle Tabs).
        self.ui.retranslate_ui()

        # 2) Streaming-Tab (eigenes Widget) ebenfalls neu übersetzen.
        if hasattr(self, 'streaming_settings') and hasattr(self.streaming_settings, 'retranslate'):
            self.streaming_settings.retranslate()

        # 3) Info-Text (Willkommen / Welcome)
        self._set_welcome_text()

        # App-Versions-Label + Update-Pfeil-Tooltip an die Sprache anpassen
        self._refresh_app_version_label()

        # Status-Label der OpenXR-Box neu setzen
        self.refresh_openxr_status()

        # USB-Ampel + Raten-Hinweis stehen in der alten Sprache da — der
        # zuletzt erkannte Zustand wird einfach neu gezeichnet (kein neuer
        # Scan noetig).
        self._render_usb_state(self._usb_last_info)

        # --- Ab hier nur noch DYNAMISCHE Texte, die vom aktuellen Zustand abhängen ---

        # Server status text (nur wenn inaktiv — laufender Status wird dynamisch gesetzt)
        current_status = self.ui.lbl_status_text.text()
        if any(x in current_status for x in ["Ausgeschaltet", "Inactive", "Inaktiv"]):
            self.ui.lbl_status_text.setText(tr("dashboard_inactive"))

        # Prog labels in Installation tab
        if hasattr(self, 'prog_labels'):
            for prog_name, lbl in self.prog_labels.items():
                text = lbl.text()
                if "Update" in text:
                    lbl.setText(tr("pkg_installed") + " " + tr("pkg_update_suffix"))
                elif "✔" in text:
                    lbl.setText(tr("pkg_installed"))
                elif "⚠" in text:
                    lbl.setText(tr("pkg_incomplete"))

        # Tool-Karten: Beschreibung neu setzen, Status/Buttons aus dem Cache rendern
        for key, card in self.ui.tool_cards.items():
            tool = all_tools.get(key, {})
            if "lbl_desc" in card:
                desc = tool.get("desc_eng", tool.get("desc", "")) if lang == "en" else tool.get("desc", "")
                card["lbl_desc"].setText(desc)
            if card.get("lbl_note") is not None:
                note = tool.get("note_eng", tool.get("note", "")) if lang == "en" else tool.get("note", "")
                card["lbl_note"].setText(note)
        self.check_tools_status()

    def _get_pictures_dir(self):
        """Ermittelt den lokalisierten Bilder-Ordner.
        Gibt z. B. ~/Bilder auf deutschen, ~/Pictures auf englischen Systemen zurück."""
        import pathlib
        home = pathlib.Path.home()

        # 1. Bevorzugt über xdg-user-dir den korrekten, lokalisierten Ordner holen
        try:
            res = subprocess.run(
                ["xdg-user-dir", "PICTURES"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=proc.DEFAULT_TIMEOUT)
            if res.returncode == 0:
                p = res.stdout.strip()
                # xdg gibt das Home zurück, wenn nichts konfiguriert ist → das ignorieren
                if p and pathlib.Path(p) != home:
                    return pathlib.Path(p)
        except Exception as exc:
            log.debug("_get_pictures_dir: ignoriert — %s", exc)

        # 2. Fallback: bekannte Ordnernamen durchprobieren (existierender gewinnt)
        for name in ("Bilder", "Pictures"):
            if (home / name).is_dir():
                return home / name

        # 3. Letzter Fallback
        return home / "Bilder"

    def create_vrchat_symlink(self):
        """Verlinkt den VRChat Proton-Bilderordner in den lokalen Bilder-Ordner.
        Alles, was VRChat im Proton-Ordner speichert, erscheint dadurch automatisch
        auch im normalen Linux-Bilderordner (z. B. ~/Bilder/VRChat)."""
        import pathlib

        # Prefix nativ ODER Flatpak-Steam automatisch finden
        prefix = pathlib.Path(venv.vrchat_proton_prefix())
        vrchat_proton_path = prefix / "Pictures" / "VRChat"

        pictures_dir = self._get_pictures_dir()
        linux_pictures = pictures_dir / "VRChat"

        # Prüfen, ob das VRChat Proton-Prefix überhaupt existiert
        # (sonst wurde VRChat nie über Steam/Proton installiert/gestartet)
        if not prefix.exists():
            self.ui.lbl_vrchat_status.setText(
                "⚠ VRChat Proton-Prefix nicht gefunden.\n"
                "Starte VRChat mindestens einmal über Steam, bevor du den Symlink erstellst."
            )
            self.ui.lbl_vrchat_status.setStyleSheet("color: #ebcb8b; font-size: 11px;")
            return

        # VRChat-Ordner im Proton-Prefix anlegen, falls noch nicht vorhanden
        try:
            vrchat_proton_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.ui.lbl_vrchat_status.setText(tr("vrchat_err_proton").format(err=e))
            self.ui.lbl_vrchat_status.setStyleSheet("color: #bf616a; font-size: 11px;")
            return

        # Schon ein Symlink?
        if linux_pictures.is_symlink():
            ziel = pathlib.Path(os.path.realpath(linux_pictures))
            if ziel == vrchat_proton_path.resolve():
                # Zeigt bereits korrekt auf den Proton-Ordner → fertig
                self.ui.lbl_vrchat_status.setText(
                    f"✔ Symlink existiert bereits:\n{linux_pictures} → {vrchat_proton_path}"
                )
                self.ui.lbl_vrchat_status.setStyleSheet("color: #a3be8c; font-size: 11px;")
                self.ui.btn_vrchat_symlink.setText("✔ Done")
                self.ui.btn_vrchat_symlink.setEnabled(False)
                return
            # Falscher/alter Symlink → entfernen und neu setzen
            try:
                linux_pictures.unlink()
            except Exception as e:
                self.ui.lbl_vrchat_status.setText(
                    f"Fehler: alter Symlink ließ sich nicht entfernen: {e}")
                self.ui.lbl_vrchat_status.setStyleSheet("color: #bf616a; font-size: 11px;")
                return

        # Echter Ordner vorhanden → unter eindeutigem Namen als Backup sichern,
        # damit vorhandene Fotos nicht verloren gehen.
        if linux_pictures.exists() and not linux_pictures.is_symlink():
            backup = linux_pictures.with_name("VRChat_backup")
            i = 1
            while backup.exists():
                backup = linux_pictures.with_name(f"VRChat_backup_{i}")
                i += 1
            try:
                linux_pictures.rename(backup)
            except Exception as e:
                self.ui.lbl_vrchat_status.setText(
                    f"Fehler beim Sichern des bestehenden Ordners: {e}")
                self.ui.lbl_vrchat_status.setStyleSheet("color: #bf616a; font-size: 11px;")
                return

        try:
            linux_pictures.parent.mkdir(parents=True, exist_ok=True)
            linux_pictures.symlink_to(vrchat_proton_path)
            self.ui.lbl_vrchat_status.setText(
                f"✔ Symlink erfolgreich erstellt!\n{linux_pictures} → {vrchat_proton_path}\n"
                "Neue VRChat-Fotos erscheinen jetzt automatisch hier."
            )
            self.ui.lbl_vrchat_status.setStyleSheet("color: #a3be8c; font-size: 11px;")
            self.ui.btn_vrchat_symlink.setText("✔ Done")
            self.ui.btn_vrchat_symlink.setEnabled(False)
        except Exception as e:
            self.ui.lbl_vrchat_status.setText(tr("err_generic").format(err=e))
            self.ui.lbl_vrchat_status.setStyleSheet("color: #bf616a; font-size: 11px;")

    def toggle_vrcvideocacher(self):
        """Startet bzw. beendet VRCVideoCacher ueber den Dashboard-Knopf.

        Bewusst ein manueller Knopf statt eines Autostarts ueber VRChats
        Startparameter: dort war es unzuverlaessig. Hier sieht der Nutzer,
        ob es laeuft, und kann es jederzeit wieder beenden.
        """
        import vrcvideocacher_install as vci

        if not vci.is_installed():
            QMessageBox.information(self, tr("dashboard_vci_title"),
                                    tr("dashboard_vci_not_installed"))
            return

        if vci.is_running():
            vci.stop()
            QMessageBox.information(self, tr("dashboard_vci_title"),
                                    tr("dashboard_vci_stopped"))
        else:
            ok, msg = vci.start()
            if ok:
                QMessageBox.information(self, tr("dashboard_vci_title"),
                                        tr("dashboard_vci_started"))
            else:
                QMessageBox.warning(self, tr("dashboard_vci_title"),
                                    tr("dashboard_vci_failed").format(err=msg))
        self.refresh_vrcvideocacher_button()

    def refresh_vrcvideocacher_button(self):
        """Beschriftung des Dashboard-Knopfs an den Zustand anpassen."""
        btn = getattr(self.ui, "btn_vrcvideocacher", None)
        if btn is None:
            return
        import vrcvideocacher_install as vci
        if not vci.is_installed():
            btn.setText(tr("dashboard_vci_btn"))
        elif vci.is_running():
            btn.setText(tr("dashboard_vci_btn_stop"))
        else:
            btn.setText(tr("dashboard_vci_btn_start"))

    def trigger_vr_backup(self):
        if create_vr_backup():
            QMessageBox.information(self, tr("backup_ok_title"), tr("backup_ok_text"))
        else:
            QMessageBox.critical(self, tr("error"), tr("backup_fail_text"))

    def trigger_vr_restore(self):
        # FIX: 'self' übergeben, da die Funktion das Parent-Fenster für die Dialoge braucht
        restore_vr_environment(self)

    def trigger_vr_restore_github(self):
        """Lädt das saubere Referenz-Backup von GitHub ins lokale Backup-
        Verzeichnis. Danach kann normal per 'Wiederherstellen' angewendet werden."""
        sync_backup_from_github(self)

    def apply_theme(self):
        """
        Oberflaeche auf das gespeicherte Thema umfaerben.

        Wird beim Start aufgerufen und nach jeder Aenderung im Design-Bereich.
        Weil neu erzeugte Widgets (Paketzeilen, Karten) ihr Original-Stylesheet
        mitbringen, ist der Aufruf gefahrlos wiederholbar — theme.apply_to_tree
        merkt sich je Widget den unveraenderten Ausgangszustand.
        """
        try:
            count = theme.apply_to_tree(self)
            # Auch das Stylesheet der Anwendung: dort steht die Flaeche hinter
            # den Karten (QStackedWidget) sowie Dialoge, Menues und Tooltips.
            theme.apply_to_app(QApplication.instance())
            bg = theme.window_background_css()
            if bg:
                root = self.ui.central_widget
                base = root.property("yk_base_qss") or ""
                root.setStyleSheet(theme.tint(base) + "\n" + bg)
            log.debug("[Theme] %s Stylesheets eingefaerbt (%s)", count,
                      theme.current().get("theme"))
        except Exception:
            # Ein Fehler beim Faerben darf die App nicht am Start hindern —
            # im schlimmsten Fall sieht sie aus wie immer.
            log.exception("[Theme] Einfaerben fehlgeschlagen")

    def _package_groups_for(self, method):
        """Welche Status-Zeilen je Methode?"""
        if method == "apt":
            # Debian/Ubuntu/Mint: WiVRn aus der PPA plus die Komponenten, die
            # es dort NICHT als Paket gibt (xrizer aus dem GitHub-Release).
            groups = dict(INSTALL_APT)
            groups.update(apt_github_groups())
            return groups
        if method == "dnf":
            # Fedora-Repos (wivrn, wivrn-dashboard, opencomposite) PLUS die
            # COPR-Komponenten (xrizer). Letztere standen frueher nur in einem
            # Hinweisfenster zum Abtippen und tauchten im Tab gar nicht auf.
            groups = dict(INSTALL_DNF)
            groups.update(dnf_copr_groups())
            return groups
        if method == "native":
            return {"WiVRn": ["wivrn-server"]}
        if not method:
            # Ubuntu/Debian: keine Methode -> nur den WiVRn-Status zeigen
            return {"WiVRn": ["wivrn-server"]}
        return dict(INSTALL_PACKAGES)         # yay/paru

    def _rebuild_package_rows(self):
        """
        Baut die Status-Zeilen im Installations-Tab neu auf.

        Jede Zeile bekommt:
          Status | (Quelle) | [Installieren]

        Das Dropdown erscheint nur, wenn es fuer diese Komponente wirklich
        mehrere Wege gibt — bei einer einzigen Quelle waere es nur Klickarbeit
        ohne Auswahl. Der Knopf daneben installiert genau diese eine
        Komponente; der grosse Knopf unten macht weiterhin alles Fehlende auf
        einmal.
        """
        layout = self.ui.pkg_layout
        while layout.rowCount():
            layout.removeRow(0)
        self.prog_labels = {}
        self.pkg_source_combos = {}
        self.pkg_row_buttons = {}

        # Feste Breiten, damit Dropdown und Knopf ueber alle Zeilen hinweg in
        # einer Spalte stehen. Ohne das bestimmt der laengste Statustext, wo
        # der Knopf landet — und die Knoepfe fransen zeilenweise aus.
        combo_width = 210
        button_width = 120

        method = self._install_method()
        for name in self._package_groups_for(method).keys():
            lbl = QLabel("…")
            self.prog_labels[name] = lbl

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.setSpacing(10)
            row_layout.addWidget(lbl)
            row_layout.addStretch(1)

            sources = component_sources(method, name)
            if len(sources) > 1:
                combo = QComboBox()
                combo.setFixedSize(combo_width, 28)
                for src in sources:
                    combo.addItem(SOURCE_LABELS.get(src, src), src)
                combo.setToolTip(tr("install_source_tip"))
                self.pkg_source_combos[name] = combo
                row_layout.addWidget(combo)
            elif sources:
                # Platzhalter statt Dropdown: haelt die Knopf-Spalte gerade,
                # auch wenn nur eine Zeile eine Auswahl hat.
                spacer = QWidget()
                spacer.setFixedWidth(combo_width)
                row_layout.addWidget(spacer)

            if sources:
                btn = QPushButton(tr("install_row_btn"))
                btn.setFixedSize(button_width, 28)
                btn.setStyleSheet("""
                    QPushButton { background-color: #3b4252; color: #d8dee9;
                                  font-size: 11px; border-radius: 4px; border: none;
                                  padding: 0px 10px; }
                    QPushButton:hover { background-color: #4c566a; }
                    QPushButton:disabled { color: #6b7280; }
                """)
                btn.setToolTip(tr("install_row_tip").format(name=name))
                btn.clicked.connect(lambda _=False, n=name: self.install_component(n))
                self.pkg_row_buttons[name] = btn
                row_layout.addWidget(btn)

            layout.addRow(QLabel(f"{name}:"), row)

    def _selected_source(self, name):
        """Gewaehlte Quelle einer Komponente — oder die Vorauswahl."""
        combo = getattr(self, "pkg_source_combos", {}).get(name)
        if combo is not None:
            return combo.currentData()
        sources = component_sources(self._install_method(), name)
        return sources[0] if sources else ""

    def _on_install_method_changed(self, *args):
        """Dropdown gewechselt -> Zeilen neu aufbauen und Status prüfen."""
        self._rebuild_package_rows()
        self.check_system_packages()

    # ------------------------------------------------------------------ #
    #  Paketstatus im Installations-Tab                                    #
    # ------------------------------------------------------------------ #
    # Frueher lief hier beim Start je Paket ein "yay -Q" UND ein "yay -Qu",
    # nacheinander und im GUI-Thread: bei sechs Paketen also bis zu zwoelf
    # Aufrufe, von denen die Haelfte ("-Qu") das AUR abfragt und dabei ans
    # Netz geht. Das Fenster erschien erst danach — auf einem langsamen
    # Spiegelserver dauerte der Start dadurch mehrere Sekunden.
    #
    # Jetzt gilt:
    #   1. Die Paketlisten werden EINMAL geholt und ausgewertet (2 Aufrufe
    #      statt 12), egal wie viele Pakete geprueft werden.
    #   2. Das laeuft in einem Hintergrund-Thread. Das Fenster ist sofort da,
    #      die Statuszeilen fuellen sich Sekundenbruchteile spaeter.

    def check_system_packages(self):
        """Paketstatus im Hintergrund ermitteln (blockiert die Oberflaeche nicht)."""
        method = self._install_method()
        groups = self._package_groups_for(method)

        for name in groups:
            if name in self.prog_labels:
                self.prog_labels[name].setText(tr("pkg_checking"))
                self.prog_labels[name].setStyleSheet("color: #7b88a1;")

        # Laeuft bereits eine Pruefung, diese zuerst beenden — sonst schreiben
        # zwei Threads in dieselben Labels (z. B. bei schnellem Wechsel der
        # Installationsmethode).
        worker = getattr(self, "_pkgcheck_worker", None)
        if worker is not None and worker.isRunning():
            worker.wait(2000)

        self._pkgcheck_worker = PackageCheckWorker(method, groups)
        self._pkgcheck_worker.result_signal.connect(self._on_package_check_done)
        self._pkgcheck_worker.start()

    def _on_package_check_done(self, results, updates_available):
        """Ergebnis des Hintergrund-Threads in die Oberflaeche uebertragen."""
        for name, state in results.items():
            label = self.prog_labels.get(name)
            if label is None:
                continue                      # Methode wurde zwischenzeitlich gewechselt
            if state["installed"]:
                if state["has_update"]:
                    label.setText(tr("pkg_installed") + " (Update available)")
                    label.setStyleSheet("color: #d08770; font-weight: bold;")
                else:
                    label.setText(tr("pkg_installed"))
                    label.setStyleSheet("color: #a3be8c; font-weight: bold;")
            else:
                label.setText(tr("pkg_incomplete"))
                label.setStyleSheet("color: #ebcb8b; font-weight: bold;")

        self.ui.lbl_wivrn_ver.setText(f"<b>WiVRn Version:</b> {self.get_wivrn_version()}")
        note = getattr(self, "_install_missing_note", "")
        if note:
            # Einmalig: nach der naechsten Pruefung gilt wieder der Normaltext.
            self._install_missing_note = ""
            self.ui.lbl_worker_status.setText(note)
        else:
            self.ui.lbl_worker_status.setText(
                tr("install_updates_available") if updates_available else tr("install_check_done"))
        self._update_update_button()

    def _show_ubuntu_install_guide(self):
        """
        Ubuntu/Debian: WiVRn liegt nicht in den Repos. Statt Flatpak zeigen wir
        die native Bau-Anleitung (schlanker + bessere Performance) mit einem
        Knopf, der die Befehle in die Zwischenablage legt.
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle(tr("ubuntu_guide_title"))
        box.setText(tr("ubuntu_guide_text"))
        copy_btn = box.addButton(tr("ubuntu_guide_copy"), QMessageBox.AcceptRole)
        docs_btn = box.addButton(tr("ubuntu_guide_docs"), QMessageBox.ActionRole)
        box.addButton(QMessageBox.Close)
        box.exec()
        if box.clickedButton() == copy_btn:
            QApplication.clipboard().setText(UBUNTU_BUILD_COMMANDS)
            self.ui.lbl_worker_status.setText(tr("ubuntu_guide_copied"))
        elif box.clickedButton() == docs_btn:
            webbrowser.open("https://github.com/WiVRn/WiVRn/blob/master/docs/building.md")

    def _confirm_fedora_copr(self, name, copr):
        """
        Rueckfrage vor dem Aktivieren eines COPR.

        Ein COPR ist ein FREMDES Repository — das aktiviert die App nicht
        stillschweigend. Frueher stand hier ein reines Hinweisfenster mit
        'Befehle kopieren'; der Nutzer musste die zwei Zeilen selbst in ein
        Terminal einfuegen. Jetzt ist es eine Ja/Nein-Frage, und bei 'Ja'
        erledigt der InstallWorker beides im sichtbaren Terminalfenster —
        genau wie bei allen anderen Paketen.

        Rueckgabe: True = installieren, False = ueberspringen.
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(tr("fedora_copr_title").format(name=name))
        box.setText(tr("fedora_copr_text").format(name=name, copr=copr))
        yes_btn = box.addButton(tr("fedora_copr_yes"), QMessageBox.AcceptRole)
        github_btn = None
        if name == "xrizer":
            github_btn = box.addButton(tr("fedora_copr_github"), QMessageBox.ActionRole)
        box.addButton(tr("fedora_copr_no"), QMessageBox.RejectRole)
        box.setDefaultButton(yes_btn)
        box.exec()
        if github_btn is not None and box.clickedButton() == github_btn:
            return "github"
        return "copr" if box.clickedButton() == yes_btn else "skip"

    def start_xrizer_github_download(self):
        """
        xrizer ohne COPR installieren — direkt aus dem GitHub-Release.

        Gedacht fuer den Fall, dass copr.fedorainfracloud.org kriecht oder gar
        nicht antwortet: dnf bricht dann nach Minuten mit
        'Curl error (28): Timeout was reached' ab. Der Download hier braucht
        weder ein Repository noch root und landet in ~/.local/share/xrizer.
        """
        if getattr(self, "xrizer_worker", None) and self.xrizer_worker.isRunning():
            return
        self.ui.btn_install.setEnabled(False)
        self.xrizer_worker = XrizerGithubWorker()
        self.xrizer_worker.status_signal.connect(self.ui.lbl_worker_status.setText)
        self.xrizer_worker.finished_signal.connect(self._on_xrizer_github_done)
        self.xrizer_worker.start()

    def _on_xrizer_github_done(self, ok, path_or_error, tag):
        self.ui.btn_install.setEnabled(True)
        if not ok:
            self.ui.lbl_worker_status.setText(
                tr("xrizer_github_failed").format(error=path_or_error))
            QMessageBox.warning(self, tr("fedora_copr_title").format(name="xrizer"),
                                tr("xrizer_github_failed").format(error=path_or_error))
            return

        self.ui.lbl_worker_status.setText(
            tr("xrizer_github_ok").format(tag=tag, path=path_or_error))

        # WiVRn sucht ~/.local/share/xrizer NICHT von allein ab. Ohne Eintrag
        # in der config.json waere der Download also wirkungslos — deshalb die
        # Rueckfrage, statt es stillschweigend zu setzen oder es zu lassen.
        mode, current = venv.current_openvr_compat()
        if mode != venv.OPENVR_DEFAULT and current == path_or_error:
            return
        answer = QMessageBox.question(
            self, tr("xrizer_github_use_title"),
            tr("xrizer_github_use_text").format(path=path_or_error),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if answer == QMessageBox.Yes:
            venv.set_openvr_compat("path", path_or_error)
            if hasattr(self, "refresh_openvr_ui"):
                self.refresh_openvr_ui()

    def _confirm_apt_ppa(self):
        """
        Rueckfrage vor dem Eintragen der WiVRn-PPA.

        WiVRn liegt nicht in den offiziellen Ubuntu-Quellen. Eine PPA ist ein
        Fremdrepository und bleibt nach der Installation dauerhaft aktiv — sie
        liefert dann auch Updates. Beides sollte der Nutzer wissen, bevor es
        passiert; dieselbe Haltung wie beim COPR auf Fedora.
        """
        if getattr(self, "_apt_ppa_confirmed", False):
            return True

        # Baut die PPA ueberhaupt fuer diese Ubuntu-Ausgabe? Auf Mint 22.x
        # (Basis 'noble') lautet die Antwort nein, und ohne diese Vorabpruefung
        # sieht der Nutzer erst mitten in der laufenden Installation
        # 'Cannot add PPA: This PPA does not support noble'.
        codename = appimg.ubuntu_codename()
        supported = appimg.ppa_supports_codename(UBUNTU_WIVRN_PPA, codename)
        if supported is False:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle(tr("apt_ppa_unsupported_title"))
            box.setText(tr("apt_ppa_unsupported_text").format(
                ppa=UBUNTU_WIVRN_PPA, codename=codename))
            flat_btn = box.addButton(tr("apt_flatpak_yes"), QMessageBox.AcceptRole)
            box.addButton(tr("fedora_copr_no"), QMessageBox.RejectRole)
            box.setDefaultButton(flat_btn)
            box.exec()
            if box.clickedButton() == flat_btn:
                self.install_wivrn_flatpak()
            return False
        # supported is None -> Launchpad nicht erreichbar. Dann NICHT
        # blockieren: lieber der Versuch als eine falsche Absage.

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(tr("apt_ppa_title"))
        box.setText(tr("apt_ppa_text").format(ppa=UBUNTU_WIVRN_PPA))
        yes_btn = box.addButton(tr("apt_ppa_yes"), QMessageBox.AcceptRole)
        box.addButton(tr("fedora_copr_no"), QMessageBox.RejectRole)
        box.setDefaultButton(yes_btn)
        box.exec()
        ok = box.clickedButton() == yes_btn
        self._apt_ppa_confirmed = ok
        return ok

    def install_wivrn_flatpak(self):
        """
        WiVRn als Flatpak von Flathub installieren.

        Der Weg fuer Systeme, fuer die die PPA nicht baut. Der Flatpak bringt
        xrizer UND OpenComposite mit — auf diesem Weg braucht es also auch den
        GitHub-Download nicht. Dafuer laeuft er in einer Sandbox: die
        Konfiguration liegt unter ~/.var/app/, und die Steuerung des Servers
        aus yakuda-connect heraus ist eingeschraenkt. Genau das sagt die
        Rueckfrage dem Nutzer auch.
        """
        if getattr(self, "worker", None) and self.worker.isRunning():
            return
        if not shutil.which("flatpak"):
            QMessageBox.warning(self, tr("apt_flatpak_title"),
                                tr("apt_flatpak_missing"))
            return
        self.ui.btn_install.setEnabled(False)
        self._last_install_method = "flatpak"
        self._last_install_pkgs = []          # Nachkontrolle laeuft ueber flatpak info
        self._xrizer_github_after_install = False
        self.worker = InstallWorker([WIVRN_FLATPAK_ID], helper="flatpak")
        self.worker.status_signal.connect(self.ui.lbl_worker_status.setText)
        self.worker.finished_signal.connect(self.on_installation_finished)
        self.worker.start()

    def _apt_packages_still_missing(self):
        """Welche der angeforderten .deb-Pakete sind nicht angekommen?"""
        missing = []
        for pkg in getattr(self, "_last_install_pkgs", []):
            out = proc.output_of(["dpkg-query", "-W", "-f=${db:Status-Status}", pkg],
                                 timeout=proc.DEFAULT_TIMEOUT)
            if (out or "").strip() != "installed":
                missing.append(pkg)
        return missing

    def _pending_dnf_copr_packages(self):
        """
        Welche COPR-Komponenten fehlen noch? Rueckgabe: [(anzeigename, pkg), ...]

        Geprueft wird doppelt: 'rpm -q' fuer das Paket UND find_openvr_compat
        fuer den Fall, dass der Nutzer die Runtime selbst gebaut hat (dann
        liegt sie auf der Platte, ohne dass rpm davon weiss).
        """
        pending = []
        for name, cfg in INSTALL_DNF_COPR.items():
            if name == "xrizer" and venv.find_openvr_compat("xrizer"):
                continue                       # selbst gebaut / schon vorhanden
            for pkg in cfg["pkgs"]:
                res = proc.run(["rpm", "-q", pkg],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=proc.DEFAULT_TIMEOUT)
                if res.returncode != 0:
                    pending.append((name, pkg))
        return pending

    def _populate_install_method_combo(self):
        """Füllt das Methoden-Dropdown des Installations-Tabs (yay/paru/dnf)."""
        combo = getattr(self.ui, "combo_install_method", None)
        methods = appimg.available_update_methods()
        self._install_methods = methods
        if combo is None:
            return
        labels = {"yay": "yay", "paru": "paru", "dnf": "dnf (Fedora)", "native": "Nativ"}
        combo.blockSignals(True)
        combo.clear()
        for mthd in methods:
            combo.addItem(labels.get(mthd, mthd), mthd)
        default = appimg.default_update_method(methods)
        if default:
            idx = combo.findData(default)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        combo.blockSignals(False)
        combo.setVisible(len(methods) >= 2)
        self._update_update_button()

    def _apply_distro_ui_rules(self):
        """
        Distro-abhängige Regeln für den Installations-Tab:
          Ubuntu/Debian : Update-Knopf komplett ausblenden (WiVRn ist nicht in den
                          Repos -> es gibt nichts, was wir aktualisieren könnten).
          Fedora        : Update-Knopf heißt 'Über Fedora-Software aktualisieren'.
          Arch          : unverändert.
        """
        try:
            if appimg.is_debian_based():
                self.ui.btn_update.setVisible(False)
                self.ui.btn_install.setText(tr("install_btn_guide"))
            elif appimg.is_fedora_based():
                self.ui.btn_update.setVisible(True)
                self.ui.btn_update.setText(tr("update_btn_fedora"))
        except Exception as e:
            log.info(f"[Distro-UI] {e}")

    def _update_update_button(self):
        """Aktualisieren-Knopf: aktiv nur, wenn es eine Methode gibt und sie NICHT 'native' ist."""
        methods = getattr(self, "_install_methods", None) or appimg.available_update_methods()
        enable = bool(methods) and self._install_method() != "native"
        self.ui.btn_update.setEnabled(enable)
        # Ubuntu/Debian: Knopf bleibt unsichtbar, egal was der Status sagt
        if appimg.is_debian_based():
            self.ui.btn_update.setVisible(False)

    def _install_method(self):
        """Aktuell gewählte Methode des Installations-Tabs."""
        combo = getattr(self.ui, "combo_install_method", None)
        methods = getattr(self, "_install_methods", None) or appimg.available_update_methods()
        if combo is not None and combo.count() > 0:
            data = combo.currentData()
            if data:
                return data
        return appimg.default_update_method(methods)

    def _open_fedora_software(self):
        """
        Öffnet das Fedora-Software-Center (GNOME Software / KDE Discover).
        True, wenn eines gestartet werden konnte.
        """
        for cmd in (["gnome-software", "--mode=updates"], ["plasma-discover", "--mode", "update"],
                    ["dnfdragora"]):
            if shutil.which(cmd[0]):
                try:
                    subprocess.Popen(cmd)
                    return True
                except Exception:
                    continue
        return False

    def start_system_update(self):
        """Update-Knopf: führt ein Ökosystem-Update über die gewählte Methode aus."""
        method = self._install_method()

        # Ubuntu/Debian: Knopf ist ausgeblendet — falls doch jemand hier landet, abbrechen
        if appimg.is_debian_based():
            return

        # Fedora: nicht selbst 'dnf upgrade' fahren, sondern das Software-Center öffnen.
        # Das ist der Weg, den Fedora-Nutzer erwarten (und es braucht kein sudo im Terminal).
        if method == "dnf":
            if self._open_fedora_software():
                self.ui.lbl_worker_status.setText(tr("fedora_update_opened"))
            else:
                QMessageBox.information(self, tr("update_btn"), tr("fedora_update_manual"))
            return

        if method == "native":
            QMessageBox.information(self, tr("native_update_title"), tr("native_update_text"))
            return
        if not method:
            self.ui.lbl_worker_status.setText(tr("install_no_update_method"))
            return
        self.ui.btn_install.setEnabled(False)
        self.ui.btn_update.setEnabled(False)
        self.update_worker = UpdateWorker(method)
        self.update_worker.status_signal.connect(self.ui.lbl_worker_status.setText)
        self.update_worker.finished_signal.connect(self.on_installation_finished)
        self.update_worker.start()

    def install_component(self, name):
        """
        Nur diese eine Komponente installieren — ueber die in ihrer Zeile
        gewaehlte Quelle.

        Bewusst getrennt vom grossen Knopf unten: wer nur xrizer nachziehen
        will, soll nicht den ganzen Durchlauf ueber alle Pakete anstossen
        muessen (und im Fehlerfall nicht raten, welches Paket geklemmt hat).
        """
        if getattr(self, "worker", None) and self.worker.isRunning():
            return
        source = self._selected_source(name)
        if not source:
            return

        if source == SOURCE_FLATPAK:
            self.install_wivrn_flatpak()
            return

        if source == SOURCE_GITHUB:
            # Nur xrizer hat aktuell einen GitHub-Weg; sollte spaeter etwas
            # dazukommen, faellt es hier auf.
            if name != "xrizer":
                log.warning("GitHub-Quelle fuer '%s' ist nicht vorgesehen.", name)
                return
            self.start_xrizer_github_download()
            return

        pkgs = self._package_groups_for(self._install_method()).get(name, [])
        if not pkgs:
            return

        copr_map = {}
        if source == SOURCE_COPR:
            # Die Auswahl im Dropdown IST die Zustimmung zum Fremdrepository —
            # eine zusaetzliche Rueckfrage waere hier nur noch laestig.
            copr = dnf_copr_for_package(pkgs[0])
            if copr:
                copr_map = {pkg: copr for pkg in pkgs}

        ppa = ""
        if source == SOURCE_PPA:
            # Hier gibt es KEIN Dropdown (es gaebe nur eine Quelle), also fehlt
            # die stillschweigende Zustimmung. Deshalb wird gefragt, bevor ein
            # Fremdrepository ins System eingetragen wird.
            if not self._confirm_apt_ppa():
                return
            ppa = UBUNTU_WIVRN_PPA

        helper = ("dnf" if source in ("dnf", SOURCE_COPR)
                  else "apt" if source == SOURCE_PPA else source)
        self.ui.btn_install.setEnabled(False)
        self._last_install_method = self._install_method()
        self._last_install_pkgs = list(pkgs)
        self._xrizer_github_after_install = False
        self.worker = InstallWorker(pkgs, helper=helper, copr_map=copr_map, ppa=ppa)
        self.worker.status_signal.connect(self.ui.lbl_worker_status.setText)
        self.worker.finished_signal.connect(self.on_installation_finished)
        self.worker.start()

    def start_package_installation(self):
        """Install-Knopf: installiert die WiVRn-Runtime über die gewählte Methode."""
        method = self._install_method()
        copr_map = {}          # nur auf Fedora gefuellt (siehe dnf-Zweig)

        # Ubuntu/Debian: kein Paket in den Repos -> Kurzanleitung zum nativen Bauen
        if appimg.is_debian_based():
            self._show_ubuntu_install_guide()
            return

        if method == "native":
            QMessageBox.information(self, tr("native_install_title"), tr("native_install_text"))
            return
        if not method:
            self.ui.lbl_worker_status.setText(tr("install_no_method"))
            return

        if method == "apt":
            # Debian/Ubuntu/Mint: fehlende .deb-Pakete aus der PPA, danach —
            # falls noetig — xrizer aus dem GitHub-Release.
            packages_to_process = []
            for pkgs in INSTALL_APT.values():
                for pkg in pkgs:
                    out = proc.output_of(["dpkg-query", "-W", "-f=${db:Status-Status}", pkg],
                                         timeout=proc.DEFAULT_TIMEOUT)
                    if (out or "").strip() != "installed":
                        packages_to_process.append(pkg)

            github_wanted = bool(apt_github_groups()) and not venv.find_openvr_compat("xrizer")
            if packages_to_process and not self._confirm_apt_ppa():
                packages_to_process = []

            if not packages_to_process:
                if github_wanted:
                    self.start_xrizer_github_download()
                    return
                self.ui.lbl_worker_status.setText(tr("install_check_done"))
                return

            self._xrizer_github_after_install = github_wanted
            self._last_install_method = method
            self._last_install_pkgs = list(packages_to_process)
            self.ui.btn_install.setEnabled(False)
            self.worker = InstallWorker(packages_to_process, helper="apt",
                                        ppa=UBUNTU_WIVRN_PPA)
            self.worker.status_signal.connect(self.ui.lbl_worker_status.setText)
            self.worker.finished_signal.connect(self.on_installation_finished)
            self.worker.start()
            return

        if method == "dnf":
            # Fedora: nur die fehlenden Pakete aus den offiziellen Repos nachziehen
            packages_to_process = []
            for pkgs in INSTALL_DNF.values():
                for pkg in pkgs:
                    res = proc.run(["rpm", "-q", pkg],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=proc.DEFAULT_TIMEOUT)
                    if res.returncode != 0:
                        packages_to_process.append(pkg)

            # COPR-Komponenten (xrizer) hinten anhaengen — je Repository einmal
            # nachfragen. 'Nein' ueberspringt nur diesen Eintrag.
            asked = {}
            github_wanted = False
            for name, pkg in self._pending_dnf_copr_packages():
                # Was in der Zeile ausgewaehlt ist, gilt auch fuer den grossen
                # Knopf — sonst wuerde er die Auswahl des Nutzers stillschweigend
                # uebergehen.
                source = self._selected_source(name)
                if source == SOURCE_GITHUB:
                    github_wanted = True
                    continue
                copr = dnf_copr_for_package(pkg)
                if copr is None:
                    continue
                if copr not in asked:
                    asked[copr] = self._confirm_fedora_copr(name, copr)
                choice = asked[copr]
                if choice == "github":
                    github_wanted = True
                    continue
                if choice != "copr":
                    continue
                packages_to_process.append(pkg)
                copr_map[pkg] = copr

            if github_wanted and not packages_to_process:
                self.start_xrizer_github_download()
                return
            self._xrizer_github_after_install = github_wanted

            if not packages_to_process:
                self.ui.lbl_worker_status.setText(tr("install_check_done"))
                return
            worker_pkgs, helper = packages_to_process, "dnf"

        elif method in ("yay", "paru"):
            # nur fehlende AUR-Pakete installieren
            packages_to_process = []
            for prog_name, pkgs in self.required_packages.items():
                for pkg in pkgs:
                    result = proc.run([method, "-Q", pkg],
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=proc.DEFAULT_TIMEOUT)
                    if result.returncode != 0:
                        packages_to_process.append(pkg)
            if not packages_to_process:
                self.ui.lbl_worker_status.setText(tr("install_check_done"))
                return
            worker_pkgs, helper = packages_to_process, method
        else:
            self.ui.lbl_worker_status.setText(tr("install_no_method"))
            return

        self.ui.btn_install.setEnabled(False)
        self.ui.btn_update.setEnabled(False)

        self._last_install_method = method
        self._last_install_pkgs = list(worker_pkgs)
        self.worker = InstallWorker(worker_pkgs, helper=helper, copr_map=copr_map)
        self.worker.status_signal.connect(self.ui.lbl_worker_status.setText)
        self.worker.finished_signal.connect(self.on_installation_finished)
        self.worker.start()

    def _dnf_packages_still_missing(self):
        """
        Welche der eben angeforderten Pakete sind NICHT angekommen?

        Das Terminalfenster schliesst sich nach zwei Sekunden von selbst. Eine
        Fehlermeldung von dnf ("nothing provides ...", falsche Fedora-Version,
        COPR ohne Build fuer diese Release) ist damit weg, bevor sie jemand
        liest — und die App meldete trotzdem "erfolgreich installiert".
        Deshalb wird hinterher nachgesehen.
        """
        missing = []
        for pkg in getattr(self, "_last_install_pkgs", []):
            res = proc.run(["rpm", "-q", pkg],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=proc.DEFAULT_TIMEOUT)
            if res.returncode != 0:
                missing.append(pkg)
        return missing

    def on_installation_finished(self, success):
        self.ui.btn_install.setEnabled(True)
        self._update_update_button()
        # Methode der Runtime-Installation in der Config merken
        m = getattr(self, "_last_install_method", "")
        if success and m:
            venv.set_runtime_method(m)
        if m == "dnf" and getattr(self, "_xrizer_github_after_install", False):
            self._xrizer_github_after_install = False
            self.start_xrizer_github_download()
            return
        if m == "apt":
            missing = self._apt_packages_still_missing()
            if missing:
                log.warning("apt-Installation unvollstaendig: %s", ", ".join(missing))
                self._install_missing_note = tr("install_apt_missing").format(
                    pkgs=", ".join(missing))
        if m == "dnf":
            missing = self._dnf_packages_still_missing()
            # Genau der Fall aus dem Fehlerbericht: das COPR antwortet mit
            # weniger als 1000 Bytes/Sekunde, dnf gibt nach Minuten auf. Statt
            # den Nutzer damit sitzen zu lassen, wird hier der Weg ueber
            # GitHub angeboten.
            if "xrizer" in missing:
                answer = QMessageBox.question(
                    self, tr("xrizer_copr_failed_title"),
                    tr("xrizer_copr_failed_text"),
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if answer == QMessageBox.Yes:
                    self.start_xrizer_github_download()
                    return
            if missing:
                log.warning("dnf-Installation unvollstaendig: %s", ", ".join(missing))
                # Nicht direkt ins Label schreiben: check_system_packages()
                # laeuft gleich im Hintergrund an und wuerde den Text mit
                # "System-Check abgeschlossen" ueberschreiben. Der Hinweis wird
                # stattdessen gemerkt und dort ausgegeben.
                self._install_missing_note = tr("install_dnf_missing").format(
                    pkgs=", ".join(missing))
        self.check_system_packages()
        if not self.are_critical_packages_missing(): self.ui.sidebar.setCurrentRow(1)

    def open_port_9757_firewall(self):
        """
        Gibt die von WiVRn benoetigten Ports frei — mit der Firewall, die auf
        DIESEM System wirklich zustaendig ist (siehe core/firewall.py).

        Freigegeben wird, was WiVRns README verlangt:
            9757/tcp + 9757/udp   Verbindung Headset <-> PC
            5353/udp  (mDNS)      damit das Headset den PC ueberhaupt findet

        Bisher wurde stur zuerst nach ufw gesucht, mDNS blieb zu, und wenn
        gar keine Firewall lief, gab es eine Fehlermeldung. Alles drei ist
        hier behoben.
        """
        info = fw.detect()
        kind = info["kind"]
        log.info("Firewall erkannt: %s (aktiv=%s, gefunden=%s)",
                 kind, info["active"], ", ".join(info["installed"]) or "-")

        # 1. Gar keine Firewall — das ist normal (Arch/CachyOS ab Werk) und
        #    kein Fehler. Frueher: rote Warnung.
        if kind is None:
            QMessageBox.information(self, tr("firewall_none_title"),
                                    tr("firewall_none_text"))
            return

        # 2. nftables/iptables fassen wir nicht selbst an — dort gibt es keine
        #    verlaesslich gleiche Stelle fuer eine Regel. Stattdessen die
        #    fertigen Befehle zum Kopieren.
        if kind not in fw.SUPPORTED:
            self._show_firewall_commands(kind, tr("firewall_manual_text").format(fw=kind))
            return

        # 3. ufw: ist das WiVRn-Profil schon da, ist nichts zu tun (dieselbe
        #    Pruefung wie im WiVRn-Dashboard) — spart eine Passwortabfrage.
        if fw.already_configured(kind):
            self._mark_firewall_done()
            QMessageBox.information(self, tr("success"),
                                    tr("firewall_already_text").format(fw=kind))
            return

        ok, err = fw.apply(kind)
        if ok:
            self._mark_firewall_done()
            text = tr("firewall_ok_text").format(fw=kind)
            if not info["active"]:
                text += "\n\n" + tr("firewall_inactive_note").format(fw=kind)
            QMessageBox.information(self, tr("success"), text)
        else:
            self._show_firewall_commands(
                kind, tr("firewall_fail_text").format(fw=kind, err=err))

    def _mark_firewall_done(self):
        """Knopf im Dashboard auf 'erledigt' setzen."""
        self.ui.btn_port_status.setText(tr_amp("firewall_btn_done"))
        # Stylesheet aus ui_main: es enthaelt den linken Innenabstand fuer das
        # (ⓘ) im Knopf. Ein eigenes Stylesheet hier wuerde ihn verlieren und
        # die Beschriftung unter das Symbol schieben.
        self.ui.btn_port_status.setStyleSheet(self.ui._CSS_FIREWALL_DONE)
        # Auf dem gruenen Grund braucht das Symbol eine dunkle Farbe, sonst
        # steht Hellgrau auf Hellgruen.
        self.ui.btn_firewall_info.setStyleSheet(
            "QToolButton { color:#2e3440; background:transparent; border:none;"
            " font-size:14px; padding:0; }"
            " QToolButton:hover { color:#3b4252; }")

    def _show_firewall_commands(self, kind, intro):
        """Zeigt die Befehle zum Selbst-Ausfuehren, mit Kopier-Knopf.

        Ohne Kopier-Knopf tippt sie niemand fehlerfrei ab — und genau in
        diesem Moment (Firewall haengt) ist der Nutzer ohnehin schon genervt.
        """
        commands = "\n".join(fw.manual_commands(kind))
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(tr("firewall_manual_title"))
        box.setText(intro)
        box.setInformativeText(
            "<pre style='font-family:monospace'>" + commands.replace("<", "&lt;") + "</pre>")
        btn_copy = box.addButton(tr("tools_copy"), QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is btn_copy:
            QApplication.clipboard().setText(commands)

    def update_autostart_fields(self):
        try:
            target_count = int(self.ui.num_apps.text())
            if target_count < 0: target_count = 0
            if target_count > 10: target_count = 10
        except ValueError:
            target_count = 1
            self.ui.num_apps.setText("1")

        current_count = len(self.autostart_rows)

        if target_count > current_count:
            for i in range(current_count + 1, target_count + 1):
                row_layout = QHBoxLayout()
                lbl = QLabel(f"Programm {i}:")
                lbl.setFixedWidth(80)
                combo = QComboBox()
                combo.addItems(["Custom Path", "CMD"])
                combo.setFixedWidth(110)
                inp = QLineEdit("")
                btn = QPushButton("Browse...")
                btn.setFixedWidth(80)

                # Debug-Checkbox
                from PySide6.QtWidgets import QCheckBox
                chk_debug = QCheckBox("Debug")
                chk_debug.setToolTip(tr("autostart_debug_tip"))
                chk_debug.setFixedWidth(65)
                chk_debug.setStyleSheet("color: #ebcb8b; font-size: 11px;")

                combo.currentTextChanged.connect(lambda text, le=inp, bb=btn: le.setReadOnly(False) if text == "Custom Path" else bb.setEnabled(False))
                inp.textChanged.connect(self.trigger_auto_save)
                chk_debug.stateChanged.connect(self.trigger_auto_save)
                btn.clicked.connect(lambda checked, le=inp: self.browse_custom_app_for_row(le))

                row_layout.addWidget(lbl)
                row_layout.addWidget(combo)
                row_layout.addWidget(inp)
                row_layout.addWidget(btn)
                row_layout.addWidget(chk_debug)
                self.ui.autostart_container_layout.addLayout(row_layout)
                self.autostart_rows.append({
                    "label": lbl, "combo": combo, "input": inp,
                    "btn": btn, "chk_debug": chk_debug, "layout": row_layout
                })
        elif target_count < current_count:
            for _ in range(current_count - target_count):
                row = self.autostart_rows.pop()
                self.ui.autostart_container_layout.removeItem(row['layout'])
                row['combo'].deleteLater()
                row['input'].deleteLater()
                row['btn'].deleteLater()
                row['label'].deleteLater()
                row['chk_debug'].deleteLater()

        if not self.ui.num_apps.signalsBlocked(): self.trigger_auto_save()

    def browse_custom_app_for_row(self, line_edit):
        file_path, _ = QFileDialog.getOpenFileName(self, tr("dlg_choose_program"), "/usr/bin", tr("dlg_all_files"))
        if file_path:
            line_edit.setText(file_path)
            self.trigger_auto_save()

    def tracking_flags(self):
        """Liefert (hand_tracking, full_body_tracking) aus der Konfiguration.

        Fuer beides gibt es seit v1.1.6 keinen Schalter mehr im Dashboard:
        Hand- und Full-Body-Tracking muessen im Headset selbst aktiviert
        werden, der Haken in der App hat daran nichts geaendert. Die Werte
        werden aber weiterhin unveraendert mitgespeichert, damit bestehende
        Konfigurationen beim naechsten Speichern nicht stillschweigend
        umgeschrieben werden.
        """
        data = load_saved_settings() or {}
        return (bool(data.get("hand_tracking", False)),
                bool(data.get("full_body_tracking", True)))

    def open_vr_settings(self):
        """Springt zu Einstellungen -> VR & OpenXR.

        Ueber die Sidebar (nicht direkt ueber pages), damit die Sperre aus
        on_tab_changed greift, solange Grundpakete fehlen.
        """
        self.ui.sidebar.setCurrentRow(5)
        if hasattr(self.ui, "settings_subtabs"):
            self.ui.settings_subtabs.setCurrentIndex(1)   # 1 = VR & OpenXR
        if hasattr(self.ui, "vr_runtime_widget"):
            self.ui.vr_runtime_widget.refresh()

    def trigger_auto_save(self):
        if hasattr(self, 'is_loading') and self.is_loading: return
        apps_data = [{
            "type":  r["combo"].currentText(),
            "cmd":   r["input"].text(),
            "debug": r["chk_debug"].isChecked()
        } for r in self.autostart_rows]
        hand, fbt = self.tracking_flags()
        save_all_settings(
            hand,
            fbt,
            self.ui.chk_steamvr_tracker.isChecked(),
            self._stored_refresh_rate,
            self.ui.num_apps.text(),
            apps_data
        )

    def apply_loaded_settings(self):
        data = load_saved_settings()
        if not data: return

        # Sprache laden und sofort anwenden
        lang = data.get("language", "en")
        set_language(lang)
        self.ui.combo_language.blockSignals(True)
        self.ui.combo_language.setCurrentIndex(0 if lang == "en" else 1)
        self.ui.combo_language.blockSignals(False)
        self.apply_translations()

        # Advanced Mode (Schalter unten links) wiederherstellen. blockSignals,
        # damit das Setzen beim Start nicht sofort wieder gespeichert wird.
        advanced = bool(data.get("advanced_mode", False))
        adv.set_enabled(advanced)
        self.ui.toggle_advanced.blockSignals(True)
        self.ui.toggle_advanced.setChecked(advanced)
        self.ui.toggle_advanced.sync_offset()
        self.ui.toggle_advanced.blockSignals(False)
        self._refresh_advanced_boxes()

        self.ui.chk_steamvr_tracker.blockSignals(True)
        self.ui.num_apps.blockSignals(True)

        self.ui.chk_steamvr_tracker.setChecked(data.get("steam_tracker", False))
        # refresh_rate hat kein Bedienelement mehr (die Rate wird im Headset
        # gesetzt). Der gespeicherte Wert wird nur noch durchgereicht, damit
        # er beim naechsten Speichern nicht verloren geht.
        self._stored_refresh_rate = data.get("refresh_rate", "Auto")

        # Autostart-Einträge befüllen (über self.ui aufrufen!)
        autostart_count = int(data.get("autostart_count", "0"))
        self.ui.num_apps.setText(str(autostart_count))
        self.update_autostart_fields()

        # Backup-Gruppe ist jetzt immer in Settings sichtbar


        saved_apps = data.get("autostart_apps", [])
        for i, app in enumerate(saved_apps):
            if i < len(self.autostart_rows):
                self.autostart_rows[i]["combo"].setCurrentText(app.get("type", "Custom Path"))
                self.autostart_rows[i]["input"].setText(app.get("cmd", ""))
                self.autostart_rows[i]["chk_debug"].setChecked(app.get("debug", False))

        self.ui.chk_steamvr_tracker.blockSignals(False)
        self.ui.num_apps.blockSignals(False)

    def refresh_headset_list(self):
        """
        Gekoppelte Headsets auflisten. Haengt eines davon gerade am USB-Kabel,
        bekommt sein Eintrag ein "· USB" angehaengt — die Information steht
        damit direkt am Geraet statt in einer eigenen Zeile weiter oben.
        """
        self.ui.list_headsets.clear()
        if proc.run(["pgrep", "wivrn-server"], stdout=subprocess.DEVNULL, timeout=proc.DEFAULT_TIMEOUT).returncode != 0:
            self.ui.list_headsets.addItem(tr("dashboard_no_server"))
            return
        try:
            res = subprocess.run(["wivrnctl", "list-paired"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=proc.DEFAULT_TIMEOUT)
            if res.returncode == 0:
                for line in res.stdout.strip().split('\n'):
                    if not line.strip() or "Headset name" in line: continue
                    self.ui.list_headsets.addItem(self._tag_usb(line.strip()))
            if self.ui.list_headsets.count() == 0:
                self.ui.list_headsets.addItem(tr("dashboard_no_paired"))
        except Exception as e: self.ui.list_headsets.addItem(tr("err_generic").format(err=e))

    def _tag_usb(self, line):
        """
        Haengt "· USB" an, wenn der Name des Listeneintrags zu einer per USB
        erkannten Brille passt.

        Verglichen wird ueber den Namen, nicht ueber die Reihenfolge: sind
        mehrere Brillen gekoppelt, darf die Markierung nicht an der falschen
        landen. Passt kein Name, bleibt der Eintrag unveraendert — dann sagt
        die Statuszeile unter der Liste, was am Kabel haengt.
        """
        low = line.lower()
        for name in self._usb_device_names():
            if name and name in low:
                return f"{line}   · USB"
        return line

    def remove_selected_headset(self):
        item = self.ui.list_headsets.currentItem()
        if not item or "Keine" in item.text() or "Server" in item.text(): return
        match = re.match(r'^(\d+)', item.text())
        if match and QMessageBox.question(self, tr("headset_unpair_title"),
                                     tr("headset_unpair_text").format(name=item.text()),
                                     QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            proc.run(["wivrnctl", "unpair", match.group(1)], timeout=proc.DEFAULT_TIMEOUT)
            self.refresh_headset_list()

    def disconnect_current_headset(self):
        proc.run(["wivrnctl", "disconnect"], timeout=proc.DEFAULT_TIMEOUT)
        self.refresh_headset_list()

    def toggle_pairing_mode(self, checked):
        if checked:
            if proc.run(["pgrep", "wivrn-server"], stdout=subprocess.DEVNULL, timeout=proc.DEFAULT_TIMEOUT).returncode != 0:
                self.ui.chk_pairing.setChecked(False)
                return
            self.pairing_process = subprocess.Popen(["wivrnctl", "pair"], stdout=subprocess.PIPE, text=True)
            output = self.pairing_process.stdout.readline()
            self.ui.txt_code.setText(output.replace("PIN:", "").strip() if "PIN:" in output else "Aktiv...")
        else:
            if self.pairing_process: self.pairing_process.terminate()
            self.ui.txt_code.setText("")

    def is_headset_connected(self):
        """
        Prüft, ob AKTUELL ein Headset mit dem WiVRn-Server verbunden ist.
        Nutzt nur LIVE-Signale, die beim Trennen wieder verschwinden – daher
        NICHT die "Client connected"-Logzeile (die bleibt die ganze Session stehen
        und würde ein Erkennen der Trennung unmöglich machen).
        """
        # Signal A: WiVRn legt beim Verbinden ein virtuelles Audiogerät "WiVRn"
        # an und entfernt es beim Trennen (dokumentiertes Verhalten).
        try:
            for kind in ("sinks", "sources"):
                res = subprocess.run(["pactl", "list", "short", kind],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     text=True, timeout=2)
                if "wivrn" in res.stdout.lower():
                    return True
        except Exception as exc:
            log.debug("is_headset_connected: ignoriert — %s", exc)

        # Signal B: aktive (ESTABLISHED) TCP-Verbindung auf dem WiVRn-Port 9757.
        try:
            res = subprocess.run(["ss", "-Htan"], stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, text=True, timeout=2)
            for line in res.stdout.splitlines():
                if "ESTAB" in line and ":9757" in line:
                    return True
        except Exception as exc:
            log.debug("is_headset_connected: ignoriert — %s", exc)

        return False

    def _poll_headset_for_autostart(self):
        """
        Einweg-Timer-Tick (1x pro Sekunde), scharfgeschaltet beim Server-Start.

        Sobald eine echte Headset-Verbindung erkannt wird, werden die Autostart-
        Programme EINMAL direkt aus dieser laufenden Sitzung gestartet — sie
        erben damit alle Desktop-Umgebungsvariablen (DISPLAY/WAYLAND_DISPLAY,
        XDG_RUNTIME_DIR, DBus ...). Danach stoppt sich der Timer SELBST: es
        findet kein weiteres Polling statt, bis er über
        'Autostart-Bereitschaft zurücksetzen' oder einen Server-Neustart wieder
        scharfgeschaltet wird.
        """
        # Server nicht (mehr) aktiv? -> Timer entwaffnen, nichts starten.
        server_running = (self.server_process and self.server_process.poll() is None) or \
            proc.run(["pgrep", "wivrn-server"], stdout=subprocess.DEVNULL, timeout=proc.DEFAULT_TIMEOUT).returncode == 0
        if not server_running:
            self.autostart_timer.stop()
            return

        if self.is_headset_connected():
            log.info("[Autostart] Headset verbunden – starte Programme aus der Sitzung.")
            self.launch_autostart_apps()
            self._autostart_launched = True
            self._headset_connected = True
            # Selbst-Beendigung: ab hier kein Polling mehr.
            self.autostart_timer.stop()
            log.info("[Autostart] Programme gestartet – Timer beendet (kein weiteres Polling).")

    def arm_autostart_timer(self):
        """
        Schaltet den Einweg-Autostart-Timer scharf. Startet noch NICHTS — der
        Timer wartet nur darauf, dass sich das Headset verbindet. Ohne
        konfigurierte Programme bleibt er aus (kein unnötiges Polling).
        """
        self._autostart_launched = False
        self._headset_connected = False
        has_apps = any(r["input"].text().strip() for r in self.autostart_rows)
        if not has_apps:
            self.autostart_timer.stop()
            log.info("[Autostart] Keine Programme konfiguriert – Timer bleibt aus.")
            return
        if not self.autostart_timer.isActive():
            self.autostart_timer.start()
        log.info("[Autostart] Bereitschaft scharf – warte auf Headset-Verbindung.")

    def reset_autostart_readiness(self):
        """
        Manueller Reset über den Dashboard-Button: schaltet den Einweg-Timer
        erneut scharf, OHNE den Server neu zu starten. Bereits laufende
        Autostart-Programme werden vorher beendet, damit es beim nächsten
        Verbinden keine doppelten Instanzen gibt.
        """
        server_running = (self.server_process and self.server_process.poll() is None) or \
            proc.run(["pgrep", "wivrn-server"], stdout=subprocess.DEVNULL, timeout=proc.DEFAULT_TIMEOUT).returncode == 0
        if not server_running:
            QMessageBox.information(
                self, tr("autostart_reset_title"), tr("autostart_reset_no_server"))
            return

        self.stop_autostart_apps()
        self.arm_autostart_timer()

        # Kurzes visuelles Feedback am Button (wie bei den OpenXR-Copy-Buttons).
        self.ui.btn_autostart_reset.setText(tr("autostart_reset_done"))
        QTimer.singleShot(
            1500,
            lambda: self.ui.btn_autostart_reset.setText(tr("dashboard_autostart_reset")))

    def kill_autostart_apps(self):
        """
        Besen-Button: beendet sofort ALLE laufenden Autostart-Programme
        (WayVR, OSC Leash ...). Reine Aufräumaktion für eine Pause:
          • der Einweg-Timer wird NICHT neu scharfgeschaltet
          • der WiVRn-Server läuft weiter
        Sollen die Apps später wieder kommen, einfach 'Timer zurücksetzen'.
        """
        self.stop_autostart_apps()
        self._headset_connected = False   # keine aktive App-Sitzung mehr
        log.info("[Autostart] Laufende Programme manuell beendet (Besen-Button).")

        # Kurzes visuelles Feedback am Button.
        self.ui.btn_autostart_kill.setText(tr("autostart_kill_done"))
        QTimer.singleShot(
            1500,
            lambda: self.ui.btn_autostart_kill.setText(tr("dashboard_autostart_kill")))

    def launch_autostart_apps(self):
        """Startet die in den Autostart-Zeilen hinterlegten Programme und merkt sich die Prozesse."""
        # Eventuelle Reste zuerst beenden, damit nichts doppelt läuft.
        self.stop_autostart_apps()
        for row in self.autostart_rows:
            cmd = row["input"].text().strip()
            if not cmd:
                continue
            try:
                if row["chk_debug"].isChecked():
                    # Mit sichtbarem Terminal starten
                    from install_worker import find_terminal
                    terminal, flags = find_terminal()
                    if terminal:
                        p = subprocess.Popen(
                            [terminal] + flags + ["bash", "-c", f"{cmd}; echo ''; echo '[Debug] Prozess beendet. Fenster schließen zum Beenden.'; read"],
                            start_new_session=True
                        )
                    else:
                        p = subprocess.Popen(cmd, shell=True, start_new_session=True)
                else:
                    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, start_new_session=True)
                self._autostart_procs.append(p)
            except Exception as e:
                log.warning(f"[Autostart] Konnte '{cmd}' nicht starten: {e}")

    # ------------------------------------------------------------------ #
    #  Eigene Kill-Befehle (Settings, ganz unten)
    # ------------------------------------------------------------------ #
    # Konzept: Der "Apps schließen"-Button killt alle Autostart-Programme
    # nach wie vor auf normalem Weg (SIGTERM → SIGKILL). Manche Apps
    # überleben das aber (Electron/VRCX, AppImage-Wrapper, ...). Für solche
    # Sonderfälle kann man hier Shell-Befehle hinterlegen, die ZUSÄTZLICH
    # direkt VOR dem normalen Kill laufen.
    def _killcmd_add_row(self, label_text="", cmd_text=""):
        """Fügt eine neue Zeile ins UI ein und merkt sie in self.ui.killcmd_rows."""
        from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        input_label = QLineEdit(label_text)
        input_label.setPlaceholderText(tr("killcmd_placeholder_lbl"))
        input_label.setFixedWidth(180)
        row_layout.addWidget(input_label)

        input_cmd = QLineEdit(cmd_text)
        input_cmd.setPlaceholderText(tr("killcmd_placeholder_cmd"))
        row_layout.addWidget(input_cmd, 1)

        btn_del = QPushButton("✕")
        btn_del.setToolTip(tr("killcmd_del_tooltip"))
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.setFixedWidth(30)
        btn_del.setStyleSheet(
            "QPushButton { background-color: #2e3440; color: #bf616a; border: 1px solid #4c566a;"
            " font-weight: bold; padding: 4px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #bf616a; color: white; border-color: #bf616a; }")
        row_layout.addWidget(btn_del)

        row_data = {"input_label": input_label, "input_cmd": input_cmd,
                    "btn_del": btn_del, "row_widget": row_widget}
        btn_del.clicked.connect(lambda: self._killcmd_remove_row(row_data))

        self.ui.killcmd_rows.append(row_data)
        self.ui.killcmd_rows_container.addWidget(row_widget)

    def _killcmd_remove_row(self, row_data):
        """Entfernt eine Zeile aus UI und Liste (Speichern muss der Nutzer selbst)."""
        try:
            self.ui.killcmd_rows.remove(row_data)
        except ValueError as exc:
            log.debug("_killcmd_remove_row: ignoriert — %s", exc)
        row_data["row_widget"].setParent(None)
        row_data["row_widget"].deleteLater()

    def _killcmd_load_from_config(self):
        """Liest gespeicherte Kill-Befehle aus der Config und baut die Zeilen."""
        entries = load_saved_settings().get("custom_kill_commands", []) or []
        # Alte UI-Zeilen aus einem evtl. Reload sauber entfernen (direkt, ohne
        # den Umweg über self._killcmd_remove_row — spart Sonderfälle).
        for row in list(self.ui.killcmd_rows):
            row["row_widget"].setParent(None)
            row["row_widget"].deleteLater()
        self.ui.killcmd_rows.clear()
        for e in entries:
            if isinstance(e, dict):
                self._killcmd_add_row(e.get("label", ""), e.get("cmd", ""))
            elif isinstance(e, str):
                # Rückwärtskompatibel: reine String-Liste ist auch okay.
                self._killcmd_add_row("", e)

    def _killcmd_save(self):
        """Schreibt die aktuellen Zeilen in die App-Config."""
        entries = []
        for row in self.ui.killcmd_rows:
            label = row["input_label"].text().strip()
            cmd = row["input_cmd"].text().strip()
            if not cmd:
                continue  # leere Befehle sind kein Eintrag
            entries.append({"label": label, "cmd": cmd})

        # Direkt in die config.json schreiben, ohne save_all_settings() zu bemühen
        # (das würde alle Dashboard-Werte mitspeichern — hier gerade nicht gewollt).
        try:
            data = load_saved_settings() or {}
        except Exception:
            data = {}
        data["custom_kill_commands"] = entries
        try:
            import json as _json
            from config_manager import CONFIG_FILE, CONFIG_DIR
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(CONFIG_FILE, "w") as f:
                _json.dump(data, f, indent=4)
        except Exception as e:
            QMessageBox.warning(self, tr("killcmd_group"), f"{e}")
            return

        # Kurzes visuelles Feedback am Speichern-Button.
        self.ui.btn_killcmd_save.setText(tr("killcmd_saved"))
        QTimer.singleShot(1500,
            lambda: self.ui.btn_killcmd_save.setText(tr("killcmd_save_btn")))

    # ------------------------------------------------------------------
    #  Mikrofon / Audio-Quelle (Settings): Standard-Source umstellen
    #
    #  Hintergrund: Seit Proton 11 werden virtuelle Mikrofone nicht mehr
    #  sauber an Spiele durchgereicht. Wer per PipeWeaver o.ä. ein virtuelles
    #  Mikrofon baut (z. B. um Spotify/YouTube-Music-Ton an VRChat zu geben),
    #  stellt hier die System-Standard-Aufnahmequelle (default-source) um.
    #  "Setzen"  -> pactl set-default-source <name>
    #  "Zurücksetzen" -> stellt die zuvor gemerkte Original-Quelle wieder her.
    # ------------------------------------------------------------------
    def _mic_state_path(self):
        """Kleine, eigene State-Datei — getrennt von der Haupt-Config, damit
        save_all_settings() sie nicht überschreiben/verlieren kann."""
        from config_manager import CONFIG_DIR
        return os.path.join(CONFIG_DIR, "mic_state.json")

    def _mic_load_original(self):
        """Liefert die gemerkte Original-Default-Source (oder None)."""
        try:
            import json as _json
            with open(self._mic_state_path()) as f:
                return (_json.load(f) or {}).get("original_default_source") or None
        except Exception:
            return None

    def _mic_save_original(self, name):
        """Merkt sich die Original-Default-Source — aber nur EINMAL, damit
        wiederholtes Setzen nicht die echte Ausgangsquelle überschreibt."""
        if self._mic_load_original():
            return  # schon gemerkt, nicht überschreiben
        try:
            import json as _json
            from config_manager import CONFIG_DIR
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(self._mic_state_path(), "w") as f:
                _json.dump({"original_default_source": name}, f, indent=4)
        except Exception as exc:
            log.debug("_mic_save_original: ignoriert — %s", exc)

    def _mic_clear_original(self):
        """Löscht die gemerkte Original-Quelle (nach dem Zurücksetzen)."""
        try:
            os.remove(self._mic_state_path())
        except Exception as exc:
            log.debug("_mic_clear_original: ignoriert — %s", exc)

    def _pactl_available(self):
        from shutil import which
        return which("pactl") is not None

    def _current_default_source(self):
        """Aktuelle Standard-Aufnahmequelle über `pactl get-default-source`."""
        try:
            res = subprocess.run(["pactl", "get-default-source"],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 text=True, timeout=3)
            return res.stdout.strip() or None
        except Exception:
            return None

    # --- Quellen einlesen und lesbar aufbereiten ------------------------
    #
    # `pactl list sources short` liefert nur die rohen Node-Namen
    # ("alsa_output.usb-Generic_USB_Audio-00.HiFi__Speaker__sink.monitor").
    # In einer Liste mit einem Dutzend Eintraegen ist darin nichts zu finden:
    # alle fangen gleich an, der unterscheidende Teil steht in der Mitte, und
    # Mikrofone, virtuelle Quellen und Monitore stehen bunt gemischt.
    #
    # Deshalb wird die LANGE Ausgabe (`pactl list sources`) gelesen. Die
    # enthaelt zu jeder Quelle eine "Description" — den Klartextnamen, den
    # auch die Systemeinstellungen anzeigen. Sortiert wird in drei Gruppen:
    #
    #   Mikrofone          echte Aufnahmegeraete (alsa_input, Bluetooth)
    #   Virtuelle Quellen  z. B. PipeWeaver-Nodes, Null-Sinks
    #   Monitore           Mithoeren einer Ausgabe (.monitor) — selten gemeint,
    #                      steht deshalb unten
    #
    # Der echte Node-Name bleibt als userData am Eintrag haengen (den braucht
    # pactl) und steht zusaetzlich im Tooltip, damit nichts verlorengeht.
    # ------------------------------------------------------------------
    _MIC_KIND_MIC = "mic"
    _MIC_KIND_VIRTUAL = "virtual"
    _MIC_KIND_MONITOR = "monitor"

    def _mic_list_sources(self):
        """[(name, description, kind)] aller Aufnahmequellen.

        LC_ALL=C erzwingt englische Feldnamen — pactl uebersetzt seine
        Ausgabe sonst mit, und "Description:" hiesse auf einem deutschen
        System "Beschreibung:". Ohne das waere die Erkennung sprachabhaengig.
        """
        import re as _re

        env = dict(os.environ, LC_ALL="C", LANG="C")
        try:
            res = subprocess.run(["pactl", "list", "sources"],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 text=True, timeout=5, env=env)
            blocks = _re.split(r"\n(?=Source #)", res.stdout)
        except Exception as exc:
            log.debug("pactl list sources fehlgeschlagen (%s) — nutze Kurzform.", exc)
            blocks = []

        out = []
        for block in blocks:
            # WICHTIG: [^\S\n] statt \s — \s schliesst den Zeilenumbruch ein.
            # Mit \s* wuerde bei einer LEEREN "Description:"-Zeile munter in
            # die naechste Zeile hineingelesen und deren Inhalt ("Monitor of
            # Sink: n/a") als Beschreibung angezeigt.
            m_name = _re.search(r"^[^\S\n]*Name:[^\S\n]*(\S+)[^\S\n]*$", block, _re.M)
            if not m_name:
                continue
            name = m_name.group(1)
            m_desc = _re.search(r"^[^\S\n]*Description:[^\S\n]*(\S.*?)[^\S\n]*$", block, _re.M)
            desc = m_desc.group(1) if m_desc else ""
            m_mon = _re.search(r"^[^\S\n]*Monitor of Sink:[^\S\n]*(\S.*?)[^\S\n]*$", block, _re.M)
            is_monitor = name.endswith(".monitor") or bool(
                m_mon and m_mon.group(1).strip().lower() not in ("n/a", "none", ""))
            out.append((name, desc, self._mic_kind(name, is_monitor)))

        if out:
            return out

        # Rueckfall: die Kurzform kennt keine Beschreibungen, reicht aber, um
        # ueberhaupt etwas anzuzeigen (z. B. wenn die lange Ausgabe scheitert).
        try:
            res = subprocess.run(["pactl", "list", "sources", "short"],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 text=True, timeout=3, env=env)
        except Exception:
            return []
        for line in res.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1].strip():
                name = parts[1].strip()
                out.append((name, "", self._mic_kind(name, name.endswith(".monitor"))))
        return out

    def _mic_kind(self, name, is_monitor):
        """Grobe Einordnung einer Quelle in eine der drei Gruppen.

        Feinheit: Der Monitor eines VIRTUELLEN Sinks (z. B.
        "pipeweaver_system.monitor") landet bewusst bei den virtuellen
        Quellen und nicht unter "Monitore". Wer sich solche Nodes gebaut hat,
        sucht sie beisammen — sie sind der Zweck des Aufbaus, waehrend die
        Monitore der Soundkarte nur Beifang der Geraeteliste sind.
        """
        if is_monitor:
            if name.startswith(("alsa_output.", "bluez_output.", "bluez_sink.")):
                return self._MIC_KIND_MONITOR
            return self._MIC_KIND_VIRTUAL
        if name.startswith(("alsa_input.", "bluez_input.", "bluez_source.")):
            return self._MIC_KIND_MIC
        return self._MIC_KIND_VIRTUAL

    def _mic_label(self, name, desc, kind):
        """Anzeigetext: Klartextname, wenn vorhanden — sonst der gekuerzte
        Node-Name (Hersteller-Praefix und Endung weg)."""
        text = (desc or "").strip()
        if not text:
            short = name
            for prefix in ("alsa_input.", "alsa_output.", "bluez_input.",
                           "bluez_source.", "bluez_output."):
                if short.startswith(prefix):
                    short = short[len(prefix):]
                    break
            if short.endswith(".monitor"):
                short = short[:-len(".monitor")]
            # "usb-Generic_USB_Audio-00.HiFi__Speaker__sink" -> lesbarer machen
            short = short.replace("__", " ").replace("_", " ").replace(".", " · ")
            text = " ".join(short.split())   # Mehrfach-Leerzeichen einsammeln
        if kind == self._MIC_KIND_MONITOR:
            return "🔊 " + text
        if kind == self._MIC_KIND_VIRTUAL:
            return "🎛 " + text
        return "🎤 " + text

    def _mic_add_header(self, combo, text):
        """Nicht waehlbare Gruppenueberschrift in die Liste einhaengen."""
        combo.addItem(text)
        idx = combo.count() - 1
        try:
            item = combo.model().item(idx)
            item.setEnabled(False)          # Qt ueberspringt sie auch per Tastatur
            from PySide6.QtGui import QColor
            item.setForeground(QColor("#7b88a1"))
        except Exception as exc:
            log.debug("_mic_add_header: Kopfzeile nicht formatierbar — %s", exc)

    def refresh_mic_sources(self):
        """Fuellt das Dropdown gruppiert (Mikrofone / Virtuelle / Monitore).
        Die aktive Standard-Quelle wird mit ● markiert und vorausgewaehlt."""
        combo = self.ui.combo_mic_source
        combo.clear()

        if not self._pactl_available():
            self.ui.lbl_mic_status.setText(tr("mic_status_no_pactl"))
            self.ui.btn_mic_set.setEnabled(False)
            self.ui.btn_mic_reset.setEnabled(False)
            return

        self.ui.btn_mic_set.setEnabled(True)
        self.ui.btn_mic_reset.setEnabled(True)

        sources = self._mic_list_sources()
        if not sources:
            self.ui.lbl_mic_status.setText(tr("mic_status_none"))
            return

        current = self._current_default_source()
        groups = [
            (self._MIC_KIND_MIC,     tr("mic_grp_mics")),
            (self._MIC_KIND_VIRTUAL, tr("mic_grp_virtual")),
            (self._MIC_KIND_MONITOR, tr("mic_grp_monitors")),
        ]

        select_index = -1
        first_real = -1
        for kind, title in groups:
            entries = [e for e in sources if e[2] == kind]
            if not entries:
                continue
            self._mic_add_header(combo, title)
            for name, desc, _k in sorted(entries, key=lambda e: (e[1] or e[0]).lower()):
                label = self._mic_label(name, desc, kind)
                if name == current:
                    label = "● " + label
                combo.addItem(label, name)
                idx = combo.count() - 1
                # Roher Node-Name bleibt im Tooltip nachschlagbar
                combo.setItemData(idx, name, Qt.ToolTipRole)
                if first_real < 0:
                    first_real = idx
                if name == current:
                    select_index = idx

        if select_index < 0:
            select_index = first_real
        if select_index >= 0:
            combo.setCurrentIndex(select_index)

        if current:
            self.ui.lbl_mic_status.setText(tr("mic_status_current").format(name=current))
        else:
            self.ui.lbl_mic_status.setText("")

    def apply_mic_source(self):
        """Setzt die im Dropdown gewählte Quelle als System-Standard."""
        if not self._pactl_available():
            self.ui.lbl_mic_status.setText(tr("mic_status_no_pactl"))
            return

        name = self.ui.combo_mic_source.currentData()
        if not name:
            self.ui.lbl_mic_status.setText(tr("mic_status_select"))
            return

        # Vor der Umstellung die aktuelle Default-Source als Original merken
        # (nur beim ersten Mal — siehe _mic_save_original).
        current = self._current_default_source()
        if current and current != name:
            self._mic_save_original(current)

        try:
            res = subprocess.run(["pactl", "set-default-source", name],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, timeout=3)
            if res.returncode != 0:
                err = (res.stderr or "").strip() or f"exit {res.returncode}"
                self.ui.lbl_mic_status.setText(tr("mic_status_error").format(err=err))
                return
        except Exception as e:
            self.ui.lbl_mic_status.setText(tr("mic_status_error").format(err=e))
            return

        self.ui.lbl_mic_status.setText(tr("mic_status_set").format(name=name))
        # Markierung (●) im Dropdown aktualisieren.
        self.refresh_mic_sources()

    def reset_mic_source(self):
        """Stellt die zuvor gemerkte Original-Default-Source wieder her."""
        if not self._pactl_available():
            self.ui.lbl_mic_status.setText(tr("mic_status_no_pactl"))
            return

        original = self._mic_load_original()
        if not original:
            self.ui.lbl_mic_status.setText(tr("mic_status_nothing_saved"))
            return

        try:
            res = subprocess.run(["pactl", "set-default-source", original],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, timeout=3)
            if res.returncode != 0:
                err = (res.stderr or "").strip() or f"exit {res.returncode}"
                self.ui.lbl_mic_status.setText(tr("mic_status_error").format(err=err))
                return
        except Exception as e:
            self.ui.lbl_mic_status.setText(tr("mic_status_error").format(err=e))
            return

        self._mic_clear_original()
        self.ui.lbl_mic_status.setText(tr("mic_status_reset").format(name=original))
        self.refresh_mic_sources()

    def _run_custom_kill_commands(self):
        """Führt die hinterlegten Zusatz-Kill-Befehle als Shell aus (best effort)."""
        try:
            entries = load_saved_settings().get("custom_kill_commands", []) or []
        except Exception:
            entries = []
        for e in entries:
            cmd = e.get("cmd") if isinstance(e, dict) else (e if isinstance(e, str) else "")
            cmd = (cmd or "").strip()
            if not cmd:
                continue
            try:
                # Als Shell starten, aber warten (die Befehle sind typisch schnelle
                # pkill/killall/...); wenn einer hängt, nach 5s aufgeben und weiter.
                subprocess.run(cmd, shell=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=5)
            except subprocess.TimeoutExpired:
                log.info(f"[Autostart] Zusatz-Kill-Befehl brauchte zu lange: {cmd}")
            except Exception as e:
                log.warning(f"[Autostart] Zusatz-Kill-Befehl fehlgeschlagen ({cmd}): {e}")

    def stop_autostart_apps(self):
        """Beendet alle zuvor gestarteten Autostart-Programme (samt Kindprozessen)."""
        # Erst zusätzliche, benutzerdefinierte Kill-Befehle laufen lassen
        # (Sonderfälle wie VRCX/Electron, die den normalen Kill überleben).
        # Der normale Kill unten läuft anschließend wie gewohnt weiter.
        self._run_custom_kill_commands()
        import signal as _signal
        for p in self._autostart_procs:
            try:
                if p.poll() is not None:
                    continue  # läuft nicht mehr
                # Ganze Prozessgruppe beenden (start_new_session -> eigene Gruppe)
                try:
                    os.killpg(os.getpgid(p.pid), _signal.SIGTERM)
                except Exception:
                    p.terminate()
            except Exception as exc:
                log.debug("stop_autostart_apps: ignoriert — %s", exc)
        # kurz warten und notfalls hart beenden
        for p in self._autostart_procs:
            try:
                p.wait(timeout=3)
            except Exception:
                try:
                    os.killpg(os.getpgid(p.pid), _signal.SIGKILL)
                except Exception:
                    try:
                        p.kill()
                    except Exception as exc:
                        log.debug("stop_autostart_apps: ignoriert — %s", exc)
        self._autostart_procs = []

    def start_wivrn_server(self):
        current_settings = load_saved_settings()
        if current_settings.get("first_time_vr_setup", 0) == 0:
            QMessageBox.information(self, tr("firstrun_title"), tr("firstrun_text"))
            # Erst abspeichern...
            save_all_settings(setup_state=1, hand=False, fbt=True, steam=False, refresh="Auto", count="1", apps_data=[])
            # ...und sofort in der laufenden App-Instanz anwenden/nachladen!
            self.apply_loaded_settings()
            create_vr_backup()

        # WICHTIG: Autostart-Apps werden NICHT sofort gestartet, sondern erst
        # sobald der Einweg-Timer (_poll_headset_for_autostart) eine echte
        # Headset-Verbindung erkennt. Sie starten direkt aus dieser Sitzung und
        # erben deren Umgebungsvariablen.
        self.stop_autostart_apps()        # evtl. Reste einer vorherigen Session beenden
        self._headset_connected = False
        self._disconnect_count = 0
        self.arm_autostart_timer()        # Einweg-Timer scharfschalten (wartet auf Headset)

        # Server-Ausgabe in eine Logdatei umleiten (statt DEVNULL), damit das
        # "Client connected"-Ereignis sauber erkannt werden kann. Eine Datei
        # blockiert nicht – anders als eine PIPE, die volllaufen und den Server
        # einfrieren lassen könnte.
        try:
            os.makedirs(os.path.dirname(self._server_log_path), exist_ok=True)
            self._server_log_fh = open(self._server_log_path, "w")
            self.server_process = subprocess.Popen(
                ["wivrn-server"], stdout=self._server_log_fh, stderr=subprocess.STDOUT)
        except Exception as e:
            log.warning(f"[Server] Konnte Logdatei nicht anlegen ({e}) – starte ohne Log.")
            self._server_log_fh = None
            self.server_process = subprocess.Popen(
                ["wivrn-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        log.info("[Autostart] Server gestartet – warte auf Headset-Verbindung, bevor Programme starten...")
        self._server_running = True
        self.update_server_status_ui()
        QTimer.singleShot(500, self.refresh_headset_list)

    def stop_wivrn_server(self):
        self.ui.chk_pairing.setChecked(False)

        # Autostart-Programme beenden und Zustand zurücksetzen
        self.autostart_timer.stop()       # Einweg-Timer entwaffnen
        self.stop_autostart_apps()
        self._headset_connected = False
        self._disconnect_count = 0
        if self._server_log_fh:
            try:
                self._server_log_fh.close()
            except Exception as exc:
                log.debug("stop_wivrn_server: ignoriert — %s", exc)
            self._server_log_fh = None

        if self.server_process: self.server_process.terminate()
        else: proc.run(["pkill", "wivrn-server"], timeout=proc.DEFAULT_TIMEOUT)
        self.server_process = None
        self._server_running = False
        self.update_server_status_ui()
        self.ui.list_headsets.clear()
        self.ui.list_headsets.addItem(tr("dashboard_no_server"))

        # Zweiter (und letzter) Pruefzeitpunkt der Einmal-Automatik: jetzt ist
        # der Server aus, also darf in WiVRns config.json geschrieben werden.
        # Die anderthalb Sekunden geben dem Prozess Zeit, wirklich zu enden —
        # sonst sieht der pgrep im Worker ihn noch und ueberspringt alles.
        QTimer.singleShot(1500, self._start_auto_backup_check)

    def update_server_status_ui(self):
        """Passt die Statusanzeige an den GEMERKTEN Zustand an (kein Subprozess)."""
        if self._server_running:
            self.ui.lbl_status_dot.setStyleSheet("color: #a3be8c; font-size: 24px; margin-left: 10px;")
            self.ui.lbl_status_text.setText(tr("dashboard_active"))
            self.ui.lbl_status_text.setStyleSheet("font-weight: bold; color: #a3be8c;")
        else:
            self.ui.lbl_status_dot.setStyleSheet("color: #bf616a; font-size: 24px; margin-left: 10px;")
            self.ui.lbl_status_text.setText(tr("dashboard_inactive"))
            self.ui.lbl_status_text.setStyleSheet("font-weight: bold; color: #7b88a1;")

    def on_server_toggled(self, checked):
        """Reagiert auf eine ECHTE Nutzer-Betätigung des Schalters."""
        if self._syncing_toggle:
            return  # Schalter wird nur an die Realität angeglichen — nicht handeln
        if checked:
            self.start_wivrn_server()
        else:
            self.stop_wivrn_server()

    def _set_toggle_silently(self, running):
        """Stellt den Schalter ohne Auslösen von start/stop auf den Zustand ein."""
        self._syncing_toggle = True
        self.ui.toggle_server.setChecked(running)
        self.ui.toggle_server.sync_offset()
        self._syncing_toggle = False

    # Alle Hintergrund-Threads, die beim Schliessen noch laufen koennen.
    # Wird ein QThread zerstoert, waehrend er laeuft, beendet Qt den Prozess
    # hart mit SIGABRT ("QThread: Destroyed while thread is still running") —
    # der Nutzer sieht dann beim Schliessen einen Absturz statt eines sauberen
    # Beendens, und ungespeicherte Einstellungen koennen verloren gehen.
    #
    # Neue Worker bitte HIER eintragen. Der Smoke-Test wuerde ein Versaeumnis
    # zwar bemerken (er endet dann mit Exitcode 134), aber erst nachtraeglich.
    _BACKGROUND_WORKERS = (
        "_cover_worker",            # Spiel-Cover vom Steam-CDN
        "_pkgcheck_worker",         # Paketstatus im Installations-Tab
        "_games_scan_worker",       # Steam-Bibliothek scannen
        "_tools_status_worker",     # Statusabfrage der Tools
        "_app_update_check_worker", # Versions-Check auf GitHub
        "_app_update_worker",       # Selbst-Update
        "_auto_backup_worker",      # automatisches Erst-Backup
        "_oxr_health_worker",       # OpenXR-Manifest-Pruefung
        "_pp_worker",               # ProtonPlus-Installation
        "_games_db_worker",         # Spiele-Datenbank
        "tool_worker",              # Tool-Installation
        "apk_worker",               # WiVRn-APK per adb
        "_usb_worker",              # USB-Ampel im Dashboard
    )

    def closeEvent(self, event):
        """Beim Schliessen alle Hintergrund-Threads geordnet beenden."""
        # Zuerst die Timer anhalten: ein Tick waehrend des Aufraeumens wuerde
        # einen frischen Worker starten, auf den niemand mehr wartet.
        self.usb_poll_timer.stop()
        self.autostart_timer.stop()

        for name in self._BACKGROUND_WORKERS:
            worker = getattr(self, name, None)
            if worker is None:
                continue
            try:
                if not worker.isRunning():
                    continue
                # stop()/cancel() gibt es nur bei manchen Workern — wo
                # vorhanden, beendet es die Schleife im Thread vorzeitig.
                for stopper in ("stop", "cancel"):
                    if hasattr(worker, stopper):
                        getattr(worker, stopper)()
                        break
                if not worker.wait(3000):
                    # Nach 3 s nicht fertig: nicht ewig blockieren, aber
                    # protokollieren — sonst haengt das Fenster beim Schliessen.
                    log.warning("Thread %s reagiert nicht — wird abgebrochen.", name)
                    worker.terminate()
                    worker.wait(1000)
            except Exception as exc:
                log.debug("closeEvent (%s): ignoriert — %s", name, exc)

        super().closeEvent(event)

    def manual_server_check(self):
        """Prüft auf Knopfdruck (oder beim Start) einmalig den echten Server-Zustand
        und gleicht Schalter + Anzeige daran an."""
        running = (self.server_process and self.server_process.poll() is None) or \
            proc.run(["pgrep", "wivrn-server"], stdout=subprocess.DEVNULL, timeout=proc.DEFAULT_TIMEOUT).returncode == 0
        self._server_running = running
        self._set_toggle_silently(running)
        self.update_server_status_ui()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VRApp()
    window.show()
    sys.exit(app.exec())
