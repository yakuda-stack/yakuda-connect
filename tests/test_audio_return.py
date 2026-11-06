#!/usr/bin/env python3
"""Audio zurueck auf den PC, wenn das Headset weg ist (core/audio_return.py)."""
import json
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import audio_return
import autostart_runner

PEER = ("192.168.1.50", 40000)


class FakePactl:
    def __init__(self, sinks, sources, default_sink, default_source):
        self.devices = {"sink": list(sinks), "source": list(sources)}
        self.default = {"sink": default_sink, "source": default_source}
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        cmd = args[0]
        if cmd.startswith("get-default-"):
            return self.default[cmd.rsplit("-", 1)[1]]
        if cmd == "list":
            kind = args[1][:-1]
            return "\n".join(f"{i}\t{n}\tmodule\tfmt\tIDLE"
                             for i, n in enumerate(self.devices[kind]))
        if cmd.startswith("set-default-"):
            kind = cmd.rsplit("-", 1)[1]
            if args[1] not in self.devices[kind]:
                return None
            self.default[kind] = args[1]
            return ""
        return None


@pytest.fixture
def pactl(monkeypatch, tmp_path):
    fake = FakePactl(["alsa_output.pc", "wivrn.sink"],
                     ["alsa_output.pc.monitor", "alsa_input.mic", "wivrn.source"],
                     "alsa_output.pc", "alsa_input.mic")
    monkeypatch.setattr(audio_return, "_pactl", fake)
    monkeypatch.setattr(audio_return, "available", lambda: True)
    monkeypatch.setattr(audio_return, "STATE_FILE", str(tmp_path / "audio-return.json"))
    return fake


def _headset_takes_over(pactl):
    pactl.default = {"sink": "wivrn.sink", "source": "wivrn.source"}


# --------------------------------------------------------------------------- #
#  HeadsetPresence
# --------------------------------------------------------------------------- #
def _presence(peers, answers):
    return audio_return.HeadsetPresence(lambda: list(peers), answers=lambda ip: answers[0],
                                        grace=3)


def test_verbinden_und_standby_werden_erkannt():
    peers, answers = [PEER], [True]
    p = _presence(peers, answers)
    assert p.update() == "connected"
    assert p.update() is None
    answers[0] = False
    assert [p.update() for _ in range(3)] == [None, None, "gone"]
    assert p.update() is None


def test_kurzer_aussetzer_zaehlt_nicht():
    peers, answers = [PEER], [True]
    p = _presence(peers, answers)
    p.update()
    answers[0] = False
    p.update()
    p.update()
    answers[0] = True
    assert p.update() is None
    answers[0] = False
    assert [p.update() for _ in range(3)] == [None, None, "gone"]


def test_geraet_das_nie_antwortet_gilt_als_da():
    p = _presence([PEER], [False])
    assert p.update() == "connected"
    assert [p.update() for _ in range(5)] == [None] * 5


def test_verbindung_weg_ist_trennen():
    peers, answers = [PEER], [True]
    p = _presence(peers, answers)
    p.update()
    peers.clear()
    assert [p.update() for _ in range(3)] == [None, None, "gone"]


def test_usb_braucht_keine_anfrage():
    asked = []
    p = audio_return.HeadsetPresence(lambda: [("127.0.0.1", 1)],
                                     answers=lambda ip: asked.append(ip) or False)
    assert p.update() == "connected"
    assert asked == []


def test_tote_verbindung_zaehlt_nach_trennen_nicht_mehr():
    peers, answers = [PEER], [True]
    p = _presence(peers, answers)
    p.update()
    answers[0] = False
    for _ in range(3):
        p.update()
    answers[0] = True
    assert p.update() is None
    peers[:] = [("192.168.1.50", 40001)]
    assert p.update() == "connected"


# --------------------------------------------------------------------------- #
#  Umstellen
# --------------------------------------------------------------------------- #
def test_trennen_stellt_auf_gemerkte_pc_geraete(pactl):
    audio_return.remember_pc_devices()
    _headset_takes_over(pactl)
    assert sorted(audio_return.handle("gone")) == ["sink", "source"]
    assert pactl.default == {"sink": "alsa_output.pc", "source": "alsa_input.mic"}


def test_wiederkommen_stellt_zurueck_aufs_headset(pactl):
    audio_return.remember_pc_devices()
    _headset_takes_over(pactl)
    audio_return.handle("gone")
    assert sorted(audio_return.handle("connected")) == ["sink", "source"]
    assert pactl.default == {"sink": "wivrn.sink", "source": "wivrn.source"}
    assert audio_return.load_state()["switched"] == {}


def test_nutzerwahl_wird_nicht_ueberschrieben(pactl):
    audio_return.remember_pc_devices()
    _headset_takes_over(pactl)
    audio_return.handle("gone")
    pactl.devices["sink"].append("bluetooth.kopfhoerer")
    pactl.default["sink"] = "bluetooth.kopfhoerer"
    assert audio_return.handle("connected") == ["source"]
    assert pactl.default["sink"] == "bluetooth.kopfhoerer"


def test_pc_geraet_bleibt_unangetastet(pactl):
    audio_return.remember_pc_devices()
    assert audio_return.handle("gone") == []
    assert not any(c[0].startswith("set-") for c in pactl.calls)


def test_ohne_gemerktes_geraet_erstes_pc_geraet(pactl):
    _headset_takes_over(pactl)
    audio_return.handle("gone")
    assert pactl.default == {"sink": "alsa_output.pc", "source": "alsa_input.mic"}


def test_monitor_ist_kein_mikrofon(pactl):
    pactl.devices["source"] = ["alsa_output.pc.monitor", "wivrn.source"]
    _headset_takes_over(pactl)
    assert audio_return.handle("gone") == ["sink"]
    assert pactl.default["source"] == "wivrn.source"


def test_wivrn_geraet_wird_nie_gemerkt(pactl):
    _headset_takes_over(pactl)
    audio_return.remember_pc_devices()
    assert "sink" not in audio_return.load_state()


def test_ohne_pactl_passiert_nichts(pactl, monkeypatch):
    monkeypatch.setattr(audio_return, "available", lambda: False)
    _headset_takes_over(pactl)
    assert audio_return.handle("gone") == []
    assert pactl.calls == []


# --------------------------------------------------------------------------- #
#  Waechter im Terminal-Modus
# --------------------------------------------------------------------------- #
class _Presence:
    def __init__(self, events):
        self.events = list(events)

    def update(self):
        return self.events.pop(0) if self.events else None


@pytest.fixture
def state_file(monkeypatch, tmp_path):
    monkeypatch.setattr(autostart_runner, "STATE_FILE", str(tmp_path / "cli.json"))
    monkeypatch.setattr(audio_return, "remember_pc_devices", lambda: None)


def test_waechter_reicht_ereignisse_weiter(state_file):
    seen = []
    autostart_runner.audio_watch(_sleep=lambda s: None, _server_running=lambda: True,
                                 _presence=_Presence([None, "gone", None, "connected"]),
                                 _handle=seen.append, _max_ticks=4)
    assert seen == ["gone", "connected"]


def test_waechter_endet_mit_dem_server(state_file):
    runs = iter([True, True, False])
    ticks = []
    autostart_runner.audio_watch(_sleep=ticks.append, _server_running=lambda: next(runs),
                                 _presence=_Presence([]), _handle=lambda e: None)
    assert len(ticks) == 2
    assert autostart_runner.load_state()["audio_watcher"] is None


def test_waechter_aus_wenn_option_aus(state_file):
    assert autostart_runner.arm_audio({audio_return.SETTING_KEY: False}, ["true"]) == "off"


def test_waechter_laeuft_nur_einmal(state_file, monkeypatch):
    started = []
    monkeypatch.setattr(autostart_runner.subprocess, "Popen",
                        lambda *a, **k: started.append(a) or type("P", (), {"pid": os.getpid()})())
    assert autostart_runner.arm_audio({}, ["x"]) == "armed"
    assert autostart_runner.arm_audio({}, ["x"]) == "running"
    assert len(started) == 1


def test_cli_kennt_den_waechter():
    import cli
    assert "_audio-watch" in cli.COMMANDS


def test_texte_in_allen_sprachen():
    root = os.path.join(os.path.dirname(__file__), "..", "locales")
    for lang in ("de", "en", "fr"):
        with open(os.path.join(root, f"{lang}.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        assert data.get("audio_return_label") and data.get("audio_return_tip")


# --------------------------------------------------------------------------- #
#  Oberflaeche
# --------------------------------------------------------------------------- #
@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    import paths
    import config_manager
    import exit_guard
    import wivrn_server
    monkeypatch.setattr(paths, "config_file", lambda name: str(tmp_path / name))
    monkeypatch.setattr(config_manager, "CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setattr(wivrn_server, "is_running", lambda p=None: True)
    monkeypatch.setattr(wivrn_server, "stop_blocking", lambda *a, **k: True)
    from main import VRApp
    monkeypatch.setattr(VRApp, "are_critical_packages_missing", lambda self: False)
    monkeypatch.setattr(VRApp, "refresh_headset_list", lambda self: None)
    w = VRApp()
    w._exit_guard = exit_guard.ExitGuard(popen=lambda *a, **k: None)
    w._stop_server_with_app = False
    jobs = []
    monkeypatch.setattr(type(w), "_run_audio_job", lambda self, f, *a: jobs.append((f, a)))
    w._jobs = jobs
    yield w
    w.close()


def test_schalter_standardmaessig_an(window):
    assert window.ui.chk_audio_return.isChecked()
    assert window._audio_return_timer.isActive()


def test_schalter_aus_wird_gespeichert(window, tmp_path):
    window.ui.chk_audio_return.setChecked(False)
    assert not window._audio_return_timer.isActive()
    with open(tmp_path / "config.json") as fh:
        assert json.load(fh)[audio_return.SETTING_KEY] is False


def test_oberflaeche_stellt_bei_trennen_um(window, monkeypatch):
    monkeypatch.setattr(autostart_runner, "audio_watcher_running", lambda state=None: False)
    window._audio_presence = _Presence(["gone"])
    window._check_audio_return()
    assert window._jobs[0][0] is audio_return.remember_pc_devices
    assert window._jobs[1] == (audio_return.handle, ("gone",))


def test_oberflaeche_laesst_terminal_waechter_machen(window, monkeypatch):
    monkeypatch.setattr(autostart_runner, "audio_watcher_running", lambda state=None: True)
    window._audio_pc_remembered = True
    window._audio_presence = _Presence(["gone"])
    window._check_audio_return()
    assert window._jobs == []
