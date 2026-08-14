#!/usr/bin/env python3
import os
import json
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QComboBox, QSlider, QGroupBox, QFormLayout,
                               QPushButton)
from PySide6.QtCore import Qt

# Importiert aus dem selben Verzeichnis (core)
from config_manager import save_all_settings, load_saved_settings
from translations import tr, tr_amp
import vr_environment as venv

from logging_setup import get_logger

log = get_logger("streaming_tab")




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
        self.compat_group = QGroupBox(tr_amp("streaming_compat"))
        compat_form = QFormLayout(self.compat_group)

        self.combo_openvr = QComboBox()
        self.combo_openvr.addItems(["Auto", "xrizer", "opencomposite"])

        self.lbl_openvr = QLabel(tr("streaming_openvr"))
        compat_form.addRow(self.lbl_openvr, self.combo_openvr)
        layout.addWidget(self.compat_group)

        # --- GRUPPE 2: GRAFIK & AUFLÖSUNG ---
        self.video_group = QGroupBox(tr_amp("streaming_video"))
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
        self.encoder_group = QGroupBox(tr_amp("streaming_encoder_grp"))
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

        # --- HINWEIS: OpenXR-Runtime + VR-Prioritaet sind umgezogen ----------
        # Beides sind einmalige System-Reparaturen, keine Stream-Einstellungen.
        # Sie liegen jetzt bei den uebrigen Fixes unter Einstellungen -> VR &
        # OpenXR. Damit niemand suchen muss, bleibt hier ein Verweis mit
        # Sprungknopf stehen.
        moved_row = QHBoxLayout()
        self.lbl_moved_hint = QLabel(tr("streaming_moved_hint"))
        self.lbl_moved_hint.setWordWrap(True)
        self.lbl_moved_hint.setStyleSheet("color:#7b88a1; font-size:11px;")
        self.btn_goto_vr_settings = QPushButton(tr_amp("dashboard_openxr_btn"))
        self.btn_goto_vr_settings.setCursor(Qt.PointingHandCursor)
        self.btn_goto_vr_settings.setStyleSheet(
            "QPushButton { background-color:#2e3440; color:#d8dee9; border:1px solid #4c566a;"
            " font-weight:bold; padding:8px 14px; border-radius:4px; font-size:12px; }"
            " QPushButton:hover { background-color:#3b4252; border-color:#5e81ac; }")
        self.btn_goto_vr_settings.clicked.connect(self.open_vr_settings)
        moved_row.addWidget(self.lbl_moved_hint, 1)
        moved_row.addWidget(self.btn_goto_vr_settings)
        layout.addLayout(moved_row)

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


    def retranslate(self):
        """Setzt alle statischen Texte des Streaming-Tabs neu (nach Sprachwechsel)."""
        self.lbl_title.setText(tr("streaming_title"))
        self.compat_group.setTitle(tr_amp("streaming_compat"))
        self.lbl_openvr.setText(tr("streaming_openvr"))
        self.video_group.setTitle(tr_amp("streaming_video"))
        self.lbl_res_title.setText(tr("streaming_res"))
        self.lbl_fov_title.setText(tr("streaming_fov"))
        self.encoder_group.setTitle(tr_amp("streaming_encoder_grp"))
        self.lbl_encoder.setText(tr("streaming_encoder"))
        self.lbl_codec.setText(tr("streaming_codec"))
        self.lbl_bitrate.setText(tr("streaming_bitrate"))
        self.lbl_moved_hint.setText(tr("streaming_moved_hint"))
        self.btn_goto_vr_settings.setText(tr_amp("dashboard_openxr_btn"))

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
                with open(wivrn_config_file) as f:
                    wivrn_data = json.load(f)

                wivrn_data["openvr-compat-path"] = target_path
                log.info(f"[Streaming Tab] openvr-compat-path -> '{target_path}'.")

                with open(wivrn_config_file, "w") as f:
                    json.dump(wivrn_data, f, indent=4)
            except Exception as e:
                log.warning(f"[Fehler] Konnte WiVRn-config.json nicht aktualisieren: {e}")
        else:
            log.warning(f"[Fehler] WiVRn config.json nicht gefunden unter {wivrn_config_file}.")

        self.trigger_auto_save()

    def open_vr_settings(self):
        """Springt zu Einstellungen -> VR & OpenXR (dort liegen Runtime-Wechsel,
        Steam-Fix und VR-Prioritaet)."""
        if self.main_app and hasattr(self.main_app, "open_vr_settings"):
            self.main_app.open_vr_settings()

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

        # Hand-/Full-Body-Tracking haben keine Schalter mehr im Dashboard —
        # die gespeicherten Werte werden unveraendert durchgereicht.
        hand, fbt = self.main_app.tracking_flags()
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
