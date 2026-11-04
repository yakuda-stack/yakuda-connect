#!/usr/bin/env python3
"""Tests fuer „Verbindung & Bildqualitaet“ (core/wivrn_net.py, Streaming-Tab)
und die einklappbaren Bereiche (ui/collapsible.py)."""
import json
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "core"))

import wivrn_net  # noqa: E402
from test_exit_guard import window, _FakeProc, exit_guard, wivrn_server  # noqa: E402,F401


def test_read_defaults_and_values():
    assert wivrn_net.read_current({}) == {"bit10": False, "tcp_only": False, "hostname": "",
                                          "manual": False, "port": 9757}
    cur = wivrn_net.read_current({"bit-depth": 10, "tcp-only": True, "hostname": "PC",
                                  "publish-service": None, "port": 9800})
    assert cur == {"bit10": True, "tcp_only": True, "hostname": "PC", "manual": True,
                   "port": 9800}
    assert not wivrn_net.read_current({"publish-service": "avahi"})["manual"]


def test_apply_sets_and_removes_keys():
    d = {"encoder": {"encoder": "vaapi"}, "other": 1}
    wivrn_net.apply(d, {"bit10": True, "tcp_only": True, "hostname": " PC ",
                        "manual": True, "port": 9800}, "vaapi")
    assert d == {"encoder": {"encoder": "vaapi"}, "other": 1, "bit-depth": 10,
                 "tcp-only": True, "hostname": "PC", "publish-service": None, "port": 9800}
    wivrn_net.apply(d, {"port": 9757}, "vaapi")
    assert d == {"encoder": {"encoder": "vaapi"}, "other": 1}


def test_ten_bit_only_with_vaapi_nvenc():
    assert wivrn_net.ten_bit_possible("nvenc") and wivrn_net.ten_bit_possible("Auto")
    assert not wivrn_net.ten_bit_possible("Vulkan") and not wivrn_net.ten_bit_possible("x264")
    d = {}
    wivrn_net.apply(d, {"bit10": True}, "x264")
    assert "bit-depth" not in d


def test_sync_with_wivrn_only_when_card_saved(tmp_path, monkeypatch):
    import config_manager as cm
    import vr_environment as venv
    path = tmp_path / "wivrn.json"
    path.write_text(json.dumps({"tcp-only": True, "hostname": "handmade"}))
    monkeypatch.setattr(venv, "wivrn_config_file", lambda: str(path))
    cm.sync_with_wivrn({"encoder": "Auto"})                 # Karte nie gespeichert
    assert json.loads(path.read_text())["hostname"] == "handmade"
    cm.sync_with_wivrn({"encoder": "Auto", "wivrn_net": {"hostname": "Yakuda"}})
    data = json.loads(path.read_text())
    assert data["hostname"] == "Yakuda" and "tcp-only" not in data


def test_streaming_card_writes_wivrn_config(window, tmp_path, monkeypatch):
    import vr_environment as venv
    path = tmp_path / "wivrn.json"
    path.write_text("{}")
    monkeypatch.setattr(venv, "wivrn_config_file", lambda: str(path))
    st = window.streaming_settings
    st.load_connection_settings()
    st.combo_transport.setCurrentIndex(1)
    st._on_connection_changed()
    st.edit_hostname.setText("Yakudas PC")
    st.edit_hostname.editingFinished.emit()
    st.combo_discovery.setCurrentIndex(1)
    st._on_connection_changed()
    data = json.loads(path.read_text())
    assert data["tcp-only"] is True and data["hostname"] == "Yakudas PC"
    assert "publish-service" in data and data["publish-service"] is None
    form = st.conn_group.layout()
    assert form.isRowVisible(st.port_row)
    st.combo_discovery.setCurrentIndex(0)
    st._on_connection_changed()
    assert "publish-service" not in json.loads(path.read_text())
    assert not form.isRowVisible(st.port_row)


def test_ten_bit_disabled_for_vulkan(window):
    st = window.streaming_settings
    st.combo_encoder.setCurrentText("Vulkan")
    st._sync_ten_bit()
    assert not st.combo_bit_depth.isEnabled()
    st.combo_encoder.setCurrentText("nvenc")
    st._sync_ten_bit()
    assert st.combo_bit_depth.isEnabled()


def test_sections_collapse_and_remember(window):
    import paths
    header = window.ui.autostart_profiles_header
    assert not header.body.isHidden()
    header.click()
    assert header.body.isHidden()
    with open(paths.config_file("config.json")) as fh:
        sec = json.load(fh)["collapsed_sections"]
    assert sec == {"autostart_profiles": True}
    from ui.collapsible import CollapsibleHeader
    from PySide6.QtWidgets import QWidget
    again = CollapsibleHeader("autostart_profiles", QWidget())   # wie nach Neustart
    assert again.body.isHidden()
    header.click()
    assert not header.body.isHidden()


def test_header_shows_ampersand(qapp):
    from PySide6.QtWidgets import QWidget
    from ui.collapsible import CollapsibleHeader
    h = CollapsibleHeader("x_test", QWidget())
    h.setText("Verbindung & Bildqualität")
    assert h.text() == "Verbindung && Bildqualität"


def test_dashboard_autostart_collapsible_with_count(window):
    from translations import tr
    ui = window.ui
    while window.autostart_rows:
        window._vr_remove_row(window.autostart_rows[0])
    assert ui.autostart_header.text() == tr("dashboard_autostart").replace("&", "&&")
    window._vr_add_row_clicked()
    window._vr_add_row_clicked()
    assert ui.autostart_header.text().endswith("(2)")
    assert not ui.autostart_header.body.isHidden()          # Standard: offen
    ui.autostart_header.click()
    assert ui.autostart_header.body.isHidden()
    ui.autostart_header.click()
    assert not ui.autostart_header.body.isHidden()
    row = window.autostart_rows[0]
    assert row["widget"].objectName() == "autostartRowCard"
    row["chk_kill"].setChecked(True)
    assert not row["kill_row"].isHidden()
