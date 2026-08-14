#!/usr/bin/env python3
"""
core/tabs/tools_mixin.py — Tools-Tab
====================================
Ausgelagert aus core/main.py (siehe games_mixin.py fuer die Begruendung).

Zustaendig fuer: Statuskarten der VR-Zusatzprogramme (WayVR, VRCX,
ProtonPlus, OSC-DreamChatbox, OSC Leash ...), Installation und Entfernung
ueber AppImage, Flatpak oder Paketmanager, sowie den Update-Check.

Auch das ist ein MIXIN — self.ui und die Worker-Attribute stammen aus VRApp.
"""

from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import QThread, Signal as QtSignal

import appimage_installer as appimg
import paths
from appimage_installer import AppImageInstallWorker
from install_worker import InstallWorker, RemoveWorker
from jsonio import read_json, write_json_atomic
from translations import tr

from logging_setup import get_logger

log = get_logger("tools_tab")


# --------------------------------------------------------------------------- #
#  Hintergrund-Worker des Tools-Tabs
# --------------------------------------------------------------------------- #
# Umgezogen aus core/main.py — siehe games_mixin.py zur Begruendung.

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


class ToolsTabMixin:
    """Alles rund um den Tools-Tab. Wird von VRApp geerbt."""

    def check_tools_status(self):
        """Lädt den Status aus dem Cache (programs.json) und zeigt ihn sofort an."""
        cache = self._load_programs_cache()
        for key, card in self.ui.tool_cards.items():
            entry = cache.get(key)
            if entry is None:
                card["lbl_status"].setText(tr("tools_unknown"))
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
            card["lbl_update"].setText(tr("tools_update") if pm_upd else "")
            st.setText(tr("tools_pm_ok").format(helper=pm_helper))
            st.setStyleSheet("color: #a3be8c; font-size: 12px; font-weight: bold;")
            # Per yay/paru installiert -> der Knopf wird zum Löschen-Knopf.
            # Nach dem Entfernen erkennt _refresh_single_tool (yay -Q) den
            # neuen Zustand und die Karte springt auf 'Nicht installiert'.
            btn.setText(tr("tools_delete"))
            btn.setEnabled(True)
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
        self.ui.btn_tools_check.setText("⏳ " + tr("tools_checking"))

        for key, card in self.ui.tool_cards.items():
            card["lbl_status"].setText(tr("tools_checking"))
            card["lbl_status"].setStyleSheet("color: #ebcb8b; font-size: 12px; font-style: italic;")

        tools = {key: card.get("tool", {"pkg": card["pkg"]})
                 for key, card in self.ui.tool_cards.items()}
        self._tools_status_worker = ToolsStatusWorker(tools)
        self._tools_status_worker.result_signal.connect(self._apply_tool_status)
        self._tools_status_worker.finished.connect(self._on_tools_check_done)
        self._tools_status_worker.start()

    def _on_tools_check_done(self):
        self.ui.btn_tools_check.setEnabled(True)
        self.ui.btn_tools_check.setText(tr("tools_check_btn"))
        self._tools_status_worker = None

    def _load_programs_cache(self) -> dict:
        """Gemerkte Tool-Versionen (verhindert, dass beim Start alles neu
        vom Netz geprüft werden muss)."""
        data = read_json(paths.config_file("programs.json"), default={})
        return data if isinstance(data, dict) else {}

    def _save_programs_cache(self, data: dict):
        if not write_json_atomic(paths.config_file("programs.json"), data):
            log.warning("programs.json konnte nicht geschrieben werden.")

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
        elif status.get("pm_installed"):
            # Per yay/paru installiert -> Paket entfernen
            self.remove_tool_pm(key)
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
            log.warning(f"[AppImage] Löschen fehlgeschlagen: {e}")

        # Config-Ordner nur auf Wunsch
        if also_config:
            try:
                appimg.delete_config(tool)
            except Exception as e:
                log.warning(f"[AppImage] Config-Löschen fehlgeschlagen: {e}")

        # Status frisch berechnen und anzeigen
        self._refresh_single_tool(key)

    def remove_tool_pm(self, key):
        """
        Entfernt ein per yay/paru installiertes Tool (Tools-Tab, 'Löschen').

        Öffnet ein Terminal mit '{helper} -Rns {pkg}' (sudo-Passwort + Übersicht
        für den Nutzer). Danach wird der Status neu berechnet — yay -Q schlägt
        dann fehl und die Karte springt auf 'Nicht installiert'.
        """
        card = self.ui.tool_cards.get(key)
        if not card:
            return
        tool = card.get("tool", {})
        status = card.get("status", {}) or {}
        name = tool.get("name", key)
        pkg = tool.get("pkg") or card.get("pkg")
        helper = status.get("pm_helper") or "yay"
        if not pkg:
            return

        # Bestätigung vor dem Entfernen
        reply = QMessageBox.question(
            self, tr("tools_pm_remove_title"),
            tr("tools_pm_remove_text").format(name=name, pkg=pkg, helper=helper),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        # Optional den Config-Ordner mit entfernen (wie beim AppImage-Löschen)
        also_config = False
        if tool.get("config_dirs"):
            hint = appimg.config_path_hint(tool)
            path = f" ({hint})" if hint else ""
            reply = QMessageBox.question(
                self, tr("tools_delete_config_title"),
                tr("tools_delete_config_text").format(name=name, path=path),
                QMessageBox.Yes | QMessageBox.No)
            also_config = (reply == QMessageBox.Yes)

        card["btn_install"].setEnabled(False)
        card["btn_install"].setText(tr("tools_deleting"))
        card["lbl_status"].setText("⏳ ...")
        card["lbl_status"].setStyleSheet("color: #ebcb8b; font-size: 12px;")

        self.tool_worker = RemoveWorker([pkg], helper=helper)
        self.tool_worker.finished_signal.connect(
            lambda success, k=key, cfg=also_config: self._on_tool_removed(k, success, cfg)
        )
        self.tool_worker.start()

    def _on_tool_removed(self, key, success, also_config):
        """Callback nach dem Terminal-Entfernen: Config löschen (optional) + Status neu."""
        card = self.ui.tool_cards.get(key)
        if not card:
            return
        tool = card.get("tool", {})
        if success and also_config:
            try:
                appimg.delete_config(tool)
            except Exception as e:
                log.warning(f"[Tools] Config-Löschen fehlgeschlagen: {e}")
        # Immer neu prüfen — auch bei Abbruch im Terminal zeigt die Karte
        # danach den echten Zustand (yay -Q entscheidet, nicht der Returncode).
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
