"""Tests fuer die Installationsmethode "script" (curl | bash) im Tools-Tab."""
import json
import os

import pytest


@pytest.fixture
def mods(monkeypatch, tmp_path):
    import script_installer as si
    monkeypatch.setattr(si, "SCRIPT_TOOLS_DIR", str(tmp_path / "script"))
    return si


def _viewshot():
    root = os.path.join(os.path.dirname(__file__), "..", "config", "tools.json")
    with open(root, encoding="utf-8") as f:
        apps = json.load(f)["apps"]
    keys = [a["key"] for a in apps]
    # steht direkt unter SlimeVR
    assert keys[keys.index("slimevr-bin") + 1] == "linuxvr-viewshot"
    return next(a for a in apps if a["key"] == "linuxvr-viewshot")


def test_viewshot_eintrag_hat_alle_methoden():
    tool = _viewshot()
    assert set(tool["install_methods"]) == {"aur", "appimage", "script"}
    assert tool["script_url"].endswith("/install.sh")


def test_script_wird_angeboten_wenn_curl_da(mods, monkeypatch):
    import appimage_installer as appimg
    monkeypatch.setattr(mods, "available", lambda tool: True)
    assert "script" in appimg.detect_install_methods(_viewshot())
    monkeypatch.setattr(mods, "available", lambda tool: False)
    assert "script" not in appimg.detect_install_methods(_viewshot())


def test_build_script_install_und_uninstall(mods):
    tool = _viewshot()
    inst = mods.build_script(tool)
    assert "curl -fsSL" in inst and "| bash;" in inst and "touch" in inst
    rem = mods.build_script(tool, uninstall=True)
    assert "| bash -s -- uninstall" in rem and "rm -f" in rem


def test_local_status_braucht_marker_und_befehl(mods, monkeypatch, tmp_path):
    tool = _viewshot()
    monkeypatch.setattr(mods.shutil, "which", lambda cmd: "/usr/bin/" + cmd)
    assert mods.local_status(tool)[0] is False
    os.makedirs(mods.tool_root(tool))
    open(mods._marker(tool), "w").close()
    assert mods.local_status(tool)[0] is True
