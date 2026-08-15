#!/usr/bin/env python3
import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QComboBox, QSlider, QGroupBox, QFormLayout,
                               QPushButton, QFileDialog, QMessageBox)
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
        # Eigener OpenVR-Pfad (Auswahl "Eigener Pfad…"). Muss VOR init_ui
        # stehen: der Aufbau der Auswahlliste liest ihn bereits.
        self._custom_openvr_path = ""
        self._openvr_found = []
        # Zuletzt erfolgreich angewandte Auswahl. Bricht der Nutzer die
        # Ordnerauswahl ab, springt die Liste hierhin zurueck statt auf
        # "Eigener Pfad…" stehen zu bleiben.
        self._openvr_applied_key = "default"
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
        openvr_val = data.get("openvr_compat", "default")
        self._custom_openvr_path = data.get("openvr_compat_custom", "") or ""
        res_val = data.get("render_resolution", 100)
        fov_val = data.get("foveated_encoding", 50)
        encoder_val = data.get("encoder", "Auto")
        codec_val = data.get("codec", "Automatic")
        bitrate_val = data.get("bitrate", 100)

        # UI-Elemente auf die gespeicherten Werte setzen.
        # Die WAHRHEIT ist WiVRns config.json, nicht unsere: der Nutzer kann
        # den Wert auch im WiVRn-Dashboard oder von Hand geändert haben.
        # Unsere gespeicherte Auswahl dient nur als Rückfall, wenn dort
        # nichts steht.
        mode, path = venv.current_openvr_compat()
        if mode == venv.OPENVR_PATH:
            openvr_val = f"path:{path}"
        elif mode == venv.OPENVR_DISABLED:
            openvr_val = "disabled"
        elif not openvr_val or openvr_val in ("Auto", "auto"):
            openvr_val = "default"
        self._openvr_applied_key = self._migrate_key(openvr_val)
        self.reload_openvr_options(select=self._openvr_applied_key)

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

        # Auswahlliste wird zur Laufzeit gefüllt (reload_openvr_options):
        # angeboten wird nur, was auch wirklich installiert ist — nicht
        # gefundene Backends stehen ausgegraut daneben, damit sichtbar bleibt,
        # dass es sie gibt.
        openvr_row = QHBoxLayout()
        self.combo_openvr = QComboBox()
        self.combo_openvr.setMinimumWidth(260)

        self.btn_openvr_rescan = QPushButton("⟳")
        self.btn_openvr_rescan.setToolTip(tr("streaming_openvr_rescan_tip"))
        self.btn_openvr_rescan.setFixedWidth(34)
        self.btn_openvr_rescan.setCursor(Qt.PointingHandCursor)
        self.btn_openvr_rescan.setStyleSheet(
            "QPushButton { background-color:#434c5e; color:#eceff4; border:none;"
            " font-weight:bold; border-radius:4px; padding:4px; }"
            " QPushButton:hover { background-color:#5e81ac; }")
        self.btn_openvr_rescan.clicked.connect(lambda: self.reload_openvr_options())

        openvr_row.addWidget(self.combo_openvr)
        openvr_row.addWidget(self.btn_openvr_rescan)
        openvr_row.addStretch()

        self.lbl_openvr = QLabel(tr("streaming_openvr"))
        compat_form.addRow(self.lbl_openvr, openvr_row)

        # Zeigt, was WiVRn gerade wirklich benutzt — die Auswahl oben ist
        # unsere Sicht, diese Zeile die Wahrheit aus WiVRns config.json.
        self.lbl_openvr_active = QLabel("")
        self.lbl_openvr_active.setWordWrap(True)
        self.lbl_openvr_active.setStyleSheet("color:#7b88a1; font-size:11px;")
        compat_form.addRow(self.lbl_openvr_active)

        layout.addWidget(self.compat_group)
        self.reload_openvr_options()

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

        # Laufzeit-Umschaltung NUR bei echter Nutzerauswahl (activated), nicht
        # bei jedem programmatischen Setzen — sonst schreibt schon das Laden
        # der Einstellungen in WiVRns config.json.
        self.combo_openvr.activated.connect(self.apply_openvr_compatibility)
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
        self.btn_openvr_rescan.setToolTip(tr("streaming_openvr_rescan_tip"))
        self.reload_openvr_options()
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

    # ------------------------------------------------------------------ #
    #  OpenVR-Kompatibilität                                              #
    # ------------------------------------------------------------------ #
    #  Aufgebaut wie WiVRns eigene Auswahl (dashboard/qml/SettingsPage.qml
    #  + dashboard/settings.cpp):
    #
    #    Standard         -> Schlüssel wird entfernt, WiVRn sucht selbst
    #    <gefundener Ordner> -> genau dieser Pfad wird eingetragen
    #    Eigener Pfad…    -> Ordnerauswahl, '/bin' und '/linux64' werden
    #                        abgeschnitten (macht WiVRns Dashboard genauso)
    #    Deaktiviert      -> JSON null; WiVRn fasst OpenVR gar nicht an
    #
    #  Gelistet wird nur, was WIRKLICH existiert — eine Auswahl, die es auf
    #  dem System nicht gibt, hilft niemandem. Wo gesucht wurde, steht im
    #  Tooltip der Statuszeile.
    # ------------------------------------------------------------------ #
    def reload_openvr_options(self, select=None):
        """Baut die Auswahlliste aus dem aktuellen Systemzustand neu auf."""
        current = select if select is not None else self.current_openvr_key()

        self.combo_openvr.blockSignals(True)
        self.combo_openvr.clear()

        auto_path = venv.wivrn_autodetect_path()
        self.combo_openvr.addItem(tr("streaming_openvr_default"), "default")
        self.combo_openvr.setItemData(
            0,
            tr("streaming_openvr_default_tip").format(
                path=auto_path or tr("streaming_openvr_default_none")),
            Qt.ToolTipRole)

        self._openvr_found = venv.openvr_compat_candidates()
        for entry in self._openvr_found:
            label = f"{entry['label']}  ({entry['path']})"
            if not entry["complete"]:
                label += f"  ⚠ {tr('streaming_openvr_incomplete')}"
            tip = entry["path"] if entry["autodetect"] else \
                tr("streaming_openvr_outside_tip")
            self.combo_openvr.addItem(label, f"path:{entry['path']}")
            self.combo_openvr.setItemData(self.combo_openvr.count() - 1, tip,
                                          Qt.ToolTipRole)

        custom_label = tr("streaming_openvr_custom")
        if self._custom_openvr_path:
            custom_label = f"{custom_label}  ({self._custom_openvr_path})"
        self.combo_openvr.addItem(custom_label, "custom")
        self.combo_openvr.setItemData(self.combo_openvr.count() - 1,
                                      self._custom_openvr_path or tr("streaming_openvr_custom_tip"),
                                      Qt.ToolTipRole)

        self.combo_openvr.addItem(tr("streaming_openvr_off"), "disabled")
        self.combo_openvr.setItemData(self.combo_openvr.count() - 1,
                                      tr("streaming_openvr_off_tip"), Qt.ToolTipRole)

        self.select_openvr_key(current)
        self.combo_openvr.blockSignals(False)
        self.update_openvr_active_label()

    def current_openvr_key(self):
        """Schlüssel des ausgewählten Eintrags ('default', 'path:/opt/...')."""
        data = self.combo_openvr.currentData()
        return data if data else "default"

    def select_openvr_key(self, key):
        """
        Eintrag anhand des Schlüssels wählen — nicht anhand des Anzeigetexts,
        der ändert sich mit Sprache und Fundstatus.

        Ein gespeicherter Pfad, der nicht (mehr) in der Liste steht, landet
        auf "Eigener Pfad…" — genauso macht es WiVRns Dashboard.
        """
        key = self._migrate_key(key)
        index = self.combo_openvr.findData(key)
        if index < 0 and key.startswith("path:"):
            self._custom_openvr_path = key[len("path:"):]
            index = self.combo_openvr.findData("custom")
        self.combo_openvr.setCurrentIndex(max(index, 0))

    @staticmethod
    def _migrate_key(key):
        """
        Alte gespeicherte Werte auf die neuen Schlüssel abbilden.

        Bis v1.1.6 stand in der Config "Auto", "xrizer" oder "opencomposite".
        Aus einem Werkzeugnamen wird der Pfad, an dem er jetzt gefunden wird —
        ist er weg, bleibt "Standard" übrig statt eines toten Eintrags.
        """
        if not key or key in ("Auto", "auto"):
            return "default"
        if key in ("none", "off"):
            return "disabled"
        if key in ("default", "disabled", "custom") or key.startswith("path:"):
            return key
        found = venv.find_openvr_compat(key)
        return f"path:{found}" if found else "default"

    def update_openvr_active_label(self):
        """Zeigt, was tatsächlich in WiVRns config.json steht."""
        mode, path = venv.current_openvr_compat()
        if mode == venv.OPENVR_DISABLED:
            text = tr("streaming_openvr_active_off")
        elif mode == venv.OPENVR_DEFAULT:
            auto_path = venv.wivrn_autodetect_path()
            text = tr("streaming_openvr_active_default").format(
                path=auto_path or tr("streaming_openvr_default_none"))
        else:
            text = tr("streaming_openvr_active").format(path=path)
            if not venv.looks_like_openvr_compat(path):
                text += f"  ⚠ {tr('streaming_openvr_active_broken')}"
        self.lbl_openvr_active.setText(f"{text}\n{tr('streaming_openvr_restart_hint')}")

    def apply_openvr_compatibility(self, *_args):
        """Setzt die Auswahl in WiVRns config.json um und speichert sie."""
        choice = self.current_openvr_key()

        if choice == "custom":
            folder = QFileDialog.getExistingDirectory(
                self, tr("streaming_openvr_custom_pick"),
                self._custom_openvr_path or os.path.expanduser("~"))
            if not folder:
                self.reload_openvr_options(select=self._openvr_applied_key)
                return
            # '/bin' und '/linux64' abschneiden: im Dateidialog landet man
            # fast zwangsläufig eine Ebene zu tief.
            folder = venv.normalize_compat_path(folder)
            if not venv.looks_like_openvr_compat(folder):
                # WiVRn selbst bricht hier NICHT ab, es schreibt nur eine
                # Warnung ins Log. Also fragen statt verbieten — es kann eine
                # ungewöhnliche, aber gültige Installation sein.
                answer = QMessageBox.question(
                    self, tr("streaming_openvr_custom_pick"),
                    tr("streaming_openvr_custom_invalid").format(
                        path=folder, file=venv.openvr_lib_file(folder)),
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if answer != QMessageBox.Yes:
                    self.reload_openvr_options(select=self._openvr_applied_key)
                    return
            self._custom_openvr_path = folder
            ok = venv.set_openvr_compat(venv.OPENVR_PATH, folder)
        elif choice == "disabled":
            ok = venv.set_openvr_compat(venv.OPENVR_DISABLED)
        elif choice.startswith("path:"):
            ok = venv.set_openvr_compat(venv.OPENVR_PATH, choice[len("path:"):])
        else:
            ok = venv.set_openvr_compat(venv.OPENVR_DEFAULT)

        if not ok:
            QMessageBox.warning(self, tr("streaming_openvr"),
                                tr("streaming_openvr_write_failed").format(
                                    path=venv.wivrn_config_file()))

        self._openvr_applied_key = self.current_openvr_key()
        self.reload_openvr_options(select=self._openvr_applied_key)
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
            "openvr_compat": self.current_openvr_key(),
            "openvr_compat_custom": self._custom_openvr_path,
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
        # refresh_rate hat kein Bedienelement mehr (wird im Headset gesetzt);
        # der gespeicherte Wert wird nur durchgereicht.
        refresh = getattr(self.main_app, "_stored_refresh_rate", "Auto")
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
