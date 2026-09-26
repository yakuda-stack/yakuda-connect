#!/usr/bin/env python3
"""
tests/test_autostart_profiles.py — Autostart-Tabs mit Bedingung
==============================================================
  * process_watch: Namensvergleich (VRChat == VRChat.exe == Z:\\...\\VRChat.exe),
    kein Teilstring-Treffer, gekuerztes comm, echte Prozesse in /proc
  * Dashboard: Tab „VR“ fest (kein ✕, nicht umbenennbar), „+“ legt Profile an
  * Ablauf: Ausloeser startet → Verzoegerung → Programme starten →
    Ausloeser weg (entprellt) → Programme werden beendet
  * Besen-Button schliesst Profil-Programme, ohne sie sofort neu zu starten
  * Speichern/Laden ueber config.json (andere Schluessel bleiben erhalten)
"""
import json
import os
import pathlib
import subprocess
import sys
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import process_watch as pw  # noqa: E402


# --------------------------------------------------------------------------- #
#  process_watch
# --------------------------------------------------------------------------- #
def _fake_proc(root, pid, comm, argv):
    d = root / str(pid)
    d.mkdir()
    (d / "comm").write_text(comm + "\n")
    (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + (b"\0" if argv else b""))


def test_norm():
    assert pw.norm("VRChat.exe") == "vrchat"
    assert pw.norm("Z:\\Games\\VRChat\\VRChat.exe") == "vrchat"
    assert pw.norm("/usr/bin/wivrn-server") == "wivrn-server"
    assert pw.norm('  "VRChat"  ') == "vrchat"


def test_snapshot_and_matches(tmp_path):
    _fake_proc(tmp_path, 100, "VRChat.exe", ["Z:\\steam\\VRChat\\VRChat.exe", "--no-vr"])
    _fake_proc(tmp_path, 101, "vrchat-osc-too", ["/usr/bin/vrchat-osc-tool"])
    _fake_proc(tmp_path, 102, "kworker/0:1", [])          # Kernel-Thread
    _fake_proc(tmp_path, 103, "SomeVeryLongGam", ["SomeVeryLongGame"])
    names = pw.snapshot(str(tmp_path))
    assert pw.matches("VRChat", names)
    assert pw.matches("vrchat.exe", names)
    assert pw.matches("vrchat-osc-tool", names)
    assert not pw.matches("vrc", names)                   # kein Teilstring
    assert not pw.matches("", names)
    assert pw.matches("SomeVeryLongGame.exe", names)


def test_long_name_only_in_comm(tmp_path):
    # Programm, dessen Kommandozeile nichts hergibt — nur comm (15 Zeichen).
    _fake_proc(tmp_path, 200, "averyverylongpr", ["python3", "x.py"])
    names = pw.snapshot(str(tmp_path))
    assert pw.matches("averyverylongprogram", names)


def test_real_process(tmp_path):
    script = tmp_path / "yc-test-trigger"
    script.write_text("#!/bin/sh\nsleep 30\n")
    script.chmod(0o755)
    p = subprocess.Popen(["/bin/sh", str(script)], start_new_session=True)
    try:
        time.sleep(0.2)
        assert pw.is_running("yc-test-trigger")
    finally:
        os.killpg(p.pid, 9)
        p.wait()
    assert not pw.is_running("yc-test-trigger")


def test_list_programs_contains_exe_names(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "getuid", lambda: os.stat(tmp_path).st_uid)
    _fake_proc(tmp_path, 300, "wine64-preload", ["Z:\\x\\VRChat.exe"])
    _fake_proc(tmp_path, 301, "bash", ["bash"])
    progs = pw.list_programs(str(tmp_path))
    assert "VRChat.exe" in progs and "bash" in progs


# --------------------------------------------------------------------------- #
#  Dashboard
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def app(qapp, tmp_path_factory):
    home = tmp_path_factory.mktemp("home")
    os.environ["HOME"] = str(home)
    from PySide6.QtWidgets import QMessageBox
    for m in ("warning", "information", "critical"):
        setattr(QMessageBox, m, staticmethod(lambda *a, **k: QMessageBox.Ok))
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    from main import VRApp
    window = VRApp()
    yield window
    window.close()


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Eigene config.json pro Test."""
    import config_manager
    import tabs.autostart_profiles_mixin as mix
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"language": "de", "autostart_count": "2"}))
    monkeypatch.setattr(config_manager, "CONFIG_FILE", str(path))
    monkeypatch.setattr(mix, "CONFIG_FILE", str(path))
    return path


@pytest.fixture
def clean(app, cfg):
    """Nach jedem Test alle Profil-Tabs wieder weg. Headset gilt als verbunden,
    Hauptschalter („Mit App-Profilen starten“) ist an."""
    app._profile_headset = lambda: True
    app.ui.toggle_profiles.setChecked(True)
    yield app
    for prof in list(app._profiles):
        app._profile_stop(prof)
    while app.ui.autostart_tabs.count() > 0:
        app.ui.autostart_tabs.removeTab(0)
    app._profiles.clear()
    app._profile_timer.stop()
    # Verzoegertes Speichern verwerfen — es wuerde sonst NACH dem Test in
    # die echte config.json schreiben (monkeypatch ist dann schon zurueck).
    app._profile_save_timer.stop()


def _new_profile(app, trigger="yc-fake-trigger", cmd="sleep 60", delay=0):
    prof = app._profile_add({"name": "Test", "trigger": trigger, "delay": delay,
                             "stop_with": True, "enabled": True,
                             "apps": [{"type": "CMD", "cmd": cmd}]})
    return prof


def test_profiles_live_in_streaming_tab(app, clean):
    """Dashboard nur VR-Autostart; Profile als Gruppe oben im Streaming-Tab."""
    group = app.ui.autostart_profiles_group
    assert group.parent() is app.streaming_settings
    lay = app.streaming_settings.layout()
    assert lay.indexOf(group) == lay.count() - 2          # unten, vor dem Stretch
    assert lay.indexOf(group) > lay.indexOf(app.streaming_settings.encoder_group)
    assert not app.ui.autostart_group.isAncestorOf(app.ui.autostart_tabs)
    assert app.ui.autostart_group.isAncestorOf(app.ui.btn_autostart_add_vr_row)
    # Ohne Profil: Hinweis statt leerer Tab-Leiste
    app._profiles_update_empty()
    assert app.ui.autostart_tabs.isHidden() and not app.ui.lbl_profiles_empty.isHidden()


def test_add_via_plus_button(app, clean, cfg, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("VRChat-Extras", True)))
    app.ui.btn_autostart_add_profile.click()
    tabs = app.ui.autostart_tabs
    assert tabs.count() == 1 and tabs.tabText(0) == "VRChat-Extras"
    assert tabs.currentIndex() == 0 and not tabs.isHidden()
    # Umbenennen per Doppelklick
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Neu", True)))
    app._profile_rename(0)
    assert tabs.tabText(0) == "Neu"
    app._profiles_save_now()
    data = json.loads(cfg.read_text())
    assert data["autostart_profiles"][0]["name"] == "Neu"
    assert data["autostart_count"] == "2"                 # Rest unberuehrt
    # Loeschen
    app._profile_close_requested(0)
    assert tabs.count() == 0 and tabs.isHidden()


def test_timer_only_when_needed(app, clean):
    prof = _new_profile(app, trigger="", cmd="")
    app._profiles_update_timer()
    assert not app._profile_timer.isActive()
    prof["inp_trigger"].setText("VRChat.exe")
    prof["rows"][0]["input"].setText("sleep 1")
    app._profiles_update_timer()
    assert app._profile_timer.isActive()
    prof["chk_enabled"].setChecked(False)
    app._profiles_update_timer()
    assert not app._profile_timer.isActive()


def test_start_delay_and_stop_with_trigger(app, clean):
    prof = _new_profile(app, delay=5)
    t0 = 1000.0
    on = {"yc-fake-trigger"}
    app._profile_step(prof, on, t0)
    assert not prof["launched"] and prof["seen_since"] == t0
    app._profile_step(prof, on, t0 + 3)
    assert not prof["launched"]                          # Verzoegerung laeuft
    app._profile_step(prof, on, t0 + 5)
    assert prof["launched"] and len(prof["procs"]) == 1
    proc = prof["procs"][0]
    assert proc.poll() is None
    app._profile_step(prof, on, t0 + 8)
    assert len(prof["procs"]) == 1                       # nicht doppelt
    # Ausloeser weg: erster Tick = Aussetzer, zweiter = wirklich beendet
    app._profile_step(prof, set(), t0 + 11)
    assert proc.poll() is None
    app._profile_step(prof, set(), t0 + 14)
    assert proc.poll() is not None
    assert not prof["launched"] and prof["seen_since"] is None


def test_short_gap_does_not_kill(app, clean):
    prof = _new_profile(app)
    on = {"yc-fake-trigger"}
    app._profile_step(prof, on, 0)
    proc = prof["procs"][0]
    app._profile_step(prof, set(), 3)                    # kurzer Aussetzer
    app._profile_step(prof, on, 6)
    app._profile_step(prof, set(), 9)
    assert proc.poll() is None and prof["launched"]


def test_stop_with_off_keeps_apps(app, clean):
    prof = _new_profile(app)
    prof["chk_stop"].setChecked(False)
    app._profile_step(prof, {"yc-fake-trigger"}, 0)
    proc = prof["procs"][0]
    app._profile_step(prof, set(), 3)
    app._profile_step(prof, set(), 6)
    assert proc.poll() is None and not prof["launched"]
    proc.kill()
    proc.wait()


def test_broom_kills_without_restart(app, clean):
    prof = _new_profile(app)
    app._profile_step(prof, {"yc-fake-trigger"}, 0)
    proc = prof["procs"][0]
    app.kill_autostart_apps()
    assert proc.poll() is not None
    app._profile_step(prof, {"yc-fake-trigger"}, 3)
    assert prof["procs"] == [] and prof["launched"]      # kein Neustart


def test_load_roundtrip(app, clean, cfg):
    import tabs.autostart_profiles_mixin as mix
    prof = _new_profile(app, trigger="VRChat.exe", delay=20)
    app._profile_add_row(prof, {"type": "Custom Path", "cmd": "/opt/x", "debug": True})
    app._profiles_save_now()
    loaded = mix.load_profiles()
    assert loaded == [{
        "name": "Test", "trigger": "VRChat.exe", "delay": 20, "gap": 0,
        "stop_with": True, "enabled": True,
        "apps": [{"type": "CMD", "cmd": "sleep 60", "debug": False},
                 {"type": "Custom Path", "cmd": "/opt/x", "debug": True}],
    }]


def test_retranslate(app, clean):
    from translations import set_language, tr
    prof = _new_profile(app)
    set_language("en")
    app.autostart_profiles_retranslate()
    assert prof["btn_start_now"].text() == tr("autostart_profile_start_now") == "▶  Start programs"
    assert prof["chk_enabled"].text() == "⏸ Stop timer"
    set_language("de")
    app.autostart_profiles_retranslate()
    assert prof["btn_start_now"].text() == "▶  Programme starten"
    prof["chk_enabled"].setChecked(False)
    assert prof["chk_enabled"].text() == "▶ Timer starten"


def test_bracket_key_matches_appid():
    names = {"appid=438100", "reaper"}
    assert pw.matches("VRChat [AppId=438100]", names)
    assert not pw.matches("Beat Saber [AppId=620980]", names)
    assert pw.match_key("VRChat [AppId=438100]") == "AppId=438100"
    assert pw.match_key("VRChat.exe") == "VRChat.exe"


def test_real_steam_reaper_cmdline(tmp_path):
    # So sieht Steams reaper fuer ein Proton-Spiel aus.
    _fake_proc(tmp_path, 500, "reaper", [
        "/home/u/.local/share/Steam/ubuntu12_32/reaper", "SteamLaunch",
        "AppId=438100", "--", "/home/u/.steam/steamapps/common/Proton/proton",
        "waitforexitandrun", "/games/VRChat/VRChat.exe"])
    names = pw.snapshot(str(tmp_path))
    assert pw.matches("VRChat [AppId=438100]", names)


def test_game_trigger_texts(monkeypatch):
    import tabs.autostart_profiles_mixin as mix
    assert mix.game_trigger({"id": "438100", "name": "VRChat", "kind": "steam", "exe": ""}) \
        == "VRChat [AppId=438100]"
    assert mix.game_trigger({"id": "local:1", "name": "Mein Spiel", "kind": "local",
                             "exe": "/games/x/MyGame.x86_64"}) == "Mein Spiel [MyGame.x86_64]"
    import steam_shortcuts
    monkeypatch.setattr(steam_shortcuts, "get",
                        lambda appid, roots=None: {"exe": '"Z:\\g\\Foo.exe"'})
    assert mix.game_trigger({"id": "3000000000", "name": "Foo", "kind": "shortcut",
                             "exe": ""}) == "Foo [Foo.exe]"


def test_games_button_sets_trigger(app, clean, monkeypatch):
    import games as games_db
    from PySide6.QtWidgets import QDialog
    monkeypatch.setattr(games_db, "games_tab_entries", lambda: [
        {"id": "620980", "name": "Beat Saber", "kind": "steam", "exe": ""},
        {"id": "438100", "name": "VRChat", "kind": "steam", "exe": ""}])
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.Accepted)
    prof = _new_profile(app, trigger="")
    app._profile_pick_game(prof)
    # sortiert nach Name -> erste Zeile = Beat Saber
    assert prof["inp_trigger"].text() == "Beat Saber [AppId=620980]"


def test_start_now_and_timer_off(app, clean):
    prof = _new_profile(app)
    prof["chk_enabled"].setChecked(False)                 # Timer aus
    app._profiles_update_timer()
    assert not app._profile_timer.isActive()
    app._profile_start_now(prof)
    proc = prof["procs"][0]
    assert proc.poll() is None and prof["manual"]
    # Ausloeser laeuft nicht — von Hand Gestartetes bleibt trotzdem
    for t in (3, 6, 9):
        app._profile_step(prof, set(), t)
    assert proc.poll() is None
    assert "Hand" in prof["lbl_status"].text() or "hand" in prof["lbl_status"].text()
    # Nochmal druecken: alte weg, neue da (nichts doppelt)
    app._profile_start_now(prof)
    assert proc.poll() is not None and len(prof["procs"]) == 1
    app.kill_autostart_apps()
    assert prof["procs"] == []


def test_manual_then_trigger_takes_over(app, clean):
    prof = _new_profile(app)
    app._profile_start_now(prof)
    proc = prof["procs"][0]
    app._profile_step(prof, {"yc-fake-trigger"}, 0)       # Spiel startet
    assert not prof["manual"] and prof["procs"] == [proc]  # kein Doppelstart
    app._profile_step(prof, set(), 3)
    app._profile_step(prof, set(), 6)                     # Spiel zu -> mit beenden
    assert proc.poll() is not None


# --------------------------------------------------------------------------- #
#  Headset-Pflicht, Staffel-Start, Punkt am Tab
# --------------------------------------------------------------------------- #
def test_needs_headset(app, clean):
    prof = _new_profile(app)
    app._profile_headset = lambda: False
    app._profile_step(prof, {"yc-fake-trigger"}, 0)
    assert not prof["launched"] and prof["procs"] == []
    app._profile_render_status(prof)
    assert "headset" in prof["lbl_status"].text().lower()
    app._profile_headset = lambda: True
    app._profile_step(prof, {"yc-fake-trigger"}, 3)
    assert prof["launched"]


def test_headset_only_checked_when_trigger_runs(app, clean):
    prof = _new_profile(app)
    calls = []
    app._profile_headset = lambda: calls.append(1) or True
    app._profile_step(prof, set(), 0)
    assert calls == []


def test_headset_lost_stops_apps(app, clean):
    prof = _new_profile(app)
    app._profile_step(prof, {"yc-fake-trigger"}, 0)
    proc = prof["procs"][0]
    app._profile_headset = lambda: False       # Brille ab, Spiel laeuft weiter
    app._profile_step(prof, {"yc-fake-trigger"}, 3)
    app._profile_step(prof, {"yc-fake-trigger"}, 6)
    assert proc.poll() is not None


def test_staggered_start(app, clean, qapp, monkeypatch):
    # Der echte Takt laeuft beim Warten mit — dort soll das Spiel auch „laufen“.
    monkeypatch.setattr(pw, "snapshot", lambda *a, **k: {"yc-fake-trigger"})
    prof = _new_profile(app)
    app._profile_add_row(prof, {"type": "CMD", "cmd": "sleep 61"})
    prof["spin_gap"].setValue(1)
    app._profile_step(prof, {"yc-fake-trigger"}, 0)
    assert len(prof["procs"]) == 1                    # erstes sofort
    deadline = time.time() + 3
    while len(prof["procs"]) < 2 and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.05)
    assert len(prof["procs"]) == 2                    # zweites nach 1 s


def test_stop_cancels_pending_staggered(app, clean, qapp):
    prof = _new_profile(app)
    app._profile_add_row(prof, {"type": "CMD", "cmd": "sleep 61"})
    prof["spin_gap"].setValue(1)
    app._profile_step(prof, {"yc-fake-trigger"}, 0)
    app._profile_stop(prof)
    deadline = time.time() + 1.6
    while time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.05)
    assert prof["procs"] == []                        # verfallen, nicht nachgestartet


def test_tab_dot(app, clean):
    prof = _new_profile(app)
    idx = app.ui.autostart_tabs.indexOf(prof["page"])
    app._refresh_tab_dots()
    assert app.ui.autostart_tabs.tabIcon(idx).isNull()
    app._profile_step(prof, {"yc-fake-trigger"}, 0)
    assert not app.ui.autostart_tabs.tabIcon(idx).isNull()
    app.kill_autostart_apps()
    assert app.ui.autostart_tabs.tabIcon(idx).isNull()


def test_no_timer_without_profiles(app, clean):
    app._profiles_update_timer()
    assert not app._profile_timer.isActive()


# --------------------------------------------------------------------------- #
#  VR-Tab: + Programm / ✕ je Zeile
# --------------------------------------------------------------------------- #
def test_vr_tab_add_and_remove_rows(app, clean, cfg):
    while app.autostart_rows:
        app._vr_remove_row(app.autostart_rows[0])
    assert app.ui.num_apps.text() == "0"
    app.ui.btn_autostart_add_vr_row.click()
    app.ui.btn_autostart_add_vr_row.click()
    app.ui.btn_autostart_add_vr_row.click()
    assert len(app.autostart_rows) == 3 and app.ui.num_apps.text() == "3"
    for i, r in enumerate(app.autostart_rows):
        r["input"].setText(f"cmd{i}")
    app.autostart_rows[1]["btn_del"].click()          # mittlere Zeile weg
    assert [r["input"].text() for r in app.autostart_rows] == ["cmd0", "cmd2"]
    assert app.ui.num_apps.text() == "2"
    data = json.loads(cfg.read_text())
    assert data["autostart_count"] == "2"
    assert [a["cmd"] for a in data["autostart_apps"]] == ["cmd0", "cmd2"]
    while app.autostart_rows:
        app._vr_remove_row(app.autostart_rows[0])


# --------------------------------------------------------------------------- #
#  Gemeinsamer Kern + Headset-Check
# --------------------------------------------------------------------------- #
def test_engine_step_rules():
    import autostart_profiles as engine
    st = engine.new_state()
    assert engine.step(st, True, 0, True, 0) == "launch"
    assert engine.step(st, True, 0, True, 1) is None
    assert engine.step(st, False, 0, True, 2) is None     # Aussetzer
    assert engine.step(st, False, 0, True, 3) == "stop"
    st = engine.new_state()
    st.update(launched=True, manual=True)
    for t in range(5):
        assert engine.step(st, False, 0, True, t) is None
    assert engine.schedule([1, 2, 3], 5, 100) == [(100, 1), (105, 2), (110, 3)]


def test_engine_normalize_bad_data():
    import autostart_profiles as engine
    out = engine.normalize([None, {"name": "x" * 99, "delay": "abc", "gap": 999,
                                   "apps": [{"cmd": "a"}, "kaputt"]}])
    assert out[0]["name"] == "x" * engine.NAME_MAX
    assert out[0]["delay"] == 0 and out[0]["gap"] == engine.GAP_MAX
    assert out[0]["apps"] == [{"cmd": "a"}]


def test_headset_connected_from_proc_net(tmp_path):
    net = tmp_path / "net"
    net.mkdir()
    head = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid\n"
    (net / "tcp").write_text(head +
        "   0: 00000000:261D 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000\n")
    (net / "tcp6").write_text(head)
    assert not pw.headset_connected(str(tmp_path))       # nur LISTEN
    (net / "tcp6").write_text(head +
        "   0: 0000000000000000FFFF00000A00000A:261D 0000000000000000FFFF00000A000014:B2C4 01 "
        "00000000:00000000 00:00000000 00000000  1000\n")
    assert pw.headset_connected(str(tmp_path))           # ESTABLISHED auf 9757


# --------------------------------------------------------------------------- #
#  Terminal-Modus: Profil-Waechter
# --------------------------------------------------------------------------- #
@pytest.fixture
def runner(tmp_path, monkeypatch):
    import autostart_runner
    monkeypatch.setattr(autostart_runner, "STATE_FILE", str(tmp_path / "state.json"))
    started = []

    def fake_launch(apps, terminal_command=None):
        pids = []
        for a in apps:
            p = subprocess.Popen(["sleep", "60"], start_new_session=True)
            started.append((a["cmd"], p))
            pids.append(p.pid)
        return pids
    monkeypatch.setattr(autostart_runner, "launch_apps", fake_launch)
    yield autostart_runner, started
    for _c, p in started:
        try:
            os.killpg(p.pid, 9)
        except OSError:
            pass
        p.wait()


def _settings(gap=0, stop_with=True, master=True):
    return {"autostart_profiles_enabled": master, "autostart_profiles": [{
        "name": "VRC", "trigger": "VRChat [AppId=438100]", "delay": 0, "gap": gap,
        "stop_with": stop_with, "enabled": True,
        "apps": [{"type": "CMD", "cmd": "a"}, {"type": "CMD", "cmd": "b"}]}]}


def test_cli_profile_watch_start_and_stop(runner):
    run, started = runner
    clock = {"t": 0.0}
    game = {"on": True}
    server = {"on": True}

    def sleep(d):
        clock["t"] += d
        if clock["t"] > 20:
            game["on"] = False               # Spiel zu
        if clock["t"] > 40:
            server["on"] = False             # Server aus -> Waechter endet
    run.profile_watch(_settings(gap=5), _sleep=sleep, _now=lambda: clock["t"],
                      _snapshot=lambda: {"appid=438100"} if game["on"] else set(),
                      _headset=lambda: True, _server_running=lambda: server["on"],
                      _max_ticks=200)
    assert [c for c, _p in started] == ["a", "b"]         # gestaffelt, beide
    time.sleep(0.2)
    assert all(p.poll() is not None for _c, p in started)  # mit beendet
    st = run.load_state()
    assert st["profile_watcher"] is None and run.running_profile_apps(st) == []


def test_cli_profile_watch_needs_headset(runner):
    run, started = runner
    run.profile_watch(_settings(), _sleep=lambda d: None, _now=lambda: 0.0,
                      _snapshot=lambda: {"appid=438100"}, _headset=lambda: False,
                      _server_running=lambda: True, _max_ticks=5)
    assert started == []


def test_cli_adopts_handed_over_apps(runner):
    run, started = runner
    p = subprocess.Popen(["sleep", "60"], start_new_session=True)
    started.append(("uebergeben", p))
    import exit_guard
    run.remember_profile_apps([[p.pid, exit_guard.process_starttime(p.pid), 0]])
    # Spiel laeuft weiter -> nichts doppelt starten
    run.profile_watch(_settings(), _sleep=lambda d: None, _now=lambda: 0.0,
                      _snapshot=lambda: {"appid=438100"}, _headset=lambda: True,
                      _server_running=lambda: True, _max_ticks=3)
    assert [c for c, _p in started] == ["uebergeben"]
    assert run.running_profile_apps()[0][0] == p.pid
    assert run.kill_apps({}) == 1
    time.sleep(0.2)
    assert p.poll() is not None


def test_cli_arm_profiles_without_profiles(runner):
    run, _started = runner
    assert run.arm_profiles({}, ["true"]) == "no_profiles"


def test_master_switch_off(app, clean, cfg):
    prof = _new_profile(app)
    app._profiles_update_timer()
    assert app._profile_timer.isActive()
    app.ui.toggle_profiles.setChecked(False)
    assert not app._profile_timer.isActive()
    assert json.loads(cfg.read_text())["autostart_profiles_enabled"] is False
    app._profile_render_status(prof)
    assert "Automati" in prof["lbl_status"].text()
    # Knopf geht trotzdem
    app._profile_start_now(prof)
    assert prof["procs"] and prof["procs"][0].poll() is None


def test_stop_button(app, clean):
    prof = _new_profile(app)
    prof["btn_start_now"].click()
    proc = prof["procs"][0]
    assert prof["btn_start_now"].minimumHeight() >= 48     # im Headset gut treffbar
    prof["btn_stop_now"].click()
    assert proc.poll() is not None and prof["procs"] == []


def test_cli_master_off(runner):
    run, started = runner
    assert run.arm_profiles(_settings(master=False), ["true"]) == "no_profiles"
    run.profile_watch(_settings(master=False), _sleep=lambda d: None, _now=lambda: 0.0,
                      _snapshot=lambda: {"appid=438100"}, _headset=lambda: True,
                      _server_running=lambda: True, _max_ticks=3)
    assert started == []


def test_locales_complete():
    de = json.loads((ROOT / "locales" / "de.json").read_text())
    en = json.loads((ROOT / "locales" / "en.json").read_text())
    keys = [k for k in de if k.startswith("autostart_profile_")]
    assert len(keys) > 20
    assert all(k in en for k in keys)


# --------------------------------------------------------------------------- #
#  Gleicher Ausloeser in mehreren Profilen: nur eins aktiv
# --------------------------------------------------------------------------- #
def test_engine_blocked_by_same_trigger():
    import autostart_profiles as engine
    app_row = [{"cmd": "x"}]
    profs = [
        {"name": "A", "trigger": "VRChat.exe", "enabled": True, "apps": app_row},
        {"name": "B", "trigger": "vrchat", "enabled": True, "apps": app_row},
        {"name": "C", "trigger": "VRChat", "enabled": False, "apps": app_row},
        {"name": "D", "trigger": "Resonite", "enabled": True, "apps": app_row},
        {"name": "E", "trigger": "VRChat [AppId=438100]", "enabled": True, "apps": app_row},
    ]
    assert engine.blocked_by(profs) == {1: 0}
    assert engine.trigger_key("VRChat [AppId=438100]") == engine.trigger_key("x [appid=438100]")


def test_gui_enable_turns_other_same_trigger_off(app, clean):
    a = _new_profile(app, trigger="VRChat.exe")
    b = _new_profile(app, trigger="VRChat", cmd="sleep 61")
    # b wurde mit Timer an angelegt (alte Config) -> a gewinnt (erstes)
    assert app._profile_blocked_by(b) == a["name"] and app._profile_blocked_by(a) is None
    on = {"vrchat"}
    app._profile_step(a, on, 0)
    app._profile_step(b, on, 0)
    assert a["launched"] and not b["launched"]           # kein Doppelstart
    # b aktivieren -> a geht aus und seine Programme werden beendet
    b["chk_enabled"].setChecked(False)
    b["chk_enabled"].setChecked(True)
    assert not a["chk_enabled"].isChecked() and a["procs"] == []
    assert "Test" in a["lbl_status"].text()               # Hinweis mit Profilname
    app._profile_step(b, on, 1)
    assert b["launched"] and len(b["procs"]) == 1


def test_gui_trigger_edit_claims(app, clean):
    a = _new_profile(app, trigger="VRChat")
    b = _new_profile(app, trigger="Resonite")
    b["inp_trigger"].setText("VRChat.exe")
    b["inp_trigger"].editingFinished.emit()
    assert b["chk_enabled"].isChecked() and not a["chk_enabled"].isChecked()


def test_cli_profile_watch_same_trigger_only_first(runner):
    run, started = runner
    s = _settings()
    second = dict(s["autostart_profiles"][0], name="VRC2",
                  apps=[{"type": "CMD", "cmd": "c"}])
    s["autostart_profiles"].append(second)
    run.profile_watch(s, _sleep=lambda d: None, _now=lambda: 0.0,
                      _snapshot=lambda: {"appid=438100"}, _headset=lambda: True,
                      _server_running=lambda: True, _max_ticks=3)
    assert [c for c, _p in started] == ["a", "b"]         # "c" nie gestartet
