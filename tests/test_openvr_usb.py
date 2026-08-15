#!/usr/bin/env python3
"""
tests/test_openvr_usb.py — OpenVR-Auswahl, USB-Erkennung, Bildwiederholrate
===========================================================================
Laufen OHNE Qt, ohne Headset, ohne Netz:

    pytest tests/

Warum diese Tests? Alle drei Bausteine entscheiden anhand von Dateien, die
auf dem Testrechner nicht existieren (``/opt/xrizer``, ``/sys/bus/usb``,
WiVRns ``config.json``). Genau deshalb sind sie testbar: die Pfade lassen
sich umbiegen, und dann laesst sich pruefen, was die App wirklich in fremde
Konfigurationsdateien schreibt — der Teil, der beim Nutzer kaputtgeht, wenn
er falsch ist.
"""
import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))


@pytest.fixture(autouse=True)
def fake_home(tmp_path, monkeypatch):
    """Eigenes HOME pro Test — nie die echte Konfiguration anfassen."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    return tmp_path


def _make_compat_dir(base, name):
    """Legt einen Ordner an, der aussieht wie eine OpenVR-Ersatzbibliothek."""
    target = base / name / "bin" / "linux64"
    target.mkdir(parents=True)
    (target / "vrclient.so").write_bytes(b"\x7fELF fake")
    return str(base / name)


# --------------------------------------------------------------------------- #
#  OpenVR-Kompatibilitaet: erkennen
# --------------------------------------------------------------------------- #
def test_wivrn_suchpfad_unveraendert():
    """
    Diese Liste stammt 1:1 aus WiVRns CMakeLists.txt (OVR_COMPAT_SEARCH_PATH).
    Faellt sie auseinander, zeigt die Oberflaeche unter "Standard" etwas
    anderes an, als WiVRn tatsaechlich nimmt.
    """
    import vr_environment as venv

    assert venv.WIVRN_OVR_SEARCH_PATH == (
        "/opt/xrizer",
        "/usr/local/lib/OpenComposite",
        "/usr/lib/OpenComposite",
        "/opt/OpenComposite",
        "/opt/opencomposite",
        "/opt/VapoR",
        "/usr/local/lib/VapoR",
    )


def test_leerer_ordner_gilt_nicht_als_installiert(tmp_path):
    """
    Der haeufigste Fall nach einer Deinstallation: /opt/xrizer bleibt als
    leerer Ordner liegen. Frueher zaehlte das als "installiert" — WiVRn bekam
    einen Pfad, unter dem kein Spiel startet.
    """
    import vr_environment as venv

    leer = tmp_path / "leer"
    leer.mkdir()
    assert venv.looks_like_openvr_compat(str(leer)) is False


def test_ordner_mit_vrclient_wird_erkannt(tmp_path):
    import vr_environment as venv

    pfad = _make_compat_dir(tmp_path, "xrizer")
    assert venv.looks_like_openvr_compat(pfad) is True


def test_nur_existierende_ordner_werden_gelistet(tmp_path, monkeypatch):
    """Wie WiVRns Dashboard: was es nicht gibt, steht auch nicht zur Wahl."""
    import vr_environment as venv

    pfad = _make_compat_dir(tmp_path, "xrizer")
    monkeypatch.setattr(venv, "WIVRN_OVR_SEARCH_PATH",
                        (pfad, str(tmp_path / "gibtsnicht")))
    monkeypatch.setattr(venv, "EXTRA_OVR_PATHS", ())

    eintraege = venv.openvr_compat_candidates()
    assert [e["path"] for e in eintraege] == [pfad]
    assert eintraege[0]["label"] == "xrizer"
    assert eintraege[0]["autodetect"] is True
    assert eintraege[0]["complete"] is True


def test_extra_pfade_sind_als_ausserhalb_markiert(tmp_path, monkeypatch):
    """
    Fedora legt xrizer nach /usr/lib64 — WiVRn sucht dort NICHT. Der Ordner
    ist trotzdem waehlbar, muss aber als "nur mit explizitem Eintrag" kenntlich
    sein, sonst waere unklar, warum "Standard" ihn nicht findet.
    """
    import vr_environment as venv

    pfad = _make_compat_dir(tmp_path, "xrizer")
    monkeypatch.setattr(venv, "WIVRN_OVR_SEARCH_PATH", ())
    monkeypatch.setattr(venv, "EXTRA_OVR_PATHS", (pfad,))

    eintrag = venv.openvr_compat_candidates()[0]
    assert eintrag["autodetect"] is False
    assert venv.wivrn_autodetect_path() == ""


def test_autodetect_bildet_wivrn_nach(tmp_path, monkeypatch):
    """Erster EXISTIERENDER Eintrag der Suchliste gewinnt — wie active_runtime.cpp."""
    import vr_environment as venv

    zweiter = _make_compat_dir(tmp_path, "opencomposite")
    monkeypatch.setattr(venv, "WIVRN_OVR_SEARCH_PATH",
                        (str(tmp_path / "gibtsnicht"), zweiter))
    assert venv.wivrn_autodetect_path() == zweiter


@pytest.mark.parametrize("eingabe, erwartet", [
    ("/opt/xrizer/bin/linux64", "/opt/xrizer"),
    ("/opt/xrizer/bin", "/opt/xrizer"),
    ("/opt/xrizer/", "/opt/xrizer"),
    ("/opt/xrizer", "/opt/xrizer"),
])
def test_ordnerauswahl_wird_aufgeraeumt(eingabe, erwartet):
    """Im Dateidialog landet man fast zwangslaeufig in bin/linux64."""
    import vr_environment as venv

    assert venv.normalize_compat_path(eingabe) == erwartet


# --------------------------------------------------------------------------- #
#  OpenVR-Kompatibilitaet: in WiVRns config.json schreiben
# --------------------------------------------------------------------------- #
def test_standard_entfernt_den_schluessel(tmp_path):
    """
    "Standard" darf keinen Pfad erzwingen, sondern muss den Schluessel
    entfernen — nur dann sucht WiVRn selbst (monostate im configuration.h).
    """
    import vr_environment as venv

    cfg = pathlib.Path(venv.wivrn_config_file())
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({"port": 9757,
                               "openvr-compat-path": "/opt/xrizer"}))

    assert venv.set_openvr_compat(venv.OPENVR_DEFAULT) is True
    data = json.loads(cfg.read_text())
    assert "openvr-compat-path" not in data
    # Fremde Schluessel bleiben unangetastet.
    assert data["port"] == 9757
    assert venv.current_openvr_compat() == (venv.OPENVR_DEFAULT, "")


def test_aus_schreibt_echtes_json_null(tmp_path):
    """
    WiVRn unterscheidet null (= OpenVR nicht anfassen) von einem Textwert.
    Ein leerer String ist NICHT der dokumentierte Weg.
    """
    import vr_environment as venv

    assert venv.set_openvr_compat(venv.OPENVR_DISABLED) is True
    roh = pathlib.Path(venv.wivrn_config_file()).read_text()
    assert json.loads(roh)["openvr-compat-path"] is None
    assert venv.current_openvr_compat() == (venv.OPENVR_DISABLED, "")


def test_leerer_string_aus_alter_version_gilt_als_aus(tmp_path):
    import vr_environment as venv

    cfg = pathlib.Path(venv.wivrn_config_file())
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({"openvr-compat-path": ""}))
    assert venv.current_openvr_compat() == (venv.OPENVR_DISABLED, "")


def test_pfad_wird_gesetzt_und_aufgeraeumt(tmp_path):
    import vr_environment as venv

    pfad = _make_compat_dir(tmp_path, "opencomposite")
    assert venv.set_openvr_compat(venv.OPENVR_PATH, pfad + "/bin/linux64") is True
    assert venv.current_openvr_compat() == (venv.OPENVR_PATH, pfad)


# --------------------------------------------------------------------------- #
#  Bildwiederholrate
# --------------------------------------------------------------------------- #
def test_refresh_rate_wird_nicht_mehr_geschrieben(monkeypatch):
    """
    WiVRn kennt keinen refresh_rate-Schluessel (in keiner Version). Ein
    Altbestand aus frueheren Versionen dieser App wird aufgeraeumt.
    """
    import config_manager as cm
    import vr_environment as venv

    cfg = pathlib.Path(venv.wivrn_config_file())
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({"refresh_rate": 90, "port": 9757}))

    cm.sync_with_wivrn({"refresh_rate": "120"})
    data = json.loads(cfg.read_text())
    assert "refresh_rate" not in data
    assert data["port"] == 9757


def test_encoder_schluessel_neue_wivrn_version(monkeypatch):
    """Ab 25.12 heisst der Schluessel 'encoder' (Objekt)."""
    import config_manager as cm
    import vr_environment as venv

    monkeypatch.setattr(venv, "wivrn_version", lambda: (25, 12))
    cm.sync_with_wivrn({"encoder": "vaapi", "codec": "h265"})
    data = json.loads(pathlib.Path(venv.wivrn_config_file()).read_text())
    assert data["encoder"] == {"encoder": "vaapi", "codec": "h265"}
    assert "encoders" not in data
    assert "bitrate" not in data


def test_encoder_schluessel_alte_wivrn_version(monkeypatch):
    """Bis 25.11 hiess er 'encoders' (Liste), dazu scale und bitrate."""
    import config_manager as cm
    import vr_environment as venv

    monkeypatch.setattr(venv, "wivrn_version", lambda: (25, 11))
    cm.sync_with_wivrn({"encoder": "vaapi", "codec": "h265",
                        "render_resolution": 150, "bitrate": 80})
    data = json.loads(pathlib.Path(venv.wivrn_config_file()).read_text())
    assert data["encoders"] == [{"encoder": "vaapi", "codec": "h265"}]
    assert data["scale"] == 1.5
    assert data["bitrate"] == 80_000_000


def test_encoder_auto_setzt_keinen_schluessel(monkeypatch):
    import config_manager as cm
    import vr_environment as venv

    monkeypatch.setattr(venv, "wivrn_version", lambda: (26, 6))
    cm.sync_with_wivrn({"encoder": "Auto"})
    data = json.loads(pathlib.Path(venv.wivrn_config_file()).read_text())
    assert "encoder" not in data


def test_sync_laesst_openvr_pfad_in_ruhe(monkeypatch):
    """
    Das Speichern der Streaming-Werte darf die OpenVR-Auswahl nicht
    ueberschreiben — die wird nur beim Umschalten gesetzt.
    """
    import config_manager as cm
    import vr_environment as venv

    monkeypatch.setattr(venv, "wivrn_version", lambda: (26, 6))
    venv.set_openvr_compat(venv.OPENVR_PATH, "/opt/opencomposite")
    cm.sync_with_wivrn({"refresh_rate": "90"})
    assert venv.current_openvr_compat() == (venv.OPENVR_PATH, "/opt/opencomposite")


@pytest.mark.parametrize("ausgabe, erwartet", [
    ("WiVRn version 25.12\n", (25, 12)),
    ("WiVRn version 26.6\n", (26, 6)),
    ("WiVRn version 25.11.1\n", (25, 11, 1)),
    ("WiVRn version 0.22\n", (0, 22)),
    ("WiVRn version 25.12-30-gabc123\n", (25, 12)),
    ("", None),
])
def test_wivrn_version_wird_geparst(monkeypatch, ausgabe, erwartet):
    import proc
    import vr_environment as venv

    monkeypatch.setattr(proc, "output_of", lambda *a, **k: ausgabe)
    assert venv.wivrn_version() == erwartet


def test_unbekannte_version_gilt_als_aktuell(monkeypatch):
    """
    Laesst sich die Version nicht ermitteln, wird das NEUE Format
    geschrieben — ein alter Server ignoriert einen unbekannten Schluessel
    einfach, umgekehrt gilt dasselbe.
    """
    import vr_environment as venv

    monkeypatch.setattr(venv, "wivrn_version", lambda: None)
    assert venv.wivrn_at_least(25, 12) is True


# --------------------------------------------------------------------------- #
#  USB-Erkennung
# --------------------------------------------------------------------------- #
def _fake_usb(tmp_path, monkeypatch, vendor, product, manufacturer=""):
    """Baut ein Mini-sysfs mit genau einem Geraet."""
    import usb_headsets as usbhs

    bus = tmp_path / "usbbus"
    dev = bus / "1-2"
    dev.mkdir(parents=True)
    (dev / "idVendor").write_text(vendor)
    (dev / "idProduct").write_text("0186")
    (dev / "product").write_text(product)
    (dev / "manufacturer").write_text(manufacturer)
    (dev / "serial").write_text("TESTSERIAL")
    # Ein Interface-Ordner darf NICHT als eigenes Geraet gezaehlt werden.
    (bus / "1-2:1.0").mkdir()
    monkeypatch.setattr(usbhs, "SYSFS_USB", str(bus))
    return usbhs


def test_quest_wird_erkannt(tmp_path, monkeypatch):
    usbhs = _fake_usb(tmp_path, monkeypatch, "2833", "Quest 3", "Oculus")

    geraete = usbhs.list_usb_headsets()
    assert len(geraete) == 1
    assert geraete[0]["family"] == "quest"
    assert geraete[0]["name"] == "Quest 3"


def test_fremdes_usb_geraet_wird_ignoriert(tmp_path, monkeypatch):
    usbhs = _fake_usb(tmp_path, monkeypatch, "046d", "USB Keyboard")
    assert usbhs.list_usb_headsets() == []


def test_pico_profil_endet_bei_90(tmp_path, monkeypatch):
    usbhs = _fake_usb(tmp_path, monkeypatch, "2d40", "Pico 4 Ultra", "Pico")

    profil = usbhs.profile_for(usbhs.list_usb_headsets()[0])
    assert profil["max"] == 90
    assert 120 not in profil["rates"]


def test_quest2_kann_120(tmp_path, monkeypatch):
    usbhs = _fake_usb(tmp_path, monkeypatch, "2833", "Quest 2", "Oculus")

    profil = usbhs.profile_for(usbhs.list_usb_headsets()[0])
    assert 120 in profil["rates"]
    assert 60 in profil["rates"]


def test_ohne_headset_ist_nichts_gesperrt():
    import usb_headsets as usbhs

    profil = usbhs.profile_for(None)
    assert set(profil["rates"]) == set(usbhs.ALL_RATES)


def test_zustand_ohne_adb(tmp_path, monkeypatch):
    """Brille am Kabel, adb fehlt: gelb — nicht gruen und nicht grau."""
    usbhs = _fake_usb(tmp_path, monkeypatch, "2833", "Quest 3", "Oculus")
    monkeypatch.setattr(usbhs, "adb_available", lambda: False)

    assert usbhs.scan()["state"] == "no_adb"


def test_zustand_unauthorized(tmp_path, monkeypatch):
    usbhs = _fake_usb(tmp_path, monkeypatch, "2833", "Quest 3", "Oculus")
    monkeypatch.setattr(usbhs, "adb_available", lambda: True)
    monkeypatch.setattr(usbhs, "adb_devices", lambda: {"1WMHH": "unauthorized"})

    assert usbhs.scan()["state"] == "unauthorized"


def test_zustand_bereit(tmp_path, monkeypatch):
    usbhs = _fake_usb(tmp_path, monkeypatch, "2833", "Quest 3", "Oculus")
    monkeypatch.setattr(usbhs, "adb_available", lambda: True)
    monkeypatch.setattr(usbhs, "adb_devices", lambda: {"1WMHH": "device"})

    info = usbhs.scan()
    assert info["state"] == "ready"
    assert info["profile"]["model"] == "Meta Quest 3"


def test_ohne_sysfs_kein_absturz(monkeypatch):
    """Auf Systemen ohne /sys/bus/usb darf die Ampel nur grau bleiben."""
    import usb_headsets as usbhs

    monkeypatch.setattr(usbhs, "SYSFS_USB", "/gibt/es/nicht")
    assert usbhs.scan()["state"] == "none"


def test_adb_wird_ohne_headset_nicht_aufgerufen(monkeypatch):
    """
    Kein Geraet am Bus -> kein adb-Aufruf. Sonst startet die App im
    Sekundentakt einen adb-Daemon, den niemand bestellt hat.
    """
    import usb_headsets as usbhs

    monkeypatch.setattr(usbhs, "SYSFS_USB", "/gibt/es/nicht")

    def _boom():
        raise AssertionError("adb darf hier nicht aufgerufen werden")

    monkeypatch.setattr(usbhs, "adb_devices", _boom)
    monkeypatch.setattr(usbhs, "adb_available", _boom)
    assert usbhs.scan()["state"] == "none"


def test_adb_ausgabe_wird_geparst(monkeypatch):
    import subprocess

    import proc
    import usb_headsets as usbhs

    monkeypatch.setattr(usbhs.shutil, "which", lambda _n: "/usr/bin/adb")
    ausgabe = "List of devices attached\n1WMHH865AB\tdevice\n2ZZZZ\tunauthorized\n\n"
    monkeypatch.setattr(proc, "run", lambda *a, **k: subprocess.CompletedProcess(
        a[0] if a else [], 0, stdout=ausgabe, stderr=""))

    states = usbhs.adb_devices()
    assert states == {"1WMHH865AB": "device", "2ZZZZ": "unauthorized"}


def test_kaputte_adb_ausgabe_gibt_leeres_dict(monkeypatch):
    import subprocess

    import proc
    import usb_headsets as usbhs

    monkeypatch.setattr(usbhs.shutil, "which", lambda _n: "/usr/bin/adb")
    monkeypatch.setattr(proc, "run", lambda *a, **k: subprocess.CompletedProcess(
        [], 127, stdout="", stderr="not found"))

    assert usbhs.adb_devices() == {}


def test_meta_store_link_ist_im_ui_hinterlegt():
    """
    Der Link unter dem APK-Installer ist die kabellose Alternative — wenn er
    verschwindet oder ins Leere zeigt, merkt es sonst niemand.
    """
    sys.path.insert(0, str(ROOT / "ui"))
    quelle = (ROOT / "ui" / "ui_main.py").read_text(encoding="utf-8")
    assert "meta.com/experiences/wivrn" in quelle
    assert "lbl_apk_meta" in quelle


# --------------------------------------------------------------------------- #
#  USB-Markierung in der Headset-Liste
# --------------------------------------------------------------------------- #
class _FakeApp:
    """
    Nur die beiden Methoden, um die es geht — ohne Qt und ohne Fenster.
    Gebunden wird die echte Implementierung aus VRApp, damit der Test wirklich
    den ausgelieferten Code prueft und keine Kopie davon.
    """

    def __init__(self, devices):
        self._usb_last_info = {"devices": devices}

    @staticmethod
    def _load():
        sys.path.insert(0, str(ROOT / "ui"))
        import os as _os
        _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from main import VRApp
        return VRApp

    def bind(self):
        cls = self._load()
        self._usb_device_names = cls._usb_device_names.__get__(self)
        self._tag_usb = cls._tag_usb.__get__(self)
        return self


def test_usb_markierung_trifft_das_richtige_headset():
    app = _FakeApp([{"name": "Pico 4"}]).bind()
    assert app._tag_usb("1  Quest 3") == "1  Quest 3"
    assert app._tag_usb("2  Pico 4").endswith("· USB")


def test_ohne_usb_geraet_bleibt_die_zeile_unveraendert():
    app = _FakeApp([]).bind()
    assert app._tag_usb("1  Quest 3") == "1  Quest 3"


def test_gross_kleinschreibung_egal():
    app = _FakeApp([{"name": "QUEST 3"}]).bind()
    assert app._tag_usb("1  Quest 3").endswith("· USB")
