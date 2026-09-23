#!/usr/bin/env python3
"""
tests/test_steamos_flatpak.py — WiVRn als Flatpak / SteamOS
==========================================================
  * Nur-Flatpak erkannt -> Server-Start per ``flatpak run --command=wivrn-server``
    (GPU-Wahl per ``--env``), Config in der Sandbox (~/.var/app/...)
  * native Installation hat immer Vorrang
  * SteamOS -> Installations-Methode „flatpak“ (kein AUR/pacman),
    Flatpak-Installation mit ``--user``, Update per ``flatpak update``
  * Cargo-Build bricht auf SteamOS mit klarer Meldung ab statt pacman zu rufen
"""
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import vr_environment as venv  # noqa: E402
import appimage_installer as appimg  # noqa: E402


@pytest.fixture
def flatpak_only(tmp_path, monkeypatch):
    app_dir = tmp_path / "flatpak" / "app" / venv.WIVRN_FLATPAK_ID
    app_dir.mkdir(parents=True)
    monkeypatch.setattr(venv, "_FLATPAK_APP_DIRS", (str(app_dir),))
    monkeypatch.setattr(venv, "wivrn_server_binary", lambda: None)
    return app_dir


def test_flatpak_only_detected(flatpak_only):
    assert venv.wivrn_flatpak_installed()
    assert venv.wivrn_uses_flatpak()
    assert venv.wivrn_available()


def test_flatpak_server_argv_with_gpu(flatpak_only):
    argv = venv.wivrn_server_argv({"MESA_VK_DEVICE_SELECT": "1002:73df"})
    assert argv == ["flatpak", "run", "--env=MESA_VK_DEVICE_SELECT=1002:73df",
                    "--command=wivrn-server", "io.github.wivrn.wivrn"]
    assert venv.wivrn_server_argv() == ["flatpak", "run", "--command=wivrn-server",
                                        "io.github.wivrn.wivrn"]


def test_flatpak_config_dir(flatpak_only):
    assert venv.wivrn_config_dir().endswith(".var/app/io.github.wivrn.wivrn/config/wivrn")
    assert venv.wivrn_config_file().endswith("config/wivrn/config.json")


def test_native_wins(flatpak_only, monkeypatch):
    monkeypatch.setattr(venv, "wivrn_server_binary", lambda: "/usr/bin/wivrn-server")
    assert not venv.wivrn_uses_flatpak()
    assert venv.wivrn_server_argv({"X": "1"}) == ["wivrn-server"]
    assert venv.wivrn_config_dir().endswith(".config/wivrn")


def test_nothing_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(venv, "_FLATPAK_APP_DIRS", (str(tmp_path / "nope"),))
    monkeypatch.setattr(venv, "wivrn_server_binary", lambda: None)
    assert not venv.wivrn_available() and not venv.wivrn_uses_flatpak()


# --------------------------------------------------------------------------- #
#  SteamOS
# --------------------------------------------------------------------------- #
@pytest.fixture
def steamos(monkeypatch):
    monkeypatch.setattr(appimg, "_os_release_ids", lambda: ("steamos", "arch"))
    monkeypatch.setattr(appimg.shutil, "which",
                        lambda name: "/usr/bin/" + name if name in ("flatpak", "pacman") else None)


def test_steamos_detected(steamos):
    assert appimg.is_steamos()
    assert appimg.is_arch_based()             # bleibt Arch-Familie (Tools-Tab)


def test_steamos_install_method_is_flatpak(steamos):
    assert appimg.available_update_methods() == ["flatpak"]
    assert appimg.default_update_method(["flatpak"]) == "flatpak"


def test_plain_arch_unchanged(monkeypatch):
    monkeypatch.setattr(appimg, "_os_release_ids", lambda: ("arch", ""))
    monkeypatch.setattr(appimg.shutil, "which",
                        lambda name: "/usr/bin/" + name if name in ("yay", "pacman") else None)
    assert not appimg.is_steamos()
    assert appimg.available_update_methods() == ["yay"]


def test_component_sources_flatpak():
    from programs import component_sources, SOURCE_FLATPAK
    assert component_sources("flatpak", "WiVRn (Flatpak)") == [SOURCE_FLATPAK]


def test_flatpak_user_install_command():
    from install_worker import InstallWorker
    w = InstallWorker(["io.github.wivrn.wivrn"], helper="flatpak", flatpak_user=True)
    cmd = w.build_bash_command("io.github.wivrn.wivrn", 1, 1)
    assert "flatpak remote-add --user --if-not-exists flathub" in cmd
    assert "flatpak install --user -y flathub io.github.wivrn.wivrn" in cmd
    w = InstallWorker(["x"], helper="flatpak")
    assert "--user" not in w.build_bash_command("x", 1, 1)


def test_cargo_script_guards_steamos(tmp_path):
    import cargo_installer
    script = cargo_installer.build_script(
        {"key": "obah", "crate": "obah",
         "sys_deps": {"arch": ["openxr"], "fedora": ["openxr-devel"],
                      "debian": ["libopenxr-dev"], "suse": ["openxr-devel"]}}, "de")
    path = tmp_path / "install.sh"
    path.write_text(script)
    assert subprocess.run(["bash", "-n", str(path)]).returncode == 0
    assert "is_steamos()" in script
    assert "if   is_steamos; then fail" in script
    # Auf SteamOS kein 'pacman -S rust', sondern rustup im Home
    assert "elif ! is_steamos && { is_arch || is_fedora; }; then" in script


def test_cargo_script_steamos_really_stops(tmp_path):
    """Script mit gefaelschtem os-release und ohne cc: bricht VOR pacman ab."""
    import cargo_installer
    script = cargo_installer.build_script({"key": "obah", "crate": "obah"}, "en")
    # os-release umbiegen, cc/pacman/sudo verstecken, 'read' nicht blockieren lassen
    script = script.replace("/etc/os-release", str(tmp_path / "os-release"))
    (tmp_path / "os-release").write_text("ID=steamos\nID_LIKE=arch\n")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ("sudo", "pacman"):
        (bindir / tool).write_text(f"#!/bin/sh\necho CALLED-{tool} >> {tmp_path}/calls\n")
        (bindir / tool).chmod(0o755)
    env = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(tmp_path)}
    # 'command -v cc' soll scheitern: eigene Funktion vor dem Script
    script = script.replace("#!/usr/bin/env bash", "#!/usr/bin/env bash\ncommand() { [ \"$2\" = cc ] && return 1; builtin command \"$@\"; }", 1)
    (tmp_path / "install.sh").write_text(script)
    res = subprocess.run(["bash", str(tmp_path / "install.sh")], input="\n", text=True,
                         capture_output=True, env=env, timeout=30, cwd=tmp_path)
    assert res.returncode == 1
    assert "SteamOS" in res.stdout
    assert not (tmp_path / "calls").exists()          # weder sudo noch pacman
