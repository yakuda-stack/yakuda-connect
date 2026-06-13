#!/usr/bin/env python3
import os
import sys
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
                               QStackedWidget, QLabel, QPushButton, QCheckBox,
                               QComboBox, QLineEdit, QGroupBox, QFormLayout,
                               QSlider, QTextEdit)
from PySide6.QtCore import Qt

# Programme aus zentraler Datei laden
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'core')))
from programs import TOOLS_APPS, TOOLS_OSC

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
        self.sidebar.addItems([
            "Installation",
            "Dashboard",
            "Streaming",
            "Tools",
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

        self.pages.addWidget(self.tab_installation)    # Index 0
        self.pages.addWidget(self.tab_dashboard)       # Index 1
        self.pages.addWidget(self.tab_streaming)       # Index 2
        self.pages.addWidget(self.tab_tools)           # Index 3

        # Initialisiere die einzelnen Bereiche
        self.setup_installation_tab()
        self.setup_dashboard_tab()
        self.setup_tools_tab()
        # self.setup_streaming_tab() # DEAKTIVIERT: main.py bettet StreamingTab dynamisch ein und erzeugt das Layout selbst!

    def setup_installation_tab(self):
        layout = QVBoxLayout(self.tab_installation)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Systemkomponenten & Installation")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        self.pkg_group = QGroupBox("Erforderliche Abhängigkeiten (Arch Linux / AUR)")
        self.pkg_layout = QFormLayout(self.pkg_group)
        layout.addWidget(self.pkg_group)

        btn_layout = QHBoxLayout()
        self.btn_install = QPushButton("Fehlende Komponenten installieren")
        self.btn_install.setFixedHeight(30)
        self.btn_install.setStyleSheet("""
            QPushButton { background-color: #5e81ac; color: white; font-weight: bold;
                          font-size: 11px; border-radius: 4px; border: none; }
            QPushButton:hover { background-color: #81a1c1; }
        """)
        self.btn_update = QPushButton("Aktualisieren")
        self.btn_update.setFixedHeight(30)
        self.btn_update.setStyleSheet("""
            QPushButton { background-color: #3b4252; color: #d8dee9; font-weight: bold;
                          font-size: 11px; border-radius: 4px; border: none; }
            QPushButton:hover { background-color: #4c566a; }
        """)
        btn_layout.addWidget(self.btn_install)
        btn_layout.addWidget(self.btn_update)
        layout.addLayout(btn_layout)

        self.lbl_worker_status = QLabel("Bereit.")
        self.lbl_worker_status.setStyleSheet("color: #7b88a1; font-style: italic; margin-top: 5px;")
        layout.addWidget(self.lbl_worker_status)

        layout.addSpacing(20)

        # Container für dynamische Backup-Buttons
        self.backup_group = QGroupBox("VR-Umgebung Sicherung & Wiederherstellung")
        backup_layout = QVBoxLayout(self.backup_group)
        backup_layout.setSpacing(10)

        self.btn_vr_backup = QPushButton("XR/VR Umgebung backup machen")
        self.btn_vr_backup.setStyleSheet("""
            QPushButton { background-color: #5e81ac; color: white; border: none; font-weight: bold; padding: 10px; border-radius: 4px; font-size: 13px; }
            QPushButton:hover { background-color: #81a1c1; }
        """)
        backup_layout.addWidget(self.btn_vr_backup)

        self.btn_vr_restore = QPushButton("XR/VR Umgebung wiederherstellen")
        self.btn_vr_restore.setStyleSheet("""
            QPushButton { background-color: #4c566a; color: #eceff4; border: none; font-weight: bold; padding: 10px; border-radius: 4px; font-size: 13px; }
            # QPushButton:hover { background-color: #d08770; color: white; }
        """)
        backup_layout.addWidget(self.btn_vr_restore)

        layout.addWidget(self.backup_group)


        self.backup_group.hide() # Standardmäßig versteckt

        # Container für dynamische Backup-Buttons
        self.backup_group = QGroupBox("VR-Umgebung Sicherung & Wiederherstellung")
        backup_layout = QVBoxLayout(self.backup_group)
        backup_layout.setSpacing(10)

        self.btn_vr_backup = QPushButton("XR/VR Umgebung backup machen")
        self.btn_vr_backup.setStyleSheet("""
            QPushButton { background-color: #5e81ac; color: white; border: none; font-weight: bold; padding: 10px; border-radius: 4px; font-size: 13px; }
            QPushButton:hover { background-color: #81a1c1; }
        """)
        backup_layout.addWidget(self.btn_vr_backup)

        self.btn_vr_restore = QPushButton("XR/VR Umgebung wiederherstellen")
        self.btn_vr_restore.setStyleSheet("""
            QPushButton { background-color: #4c566a; color: #eceff4; border: none; font-weight: bold; padding: 10px; border-radius: 4px; font-size: 13px; }
            QPushButton:hover { background-color: #d08770; color: white; }
        """)
        backup_layout.addWidget(self.btn_vr_restore)

        layout.addWidget(self.backup_group)
        self.backup_group.hide() # Standardmäßig versteckt (bleibt wie gewünscht!)

# --- INFO-KASTEN (ERWEITERTE HÖHE FÜR VOLLSTÄNDIGEN TEXT) ---
        from PySide6.QtWidgets import QTextEdit

        self.info_group = QGroupBox("Hinweise & Informationen")
        info_layout = QVBoxLayout(self.info_group)
        info_layout.setSpacing(10)

        self.txt_free_info = QTextEdit()
        self.txt_free_info.setReadOnly(True)

        # Auf 350 erhöht, damit die Box groß genug nach unten gezogen wird
        # und alle Punkte (Backups + Performance) gleichzeitig reinpassen!
        self.txt_free_info.setMinimumHeight(350)

        # Scrollbalken rigoros abschalten
        self.txt_free_info.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
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
        layout = QVBoxLayout(self.tab_dashboard)
        layout.setContentsMargins(20, 20, 20, 20)

        version_layout = QHBoxLayout()
        self.lbl_app_ver = QLabel("<b>App Version:</b> v1.0.0-alpha")
        self.lbl_app_ver.setStyleSheet("color: #81a1c1;")
        self.lbl_wivrn_ver = QLabel("<b>WiVRn Version:</b> Prüfe...")
        self.lbl_wivrn_ver.setStyleSheet("color: #81a1c1;")
        version_layout.addWidget(self.lbl_app_ver)
        version_layout.addStretch()
        version_layout.addWidget(self.lbl_wivrn_ver)
        layout.addLayout(version_layout)

        server_group = QGroupBox("Server Steuerung")
        server_layout = QVBoxLayout(server_group)

        top_row = QHBoxLayout()
        self.btn_start = QPushButton("Server Start")
        self.btn_stop = QPushButton("Server Stop")

        self.lbl_status_dot = QLabel("●")
        self.lbl_status_dot.setStyleSheet("color: #bf616a; font-size: 24px; margin-left: 10px;")
        self.lbl_status_text = QLabel("Ausgeschaltet")
        self.lbl_status_text.setStyleSheet("font-weight: bold; color: #7b88a1;")

        top_row.addWidget(self.btn_start)
        top_row.addWidget(self.btn_stop)
        top_row.addSpacing(20)
        top_row.addWidget(self.lbl_status_dot)
        top_row.addWidget(self.lbl_status_text)
        top_row.addStretch()
        server_layout.addLayout(top_row)

        self.btn_port_status = QPushButton("Firewall fixen & Port 9757 freigeben")
        self.btn_port_status.setFixedWidth(320)
        self.btn_port_status.setStyleSheet("""
            QPushButton { background-color: #4c566a; color: #eceff4; border: none; font-weight: bold; border-radius: 4px; padding: 6px; margin-top: 5px; }
            QPushButton:hover { background-color: #5e81ac; }
        """)
        server_layout.addWidget(self.btn_port_status)
        layout.addWidget(server_group)

        tracking_group = QGroupBox("Tracking & Display-Optionen")
        tracking_layout = QVBoxLayout(tracking_group)

        self.chk_hand_tracking = QCheckBox("Hand Tracking")
        self.chk_fbt = QCheckBox("Full Body Tracking")
        self.chk_fbt.setChecked(True)
        self.chk_steamvr_tracker = QCheckBox("Enable Steam VR Tracker Device")

        lbl_tracker_note = QLabel("  ↳ Hinweis: OpenComposite muss active genutzt werden!")
        lbl_tracker_note.setStyleSheet("color: #d08770; font-style: italic; font-weight: bold; margin-bottom: 5px;")

        refresh_layout = QHBoxLayout()
        lbl_refresh = QLabel("Refresh Rate:")
        self.combo_refresh = QComboBox()
        self.combo_refresh.addItems(["Auto", "72", "90"])
        self.combo_refresh.setFixedWidth(100)
        refresh_layout.addWidget(lbl_refresh)
        refresh_layout.addWidget(self.combo_refresh)
        refresh_layout.addStretch()

        tracking_layout.addWidget(self.chk_hand_tracking)
        tracking_layout.addWidget(self.chk_fbt)
        tracking_layout.addWidget(self.chk_steamvr_tracker)
        tracking_layout.addWidget(lbl_tracker_note)
        tracking_layout.addLayout(refresh_layout)
        layout.addWidget(tracking_group)

        pairing_group = QGroupBox("Pairing Modus")
        pairing_layout = QHBoxLayout(pairing_group)
        self.chk_pairing = QCheckBox("Pairing aktivieren")
        self.txt_code = QLineEdit()
        self.txt_code.setPlaceholderText("Generiere Code...")
        self.txt_code.setFixedWidth(150)
        self.txt_code.setReadOnly(True)

        pairing_layout.addWidget(self.chk_pairing)
        pairing_layout.addWidget(QLabel("Pairing Code:"))
        pairing_layout.addWidget(self.txt_code)
        pairing_layout.addStretch()
        layout.addWidget(pairing_group)

        autostart_group = QGroupBox("Autostart Applikationen")
        autostart_layout = QVBoxLayout(autostart_group)
        form_layout = QFormLayout()

        self.num_apps = QLineEdit("1")
        self.num_apps.setFixedWidth(50)
        self.num_apps.setAlignment(Qt.AlignCenter)
        form_layout.addRow("Anzahl zu startender Programme:", self.num_apps)
        autostart_layout.addLayout(form_layout)

        self.autostart_container = QWidget()
        self.autostart_container_layout = QVBoxLayout(self.autostart_container)
        self.autostart_container_layout.setContentsMargins(0, 0, 0, 0)
        autostart_layout.addWidget(self.autostart_container)
        layout.addWidget(autostart_group)

        self.headset_group = QGroupBox("Gekoppelte Headsets")
        headset_layout = QHBoxLayout(self.headset_group)

        self.list_headsets = QListWidget()
        self.list_headsets.setFixedHeight(150)
        self.list_headsets.setStyleSheet("""
            QListWidget { background-color: #1e222a; color: #d8dee9; border: 1px solid #3b4252; border-radius: 4px; }
            QListWidget::item { padding: 6px; border-bottom: 1px solid #2e3440; }
            QListWidget::item:selected { background-color: #3b4252; color: #bf616a; font-weight: bold; }
        """)

        right_btn_layout = QVBoxLayout()
        self.btn_refresh_list = QPushButton("Liste aktualisieren")
        self.btn_remove_headset = QPushButton("Headset löschen")
        self.btn_remove_headset.setStyleSheet("QPushButton { background-color: #bf616a; border: none; color: white; font-weight: bold; } QPushButton:hover { background-color: #d08770; }")
        self.btn_disconnect_headset = QPushButton("Verbindung trennen")
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

        title = QLabel("Tools")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 5px;")
        layout.addWidget(title)

        subtitle = QLabel("Installiere und starte nützliche VR-Begleitprogramme direkt von hier.")
        subtitle.setStyleSheet("color: #7b88a1; font-style: italic; margin-bottom: 10px;")
        layout.addWidget(subtitle)

        # Update-Check Button oben
        header_row = QHBoxLayout()
        header_row.addStretch()
        self.btn_tools_check = QPushButton("🔄 Updates prüfen")
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
        apps_group = QGroupBox("Anwendungen")
        apps_layout = QVBoxLayout(apps_group)
        apps_layout.setSpacing(8)
        apps_layout.setAlignment(Qt.AlignTop)
        for tool in TOOLS_APPS:
            apps_layout.addWidget(self._build_tool_card(tool))
        apps_layout.addStretch()

        # Rechte Spalte: OSC
        osc_group = QGroupBox("OSC")
        osc_layout = QVBoxLayout(osc_group)
        osc_layout.setSpacing(8)
        osc_layout.setAlignment(Qt.AlignTop)
        for tool in TOOLS_OSC:
            osc_layout.addWidget(self._build_tool_card(tool))
        osc_layout.addStretch()

        columns_layout.addWidget(apps_group)
        columns_layout.addWidget(osc_group)
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

        lbl_status = QLabel("Unbekannt")
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

        btn_copy = QPushButton("Kopieren")
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

        # Zeile 4: Install-Button — kompakt
        btn_install = QPushButton("Installieren")
        btn_install.setFixedHeight(26)
        btn_install.setStyleSheet("""
            QPushButton { background-color: #5e81ac; color: white; font-weight: bold;
                          font-size: 11px; border-radius: 4px; border: none; }
            QPushButton:hover { background-color: #81a1c1; }
            QPushButton:disabled { background-color: #3b4252; color: #4c566a; }
        """)
        card_layout.addWidget(btn_install)

        self.tool_cards[tool["key"]] = {
            "pkg":         tool["pkg"],
            "lbl_status":  lbl_status,
            "lbl_version": lbl_version,
            "lbl_update":  lbl_update,
            "btn_install": btn_install,
            "cmd_widget":  cmd_widget,
            "start_cmd":   tool["start_cmd"],
        }

        return card

    def _open_url(self, url):
        import subprocess
        subprocess.Popen(["xdg-open", url])

    def _copy_to_clipboard(self, text):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
