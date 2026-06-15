#!/usr/bin/env python3
import os
import subprocess
import json
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QComboBox, QSlider, QGroupBox, QFormLayout,
                               QPushButton, QMessageBox)
from PySide6.QtCore import Qt

# Importiert aus dem selben Verzeichnis (core)
from config_manager import save_all_settings, load_saved_settings
from translations import tr



class StreamingTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_app = parent  # Verbindung zur Hauptanwendung
        self.init_ui()
        self.apply_loaded_streaming_settings()

    def apply_loaded_streaming_settings(self):
        """Lädt die Streaming-Einstellungen beim Start und setzt die UI-Elemente."""
        data = load_saved_settings()
        if not data:
            return

        # Signale kurz blockieren, damit wir beim Setzen kein ungewolltes Autosave triggern
        self.combo_openvr.blockSignals(True)
        self.slider_res.blockSignals(True)
        self.slider_fov.blockSignals(True)
        self.combo_encoder.blockSignals(True)
        self.combo_codec.blockSignals(True)
        self.slider_bitrate.blockSignals(True)

        # Werte auslesen (mit Fallbacks, falls die Keys in alten Configs fehlen)
        openvr_val = data.get("openvr_compat", "Auto")
        res_val = data.get("render_resolution", 100)
        fov_val = data.get("foveated_encoding", 50)
        encoder_val = data.get("encoder", "Auto")
        codec_val = data.get("codec", "Automatic")
        bitrate_val = data.get("bitrate", 100)

        # UI-Elemente auf die gespeicherten Werte setzen
        self.combo_openvr.setCurrentText(openvr_val)

        self.slider_res.setValue(int(res_val))
        self.update_resolution_label(int(res_val)) # Text-Label (z.B. "100% (2160 x 2160)") updaten

        self.slider_fov.setValue(int(fov_val))
        self.update_fov_label(int(fov_val))

        self.combo_encoder.setCurrentText(encoder_val)
        self.combo_codec.setCurrentText(codec_val)

        self.slider_bitrate.setValue(int(bitrate_val))
        self.update_bitrate_label(int(bitrate_val))

        # Signale wieder freigeben
        self.combo_openvr.blockSignals(False)
        self.slider_res.blockSignals(False)
        self.slider_fov.blockSignals(False)
        self.combo_encoder.blockSignals(False)
        self.combo_codec.blockSignals(False)
        self.slider_bitrate.blockSignals(False)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel(tr("streaming_title"))
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 15px;")
        layout.addWidget(title)

        # --- GRUPPE 1: KOMPATIBILITÄT ---
        compat_group = QGroupBox(tr("streaming_compat"))
        compat_form = QFormLayout(compat_group)

        self.combo_openvr = QComboBox()
        self.combo_openvr.addItems(["Auto", "xrizer", "opencomposite"])

        compat_form.addRow(tr("streaming_openvr"), self.combo_openvr)
        layout.addWidget(compat_group)

        # --- GRUPPE 2: GRAFIK & AUFLÖSUNG ---
        video_group = QGroupBox("Video & Enkodierung")
        video_form = QFormLayout(video_group)

        # Render Resolution Slider (50% bis 200%)
        res_layout = QHBoxLayout()
        self.slider_res = QSlider(Qt.Horizontal)
        self.slider_res.setMinimum(50)
        self.slider_res.setMaximum(200)
        self.slider_res.setValue(100)

        self.lbl_res_val = QLabel("100% (2160 x 2160)")
        self.lbl_res_val.setStyleSheet("font-weight: bold; color: #88c0d0; min-width: 130px;")

        res_layout.addWidget(self.slider_res)
        res_layout.addWidget(self.lbl_res_val)
        video_form.addRow("Render Resolution pro Auge:", res_layout)

        # Foveated Encoding Slider (0% bis 100%)
        fov_layout = QHBoxLayout()
        self.slider_fov = QSlider(Qt.Horizontal)
        self.slider_fov.setMinimum(0)
        self.slider_fov.setMaximum(100)
        self.slider_fov.setValue(50)

        self.lbl_fov_val = QLabel("50% (Default)")
        self.lbl_fov_val.setStyleSheet("font-weight: bold; color: #88c0d0; min-width: 90px;")

        fov_layout.addWidget(self.slider_fov)
        fov_layout.addWidget(self.lbl_fov_val)
        video_form.addRow("Foveated Encoding:", fov_layout)

        # --- SICHTBARKEIT: video_group (Render Resolution + Foveated) ---
        # Um wieder einzublenden: video_group.setVisible(True)
        video_group.setVisible(False)

        layout.addWidget(video_group)

        # --- GRUPPE 3: ENCODER & BITRATE ---
        encoder_group = QGroupBox(tr("streaming_encoder_grp"))
        encoder_form = QFormLayout(encoder_group)

        self.combo_encoder = QComboBox()
        self.combo_encoder.addItems(["Auto", "nvenc", "vaapi", "Vulkan", "x264"])
        encoder_form.addRow(tr("streaming_encoder"), self.combo_encoder)

        # Codec-Zeile (versteckt) — zum Einblenden: self.row_codec.setVisible(True)
        self.row_codec = QWidget()
        row_codec_layout = QHBoxLayout(self.row_codec)
        row_codec_layout.setContentsMargins(0, 0, 0, 0)
        self.combo_codec = QComboBox()
        self.combo_codec.addItems(["Automatic", "av1 (Quest 3 / Pico 4 Ultra)", "h265", "h264"])
        row_codec_layout.addWidget(QLabel("Codec:"))
        row_codec_layout.addWidget(self.combo_codec)
        row_codec_layout.addStretch()
        encoder_form.addRow(self.row_codec)
        self.row_codec.setVisible(False)

        # Bitrate-Zeile (versteckt) — zum Einblenden: self.row_bitrate.setVisible(True)
        self.row_bitrate = QWidget()
        row_bitrate_layout = QHBoxLayout(self.row_bitrate)
        row_bitrate_layout.setContentsMargins(0, 0, 0, 0)
        self.slider_bitrate = QSlider(Qt.Horizontal)
        self.slider_bitrate.setMinimum(0)
        self.slider_bitrate.setMaximum(200)
        self.slider_bitrate.setValue(100)
        self.lbl_bitrate_val = QLabel("100 Mbps")
        self.lbl_bitrate_val.setStyleSheet("font-weight: bold; color: #88c0d0; min-width: 90px;")
        row_bitrate_layout.addWidget(QLabel("Bitrate:"))
        row_bitrate_layout.addWidget(self.slider_bitrate)
        row_bitrate_layout.addWidget(self.lbl_bitrate_val)
        encoder_form.addRow(self.row_bitrate)
        self.row_bitrate.setVisible(False)

        layout.addWidget(encoder_group)
        # --- GRUPPE 4: OPENXR RUNTIME ---
        openxr_group = QGroupBox(tr("streaming_openxr"))
        openxr_layout = QFormLayout(openxr_group)

        self.lbl_active_runtime = QLabel(tr("streaming_checking"))
        self.lbl_active_runtime.setStyleSheet("font-weight: bold; color: #ebcb8b; font-size: 13px;")

        self.btn_switch_wivrn = QPushButton(tr("streaming_wivrn_btn"))
        self.btn_switch_wivrn.setStyleSheet(
            "QPushButton { background-color: #81a1c1; color: #2e3440; font-weight: bold; padding: 8px; } "
            "QPushButton:hover { background-color: #88c0d0; }"
        )

        self.btn_switch_steamvr = QPushButton(tr("streaming_steam_btn"))
        self.btn_switch_steamvr.setStyleSheet(
            "QPushButton { background-color: #4c566a; color: #eceff4; font-weight: bold; padding: 8px; } "
            "QPushButton:hover { background-color: #5e81ac; }"
        )

        openxr_layout.addRow(tr("streaming_status"), self.lbl_active_runtime)
        openxr_layout.addRow(self.btn_switch_wivrn)
        openxr_layout.addRow(self.btn_switch_steamvr)

        layout.addWidget(openxr_group)
        layout.addStretch()

        # --- SIGNALE VERKNÜPFEN ---
        self.slider_res.valueChanged.connect(self.update_resolution_label)
        self.slider_fov.valueChanged.connect(self.update_fov_label)
        self.slider_bitrate.valueChanged.connect(self.update_bitrate_label)

        # Verknüpfung für die Laufzeit-Umschaltung
        self.combo_openvr.currentTextChanged.connect(self.apply_openvr_compatibility)

        # Aktiviert automatisches Speichern NUR bei Uservariation
        self.combo_openvr.activated.connect(self.trigger_auto_save)
        self.slider_res.sliderReleased.connect(self.trigger_auto_save)
        self.slider_fov.sliderReleased.connect(self.trigger_auto_save)
        self.combo_encoder.activated.connect(self.trigger_auto_save)
        self.combo_codec.activated.connect(self.trigger_auto_save)
        self.slider_bitrate.sliderReleased.connect(self.trigger_auto_save)

        # OpenXR Runtime Buttons
        self.btn_switch_wivrn.clicked.connect(self.set_openxr_runtime_wivrn)
        self.btn_switch_steamvr.clicked.connect(self.set_openxr_runtime_steamvr)
        self.check_active_openxr_runtime()

    def update_resolution_label(self, value):
        base_w, base_h = 2160, 2160
        scale = value / 100.0
        self.lbl_res_val.setText(f"{value}% ({int(base_w * scale)} x {int(base_h * scale)})")

    def update_fov_label(self, value):
        if value == 50:
            self.lbl_fov_val.setText("50% (Default)")
        else:
            self.lbl_fov_val.setText(f"{value}%")

    def update_bitrate_label(self, value):
        if value == 0:
            self.lbl_bitrate_val.setText("Auto")
        else:
            self.lbl_bitrate_val.setText(f"{value} Mbps")

    def apply_openvr_compatibility(self):
        selected_text = self.combo_openvr.currentText()

        if selected_text == "opencomposite":
            target_path = "/opt/opencomposite"
        else:
            target_path = "/opt/xrizer"

        wivrn_config_file = os.path.expanduser("~/.config/wivrn/config.json")

        if os.path.exists(wivrn_config_file):
            try:
                with open(wivrn_config_file, "r") as f:
                    wivrn_data = json.load(f)

                wivrn_data["openvr-compat-path"] = target_path

                with open(wivrn_config_file, "w") as f:
                    json.dump(wivrn_data, f, indent=4)
                print(f"[Streaming Tab] WiVRn Runtime in config.json erfolgreich auf '{target_path}' geändert.")
            except Exception as e:
                print(f"[Fehler] Konnte WiVRn-config.json nicht aktualisieren: {e}")
        else:
            print("[Fehler] WiVRn config.json wurde unter ~/.config/wivrn/ nicht gefunden.")

        self.trigger_auto_save()

    def check_active_openxr_runtime(self):
        """Prüft, welche OpenXR Runtime aktuell im System aktiv ist."""
        try:
            active_json = os.path.expanduser("~/.config/openxr/1/active_runtime.json")
            if os.path.exists(active_json):
                with open(active_json, "r") as f:
                    content = f.read()
                    if "wivrn" in content.lower():
                        self.lbl_active_runtime.setText("✔ WiVRn (Aktiv)")
                        self.lbl_active_runtime.setStyleSheet("font-weight: bold; color: #a3be8c; font-size: 13px;")
                    elif "steamvr" in content.lower():
                        self.lbl_active_runtime.setText("✔ SteamVR (Aktiv)")
                        self.lbl_active_runtime.setStyleSheet("font-weight: bold; color: #81a1c1; font-size: 13px;")
                    else:
                        self.lbl_active_runtime.setText("Andere Runtime aktiv")
                        self.lbl_active_runtime.setStyleSheet("font-weight: bold; color: #ebcb8b; font-size: 13px;")
            else:
                self.lbl_active_runtime.setText("Keine Runtime gesetzt (System-Standard)")
                self.lbl_active_runtime.setStyleSheet("font-weight: bold; color: #bf616a; font-size: 13px;")
        except Exception as e:
            self.lbl_active_runtime.setText(f"Fehler beim Prüfen: {e}")

    def set_openxr_runtime_wivrn(self):
        """Schaltet die OpenXR Runtime auf WiVRn um."""
        try:
            os.makedirs(os.path.expanduser("~/.config/openxr/1"), exist_ok=True)
            wivrn_runtime_path = "/usr/share/openxr/1/openxr_wivrn.json"
            if not os.path.exists(wivrn_runtime_path):
                wivrn_runtime_path = os.path.expanduser("~/.local/share/openxr/1/openxr_wivrn.json")

            active_json = os.path.expanduser("~/.config/openxr/1/active_runtime.json")
            data = {"file_format_version": "1.0.0", "runtime": {"library_path": wivrn_runtime_path}}
            with open(active_json, "w") as f:
                json.dump(data, f, indent=4)

            self.check_active_openxr_runtime()
            QMessageBox.information(self, "Runtime gewechselt", "WiVRn wurde erfolgreich als Standard-OpenXR-Runtime gesetzt.")
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Konnte Runtime nicht wechseln: {e}")

    def set_openxr_runtime_steamvr(self):
        """Schaltet die OpenXR Runtime auf SteamVR um."""
        try:
            os.makedirs(os.path.expanduser("~/.config/openxr/1"), exist_ok=True)
            steamvr_runtime_path = os.path.expanduser("~/.local/share/Steam/steamapps/common/SteamVR/steamxr_linux64.json")

            active_json = os.path.expanduser("~/.config/openxr/1/active_runtime.json")
            data = {"file_format_version": "1.0.0", "runtime": {"library_path": steamvr_runtime_path}}
            with open(active_json, "w") as f:
                json.dump(data, f, indent=4)

            self.check_active_openxr_runtime()
            QMessageBox.information(self, "Runtime gewechselt", "SteamVR wurde erfolgreich als Standard-OpenXR-Runtime gesetzt.")
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Konnte Runtime nicht wechseln: {e}")

    def trigger_auto_save(self):
        """Reicht die aktuellen Streaming-Werte an die Hauptanwendung weiter und speichert."""
        if self.main_app and hasattr(self.main_app, 'is_loading') and self.main_app.is_loading:
            return

        slider_percentage = self.slider_res.value()

        streaming_data = {
            "openvr_compat": self.combo_openvr.currentText(),
            "render_resolution": slider_percentage,
            "foveated_encoding": self.slider_fov.value(),
            "encoder": self.combo_encoder.currentText(),
            "codec": self.combo_codec.currentText(),
            "bitrate": self.slider_bitrate.value()
        }

        # FIX: Zugriff erfolgt nun über self.main_app.ui.<widget_name>
        hand = self.main_app.ui.chk_hand_tracking.isChecked()
        fbt = self.main_app.ui.chk_fbt.isChecked()
        steam = self.main_app.ui.chk_steamvr_tracker.isChecked()
        refresh = self.main_app.ui.combo_refresh.currentText()
        count = self.main_app.ui.num_apps.text()

        apps_data = []
        if hasattr(self.main_app, 'autostart_rows'):
            for row in self.main_app.autostart_rows:
                apps_data.append({
                    "type": row["combo"].currentText(),
                    "cmd": row["input"].text()
                })

        # Ausführen des zentralen Speicherbefehls
        save_all_settings(hand, fbt, steam, refresh, count, apps_data, streaming_data)
