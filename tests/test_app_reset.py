#!/usr/bin/env python3
"""Reset der App (core/app_reset.py): nur Einstellungen und Icons verschwinden."""
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import app_reset
import paths


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "config_root", lambda: str(tmp_path))
    monkeypatch.setattr(paths, "config_dir", lambda: str(tmp_path / "config"))
    for name in ("config", "icons", "backup", "tools/wayvr", "xrbinder"):
        (tmp_path / name).mkdir(parents=True)
        (tmp_path / name / "datei").write_text("x")
    return tmp_path


def test_reset_loescht_einstellungen_und_icons(root):
    assert app_reset.reset_app() is True
    assert not (root / "config").exists()
    assert not (root / "icons").exists()


def test_reset_behaelt_backup_tools_und_xrbinder(root):
    app_reset.reset_app()
    assert (root / "backup" / "datei").exists()
    assert (root / "tools" / "wayvr" / "datei").exists()
    assert (root / "xrbinder" / "datei").exists()


def test_reset_ohne_ordner_ist_ok(root):
    shutil.rmtree(root / "config")
    shutil.rmtree(root / "icons")
    assert app_reset.reset_app() is True


def test_fehler_wird_gemeldet(root, monkeypatch):
    def fail(_path):
        raise PermissionError("nein")
    monkeypatch.setattr(shutil, "rmtree", fail)
    assert app_reset.reset_app() is False
