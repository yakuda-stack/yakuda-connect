#!/usr/bin/env python3
"""
tests/test_fedora_paths.py — Fedora legt die OpenVR-Runtime tiefer ab
====================================================================
Der Fehler, um den es hier geht: auf Fedora meldete die OpenVR-Auswahl fuer
eine voellig intakte Installation "no vrclient.so".

Grund ist das Paketlayout. Arch (AUR) legt ab:

    /opt/opencomposite/bin/linux64/vrclient.so

Fedora dagegen (Dateiliste des offiziellen RPMs opencomposite):

    /usr/lib64/opencomposite/runtime/bin/linux64/vrclient.so

Die App kannte nur den Basisordner. Der existiert auf Fedora, enthaelt aber
kein bin/linux64 — also "unvollstaendig". Schlimmer noch: bei Auswahl waere
genau dieser tote Pfad in WiVRns config.json gelandet.

Die Tests laufen ohne Fedora; die Ordner werden in tmp_path nachgebaut.
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))


@pytest.fixture(autouse=True)
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))


def _arch_layout(base, name):
    """/opt/<name>/bin/linux64/vrclient.so"""
    d = base / name / "bin" / "linux64"
    d.mkdir(parents=True)
    (d / "vrclient.so").write_bytes(b"\x7fELF")
    return str(base / name)


def _fedora_layout(base, name):
    """/usr/lib64/<name>/runtime/bin/linux64/vrclient.so"""
    d = base / name / "runtime" / "bin" / "linux64"
    d.mkdir(parents=True)
    (d / "vrclient.so").write_bytes(b"\x7fELF")
    return str(base / name)


# --------------------------------------------------------------------------- #
#  resolve_compat_root
# --------------------------------------------------------------------------- #
def test_arch_layout_bleibt_unveraendert(tmp_path):
    import vr_environment as venv
    base = _arch_layout(tmp_path, "opencomposite")
    assert venv.resolve_compat_root(base) == base


def test_fedora_runtime_unterordner_wird_gefunden(tmp_path):
    import vr_environment as venv
    base = _fedora_layout(tmp_path, "opencomposite")
    assert venv.resolve_compat_root(base) == str(tmp_path / "opencomposite" / "runtime")


def test_unbekanntes_layout_eine_ebene_tiefer(tmp_path):
    """Auch ohne den Namen 'runtime' wird eine Ebene tiefer geschaut."""
    import vr_environment as venv
    d = tmp_path / "xrizer" / "lib64" / "bin" / "linux64"
    d.mkdir(parents=True)
    (d / "vrclient.so").write_bytes(b"\x7fELF")
    assert venv.resolve_compat_root(str(tmp_path / "xrizer")) == \
        str(tmp_path / "xrizer" / "lib64")


def test_leerer_ordner_bleibt_leer(tmp_path):
    """Ein Restordner nach der Deinstallation darf nicht plötzlich gelten."""
    import vr_environment as venv
    leer = tmp_path / "opencomposite"
    (leer / "runtime").mkdir(parents=True)
    assert venv.resolve_compat_root(str(leer)) == str(leer)
    assert venv.looks_like_openvr_compat(str(leer)) is False


def test_nicht_existierender_pfad_kommt_zurueck(tmp_path):
    import vr_environment as venv
    p = str(tmp_path / "gibtsnicht")
    assert venv.resolve_compat_root(p) == p


def test_zweite_ebene_wird_nicht_durchsucht(tmp_path):
    """
    Begrenzte Tiefe mit Absicht: ein Scan ueber /usr/lib64 in voller Tiefe
    waere bei jedem Oeffnen des Tabs spuerbar langsam.
    """
    import vr_environment as venv
    d = tmp_path / "oc" / "a" / "b" / "bin" / "linux64"
    d.mkdir(parents=True)
    (d / "vrclient.so").write_bytes(b"\x7fELF")
    assert venv.resolve_compat_root(str(tmp_path / "oc")) == str(tmp_path / "oc")


# --------------------------------------------------------------------------- #
#  Auswirkung auf die Auswahlliste
# --------------------------------------------------------------------------- #
def test_kandidat_zeigt_auf_den_echten_ordner(tmp_path, monkeypatch):
    """
    Der Eintrag muss auf .../runtime zeigen — genau dieser Pfad landet bei
    Auswahl in WiVRns config.json.
    """
    import vr_environment as venv
    base = _fedora_layout(tmp_path, "opencomposite")
    monkeypatch.setattr(venv, "WIVRN_OVR_SEARCH_PATH", ())
    monkeypatch.setattr(venv, "EXTRA_OVR_PATHS", (base,))

    eintrag = venv.openvr_compat_candidates()[0]
    assert eintrag["path"] == str(tmp_path / "opencomposite" / "runtime")
    assert eintrag["complete"] is True
    # Der Klarname kommt weiter vom Basisordner — sonst hiesse der Eintrag
    # in der Auswahl "runtime".
    assert eintrag["label"] == "OpenComposite"


def test_verschachtelt_ist_nicht_autodetect(tmp_path, monkeypatch):
    """
    Steht der Basisordner in WiVRns Suchliste, die Bibliothek aber eine Ebene
    tiefer, findet WiVRn sie NICHT von allein. Das muss die Oberflaeche sagen,
    sonst ist unklar, warum "Standard" nicht funktioniert.
    """
    import vr_environment as venv
    base = _fedora_layout(tmp_path, "opencomposite")
    monkeypatch.setattr(venv, "WIVRN_OVR_SEARCH_PATH", (base,))
    monkeypatch.setattr(venv, "EXTRA_OVR_PATHS", ())

    eintrag = venv.openvr_compat_candidates()[0]
    assert eintrag["autodetect"] is False


def test_find_openvr_compat_liefert_runtime(tmp_path, monkeypatch):
    """
    Wichtig fuer die xrizer-Automatik und die COPR-Rueckfrage: beide fragen
    ueber find_openvr_compat(), ob xrizer schon da ist.
    """
    import vr_environment as venv
    base = _fedora_layout(tmp_path, "xrizer")
    monkeypatch.setattr(venv, "WIVRN_OVR_SEARCH_PATH", ())
    monkeypatch.setattr(venv, "EXTRA_OVR_PATHS", (base,))

    assert venv.find_openvr_compat("xrizer") == str(tmp_path / "xrizer" / "runtime")


def test_dateidialog_biegt_auf_runtime_um(tmp_path):
    """Wer im Dialog /usr/lib64/opencomposite waehlt, meint den Ordner darunter."""
    import vr_environment as venv
    base = _fedora_layout(tmp_path, "opencomposite")
    assert venv.normalize_compat_path(base) == \
        str(tmp_path / "opencomposite" / "runtime")
    # Und der Klassiker bleibt: zu tief geklickt wird weiterhin gekuerzt.
    arch = _arch_layout(tmp_path, "xrizer")
    assert venv.normalize_compat_path(arch + "/bin/linux64") == arch


# --------------------------------------------------------------------------- #
#  Fedora: 'wivrn' bringt das Dashboard nicht mit
# --------------------------------------------------------------------------- #
def test_dashboard_ist_eigene_zeile():
    """
    Das Fedora-RPM 'wivrn' hat 'wivrn-dashboard' NICHT in seinen Requires.
    Wer nur wivrn installiert, hat einen Server ohne Oberflaeche — deshalb
    muss das Dashboard ausdruecklich in der Installationsliste stehen.
    """
    import programs
    assert programs.INSTALL_DNF["WiVRn Dashboard"] == ["wivrn-dashboard"]
    assert "wivrn-dashboard" not in programs.INSTALL_DNF["WiVRn / Monado"]


def test_binary_rueckfall_fuer_selbstbau():
    import programs
    assert programs.DNF_BINARY_FALLBACK["WiVRn Dashboard"] == "wivrn-dashboard"
    assert programs.DNF_BINARY_FALLBACK["WiVRn / Monado"] == "wivrn-server"


def test_hinweistext_existiert():
    import json
    for lang in ("en", "de"):
        data = json.loads((ROOT / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        assert "{pkgs}" in data["install_dnf_missing"]
