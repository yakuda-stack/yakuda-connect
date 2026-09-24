#!/usr/bin/env python3
"""Tests fuer scripts/bump_version.py — Version setzen/pruefen inkl. .SRCINFO,
CHANGELOG.md und HIGHLIGHTS.md. Arbeitet auf einer Kopie im tmp-Ordner."""
import importlib.util
import os
import pathlib
import shutil

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def bv(tmp_path, monkeypatch):
    for rel in ("core/version.py", "core/main.py", "packaging/aur/PKGBUILD",
                "packaging/aur/.SRCINFO", "CHANGELOG.md", "HIGHLIGHTS.md", "README.md"):
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, dst)
    spec = importlib.util.spec_from_file_location("bump_version", ROOT / "scripts" / "bump_version.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name in ("VERSION_PY", "MAIN_PY", "PKGBUILD", "SRCINFO", "CHANGELOG", "HIGHLIGHTS", "README"):
        monkeypatch.setattr(mod, name, tmp_path / os.path.relpath(getattr(mod, name), mod.ROOT))
    monkeypatch.setattr(mod, "NOTES", (mod.CHANGELOG, mod.HIGHLIGHTS))
    return mod


def test_repo_is_consistent(bv):
    assert bv.check() == 0


def test_bump_adds_only_headings(bv):
    assert bv.bump("9.9.9", date="2030-01-02") == 0
    for path in (bv.CHANGELOG, bv.HIGHLIGHTS):
        ver, date, content = bv.read_top_block(path)
        assert (ver, date, content) == ("9.9.9", "2030-01-02", [])
    assert "### 🚀 v9.9.9 — 2030-01-02\n\n---\n\n### " in bv.HIGHLIGHTS.read_text(encoding="utf-8")
    assert bv.read_badge() == "9.9.9"
    s_ver, s_rel, sources = bv.read_srcinfo()
    assert (s_ver, s_rel) == ("9.9.9", "1")
    assert sources[0].startswith("yakuda-connect-9.9.9.tar.gz::") and sources[0].endswith("/v9.9.9.tar.gz")
    # leer: normaler Check nur Hinweis, Release-Check (--expect) Fehler
    assert bv.check() == 0
    assert bv.check(expect="9.9.9") == 1
    # zweites Mal: keine doppelte Ueberschrift
    bv.bump("9.9.9", date="2030-01-03")
    assert bv.CHANGELOG.read_text(encoding="utf-8").count("v9.9.9 —") == 1


def test_check_catches_srcinfo_and_notes(bv):
    text = bv.SRCINFO.read_text(encoding="utf-8")
    bv.SRCINFO.write_text(text.replace("pkgrel = 1", "pkgrel = 2"), encoding="utf-8")
    assert bv.check() == 1
    bv.SRCINFO.write_text(text, encoding="utf-8")
    bv.SRCINFO.unlink()
    assert bv.check() == 1
    bv.SRCINFO.write_text(text, encoding="utf-8")
    # Version im Code, aber kein Block im HIGHLIGHTS -> Fehler
    bv._sub_once(bv.VERSION_PY, r'^VERSION\s*=\s*"[^"]+"', 'VERSION = "8.8.8"', "t")
    assert bv.check() == 1
