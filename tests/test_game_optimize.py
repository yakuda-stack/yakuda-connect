#!/usr/bin/env python3
"""Tests fuer „✨ Optimieren“ (ui/game_optimize_dialog.py, games_optimize_mixin)."""
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "core"))

TOGGLES = [("force_openxr", "--force-openxr", "OpenXR statt OpenVR", True, True),
           ("gamemoderun", "gamemoderun", "GameMode", False, True),
           ("mullvad_exclude", "mullvad-exclude", "fehlt", True, False)]


def test_dialog_pages_and_result(qapp):
    from ui.game_optimize_dialog import GameOptimizeDialog
    dlg = GameOptimizeDialog(None, game="VRChat", toggles=TOGGLES,
                             cache=(30, 30, 130, 30), plan=["Proton X"])
    assert len(dlg.pages) == 3
    assert dlg.stack.currentIndex() == 0 and not dlg.btn_back.isVisible()
    dlg.cache_slider.setValue(80)
    dlg._next()
    dlg.checks["gamemoderun"].setChecked(True)
    assert not dlg.checks["mullvad_exclude"].isEnabled()
    dlg._next()
    text = dlg.lbl_summary.text()
    assert "Proton X" in text and "80" in text and "gamemoderun" in text
    assert dlg.enabled_keys() == ["force_openxr", "gamemoderun"]
    assert dlg.cache_value() == 80
    dlg._next()
    assert dlg.result() == GameOptimizeDialog.Accepted
    dlg.deleteLater()


def test_dialog_without_cache(qapp):
    from ui.game_optimize_dialog import GameOptimizeDialog
    dlg = GameOptimizeDialog(None, game="Other", toggles=TOGGLES)
    assert len(dlg.pages) == 2 and dlg.cache_value() is None
    dlg.deleteLater()


class _Fake:
    from tabs.games_optimize_mixin import GamesOptimizeMixin as _M
    _apply_game_optimize = _M._apply_game_optimize
    optimize_after_proton_install = _M.optimize_after_proton_install

    def __init__(self):
        self.calls = []

    def _refresh_detail(self):
        self.calls.append("refresh")

    def create_vrchat_symlink(self):
        self.calls.append("pictures")

    def _detail_status(self, text, color=""):
        self.calls.append(("status", text))

    def _is_active_proton(self, appid, proton):
        return False

    def _use_proton(self, appid, proton):
        self.calls.append(("use", proton["version"]))

    def start_manual_proton_install(self, proton, button=None):
        self.calls.append(("install", proton["version"]))


def test_apply_installs_then_uses_proton(monkeypatch):
    import games as games_db
    import vrchat_config as vrc_cfg
    saved = {}
    monkeypatch.setattr(games_db, "save_launch_toggles",
                        lambda a, k, c: saved.update(appid=a, keys=k, custom=c))
    monkeypatch.setattr(vrc_cfg, "set_cache_size", lambda gb: saved.update(cache=gb) or True)
    state = {"found": False}
    monkeypatch.setattr(games_db, "resolve_steam_tool",
                        lambda p: ("Tool", state["found"], "manual"))
    f = _Fake()
    rec = {"version": "RTSP", "download_url": "https://x"}
    f._apply_game_optimize("438100", {"fixes": ["vrchat_pictures"]}, ["force_openxr"], "",
                           60, rec)
    assert saved == {"appid": "438100", "keys": ["force_openxr"], "custom": "", "cache": 60}
    assert "pictures" in f.calls and ("install", "RTSP") in f.calls
    assert ("use", "RTSP") not in f.calls
    state["found"] = True
    f.optimize_after_proton_install(True)
    assert ("use", "RTSP") in f.calls


def test_steam_hint_only_when_requested(qapp):
    from translations import tr
    from ui.game_optimize_dialog import GameOptimizeDialog
    from PySide6.QtWidgets import QLabel
    plain = GameOptimizeDialog(None, game="Other", toggles=TOGGLES)
    hinted = GameOptimizeDialog(None, game="VRChat", toggles=TOGGLES, steam_hint=True)
    head = tr("gopt_steam_hint_head")
    assert head not in [l.text() for l in plain.findChildren(QLabel)]
    assert head in [l.text() for l in hinted.findChildren(QLabel)]


def _open_with(monkeypatch, game, saved_keys):
    """Oeffnet den Assistenten und liefert die Vorauswahl je Schalter."""
    import games as games_db
    import ui.game_optimize_dialog as dialog
    from tabs.games_optimize_mixin import GamesOptimizeMixin
    seen = {}

    class Dialog:
        Accepted = 1

        def __init__(self, _parent, **kwargs):
            seen.update({t[0]: t[3] for t in kwargs["toggles"]})
            seen["_hint"] = kwargs["steam_hint"]

        def exec(self):
            return 0

    class Host(GamesOptimizeMixin):
        def _game_data_for(self, _appid):
            return game

        def _optimize_recommended_proton(self, _game):
            return None

    monkeypatch.setattr(dialog, "GameOptimizeDialog", Dialog)
    monkeypatch.setattr(games_db, "refresh_vrcvideocacher_path", lambda: None)
    monkeypatch.setattr(games_db, "load_launch_toggles", lambda a, t: (saved_keys, "eigen"))
    Host().open_game_optimize("438100")
    return seen


def test_vrchat_nur_empfehlungen_vorausgewaehlt(monkeypatch):
    import games as games_db
    game = games_db.GAMES["438100"]
    seen = _open_with(monkeypatch, game, ["proton_use_wayland", "vrc_launch_in_vr", "gamemoderun"])
    assert seen.pop("_hint") is True
    assert sorted(k for k, on in seen.items() if on) == ["force_openxr", "vrc_hw_video_decoding"]
    assert "gamemoderun" not in seen
    assert "vrc_avpro_proton" not in seen and "vrc_amd_stutter" not in seen
