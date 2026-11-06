#!/usr/bin/env python3
"""Headset-Erkennung: nutzt den Port aus WiVRns Config und startet nichts."""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import autostart_runner
import process_watch
import vr_environment as venv


def _setup(monkeypatch, tmp_path, data):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    monkeypatch.setattr(venv, "wivrn_config_file", lambda: str(path))
    seen = []
    monkeypatch.setattr(process_watch, "headset_connected",
                        lambda port=0: seen.append(port) or True)
    return seen


def test_standardport(monkeypatch, tmp_path):
    seen = _setup(monkeypatch, tmp_path, {})
    assert autostart_runner.headset_connected() is True
    assert seen == [9757]


def test_eigener_port(monkeypatch, tmp_path):
    seen = _setup(monkeypatch, tmp_path, {"port": 12345})
    autostart_runner.headset_connected()
    assert seen == [12345]


def test_kaputte_config_faellt_auf_standard(monkeypatch, tmp_path):
    seen = _setup(monkeypatch, tmp_path, {"port": "kaputt"})
    autostart_runner.headset_connected()
    assert seen == [9757]


def test_startet_keinen_prozess(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, {})

    def fail(*_a, **_k):
        raise AssertionError("Prozess gestartet")
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(subprocess, "Popen", fail)
    assert autostart_runner.headset_connected() is True


def _tcp(tmp_path, remote):
    net = tmp_path / "net"
    net.mkdir()
    head = "sl local rem st\n"
    (net / "tcp").write_text(head + f"0: 0100007F:261D {remote} 01 x\n")
    (net / "tcp6").write_text(head)
    return str(tmp_path)


def test_gegenstelle_wird_gelesen(tmp_path):
    root = _tcp(tmp_path, "3201A8C0:9C40")
    assert process_watch.headset_peers(root) == [("192.168.1.50", 40000)]


def test_ipv4_im_ipv6_socket(tmp_path):
    net = tmp_path / "net"
    net.mkdir()
    (net / "tcp").write_text("kopf\n")
    (net / "tcp6").write_text(
        "kopf\n0: 0:261D 0000000000000000FFFF00003201A8C0:9C40 01 x\n")
    assert process_watch.headset_peers(str(tmp_path)) == [("192.168.1.50", 40000)]


def test_abgewiesene_anfrage_zaehlt_als_antwort():
    import errno
    import socket

    class Probe:
        code = errno.ECONNREFUSED

        def __init__(self, *_a):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def settimeout(self, _t):
            pass

        def connect_ex(self, _addr):
            return Probe.code

    original = socket.socket
    socket.socket = Probe
    try:
        assert process_watch.host_answers("192.168.1.50") is True
        Probe.code = errno.EHOSTUNREACH
        assert process_watch.host_answers("192.168.1.50") is False
    finally:
        socket.socket = original
