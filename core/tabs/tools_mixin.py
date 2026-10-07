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

import os

from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import QThread, Signal as QtSignal

import appimage_installer as appimg
import paths
from appimage_installer import AppImageInstallWorker
import cargo_installer
from cargo_installer import CargoInstallWorker
from script_installer import ScriptInstallWorker
from install_worker import InstallWorker, RemoveWorker, RpmInstallWorker
from jsonio import read_json, write_json_atomic
from translations import tr, get_language

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

    # ------------------------------------------------------------------ #
    #  Filter: Suche / Kategorie / Installationsstatus
    # ------------------------------------------------------------------ #
    # Reihenfolge der Status-Auswahl. Der interne Schluessel wird ueber
    # QComboBox.currentData transportiert, damit ein Sprachwechsel die
    # getroffene Auswahl nicht verliert (die Beschriftung aendert sich, die
    # Daten nicht).
    TOOL_STATUS_FILTERS = ("all", "installed", "missing", "update")

    def setup_tools_filter(self):
        """Fuellt die beiden Auswahlfelder und haengt die Signale an."""
        ui = self.ui
        if not hasattr(ui, "tools_search"):
            return

        # Kategorien kommen aus den Tools selbst, nicht aus einer festen
        # Liste: ein neues Tool mit neuer Kategorie in der tools.json soll
        # ohne Code-Aenderung im Filter auftauchen.
        cats = sorted({c.get("category", "misc") for c in ui.tool_cards.values()})
        ui.tools_filter_category.blockSignals(True)
        ui.tools_filter_category.clear()
        ui.tools_filter_category.addItem(tr("tools_cat_all"), "all")
        for c in cats:
            # Unbekannte Kategorien bekommen ihren Rohnamen statt eines
            # leeren Eintrags — tr() liefert fuer fehlende Schluessel sonst
            # nichts Brauchbares.
            label = tr(f"tools_cat_{c}") or c
            if label == f"tools_cat_{c}":
                label = c
            ui.tools_filter_category.addItem(label, c)
        ui.tools_filter_category.blockSignals(False)

        ui.tools_filter_status.blockSignals(True)
        ui.tools_filter_status.clear()
        for key in self.TOOL_STATUS_FILTERS:
            ui.tools_filter_status.addItem(tr(f"tools_status_{key}"), key)
        ui.tools_filter_status.blockSignals(False)

        ui.tools_search.textChanged.connect(self.apply_tools_filter)
        ui.tools_filter_category.currentIndexChanged.connect(self.apply_tools_filter)
        ui.tools_filter_status.currentIndexChanged.connect(self.apply_tools_filter)
        self.apply_tools_filter()

    def _tool_install_state(self, card):
        """'installed' | 'update' | 'missing' fuer eine Karte.

        Gelesen wird der Status, den _render_tool_card zuletzt gesetzt hat.
        Bewusst kein eigener Check: der wuerde bei jedem Tastendruck im
        Suchfeld ueber alle Tools laufen.
        """
        st = card.get("status") or {}
        installed = (st.get("appimage_installed") or st.get("pm_installed")
                     or st.get("flatpak_installed") or st.get("cargo_installed"))
        if not installed:
            return "missing"
        if (st.get("appimage_has_update") or st.get("pm_has_update")
                or st.get("cargo_has_update")):
            return "update"
        return "installed"

    def apply_tools_filter(self):
        """Blendet die Tool-Karten nach Suchtext, Kategorie und Status ein/aus."""
        ui = self.ui
        if not hasattr(ui, "tools_search"):
            return
        needle = ui.tools_search.text().strip().lower()
        cat = ui.tools_filter_category.currentData() or "all"
        want = ui.tools_filter_status.currentData() or "all"
        lang = get_language()

        visible = {"apps": 0, "osc": 0}
        total = 0
        for key, card in ui.tool_cards.items():
            widget = card.get("card")
            if widget is None:
                continue
            total += 1
            tool = card.get("tool", {})

            # Gesucht wird ueber Name, Schluessel, Paketname UND Beschreibung.
            # Nur der Name waere zu wenig: wer "tracker" tippt, meint das
            # Thema, nicht ein Tool, das zufaellig so heisst.
            desc = tool.get("desc_eng", "") if lang == "en" else tool.get("desc", "")
            haystack = " ".join([
                str(tool.get("name", "")), str(key), str(tool.get("pkg", "")),
                str(card.get("category", "")), str(desc),
            ]).lower()

            ok = (not needle or needle in haystack)
            if ok and cat != "all":
                ok = card.get("category", "misc") == cat
            if ok and want != "all":
                state = self._tool_install_state(card)
                # "Installiert" schliesst Karten mit verfuegbarem Update ein —
                # die sind ja installiert. "Update verfuegbar" ist die
                # engere Auswahl darunter.
                ok = (state in ("installed", "update")) if want == "installed" \
                    else (state == want)

            widget.setVisible(ok)
            if ok:
                visible[card.get("page", "apps")] = visible.get(card.get("page", "apps"), 0) + 1

        shown = sum(visible.values())
        ui.lbl_tools_count.setText(tr("tools_filter_count").format(shown=shown, total=total))
        if hasattr(ui, "lbl_tools_empty_apps"):
            ui.lbl_tools_empty_apps.setVisible(visible.get("apps", 0) == 0)
        if hasattr(ui, "lbl_tools_empty_osc"):
            ui.lbl_tools_empty_osc.setVisible(visible.get("osc", 0) == 0)

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
        # Der Status-Filter arbeitet auf card["status"], das gerade neu
        # gesetzt wurde — ohne diesen Aufruf zeigte "Nicht installiert"
        # weiter den Stand von vor dem Cache-Laden.
        self.apply_tools_filter()

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
        cargo_inst    = status.get("cargo_installed", False)
        cargo_ver     = status.get("cargo_version", "")
        cargo_upd     = status.get("cargo_has_update", False)
        script_inst   = status.get("script_installed", False)
        config_ok     = status.get("config_present", False)

        methods = card.get("methods") or []
        combo = card.get("combo_method")

        btn = card["btn_install"]
        st = card["lbl_status"]

        # Dropdown nur zeigen, wenn Auswahl besteht UND noch installiert/aktualisiert werden kann
        show_combo = (combo is not None and len(methods) >= 2
                      and not appimage_inst and not pm_inst and not flatpak_inst
                      and not cargo_inst and not script_inst)
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

        elif cargo_inst:
            # Wie AppImage: liegt komplett im eigenen Tool-Ordner, also
            # Loeschen ohne sudo; bei neuer Version auf crates.io -> Update.
            card["lbl_version"].setText(f"v{cargo_ver}" if cargo_ver else "")
            st.setText(tr("tools_cargo_ok"))
            st.setStyleSheet("color: #a3be8c; font-size: 12px; font-weight: bold;")
            card["cmd_widget"].setVisible(True)
            if cargo_upd:
                card["lbl_update"].setText(tr("tools_update"))
                btn.setText(tr("tools_update_btn"))
            else:
                card["lbl_update"].setText("")
                btn.setText(tr("tools_delete"))
            btn.setEnabled(True)

        elif script_inst:
            # Per Projekt-Skript installiert: Loeschen laeuft ueber dasselbe
            # Skript ("uninstall"), Updates bringt das Projekt selbst mit.
            card["lbl_version"].setText("")
            card["lbl_update"].setText("")
            st.setText(tr("tools_script_ok"))
            st.setStyleSheet("color: #a3be8c; font-size: 12px; font-weight: bold;")
            card["cmd_widget"].setVisible(True)
            btn.setText(tr("tools_delete"))
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
        # Nach Installation/Entfernung kann die Karte aus dem aktiven
        # Status-Filter herausfallen (oder neu hineinfallen).
        self.apply_tools_filter()
        # Controls-Tab mitziehen (z. B. hier geloescht -> Schalter aus).
        if hasattr(self, "on_control_tool_status"):
            self.on_control_tool_status(key, status)

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
                  "flatpak": "Flatpak", "rpm": "RPM (dnf)", "cargo": "Cargo",
                  "script": tr("tools_method_script")}
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
        elif status.get("cargo_installed") and not status.get("cargo_has_update"):
            self.delete_tool(key)
        elif status.get("script_installed"):
            self.remove_tool_script(key)
        elif status.get("pm_installed"):
            # Per yay/paru installiert -> Paket entfernen
            self.remove_tool_pm(key)
        else:
            # sonst Installieren bzw. Aktualisieren (per gewählter Methode)
            self.install_tool(key)

    def start_tool(self, key):
        """
        Installiertes Werkzeug aus seiner Karte heraus starten.

        Der Knopf sitzt in derselben Zeile wie der Startbefehl und ist damit
        nur zu sehen, wenn das Werkzeug installiert ist. Trotzdem kann der
        Befehl fehlen (per Hand geloescht, Paket kaputt) — dann kommt eine
        Meldung statt eines stillen Nichts.
        """
        import tool_launcher

        card = self.ui.tool_cards.get(key)
        if not card:
            return
        tool = card.get("tool", {})
        status = card.get("status", {}) or {}
        name = tool.get("name", key)

        terminal = None
        if tool_launcher.wants_terminal(tool):
            from install_worker import find_terminal
            terminal = find_terminal()

        try:
            tool_launcher.start(tool, status, terminal=terminal,
                                texts={"exit_code": tr("controls_exit_code"),
                                       "press_enter": tr("controls_press_enter")})
        except FileNotFoundError:
            QMessageBox.warning(self, name, tr("tools_start_missing").format(
                cmd=tool.get("start_cmd", key)))
        except RuntimeError:
            QMessageBox.warning(self, name, tr("tools_cargo_no_terminal"))
        except OSError as exc:
            log.warning("Start von %s fehlgeschlagen: %s", key, exc)
            QMessageBox.warning(self, name, str(exc))

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

        updating = bool((status.get("appimage_installed") and status.get("appimage_has_update"))
                        or (status.get("cargo_installed") and status.get("cargo_has_update")))
        if status.get("cargo_installed"):
            # Update eines Cargo-Tools laeuft immer ueber Cargo — egal, was im
            # (dann ausgeblendeten) Dropdown steht.
            method = "cargo"

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
        elif method == "rpm":
            # Fedora: RPM aus dem neuesten GitHub-Release, Installation per dnf
            # im Terminal (root noetig).
            self.tool_worker = RpmInstallWorker(tool)
            self.tool_worker.status_signal.connect(
                lambda msg, k=key: self._set_tool_status(k, msg)
            )
            self.tool_worker.finished_signal.connect(
                lambda success, k=key: self.on_tool_installed(k, success)
            )
            self.tool_worker.start()
        elif method == "cargo":
            # Sichtbares Terminal: Compiler/Rust nachinstallieren, bauen,
            # verlinken. Bei Fehlern bleibt das Fenster offen.
            self.tool_worker = CargoInstallWorker(tool, lang=get_language())
            self.tool_worker.status_signal.connect(
                lambda msg, k=key: self._set_tool_status(k, msg)
            )
            self.tool_worker.finished_signal.connect(
                lambda success, k=key: self.on_tool_installed(k, success)
            )
            self.tool_worker.start()
        elif method == "script":
            # Offizielles Installationsskript des Projekts im Terminal.
            self.tool_worker = ScriptInstallWorker(tool)
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

        # Cargo-Tool: Ordner + Startbefehl. Sonst AppImage, Symlink und
        # Desktop-Eintrag.
        try:
            if (card.get("status") or {}).get("cargo_installed"):
                cargo_installer.uninstall(tool)
            else:
                appimg.uninstall(tool)
        except Exception as e:
            log.warning(f"[Tools] Löschen fehlgeschlagen: {e}")

        # Config-Ordner nur auf Wunsch
        if also_config:
            try:
                appimg.delete_config(tool)
            except Exception as e:
                log.warning(f"[AppImage] Config-Löschen fehlgeschlagen: {e}")

        # Status frisch berechnen und anzeigen
        self._refresh_single_tool(key)

    def remove_tool_script(self, key):
        """Entfernt ein per Projekt-Skript installiertes Tool (Skript mit 'uninstall')."""
        card = self.ui.tool_cards.get(key)
        if not card:
            return
        tool = card.get("tool", {})
        name = tool.get("name", key)
        reply = QMessageBox.question(
            self, tr("tools_script_remove_title"),
            tr("tools_script_remove_text").format(name=name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        card["btn_install"].setEnabled(False)
        card["btn_install"].setText(tr("tools_deleting"))
        self.tool_worker = ScriptInstallWorker(tool, uninstall=True)
        self.tool_worker.status_signal.connect(
            lambda msg, k=key: self._set_tool_status(k, msg))
        self.tool_worker.finished_signal.connect(
            lambda _ok, k=key: self._refresh_single_tool(k))
        self.tool_worker.start()

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
            msg = tr("tools_install_error")
            tool = card.get("tool", {})
            if "cargo" in appimg.supported_methods(tool) \
                    and os.path.exists(cargo_installer.log_path(tool)):
                # Der Nutzer soll wissen, wo er nachlesen kann.
                msg += " — " + cargo_installer.log_path(tool).replace(os.path.expanduser("~"), "~", 1)
            card["lbl_status"].setText(msg)
            card["lbl_status"].setStyleSheet("color: #bf616a; font-size: 12px;")
            card["btn_install"].setText(tr("tools_retry"))
            card["btn_install"].setEnabled(True)
        # Kam die Installation aus dem Controls-Tab? Dann dort Schalter setzen.
        if hasattr(self, "on_control_install_finished"):
            self.on_control_install_finished(key, success)
