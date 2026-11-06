#!/usr/bin/env python3
"""Icon-Ordner, Download und eigene Icons (core/tool_icons.py)."""
import io
import os
import sys
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import paths
import tool_icons as ti

PNG = b"\x89PNG\r\n\x1a\nDATEN"
TOOL = {"key": "wayvr", "icon_url": "https://raw.githubusercontent.com/a/b/main/i.png"}


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "config_root", lambda: str(tmp_path))
    return tmp_path


def _answer(monkeypatch, data):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Response(data))


def test_download_legt_icon_im_ordner_ab(monkeypatch):
    _answer(monkeypatch, PNG)
    assert ti.download(TOOL) is True
    assert ti.local_icon(TOOL) == ti.icon_path("wayvr")


def test_download_lehnt_html_ab(monkeypatch):
    _answer(monkeypatch, b"<html>404</html>")
    assert ti.download(TOOL) is False
    assert ti.local_icon(TOOL) == ""


def test_download_lehnt_zu_grosse_datei_ab(monkeypatch):
    _answer(monkeypatch, PNG + b"0" * ti.MAX_BYTES)
    assert ti.download(TOOL) is False


def test_download_ohne_netz(monkeypatch):
    def fail(*_a, **_k):
        raise urllib.error.URLError("kein Netz")
    monkeypatch.setattr(urllib.request, "urlopen", fail)
    assert ti.download(TOOL) is False


def test_ohne_https_adresse_kein_download():
    assert ti.download({"key": "x"}) is False
    assert ti.download({"key": "x", "icon_url": "http://example.org/i.png"}) is False


def test_blob_adresse_wird_umgeschrieben():
    url = ti._raw_url("https://github.com/a/b/blob/main/i.png")
    assert url == "https://raw.githubusercontent.com/a/b/main/i.png"


def test_appimage_icon_wird_uebernommen(root):
    folder = root / "tools" / "wayvr"
    folder.mkdir(parents=True)
    (folder / "icon.png").write_bytes(PNG)
    assert ti.local_icon(TOOL) == ti.icon_path("wayvr")
    assert os.path.isfile(ti.icon_path("wayvr"))


def test_eigenes_icon_landet_im_ordner(tmp_path):
    source = tmp_path / "bild.PNG"
    source.write_bytes(PNG)
    target = ti.import_file(str(source))
    assert target.startswith(ti.icon_dir()) and target.endswith(".png")
    assert ti.import_file(str(tmp_path / "fehlt.png")) == ""
