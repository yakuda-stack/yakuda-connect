#!/usr/bin/env python3
"""
tests/test_language_setting.py — Sprachauswahl in Einstellungen → Allgemein
==========================================================================
  * sitzt in den Einstellungen, nicht mehr auf dem Dashboard
  * Liste kommt aus locales/*.json (Anzeigename "language_name"), Englisch zuerst
  * Umschalten setzt die Sprache und speichert sie
  * jede Sprachdatei hat einen eigenen language_name
"""
import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app(qapp, tmp_path_factory):
    os.environ["HOME"] = str(tmp_path_factory.mktemp("home"))
    from PySide6.QtWidgets import QMessageBox
    for m in ("warning", "information", "critical", "question"):
        setattr(QMessageBox, m, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from main import VRApp
    window = VRApp()
    yield window
    window.close()


def test_language_combo_in_settings(app):
    combo = app.ui.combo_language
    assert app.ui.tab_settings.isAncestorOf(combo)
    assert not app.ui.tab_dashboard.isAncestorOf(combo)
    codes = [combo.itemData(i) for i in range(combo.count())]
    assert codes[0] == "en" and "de" in codes
    assert combo.itemText(codes.index("de")) == "🇩🇪 Deutsch"


def test_switch_saves(app, tmp_path, monkeypatch):
    import paths
    from translations import get_language
    cfg = tmp_path / "config.json"
    cfg.write_text("{}")
    monkeypatch.setattr(paths, "config_file", lambda name: str(cfg))
    combo = app.ui.combo_language
    combo.setCurrentIndex(combo.findData("de"))
    assert get_language() == "de"
    assert json.loads(cfg.read_text())["language"] == "de"
    combo.setCurrentIndex(combo.findData("en"))
    assert get_language() == "en"


def test_every_locale_names_itself():
    names = {}
    for path in sorted((ROOT / "locales").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("language_name"), f"{path.name}: language_name fehlt"
        names[path.stem] = data["language_name"]
    assert len(set(names.values())) == len(names)       # keine zwei gleich
