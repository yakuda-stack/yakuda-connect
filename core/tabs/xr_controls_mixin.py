#!/usr/bin/env python3
"""
core/tabs/xr_controls_mixin.py — OpenXR-Spiele im Bereich „obah & xrBinder“
===========================================================================
Der Bereich „Controls per obah & xrBinder“ zeigt fuer OpenVR-Spiele die
obah-Ansicht (controls_mixin.py). OpenXR-Spiele — also alles, was xrBinder
schon einmal gesehen hat — stehen in derselben Spieleliste („· OpenXR“) und
bekommen DIESELBE Ansicht: zwei Controller, je Taste eine Karte, Klick
oeffnet einen Dialog. Im Hintergrund arbeitet xrBinder.

Unterschiede zur obah-Ansicht:
  * ② Controller wird erkannt (aktives Profil im Spiel), ③ Quelle ist fest
    „xrBinder“ — beide Auswahlen sind gesperrt.
  * Keine Action-Set-Tabs, keine Posen/Chords, keine Profile.
  * Karte = physische Taste; darauf stehen die Funktionen des Spiels, die
    gerade dort liegen ("↪" = hierher verschoben).
  * „Alles auf Standard“ nimmt alle Umbelegungen zurueck.

Die Regeln stecken in core/xr_bindings.py, Dateien/IPC in
core/xrbinder.py und core/xrbinder_session.py. controls_mixin.py ruft an
einigen Stellen hier herein (xr_* Methoden); sonst bleibt obah unberuehrt.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QMessageBox

import obah_bindings as ob
import xr_bindings as xr
import xrbinder as xb
from logging_setup import get_logger
from translations import tr

log = get_logger("xr_controls")

XR_PREFIX = "xr:"


class XrControlsMixin:
    """Wird von VRApp geerbt (neben ControlsTabMixin)."""

    # ------------------------------------------------------------------ #
    #  Aufbau
    # ------------------------------------------------------------------ #
    def setup_xr_controls(self):
        ui = self.ui
        self._xr_mode = False
        self._xr_game = ""
        self._xr_state = {}
        self._xr_mappings = {}
        session = ui.xrbinder_session
        session.games_changed.connect(self._xr_games_changed)
        session.state_updated.connect(self._xr_state_updated)
        session.apply_result.connect(self._xr_apply_result)
        ui.xrbinder_card.enabled_changed.connect(lambda _on: self._xr_games_changed())
        ui.btn_xr_reset_all.clicked.connect(self.xr_reset_all)
        ui.btn_xr_template.clicked.connect(self.xr_apply_template)
        ui.xrbinder_card.activate()

    # ------------------------------------------------------------------ #
    #  Spieleliste
    # ------------------------------------------------------------------ #
    def xr_game_names(self):
        return [n for n in self.ui.xrbinder_session.games() if xb.valid_app_name(n)]

    def _xr_label(self, name):
        label = f"{xb.display_app_name(name)}   · OpenXR"
        if self.ui.xrbinder_session.pid_of(name):
            label += "   ● " + tr("xrb_running")
        return label

    def xr_append_games(self, combo):
        """XR-Spiele in die obah-Spieleliste einfuegen (Signale sind gesperrt):
        nach den OpenVR-Spielen mit Action-Datei, vor denen ohne."""
        # obah-Spiele stehen sortiert (mit Action-Datei zuerst), XR-Eintraege
        # sind vorher entfernt -> Einfuegestelle = Anzahl mit Action-Datei
        i = min(sum(1 for g in self._obah_games if g.has_manifest), combo.count())
        for name in self.xr_game_names():
            combo.insertItem(i, self._xr_label(name), XR_PREFIX + name)
            combo.setItemData(i, f"{tr('xrb_game_tip')}\n{name}", Qt.ToolTipRole)
            if not self.ui.xrbinder_session.pid_of(name):
                combo.setItemData(i, QColor("#a6b2c0"), Qt.ForegroundRole)
            i += 1

    def xr_selected(self):
        data = self.ui.combo_obah_game.currentData()
        if isinstance(data, str) and data.startswith(XR_PREFIX):
            return data[len(XR_PREFIX):]
        return ""

    def _xr_games_changed(self):
        """Spiel gestartet/beendet: nur die XR-Eintraege der Liste auffrischen."""
        if not getattr(self, "_obah_scanned", False):
            return
        combo = self.ui.combo_obah_game
        if not self._obah_games and not combo.isEnabled():
            # Liste zeigte „keine Spiele“ — jetzt gibt es evtl. XR-Spiele
            if self.xr_game_names():
                self._on_obah_games_found([])
            return
        current = combo.currentData()
        combo.blockSignals(True)
        for i in range(combo.count() - 1, -1, -1):
            data = combo.itemData(i)
            if isinstance(data, str) and data.startswith(XR_PREFIX):
                combo.removeItem(i)
        self.xr_append_games(combo)
        idx = combo.findData(current)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)
        if idx < 0:
            self._on_obah_game_changed(combo.currentIndex())
        elif self._xr_mode:
            self._xr_update_hint()
            self.xr_render_views()
        else:
            # graues Spiel gewaehlt: Hinweis nennt laufende OpenXR-Spiele
            game = self._current_obah_game()
            if game is not None and not game.has_manifest:
                self._on_obah_game_changed(combo.currentIndex())

    # ------------------------------------------------------------------ #
    #  Umschalten obah <-> XR
    # ------------------------------------------------------------------ #
    def xr_on_game_changed(self):
        """Aus _on_obah_game_changed: True = XR-Spiel, obah macht nichts weiter."""
        name = self.xr_selected()
        if self._xr_mode and self._obah_dirty and name != self._xr_game:
            self._ask_save_before_leaving()
        if not name:
            if self._xr_mode:
                self._xr_leave()
            return False
        self._obah_last_game = XR_PREFIX + name
        self._xr_enter(name)
        return True

    def _xr_set_obah_widgets(self, xr_mode):
        ui = self.ui
        for w in (ui.obah_set_tabs, ui.btn_obah_aux_expand, ui.lbl_obah_profile,
                  ui.combo_obah_profile, ui.btn_obah_profile_load, ui.btn_obah_profile_save,
                  ui.btn_obah_profile_delete, ui.btn_obah_pick_manifest):
            w.setVisible(not xr_mode)
        if xr_mode:
            ui.obah_aux_body.setVisible(False)
            ui.btn_obah_clear_manifest.setVisible(False)
        else:
            ui.obah_aux_body.setVisible(ui.btn_obah_aux_expand.isChecked())
        ui.btn_xr_reset_all.setVisible(xr_mode)
        if not xr_mode:
            ui.btn_xr_template.setVisible(False)

    def _xr_leave(self):
        self._xr_mode = False
        self._xr_game = ""
        self._obah_edit = None
        self._set_obah_dirty(False)
        self._xr_set_obah_widgets(False)

    def _xr_enter(self, name):
        ui = self.ui
        self._xr_mode = True
        self._xr_game = name
        self._obah_bindings = None
        self._xr_set_obah_widgets(True)
        self._xr_load_state()
        ct = xr.detect_controller(self._xr_state)
        for combo, label, data in ((ui.combo_obah_controller,
                                    ob.controller_label(ct) + "   · " + tr("xrb_detected"), ct),
                                   (ui.combo_obah_source, "xrBinder", "xrbinder")):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(label, data)
            combo.setEnabled(False)
            combo.blockSignals(False)
        self._obah_edit = {"controller": ct, "xr": True, "game": None, "source": None,
                           "path": None, "binding": None, "lang": "en"}
        self._set_obah_dirty(False)
        self.xr_refresh_editor()
        # Laeuft das Spiel: Aktionen frisch holen (Profil kann gewechselt haben)
        self.ui.xrbinder_session.request_dump(name)

    @staticmethod
    def _xr_read_state(name):
        """Gespeicherten Stand lesen — fehlen die Tasten (xrizer unter WiVRn),
        xrizers Standardbelegung ergaenzen. IMMER ueber diese Funktion lesen,
        sonst stehen die Karten nach dem Speichern wieder leer da."""
        state = xb.load_state(name)
        if xb.fill_known_bindings(state):
            state["bindings_guessed"] = True
        return state

    def _xr_load_state(self):
        self._xr_state = self._xr_read_state(self._xr_game)
        self._xr_mappings = xr.mappings_from_list(self._xr_state.get("mappings"))

    def _xr_update_hint(self):
        ui = self.ui
        session = ui.xrbinder_session
        if not ui.xrbinder_card.is_enabled():
            text = tr("xrb_hint_disabled_card")
        elif xb.needs_rebuild():
            text = tr("xrb_status_rebuild_needed")
        elif not self._xr_state.get("actions"):
            text = tr("xrb_hint_no_actions")
        elif xr.template_offered((self._obah_edit or {}).get("controller") or xr.DEFAULT_CT,
                                 self._xr_state, self._xr_mappings):
            text = tr("xrb_hint_template")
        elif session.pid_of(self._xr_game):
            text = tr("xrb_hint_running")
        else:
            text = tr("xrb_hint_offline")
        ui.lbl_obah_hint.setText(text)

    # ------------------------------------------------------------------ #
    #  Ansicht
    # ------------------------------------------------------------------ #
    def xr_refresh_editor(self):
        """Aus _refresh_obah_editor (XR-Modus)."""
        self._xr_update_hint()
        ready = bool(xr.actions(self._xr_state))
        self._show_obah_editor(ready)
        if ready:
            self.xr_render_views()

    def _xr_texts(self):
        from ui.xr_button_dialog import kind_label
        modes = {k: kind_label(k) for k in ("click", "touch", "value", "force", "x", "y", "dir")}
        return {"modes": modes, "inputs": {}, "unbound": tr("xrb_card_unbound"), "none": "—",
                "menu_show": tr("obah_menu_show"), "menu_hide": tr("obah_menu_hide"),
                "menu_show_all": tr("obah_menu_show_all"),
                "menu_hide_all": tr("obah_menu_hide_all")}

    def xr_render_views(self):
        """Aus _render_obah_views (XR-Modus): beide Controller mit XR-Karten."""
        ui = self.ui
        edit = self._obah_edit or {}
        ct = edit.get("controller") or xr.DEFAULT_CT
        base = self._xr_texts()
        ui.obah_view_right.setVisible(True)
        ui.obah_view_left.setVisible(True)
        for side, view, title_key in (("left", ui.obah_view_left, "obah_left"),
                                      ("right", ui.obah_view_right, "obah_right")):
            views = xr.build_views(ct, side, self._xr_state, self._xr_mappings,
                                   tilt_label=tr("xrd_tilt_short"),
                                   deadzone_label=tr("xrd_deadzone_short"))
            view.set_layout(self._load_obah_layout(ct, side))
            view.set_data(ct, side, views, dict(base, title=tr(title_key),
                                                hint=tr("xrb_card_hint"),
                                                hint_image=tr("obah_image_hint")))
        ui.obah_hands.sync_mirror()
        ui.obah_hands.relayout()
        self._sync_obah_tidy_button()
        ui.btn_obah_layout_reset.setEnabled(
            ui.obah_view_left.has_manual_layout() or ui.obah_view_right.has_manual_layout())
        ui.btn_xr_reset_all.setEnabled(bool(self._xr_mappings))
        ui.btn_xr_template.setVisible(xr.template_offered(ct, self._xr_state, self._xr_mappings))

        bound, total = xr.counts(ct, self._xr_state, self._xr_mappings)
        changed = len(self._xr_mappings)
        text = tr("xrb_editor_status").format(bound=bound, total=total, changed=changed)
        if self._xr_state.get("bindings_guessed"):
            text += "  ·  " + tr("xrb_bindings_guessed")
        if self._obah_dirty:
            text = "● " + tr("obah_unsaved") + "  ·  " + text
        ui.lbl_obah_editor_status.setText(text)
        ui.lbl_obah_editor_status.setStyleSheet(
            "color:#ebcb8b; font-size:11px;" if self._obah_dirty else "color:#7b88a1; font-size:11px;")
        self.xr_update_save_button()

    def xr_update_save_button(self):
        self.ui.btn_obah_save.setText("💾  " + tr("xrb_save_button"))
        self.ui.btn_obah_save.setEnabled(self._obah_dirty)
        for act in self.ui.menu_obah_save.actions():
            act.setEnabled(False)

    # ------------------------------------------------------------------ #
    #  Bearbeiten
    # ------------------------------------------------------------------ #
    def xr_open_dialog(self, view, input_path):
        from ui.xr_button_dialog import XrButtonDialog
        ct = (self._obah_edit or {}).get("controller") or xr.DEFAULT_CT
        side = "left" if view is self.ui.obah_view_left else "right"
        d = next((x for x in xr.card_inputs(ct, side) if x.path == input_path), None)
        if d is None:
            return
        dlg = XrButtonDialog(self, controller_type=ct, side=side, input_def=d,
                             state=self._xr_state, mappings=self._xr_mappings,
                             game=xb.display_app_name(self._xr_game))
        self._obah_open_dialog = dlg            # fuer Tests erreichbar
        accepted = dlg.exec() == XrButtonDialog.Accepted
        self._obah_open_dialog = None
        if not accepted or dlg.mappings == self._xr_mappings:
            return
        self._xr_mappings = dlg.mappings
        self._set_obah_dirty(True)
        self.xr_render_views()

    def xr_reset_all(self):
        if not self._xr_mappings:
            return
        reply = QMessageBox.question(self, tr("xrb_reset_all_title"),
                                     tr("xrb_reset_all_text").format(game=xb.display_app_name(self._xr_game)),
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self._xr_mappings = {}
        self._set_obah_dirty(True)
        self.xr_render_views()

    def xr_apply_template(self):
        """„OpenXR-Vorlage verwenden“: Standardbelegung als (ungespeicherte) Umbelegung."""
        ct = (self._obah_edit or {}).get("controller") or xr.DEFAULT_CT
        mappings, matched, total = xr.template_mappings(self._xr_state, ct)
        if not mappings:
            QMessageBox.information(self, tr("xrb_template"), tr("xrb_template_none"))
            return
        self._xr_mappings = mappings
        self._set_obah_dirty(True)
        self._xr_update_hint()
        self.xr_render_views()
        self.ui.lbl_obah_editor_status.setText(
            "● " + tr("xrb_template_applied").format(matched=matched, total=total))

    def xr_discard(self):
        self._xr_load_state()
        self._set_obah_dirty(False)
        self.xr_render_views()

    def xr_save(self):
        name = self._xr_game
        if not name:
            return False
        try:
            live = self.ui.xrbinder_session.save(name, xr.mappings_to_list(self._xr_mappings))
        except (OSError, ValueError) as exc:
            log.warning("xrBinder-Belegung nicht gespeichert: %s", exc)
            QMessageBox.warning(self, tr("obah_save_failed_title"),
                                tr("obah_save_failed_text").format(error=exc))
            return False
        self._xr_state = self._xr_read_state(name)
        self._set_obah_dirty(False)
        self.xr_render_views()
        if live:
            self.ui.lbl_obah_editor_status.setText("… " + tr("xrb_applying"))
        else:
            # Spiel laeuft nicht: das Ergebnis kam schon waehrend save()
            self._xr_apply_result(name, "offline")
        return True

    def _xr_apply_result(self, name, result):
        if not self._xr_mode or name != self._xr_game:
            return
        key = {"live": "xrb_result_live", "restart": "xrb_result_restart",
               "restart_axis": "xrb_result_restart_axis"}.get(
            result, "xrb_result_next_start")
        ok = result == "live"
        self.ui.lbl_obah_editor_status.setText(("✔ " if ok else "") + tr(key).format(game=xb.display_app_name(name)))
        self.ui.lbl_obah_editor_status.setStyleSheet(
            f"color:{'#a3be8c' if ok else '#ebcb8b'}; font-size:11px;")

    def _xr_state_updated(self, name):
        """Frische Aktionen vom laufenden Spiel."""
        if not self._xr_mode or name != self._xr_game:
            return
        fresh = self._xr_read_state(name)
        self._xr_state.update(actions=fresh.get("actions"), bindings=fresh.get("bindings"),
                              sources=fresh.get("sources"),
                              bindings_guessed=fresh.get("bindings_guessed", False))
        if not self._obah_dirty:
            self._xr_mappings = xr.mappings_from_list(fresh.get("mappings"))
        ct = xr.detect_controller(self._xr_state)
        if (self._obah_edit or {}).get("controller") != ct:
            self._xr_enter(name)
            return
        self.xr_refresh_editor()
