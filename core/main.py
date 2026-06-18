#!/usr/bin/env python3
import sys
import subprocess
import shutil
import re
import os
import json
from PySide6.QtWidgets import (QApplication, QMainWindow, QLabel, QMessageBox,
                               QHBoxLayout, QVBoxLayout, QComboBox, QLineEdit,
                               QPushButton, QFileDialog)
from PySide6.QtCore import Qt, QTimer

# Korrektur des Pfads für das UI, da main.py jetzt in core/ liegt
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui.ui_main import Ui_MainWindow

# Interne Importe (liegen im selben Ordner 'core')
from install_worker import InstallWorker
from config_manager import load_saved_settings, save_all_settings
from streaming_tab import StreamingTab
from backup_manager import create_vr_backup, restore_vr_environment
from overlay_manager import (DesignInstallWorker, set_slimevr_ui,
                             is_slimevr_active, is_design_installed,
                             reset_wayvr_to_default)
from programs import INSTALL_PACKAGES, TOOLS_APPS, TOOLS_OSC
import openxr_manager as oxr
from translations import tr, set_language, get_language
from PySide6.QtCore import QThread, Signal as QtSignal


class ToolsStatusWorker(QThread):
    """Prüft den Installationsstatus aller Tools im Hintergrund — ein Signal pro Tool."""
    result_signal = QtSignal(str, bool, str, bool)  # key, installed, version, has_update

    def __init__(self, packages: dict):
        super().__init__()
        self.packages = packages  # {key: pkg_name}

    def run(self):
        for key, pkg in self.packages.items():
            res = subprocess.run(
                f"yay -Q {pkg}", shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
            )
            installed = res.returncode == 0
            version = ""
            has_update = False
            if installed:
                version = res.stdout.strip().split()[-1] if res.stdout.strip() else ""
                res_upd = subprocess.run(
                    f"yay -Qu {pkg}", shell=True,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
                )
                has_update = res_upd.returncode == 0 and bool(res_upd.stdout.strip())
            self.result_signal.emit(key, installed, version, has_update)


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
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

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
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            if res.returncode == 0:
                self.status_signal.emit(f"✔ WiVRn {tag} successfully installed!")
                self.finished_signal.emit(True)
            else:
                self.status_signal.emit(f"Error during adb install going to tools and install android tools:\n{res.stderr.strip()}")
                self.finished_signal.emit(False)

        except Exception as e:
            self.status_signal.emit(f"Fehler: {e}")
            self.finished_signal.emit(False)


class VRApp(QMainWindow):
    def __init__(self):
        super().__init__()
        #loading initliserung
        self.is_loading = True
        # UI Instanziieren und anwenden
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # === ORDNERSTRUKTUR FIX ===
        PROJEKT_CONFIG_DIR = os.path.expanduser("~/.config/yakuda-connect/config")
        os.makedirs(PROJEKT_CONFIG_DIR, exist_ok=True)
        print(f"[System] Folder structure checked/created under: {PROJEKT_CONFIG_DIR}")

        self.APP_VERSION = "v1.0.2-alpha"
        self.server_process = None
        self.pairing_process = None
        self._overlay_worker = None

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

        self.is_loading = True  # Verhindert das Speichern während des Ladens

        self.required_packages = INSTALL_PACKAGES

        # Dynamische Erstellung der Paket-Status-Labels im UI
        self.prog_labels = {}
        for prog_name in self.required_packages.keys():
            self.prog_labels[prog_name] = QLabel("Check status...")
            self.ui.pkg_layout.addRow(QLabel(f"{prog_name}:"), self.prog_labels[prog_name])

        self.init_logic_connections()
        self.check_system_packages()

        # Start-Tab Sperren-Logik (Lock)
        if self.are_critical_packages_missing():
            self.ui.sidebar.setCurrentRow(0)
            QMessageBox.warning(
                self,
                "Components are missing",
                "Please install the required system components first to enable the dashboard!"
            )
        else:
            self.ui.sidebar.setCurrentRow(1)

        # Live-Timer für Server-Status
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_server_status_ui)
        self.status_timer.timeout.connect(self.check_headset_autostart)
        self.status_timer.start(1000)

        self.apply_loaded_settings()
        self.is_loading = False

# Erststart- / Willkommenstext für den Nutzer setzen
        self._set_welcome_text()

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

    def init_logic_connections(self):
        """Verknüpft die UI-Komponenten aus ui_main.py mit den Logik-Funktionen."""
        # Navigation
        self.ui.sidebar.currentRowChanged.connect(self.on_tab_changed)

        # Installation / Update
        self.ui.btn_install.clicked.connect(self.start_package_installation)
        self.ui.btn_update.clicked.connect(self.start_package_installation)
        self.ui.btn_vr_backup.clicked.connect(self.trigger_vr_backup)
        self.ui.btn_vr_restore.clicked.connect(self.trigger_vr_restore)
        self.ui.btn_overlay_design.clicked.connect(self.start_overlay_design)
        self.ui.btn_overlay_reset.clicked.connect(self.reset_overlay_design)
        self.ui.chk_overlay_slimevr.toggled.connect(self.toggle_overlay_slimevr)
        self.ui.btn_openxr_copy_path.clicked.connect(self.copy_openxr_path)
        self.ui.btn_openxr_copy_content.clicked.connect(self.copy_openxr_content)
        self.refresh_overlay_state()
        self.fill_openxr_fields()

        # Dashboard Steuerung
        self.ui.btn_start.clicked.connect(self.start_wivrn_server)
        self.ui.btn_stop.clicked.connect(self.stop_wivrn_server)
        self.ui.btn_port_status.clicked.connect(self.open_port_9757_firewall)
        self.ui.combo_language.currentIndexChanged.connect(self.on_language_changed)

        # APK Installation
        self.ui.btn_apk_install.clicked.connect(self.start_apk_install)
        self.ui.btn_apk_cancel.clicked.connect(self.cancel_apk_install)
        self._apk_worker = None

        # Autosave Trigger
        self.ui.chk_hand_tracking.clicked.connect(self.trigger_auto_save)
        self.ui.chk_fbt.clicked.connect(self.trigger_auto_save)
        self.ui.chk_steamvr_tracker.clicked.connect(self.trigger_auto_save)
        self.ui.combo_refresh.activated.connect(self.trigger_auto_save)
        self.ui.chk_pairing.toggled.connect(self.toggle_pairing_mode)

        # Autostart Zeilen-Generierung
        self.ui.num_apps.returnPressed.connect(self.update_autostart_fields)
        self.ui.num_apps.editingFinished.connect(self.update_autostart_fields)

        # Headset Management
        self.ui.btn_refresh_list.clicked.connect(self.refresh_headset_list)
        self.ui.btn_remove_headset.clicked.connect(self.remove_selected_headset)
        self.ui.btn_disconnect_headset.clicked.connect(self.disconnect_current_headset)

        self.autostart_rows = []
        self.update_autostart_fields()

        # Streaming Tab dynamisch einbetten
        stream_layout = QVBoxLayout(self.ui.tab_streaming)
        stream_layout.setContentsMargins(0, 0, 0, 0)
        self.streaming_settings = StreamingTab(self)
        stream_layout.addWidget(self.streaming_settings)

        # Tools Tab — Install-Buttons verknüpfen
        for key, card in self.ui.tool_cards.items():
            card["btn_install"].clicked.connect(
                lambda checked=False, k=key: self.install_tool(k)
            )
        self.ui.btn_tools_check.clicked.connect(self.start_tools_update_check)

        # Settings Tab
        self.ui.btn_vrchat_symlink.clicked.connect(self.create_vrchat_symlink)

    def get_wivrn_version(self):
        try:
            res = subprocess.run(["wivrn-server", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                version_match = re.search(r'[\d\.]+', res.stdout)
                return version_match.group(0) if version_match else "Unbekannt"
        except:
            pass
        return tr("tools_not_installed")

    def are_critical_packages_missing(self):
        if not shutil.which("yay"): return True
        for prog_name, pkgs in self.required_packages.items():
            for pkg in pkgs:
                res = subprocess.run(f"yay -Q {pkg}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if res.returncode != 0: return True
        return False

    def on_tab_changed(self, index):
        if index != 0 and self.are_critical_packages_missing():
            self.ui.sidebar.blockSignals(True)
            self.ui.sidebar.setCurrentRow(0)
            self.ui.pages.setCurrentIndex(0)
            self.ui.sidebar.blockSignals(False)
            QMessageBox.critical(self, "Zugriff verweigert", "Du kannst andere Funktionen erst nutzen, wenn alle Komponenten installiert sind!")
            return
        self.ui.pages.setCurrentIndex(index)
        if index == 1: self.refresh_headset_list()
        if index == 3: self.check_tools_status()

    def check_tools_status(self):
        """Lädt den Status aus dem Cache (programs.json) und zeigt ihn sofort an."""
        cache = self._load_programs_cache()
        for key, card in self.ui.tool_cards.items():
            entry = cache.get(key)
            if entry is None:
                # Noch nie geprüft
                card["lbl_status"].setText("Unbekannt — bitte Update-Check starten")
                card["lbl_status"].setStyleSheet("color: #7b88a1; font-size: 12px; font-style: italic;")
                card["lbl_version"].setText("")
                card["lbl_update"].setText("")
                card["btn_install"].setText(tr("tools_install_btn"))
                card["btn_install"].setEnabled(True)
                card["cmd_widget"].setVisible(False)
            elif entry.get("installed"):
                card["lbl_version"].setText(f"v{entry.get('version', '')}")
                card["lbl_update"].setText("⬆ Update verfügbar" if entry.get("has_update") else "")
                card["lbl_status"].setText(tr("pkg_installed"))
                card["lbl_status"].setStyleSheet("color: #a3be8c; font-size: 12px; font-weight: bold;")
                card["btn_install"].setText(tr("tools_already"))
                card["btn_install"].setEnabled(False)
                card["cmd_widget"].setVisible(True)
            else:
                card["lbl_version"].setText("")
                card["lbl_update"].setText("")
                card["lbl_status"].setText(tr("tools_not_installed"))
                card["lbl_status"].setStyleSheet("color: #7b88a1; font-size: 12px; font-style: italic;")
                card["btn_install"].setText(tr("tools_install_btn"))
                card["btn_install"].setEnabled(True)
                card["cmd_widget"].setVisible(False)

    def _apply_tool_status(self, key, installed, version, has_update):
        """Wird vom Worker pro Tool aufgerufen, aktualisiert UI und Cache."""
        card = self.ui.tool_cards.get(key)
        if not card:
            return

        # Cache aktualisieren
        cache = self._load_programs_cache()
        cache[key] = {
            "installed":  installed,
            "version":    version,
            "has_update": has_update,
        }
        self._save_programs_cache(cache)

        # UI aktualisieren
        if installed:
            card["lbl_version"].setText(f"v{version}")
            card["lbl_update"].setText("⬆ Update verfügbar" if has_update else "")
            card["lbl_status"].setText(tr("pkg_installed"))
            card["lbl_status"].setStyleSheet("color: #a3be8c; font-size: 12px; font-weight: bold;")
            card["btn_install"].setText(tr("tools_already"))
            card["btn_install"].setEnabled(False)
            card["cmd_widget"].setVisible(True)
        else:
            card["lbl_version"].setText("")
            card["lbl_update"].setText("")
            card["lbl_status"].setText(tr("tools_not_installed"))
            card["lbl_status"].setStyleSheet("color: #7b88a1; font-size: 12px; font-style: italic;")
            card["btn_install"].setText(tr("tools_install_btn"))
            card["btn_install"].setEnabled(True)
            card["cmd_widget"].setVisible(False)

    def start_tools_update_check(self):
        """Startet den echten Versions-Check im Hintergrund (nur auf Knopfdruck)."""
        if hasattr(self, '_tools_status_worker') and self._tools_status_worker is not None:
            if self._tools_status_worker.isRunning():
                return  # Läuft bereits

        self.ui.btn_tools_check.setEnabled(False)
        self.ui.btn_tools_check.setText("⏳ Prüfe...")

        for key, card in self.ui.tool_cards.items():
            card["lbl_status"].setText("Prüfe...")
            card["lbl_status"].setStyleSheet("color: #ebcb8b; font-size: 12px; font-style: italic;")

        packages = {key: card["pkg"] for key, card in self.ui.tool_cards.items()}
        self._tools_status_worker = ToolsStatusWorker(packages)
        self._tools_status_worker.result_signal.connect(self._apply_tool_status)
        self._tools_status_worker.finished.connect(self._on_tools_check_done)
        self._tools_status_worker.start()

    def _on_tools_check_done(self):
        self.ui.btn_tools_check.setEnabled(True)
        self.ui.btn_tools_check.setText("🔄 Nach Updates suchen")
        self._tools_status_worker = None

    def _load_programs_cache(self) -> dict:
        path = os.path.expanduser("~/.config/yakuda-connect/config/programs.json")
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_programs_cache(self, data: dict):
        path = os.path.expanduser("~/.config/yakuda-connect/config/programs.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[Cache] Konnte programs.json nicht schreiben: {e}")

    def install_tool(self, key):
        """Startet die Installation eines Tools über den InstallWorker."""
        card = self.ui.tool_cards.get(key)
        if not card:
            return
        card["btn_install"].setEnabled(False)
        card["btn_install"].setText(tr("tools_installing"))
        card["lbl_status"].setText("⏳ Installiere...")
        card["lbl_status"].setStyleSheet("color: #ebcb8b; font-size: 12px;")

        self.tool_worker = InstallWorker([card["pkg"]])
        self.tool_worker.finished_signal.connect(
            lambda success, k=key: self.on_tool_installed(k, success)
        )
        self.tool_worker.start()

    def on_tool_installed(self, key, success):
        """Callback nach abgeschlossener Tool-Installation."""
        card = self.ui.tool_cards.get(key)
        if not card:
            return
        if success:
            card["lbl_status"].setText(tr("pkg_installed"))
            card["lbl_status"].setStyleSheet("color: #a3be8c; font-size: 12px; font-weight: bold;")
            card["btn_install"].setText(tr("tools_already"))
            card["btn_install"].setEnabled(False)
            card["cmd_widget"].setVisible(True)
            # Nach WayVR-Installation: Hinweis auf das bessere UI-Design in den Settings
            if key == "wayvr":
                QMessageBox.information(self, tr("overlay_popup_title"), tr("overlay_popup_text"))
        else:
            card["lbl_status"].setText(tr("tools_install_error"))
            card["lbl_status"].setStyleSheet("color: #bf616a; font-size: 12px;")
            card["btn_install"].setText(tr("tools_retry"))
            card["btn_install"].setEnabled(True)

    # ----------------------------------------------------------------------- #
    #  WayVR Overlay (UI-Design)
    # ----------------------------------------------------------------------- #
    def start_overlay_design(self):
        """Lädt das WayVR-Design herunter und aktiviert das Performance-Overlay."""
        if self._overlay_worker and self._overlay_worker.isRunning():
            return
        self.ui.btn_overlay_design.setEnabled(False)
        self.ui.btn_overlay_reset.setEnabled(False)
        self.ui.chk_overlay_slimevr.setEnabled(False)
        self.ui.btn_overlay_design.setText(tr("overlay_installing"))

        self._overlay_worker = DesignInstallWorker()
        self._overlay_worker.finished_signal.connect(self._on_overlay_design_done)
        self._overlay_worker.start()

    def _on_overlay_design_done(self, success, err):
        self.ui.btn_overlay_design.setEnabled(True)
        self.ui.btn_overlay_reset.setEnabled(True)
        self.ui.btn_overlay_design.setText(tr("overlay_design_btn"))
        if success:
            QMessageBox.information(self, tr("success"), tr("overlay_design_ok"))
        else:
            QMessageBox.critical(self, tr("error"), tr("overlay_design_err") + "\n\n" + (err or ""))
        # Checkbox-Zustand an die nun installierte watch.xml angleichen
        self.refresh_overlay_state()

    def reset_overlay_design(self):
        """Setzt WayVR auf Standard zurück (Design deinstallieren)."""
        reply = QMessageBox.question(
            self, tr("overlay_reset_confirm_title"), tr("overlay_reset_confirm_text"),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        ok, msg = reset_wayvr_to_default()
        if ok:
            QMessageBox.information(self, tr("success"), tr("overlay_reset_ok"))
        else:
            QMessageBox.critical(self, tr("error"), tr("overlay_reset_err") + "\n\n" + str(msg))
        self.refresh_overlay_state()

    def toggle_overlay_slimevr(self, checked):
        """Schaltet die SlimeVR-Reset-Buttons an/aus (Performance-Overlay bleibt)."""
        ok, msg = set_slimevr_ui(checked)
        if ok:
            key = "overlay_slimevr_ok" if checked else "overlay_slimevr_off"
            QMessageBox.information(self, tr("success"), tr(key))
            return
        # Fehlschlag -> Checkbox ohne erneutes Auslösen zurücksetzen
        self.ui.chk_overlay_slimevr.blockSignals(True)
        self.ui.chk_overlay_slimevr.setChecked(not checked)
        self.ui.chk_overlay_slimevr.blockSignals(False)
        if msg == "no_design":
            QMessageBox.warning(self, tr("error"), tr("overlay_need_design"))
        else:
            QMessageBox.critical(self, tr("error"), tr("overlay_slimevr_err") + "\n\n" + str(msg))

    def refresh_overlay_state(self):
        """Spiegelt den tatsächlichen watch.xml-Zustand in die UI (ohne Signale auszulösen)."""
        design = is_design_installed()
        self.ui.chk_overlay_slimevr.setEnabled(design)
        self.ui.chk_overlay_slimevr.blockSignals(True)
        self.ui.chk_overlay_slimevr.setChecked(design and is_slimevr_active())
        self.ui.chk_overlay_slimevr.blockSignals(False)

    def fill_openxr_fields(self):
        """Füllt das Pfad-Feld und das Inhalt-Feld für die manuelle OpenXR-Reparatur."""
        try:
            self.ui.txt_openxr_path.setText(oxr.ACTIVE_RUNTIME)
            openxr_so, monado_so = oxr.find_wivrn_libs()
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
        except Exception:
            pass

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
        self.ui.lbl_apk_status.setText("Starte...")
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
        path = os.path.expanduser("~/.config/yakuda-connect/config/config.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=4)

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
                    lbl.setText(tr("pkg_installed") + " (Update available)" if lang == "en" else tr("pkg_installed") + " (Update verfügbar)")
                elif "✔" in text:
                    lbl.setText(tr("pkg_installed"))
                elif "⚠" in text:
                    lbl.setText(tr("pkg_incomplete"))

        # Tool-Karten (Beschreibung + Status sind zustandsabhängig)
        for key, card in self.ui.tool_cards.items():
            tool = all_tools.get(key, {})
            if "lbl_desc" in card:
                desc = tool.get("desc_eng", tool.get("desc", "")) if lang == "en" else tool.get("desc", "")
                card["lbl_desc"].setText(desc)
            status = card["lbl_status"].text()
            if any(x in status for x in ["Installiert", "Installed", "✔"]):
                card["lbl_status"].setText(tr("tools_installed"))
                card["btn_install"].setText(tr("tools_already"))
            elif any(x in status for x in ["Unbekannt", "Unknown"]):
                card["lbl_status"].setText(tr("tools_unknown"))
            elif any(x in status for x in ["Nicht install", "Not install"]):
                card["lbl_status"].setText(tr("tools_not_installed"))
                card["btn_install"].setText(tr("tools_install_btn"))

    def create_vrchat_symlink(self):
        """Erstellt einen Symlink vom VRChat Proton-Bilderordner zum Linux Pictures-Ordner."""
        import pathlib

        vrchat_proton_path = pathlib.Path.home() / \
            ".local/share/Steam/steamapps/compatdata/438100/pfx/drive_c/users/steamuser/Pictures"
        linux_pictures = pathlib.Path.home() / "Pictures" / "VRChat"

        # Prüfen ob Proton-Pfad existiert
        if not vrchat_proton_path.exists():
            self.ui.lbl_vrchat_status.setText(
                "⚠ VRChat Proton-Ordner nicht gefunden.\n"
                "Starte VRChat mindestens einmal bevor du den Symlink erstellst."
            )
            self.ui.lbl_vrchat_status.setStyleSheet("color: #ebcb8b; font-size: 11px;")
            return

        # Schon ein Symlink?
        if linux_pictures.is_symlink():
            self.ui.lbl_vrchat_status.setText(
                f"✔ Symlink existiert bereits:\n{linux_pictures} → {vrchat_proton_path}"
            )
            self.ui.lbl_vrchat_status.setStyleSheet("color: #a3be8c; font-size: 11px;")
            return

        # Pictures-Ordner als echter Ordner vorhanden → umbenennen
        if linux_pictures.exists():
            backup = linux_pictures.with_name("VRChat_backup")
            linux_pictures.rename(backup)

        try:
            linux_pictures.parent.mkdir(parents=True, exist_ok=True)
            linux_pictures.symlink_to(vrchat_proton_path)
            self.ui.lbl_vrchat_status.setText(
                f"✔ Symlink erfolgreich erstellt!\n{linux_pictures} → {vrchat_proton_path}"
            )
            self.ui.lbl_vrchat_status.setStyleSheet("color: #a3be8c; font-size: 11px;")
            self.ui.btn_vrchat_symlink.setText("✔ Done")
            self.ui.btn_vrchat_symlink.setEnabled(False)
        except Exception as e:
            self.ui.lbl_vrchat_status.setText(f"Fehler: {e}")
            self.ui.lbl_vrchat_status.setStyleSheet("color: #bf616a; font-size: 11px;")

    def trigger_vr_backup(self):
        if create_vr_backup():
            QMessageBox.information(self, "Backup erfolgreich", "Die VR-Umgebung wurde erfolgreich gesichert!")
        else:
            QMessageBox.critical(self, "Fehler", "Das Backup konnte nicht erstellt werden.")

    def trigger_vr_restore(self):
        # FIX: 'self' übergeben, da die Funktion das Parent-Fenster für die Dialoge braucht
        restore_vr_environment(self)

    def check_system_packages(self):
        updates_available = False
        if not shutil.which("yay"): return

        for prog_name, pkgs in self.required_packages.items():
            if prog_name not in self.prog_labels: continue
            prog_installed = True
            prog_has_update = False

            for pkg in pkgs:
                res_check = subprocess.run(f"yay -Q {pkg}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if res_check.returncode != 0: prog_installed = False
                else:
                    res_update = subprocess.run(f"yay -Qu {pkg}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if res_update.returncode == 0:
                        prog_has_update = True
                        updates_available = True

            if prog_installed:
                if prog_has_update:
                    self.prog_labels[prog_name].setText(tr("pkg_installed") + " (Update available)")
                    self.prog_labels[prog_name].setStyleSheet("color: #d08770; font-weight: bold;")
                else:
                    self.prog_labels[prog_name].setText(tr("pkg_installed"))
                    self.prog_labels[prog_name].setStyleSheet("color: #a3be8c; font-weight: bold;")
            else:
                self.prog_labels[prog_name].setText(tr("pkg_incomplete"))
                self.prog_labels[prog_name].setStyleSheet("color: #ebcb8b; font-weight: bold;")

        self.ui.lbl_wivrn_ver.setText(f"<b>WiVRn Version:</b> {self.get_wivrn_version()}")
        if updates_available:
            self.ui.lbl_worker_status.setText(tr("install_updates_available"))
            self.ui.btn_update.setEnabled(True)
        else:
            self.ui.lbl_worker_status.setText(tr("install_check_done"))
            self.ui.btn_update.setEnabled(False)

    def start_package_installation(self):
        packages_to_process = []
        if self.sender() == self.ui.btn_update:
            for pkgs in self.required_packages.values(): packages_to_process.extend(pkgs)
        else:
            for prog_name, pkgs in self.required_packages.items():
                for pkg in pkgs:
                    result = subprocess.run(f"yay -Q {pkg}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if result.returncode != 0: packages_to_process.append(pkg)

        if not packages_to_process: return
        self.ui.btn_install.setEnabled(False)
        self.ui.btn_update.setEnabled(False)

        self.worker = InstallWorker(packages_to_process)
        self.worker.status_signal.connect(self.ui.lbl_worker_status.setText)
        self.worker.finished_signal.connect(self.on_installation_finished)
        self.worker.start()

    def on_installation_finished(self, success):
        self.ui.btn_install.setEnabled(True)
        self.check_system_packages()
        if not self.are_critical_packages_missing(): self.ui.sidebar.setCurrentRow(1)

    def open_port_9757_firewall(self):
        """
        Gibt den WiVRn-Port exakt so frei wie der offizielle WiVRn-Server:
        1. UFW-App-Profil unter /etc/ufw/applications.d/wivrn schreiben
        2. 'ufw allow wivrn' ausführen — identisch zu WiVRns do_setup()
        Fallback: firewall-cmd (Firewalld) für nicht-UFW-Systeme.
        """
        WIVRN_PORT = 9757
        UFW_PROFILE_PATH = "/etc/ufw/applications.d/wivrn"
        UFW_PROFILE_CONTENT = (
            "[WiVRn]\n"
            "title=WiVRn server\n"
            "description=WiVRn OpenXR streaming server\n"
            f"ports={WIVRN_PORT}\n"
        )

        opened_any = False
        errors = []

        if shutil.which("ufw"):
            # Schritt 1: Profildatei schreiben (identisch zu WiVRns C++-Code)
            write_cmd = (
                f"printf '{UFW_PROFILE_CONTENT}' > {UFW_PROFILE_PATH}"
            )
            res_write = subprocess.run(
                ["pkexec", "sh", "-c", write_cmd],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )

            if res_write.returncode != 0:
                errors.append(f"UFW Profil konnte nicht geschrieben werden:\n{res_write.stderr}")
            else:
                # Schritt 2: Port über den Profilnamen freigeben — genau wie WiVRn
                res_allow = subprocess.run(
                    ["pkexec", "ufw", "allow", "wivrn"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                if res_allow.returncode == 0:
                    opened_any = True
                else:
                    errors.append(f"UFW Fehler:\n{res_allow.stderr}")

        elif shutil.which("firewall-cmd"):
            # Firewalld-Fallback (z.B. Fedora/openSUSE)
            res_udp = subprocess.run(
                ["pkexec", "firewall-cmd", "--permanent", f"--add-port={WIVRN_PORT}/udp"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            res_tcp = subprocess.run(
                ["pkexec", "firewall-cmd", "--permanent", f"--add-port={WIVRN_PORT}/tcp"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            if res_udp.returncode == 0 and res_tcp.returncode == 0:
                subprocess.run(["pkexec", "firewall-cmd", "--reload"])
                opened_any = True
            else:
                errors.append(f"Firewalld Fehler:\n{res_udp.stderr}")
        else:
            errors.append("Kein unterstützter Firewall-Manager gefunden (ufw oder firewall-cmd).")

        if opened_any:
            QMessageBox.information(self, "Erfolg", "WiVRn-Firewall-Profil gesetzt und Port freigegeben!")
            self.ui.btn_port_status.setText("✔ Port & Dashboard gefixt")
            self.ui.btn_port_status.setStyleSheet("QPushButton { background-color: #a3be8c; color: #2e3440; font-weight: bold; border-radius: 4px; padding: 6px; margin-top: 5px; }")
        else:
            if errors:
                QMessageBox.warning(self, "Firewall Fehler", "\n".join(errors))

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
                chk_debug.setToolTip("Terminal anzeigen (für OSC-Programme zum Debuggen)")
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
        file_path, _ = QFileDialog.getOpenFileName(self, "Programm auswählen", "/usr/bin", "Alle Dateien (*)")
        if file_path:
            line_edit.setText(file_path)
            self.trigger_auto_save()

    def trigger_auto_save(self):
        if hasattr(self, 'is_loading') and self.is_loading: return
        apps_data = [{
            "type":  r["combo"].currentText(),
            "cmd":   r["input"].text(),
            "debug": r["chk_debug"].isChecked()
        } for r in self.autostart_rows]
        save_all_settings(
            self.ui.chk_hand_tracking.isChecked(),
            self.ui.chk_fbt.isChecked(),
            self.ui.chk_steamvr_tracker.isChecked(),
            self.ui.combo_refresh.currentText(),
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

        self.ui.chk_hand_tracking.blockSignals(True)
        self.ui.chk_fbt.blockSignals(True)
        self.ui.chk_steamvr_tracker.blockSignals(True)
        self.ui.combo_refresh.blockSignals(True)
        self.ui.num_apps.blockSignals(True)

        self.ui.chk_hand_tracking.setChecked(data.get("hand_tracking", False))
        self.ui.chk_fbt.setChecked(data.get("full_body_tracking", True))
        self.ui.chk_steamvr_tracker.setChecked(data.get("steam_tracker", False))
        self.ui.combo_refresh.setCurrentText(data.get("refresh_rate", "Auto"))

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

        self.ui.chk_hand_tracking.blockSignals(False)
        self.ui.chk_fbt.blockSignals(False)
        self.ui.chk_steamvr_tracker.blockSignals(False)
        self.ui.combo_refresh.blockSignals(False)
        self.ui.num_apps.blockSignals(False)

    def refresh_headset_list(self):
        self.ui.list_headsets.clear()
        if subprocess.run(["pgrep", "wivrn-server"], stdout=subprocess.DEVNULL).returncode != 0:
            self.ui.list_headsets.addItem(tr("dashboard_no_server"))
            return
        try:
            res = subprocess.run(["wivrnctl", "list-paired"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                for line in res.stdout.strip().split('\n'):
                    if not line.strip() or "Headset name" in line: continue
                    self.ui.list_headsets.addItem(line.strip())
            if self.ui.list_headsets.count() == 0: self.ui.list_headsets.addItem("Keine gekoppelten Headsets gefunden.")
        except Exception as e: self.ui.list_headsets.addItem(f"Fehler: {e}")

    def remove_selected_headset(self):
        item = self.ui.list_headsets.currentItem()
        if not item or "Keine" in item.text() or "Server" in item.text(): return
        match = re.match(r'^(\d+)', item.text())
        if match and QMessageBox.question(self, "Entkoppeln", f"Headset entkoppeln?\n{item.text()}", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            subprocess.run(["wivrnctl", "unpair", match.group(1)])
            self.refresh_headset_list()

    def disconnect_current_headset(self):
        subprocess.run(["wivrnctl", "disconnect"])
        self.refresh_headset_list()

    def toggle_pairing_mode(self, checked):
        if checked:
            if subprocess.run(["pgrep", "wivrn-server"], stdout=subprocess.DEVNULL).returncode != 0:
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
        except Exception:
            pass

        # Signal B: aktive (ESTABLISHED) TCP-Verbindung auf dem WiVRn-Port 9757.
        try:
            res = subprocess.run(["ss", "-Htan"], stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, text=True, timeout=2)
            for line in res.stdout.splitlines():
                if "ESTAB" in line and ":9757" in line:
                    return True
        except Exception:
            pass

        return False

    def check_headset_autostart(self):
        """
        Läuft im 1-Sekunden-Takt (am Status-Timer) und hält die Autostart-Programme
        an die Headset-Verbindung gekoppelt:
          • Spieler verbindet  -> Programme starten
          • Spieler trennt sich -> Programme beenden (nach kurzer Karenzzeit)
          • Server gestoppt     -> Programme beenden
        """
        # Läuft der Server überhaupt?
        server_running = (self.server_process and self.server_process.poll() is None) or \
            subprocess.run(["pgrep", "wivrn-server"], stdout=subprocess.DEVNULL).returncode == 0
        if not server_running:
            if self._headset_connected or self._autostart_procs:
                print("[Autostart] Server gestoppt – beende Autostart-Programme.")
                self.stop_autostart_apps()
            self._headset_connected = False
            self._disconnect_count = 0
            return

        connected = self.is_headset_connected()

        if connected:
            self._disconnect_count = 0
            if not self._headset_connected:
                # Steigende Flanke: Spieler hat (wieder) verbunden
                self._headset_connected = True
                print("[Autostart] Headset verbunden – starte Autostart-Programme.")
                self.launch_autostart_apps()
        else:
            if self._headset_connected:
                # Erst nach mehreren "getrennt"-Messungen tatsächlich beenden
                self._disconnect_count += 1
                if self._disconnect_count >= self._disconnect_grace:
                    self._headset_connected = False
                    self._disconnect_count = 0
                    print("[Autostart] Headset getrennt – beende Autostart-Programme.")
                    self.stop_autostart_apps()

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
                print(f"[Autostart] Konnte '{cmd}' nicht starten: {e}")

    def stop_autostart_apps(self):
        """Beendet alle zuvor gestarteten Autostart-Programme (samt Kindprozessen)."""
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
            except Exception:
                pass
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
                    except Exception:
                        pass
        self._autostart_procs = []

    def start_wivrn_server(self):
        current_settings = load_saved_settings()
        if current_settings.get("first_time_vr_setup", 0) == 0:
            QMessageBox.information(self, "Erststart", "Proton & WiVRn werden initialisiert. Setze deine Brille auf.")
            # Erst abspeichern...
            save_all_settings(setup_state=1, hand=False, fbt=True, steam=False, refresh="Auto", count="1", apps_data=[])
            # ...und sofort in der laufenden App-Instanz anwenden/nachladen!
            self.apply_loaded_settings()
            create_vr_backup()

        # WICHTIG: Autostart-Apps werden NICHT sofort gestartet, sondern erst
        # sobald check_headset_autostart() eine echte Headset-Verbindung erkennt –
        # und automatisch wieder beendet, wenn der Spieler sich trennt.
        self.stop_autostart_apps()        # evtl. Reste einer vorherigen Session beenden
        self._headset_connected = False
        self._disconnect_count = 0

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
            print(f"[Server] Konnte Logdatei nicht anlegen ({e}) – starte ohne Log.")
            self._server_log_fh = None
            self.server_process = subprocess.Popen(
                ["wivrn-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        print("[Autostart] Server gestartet – warte auf Headset-Verbindung, bevor Programme starten...")
        QTimer.singleShot(500, self.refresh_headset_list)

    def stop_wivrn_server(self):
        self.ui.chk_pairing.setChecked(False)

        # Autostart-Programme beenden und Zustand zurücksetzen
        self.stop_autostart_apps()
        self._headset_connected = False
        self._disconnect_count = 0
        if self._server_log_fh:
            try:
                self._server_log_fh.close()
            except Exception:
                pass
            self._server_log_fh = None

        if self.server_process: self.server_process.terminate()
        else: subprocess.run(["pkill", "wivrn-server"])
        self.ui.list_headsets.clear()
        self.ui.list_headsets.addItem(tr("dashboard_no_server"))

    def update_server_status_ui(self):
        """Überprüft den Server-Status und passt die Button-Styles dynamisch an."""
        server_running = (self.server_process and self.server_process.poll() is None) or subprocess.run(["pgrep", "wivrn-server"], stdout=subprocess.DEVNULL).returncode == 0

        if server_running:
            self.ui.lbl_status_dot.setStyleSheet("color: #a3be8c; font-size: 24px; margin-left: 10px;")
            self.ui.lbl_status_text.setText(tr("dashboard_active"))
            self.ui.lbl_status_text.setStyleSheet("font-weight: bold; color: #a3be8c;")

            # Start-Button deaktivieren & ausgrauen
            self.ui.btn_start.setEnabled(False)
            self.ui.btn_start.setStyleSheet("QPushButton { background-color: #4c566a; color: #7b88a1; font-weight: normal; }")

            # Stop-Button aktivieren & hellblau aufleuchten lassen
            self.ui.btn_stop.setEnabled(True)
            self.ui.btn_stop.setStyleSheet(
                "QPushButton { background-color: #81a1c1; color: #2e3440; font-weight: bold; border-radius: 4px; padding: 6px; }"
                "QPushButton:hover { background-color: #88c0d0; }"
            )
        else:
            self.ui.lbl_status_dot.setStyleSheet("color: #bf616a; font-size: 24px; margin-left: 10px;")
            self.ui.lbl_status_text.setText(tr("dashboard_inactive"))
            self.ui.lbl_status_text.setStyleSheet("font-weight: bold; color: #7b88a1;")

            # Start-Button reaktivieren
            self.ui.btn_start.setEnabled(True)
            self.ui.btn_start.setStyleSheet("") # Nutzt wieder das Standard-Theme-Styling

            # Stop-Button deaktivieren & abdunkeln
            self.ui.btn_stop.setEnabled(False)
            self.ui.btn_stop.setStyleSheet("QPushButton { background-color: #4c566a; color: #7b88a1; font-weight: normal; border-radius: 4px; padding: 6px; }")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VRApp()
    window.show()
    sys.exit(app.exec())
