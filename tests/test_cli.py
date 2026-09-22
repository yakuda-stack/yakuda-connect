#!/usr/bin/env python3
"""
tests/test_cli.py — Terminal-Modus (core/cli.py, core/cli_install.py)

Wichtigste Pruefung: der Terminal-Modus laedt KEIN PySide6. Genau dafuer
gibt es ihn (RAM sparen unter VR).
"""
import os
import stat
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(args, home, extra_env=None):
    env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME="", XDG_CACHE_HOME="")
    env.update(extra_env or {})
    return subprocess.run([sys.executable, os.path.join(ROOT, "starter.py"), "--cli"] + args,
                          capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL,
                          timeout=60)


def test_cli_does_not_load_qt(tmp_path):
    code = (
        "import sys; sys.path.insert(0, %r); sys.path.insert(0, %r)\n"
        "import cli, cli_install, autostart_runner\n"
        "assert not any(m.startswith('PySide6') for m in sys.modules), "
        "[m for m in sys.modules if m.startswith('PySide6')]\n"
        % (os.path.join(ROOT, "core"), ROOT))
    env = dict(os.environ, HOME=str(tmp_path))
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert res.returncode == 0, res.stderr


def test_help_and_unknown(tmp_path):
    res = _run(["help"], tmp_path)
    assert res.returncode == 0
    for name in ("YC-help", "YC-wivrn-toggle", "YC-openvr", "YC-encoder", "YC-GPU",
                 "YC-killapps", "YC-autostart-reset", "YC-pairing"):
        assert name in res.stdout
    assert _run(["gibtsnicht"], tmp_path).returncode == 2


def test_encoder_direct_writes_both_configs(tmp_path):
    res = _run(["encoder", "vaapi"], tmp_path)
    assert res.returncode == 0, res.stderr
    import json
    ours = json.load(open(tmp_path / ".config/yakuda-connect/config/config.json"))
    assert ours["encoder"] == "vaapi"
    assert (tmp_path / ".config/wivrn/config.json").exists()


def test_bad_choice_changes_nothing(tmp_path):
    res = _run(["encoder", "99"], tmp_path)
    assert res.returncode == 0
    assert not (tmp_path / ".config/yakuda-connect/config/config.json").exists()


def test_shims_point_to_launcher_and_respect_foreign_files(tmp_path):
    sys.path.insert(0, os.path.join(ROOT, "core"))
    import cli_install
    target = tmp_path / "bin"
    target.mkdir()
    (target / "YC-GPU").write_text("#!/bin/sh\necho fremd\n")
    written, skipped = cli_install.install_user_shims(str(target), ["/x/My App.AppImage"])
    assert skipped == ["YC-GPU"]
    text = (target / "YC-encoder").read_text()
    assert "'/x/My App.AppImage' --cli encoder" in text
    assert (target / "YC-encoder").stat().st_mode & stat.S_IXUSR
    # Nochmal: eigene Dateien werden ueberschrieben, fremde nie.
    cli_install.install_user_shims(str(target), ["/neu"])
    assert "/neu --cli encoder" in (target / "YC-encoder").read_text()
    assert "fremd" in (target / "YC-GPU").read_text()
    removed = cli_install.remove_user_shims(str(target))
    assert "YC-GPU" not in removed and not (target / "YC-help").exists()


def test_install_kind_and_launcher(monkeypatch):
    sys.path.insert(0, os.path.join(ROOT, "core"))
    import cli_install
    monkeypatch.setenv("APPIMAGE", "/home/u/yc.AppImage")
    assert cli_install.install_kind() == "appimage"
    assert cli_install.cli_argv("gpu") == ["/home/u/yc.AppImage", "--cli", "gpu"]
    monkeypatch.delenv("APPIMAGE")
    monkeypatch.setattr(cli_install, "APP_DIR", "/usr/share/yakuda-connect")
    assert cli_install.install_kind() == "aur"
    monkeypatch.setattr(cli_install, "APP_DIR", "/opt/yakuda-connect")
    assert cli_install.install_kind() == "curl"
    monkeypatch.setattr(cli_install, "APP_DIR", "/home/u/src/yakuda-connect")
    assert cli_install.install_kind() == "source"
    assert cli_install.launcher_argv()[-1].endswith("starter.py")


def test_terminal_command(monkeypatch):
    sys.path.insert(0, os.path.join(ROOT, "core"))
    import cli_install
    monkeypatch.delenv("TERMINAL", raising=False)
    monkeypatch.setattr(cli_install.shutil, "which",
                        lambda p: "/usr/bin/konsole" if p == "konsole" else None)
    assert cli_install.terminal_command(["yc", "--cli"]) == ["konsole", "-e", "yc", "--cli"]
    monkeypatch.setattr(cli_install.shutil, "which", lambda p: None)
    assert cli_install.terminal_command(["yc"]) is None


# --------------------------------------------------------------------------- #
#  Autostart im Terminal-Modus (core/autostart_runner.py)
# --------------------------------------------------------------------------- #
def _runner(tmp_path, monkeypatch):
    sys.path.insert(0, os.path.join(ROOT, "core"))
    import autostart_runner
    monkeypatch.setattr(autostart_runner, "STATE_FILE", str(tmp_path / "state.json"))
    return autostart_runner


def test_configured_apps_respects_count_and_empty_rows(tmp_path, monkeypatch):
    ar = _runner(tmp_path, monkeypatch)
    settings = {"autostart_count": "2", "autostart_apps": [
        {"cmd": "a"}, {"cmd": "  "}, {"cmd": "c"}]}
    assert [a["cmd"] for a in ar.configured_apps(settings)] == ["a"]
    assert ar.configured_apps({"autostart_count": "x"}) == []


def test_watch_launches_once_then_killapps_stops_them(tmp_path, monkeypatch):
    ar = _runner(tmp_path, monkeypatch)
    monkeypatch.setattr(ar.wivrn_server, "is_running", lambda *a: True)
    marker = tmp_path / "ran"
    settings = {"autostart_count": "1",
                "autostart_apps": [{"cmd": f"touch {marker}; sleep 30"}],
                "custom_kill_commands": [{"cmd": f"touch {tmp_path / 'killcmd'}"}]}
    ticks = iter([False, False, True])
    ar.watch(settings, _sleep=lambda s: None, _connected=lambda: next(ticks))
    groups = ar.running_apps()
    assert len(groups) == 1
    assert ar.load_state()["watcher"] is None
    assert ar.kill_apps(settings) == 1
    assert (tmp_path / "killcmd").exists()
    assert ar.running_apps() == []


def test_watch_gives_up_when_server_stops(tmp_path, monkeypatch):
    ar = _runner(tmp_path, monkeypatch)
    monkeypatch.setattr(ar.wivrn_server, "is_running", lambda *a: False)
    started = []
    monkeypatch.setattr(ar, "launch_apps", lambda *a, **k: started.append(1) or [])
    ar.watch({"autostart_count": "1", "autostart_apps": [{"cmd": "x"}]},
             _sleep=lambda s: None, _connected=lambda: True)
    assert started == []


def test_arm_without_apps_starts_nothing(tmp_path, monkeypatch):
    ar = _runner(tmp_path, monkeypatch)
    assert ar.arm({}, ["false"]) == "no_apps"
    assert ar.watcher_running() is False
