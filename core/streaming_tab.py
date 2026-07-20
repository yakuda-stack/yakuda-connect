#!/usr/bin/env python3
import os
import shutil
import subprocess
import json
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QComboBox, QSlider, QGroupBox, QFormLayout,
                               QPushButton, QMessageBox, QLineEdit, QApplication)
from PySide6.QtCore import Qt

# Importiert aus dem selben Verzeichnis (core)
from config_manager import save_all_settings, load_saved_settings
from translations import tr
import vr_environment as venv



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

        self.lbl_title = QLabel(tr("streaming_title"))
        self.lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 15px;")
        layout.addWidget(self.lbl_title)

        # --- GRUPPE 1: KOMPATIBILITÄT ---
        self.compat_group = QGroupBox(tr("streaming_compat"))
        compat_form = QFormLayout(self.compat_group)

        self.combo_openvr = QComboBox()
        self.combo_openvr.addItems(["Auto", "xrizer", "opencomposite"])

        self.lbl_openvr = QLabel(tr("streaming_openvr"))
        compat_form.addRow(self.lbl_openvr, self.combo_openvr)
        layout.addWidget(self.compat_group)

        # --- GRUPPE 2: GRAFIK & AUFLÖSUNG ---
        self.video_group = QGroupBox(tr("streaming_video"))
        video_form = QFormLayout(self.video_group)

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
        self.lbl_res_title = QLabel(tr("streaming_res"))
        video_form.addRow(self.lbl_res_title, res_layout)

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
        self.lbl_fov_title = QLabel(tr("streaming_fov"))
        video_form.addRow(self.lbl_fov_title, fov_layout)

        # --- SICHTBARKEIT: video_group (Render Resolution + Foveated) ---
        # Um wieder einzublenden: self.video_group.setVisible(True)
        self.video_group.setVisible(False)

        layout.addWidget(self.video_group)

        # --- GRUPPE 3: ENCODER & BITRATE ---
        self.encoder_group = QGroupBox(tr("streaming_encoder_grp"))
        encoder_form = QFormLayout(self.encoder_group)

        self.combo_encoder = QComboBox()
        self.combo_encoder.addItems(["Auto", "nvenc", "vaapi", "Vulkan", "x264"])
        self.lbl_encoder = QLabel(tr("streaming_encoder"))
        encoder_form.addRow(self.lbl_encoder, self.combo_encoder)

        # Codec-Zeile (versteckt) — zum Einblenden: self.row_codec.setVisible(True)
        self.row_codec = QWidget()
        row_codec_layout = QHBoxLayout(self.row_codec)
        row_codec_layout.setContentsMargins(0, 0, 0, 0)
        self.combo_codec = QComboBox()
        self.combo_codec.addItems(["Automatic", "av1 (Quest 3 / Pico 4 Ultra)", "h265", "h264"])
        self.lbl_codec = QLabel(tr("streaming_codec"))
        row_codec_layout.addWidget(self.lbl_codec)
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
        self.lbl_bitrate = QLabel(tr("streaming_bitrate"))
        row_bitrate_layout.addWidget(self.lbl_bitrate)
        row_bitrate_layout.addWidget(self.slider_bitrate)
        row_bitrate_layout.addWidget(self.lbl_bitrate_val)
        encoder_form.addRow(self.row_bitrate)
        self.row_bitrate.setVisible(False)

        layout.addWidget(self.encoder_group)

        # --- GRUPPE: VR-PRIORITÄT (Async Reprojection / CAP_SYS_NICE) ---
        self.prio_group = QGroupBox(tr("streaming_prio"))
        prio_layout = QVBoxLayout(self.prio_group)

        self.lbl_prio_desc = QLabel(tr("streaming_prio_desc"))
        self.lbl_prio_desc.setWordWrap(True)
        self.lbl_prio_desc.setStyleSheet("color: #7b88a1; font-size: 11px;")
        prio_layout.addWidget(self.lbl_prio_desc)

        prio_row = QHBoxLayout()
        self.lbl_prio_status = QLabel(tr("streaming_checking"))
        self.lbl_prio_status.setStyleSheet("font-weight: bold; color: #ebcb8b; font-size: 13px;")
        self.btn_vr_priority = QPushButton(tr("streaming_prio_btn"))
        self.btn_vr_priority.setStyleSheet(
            "QPushButton { background-color: #81a1c1; color: #2e3440; font-weight: bold; padding: 8px; } "
            "QPushButton:hover { background-color: #88c0d0; }"
        )
        prio_row.addWidget(self.lbl_prio_status)
        prio_row.addStretch()
        prio_row.addWidget(self.btn_vr_priority)
        prio_layout.addLayout(prio_row)

        # Kompakte Latenz-Tipps direkt unter der VR-Priorität
        self.lbl_perf_tips = QLabel(tr("perf_tips"))
        self.lbl_perf_tips.setStyleSheet(
            "color: #d8dee9; font-size: 11px; background-color: #2e3440; "
            "border-radius: 4px; padding: 8px;")
        self.lbl_perf_tips.setWordWrap(True)
        self.lbl_perf_tips.setTextFormat(Qt.RichText)
        prio_layout.addWidget(self.lbl_perf_tips)

        layout.addWidget(self.prio_group)
        # --- GRUPPE 4: OPENXR RUNTIME ---
        self.openxr_group = QGroupBox(tr("streaming_openxr"))
        openxr_layout = QFormLayout(self.openxr_group)

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

        self.lbl_status_title = QLabel(tr("streaming_status"))
        openxr_layout.addRow(self.lbl_status_title, self.lbl_active_runtime)
        openxr_layout.addRow(self.btn_switch_wivrn)
        openxr_layout.addRow(self.btn_switch_steamvr)

        layout.addWidget(self.openxr_group)

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

        # VR-Priorität (CAP_SYS_NICE)
        self.btn_vr_priority.clicked.connect(self.enable_vr_priority)
        self.check_vr_priority()

    def retranslate(self):
        """Setzt alle statischen Texte des Streaming-Tabs neu (nach Sprachwechsel)."""
        self.lbl_title.setText(tr("streaming_title"))
        self.compat_group.setTitle(tr("streaming_compat"))
        self.lbl_openvr.setText(tr("streaming_openvr"))
        self.video_group.setTitle(tr("streaming_video"))
        self.lbl_res_title.setText(tr("streaming_res"))
        self.lbl_fov_title.setText(tr("streaming_fov"))
        self.encoder_group.setTitle(tr("streaming_encoder_grp"))
        self.lbl_encoder.setText(tr("streaming_encoder"))
        self.lbl_codec.setText(tr("streaming_codec"))
        self.lbl_bitrate.setText(tr("streaming_bitrate"))
        self.openxr_group.setTitle(tr("streaming_openxr"))
        self.lbl_status_title.setText(tr("streaming_status"))
        self.btn_switch_wivrn.setText(tr("streaming_wivrn_btn"))
        self.btn_switch_steamvr.setText(tr("streaming_steam_btn"))
        self.prio_group.setTitle(tr("streaming_prio"))
        self.lbl_prio_desc.setText(tr("streaming_prio_desc"))
        self.btn_vr_priority.setText(tr("streaming_prio_btn"))
        self.lbl_perf_tips.setText(tr("perf_tips"))
        # Aktiven Runtime-Status neu prüfen/setzen (Text ist sprachabhängig)
        self.check_active_openxr_runtime()
        self.check_vr_priority()

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
        choice = "opencomposite" if selected_text == "opencomposite" else "xrizer"

        target_path = venv.openvr_compat_path(choice)
        wivrn_config_file = venv.wivrn_config_file()

        if os.path.exists(wivrn_config_file):
            try:
                with open(wivrn_config_file, "r") as f:
                    wivrn_data = json.load(f)

                wivrn_data["openvr-compat-path"] = target_path
                print(f"[Streaming Tab] openvr-compat-path -> '{target_path}'.")

                with open(wivrn_config_file, "w") as f:
                    json.dump(wivrn_data, f, indent=4)
            except Exception as e:
                print(f"[Fehler] Konnte WiVRn-config.json nicht aktualisieren: {e}")
        else:
            print(f"[Fehler] WiVRn config.json nicht gefunden unter {wivrn_config_file}.")

        self.trigger_auto_save()

    def check_active_openxr_runtime(self):
        """Prüft, welche OpenXR Runtime aktuell im System aktiv ist."""
        try:
            active_json = os.path.expanduser("~/.config/openxr/1/active_runtime.json")
            if os.path.exists(active_json):
                with open(active_json, "r") as f:
                    content = f.read()
                    if "wivrn" in content.lower():
                        self.lbl_active_runtime.setText(tr("streaming_rt_wivrn"))
                        self.lbl_active_runtime.setStyleSheet("font-weight: bold; color: #a3be8c; font-size: 13px;")
                    elif "steamvr" in content.lower():
                        self.lbl_active_runtime.setText(tr("streaming_rt_steamvr"))
                        self.lbl_active_runtime.setStyleSheet("font-weight: bold; color: #81a1c1; font-size: 13px;")
                    else:
                        self.lbl_active_runtime.setText(tr("streaming_rt_other"))
                        self.lbl_active_runtime.setStyleSheet("font-weight: bold; color: #ebcb8b; font-size: 13px;")
            else:
                self.lbl_active_runtime.setText(tr("streaming_rt_none"))
                self.lbl_active_runtime.setStyleSheet("font-weight: bold; color: #bf616a; font-size: 13px;")
        except Exception as e:
            self.lbl_active_runtime.setText(tr("streaming_rt_error") + str(e))

    def set_openxr_runtime_wivrn(self):
        """Schaltet die OpenXR Runtime auf WiVRn um (Host + Steam-Flatpak-Sandbox)."""
        try:
            wivrn_runtime_path = venv.find_wivrn_manifest()
            data = {"file_format_version": "1.0.0", "runtime": {"library_path": wivrn_runtime_path}}
            for d in venv.openxr_config_dirs():
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, "active_runtime.json"), "w") as f:
                    json.dump(data, f, indent=4)

            self.check_active_openxr_runtime()
            QMessageBox.information(self, tr("streaming_rt_switched"), tr("streaming_rt_wivrn_ok"))
        except Exception as e:
            QMessageBox.critical(self, tr("error"), tr("streaming_rt_switch_err") + str(e))

    def set_openxr_runtime_steamvr(self):
        """Schaltet die OpenXR Runtime auf SteamVR um (Host + Steam-Flatpak-Sandbox)."""
        try:
            steamvr_runtime_path = venv.find_steamvr_manifest()
            data = {"file_format_version": "1.0.0", "runtime": {"library_path": steamvr_runtime_path}}
            for d in venv.openxr_config_dirs():
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, "active_runtime.json"), "w") as f:
                    json.dump(data, f, indent=4)

            self.check_active_openxr_runtime()
            QMessageBox.information(self, tr("streaming_rt_switched"), tr("streaming_rt_steam_ok"))
        except Exception as e:
            QMessageBox.critical(self, tr("error"), tr("streaming_rt_switch_err") + str(e))

    def _wivrn_server_path(self):
        """Findet die wivrn-server-Binary (Symlinks aufgelöst). None, wenn nicht da."""
        return venv.wivrn_server_binary()

    def check_vr_priority(self):
        """Prüft, ob die wivrn-server-Binary bereits CAP_SYS_NICE besitzt."""
        path = self._wivrn_server_path()
        if not path:
            self.lbl_prio_status.setText(tr("streaming_prio_missing"))
            self.lbl_prio_status.setStyleSheet("font-weight: bold; color: #bf616a; font-size: 13px;")
            self.btn_vr_priority.setEnabled(False)
            return

        # Bei Nix (read-only /nix/store) ist setcap nicht möglich
        if not venv.supports_setcap():
            self.lbl_prio_status.setText(tr("streaming_prio_unsupported"))
            self.lbl_prio_status.setStyleSheet("font-weight: bold; color: #ebcb8b; font-size: 13px;")
            self.btn_vr_priority.setEnabled(False)
            return

        try:
            res = subprocess.run(["getcap", path], stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, text=True)
            has_cap = "cap_sys_nice" in res.stdout.lower()
        except Exception:
            has_cap = False

        if has_cap:
            self.lbl_prio_status.setText(tr("streaming_prio_on"))
            self.lbl_prio_status.setStyleSheet("font-weight: bold; color: #a3be8c; font-size: 13px;")
            self.btn_vr_priority.setEnabled(False)
        else:
            self.lbl_prio_status.setText(tr("streaming_prio_off"))
            self.lbl_prio_status.setStyleSheet("font-weight: bold; color: #ebcb8b; font-size: 13px;")
            self.btn_vr_priority.setEnabled(True)

    def enable_vr_priority(self):
        """Setzt CAP_SYS_NICE auf die wivrn-server-Binary (per pkexec)."""
        path = self._wivrn_server_path()
        if not path:
            QMessageBox.warning(self, tr("error"), tr("streaming_prio_missing"))
            return
        try:
            res = subprocess.run(
                ["pkexec", "setcap", "cap_sys_nice+ep", path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                QMessageBox.information(self, tr("streaming_prio_ok_title"),
                                        tr("streaming_prio_ok_text"))
            else:
                QMessageBox.critical(self, tr("error"),
                                     tr("streaming_prio_err") + "\n\n" + (res.stderr or "").strip())
        except Exception as e:
            QMessageBox.critical(self, tr("error"),
                                 tr("streaming_prio_err") + "\n\n" + str(e))
        self.check_vr_priority()

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
