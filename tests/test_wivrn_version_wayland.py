"""
Tests fuer die WiVRn-Versionswarnung (Brille <-> PC) und die
Wayland/X11-Abfrage im Spiele-Tab (VRChat).
"""
import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app(qapp, tmp_path_factory):
    home = tmp_path_factory.mktemp("home")
    os.environ["HOME"] = str(home)
    from PySide6.QtWidgets import QMessageBox, QDialog
    for m in ("warning", "information", "critical"):
        setattr(QMessageBox, m, staticmethod(lambda *a, **k: QMessageBox.Ok))
    QMessageBox.exec = lambda self, *a, **k: QMessageBox.Ok
    QDialog.exec = lambda self, *a, **k: 0
    from main import VRApp
    window = VRApp()
    yield window
    window.close()


@pytest.fixture
def clean_config(monkeypatch, tmp_path):
    import games as games_db
    monkeypatch.setattr(games_db, "APP_CONFIG", str(tmp_path / "config.json"))
    return games_db


# --------------------------------------------------------------------------- #
#  WiVRn-Version
# --------------------------------------------------------------------------- #
def _ready_info():
    return {"state": "ready", "headset": {"name": "Pico 4"}, "devices": []}


def test_warnung_bei_unterschiedlicher_version(app, monkeypatch):
    monkeypatch.setattr(app, "_start_wivrn_version_check", lambda: None)
    app._wivrn_ver_state = None
    app._usb_last_info = _ready_info()
    app._on_wivrn_version_done({"client": "25.11", "server": "26.1", "match": False})
    text = app.ui.lbl_usb_state.text()
    assert "25.11" in text and "26.1" in text
    assert not app.ui.usb_state_widget.isHidden()


def test_keine_warnung_wenn_gleich_oder_unbekannt(app, monkeypatch):
    monkeypatch.setattr(app, "_start_wivrn_version_check", lambda: None)
    for match in (True, None):
        app._usb_last_info = _ready_info()
        app._on_wivrn_version_done({"client": "26.1", "server": "26.1.2", "match": match})
        assert app.ui.lbl_usb_state.text() == ""


def test_abstecken_setzt_pruefung_zurueck(app, monkeypatch):
    monkeypatch.setattr(app, "_start_wivrn_version_check", lambda: None)
    app._wivrn_ver_state = ("25.11", "26.1")
    app._render_usb_state({"state": "none", "headset": None, "devices": []})
    assert app._wivrn_ver_state is None


# --------------------------------------------------------------------------- #
#  Wayland / X11 und Proton-Infolinks
# --------------------------------------------------------------------------- #
def _vrchat():
    import games as games_db
    root = os.path.join(os.path.dirname(__file__), "..", "config", "games.json")
    with open(root, encoding="utf-8") as f:
        return games_db.build_games_from_config(json.load(f))["438100"]


def test_vrchat_empfehlung_je_nach_sitzung(clean_config):
    g = clean_config
    game = _vrchat()
    assert g.get_uses_wayland() is None
    g.set_uses_wayland(True)
    assert "Wayland" in g.visible_protons(game)[0]["version"]
    g.set_uses_wayland(False)
    first = g.visible_protons(game)[0]["version"]
    assert first.startswith("proton-rtsp") and "Wayland" not in first


def test_proton_info_links(clean_config):
    g = clean_config
    for proton in _vrchat()["protons"]:
        assert g.proton_info_url(proton).startswith("https://github.com/")
    assert g.proton_info_url({"version": "irgendwas"}) == ""
