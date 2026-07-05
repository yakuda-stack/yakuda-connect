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
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices

# Community-Links (Settings -> "Community & Updates")
DISCORD_URL = "https://discord.gg/X5TaN4A47h"
PAYPAL_URL  = "https://paypal.me/riesensika"

# Korrektur des Pfads für das UI, da main.py jetzt in core/ liegt
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui.ui_main import Ui_MainWindow

# Interne Importe (liegen im selben Ordner 'core')
from install_worker import (InstallWorker, UpdateWorker,
                            AppUpdateCheckWorker, AppUpdateWorker)
from appimage_installer import AppImageInstallWorker
import appimage_installer as appimg
import vr_environment as venv
from config_manager import load_saved_settings, save_all_settings
from streaming_tab import StreamingTab
from backup_manager import (create_vr_backup, restore_vr_environment,
                            auto_backup_on_start)
from overlay_manager import (DesignInstallWorker, set_slimevr_ui,
                             is_slimevr_active, is_design_installed,
                             reset_wayvr_to_default)
from programs import INSTALL_PACKAGES, INSTALL_FLATPAK, TOOLS_APPS, TOOLS_OSC
import openxr_manager as oxr
from translations import tr, set_language, get_language
from PySide6.QtCore import QThread, Signal as QtSignal


class ToolsStatusWorker(QThread):
    """Prüft den Status aller Tools im Hintergrund — ein Signal pro Tool (voller Bericht)."""
    result_signal = QtSignal(str, object)  # key, status-dict

    def __init__(self, tools: dict):
        super().__init__()
        self.tools = tools  # {key: tool_dict}

    def run(self):
        import appimage_installer as appimg
        for key, tool in self.tools.items():
            try:
                status = appimg.compute_status(tool)
            except Exception:
                status = {}
            self.result_signal.emit(key, status)


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

        self.APP_VERSION = "v1.0.8-alpha"
        self.server_process = None
        self.pairing_process = None
        self._overlay_worker = None

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

        self.is_loading = True  # Verhindert das Speichern während des Ladens

        self.required_packages = INSTALL_PACKAGES

        # Paket-Status-Labels werden methoden-abhängig erzeugt (_rebuild_package_rows)
        self.prog_labels = {}

        self.init_logic_connections()
        self._rebuild_package_rows()
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
        if available:
            self.ui.btn_app_update.setToolTip(
                tr("app_update_tooltip").format(version=self._app_remote_version))
            self.ui.btn_app_update.setVisible(True)
        else:
            self.ui.btn_app_update.setVisible(False)

    def start_app_self_update(self):
        """Klick auf den Pfeil: nachfragen, dann install.sh im Terminal ausführen."""
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
            except Exception:
                pass
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

    def open_paypal_link(self):
        QDesktopServices.openUrl(QUrl(PAYPAL_URL))

    # ------------------------------------------------------------------ #
    #  Automatisches Erst-Backup beim Start (siehe backup_manager.py)
    # ------------------------------------------------------------------ #
    def _start_auto_backup_check(self):
        """Startet den stillen Auto-Backup-Check im Hintergrund-Thread."""
        class _AutoBackupWorker(QThread):
            done = QtSignal(bool)

            def run(self):
                try:
                    created = auto_backup_on_start()
                except Exception as e:
                    print(f"[Backup] Auto-Backup-Check fehlgeschlagen: {e}")
                    created = False
                self.done.emit(bool(created))

        self._auto_backup_worker = _AutoBackupWorker()
        self._auto_backup_worker.done.connect(self._on_auto_backup_done)
        self._auto_backup_worker.start()

    def _on_auto_backup_done(self, created):
        if created:
            print("[Backup] Automatisches Erst-Backup der VR-Umgebung wurde angelegt.")

    # ------------------------------------------------------------------ #
    #  OpenXR-Runtime (Steam-Fix): automatischer Fix + manueller Bereich
    # ------------------------------------------------------------------ #
    def refresh_openxr_status(self):
        """Zeigt an, ob die active_runtime.json ok / kaputt / nicht vorhanden ist."""
        try:
            state, _detail = oxr.current_status()
        except Exception:
            state = "missing"
        if state == "ok":
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

    def toggle_openxr_manual(self):
        """Klappt den manuellen Fix-Bereich ein/aus."""
        visible = not self.ui.openxr_manual_widget.isVisible()
        self.ui.openxr_manual_widget.setVisible(visible)
        self.ui.btn_openxr_manual_toggle.setText(
            tr("openxr_manual_hide") if visible else tr("openxr_manual_show"))

    def init_logic_connections(self):
        """Verknüpft die UI-Komponenten aus ui_main.py mit den Logik-Funktionen."""
        # Navigation
        self.ui.sidebar.currentRowChanged.connect(self.on_tab_changed)

        # Installation / Update
        self.ui.btn_install.clicked.connect(self.start_package_installation)
        self.ui.btn_update.clicked.connect(self.start_system_update)
        self._populate_install_method_combo()
        self.ui.combo_install_method.currentIndexChanged.connect(self._on_install_method_changed)
        # NixOS: ggf. auf Flatpak hinweisen / Flathub einrichten (nach Fensterstart)
        QTimer.singleShot(400, self._maybe_offer_nixos_flatpak)
        self.ui.btn_vr_backup.clicked.connect(self.trigger_vr_backup)
        self.ui.btn_vr_restore.clicked.connect(self.trigger_vr_restore)
        self.ui.btn_overlay_design.clicked.connect(self.start_overlay_design)
        self.ui.btn_overlay_reset.clicked.connect(self.reset_overlay_design)
        self.ui.chk_overlay_slimevr.toggled.connect(self.toggle_overlay_slimevr)
        self.ui.btn_openxr_copy_path.clicked.connect(self.copy_openxr_path)
        self.ui.btn_openxr_copy_content.clicked.connect(self.copy_openxr_content)
        # OpenXR: automatischer Fix + Ein-/Ausklappen des manuellen Bereichs
        self.ui.btn_openxr_fix.clicked.connect(self.apply_openxr_fix_clicked)
        self.ui.btn_openxr_manual_toggle.clicked.connect(self.toggle_openxr_manual)
        # Community & Updates (Settings, ganz oben)
        self.ui.btn_community_check.clicked.connect(self.manual_check_app_update)
        self.ui.btn_community_discord.clicked.connect(self.open_discord_link)
        self.ui.btn_community_donate.clicked.connect(self.open_paypal_link)
        self.refresh_overlay_state()
        self.fill_openxr_fields()
        self.refresh_openxr_status()

        # Dashboard Steuerung — Schiebeschalter statt Start/Stop-Buttons
        self.ui.toggle_server.toggled.connect(self.on_server_toggled)
        self.ui.btn_server_check.clicked.connect(self.manual_server_check)
        self.ui.btn_port_status.clicked.connect(self.open_port_9757_firewall)
        self.ui.combo_language.currentIndexChanged.connect(self.on_language_changed)
        # Selbst-Update: kleiner Pfeil neben der App-Version
        self.ui.btn_app_update.clicked.connect(self.start_app_self_update)

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
        # Manueller Reset des Einweg-Autostart-Timers
        self.ui.btn_autostart_reset.clicked.connect(self.reset_autostart_readiness)
        # Besen-Button: laufende Autostart-Apps sofort beenden
        self.ui.btn_autostart_kill.clicked.connect(self.kill_autostart_apps)

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

        # Tools Tab — Buttons verknüpfen (Dispatcher: Installieren/Aktualisieren/Löschen)
        for key, card in self.ui.tool_cards.items():
            card["btn_install"].clicked.connect(
                lambda checked=False, k=key: self.on_tool_action(k)
            )
            self._populate_method_combo(card)
        self.ui.btn_tools_check.clicked.connect(self.start_tools_update_check)

        # Settings Tab
        self.ui.btn_vrchat_symlink.clicked.connect(self.create_vrchat_symlink)

    def get_wivrn_version(self):
        # Flatpak: Version aus 'flatpak info' lesen
        if self._install_method() == "flatpak" and INSTALL_FLATPAK:
            ok, ver = appimg.flatpak_query({"flatpak_id": INSTALL_FLATPAK[0]})
            if ok:
                return ver or "Flatpak"
        try:
            res = subprocess.run(["wivrn-server", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                version_match = re.search(r'[\d\.]+', res.stdout)
                return version_match.group(0) if version_match else "Unbekannt"
        except:
            pass
        return tr("tools_not_installed")

    def _runtime_installed(self):
        """Ist die WiVRn-Runtime für die aktuell gewählte Methode installiert?"""
        method = self._install_method()
        if not method:
            return False
        if method == "flatpak":
            if not INSTALL_FLATPAK:
                return False
            ok, _ = appimg.flatpak_query({"flatpak_id": INSTALL_FLATPAK[0]})
            return ok
        if method == "native":
            return shutil.which("wivrn-server") is not None
        # yay/paru: WiVRn/Monado-Pakete vorhanden?
        if not shutil.which(method):
            return False
        for pkg in INSTALL_PACKAGES.get("WiVRn / Monado", []):
            res = subprocess.run(f"{method} -Q {pkg}", shell=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
                card["lbl_status"].setText("Unbekannt — bitte Update-Check starten")
                card["lbl_status"].setStyleSheet("color: #7b88a1; font-size: 12px; font-style: italic;")
                card["lbl_version"].setText("")
                card["lbl_update"].setText("")
                card["btn_install"].setText(tr("tools_install_btn"))
                card["btn_install"].setEnabled(bool(card.get("methods")))
                card["cmd_widget"].setVisible(False)
                card["status"] = {}
            else:
                self._render_tool_card(key, entry)

    def _render_tool_card(self, key, status):
        """Zentrale UI-Logik einer Tool-Karte aus dem Status-Dict."""
        card = self.ui.tool_cards.get(key)
        if not card:
            return
        if not isinstance(status, dict):
            status = {}
        card["status"] = status

        appimage_inst = status.get("appimage_installed", False)
        appimage_ver  = status.get("appimage_version", "")
        appimage_upd  = status.get("appimage_has_update", False)
        pm_inst       = status.get("pm_installed", False)
        pm_helper     = status.get("pm_helper", "")
        pm_ver        = status.get("pm_version", "")
        pm_upd        = status.get("pm_has_update", False)
        flatpak_inst  = status.get("flatpak_installed", False)
        flatpak_ver   = status.get("flatpak_version", "")
        config_ok     = status.get("config_present", False)

        methods = card.get("methods") or []
        combo = card.get("combo_method")

        btn = card["btn_install"]
        st = card["lbl_status"]

        # Dropdown nur zeigen, wenn Auswahl besteht UND noch installiert/aktualisiert werden kann
        show_combo = (combo is not None and len(methods) >= 2
                      and not appimage_inst and not pm_inst and not flatpak_inst)
        if combo is not None:
            combo.setVisible(show_combo)

        if appimage_inst:
            card["lbl_version"].setText(appimage_ver or "")
            st.setText(tr("tools_appimage_ok"))
            st.setStyleSheet("color: #a3be8c; font-size: 12px; font-weight: bold;")
            card["cmd_widget"].setVisible(True)
            if appimage_upd:
                card["lbl_update"].setText(tr("tools_update"))
                btn.setText(tr("tools_update_btn"))   # ⬆ Aktualisieren
            else:
                card["lbl_update"].setText("")
                btn.setText(tr("tools_delete"))         # 🗑 Löschen
            btn.setEnabled(True)

        elif pm_inst:
            card["lbl_version"].setText(f"v{pm_ver}" if pm_ver else "")
            card["lbl_update"].setText("⬆ Update verfügbar" if pm_upd else "")
            st.setText(tr("tools_pm_ok").format(helper=pm_helper))
            st.setStyleSheet("color: #a3be8c; font-size: 12px; font-weight: bold;")
            btn.setText(tr("tools_already"))
            btn.setEnabled(False)
            card["cmd_widget"].setVisible(True)

        elif flatpak_inst:
            card["lbl_version"].setText(flatpak_ver or "")
            card["lbl_update"].setText("")
            st.setText(tr("tools_flatpak_ok"))
            st.setStyleSheet("color: #a3be8c; font-size: 12px; font-weight: bold;")
            btn.setText(tr("tools_already"))
            btn.setEnabled(False)
            card["cmd_widget"].setVisible(True)

        elif config_ok:
            card["lbl_version"].setText("")
            card["lbl_update"].setText("")
            st.setText(tr("tools_native"))
            st.setStyleSheet("color: #ebcb8b; font-size: 12px; font-weight: bold;")
            btn.setText(tr("tools_install_btn"))
            btn.setEnabled(bool(methods))
            card["cmd_widget"].setVisible(True)

        else:
            card["lbl_version"].setText("")
            card["lbl_update"].setText("")
            if methods:
                st.setText(tr("tools_not_installed"))
                st.setStyleSheet("color: #7b88a1; font-size: 12px; font-style: italic;")
                btn.setText(tr("tools_install_btn"))
                btn.setEnabled(True)
            else:
                # keine Methode verfügbar (z. B. AUR-Tool ohne yay/paru / nicht Arch)
                st.setText(tr("tools_no_method"))
                st.setStyleSheet("color: #bf616a; font-size: 12px; font-style: italic;")
                btn.setText(tr("tools_install_btn"))
                btn.setEnabled(False)
            card["cmd_widget"].setVisible(False)

    def _apply_tool_status(self, key, status):
        """Vom Worker pro Tool aufgerufen: Cache aktualisieren + rendern."""
        card = self.ui.tool_cards.get(key)
        if not card:
            return
        if not isinstance(status, dict):
            status = {}
        cache = self._load_programs_cache()
        cache[key] = status
        self._save_programs_cache(cache)
        self._render_tool_card(key, status)

    def start_tools_update_check(self):
        """Startet den echten Versions-Check im Hintergrund."""
        import time
        if hasattr(self, '_tools_status_worker') and self._tools_status_worker is not None:
            if self._tools_status_worker.isRunning():
                return  # Läuft bereits
        self._last_tools_check_ts = time.time()

        self.ui.btn_tools_check.setEnabled(False)
        self.ui.btn_tools_check.setText("⏳ Prüfe...")

        for key, card in self.ui.tool_cards.items():
            card["lbl_status"].setText("Prüfe...")
            card["lbl_status"].setStyleSheet("color: #ebcb8b; font-size: 12px; font-style: italic;")

        tools = {key: card.get("tool", {"pkg": card["pkg"]})
                 for key, card in self.ui.tool_cards.items()}
        self._tools_status_worker = ToolsStatusWorker(tools)
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

    def _populate_method_combo(self, card):
        """Füllt das Methoden-Dropdown einer Karte (AppImage/yay/paru) und wählt vor."""
        tool = card.get("tool", {})
        combo = card.get("combo_method")
        if combo is None:
            return
        methods = appimg.detect_install_methods(tool)
        card["methods"] = methods
        labels = {"appimage": "AppImage", "yay": "yay", "paru": "paru",
                  "flatpak": "Flatpak"}
        combo.blockSignals(True)
        combo.clear()
        for mthd in methods:
            combo.addItem(labels.get(mthd, mthd), mthd)
        default = appimg.default_method(methods)
        if default:
            idx = combo.findData(default)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        combo.blockSignals(False)
        combo.setVisible(len(methods) >= 2)

    def _selected_method(self, card):
        """Aktuell im Dropdown gewählte Methode (oder die einzige verfügbare)."""
        combo = card.get("combo_method")
        methods = card.get("methods") or appimg.detect_install_methods(card.get("tool", {}))
        if combo is not None and combo.count() > 0:
            data = combo.currentData()
            if data:
                return data
        return appimg.default_method(methods)

    def on_tool_action(self, key):
        """Dispatcher des Karten-Buttons: Installieren / Aktualisieren / Löschen."""
        card = self.ui.tool_cards.get(key)
        if not card:
            return
        status = card.get("status", {}) or {}
        # AppImage installiert + kein Update -> Löschen
        if status.get("appimage_installed") and not status.get("appimage_has_update"):
            self.delete_tool(key)
        else:
            # sonst Installieren bzw. Aktualisieren (per gewählter Methode)
            self.install_tool(key)

    def install_tool(self, key):
        """Installiert/aktualisiert ein Tool — per gewählter Methode (AppImage/yay/paru)."""
        card = self.ui.tool_cards.get(key)
        if not card:
            return
        tool = card.get("tool", {})
        status = card.get("status", {}) or {}
        method = self._selected_method(card)
        if not method:
            QMessageBox.information(self, tool.get("name", key), tr("tools_no_method"))
            return

        updating = bool(status.get("appimage_installed") and status.get("appimage_has_update"))

        # AppImage, aber Config-Ordner schon vorhanden -> vorher warnen (Konflikte vermeiden)
        if method == "appimage" and status.get("config_present") and not status.get("appimage_installed"):
            name = tool.get("name", key)
            hint = appimg.config_path_hint(tool)
            path = f" ({hint})" if hint else ""
            reply = QMessageBox.question(
                self, tr("tools_native_title"),
                tr("tools_native_text").format(name=name, path=path),
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                self._render_tool_card(key, status)
                return

        card["btn_install"].setEnabled(False)
        card["btn_install"].setText(tr("tools_updating") if updating else tr("tools_installing"))
        card["lbl_status"].setText("⏳ ...")
        card["lbl_status"].setStyleSheet("color: #ebcb8b; font-size: 12px;")

        if method == "appimage":
            self.tool_worker = AppImageInstallWorker(tool)
            self.tool_worker.status_signal.connect(
                lambda msg, k=key: self._set_tool_status(k, msg)
            )
            self.tool_worker.finished_signal.connect(
                lambda success, k=key: self.on_tool_installed(k, success)
            )
            self.tool_worker.start()
        elif method == "flatpak":
            self.tool_worker = InstallWorker([tool.get("flatpak_id", "")], helper="flatpak")
            self.tool_worker.finished_signal.connect(
                lambda success, k=key: self.on_tool_installed(k, success)
            )
            self.tool_worker.start()
        else:
            # method ist 'yay' oder 'paru'
            self.tool_worker = InstallWorker([card["pkg"]], helper=method)
            self.tool_worker.finished_signal.connect(
                lambda success, k=key: self.on_tool_installed(k, success)
            )
            self.tool_worker.start()

    def delete_tool(self, key):
        """Entfernt eine AppImage-Installation; fragt zusätzlich nach dem Config-Ordner."""
        card = self.ui.tool_cards.get(key)
        if not card:
            return
        tool = card.get("tool", {})
        name = tool.get("name", key)
        hint = appimg.config_path_hint(tool)
        path = f" ({hint})" if hint else ""

        # Vor dem Löschen fragen, ob auch der Konfigurationsordner mit entfernt werden soll
        also_config = False
        if tool.get("config_dirs"):
            reply = QMessageBox.question(
                self, tr("tools_delete_config_title"),
                tr("tools_delete_config_text").format(name=name, path=path),
                QMessageBox.Yes | QMessageBox.No
            )
            also_config = (reply == QMessageBox.Yes)

        card["btn_install"].setEnabled(False)
        card["btn_install"].setText(tr("tools_deleting"))

        # AppImage, Symlink und Desktop-Eintrag immer entfernen
        try:
            appimg.uninstall(tool)
        except Exception as e:
            print(f"[AppImage] Löschen fehlgeschlagen: {e}")

        # Config-Ordner nur auf Wunsch
        if also_config:
            try:
                appimg.delete_config(tool)
            except Exception as e:
                print(f"[AppImage] Config-Löschen fehlgeschlagen: {e}")

        # Status frisch berechnen und anzeigen
        self._refresh_single_tool(key)

    def _refresh_single_tool(self, key):
        """Berechnet den Status eines einzelnen Tools neu (lokal/PM) und rendert ihn."""
        card = self.ui.tool_cards.get(key)
        if not card:
            return
        tool = card.get("tool", {})
        try:
            status = appimg.compute_status(tool)
        except Exception:
            status = {}
        self._apply_tool_status(key, status)

    def _set_tool_status(self, key, msg):
        """Live-Statustext einer Tool-Karte aktualisieren (AppImage-Fortschritt)."""
        card = self.ui.tool_cards.get(key)
        if not card:
            return
        card["lbl_status"].setText(msg)
        card["lbl_status"].setStyleSheet("color: #ebcb8b; font-size: 12px;")

    def on_tool_installed(self, key, success):
        """Callback nach abgeschlossener Tool-Installation/-Aktualisierung."""
        card = self.ui.tool_cards.get(key)
        if not card:
            return
        if success:
            self._refresh_single_tool(key)
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

        # App-Versions-Label + Update-Pfeil-Tooltip an die Sprache anpassen
        self._refresh_app_version_label()

        # Status-Label der OpenXR-Box neu setzen
        self.refresh_openxr_status()

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

        # Tool-Karten: Beschreibung neu setzen, Status/Buttons aus dem Cache rendern
        for key, card in self.ui.tool_cards.items():
            tool = all_tools.get(key, {})
            if "lbl_desc" in card:
                desc = tool.get("desc_eng", tool.get("desc", "")) if lang == "en" else tool.get("desc", "")
                card["lbl_desc"].setText(desc)
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
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
            )
            if res.returncode == 0:
                p = res.stdout.strip()
                # xdg gibt das Home zurück, wenn nichts konfiguriert ist → das ignorieren
                if p and pathlib.Path(p) != home:
                    return pathlib.Path(p)
        except Exception:
            pass

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

        home = pathlib.Path.home()
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
            self.ui.lbl_vrchat_status.setText(f"Fehler beim Anlegen des Proton-Ordners: {e}")
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

    def _package_groups_for(self, method):
        """Welche Status-Zeilen je Methode? Flatpak/Nativ = nur 'WiVRn'."""
        if method == "flatpak":
            return {"WiVRn": list(INSTALL_FLATPAK)}
        if method == "native":
            return {"WiVRn": ["wivrn-server"]}
        return dict(INSTALL_PACKAGES)

    def _rebuild_package_rows(self):
        """Baut die Status-Zeilen im Installations-Tab passend zur gewählten Methode neu auf."""
        layout = self.ui.pkg_layout
        while layout.rowCount():
            layout.removeRow(0)
        self.prog_labels = {}
        for name in self._package_groups_for(self._install_method()).keys():
            lbl = QLabel("…")
            self.prog_labels[name] = lbl
            layout.addRow(QLabel(f"{name}:"), lbl)

    def _on_install_method_changed(self, *args):
        """Dropdown gewechselt -> Zeilen neu aufbauen und Status prüfen."""
        self._rebuild_package_rows()
        self.check_system_packages()

    def check_system_packages(self):
        method = self._install_method()
        groups = self._package_groups_for(method)
        updates_available = False

        for name, idents in groups.items():
            if name not in self.prog_labels:
                continue
            installed = True
            has_update = False

            if method == "flatpak":
                for fid in idents:
                    ok, _ = appimg.flatpak_query({"flatpak_id": fid})
                    if not ok:
                        installed = False
            elif method == "native":
                # Selbst installiert -> nur prüfen, ob die Binary da ist; kein Update-Check
                installed = shutil.which("wivrn-server") is not None
            else:
                if not shutil.which(method):
                    installed = False
                else:
                    for pkg in idents:
                        res_check = subprocess.run(f"{method} -Q {pkg}", shell=True,
                                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        if res_check.returncode != 0:
                            installed = False
                        else:
                            res_update = subprocess.run(f"{method} -Qu {pkg}", shell=True,
                                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            if res_update.returncode == 0:
                                has_update = True
                                updates_available = True

            if installed:
                if has_update:
                    self.prog_labels[name].setText(tr("pkg_installed") + " (Update available)")
                    self.prog_labels[name].setStyleSheet("color: #d08770; font-weight: bold;")
                else:
                    self.prog_labels[name].setText(tr("pkg_installed"))
                    self.prog_labels[name].setStyleSheet("color: #a3be8c; font-weight: bold;")
            else:
                self.prog_labels[name].setText(tr("pkg_incomplete"))
                self.prog_labels[name].setStyleSheet("color: #ebcb8b; font-weight: bold;")

        self.ui.lbl_wivrn_ver.setText(f"<b>WiVRn Version:</b> {self.get_wivrn_version()}")
        if updates_available:
            self.ui.lbl_worker_status.setText(tr("install_updates_available"))
        else:
            self.ui.lbl_worker_status.setText(tr("install_check_done"))
        # Aktualisieren-Knopf je nach Methode (bei 'native' deaktiviert)
        self._update_update_button()

    def _maybe_offer_nixos_flatpak(self):
        """Auf NixOS: Flatpak erklären bzw. Flathub-Remote per Klick einrichten."""
        try:
            if not appimg.is_nixos():
                return
            if not appimg.flatpak_available():
                # Flatpak gar nicht aktiv -> Anleitung zeigen (Rebuild nötig, kein Klick möglich)
                QMessageBox.information(self, tr("nixos_title"), tr("nixos_no_flatpak_text"))
                return
            if not appimg.flathub_remote_present():
                # Flatpak da, aber Flathub fehlt -> direkt anbieten einzurichten
                reply = QMessageBox.question(
                    self, tr("nixos_add_flathub_title"), tr("nixos_add_flathub_text"),
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    if appimg.add_flathub_remote():
                        QMessageBox.information(self, tr("nixos_title"), tr("nixos_flathub_ok"))
                        self._populate_install_method_combo()
                        self._rebuild_package_rows()
                        self.check_system_packages()
                    else:
                        QMessageBox.warning(self, tr("nixos_title"), tr("nixos_flathub_fail"))
        except Exception as e:
            print(f"[NixOS-Check] {e}")

    def _populate_install_method_combo(self):
        """Füllt das Methoden-Dropdown des Installations-Tabs (yay/paru/flatpak)."""
        combo = getattr(self.ui, "combo_install_method", None)
        methods = appimg.available_update_methods()
        self._install_methods = methods
        if combo is None:
            return
        labels = {"yay": "yay", "paru": "paru", "flatpak": "Flatpak", "native": "Nativ"}
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

    def _update_update_button(self):
        """Aktualisieren-Knopf: aktiv nur, wenn es eine Methode gibt und sie NICHT 'native' ist."""
        methods = getattr(self, "_install_methods", None) or appimg.available_update_methods()
        enable = bool(methods) and self._install_method() != "native"
        self.ui.btn_update.setEnabled(enable)

    def _install_method(self):
        """Aktuell gewählte Methode des Installations-Tabs."""
        combo = getattr(self.ui, "combo_install_method", None)
        methods = getattr(self, "_install_methods", None) or appimg.available_update_methods()
        if combo is not None and combo.count() > 0:
            data = combo.currentData()
            if data:
                return data
        return appimg.default_update_method(methods)

    def start_system_update(self):
        """Update-Knopf: führt ein Ökosystem-Update über die gewählte Methode aus."""
        method = self._install_method()
        if method == "native":
            QMessageBox.information(self, tr("native_update_title"), tr("native_update_text"))
            return
        if not method:
            self.ui.lbl_worker_status.setText("Keine Update-Methode verfügbar (yay/paru/flatpak).")
            return
        self.ui.btn_install.setEnabled(False)
        self.ui.btn_update.setEnabled(False)
        self.update_worker = UpdateWorker(method)
        self.update_worker.status_signal.connect(self.ui.lbl_worker_status.setText)
        self.update_worker.finished_signal.connect(self.on_installation_finished)
        self.update_worker.start()

    def start_package_installation(self):
        """Install-Knopf: installiert die WiVRn-Runtime über die gewählte Methode."""
        method = self._install_method()
        if method == "native":
            QMessageBox.information(self, tr("native_install_title"), tr("native_install_text"))
            return
        if not method:
            self.ui.lbl_worker_status.setText("Keine Installationsmethode verfügbar (yay/paru/flatpak).")
            return

        if method in ("yay", "paru"):
            # nur fehlende AUR-Pakete installieren
            packages_to_process = []
            for prog_name, pkgs in self.required_packages.items():
                for pkg in pkgs:
                    result = subprocess.run(f"{method} -Q {pkg}", shell=True,
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if result.returncode != 0:
                        packages_to_process.append(pkg)
            if not packages_to_process:
                self.ui.lbl_worker_status.setText(tr("install_check_done"))
                return
            worker_pkgs, helper = packages_to_process, method
        else:  # flatpak
            worker_pkgs, helper = list(INSTALL_FLATPAK), "flatpak"

        self.ui.btn_install.setEnabled(False)
        self.ui.btn_update.setEnabled(False)

        self._last_install_method = method
        self.worker = InstallWorker(worker_pkgs, helper=helper)
        self.worker.status_signal.connect(self.ui.lbl_worker_status.setText)
        self.worker.finished_signal.connect(self.on_installation_finished)
        self.worker.start()

    def on_installation_finished(self, success):
        self.ui.btn_install.setEnabled(True)
        self._update_update_button()
        # Methode der Runtime-Installation in der Config merken (für flatpak-Pfade)
        m = getattr(self, "_last_install_method", "")
        if success and m:
            venv.set_runtime_method(m)
            # Flatpak: Ordner (config/openxr/openvr) entstehen erst beim ersten Start
            if m == "flatpak":
                self._offer_wivrn_first_run()
        self.check_system_packages()
        if not self.are_critical_packages_missing(): self.ui.sidebar.setCurrentRow(1)

    def _offer_wivrn_first_run(self):
        """Nach Flatpak-Installation: Hinweis + Angebot, WiVRn einmal zu starten."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle(tr("flatpak_firstrun_title"))
        box.setText(tr("flatpak_firstrun_text"))
        launch_btn = box.addButton(tr("flatpak_firstrun_launch"), QMessageBox.AcceptRole)
        box.addButton(tr("flatpak_firstrun_later"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() == launch_btn:
            try:
                subprocess.Popen(["flatpak", "run", venv.WIVRN_FLATPAK_ID])
            except Exception as e:
                QMessageBox.warning(self, tr("error"),
                                    tr("flatpak_firstrun_launch_fail") + str(e))

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
            subprocess.run(["pgrep", "wivrn-server"], stdout=subprocess.DEVNULL).returncode == 0
        if not server_running:
            self.autostart_timer.stop()
            return

        if self.is_headset_connected():
            print("[Autostart] Headset verbunden – starte Programme aus der Sitzung.")
            self.launch_autostart_apps()
            self._autostart_launched = True
            self._headset_connected = True
            # Selbst-Beendigung: ab hier kein Polling mehr.
            self.autostart_timer.stop()
            print("[Autostart] Programme gestartet – Timer beendet (kein weiteres Polling).")

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
            print("[Autostart] Keine Programme konfiguriert – Timer bleibt aus.")
            return
        if not self.autostart_timer.isActive():
            self.autostart_timer.start()
        print("[Autostart] Bereitschaft scharf – warte auf Headset-Verbindung.")

    def reset_autostart_readiness(self):
        """
        Manueller Reset über den Dashboard-Button: schaltet den Einweg-Timer
        erneut scharf, OHNE den Server neu zu starten. Bereits laufende
        Autostart-Programme werden vorher beendet, damit es beim nächsten
        Verbinden keine doppelten Instanzen gibt.
        """
        server_running = (self.server_process and self.server_process.poll() is None) or \
            subprocess.run(["pgrep", "wivrn-server"], stdout=subprocess.DEVNULL).returncode == 0
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
        print("[Autostart] Laufende Programme manuell beendet (Besen-Button).")

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
            print(f"[Server] Konnte Logdatei nicht anlegen ({e}) – starte ohne Log.")
            self._server_log_fh = None
            self.server_process = subprocess.Popen(
                ["wivrn-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        print("[Autostart] Server gestartet – warte auf Headset-Verbindung, bevor Programme starten...")
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
            except Exception:
                pass
            self._server_log_fh = None

        if self.server_process: self.server_process.terminate()
        else: subprocess.run(["pkill", "wivrn-server"])
        self.server_process = None
        self._server_running = False
        self.update_server_status_ui()
        self.ui.list_headsets.clear()
        self.ui.list_headsets.addItem(tr("dashboard_no_server"))

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

    def manual_server_check(self):
        """Prüft auf Knopfdruck (oder beim Start) einmalig den echten Server-Zustand
        und gleicht Schalter + Anzeige daran an."""
        running = (self.server_process and self.server_process.poll() is None) or \
            subprocess.run(["pgrep", "wivrn-server"], stdout=subprocess.DEVNULL).returncode == 0
        self._server_running = running
        self._set_toggle_silently(running)
        self.update_server_status_ui()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VRApp()
    window.show()
    sys.exit(app.exec())
