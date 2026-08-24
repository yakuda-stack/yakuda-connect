#!/usr/bin/env python3
"""
tests/test_xrizer_github.py — xrizer als Rueckfall von GitHub
=============================================================
Anlass: copr.fedorainfracloud.org antwortet zeitweise mit weniger als 1000
Bytes/Sekunde, dnf bricht dann mit ``Curl error (28): Timeout was reached`` ab.
xrizer laesst sich stattdessen direkt aus dem GitHub-Release holen.

Geprueft wird das, was dabei schiefgehen kann — ohne echten Netzzugriff:
  1. Das RICHTIGE Asset wird gewaehlt (nicht dependencies.zip).
  2. Der Zwischenordner aus dem Archiv (xrizer-v0.5/) faellt beim Entpacken weg.
  3. Ein Archiv mit '../'-Pfaden wird abgelehnt.
  4. Eine bestehende Installation ueberlebt einen fehlgeschlagenen Versuch.
"""
import io
import json
import pathlib
import sys
import zipfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))


@pytest.fixture
def xg(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    import xrizer_github
    monkeypatch.setattr(xrizer_github, "INSTALL_DIR",
                        str(tmp_path / "data" / "xrizer"))
    return xrizer_github


def _release_zip(path, top="xrizer-v0.5", body=b"\x7fELF-fake"):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{top}/bin/linux64/vrclient.so", body)
        zf.writestr(f"{top}/bin/version.txt", "v0.5")


# --------------------------------------------------------------------------- #
#  1. Asset-Auswahl
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name, erwartet", [
    ("xrizer-v0.5.zip", True),
    ("xrizer-release.zip", True),
    ("dependencies.zip", False),      # liegt im selben Release, ist NICHT xrizer
    ("Source code (zip)", False),
    ("xrizer-v0.5.tar.gz", False),
])
def test_nur_das_programm_asset(xg, name, erwartet):
    assert xg._is_program_asset(name) is erwartet


def test_latest_release_liest_die_api(xg, monkeypatch):
    antwort = {
        "tag_name": "v0.5",
        "assets": [
            {"name": "dependencies.zip",
             "browser_download_url": "https://example.invalid/dependencies.zip"},
            {"name": "xrizer-v0.5.zip",
             "browser_download_url": "https://example.invalid/xrizer-v0.5.zip"},
        ],
    }
    monkeypatch.setattr(xg.urllib.request, "urlopen",
                        lambda *a, **k: io.BytesIO(json.dumps(antwort).encode()))

    tag, url = xg.latest_release()
    assert tag == "v0.5"
    assert url.endswith("xrizer-v0.5.zip")


def test_release_ohne_passendes_asset_meldet_sich(xg, monkeypatch):
    antwort = {"tag_name": "v9", "assets": [
        {"name": "dependencies.zip", "browser_download_url": "https://x.invalid/d.zip"}]}
    monkeypatch.setattr(xg.urllib.request, "urlopen",
                        lambda *a, **k: io.BytesIO(json.dumps(antwort).encode()))
    with pytest.raises(xg.XrizerError):
        xg.latest_release()


# --------------------------------------------------------------------------- #
#  2. Entpacken
# --------------------------------------------------------------------------- #
def test_zwischenordner_faellt_weg(xg, tmp_path, monkeypatch):
    """
    Im Archiv liegt alles unter 'xrizer-v0.5/'. Bliebe der Ordner stehen,
    zeigte der Eintrag in WiVRns config.json eine Ebene zu hoch.
    """
    quelle = tmp_path / "release.zip"
    _release_zip(quelle)

    monkeypatch.setattr(xg, "latest_release", lambda **k: ("v0.5", "https://x.invalid/a.zip"))
    monkeypatch.setattr(xg, "supported_platform", lambda: True)
    monkeypatch.setattr(xg, "_download",
                        lambda url, dest, **k: pathlib.Path(dest).write_bytes(quelle.read_bytes()))

    pfad, tag = xg.install()
    assert tag == "v0.5"
    assert (pathlib.Path(pfad) / "bin" / "linux64" / "vrclient.so").exists()
    assert not (pathlib.Path(pfad) / "xrizer-v0.5").exists()


def test_herkunft_wird_vermerkt(xg, tmp_path, monkeypatch):
    """Ohne Markierung wuesste die App spaeter nicht, dass der Ordner von ihr stammt."""
    quelle = tmp_path / "release.zip"
    _release_zip(quelle)
    monkeypatch.setattr(xg, "latest_release", lambda **k: ("v0.5", "https://x.invalid/a.zip"))
    monkeypatch.setattr(xg, "supported_platform", lambda: True)
    monkeypatch.setattr(xg, "_download",
                        lambda url, dest, **k: pathlib.Path(dest).write_bytes(quelle.read_bytes()))
    xg.install()
    assert xg.installed_info()["tag"] == "v0.5"


def test_fremder_ordner_wird_nicht_entfernt(xg, tmp_path):
    """
    uninstall() fasst nur an, was von hier stammt — ein selbst gebautes
    xrizer im selben Pfad darf nicht geloescht werden.
    """
    ziel = pathlib.Path(xg.INSTALL_DIR)
    (ziel / "bin" / "linux64").mkdir(parents=True)
    (ziel / "bin" / "linux64" / "vrclient.so").write_bytes(b"selbst gebaut")
    assert xg.uninstall() is False
    assert (ziel / "bin" / "linux64" / "vrclient.so").exists()


# --------------------------------------------------------------------------- #
#  3. Boesartige Archive
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("member", ["../../.bashrc", "/etc/passwd"])
def test_pfadausbruch_wird_abgelehnt(xg, tmp_path, member):
    boese = tmp_path / "boese.zip"
    with zipfile.ZipFile(boese, "w") as zf:
        zf.writestr(member, "harmlos aussehend")
    with pytest.raises(xg.XrizerError):
        xg._safe_extract(str(boese), str(tmp_path / "ziel"))


def test_archiv_ohne_vrclient_wird_abgelehnt(xg, tmp_path, monkeypatch):
    leer = tmp_path / "leer.zip"
    with zipfile.ZipFile(leer, "w") as zf:
        zf.writestr("xrizer-v0.5/README.md", "nichts drin")
    monkeypatch.setattr(xg, "latest_release", lambda **k: ("v0.5", "https://x.invalid/a.zip"))
    monkeypatch.setattr(xg, "supported_platform", lambda: True)
    monkeypatch.setattr(xg, "_download",
                        lambda url, dest, **k: pathlib.Path(dest).write_bytes(leer.read_bytes()))
    with pytest.raises(xg.XrizerError):
        xg.install()


# --------------------------------------------------------------------------- #
#  4. Bestehende Installation
# --------------------------------------------------------------------------- #
def test_alte_installation_ueberlebt_fehlschlag(xg, tmp_path, monkeypatch):
    """
    Ein halb entpacktes xrizer waere schlimmer als gar keines: WiVRn zeigte
    dann auf eine kaputte Bibliothek. Also erst tauschen, wenn alles steht.
    """
    ziel = pathlib.Path(xg.INSTALL_DIR)
    (ziel / "bin" / "linux64").mkdir(parents=True)
    (ziel / "bin" / "linux64" / "vrclient.so").write_bytes(b"alte version")

    monkeypatch.setattr(xg, "latest_release", lambda **k: ("v0.6", "https://x.invalid/a.zip"))
    monkeypatch.setattr(xg, "supported_platform", lambda: True)

    def kaputt(url, dest, **k):
        raise xg.XrizerError("Verbindung abgebrochen")
    monkeypatch.setattr(xg, "_download", kaputt)

    with pytest.raises(xg.XrizerError):
        xg.install()
    assert (ziel / "bin" / "linux64" / "vrclient.so").read_bytes() == b"alte version"
    assert not pathlib.Path(str(ziel) + ".new").exists()


def test_fremde_architektur_wird_abgelehnt(xg, monkeypatch):
    """Das Release enthaelt nur bin/linux64 — auf arm64 waere es nutzlos."""
    monkeypatch.setattr(xg.platform, "machine", lambda: "aarch64")
    assert xg.supported_platform() is False
    with pytest.raises(xg.XrizerError):
        xg.install()


# --------------------------------------------------------------------------- #
#  5. Oberflaeche
# --------------------------------------------------------------------------- #
def test_texte_vorhanden():
    for lang in ("en", "de"):
        data = json.loads((ROOT / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        for key in ("fedora_copr_github", "xrizer_github_ok", "xrizer_github_failed",
                    "xrizer_github_use_title", "xrizer_github_use_text",
                    "xrizer_copr_failed_title", "xrizer_copr_failed_text"):
            assert key in data, f"{key} fehlt in {lang}.json"
        assert "{tag}" in data["xrizer_github_ok"]
        assert "{path}" in data["xrizer_github_use_text"]


def test_zielordner_ist_bekannt(xg):
    """
    ~/.local/share/xrizer steht in EXTRA_OVR_PATHS — sonst taucht das
    heruntergeladene xrizer in der OpenVR-Auswahl gar nicht auf.
    """
    import os
    import vr_environment as venv
    assert any(os.path.basename(p) == "xrizer" and ".local/share" in p
               for p in venv.EXTRA_OVR_PATHS)
