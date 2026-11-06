#!/usr/bin/env python3
"""Server mit der App starten, Status-Pruefung im Dashboard, Timer Server Check."""
import json
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import exit_guard
import wivrn_server


@pytest.fixture
def state():
    return {"running": False}


@pytest.fixture
def window(qapp, tmp_path, monkeypatch, state):
    import paths
    import config_manager
    monkeypatch.setattr(paths, "config_file", lambda name: str(tmp_path / name))
    monkeypatch.setattr(config_manager, "CONFIG_FILE", str(tmp_path / "config.json"))
    from PySide6.QtWidgets import QMessageBox, QDialog
    for m in ("warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, m, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QDialog, "exec", lambda self, *a, **k: 0)
    monkeypatch.setattr(wivrn_server, "is_running", lambda p=None: state["running"])
    monkeypatch.setattr(wivrn_server, "stop_blocking", lambda *a, **k: True)
    from main import VRApp
    monkeypatch.setattr(VRApp, "are_critical_packages_missing", lambda self: False)
    monkeypatch.setattr(VRApp, "refresh_headset_list", lambda self: setattr(self, "_list_refreshed", True))
    starts = []
    monkeypatch.setattr(VRApp, "start_wivrn_server", lambda self: starts.append(1))
    w = VRApp()
    w._exit_guard = exit_guard.ExitGuard(popen=lambda *a, **k: None)
    w._stop_server_with_app = False
    w._starts = starts
    w._list_refreshed = False
    yield w
    w.close()


def _config(tmp_path):
    with open(tmp_path / "config.json") as fh:
        return json.load(fh)


def test_start_mit_app_standardmaessig_aus(window):
    assert not window.ui.chk_start_server_with_app.isChecked()
    window._start_server_on_launch()
    assert window._starts == []


def test_start_mit_app_wird_gespeichert_und_startet(window, tmp_path):
    window.ui.chk_start_server_with_app.setChecked(True)
    assert _config(tmp_path)["start_server_with_app"] is True
    window._start_server_on_launch()
    assert window._starts == [1]
    assert window.ui.toggle_server.isChecked()


def test_start_mit_app_nicht_wenn_server_schon_laeuft(window):
    window.ui.chk_start_server_with_app.setChecked(True)
    window._server_running = True
    window._start_server_on_launch()
    assert window._starts == []


def test_start_mit_app_nicht_ohne_wivrn(window, monkeypatch):
    window.ui.chk_start_server_with_app.setChecked(True)
    monkeypatch.setattr(type(window), "are_critical_packages_missing", lambda self: True)
    window._start_server_on_launch()
    assert window._starts == []


def test_dashboard_klick_erkennt_fremden_server(window, state):
    window.ui.sidebar.setCurrentRow(2)
    state["running"] = True
    window.on_tab_changed(1)
    assert window._server_running is True
    assert window.ui.toggle_server.isChecked()
    assert window._starts == []


def test_pruefung_stoert_laufendes_beenden_nicht(window, state):
    state["running"] = True
    window._server_stopping = True
    assert window.manual_server_check() is False
    assert window._server_running is False
    assert not window.ui.toggle_server.isChecked()
    window._server_stopping = False


def test_headset_liste_nur_bei_aenderung(window, state):
    window._check_server_and_refresh()
    assert window._list_refreshed is False
    state["running"] = True
    window._check_server_and_refresh()
    assert window._list_refreshed is True


@pytest.fixture
def armed(window, monkeypatch):
    calls = []
    monkeypatch.setattr(type(window), "arm_autostart_timer", lambda self: calls.append(1))
    return calls


def test_fremder_server_schaltet_autostart_scharf(window, state, armed):
    assert window.ui.chk_autostart_external_server.isChecked()
    state["running"] = True
    window.manual_server_check()
    assert armed == [1]
    assert window._external_autostart is True


def test_fremder_server_nur_einmal_scharf(window, state, armed):
    state["running"] = True
    window.manual_server_check()
    window.manual_server_check()
    assert armed == [1]


def test_fremder_server_option_aus(window, state, armed, tmp_path):
    window.ui.chk_autostart_external_server.setChecked(False)
    assert _config(tmp_path)["autostart_external_server"] is False
    state["running"] = True
    window.manual_server_check()
    assert armed == []


def test_eigener_server_wird_nicht_doppelt_scharf(window, state, armed):
    class Own:
        def poll(self):
            return None
    window.server_process = Own()
    state["running"] = True
    window.manual_server_check()
    window.server_process = None
    assert armed == []


def test_terminal_modus_behaelt_seine_programme(window, state, armed, monkeypatch):
    import autostart_runner
    monkeypatch.setattr(autostart_runner, "watcher_running", lambda s=None: True)
    state["running"] = True
    window.manual_server_check()
    assert armed == []


def test_start_schaltet_nach_laden_der_zeilen_scharf(window, armed):
    window._server_running = True
    window._start_server_on_launch()
    assert armed == [1]


def test_fremder_server_weg_beendet_programme(window, state, armed, monkeypatch):
    stopped = []
    monkeypatch.setattr(type(window), "stop_autostart_apps", lambda self: stopped.append(1))
    state["running"] = True
    window.manual_server_check()
    state["running"] = False
    window.manual_server_check()
    assert stopped == [1]
    assert window._external_autostart is False


def test_timer_standardmaessig_aus(window):
    assert not window._server_timer.isActive()
    assert window.ui.btn_server_timer.property("timerOn") == "false"


def test_timer_dialog_schaltet_und_speichert(window, tmp_path, monkeypatch):
    from ui import server_check_dialog as scd
    monkeypatch.setattr(scd.ServerCheckDialog, "exec", lambda self: 1)
    monkeypatch.setattr(scd.ServerCheckDialog, "values", lambda self: (True, 45))
    window.open_server_timer_dialog()
    assert window._server_timer.isActive()
    assert window._server_timer.interval() == 45000
    assert "45" in window.ui.btn_server_timer.text()
    assert window.ui.btn_server_timer.property("timerOn") == "true"
    saved = _config(tmp_path)
    assert saved["server_check_timer"] is True
    assert saved["server_check_interval"] == 45

    monkeypatch.setattr(scd.ServerCheckDialog, "values", lambda self: (False, 45))
    window.open_server_timer_dialog()
    assert not window._server_timer.isActive()
    assert "45" not in window.ui.btn_server_timer.text()


def test_timer_dialog_abbrechen_aendert_nichts(window):
    window.open_server_timer_dialog()
    assert not window._server_timer.isActive()


def test_timer_laeuft_nach_schliessen_nicht_weiter(window):
    window._server_timer.start(5000)
    window.close()
    assert not window._server_timer.isActive()


@pytest.mark.parametrize("value,expected", [(1, 30), (30, 30), (120, 120), (99999, 300), ("kaputt", 30), (None, 30)])
def test_abstand_wird_begrenzt(window, value, expected):
    assert window._clamp_server_timer(value) == expected


def test_dialog_gibt_werte_zurueck(qapp):
    from ui.server_check_dialog import ServerCheckDialog
    dialog = ServerCheckDialog(False, 30, 5, 3600)
    dialog.chk_enabled.setChecked(True)
    dialog.spin_seconds.setValue(60)
    assert dialog.values() == (True, 60)


@pytest.mark.parametrize("timer_on", [False, True])
@pytest.mark.parametrize("typed,expected", [("45", 45), ("3", 5), ("120", 120)])
def test_dialog_eingabe_geht_auch_bei_timer_aus(qapp, timer_on, typed, expected):
    from PySide6.QtTest import QTest
    from ui.server_check_dialog import ServerCheckDialog
    dialog = ServerCheckDialog(timer_on, 30, 5, 3600)
    edit = dialog.spin_seconds.lineEdit()
    edit.selectAll()
    QTest.keyClicks(edit, typed)
    assert dialog.values() == (timer_on, expected)


class _Proc:
    def __init__(self, code):
        self.code = code

    def poll(self):
        return self.code


@pytest.fixture
def rearm(window, state, armed, monkeypatch):
    monkeypatch.setattr(type(window), "_live_headset_peers",
                        lambda self: None if state.get("headset") else [])
    window.ui.chk_stop_apps_on_disconnect.setChecked(False)
    window.ui.chk_restart_on_poweroff.setChecked(False)
    state["running"] = True
    window._server_running = True
    window._disconnect_count = 0
    return window


def _nach_frist(window):
    for _ in range(window._disconnect_grace):
        window._check_autostart_rearm()


def test_programme_zu_und_getrennt_wird_nach_frist_scharf(rearm, armed):
    rearm._autostart_procs = [_Proc(0)]
    for _ in range(rearm._disconnect_grace - 1):
        rearm._check_autostart_rearm()
    assert armed == []
    rearm._check_autostart_rearm()
    assert armed == [1]
    rearm._autostart_procs = []


def test_offene_programme_bleiben_ohne_option(rearm, armed, monkeypatch):
    stopped = []
    monkeypatch.setattr(type(rearm), "stop_autostart_apps", lambda self: stopped.append(1))
    rearm._autostart_procs = [_Proc(None)]
    _nach_frist(rearm)
    assert stopped == [] and armed == []
    rearm._autostart_procs = []


def test_option_beendet_offene_programme(rearm, armed, monkeypatch, tmp_path):
    stopped = []
    monkeypatch.setattr(type(rearm), "stop_autostart_apps", lambda self: stopped.append(1))
    rearm.ui.chk_stop_apps_on_disconnect.setChecked(True)
    assert _config(tmp_path)["stop_apps_on_disconnect"] is True
    rearm._autostart_procs = [_Proc(None)]
    _nach_frist(rearm)
    assert stopped == [1] and armed == [1]
    rearm._autostart_procs = []


def test_kurzer_aussetzer_zaehlt_nicht(rearm, armed, state):
    rearm._autostart_procs = [_Proc(0)]
    rearm._check_autostart_rearm()
    state["headset"] = True
    rearm._check_autostart_rearm()
    assert rearm._disconnect_count == 0 and armed == []
    rearm._autostart_procs = []


def test_ohne_server_endet_die_pruefung(rearm, armed, state):
    rearm._autostart_procs = []
    state["running"] = False
    rearm._autostart_rearm_timer.start()
    rearm._check_autostart_rearm()
    assert not rearm._autostart_rearm_timer.isActive() and armed == []


def test_start_ist_nach_programmstart_vorgesehen(window, state, monkeypatch):
    state["running"] = True
    monkeypatch.setattr(type(window), "is_headset_connected", lambda self: True)
    monkeypatch.setattr(type(window), "launch_autostart_apps", lambda self: None)
    window._poll_headset_for_autostart()
    assert window._autostart_rearm_timer.isActive()
    window.kill_autostart_apps()
    assert not window._autostart_rearm_timer.isActive()


def test_beenden_beim_trennen_standardmaessig_an(window):
    assert window.ui.chk_stop_apps_on_disconnect.isChecked()


def test_hinweis_nur_einmal(window, tmp_path):
    assert _config(tmp_path)["autostart_disconnect_notice_seen"] is True
    window.ui.lbl_autostart_notice.setVisible(False)
    window._show_autostart_notice_once()
    assert window.ui.lbl_autostart_notice.isHidden()


PEER = ("192.168.1.50", 40000)


def _peers(window, monkeypatch, answers):
    import autostart_runner
    import process_watch
    monkeypatch.setattr(autostart_runner, "headset_peers", lambda: [PEER])
    monkeypatch.setattr(process_watch, "host_answers", lambda ip: answers["ok"])


def test_antwortendes_headset_ist_da(window, monkeypatch):
    answers = {"ok": True}
    _peers(window, monkeypatch, answers)
    assert window._live_headset_peers() is None


def test_schweigen_zaehlt_erst_nach_einer_antwort(window, monkeypatch):
    answers = {"ok": False}
    _peers(window, monkeypatch, answers)
    window._answering_ips.clear()
    assert window._live_headset_peers() is None
    answers["ok"] = True
    window._live_headset_peers()
    answers["ok"] = False
    assert window._live_headset_peers() == [PEER]


def test_usb_wird_nicht_angefragt(window, monkeypatch):
    import autostart_runner
    import process_watch
    monkeypatch.setattr(autostart_runner, "headset_peers", lambda: [("127.0.0.1", 40000)])
    monkeypatch.setattr(process_watch, "host_answers", lambda ip: pytest.fail("angefragt"))
    assert window._live_headset_peers() is None


def test_tote_verbindung_startet_programme_nicht_neu(window, monkeypatch):
    import autostart_runner
    monkeypatch.setattr(autostart_runner, "headset_peers", lambda: [PEER])
    window._dead_peers = {PEER}
    assert window.is_headset_connected() is False
    monkeypatch.setattr(autostart_runner, "headset_peers", lambda: [("192.168.1.50", 40001)])
    assert window.is_headset_connected() is True
    assert window._dead_peers == set()


@pytest.fixture
def poweroff(rearm, monkeypatch):
    calls = []
    monkeypatch.setattr(type(rearm), "_live_headset_peers", lambda self: [PEER])
    monkeypatch.setattr(type(rearm), "stop_wivrn_server", lambda self: calls.append("stop"))
    rearm.ui.chk_restart_on_poweroff.setChecked(True)
    rearm._calls = calls
    return rearm


def test_neustart_standardmaessig_an(window):
    assert window.ui.chk_restart_on_poweroff.isChecked()


def test_ausgeschaltet_startet_eigenen_server_neu(poweroff, armed):
    poweroff.server_process = _Proc(None)
    _nach_frist(poweroff)
    poweroff.server_process = None
    assert poweroff._calls == ["stop"] and poweroff._restart_after_stop is True
    assert armed == []
    poweroff._restart_after_stop = False


def test_fremder_server_wird_nicht_neu_gestartet(poweroff):
    poweroff.server_process = None
    _nach_frist(poweroff)
    assert poweroff._calls == [] and poweroff._restart_after_stop is False


def test_normales_trennen_startet_nicht_neu(poweroff, monkeypatch):
    monkeypatch.setattr(type(poweroff), "_live_headset_peers", lambda self: [])
    poweroff.server_process = _Proc(None)
    _nach_frist(poweroff)
    poweroff.server_process = None
    assert poweroff._calls == []


def test_option_aus_startet_nicht_neu(poweroff):
    poweroff.ui.chk_restart_on_poweroff.setChecked(False)
    poweroff.server_process = _Proc(None)
    _nach_frist(poweroff)
    poweroff.server_process = None
    assert poweroff._calls == []


def test_neustart_laeuft_nach_dem_beenden(window, state):
    state["running"] = False
    window._server_running = False
    window._restart_server_now()
    assert window._starts == [1]


def test_kein_neustart_wenn_beenden_scheitert(window, monkeypatch):
    import main
    planned = []
    monkeypatch.setattr(main.QTimer, "singleShot", staticmethod(lambda ms, fn: planned.append(fn)))
    window._restart_after_stop = True
    window._finish_server_shutdown(False)
    assert window._restart_after_stop is False
    assert window._restart_server_now not in planned
