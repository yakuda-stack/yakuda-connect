#!/usr/bin/env python3
"""
core/tabs/games_optimize_mixin.py — „✨ Optimieren“ neben „Play“
================================================================
Ein Klick, ein paar Fragen, fertig eingerichtet:

  * VRChat: Cache-Groesse (Standard 30 GB), Bilder-Fix laeuft automatisch
  * Startoptionen: jede mit Erklaerung, nur die Empfehlungen sind
    vorausgewaehlt — nicht, was bisher an war, das kann Fehler mitschleppen
  * Proton: die empfohlene Version wird automatisch gewaehlt — fehlt sie,
    wird sie vorher installiert und danach gesetzt

Die Fragen stellt ui/game_optimize_dialog.py; hier wird angewendet.
"""
import games as games_db
import vrchat_config as vrc_cfg
from logging_setup import get_logger
from translations import tr

log = get_logger("games_optimize")

VRCHAT_APPID = "438100"


class GamesOptimizeMixin:

    def open_game_optimize(self, appid):
        from ui.game_optimize_dialog import GameOptimizeDialog
        game = self._game_data_for(appid)
        if not game or game.get("local"):
            return
        is_vrc = str(appid) == VRCHAT_APPID
        fixes = game.get("fixes", [])

        # Startoptionen: immer nur die Empfehlungen des Spiels. Eigene
        # Parameter bleiben, sie stehen nicht zur Auswahl.
        games_db.refresh_vrcvideocacher_path()
        game_toggles = games_db.resolved_toggles(game)
        saved, custom = games_db.load_launch_toggles(appid, game_toggles)
        initial = set(game.get("default_on", []))
        initial |= {t["key"] for t in game_toggles if t.get("default")}
        toggles = []
        # Schalter nur fuer die Spiel-Einstellungen: bleiben, wie sie sind.
        kept = [t["key"] for t in game_toggles if t.get("panel_only") and t["key"] in saved]
        for t in list(games_db.LAUNCH_TOGGLES) + list(game_toggles):
            if t.get("panel_only") or (is_vrc and t["key"] == "gamemoderun"):
                continue
            enabled = bool(t.get("arg"))
            tip = tr(f"games_toggle_{t['key']}_tip") if enabled \
                else tr(f"games_toggle_{t['key']}_missing")
            toggles.append((t["key"], tr(f"games_toggle_{t['key']}"), tip,
                            t["key"] in initial, enabled))

        cache = None
        if is_vrc and "vrchat_cache" in fixes and vrc_cfg.prefix_exists():
            cache = (vrc_cfg.cache_size(), vrc_cfg.CACHE_MIN, vrc_cfg.CACHE_MAX,
                     vrc_cfg.CACHE_DEFAULT)

        rec = self._optimize_recommended_proton(game)
        plan = []
        if rec is not None:
            tool, found, _k = games_db.resolve_steam_tool(rec)
            name = tool or rec.get("version", "")
            plan.append(tr("gopt_sum_proton" if found else "gopt_sum_proton_install")
                        .format(proton=name))
        if is_vrc and "vrchat_pictures" in fixes:
            plan.append(tr("gopt_sum_pictures"))

        dlg = GameOptimizeDialog(self, game=game.get("name", ""), toggles=toggles,
                                 cache=cache, plan=plan, steam_hint=is_vrc)
        if dlg.exec() != GameOptimizeDialog.Accepted:
            return
        self._apply_game_optimize(appid, game, list(dlg.enabled_keys()) + kept, custom,
                                  dlg.cache_value(), rec)

    def game_optimize_state(self, appid):
        """
        Sind alle Optimierungen gesetzt, die der Assistent vorschlaegt?
        True / False, None wenn es nichts zu optimieren gibt oder die
        Pruefung scheitert. Geprueft werden die empfohlenen Startoptionen
        und die empfohlene Proton-Version.
        """
        try:
            game = self._game_data_for(appid)
            if not game or game.get("local"):
                return None
            is_vrc = str(appid) == VRCHAT_APPID
            game_toggles = games_db.resolved_toggles(game)
            saved, _custom = games_db.load_launch_toggles(appid, game_toggles)
            wanted = set(game.get("default_on", []))
            wanted |= {t["key"] for t in game_toggles if t.get("default")}
            usable = {t["key"] for t in list(games_db.LAUNCH_TOGGLES) + list(game_toggles)
                      if t.get("arg") and not t.get("panel_only")
                      and not (is_vrc and t["key"] == "gamemoderun")}
            if not (wanted & usable) <= set(saved):
                return False
            rec = self._optimize_recommended_proton(game)
            if rec is not None and not self._is_active_proton(appid, rec):
                return False
            return True
        except Exception:                          # noqa: BLE001 — nur Anzeige
            log.debug("Optimierungs-Status fuer %s nicht ermittelbar", appid, exc_info=True)
            return None

    @staticmethod
    def _optimize_recommended_proton(game):
        role = games_db.recommended_role(game)
        protons = list(games_db.visible_protons(game))
        return next((p for p in protons if p.get("role") == role),
                    protons[0] if protons else None)

    def _apply_game_optimize(self, appid, game, keys, custom, cache, rec):
        done = []
        games_db.save_launch_toggles(appid, keys, custom)
        done.append(tr("gopt_done_toggles"))
        if cache is not None:
            if vrc_cfg.set_cache_size(cache):
                done.append(tr("gopt_sum_cache").format(gb=cache))
        if str(appid) == VRCHAT_APPID and "vrchat_pictures" in game.get("fixes", []):
            try:
                self._refresh_detail()            # Fix-Knoepfe/Statuszeile frisch
                self.create_vrchat_symlink()
                done.append(tr("gopt_sum_pictures"))
            except Exception as exc:              # noqa: BLE001 — Rest soll weiterlaufen
                log.warning("[Optimieren] Bilder-Fix: %s", exc)
        self._refresh_detail()
        self._detail_status("✔ " + tr("gopt_done").format(items=", ".join(done)), "#a3be8c")

        # Proton zuletzt: kann Rueckfragen stellen (Backup, Steam beenden)
        if rec is None:
            return
        _tool, found, _k = games_db.resolve_steam_tool(rec)
        if found:
            if not self._is_active_proton(appid, rec):
                self._use_proton(appid, rec)
            return
        self._optimize_pending_proton = (appid, rec)
        if rec.get("download_url"):
            self.start_manual_proton_install(rec)
        elif rec.get("protonplus_runner"):
            self.start_protonplus_install(rec["protonplus_runner"])
        else:
            self._optimize_pending_proton = None
            self._detail_status(tr("games_tool_missing"), "#ebcb8b")

    def optimize_after_proton_install(self, ok):
        """Aus den Install-Callbacks: war der Assistent der Ausloeser, jetzt setzen."""
        pending = getattr(self, "_optimize_pending_proton", None)
        self._optimize_pending_proton = None
        if not pending or not ok:
            return
        appid, rec = pending
        _tool, found, _k = games_db.resolve_steam_tool(rec)
        if found:
            self._use_proton(appid, rec)
