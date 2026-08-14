#!/usr/bin/env python3
"""
tests/test_safety.py — Tests fuer die gefaehrlichsten Codepfade
===============================================================
Hier liegen die Sicherheitsmechanismen aus v1.1.4. Warum ausgerechnet die
getestet werden:

Ein Fehler in `config_manager` kostet den Nutzer seine Einstellungen. Ein
Fehler HIER hat schon einmal Steam auf Nobara komplett lahmgelegt — ein
Arch-Backup wurde auf Fedora zurueckgespielt, Steams pressure-vessel las
das fremde Manifest und brach mit ``gelf_getehdr(): invalid 'Elf' handle``
in eine steamwebhelper-Endlosschleife. Dazu kommt, dass dieser Code
``shutil.rmtree`` auf Systemordner anwendet.

Von Hand ist das kaum reproduzierbar: man braeuchte zwei Distributionen und
ein kaputtes Backup. Als Test mit Fixture-Dateien geht es in Millisekunden.

Alle Tests laufen ohne Qt, ohne Netz und ohne echte VR-Installation.
"""
import json
import os
import pathlib
import struct
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))


# --------------------------------------------------------------------------- #
#  Hilfsmittel: echte ELF-Dateien bauen
# --------------------------------------------------------------------------- #
def write_elf(path, bits=64):
    """
    Schreibt eine minimale, aber echte ELF-Datei. Die Bitness steckt in Byte 4
    des Headers (1 = 32 Bit, 2 = 64 Bit) — genau das lesen elf_class() und
    _is_elf(). Eine leere Datei mit .so-Endung wuerde die Pruefung nicht
    abbilden, denn frueher wurde nur "Datei existiert" geprueft. Genau diese
    zu laxe Pruefung war die Ursache des Steam-Absturzes.
    """
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(b"\x7fELF")
    header.append(2 if bits == 64 else 1)   # EI_CLASS
    header.append(1)                        # little endian
    header.append(1)                        # ELF-Version
    header += b"\x00" * 9
    header += struct.pack("<HH", 3, 62 if bits == 64 else 3)
    path.write_bytes(bytes(header) + b"\x00" * 64)
    return str(path)


def write_manifest(path, library_path):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "file_format_version": "1.0.0",
        "runtime": {"name": "WiVRn", "library_path": library_path},
    }), encoding="utf-8")
    return str(path)


# --------------------------------------------------------------------------- #
#  ELF-Erkennung — die Grundlage aller Bitness-Pruefungen
# --------------------------------------------------------------------------- #
def test_elf_class_detects_bitness(tmp_path):
    import vr_environment as venv
    assert venv.elf_class(write_elf(tmp_path / "lib64.so", 64)) == 64
    assert venv.elf_class(write_elf(tmp_path / "lib32.so", 32)) == 32


def test_elf_class_rejects_non_elf(tmp_path):
    """
    Der Kern des Bugs von v1.1.4: eine Datei, die nur SO HEISST wie eine
    Bibliothek, darf nicht als gueltig durchgehen.
    """
    import vr_environment as venv
    fake = tmp_path / "libnicht_echt.so"
    fake.write_text("das ist ein Textfile, keine Bibliothek", encoding="utf-8")
    assert venv.elf_class(str(fake)) not in (32, 64)


def test_is_elf_on_missing_file():
    import openxr_manager as oxr
    assert oxr._is_elf("/gibt/es/nicht/libwivrn.so") is False


# --------------------------------------------------------------------------- #
#  Bitness aus dem Dateinamen ableiten
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name,expected", [
    ("wivrn.i686.json", 32),
    ("wivrn.i386.json", 32),
    ("openxr.x86.json", 32),
    ("wivrn_i686.json", 32),
    ("wivrn.json", 64),
    ("openxr_wivrn64.json", 64),
])
def test_expected_bits_from_filename(name, expected):
    """Ein *.i686.json-Manifest muss auf eine 32-Bit-Bibliothek zeigen.
    Verwechselt man das, startet Steam nicht mehr."""
    import openxr_manager as oxr
    assert oxr._expected_bits(name) == expected


def test_resolve_lib_relative_and_absolute(tmp_path):
    import openxr_manager as oxr
    manifest = tmp_path / "1" / "wivrn.json"
    assert oxr._resolve_lib(str(manifest), "/usr/lib/libwivrn.so") == "/usr/lib/libwivrn.so"
    # relativ = relativ zum Ordner des Manifests
    assert oxr._resolve_lib(str(manifest), "../libwivrn.so") == str(tmp_path / "libwivrn.so")
    assert oxr._resolve_lib(str(manifest), "") is None


# --------------------------------------------------------------------------- #
#  Manifest-Pruefung vor dem Zurueckspielen
# --------------------------------------------------------------------------- #
def test_manifest_with_missing_library_is_rejected(tmp_path):
    """Zeigt ein Manifest auf eine Bibliothek, die es nicht gibt, darf es
    nicht nach /usr/share/openxr geschrieben werden."""
    import backup_manager as bm
    m = write_manifest(tmp_path / "wivrn.json", "/gibt/es/nicht/libwivrn.so")
    assert bm._manifest_is_usable(m, "wivrn.json") is False


def test_manifest_with_wrong_bitness_is_rejected(tmp_path):
    """
    Der Nobara-Fall in einem Test: ein 64-Bit-Manifest zeigt auf eine
    32-Bit-Bibliothek (so entsteht es, wenn ein Arch-Backup auf Fedora
    landet). Muss abgelehnt werden.
    """
    import backup_manager as bm
    lib = write_elf(tmp_path / "libwivrn.so", 32)
    m = write_manifest(tmp_path / "wivrn.json", lib)
    assert bm._manifest_is_usable(m, "wivrn.json") is False


def test_matching_manifest_is_accepted(tmp_path):
    import backup_manager as bm
    lib = write_elf(tmp_path / "libwivrn.so", 64)
    m = write_manifest(tmp_path / "wivrn.json", lib)
    assert bm._manifest_is_usable(m, "wivrn.json") is True


def test_32bit_manifest_with_32bit_library_is_accepted(tmp_path):
    import backup_manager as bm
    lib = write_elf(tmp_path / "libwivrn32.so", 32)
    m = write_manifest(tmp_path / "wivrn.i686.json", lib)
    assert bm._manifest_is_usable(m, "wivrn.i686.json") is True


def test_broken_json_manifest_is_rejected(tmp_path):
    import backup_manager as bm
    p = tmp_path / "kaputt.json"
    p.write_text("{ kein gueltiges JSON", encoding="utf-8")
    assert bm._manifest_is_usable(str(p), "kaputt.json") is False


def test_api_layer_manifest_passes_through(tmp_path):
    """API-Layer haben keinen 'runtime'-Block und sind unkritisch —
    sie duerfen nicht faelschlich blockiert werden."""
    import backup_manager as bm
    p = tmp_path / "api_layer.json"
    p.write_text(json.dumps({"api_layer": {"name": "XR_APILAYER_test"}}), encoding="utf-8")
    assert bm._manifest_is_usable(str(p), "api_layer.json") is True


# --------------------------------------------------------------------------- #
#  Herkunftspruefung: darf ein Backup Systemordner ueberschreiben?
# --------------------------------------------------------------------------- #
def _make_backup(tmp_path, meta):
    root = tmp_path / "backup"
    root.mkdir(parents=True, exist_ok=True)
    if meta is not None:
        (root / "backup_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return str(root)


def test_foreign_distro_backup_may_not_touch_system(tmp_path):
    """
    Genau der Fall, der Steam zerlegt hat: ein auf Arch erzeugtes Backup
    wird auf Fedora eingespielt. Systemordner muessen tabu bleiben.
    """
    import backup_manager as bm
    now = bm.system_fingerprint()
    root = _make_backup(tmp_path, {
        "origin": "local",
        "system": {"distro_id": "arch",
                   "lib_layout": "usr/lib" if now["lib_layout"] != "usr/lib" else "usr/lib64"},
    })
    allowed, reason = bm._may_restore_system_dirs(root)
    assert allowed is False
    assert reason in ("distro_mismatch", "layout_mismatch")


def test_github_reference_backup_may_not_touch_system(tmp_path):
    """Das GitHub-Referenz-Backup stammt nie von diesem Rechner."""
    import backup_manager as bm
    now = bm.system_fingerprint()
    root = _make_backup(tmp_path, {"origin": "github", "system": now})
    allowed, reason = bm._may_restore_system_dirs(root)
    assert allowed is False
    assert reason == "foreign_origin"


def test_old_backup_without_meta_may_not_touch_system(tmp_path):
    """Backups von vor v1.1.4 haben keine backup_meta.json — im Zweifel Nein."""
    import backup_manager as bm
    allowed, reason = bm._may_restore_system_dirs(_make_backup(tmp_path, None))
    assert allowed is False
    assert reason == "no_meta"


def test_own_local_backup_may_restore_system(tmp_path):
    """Das eigene Backup vom selben Rechner darf natuerlich zurueck."""
    import backup_manager as bm
    root = _make_backup(tmp_path, {"origin": "local", "system": bm.system_fingerprint()})
    allowed, reason = bm._may_restore_system_dirs(root)
    assert allowed is True, reason


def test_system_fingerprint_has_required_fields():
    import backup_manager as bm
    fp = bm.system_fingerprint()
    assert "distro_id" in fp and "lib_layout" in fp
    assert fp["distro_id"]


# --------------------------------------------------------------------------- #
#  Manifest-Reparatur plant nichts Zerstoererisches
# --------------------------------------------------------------------------- #
def test_repair_plan_is_empty_without_broken_manifests(monkeypatch):
    """
    Ohne kaputte Manifeste darf der Reparaturplan leer sein — die App darf
    nicht "vorsorglich" an Systemdateien herumschreiben.
    """
    import openxr_manager as oxr
    monkeypatch.setattr(oxr, "scan_runtime_manifests", lambda: [])
    plan = oxr.plan_manifest_repair()
    assert not plan or all(not p.get("actions") for p in plan if isinstance(p, dict))


# --------------------------------------------------------------------------- #
#  WiVRn-Dashboard-Einstellungen (wivrn-dashboard.conf)
# --------------------------------------------------------------------------- #
# Das ist die Konfiguration eines FREMDEN Programms. Zerlegen wir sie, startet
# das WiVRn-Dashboard nicht mehr sauber — und der Nutzer sucht den Fehler zu
# Recht erst einmal bei WiVRn.

@pytest.fixture
def wivrn_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    import importlib
    import vr_environment
    import wivrn_dashboard
    importlib.reload(vr_environment)
    importlib.reload(wivrn_dashboard)
    return wivrn_dashboard


def test_default_is_off_without_file(wivrn_home):
    """Ohne Datei gilt der WiVRn-Standard: aus."""
    assert wivrn_home.get_auto_connect_usb() is False


def test_roundtrip_true_false(wivrn_home):
    assert wivrn_home.set_auto_connect_usb(True) is True
    assert wivrn_home.get_auto_connect_usb() is True
    assert wivrn_home.set_auto_connect_usb(False) is True
    assert wivrn_home.get_auto_connect_usb() is False


def test_qt_boolean_format(wivrn_home):
    """
    Qt schreibt und erwartet 'true'/'false' klein. Schreiben wir 'True',
    liest das Dashboard den Wert nicht als aktiviert — die Checkbox waere
    scheinbar wirkungslos.
    """
    wivrn_home.set_auto_connect_usb(True)
    content = pathlib.Path(wivrn_home.dashboard_config_file()).read_text(encoding="utf-8")
    assert "auto_connect_usb=true" in content
    assert "True" not in content


def test_foreign_keys_survive(wivrn_home):
    """
    Die Datei enthaelt auch adb_location, first_run usw. Diese Werte
    gehoeren dem Dashboard und duerfen beim Schreiben nicht verlorengehen.
    """
    path = pathlib.Path(wivrn_home.dashboard_config_file())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[General]\nfirst_run=false\nadb_location=/usr/bin/adb\n"
        "last_run_version=1.2.3\nadb_custom=true\n", encoding="utf-8")

    wivrn_home.set_auto_connect_usb(True)
    text = path.read_text(encoding="utf-8")
    for keep in ("adb_location=/usr/bin/adb", "last_run_version=1.2.3",
                 "first_run=false", "adb_custom=true"):
        assert keep in text, f"verloren gegangen: {keep}"


def test_key_case_is_preserved(wivrn_home):
    """
    configparser wuerde Schluessel standardmaessig kleinschreiben. Qt-Keys
    koennen aber CamelCase sein — die duerfen nicht umbenannt werden.
    """
    path = pathlib.Path(wivrn_home.dashboard_config_file())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[General]\nlastRunVersion=1.0\n", encoding="utf-8")
    wivrn_home.set_auto_connect_usb(True)
    assert "lastRunVersion=1.0" in path.read_text(encoding="utf-8")


def test_broken_file_does_not_crash(wivrn_home):
    """Eine unlesbare Datei darf die App nicht abschiessen."""
    path = pathlib.Path(wivrn_home.dashboard_config_file())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("das ist kein INI-Inhalt {{{", encoding="utf-8")
    assert wivrn_home.get_auto_connect_usb() is False


def test_no_temp_file_left_behind(wivrn_home):
    wivrn_home.set_auto_connect_usb(True)
    directory = pathlib.Path(wivrn_home.dashboard_config_file()).parent
    assert [p.name for p in directory.iterdir() if p.name.endswith(".tmp")] == []


def test_config_lives_next_to_wivrn_config_json(wivrn_home):
    """Beide Dateien liegen im selben Ordner — faellt auf, falls der
    Pfad-Helfer sich einmal aendert."""
    import vr_environment as venv
    assert (os.path.dirname(wivrn_home.dashboard_config_file())
            == os.path.dirname(venv.wivrn_config_file()))
    assert wivrn_home.dashboard_config_file().endswith("wivrn-dashboard.conf")


# --------------------------------------------------------------------------- #
#  Startgeschwindigkeit: Paketpruefung
# --------------------------------------------------------------------------- #
def test_package_check_uses_two_calls_not_one_per_package(monkeypatch):
    """
    Regressionstest fuer die Startzeit.

    Frueher lief je Paket ein "yay -Q" UND ein "yay -Qu" — bei sechs Paketen
    zwoelf Prozessstarts, davon sechs mit AUR-Abfrage ueber das Netz, alle
    im GUI-Thread. Das Fenster erschien erst danach.

    Jetzt werden die Paketlisten einmal geholt. Rutscht die Schleife je Paket
    wieder herein, steigt die Zahl der Aufrufe und dieser Test schlaegt an.
    """
    import main as app_main
    import proc

    calls = []

    def fake_output_of(cmd, **kwargs):
        calls.append(" ".join(cmd))
        if cmd[1] == "-Q":
            return "wivrn-server 1.0\nwivrn-dashboard 1.0\nxrizer 1.0\n"
        return "xrizer 1.1\n"

    monkeypatch.setattr(proc, "output_of", fake_output_of)
    monkeypatch.setattr(app_main.proc, "output_of", fake_output_of)
    monkeypatch.setattr(app_main.shutil, "which", lambda _name: "/usr/bin/yay")

    groups = {
        "WiVRn / Monado": ["wivrn-server"],
        "WiVRn Dashboard": ["wivrn-dashboard"],
        "xrizer": ["xrizer", "xrizer-common"],
        "opencomposite": ["opencomposite-git"],
    }
    worker = app_main.PackageCheckWorker("yay", groups)
    received = {}
    worker.result_signal.connect(lambda r, u: received.update(results=r, updates=u))
    worker.run()   # direkt, ohne echten Thread

    assert len(calls) == 2, f"erwartet 2 Aufrufe, waren {len(calls)}: {calls}"

    results = received["results"]
    assert results["WiVRn / Monado"]["installed"] is True
    # xrizer-common fehlt in der Liste -> Gruppe gilt als unvollstaendig
    assert results["xrizer"]["installed"] is False
    assert results["opencomposite"]["installed"] is False


def test_package_check_survives_failing_update_query(monkeypatch):
    """
    Ohne Netz liefert 'yay -Qu' nichts. Der Installationsstatus muss trotzdem
    korrekt angezeigt werden — sonst steht bei jedem Paket faelschlich
    "nicht installiert", nur weil die Updatepruefung scheiterte.
    """
    import main as app_main
    import proc

    def fake_output_of(cmd, **kwargs):
        if cmd[1] == "-Q":
            return "wivrn-server 1.0\n"
        return ""          # -Qu schlaegt fehl / leer

    monkeypatch.setattr(proc, "output_of", fake_output_of)
    monkeypatch.setattr(app_main.proc, "output_of", fake_output_of)
    monkeypatch.setattr(app_main.shutil, "which", lambda _name: "/usr/bin/yay")

    worker = app_main.PackageCheckWorker("yay", {"WiVRn / Monado": ["wivrn-server"]})
    received = {}
    worker.result_signal.connect(lambda r, u: received.update(results=r, updates=u))
    worker.run()

    assert received["results"]["WiVRn / Monado"]["installed"] is True
    assert received["updates"] is False
