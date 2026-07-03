#!/usr/bin/env python3
import os
import sys
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
                               QStackedWidget, QLabel, QPushButton, QCheckBox,
                               QComboBox, QLineEdit, QGroupBox, QFormLayout,
                               QSlider, QTextEdit, QFrame)
from PySide6.QtCore import Qt, QPropertyAnimation, Property, QRectF
from PySide6.QtGui import QPainter, QColor


class ToggleSwitch(QCheckBox):
    """Schiebeschalter (links = aus, rechts = an) im Stil eines iOS-Toggles.

    Verhält sich wie eine QCheckBox (isChecked/setChecked/toggled), zeichnet
    sich aber als animierter Schiebeschalter. sync_offset() setzt die
    Knopfposition ohne Animation passend zum aktuellen Zustand — praktisch,
    wenn der Zustand programmatisch gesetzt wird (z. B. beim Server-Check).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(52, 28)
        self._offset = 3.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(150)
        self.toggled.connect(self._on_toggled)

    def _knob_end(self):
        return self.width() - self.height() + 3

    def hitButton(self, pos):
        # Standardmäßig ist eine QCheckBox nur im kleinen Indikator-Bereich
        # klickbar. Wir machen die GESAMTE Fläche des Schalters klickbar.
        return self.rect().contains(pos)

    def _on_toggled(self, checked):
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(self._knob_end() if checked else 3.0)
        self._anim.start()

    def sync_offset(self):
        """Knopf ohne Animation an den aktuellen Zustand angleichen."""
        self._anim.stop()
        self._offset = self._knob_end() if self.isChecked() else 3.0
        self.update()

    def get_offset(self):
        return self._offset

    def set_offset(self, value):
        self._offset = value
        self.update()

    offset = Property(float, get_offset, set_offset)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        radius = self.height() / 2
        track = QColor("#81a1c1") if self.isChecked() else QColor("#4c566a")
        p.setBrush(track)
        p.drawRoundedRect(0, 0, self.width(), self.height(), radius, radius)
        d = self.height() - 6
        p.setBrush(QColor("#eceff4"))
        p.drawEllipse(QRectF(self._offset, 3, d, d))
        p.end()

# Programme aus zentraler Datei laden
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'core')))
from programs import TOOLS_APPS, TOOLS_OSC
from translations import tr, get_language

class Ui_MainWindow(object):
    def setupUi(self, main_window):
        main_window.setWindowTitle("yakuda-connect")

        # Fenster-Icon setzen (ersetzt das "W" in der Titelleiste)
        import os
        from PySide6.QtGui import QIcon
        icon_path = os.path.join(os.path.dirname(__file__), "..", "assets", "yakuda_icon.png")
        if os.path.exists(icon_path):
            main_window.setWindowIcon(QIcon(icon_path))
        main_window.resize(1050, 850)
        main_window.setMinimumSize(800, 600)

        # --- ZENTRALES STYLESHEET FÜR EIN MODERNES DESIGN ---
        main_window.setStyleSheet("""
            QMainWindow {
                background-color: #181a1f;
            }
            QWidget {
                color: #d8dee9;
                font-family: "Segoe UI", "Noto Sans", sans-serif;
            }

            /* Moderne Card-Optik für die GroupBoxen statt harter Rahmen */
            QGroupBox {
                background-color: #21252b;
                border: none;
                border-radius: 10px;
                margin-top: 35px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 0px;
                top: 0px;
                color: #81a1c1;
                font-size: 14px;
                font-weight: bold;
                padding: 5px 10px;
                background-color: transparent;
            }

            /* Buttons modernisieren */
            QPushButton {
                background-color: #3b4252;
                border: 1px solid #434c5e;
                color: #eceff4;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4c566a;
                border: 1px solid #5e81ac;
            }
            QPushButton:pressed {
                background-color: #2e3440;
            }

            /* Eingabefelder und Dropdowns */
            QLineEdit, QComboBox {
                background-color: #1e222a;
                border: 1px solid #3b4252;
                border-radius: 4px;
                padding: 6px;
                color: #eceff4;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #88c0d0;
            }

            /* Checkboxen */
            QCheckBox { spacing: 8px; font-size: 13px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1px solid #434c5e; background-color: #1e222a; }
            QCheckBox::indicator:checked { background-color: #5e81ac; border: 1px solid #81a1c1; }

            /* Scrollbars verstecken/minimalisieren */
            QScrollBar:vertical { width: 10px; background: transparent; }
            QScrollBar::handle:vertical { background: #434c5e; border-radius: 5px; }
        """)

        self.central_widget = QWidget()
        main_window.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Sidebar
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(200)
        from PySide6.QtWidgets import QSizePolicy
        self.sidebar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.sidebar.addItems([
            "Installation",
            "Dashboard",
            "Streaming",
            "Tools",
            "Settings",
        ])

        # Pillen-Design für Sidebar
        self.sidebar.setStyleSheet("""
            QListWidget {
                background-color: #1c1f26;
                border: none;
                outline: none;
                padding-top: 15px;
            }
            QListWidget::item {
                padding: 12px 20px;
                margin: 4px 12px;
                border-radius: 8px;
                color: #a6b2c0;
                font-size: 14px;
                font-weight: 500;
            }
            QListWidget::item:hover:!selected {
                background-color: #282c34;
                color: #d8dee9;
            }
            QListWidget::item:selected {
                background-color: #3b4252;
                color: #88c0d0;
                font-weight: bold;
            }
        """)
        self.main_layout.addWidget(self.sidebar)

        # Content Area
        self.pages = QStackedWidget()
        self.main_layout.addWidget(self.pages)

        self.tab_installation = QWidget()
        self.tab_dashboard = QWidget()
        self.tab_streaming = QWidget()
        self.tab_tools = QWidget()
        self.tab_settings = QWidget()

        self.pages.addWidget(self.tab_installation)    # Index 0
        self.pages.addWidget(self.tab_dashboard)       # Index 1
        self.pages.addWidget(self.tab_streaming)       # Index 2
        self.pages.addWidget(self.tab_tools)           # Index 3
        self.pages.addWidget(self.tab_settings)        # Index 4

        # Initialisiere die einzelnen Bereiche
        self.setup_installation_tab()
        self.setup_dashboard_tab()
        self.setup_tools_tab()
        self.setup_settings_tab()
        # self.setup_streaming_tab() # DEAKTIVIERT: main.py bettet StreamingTab dynamisch ein und erzeugt das Layout selbst!

        # Alle Texte einmal zentral setzen (eine einzige Quelle der Wahrheit)
        self.retranslate_ui()

    def retranslate_ui(self):
        """
        Setzt ALLE statischen, sichtbaren Texte neu aus den Übersetzungen.
        Wird beim Start und bei jedem Sprachwechsel aufgerufen.
        Dynamische Texte (Server-Status, Tool-Status, Versions-Labels) werden
        bewusst NICHT hier angefasst, sondern von ihrer jeweiligen Logik gesetzt.
        """
        # Sidebar
        for i, key in enumerate(["nav_installation", "nav_dashboard",
                                 "nav_streaming", "nav_tools", "nav_settings"]):
            item = self.sidebar.item(i)
            if item:
                item.setText(tr(key))

        # --- Installation-Tab ---
        self.lbl_install_title.setText(tr("install_title"))
        self.pkg_group.setTitle(tr("install_deps_title"))
        self.btn_install.setText(tr("install_btn"))
        self.btn_update.setText(tr("update_btn"))
        self.info_group.setTitle(tr("install_hints_title"))

        # --- Dashboard-Tab ---
        self.server_group.setTitle(tr("dashboard_server"))
        self.btn_server_check.setText(tr("dashboard_check"))
        self.btn_port_status.setText(tr("dashboard_firewall"))
        self.tracking_group.setTitle(tr("dashboard_tracking"))
        self.chk_hand_tracking.setText(tr("dashboard_hand"))
        self.chk_fbt.setText(tr("dashboard_fbt"))
        self.chk_steamvr_tracker.setText(tr("dashboard_steam"))
        self.lbl_tracker_note.setText(tr("dashboard_steam_hint"))
        self.lbl_refresh.setText(tr("dashboard_refresh"))
        self.pairing_group.setTitle(tr("dashboard_pairing"))
        self.chk_pairing.setText(tr("dashboard_pair_chk"))
        self.lbl_pair_code.setText(tr("dashboard_pair_code"))
        self.txt_code.setPlaceholderText(tr("dashboard_pair_gen"))
        self.autostart_group.setTitle(tr("dashboard_autostart"))
        self.lbl_app_count.setText(tr("dashboard_app_count"))
        self.btn_autostart_reset.setText(tr("dashboard_autostart_reset"))
        self.btn_autostart_kill.setText(tr("dashboard_autostart_kill"))
        self.btn_autostart_kill.setToolTip(tr("autostart_kill_tip"))
        self.headset_group.setTitle(tr("dashboard_headsets"))
        self.btn_refresh_list.setText(tr("dashboard_list_btn"))
        self.btn_remove_headset.setText(tr("dashboard_remove_btn"))
        self.btn_disconnect_headset.setText(tr("dashboard_disconnect"))

        # --- Settings-Tab ---
        self.lbl_settings_title.setText(tr("settings_title"))
        self.general_group.setTitle(tr("settings_general"))
        self.lbl_vrchat_title.setText(tr("settings_vrchat_title"))
        self.lbl_vrchat_desc.setText(tr("settings_vrchat_desc_short"))
        self.btn_vrchat_symlink.setText(tr("settings_vrchat_btn"))
        self.lbl_apk_title.setText(tr("dashboard_apk_title"))
        self.apk_info_lbl.setText(tr("dashboard_apk_info"))
        self.btn_apk_install.setText(tr("dashboard_apk_btn"))
        self.btn_apk_cancel.setText(tr("dashboard_apk_cancel"))
        self.backup_group.setTitle(tr("backup_title"))
        self.btn_vr_backup.setText(tr("backup_create_btn"))
        self.btn_vr_restore.setText(tr("backup_restore_btn"))
        self.overlay_group.setTitle(tr("overlay_group"))
        self.btn_overlay_design.setText(tr("overlay_design_btn"))
        self.btn_overlay_reset.setText(tr("overlay_reset_btn"))
        self.chk_overlay_slimevr.setText(tr("overlay_slimevr_btn"))
        self.lbl_overlay_credits.setText(tr("overlay_credits"))
        self.openxr_group.setTitle(tr("openxr_group"))
        self.lbl_openxr_desc.setText(tr("openxr_desc"))
        self.lbl_openxr_path_title.setText(tr("openxr_path_title"))
        self.lbl_openxr_content_title.setText(tr("openxr_content_title"))
        self.btn_openxr_copy_path.setText(tr("openxr_copy_btn"))
        self.btn_openxr_copy_content.setText(tr("openxr_copy_btn"))

        # --- Tools-Tab ---
        self.lbl_tools_title.setText(tr("tools_title"))
        self.lbl_tools_subtitle.setText(tr("tools_subtitle"))
        self.btn_tools_check.setText(tr("tools_check_btn"))
        self.apps_group.setTitle(tr("tools_apps"))
        self.osc_group.setTitle(tr("tools_osc"))
        for card in self.tool_cards.values():
            if "btn_copy" in card:
                card["btn_copy"].setText(tr("tools_copy"))

    def setup_installation_tab(self):
        layout = QVBoxLayout(self.tab_installation)
        layout.setContentsMargins(20, 20, 20, 20)

        self.lbl_install_title = QLabel(tr("install_title"))
        self.lbl_install_title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(self.lbl_install_title)

        self.pkg_group = QGroupBox(tr("install_deps_title"))
        self.pkg_layout = QFormLayout(self.pkg_group)
        layout.addWidget(self.pkg_group)

        btn_layout = QHBoxLayout()
        self.combo_install_method = QComboBox()
        self.combo_install_method.setFixedHeight(30)
        self.combo_install_method.setStyleSheet("""
            QComboBox { background-color: #2e3440; color: #d8dee9; font-size: 11px;
                        border: 1px solid #3b4252; border-radius: 4px; padding: 0px 8px; }
            QComboBox:hover { border-color: #5e81ac; }
            QComboBox QAbstractItemView { background-color: #2e3440; color: #d8dee9;
                        selection-background-color: #5e81ac; }
        """)
        self.combo_install_method.setVisible(False)
        btn_layout.addWidget(self.combo_install_method)

        self.btn_install = QPushButton(tr("install_btn"))
        self.btn_install.setFixedHeight(30)
        self.btn_install.setStyleSheet("""
            QPushButton { background-color: #5e81ac; color: white; font-weight: bold;
                          font-size: 11px; border-radius: 4px; border: none; }
            QPushButton:hover { background-color: #81a1c1; }
        """)
        self.btn_update = QPushButton(tr("update_btn"))
        self.btn_update.setFixedHeight(30)
        self.btn_update.setStyleSheet("""
            QPushButton { background-color: #3b4252; color: #d8dee9; font-weight: bold;
                          font-size: 11px; border-radius: 4px; border: none; }
            QPushButton:hover { background-color: #4c566a; }
        """)
        btn_layout.addWidget(self.btn_install)
        btn_layout.addWidget(self.btn_update)
        layout.addLayout(btn_layout)

        self.lbl_worker_status = QLabel(tr("install_ready"))
        self.lbl_worker_status.setStyleSheet("color: #7b88a1; font-style: italic; margin-top: 5px;")
        layout.addWidget(self.lbl_worker_status)

        layout.addSpacing(20)

# --- INFO-KASTEN (ERWEITERTE HÖHE FÜR VOLLSTÄNDIGEN TEXT) ---
        from PySide6.QtWidgets import QTextEdit

        self.info_group = QGroupBox(tr("install_hints_title"))
        info_layout = QVBoxLayout(self.info_group)
        info_layout.setSpacing(10)

        self.txt_free_info = QTextEdit()
        self.txt_free_info.setReadOnly(True)

        # Auf 350 erhöht, damit die Box groß genug nach unten gezogen wird
        # und alle Punkte (Backups + Performance) gleichzeitig reinpassen!
        self.txt_free_info.setMinimumHeight(400)

        # Scrollbalken rigoros abschalten
        self.txt_free_info.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.txt_free_info.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Cursor-Interaktion deaktivieren
        self.txt_free_info.setTextInteractionFlags(Qt.TextSelectableByMouse)

        # Styling
        self.txt_free_info.setStyleSheet("""
            QTextEdit {
                background-color: #1e222a;
                border: 1px solid #3b4252;
                border-radius: 6px;
                padding: 15px;
                color: #eceff4;
                font-size: 13px;
            }
        """)
        info_layout.addWidget(self.txt_free_info)

        layout.addWidget(self.info_group)
        # ------------------------------------------------------------

        layout.addStretch()
        # ------------------------------------------------------------

        layout.addStretch()



    def setup_dashboard_tab(self):
        from PySide6.QtWidgets import QScrollArea, QSizePolicy

        scroll = QScrollArea(self.tab_dashboard)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        outer = QVBoxLayout(self.tab_dashboard)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)

        version_layout = QHBoxLayout()
        self.lbl_app_ver = QLabel("<b>App Version:</b> v1.0.6-alpha")
        self.lbl_app_ver.setStyleSheet("color: #81a1c1;")
        self.lbl_wivrn_ver = QLabel("<b>WiVRn Version:</b> Prüfe...")
        self.lbl_wivrn_ver.setStyleSheet("color: #81a1c1;")

        self.combo_language = QComboBox()
        self.combo_language.addItems(["🇬🇧 English", "🇩🇪 Deutsch"])
        self.combo_language.setFixedWidth(120)
        self.combo_language.setStyleSheet("""
            QComboBox { background-color: #3b4252; color: #d8dee9; border: 1px solid #4c566a;
                        border-radius: 4px; padding: 2px 6px; font-size: 11px; }
            QComboBox::drop-down { border: none; }
        """)

        # Kleiner Update-Pfeil direkt neben der App-Version.
        # Standardmäßig unsichtbar; main.py blendet ihn nur ein, wenn auf GitHub
        # eine neuere yakuda-connect-Version gefunden wurde. Klick -> Selbst-Update.
        self.btn_app_update = QPushButton("⬆")
        self.btn_app_update.setCursor(Qt.PointingHandCursor)
        self.btn_app_update.setFixedSize(26, 22)
        self.btn_app_update.setVisible(False)
        self.btn_app_update.setStyleSheet("""
            QPushButton {
                background-color: #a3be8c; color: #2e3440;
                border: none; border-radius: 4px;
                font-size: 12px; font-weight: bold; padding: 0px;
            }
            QPushButton:hover  { background-color: #b4cfa0; }
            QPushButton:pressed { background-color: #8faa78; }
            QPushButton:disabled { background-color: #4c566a; color: #7b88a1; }
        """)

        version_layout.addWidget(self.lbl_app_ver)
        version_layout.addWidget(self.btn_app_update)
        version_layout.addStretch()
        version_layout.addWidget(self.combo_language)
        version_layout.addSpacing(12)
        version_layout.addWidget(self.lbl_wivrn_ver)
        layout.addLayout(version_layout)

        self.server_group = QGroupBox(tr("dashboard_server"))
        server_layout = QVBoxLayout(self.server_group)

        # Schiebeschalter Start/Stop (links = aus, rechts = an) + Statusanzeige (oben).
        top_row = QHBoxLayout()
        self.toggle_server = ToggleSwitch()

        self.lbl_status_text = QLabel(tr("dashboard_inactive"))
        self.lbl_status_text.setStyleSheet("font-weight: bold; color: #7b88a1;")
        self.lbl_status_dot = QLabel("●")
        self.lbl_status_dot.setStyleSheet("color: #bf616a; font-size: 24px; margin-left: 10px;")

        top_row.addWidget(self.toggle_server)
        top_row.addSpacing(10)
        top_row.addWidget(self.lbl_status_text)
        top_row.addWidget(self.lbl_status_dot)
        top_row.addStretch()
        server_layout.addLayout(top_row)

        # Untere Reihe: Firewall-Button + Server-Check NEBENEINANDER (aufgeräumter).
        action_row = QHBoxLayout()

        self.btn_port_status = QPushButton(tr("dashboard_firewall"))
        self.btn_port_status.setStyleSheet("""
            QPushButton { background-color: #4c566a; color: #eceff4; border: none; font-weight: bold; border-radius: 4px; padding: 6px; }
            QPushButton:hover { background-color: #5e81ac; }
        """)

        self.btn_server_check = QPushButton(tr("dashboard_check"))
        self.btn_server_check.setStyleSheet("""
            QPushButton { background-color: #434c5e; color: #eceff4; border: none; font-weight: bold; border-radius: 4px; padding: 6px; }
            QPushButton:hover { background-color: #4c566a; }
        """)

        action_row.addWidget(self.btn_port_status)
        action_row.addWidget(self.btn_server_check)
        action_row.addStretch()
        server_layout.addLayout(action_row)
        layout.addWidget(self.server_group)

        # --- APK INSTALLATION ---
        self.tracking_group = QGroupBox(tr("dashboard_tracking"))
        tracking_layout = QVBoxLayout(self.tracking_group)

        self.chk_hand_tracking = QCheckBox(tr("dashboard_hand"))
        self.chk_fbt = QCheckBox(tr("dashboard_fbt"))
        self.chk_fbt.setChecked(True)
        self.chk_steamvr_tracker = QCheckBox(tr("dashboard_steam"))

        self.lbl_tracker_note = QLabel(tr("dashboard_steam_hint"))
        self.lbl_tracker_note.setStyleSheet("color: #d08770; font-style: italic; font-weight: bold; margin-bottom: 5px;")

        refresh_layout = QHBoxLayout()
        self.lbl_refresh = QLabel(tr("dashboard_refresh"))
        self.combo_refresh = QComboBox()
        self.combo_refresh.addItems(["Auto", "72", "90"])
        self.combo_refresh.setFixedWidth(100)
        refresh_layout.addWidget(self.lbl_refresh)
        refresh_layout.addWidget(self.combo_refresh)
        refresh_layout.addStretch()

        tracking_layout.addWidget(self.chk_hand_tracking)
        tracking_layout.addWidget(self.chk_fbt)
        tracking_layout.addWidget(self.chk_steamvr_tracker)
        tracking_layout.addWidget(self.lbl_tracker_note)
        tracking_layout.addLayout(refresh_layout)
        layout.addWidget(self.tracking_group)

        self.pairing_group = QGroupBox(tr("dashboard_pairing"))
        pairing_layout = QHBoxLayout(self.pairing_group)
        self.chk_pairing = QCheckBox(tr("dashboard_pair_chk"))
        self.txt_code = QLineEdit()
        self.txt_code.setPlaceholderText(tr("dashboard_pair_gen"))
        self.txt_code.setFixedWidth(150)
        self.txt_code.setReadOnly(True)

        self.lbl_pair_code = QLabel(tr("dashboard_pair_code"))
        pairing_layout.addWidget(self.chk_pairing)
        pairing_layout.addWidget(self.lbl_pair_code)
        pairing_layout.addWidget(self.txt_code)
        pairing_layout.addStretch()
        layout.addWidget(self.pairing_group)

        self.autostart_group = QGroupBox(tr("dashboard_autostart"))
        autostart_layout = QVBoxLayout(self.autostart_group)

        # Kopfzeile: Label + Zähler links, kompakte Aktions-Buttons rechts.
        count_row = QHBoxLayout()
        self.lbl_app_count = QLabel(tr("dashboard_app_count"))
        self.num_apps = QLineEdit("1")
        self.num_apps.setFixedWidth(50)
        self.num_apps.setAlignment(Qt.AlignCenter)
        count_row.addWidget(self.lbl_app_count)
        count_row.addWidget(self.num_apps)
        count_row.addStretch()

        # Timer neu scharfschalten (kompakt, rechts neben dem Zähler).
        self.btn_autostart_reset = QPushButton(tr("dashboard_autostart_reset"))
        self.btn_autostart_reset.setStyleSheet("""
            QPushButton { background-color: #434c5e; color: #eceff4; border: none; font-weight: bold; border-radius: 4px; padding: 4px 12px; }
            QPushButton:hover { background-color: #5e81ac; }
        """)

        # Besen-Button: laufende Autostart-Apps sofort beenden (Clean-Up).
        self.btn_autostart_kill = QPushButton(tr("dashboard_autostart_kill"))
        self.btn_autostart_kill.setToolTip(tr("autostart_kill_tip"))
        self.btn_autostart_kill.setStyleSheet("""
            QPushButton { background-color: #bf616a; color: #eceff4; border: none; font-weight: bold; border-radius: 4px; padding: 4px 12px; }
            QPushButton:hover { background-color: #d08770; }
        """)

        count_row.addWidget(self.btn_autostart_reset)
        count_row.addWidget(self.btn_autostart_kill)
        autostart_layout.addLayout(count_row)

        self.autostart_container = QWidget()
        self.autostart_container_layout = QVBoxLayout(self.autostart_container)
        self.autostart_container_layout.setContentsMargins(0, 0, 0, 0)
        autostart_layout.addWidget(self.autostart_container)
        layout.addWidget(self.autostart_group)

        self.headset_group = QGroupBox(tr("dashboard_headsets"))
        headset_layout = QHBoxLayout(self.headset_group)

        self.list_headsets = QListWidget()
        self.list_headsets.setMinimumHeight(80)
        self.list_headsets.setStyleSheet("""
            QListWidget { background-color: #1e222a; color: #d8dee9; border: 1px solid #3b4252; border-radius: 4px; }
            QListWidget::item { padding: 6px; border-bottom: 1px solid #2e3440; }
            QListWidget::item:selected { background-color: #3b4252; color: #bf616a; font-weight: bold; }
        """)

        right_btn_layout = QVBoxLayout()
        self.btn_refresh_list = QPushButton(tr("dashboard_list_btn"))
        self.btn_remove_headset = QPushButton(tr("dashboard_remove_btn"))
        self.btn_remove_headset.setStyleSheet("QPushButton { background-color: #bf616a; border: none; color: white; font-weight: bold; } QPushButton:hover { background-color: #d08770; }")
        self.btn_disconnect_headset = QPushButton(tr("dashboard_disconnect"))
        self.btn_disconnect_headset.setStyleSheet("QPushButton { background-color: #d08770; border: none; color: white; font-weight: bold; } QPushButton:hover { background-color: #ebcb8b; color: #2e3440; }")

        right_btn_layout.addWidget(self.btn_refresh_list)
        right_btn_layout.addWidget(self.btn_remove_headset)
        right_btn_layout.addWidget(self.btn_disconnect_headset)
        right_btn_layout.addStretch()

        headset_layout.addWidget(self.list_headsets, 75)
        headset_layout.addLayout(right_btn_layout, 25)
        layout.addWidget(self.headset_group)

        layout.addStretch()

    def setup_streaming_tab(self):
        # Beibehalten der Methode für Abwärtskompatibilität, falls von extern aufgerufen,
        # aber leer gelassen oder nicht in setupUi ausgeführt, damit main.py das Layout setzen kann.
        pass

    def setup_settings_tab(self):
        from PySide6.QtWidgets import QScrollArea

        scroll = QScrollArea(self.tab_settings)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        outer = QVBoxLayout(self.tab_settings)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        self.lbl_settings_title = QLabel(tr("settings_title"))
        self.lbl_settings_title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 5px;")
        layout.addWidget(self.lbl_settings_title)

        # --- GENERAL (zwei Boxen nebeneinander) ---
        self.general_group = QGroupBox(tr("settings_general"))
        general_layout = QVBoxLayout(self.general_group)
        general_layout.setSpacing(10)

        # Horizontale Reihe: links APK-Box, rechts VRChat-Box
        general_row = QHBoxLayout()
        general_row.setSpacing(16)

        # Gemeinsamer Card-Stil (passt zum restlichen Design)
        _card_css = """
            QFrame#settingsCard {
                background-color: #21252b;
                border: 1px solid #2e3440;
                border-radius: 6px;
            }
        """

        # ---------- LINKS: WiVRn APK-Installation ----------
        apk_card = QFrame()
        apk_card.setObjectName("settingsCard")
        apk_card.setStyleSheet(_card_css)
        apk_box = QVBoxLayout(apk_card)
        apk_box.setContentsMargins(12, 12, 12, 12)
        apk_box.setSpacing(8)

        self.lbl_apk_title = QLabel(tr("dashboard_apk_title"))
        self.lbl_apk_title.setStyleSheet("font-weight: bold; color: #eceff4; font-size: 13px;")
        self.lbl_apk_title.setWordWrap(True)
        apk_box.addWidget(self.lbl_apk_title)

        self.apk_info_lbl = QLabel(tr("dashboard_apk_info"))
        self.apk_info_lbl.setStyleSheet("color: #d8dee9; font-size: 11px;")
        self.apk_info_lbl.setWordWrap(True)
        apk_box.addWidget(self.apk_info_lbl)

        apk_btn_row = QHBoxLayout()
        self.btn_apk_install = QPushButton(tr("dashboard_apk_btn"))
        self.btn_apk_install.setStyleSheet("""
            QPushButton { background-color: #5e81ac; color: white; font-weight: bold;
                          padding: 7px 14px; border-radius: 4px; border: none; }
            QPushButton:hover { background-color: #81a1c1; }
            QPushButton:disabled { background-color: #3b4252; color: #4c566a; }
        """)
        self.btn_apk_cancel = QPushButton(tr("dashboard_apk_cancel"))
        self.btn_apk_cancel.setVisible(False)
        self.btn_apk_cancel.setStyleSheet("""
            QPushButton { background-color: #bf616a; color: white; font-weight: bold;
                          padding: 7px 14px; border-radius: 4px; border: none; }
            QPushButton:hover { background-color: #d08770; }
        """)
        apk_btn_row.addWidget(self.btn_apk_install)
        apk_btn_row.addWidget(self.btn_apk_cancel)
        apk_btn_row.addStretch()
        apk_box.addLayout(apk_btn_row)

        self.lbl_apk_status = QLabel("")
        self.lbl_apk_status.setStyleSheet("color: #88c0d0; font-size: 11px;")
        self.lbl_apk_status.setWordWrap(True)
        apk_box.addWidget(self.lbl_apk_status)
        apk_box.addStretch()

        # ---------- RECHTS: VRChat Picture Folder Fix ----------
        vrchat_card = QFrame()
        vrchat_card.setObjectName("settingsCard")
        vrchat_card.setStyleSheet(_card_css)
        vrchat_box = QVBoxLayout(vrchat_card)
        vrchat_box.setContentsMargins(12, 12, 12, 12)
        vrchat_box.setSpacing(8)

        self.lbl_vrchat_title = QLabel(tr("settings_vrchat_title"))
        self.lbl_vrchat_title.setStyleSheet("font-weight: bold; color: #eceff4; font-size: 13px;")
        self.lbl_vrchat_title.setWordWrap(True)
        vrchat_box.addWidget(self.lbl_vrchat_title)

        self.lbl_vrchat_desc = QLabel(tr("settings_vrchat_desc_short"))
        self.lbl_vrchat_desc.setStyleSheet("color: #d8dee9; font-size: 11px;")
        self.lbl_vrchat_desc.setWordWrap(True)
        vrchat_box.addWidget(self.lbl_vrchat_desc)

        self.btn_vrchat_symlink = QPushButton(tr("settings_vrchat_btn"))
        self.btn_vrchat_symlink.setFixedWidth(160)
        self.btn_vrchat_symlink.setStyleSheet("""
            QPushButton { background-color: #5e81ac; color: white; font-weight: bold;
                          padding: 8px; border-radius: 4px; border: none; }
            QPushButton:hover { background-color: #81a1c1; }
        """)
        vrchat_box.addWidget(self.btn_vrchat_symlink, alignment=Qt.AlignLeft)

        self.lbl_vrchat_status = QLabel("")
        self.lbl_vrchat_status.setStyleSheet("font-size: 11px;")
        self.lbl_vrchat_status.setWordWrap(True)
        vrchat_box.addWidget(self.lbl_vrchat_status)
        vrchat_box.addStretch()

        # Beide Boxen gleich breit nebeneinander (stretch-Faktor 1/1)
        general_row.addWidget(apk_card, 1)
        general_row.addWidget(vrchat_card, 1)
        general_layout.addLayout(general_row)

        layout.addWidget(self.general_group)

        # --- BACKUP (jetzt oben, beide Buttons nebeneinander) ---
        self.backup_group = QGroupBox(tr("backup_title"))
        backup_layout = QVBoxLayout(self.backup_group)
        backup_layout.setSpacing(10)

        backup_btn_row = QHBoxLayout()
        backup_btn_row.setSpacing(10)

        self.btn_vr_backup = QPushButton(tr("backup_create_btn"))
        self.btn_vr_backup.setStyleSheet("""
            QPushButton { background-color: #5e81ac; color: white; border: none;
                          font-weight: bold; padding: 10px; border-radius: 4px; font-size: 13px; }
            QPushButton:hover { background-color: #81a1c1; }
        """)
        backup_btn_row.addWidget(self.btn_vr_backup)

        self.btn_vr_restore = QPushButton(tr("backup_restore_btn"))
        self.btn_vr_restore.setStyleSheet("""
            QPushButton { background-color: #4c566a; color: #eceff4; border: none;
                          font-weight: bold; padding: 10px; border-radius: 4px; font-size: 13px; }
            QPushButton:hover { background-color: #d08770; color: white; }
        """)
        backup_btn_row.addWidget(self.btn_vr_restore)

        backup_layout.addLayout(backup_btn_row)

        # --- WAYVR OVERLAY (UI Design) ---
        self.overlay_group = QGroupBox(tr("overlay_group"))
        overlay_layout = QVBoxLayout(self.overlay_group)
        overlay_layout.setSpacing(10)

        # Beide Buttons nebeneinander in einer horizontalen Reihe
        overlay_btn_row = QHBoxLayout()
        overlay_btn_row.setSpacing(10)

        self.btn_overlay_design = QPushButton(tr("overlay_design_btn"))
        self.btn_overlay_design.setStyleSheet("""
            QPushButton { background-color: #5e81ac; color: white; border: none;
                          font-weight: bold; padding: 10px; border-radius: 4px; font-size: 13px; }
            QPushButton:hover { background-color: #81a1c1; }
            QPushButton:disabled { background-color: #3b4252; color: #4c566a; }
        """)
        overlay_btn_row.addWidget(self.btn_overlay_design)

        self.btn_overlay_reset = QPushButton(tr("overlay_reset_btn"))
        self.btn_overlay_reset.setStyleSheet("""
            QPushButton { background-color: #4c566a; color: #eceff4; border: none;
                          font-weight: bold; padding: 10px; border-radius: 4px; font-size: 13px; }
            QPushButton:hover { background-color: #bf616a; color: white; }
            QPushButton:disabled { background-color: #3b4252; color: #4c566a; }
        """)
        overlay_btn_row.addWidget(self.btn_overlay_reset)

        overlay_layout.addLayout(overlay_btn_row)

        self.chk_overlay_slimevr = QCheckBox(tr("overlay_slimevr_btn"))
        self.chk_overlay_slimevr.setStyleSheet("font-size: 13px; padding: 4px;")
        overlay_layout.addWidget(self.chk_overlay_slimevr)

        # Credits / Links zum WayVR-Projekt und den Design-Autoren
        self.lbl_overlay_credits = QLabel(tr("overlay_credits"))
        self.lbl_overlay_credits.setStyleSheet(
            "color: #d8dee9; font-size: 11px; background-color: #2e3440; "
            "border-radius: 4px; padding: 8px;"
        )
        self.lbl_overlay_credits.setWordWrap(True)
        self.lbl_overlay_credits.setOpenExternalLinks(True)
        self.lbl_overlay_credits.setTextFormat(Qt.RichText)
        overlay_layout.addWidget(self.lbl_overlay_credits)

        layout.addWidget(self.overlay_group)

        # Backup-Box zwischen WayVR-Overlay und OpenXR-Runtime einordnen
        layout.addWidget(self.backup_group)

        # --- OPENXR RUNTIME (Steam-Fix) ---
        self.openxr_group = QGroupBox(tr("openxr_group"))
        openxr_layout = QVBoxLayout(self.openxr_group)
        openxr_layout.setSpacing(8)

        self.lbl_openxr_desc = QLabel(tr("openxr_desc"))
        self.lbl_openxr_desc.setStyleSheet("color: #d8dee9; font-size: 11px;")
        self.lbl_openxr_desc.setWordWrap(True)
        openxr_layout.addWidget(self.lbl_openxr_desc)

        from PySide6.QtWidgets import QPlainTextEdit
        _copy_css = ("QPushButton { background-color: #5e81ac; color: white; border: none; "
                     "font-weight: bold; padding: 6px 10px; border-radius: 4px; font-size: 12px; }"
                     "QPushButton:hover { background-color: #81a1c1; }")

        # Pfad der Datei (kopierbar)
        self.lbl_openxr_path_title = QLabel(tr("openxr_path_title"))
        self.lbl_openxr_path_title.setStyleSheet(
            "color: #eceff4; font-size: 11px; font-weight: bold; padding-top: 4px;")
        openxr_layout.addWidget(self.lbl_openxr_path_title)

        openxr_path_row = QHBoxLayout()
        self.txt_openxr_path = QLineEdit()
        self.txt_openxr_path.setReadOnly(True)
        openxr_path_row.addWidget(self.txt_openxr_path)
        self.btn_openxr_copy_path = QPushButton(tr("openxr_copy_btn"))
        self.btn_openxr_copy_path.setStyleSheet(_copy_css)
        openxr_path_row.addWidget(self.btn_openxr_copy_path)
        openxr_layout.addLayout(openxr_path_row)

        # Inhalt für die Datei (kopierbar)
        self.lbl_openxr_content_title = QLabel(tr("openxr_content_title"))
        self.lbl_openxr_content_title.setStyleSheet(
            "color: #eceff4; font-size: 11px; font-weight: bold; padding-top: 6px;")
        openxr_layout.addWidget(self.lbl_openxr_content_title)

        self.txt_openxr_content = QPlainTextEdit()
        self.txt_openxr_content.setReadOnly(True)
        self.txt_openxr_content.setFixedHeight(150)
        self.txt_openxr_content.setStyleSheet("font-family: monospace; font-size: 11px;")
        openxr_layout.addWidget(self.txt_openxr_content)

        self.btn_openxr_copy_content = QPushButton(tr("openxr_copy_btn"))
        self.btn_openxr_copy_content.setStyleSheet(_copy_css)
        openxr_layout.addWidget(self.btn_openxr_copy_content)

        layout.addWidget(self.openxr_group)

        layout.addStretch()

    def setup_tools_tab(self):
        from PySide6.QtWidgets import QScrollArea

        outer = QVBoxLayout(self.tab_tools)
        outer.setContentsMargins(0, 0, 0, 0)

        # Scroll-Container
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        self.lbl_tools_title = QLabel(tr("tools_title"))
        self.lbl_tools_title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 5px;")
        layout.addWidget(self.lbl_tools_title)

        self.lbl_tools_subtitle = QLabel(tr("tools_subtitle"))
        self.lbl_tools_subtitle.setStyleSheet("color: #7b88a1; font-style: italic; margin-bottom: 10px;")
        layout.addWidget(self.lbl_tools_subtitle)

        # Update-Check Button oben
        header_row = QHBoxLayout()
        header_row.addStretch()
        self.btn_tools_check = QPushButton(tr("tools_check_btn"))
        self.btn_tools_check.setFixedHeight(28)
        self.btn_tools_check.setStyleSheet("""
            QPushButton { background-color: #3b4252; color: #88c0d0; font-size: 11px;
                          padding: 0px 12px; border-radius: 4px; border: none; }
            QPushButton:hover { background-color: #4c566a; }
            QPushButton:disabled { background-color: #2e3440; color: #4c566a; }
        """)
        header_row.addWidget(self.btn_tools_check)
        layout.addLayout(header_row)

        self.tool_cards = {}

        # ---- ZWEI SPALTEN NEBENEINANDER ----
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(16)
        columns_layout.setAlignment(Qt.AlignTop)

        # Linke Spalte: Anwendungen
        self.apps_group = QGroupBox(tr("tools_apps"))
        apps_layout = QVBoxLayout(self.apps_group)
        apps_layout.setSpacing(8)
        apps_layout.setAlignment(Qt.AlignTop)
        for tool in TOOLS_APPS:
            apps_layout.addWidget(self._build_tool_card(tool))
        apps_layout.addStretch()

        # Rechte Spalte: OSC
        self.osc_group = QGroupBox(tr("tools_osc"))
        osc_layout = QVBoxLayout(self.osc_group)
        osc_layout.setSpacing(8)
        osc_layout.setAlignment(Qt.AlignTop)
        for tool in TOOLS_OSC:
            osc_layout.addWidget(self._build_tool_card(tool))
        osc_layout.addStretch()

        columns_layout.addWidget(self.apps_group)
        columns_layout.addWidget(self.osc_group)
        layout.addLayout(columns_layout)
        layout.addStretch()

    def _build_tool_card(self, tool):
        """Baut eine einzelne Tool-Karte — kompaktes Design."""
        from PySide6.QtWidgets import QFrame
        import subprocess

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #21252b;
                border-radius: 6px;
                border: 1px solid #2e3440;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(3)

        # Zeile 1: Name + Version + Update + Status + Link
        top_row = QHBoxLayout()
        top_row.setSpacing(4)

        lbl_name = QLabel(tool["name"])
        lbl_name.setStyleSheet("font-size: 12px; font-weight: bold; color: #eceff4;")
        top_row.addWidget(lbl_name)

        lbl_version = QLabel("")
        lbl_version.setStyleSheet("color: #4c566a; font-size: 10px; font-family: monospace;")
        top_row.addWidget(lbl_version)

        top_row.addStretch()

        lbl_update = QLabel("")
        lbl_update.setStyleSheet("color: #ebcb8b; font-size: 10px; font-weight: bold;")
        top_row.addWidget(lbl_update)

        lbl_status = QLabel(tr("tools_unknown"))
        lbl_status.setStyleSheet("color: #7b88a1; font-size: 10px; font-style: italic;")
        top_row.addWidget(lbl_status)

        if tool.get("link"):
            btn_link = QPushButton("🌐")
            btn_link.setFixedSize(24, 24)
            btn_link.setStyleSheet("""
                QPushButton { background-color: #3b4252; color: #88c0d0; font-size: 11px;
                              border-radius: 4px; border: none; padding: 0px; }
                QPushButton:hover { background-color: #4c566a; }
            """)
            btn_link.setToolTip(tool["link"])
            btn_link.clicked.connect(lambda _, url=tool["link"]: self._open_url(url))
            top_row.addWidget(btn_link)

        card_layout.addLayout(top_row)

        # Zeile 2: Beschreibung — lesbar, bricht um
        lbl_desc = QLabel(tool["desc"])
        lbl_desc.setStyleSheet("color: #d8dee9; font-size: 11px;")
        lbl_desc.setWordWrap(True)
        lbl_desc.setMinimumWidth(0)
        card_layout.addWidget(lbl_desc)

        # Zeile 3: Startbefehl (nur wenn installiert)
        cmd_row = QHBoxLayout()
        cmd_row.setSpacing(4)

        txt_cmd = QLineEdit(tool["start_cmd"])
        txt_cmd.setReadOnly(True)
        txt_cmd.setFixedHeight(22)
        txt_cmd.setStyleSheet("""
            QLineEdit {
                background-color: #1e222a; border: 1px solid #3b4252;
                border-radius: 3px; padding: 0px 6px;
                color: #a3be8c; font-family: monospace; font-size: 10px;
            }
        """)

        btn_copy = QPushButton(tr("tools_copy"))
        btn_copy.setFixedHeight(22)
        btn_copy.setFixedWidth(65)
        btn_copy.setStyleSheet("""
            QPushButton { background-color: #3b4252; color: #d8dee9; font-size: 10px;
                          padding: 0px; border-radius: 3px; border: none; }
            QPushButton:hover { background-color: #4c566a; }
        """)
        btn_copy.clicked.connect(lambda _, t=tool["start_cmd"]: self._copy_to_clipboard(t))

        cmd_row.addWidget(txt_cmd)
        cmd_row.addWidget(btn_copy)

        cmd_widget = QWidget()
        cmd_widget.setLayout(cmd_row)
        cmd_widget.setVisible(False)
        card_layout.addWidget(cmd_widget)

        # Zeile 4: Methoden-Auswahl (AppImage / yay / paru) — nur sichtbar, wenn >1 Option
        combo_method = QComboBox()
        combo_method.setFixedHeight(24)
        combo_method.setStyleSheet("""
            QComboBox { background-color: #2e3440; color: #d8dee9; font-size: 10px;
                        border: 1px solid #3b4252; border-radius: 3px; padding: 0px 6px; }
            QComboBox:hover { border-color: #5e81ac; }
            QComboBox QAbstractItemView { background-color: #2e3440; color: #d8dee9;
                        selection-background-color: #5e81ac; }
        """)
        combo_method.setVisible(False)
        card_layout.addWidget(combo_method)

        # Zeile 5: Install-Button — kompakt
        btn_install = QPushButton(tr("tools_install_btn"))
        btn_install.setFixedHeight(26)
        btn_install.setStyleSheet("""
            QPushButton { background-color: #5e81ac; color: white; font-weight: bold;
                          font-size: 11px; border-radius: 4px; border: none; }
            QPushButton:hover { background-color: #81a1c1; }
            QPushButton:disabled { background-color: #3b4252; color: #4c566a; }
        """)
        card_layout.addWidget(btn_install)

        self.tool_cards[tool["key"]] = {
            "pkg":          tool["pkg"],
            "tool":         tool,
            "lbl_status":   lbl_status,
            "lbl_version":  lbl_version,
            "lbl_update":   lbl_update,
            "lbl_desc":     lbl_desc,
            "btn_install":  btn_install,
            "btn_copy":     btn_copy,
            "cmd_widget":   cmd_widget,
            "combo_method": combo_method,
            "start_cmd":    tool["start_cmd"],
        }

        return card

    def _open_url(self, url):
        import subprocess
        subprocess.Popen(["xdg-open", url])

    def _copy_to_clipboard(self, text):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
