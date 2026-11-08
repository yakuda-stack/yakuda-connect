#!/usr/bin/env python3
"""Tests fuer „Proton erkennen“ und „Einreichen“ im Spiel-Popup."""
import os
import sys
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "core"))

import games as games_db  # noqa: E402
from test_exit_guard import window, _FakeProc, exit_guard, wivrn_server  # noqa: E402,F401


def _compat(tmp_path, monkeypatch, names):
    d = tmp_path / "compatibilitytools.d"
    d.mkdir()
    for n in names:
        (d / n).mkdir()
    (d / "not-a-dir-proton.txt").write_text("x")
    monkeypatch.setattr(games_db, "compat_tools_dirs", lambda: [str(d)])
    monkeypatch.setattr(games_db, "system_compat_tools_dirs", lambda: [])
    return d


def test_detected_tools_only_proton_dirs_sorted(tmp_path, monkeypatch):
    _compat(tmp_path, monkeypatch, ["GE-Proton9-10", "GE-Proton9-2", "luxtorpeda",
                                    "proton-cachyos-10.0"])
    assert games_db.detected_proton_tools() == ["GE-Proton9-2", "GE-Proton9-10",
                                                "proton-cachyos-10.0"]


def test_detected_entry_resolves_exact_folder(tmp_path, monkeypatch):
    _compat(tmp_path, monkeypatch, ["GE-Proton9-1", "GE-Proton9-10"])
    entry = games_db.detected_proton_entry("GE-Proton9-1")
    assert games_db.resolve_steam_tool(entry) == ("GE-Proton9-1", True, "exact")
    gone = games_db.detected_proton_entry("GE-Proton8-1")
    assert games_db.resolve_steam_tool(gone)[1] is False


def test_detected_protons_skip_known(tmp_path, monkeypatch, window):
    _compat(tmp_path, monkeypatch, ["GE-Proton9-1", "Proton-Extra"])
    known = [games_db.detected_proton_entry("GE-Proton9-1")]
    extra = window._detected_protons_for(known)
    assert [p["version"] for p in extra] == ["Proton-Extra"]


def test_game_report_has_settings_and_hides_home(monkeypatch, window):
    home = os.path.expanduser("~")
    window._selected_proton["123456"] = "GE-Proton9-1"
    monkeypatch.setattr(window, "_saved_launch_options",
                        lambda a, g: f"{home}/tools/wrap -- %command% --vr")
    title, body = window._game_report("123456", {"name": "Test Game", "untested": True})
    assert title == "[Game report] Test Game (123456)"
    assert "GE-Proton9-1" in body
    assert "`~/tools/wrap -- %command% --vr`" in body
    assert home + "/" not in body


def test_submit_opens_prefilled_issue(monkeypatch, window):
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QMessageBox
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url) or True)
    monkeypatch.setattr(window, "_game_report", lambda a, g: ("T & 1", "line1\nline2"))

    def fake_exec(box):
        box._clicked = box.buttons()[0]
        return 0
    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box._clicked)
    window._submit_game_report("1", {"name": "x"})
    assert len(opened) == 1
    url = opened[0].toString(opened[0].ComponentFormattingOption.FullyEncoded)
    parts = urlparse(url)
    assert parts.netloc == "github.com"
    assert parts.path == "/yakuda-stack/yakuda-connect/issues/new"
    q = parse_qs(parts.query)
    assert q["title"] == ["T & 1"]
    assert q["body"] == ["line1\nline2"]


def test_tested_game_report_is_suggestion(monkeypatch, window):
    monkeypatch.setattr(window, "_saved_launch_options", lambda a, g: "%command%")
    title, body = window._game_report("438100", {"name": "VRChat"})
    assert title.startswith("[Game suggestion]")
    assert body.startswith("Suggestion")


def test_ge_minimum_version(tmp_path, monkeypatch):
    _compat(tmp_path, monkeypatch, ["GE-Proton8-32", "GE-Proton-RTSP-9", "proton-ge-custom"])
    ge = {"version": "GE-Proton11-12", "protonplus_runner": "proton-ge",
          "tool_prefix": ["GE-Proton", "Proton-GE"], "min_version": True}
    assert games_db.installed_builds(ge) == ["proton-ge-custom"]


def test_ge_new_build_wins(tmp_path, monkeypatch):
    _compat(tmp_path, monkeypatch, ["GE-Proton8-32", "GE-Proton11-12"])
    ge = {"version": "GE-Proton11-12", "protonplus_runner": "proton-ge",
          "tool_prefix": ["GE-Proton", "Proton-GE"], "min_version": True}
    assert games_db.resolve_steam_tool(ge) == ("GE-Proton11-12", True, "exact")


def test_games_json_pins_ge():
    meta = games_db.GAMES_CONFIG["proton_versions"]["Pro11GE"]
    assert meta["version"] == "GE-Proton11-12"
    assert meta["download_url"].endswith("GE-Proton11-12-x86_64.tar.gz")
    ge = [p for p in games_db.dynamic_protons() if p["role"] == "alternative_ge"][0]
    assert ge["version"] == "GE-Proton11-12" and ge["min_version"]


def test_report_contains_games_json_entry(monkeypatch, window):
    import json
    window._selected_proton["555"] = "GE-Proton11-12"
    monkeypatch.setattr(window, "_saved_launch_options", lambda a, g: "PROTON_LOG=1 %command%")
    _title, body = window._game_report("555", {"name": "Neu", "untested": True})
    snippet = body.split("```json\n", 1)[1].split("\n```", 1)[0]
    data = json.loads("{" + snippet.rstrip(",") + "}")
    assert data == {"555": {"name": "Neu", "proton": {"default": "Pro11GE"},
                            "base_start": "PROTON_LOG=1 %command%"}}


def test_proton_key_mapping(window):
    assert window._proton_key_for("GE-Proton11-12") == "Pro11GE"
    assert window._proton_key_for("proton-cachyos-11.0-20260703") == "CachyOSPro11"
    assert window._proton_key_for("Proton-RTSP-Wayland-GE-Beta4") == "Pro11WaylandGE"
    assert window._proton_key_for("proton_11") == "Pro11"
    assert window._proton_key_for("Luxtorpeda") == "Luxtorpeda"
