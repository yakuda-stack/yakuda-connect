#!/usr/bin/env python3
"""
core/tabs/app_profiles_mixin.py — App-Profile in der Oberflaeche
================================================================
* Sidebar unten links: Profil waehlen, „💾 Profil speichern …“, „— kein
  Profil —“, 🗑 rechts im Eintrag loescht ein Profil. Der 💾-Knopf daneben
  speichert das aktive Profil (ohne aktives Profil: neues anlegen).
* Einstellungen → Allgemein → Profile: Ordner oeffnen, aktives Profil
  umbenennen / kopieren / loeschen / exportieren, Profil importieren,
  „Beim Schliessen speichern“.
* Streaming → Autostart-Profile: Schalter, ob diese zum App-Profil gehoeren.

Ein anderes Profil laden heisst: merken, App neu starten, die neue App
spielt es beim Start ein (app_profiles.apply_pending in VRApp.__init__).
"""
import os

from PySide6.QtCore import QEvent, QObject, QRect, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QFileDialog, QInputDialog, QLineEdit, QMessageBox,
                               QStyledItemDelegate)

import app_profiles
from logging_setup import get_logger
from translations import tr

log = get_logger("app_profiles_ui")

SAVE_NEW = "__save__"
NO_PROFILE = ""
TRASH = "🗑"
TRASH_WIDTH = 30


def _is_profile_item(data):
    return isinstance(data, str) and data not in (SAVE_NEW, NO_PROFILE)


class _TrashDelegate(QStyledItemDelegate):
    """Malt ein 🗑 rechts in jeden Profil-Eintrag der Aufklappliste."""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if _is_profile_item(index.data(Qt.UserRole)):
            r = option.rect
            painter.drawText(QRect(r.right() - TRASH_WIDTH, r.top(), TRASH_WIDTH, r.height()),
                             Qt.AlignCenter, TRASH)


class _TrashClickFilter(QObject):
    """Klick auf das 🗑 einer Zeile: loeschen statt auswaehlen."""

    def __init__(self, view, on_delete):
        super().__init__(view)
        self._view = view
        self._on_delete = on_delete

    def eventFilter(self, obj, event):
        if event.type() not in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            return False
        pos = event.position().toPoint()
        if pos.x() < obj.width() - TRASH_WIDTH:
            return False
        index = self._view.indexAt(pos)
        name = index.data(Qt.UserRole) if index.isValid() else None
        if not _is_profile_item(name):
            return False
        if event.type() == QEvent.MouseButtonRelease:
            self._on_delete(name)
        return True


class AppProfilesMixin:

    # ------------------------------------------------------------------ #
    #  Aufbau
    # ------------------------------------------------------------------ #
    def setup_app_profiles(self):
        ui = self.ui
        combo = ui.combo_app_profile
        combo.setItemDelegate(_TrashDelegate(combo))
        view = combo.view()
        self._app_profile_trash_filter = _TrashClickFilter(view, self._delete_app_profile_from_list)
        view.viewport().installEventFilter(self._app_profile_trash_filter)
        combo.activated.connect(self._on_app_profile_activated)
        ui.btn_app_profile_save.clicked.connect(self._on_app_profile_save_clicked)

        actions = {
            "open": self._open_app_profiles_folder,
            "rename": self._rename_active_app_profile,
            "copy": self._copy_active_app_profile,
            "delete": self._delete_active_app_profile,
            "export": self._export_active_app_profile,
            "import": self._import_app_profile,
        }
        for key, fn in actions.items():
            ui.app_profile_buttons[key].clicked.connect(lambda checked=False, f=fn: f())

        ui.toggle_app_profile_autosave.setChecked(app_profiles.autosave_enabled())
        ui.toggle_app_profile_autosave.toggled.connect(app_profiles.set_autosave)
        if hasattr(ui, "toggle_autostart_in_app_profile"):
            ui.toggle_autostart_in_app_profile.setChecked(app_profiles.autostart_in_profile())
            ui.toggle_autostart_in_app_profile.toggled.connect(app_profiles.set_autostart_in_profile)
        self.refresh_app_profiles()

    def refresh_app_profiles(self):
        """Aufklappliste neu fuellen und das aktive Profil auswaehlen."""
        combo = self.ui.combo_app_profile
        active = app_profiles.active_profile()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("💾 " + tr("app_profile_save_new"), SAVE_NEW)
        combo.addItem(tr("app_profile_none"), NO_PROFILE)
        for name in app_profiles.list_profiles():
            combo.addItem(name, name)
        combo.setCurrentIndex(combo.findData(active) if active else 1)
        combo.blockSignals(False)
        has_active = bool(active)
        for key in ("rename", "copy", "delete", "export"):
            self.ui.app_profile_buttons[key].setEnabled(has_active)

    # ------------------------------------------------------------------ #
    #  Sidebar
    # ------------------------------------------------------------------ #
    def _on_app_profile_activated(self, index):
        data = self.ui.combo_app_profile.itemData(index)
        active = app_profiles.active_profile()
        if data == SAVE_NEW:
            self.refresh_app_profiles()
            self._save_new_app_profile()
        elif data == NO_PROFILE:
            if active:
                app_profiles.set_active("")
            self.refresh_app_profiles()
        elif data != active:
            self.refresh_app_profiles()
            self._switch_app_profile(data)

    def _on_app_profile_save_clicked(self):
        active = app_profiles.active_profile()
        if not active:
            self._save_new_app_profile()
            return
        if app_profiles.save_profile(active):
            QMessageBox.information(self, tr("app_profiles_group"),
                                    tr("app_profile_saved").format(name=active))
        else:
            QMessageBox.warning(self, tr("app_profiles_group"), tr("app_profile_failed"))

    def _ask_app_profile_name(self, title, text, default=""):
        """Name abfragen, pruefen und Ueberschreiben bestaetigen. '' = abgebrochen."""
        while True:
            name, ok = QInputDialog.getText(self, title, text, QLineEdit.Normal, default)
            if not ok:
                return ""
            name = name.strip()
            if not app_profiles.valid_name(name):
                QMessageBox.warning(self, title, tr("app_profile_name_invalid"))
                default = name
                continue
            return name

    def _save_new_app_profile(self):
        name = self._ask_app_profile_name(tr("app_profile_save_new"), tr("app_profile_name_prompt"))
        if not name:
            return
        if app_profiles.exists(name) and QMessageBox.question(
                self, tr("app_profile_save_new"),
                tr("app_profile_overwrite").format(name=name),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if not app_profiles.save_profile(name):
            QMessageBox.warning(self, tr("app_profiles_group"), tr("app_profile_failed"))
            return
        app_profiles.set_active(name)
        self.refresh_app_profiles()

    def _switch_app_profile(self, name):
        if QMessageBox.question(
                self, tr("app_profile_switch_title"),
                tr("app_profile_switch_text").format(name=name),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) != QMessageBox.Yes:
            return
        active = app_profiles.active_profile()
        if active and app_profiles.autosave_enabled():
            app_profiles.save_profile(active)
        if not app_profiles.request_switch(name):
            QMessageBox.warning(self, tr("app_profiles_group"), tr("app_profile_failed"))
            return
        log.info("[Profil] Wechsel zu %s, App startet neu.", name)
        self.is_loading = True
        self._restart_app()

    def _delete_app_profile_from_list(self, name):
        self.ui.combo_app_profile.hidePopup()
        self._delete_app_profile(name)

    def _delete_app_profile(self, name):
        if QMessageBox.question(
                self, tr("app_profiles_btn_delete"),
                tr("app_profile_delete_confirm").format(name=name),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if not app_profiles.delete_profile(name):
            QMessageBox.warning(self, tr("app_profiles_group"), tr("app_profile_failed"))
        self.refresh_app_profiles()

    # ------------------------------------------------------------------ #
    #  Einstellungen → Allgemein → Profile
    # ------------------------------------------------------------------ #
    def _open_app_profiles_folder(self):
        folder = app_profiles.profiles_dir()
        os.makedirs(folder, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _rename_active_app_profile(self):
        active = app_profiles.active_profile()
        if not active:
            return
        name = self._ask_app_profile_name(tr("app_profiles_btn_rename"),
                                          tr("app_profile_name_prompt"), active)
        if not name or name == active:
            return
        if app_profiles.exists(name):
            QMessageBox.warning(self, tr("app_profiles_btn_rename"),
                                tr("app_profile_exists").format(name=name))
            return
        if not app_profiles.rename_profile(active, name):
            QMessageBox.warning(self, tr("app_profiles_group"), tr("app_profile_failed"))
        self.refresh_app_profiles()

    def _copy_active_app_profile(self):
        active = app_profiles.active_profile()
        if not active:
            return
        name = self._ask_app_profile_name(tr("app_profiles_btn_copy"),
                                          tr("app_profile_copy_prompt"),
                                          tr("app_profile_copy_default").format(name=active))
        if not name:
            return
        if app_profiles.exists(name):
            QMessageBox.warning(self, tr("app_profiles_btn_copy"),
                                tr("app_profile_exists").format(name=name))
            return
        if not app_profiles.copy_profile(active, name):
            QMessageBox.warning(self, tr("app_profiles_group"), tr("app_profile_failed"))
        self.refresh_app_profiles()

    def _delete_active_app_profile(self):
        active = app_profiles.active_profile()
        if active:
            self._delete_app_profile(active)

    def _export_active_app_profile(self):
        active = app_profiles.active_profile()
        if not active:
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, tr("app_profiles_btn_export"),
            os.path.join(os.path.expanduser("~"), active + app_profiles.PROFILE_EXT),
            "JSON (*.json)")
        if dest and not app_profiles.export_profile(active, dest):
            QMessageBox.warning(self, tr("app_profiles_group"), tr("app_profile_failed"))

    def _import_app_profile(self):
        src, _ = QFileDialog.getOpenFileName(self, tr("app_profiles_btn_import"),
                                             os.path.expanduser("~"), "JSON (*.json)")
        if not src:
            return
        name = app_profiles.import_name(src)
        if not name:
            QMessageBox.warning(self, tr("app_profiles_btn_import"), tr("app_profile_import_invalid"))
            return
        while app_profiles.exists(name):
            name = self._ask_app_profile_name(tr("app_profiles_btn_import"),
                                              tr("app_profile_exists").format(name=name), name)
            if not name:
                return
        if not app_profiles.import_profile(src, name):
            QMessageBox.warning(self, tr("app_profiles_group"), tr("app_profile_failed"))
        self.refresh_app_profiles()

    # ------------------------------------------------------------------ #
    #  Beim Schliessen
    # ------------------------------------------------------------------ #
    def autosave_app_profile_on_close(self):
        try:
            active = app_profiles.active_profile()
            if active and app_profiles.autosave_enabled():
                app_profiles.save_profile(active)
        except Exception:
            log.exception("Profil beim Schliessen nicht gespeichert")
