#!/usr/bin/env python3
"""WiVRn verwaltet active_runtime.json waehrend einer Sitzung selbst (Verknuepfung
auf sein Manifest). Die App darf nie hindurch schreiben, zeigt den Zustand als
„von WiVRn verwaltet“ und sperrt Umschalten/Reparieren, solange ein Headset
verbunden ist."""
import json
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "core"))

import pytest  # noqa: E402

import openxr_manager as oxr  # noqa: E402
import vr_environment as venv  # noqa: E402

RELATIVE = {"file_format_version": "1.0.0",
            "runtime": {"name": "WiVRn", "library_path": "../../../lib/wivrn/libopenxr_wivrn.so"}}


@pytest.fixture
def home(tmp_path, monkeypatch):
    cfg = tmp_path / ".config/openxr/1"
    cfg.mkdir(parents=True)
    share = tmp_path / "share/openxr/1"
    share.mkdir(parents=True)
    manifest = share / "openxr_wivrn.json"
    manifest.write_text(json.dumps(RELATIVE))
    so = tmp_path / "libopenxr_wivrn.so"
    so.write_bytes(b"\x7fELF\x02" + b"\0" * 60)
    active = cfg / "active_runtime.json"
    monkeypatch.setattr(oxr, "ACTIVE_RUNTIME", str(active))
    monkeypatch.setattr(venv, "primary_active_runtime", lambda: str(active))
    monkeypatch.setattr(venv, "openxr_config_dirs", lambda: [str(cfg)])
    monkeypatch.setattr(oxr, "find_wivrn_libs", lambda: (str(so), ""))
    monkeypatch.setattr(oxr, "_is_elf", lambda p: True)
    monkeypatch.setattr(oxr, "session_active", lambda: False)
    return {"active": active, "manifest": manifest, "so": so}


def _link(h):
    os.symlink(str(h["manifest"]), str(h["active"]))


def test_wivrn_link_counts_as_managed_not_broken(home):
    _link(home)
    assert oxr.wivrn_managed()
    assert oxr.current_status()[0] == "managed"
    assert oxr.is_openxr_fix_applied()
    assert oxr.active_runtime_name() == "wivrn"


def test_fix_removes_link_and_never_writes_through(home):
    _link(home)
    before = home["manifest"].read_text()
    ok, code, backup = oxr.apply_openxr_fix()
    assert ok and code == "ok" and backup == ""
    assert not os.path.islink(home["active"])                 # echte Datei jetzt
    assert home["manifest"].read_text() == before             # WiVRns Manifest unangetastet
    assert json.loads(home["active"].read_text())["runtime"]["library_path"] == str(home["so"])


def test_steamvr_switch_removes_link_too(home, monkeypatch):
    _link(home)
    before = home["manifest"].read_text()
    monkeypatch.setattr(venv, "find_steamvr_lib", lambda: "/steam/vrclient.so")
    ok, _code, _b = oxr.apply_steamvr_runtime()
    assert ok and not os.path.islink(home["active"])
    assert home["manifest"].read_text() == before


def test_regular_file_is_still_backed_up(home):
    home["active"].write_text(json.dumps(RELATIVE))
    ok, _code, backup = oxr.apply_openxr_fix()
    assert ok and backup and os.path.exists(backup)


def test_nothing_written_during_session(home, monkeypatch):
    _link(home)
    monkeypatch.setattr(oxr, "session_active", lambda: True)
    for fn in (oxr.apply_openxr_fix, oxr.apply_steamvr_runtime, oxr.apply_openxr_fix_elevated):
        assert fn()[:2] == (False, "session")
    assert os.path.islink(home["active"])                     # WiVRns Zustand bleibt


def test_elevated_script_removes_link_first(home, monkeypatch):
    import subprocess
    seen = {}

    class R:
        returncode = 0
        stdout = stderr = ""

    def fake_run(cmd, **kw):
        seen["script"] = cmd[-1]
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)
    oxr.apply_openxr_fix_elevated()
    target = str(home["active"])
    assert f"if [ -L '{target}' ]; then rm -f '{target}'" in seen["script"]


def test_session_active_uses_configured_port(monkeypatch):
    import process_watch
    seen = {}
    monkeypatch.setattr(oxr, "_session_port", lambda: 9800)
    monkeypatch.setattr(process_watch, "headset_connected",
                        lambda port=9757, **k: seen.setdefault("port", port) and False)
    monkeypatch.setattr(oxr, "wivrn_managed", lambda path=None: False)
    assert oxr.session_active() is False and seen["port"] == 9800


def test_runtime_widget_locked_during_session(qapp, monkeypatch):
    from ui.vr_runtime_widget import VrRuntimeWidget
    monkeypatch.setattr(oxr, "session_active", lambda: True)
    w = VrRuntimeWidget()
    w.check_active_openxr_runtime()
    assert not w.btn_switch_wivrn.isEnabled() and not w.btn_switch_steamvr.isEnabled()
    monkeypatch.setattr(oxr, "session_active", lambda: False)
    w.check_active_openxr_runtime()
    assert w.btn_switch_wivrn.isEnabled() and w.btn_switch_steamvr.isEnabled()
    w.deleteLater()


def test_optimize_skips_runtime_during_session(monkeypatch):
    import vr_optimize as vopt
    monkeypatch.setattr(oxr, "find_wivrn_libs", lambda: ("/x.so", ""))
    monkeypatch.setattr(oxr, "session_active", lambda: True)
    assert vopt.runtime_needed() is False
