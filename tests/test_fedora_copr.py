#!/usr/bin/env python3
"""
tests/test_fedora_copr.py — Fedora: COPR-Komponenten im Installations-Tab
========================================================================
Bis v1.2.2 bekam ein Fedora-Nutzer fuer xrizer nur ein Hinweisfenster mit
zwei Befehlen zum Kopieren. Seit v1.2.3 ist xrizer eine normale Statuszeile
im Installations-Tab und wird — nach Rueckfrage — im selben Terminalfenster
installiert wie alle anderen Pakete.

Geprueft wird genau das, was dabei schiefgehen kann:
  1. Die Paketliste kennt xrizer samt COPR-Kennung.
  2. Der Terminal-Befehl aktiviert das COPR VOR dem Install — und faellt auf
     dnf-plugins-core zurueck, wenn 'dnf copr' fehlt (dnf4).
  3. Pakete OHNE COPR bekommen keinen copr-enable-Aufruf untergeschoben.
  4. Der zusammengebaute Befehl ist gueltige Shell-Syntax (die geschweiften
     Klammern im ||-Zweig sind leicht falsch zu setzen).

Laeuft ohne Fedora, ohne dnf, ohne Terminal.
"""
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

import programs                                          # noqa: E402


# --------------------------------------------------------------------------- #
#  1. Paketdefinition
# --------------------------------------------------------------------------- #
def test_xrizer_is_a_copr_component():
    """xrizer steht in INSTALL_DNF_COPR — und NICHT in INSTALL_DNF."""
    assert "xrizer" in programs.INSTALL_DNF_COPR
    assert programs.INSTALL_DNF_COPR["xrizer"]["copr"] == "@xr-sig/xrizer"
    # Wuerde xrizer in INSTALL_DNF landen, liefe 'dnf install xrizer' ohne
    # aktiviertes COPR — also ein garantierter Fehlschlag beim Nutzer.
    for pkgs in programs.INSTALL_DNF.values():
        assert "xrizer" not in pkgs


def test_copr_groups_are_status_rows():
    """dnf_copr_groups() liefert das Format der Statuszeilen: {Name: [pkgs]}."""
    groups = programs.dnf_copr_groups()
    assert groups["xrizer"] == ["xrizer"]
    # Kopie, keine Referenz — die UI darf die Liste nicht versehentlich leeren.
    groups["xrizer"].append("kaputt")
    assert programs.dnf_copr_groups()["xrizer"] == ["xrizer"]


def test_copr_lookup_per_package():
    assert programs.dnf_copr_for_package("xrizer") == "@xr-sig/xrizer"
    assert programs.dnf_copr_for_package("wivrn") is None
    assert programs.dnf_copr_for_package("envision-xrizer") is None


# --------------------------------------------------------------------------- #
#  2.–4. Terminalbefehl
# --------------------------------------------------------------------------- #
@pytest.fixture
def worker_cls():
    """InstallWorker braucht PySide6 — Test ueberspringen, wenn es fehlt."""
    pytest.importorskip("PySide6.QtCore")
    from install_worker import InstallWorker
    return InstallWorker


def test_copr_is_enabled_before_install(worker_cls):
    w = worker_cls(["xrizer"], helper="dnf",
                   copr_map={"xrizer": "@xr-sig/xrizer"})
    cmd = w.build_bash_command("xrizer", 1, 1)

    assert "dnf copr enable -y @xr-sig/xrizer" in cmd
    assert "sudo dnf install -y xrizer" in cmd
    # Reihenfolge: erst Repo aktivieren, dann installieren.
    assert cmd.index("copr enable") < cmd.index("install -y xrizer")
    # dnf4-Rueckfall
    assert "dnf-plugins-core" in cmd


def test_plain_dnf_package_gets_no_copr(worker_cls):
    w = worker_cls(["wivrn"], helper="dnf", copr_map={"xrizer": "@xr-sig/xrizer"})
    cmd = w.build_bash_command("wivrn", 1, 1)
    assert "copr" not in cmd
    assert "sudo dnf install -y wivrn" in cmd


def test_default_copr_map_is_empty(worker_cls):
    """Ohne copr_map verhaelt sich der Worker exakt wie vorher."""
    w = worker_cls(["wivrn"], helper="dnf")
    assert w.copr_map == {}
    assert "copr" not in w.build_bash_command("wivrn", 1, 1)


def test_arch_path_untouched(worker_cls):
    w = worker_cls(["wivrn-server"], helper="yay")
    cmd = w.build_bash_command("wivrn-server", 1, 2)
    assert "yay -S wivrn-server" in cmd
    assert "copr" not in cmd


def test_command_is_valid_shell(worker_cls):
    """
    'bash -n' prueft die Syntax, ohne irgendetwas auszufuehren.
    Die geschweiften Klammern im ||-Zweig sind genau die Stelle, an der ein
    fehlendes Semikolon den ganzen Befehl unbrauchbar macht.
    """
    w = worker_cls(["xrizer"], helper="dnf",
                   copr_map={"xrizer": "@xr-sig/xrizer"})
    cmd = w.build_bash_command("xrizer", 1, 1)
    res = subprocess.run(["bash", "-n", "-c", cmd],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert res.returncode == 0, res.stderr.decode()


# --------------------------------------------------------------------------- #
#  5. Sprachdateien
# --------------------------------------------------------------------------- #
def test_copr_dialog_texts_exist():
    """
    Die Rueckfrage braucht ihre Texte in JEDER Sprache — fehlen sie, steht im
    Dialog der rohe Schluessel.
    """
    import json
    for lang in ("en", "de"):
        data = json.loads((ROOT / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        for key in ("fedora_copr_title", "fedora_copr_text",
                    "fedora_copr_yes", "fedora_copr_no"):
            assert key in data, f"{key} fehlt in {lang}.json"
        assert "{copr}" in data["fedora_copr_text"]
        assert "{name}" in data["fedora_copr_text"]
        # Die alten Kopier-Texte sind weg — sonst schleppt man tote Strings mit.
        assert "fedora_xrizer_text" not in data


# --------------------------------------------------------------------------- #
#  6. Bezugsquellen je Komponente
# --------------------------------------------------------------------------- #
def test_xrizer_hat_zwei_quellen_auf_fedora():
    """
    COPR steht VORNE und ist damit Vorauswahl — es ist der Weg, den das
    Projekt selbst vorgibt. Das GitHub-Release bleibt als zweite Quelle
    daneben, fuer den Fall dass das COPR wieder in Zeitueberschreitungen
    laeuft oder wie angekuendigt verschwindet.
    """
    quellen = programs.component_sources("dnf", "xrizer")
    assert quellen == [programs.SOURCE_COPR, programs.SOURCE_GITHUB]


def test_normale_fedora_pakete_haben_eine_quelle():
    assert programs.component_sources("dnf", "WiVRn / Monado") == ["dnf"]
    assert programs.component_sources("dnf", "opencomposite") == ["dnf"]


def test_arch_bleibt_beim_helper():
    assert programs.component_sources("yay", "opencomposite") == ["yay"]
    assert programs.component_sources("paru", "opencomposite") == ["paru"]
    # xrizer darf auch auf Arch von GitHub kommen, falls der AUR-Build klemmt
    assert programs.component_sources("yay", "xrizer") == ["yay", programs.SOURCE_GITHUB]


def test_ohne_paketverwaltung_keine_quelle():
    """Ubuntu/Debian: der Tab zeigt nur den Status, es gibt nichts zu klicken."""
    assert programs.component_sources("", "WiVRn") == []
    assert programs.component_sources("native", "WiVRn") == []


def test_jede_quelle_hat_einen_klarnamen():
    """Sonst steht im Dropdown die rohe Kennung."""
    for method in ("dnf", "yay", "paru"):
        for name in ("xrizer", "opencomposite", "WiVRn / Monado"):
            for src in programs.component_sources(method, name):
                assert src in programs.SOURCE_LABELS, src


def test_zeilentexte_vorhanden():
    import json
    for lang in ("en", "de"):
        data = json.loads((ROOT / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        for key in ("install_row_btn", "install_row_tip", "install_source_tip"):
            assert key in data, f"{key} fehlt in {lang}.json"
        assert "{name}" in data["install_row_tip"]


# --------------------------------------------------------------------------- #
#  7. Tools-Tab: RPM-Quelle auf Fedora
# --------------------------------------------------------------------------- #
def _tool(key):
    for entry in programs.TOOLS_APPS + programs.TOOLS_OSC:
        if entry["key"] == key:
            return entry
    raise AssertionError(f"Tool {key} nicht gefunden")


def test_slimevr_und_ogb_koennen_rpm():
    assert "rpm" in _tool("slimevr-bin")["install_methods"]
    assert "rpm" in _tool("oscgoesbrrr")["install_methods"]
    assert _tool("slimevr-bin")["github_repo"] == "SlimeVR/SlimeVR-Server"
    assert _tool("oscgoesbrrr")["github_repo"] == "OscToys/OscGoesBrrr"


def test_slimevr_hat_flathub():
    assert _tool("slimevr-bin")["flatpak_id"] == "dev.slimevr.SlimeVR"


def test_rpm_asset_waehlt_die_richtige_architektur():
    """
    Der eigentliche Stolperstein: SlimeVR legt im Release
    'SlimeVR-aarch64.rpm' VOR 'SlimeVR-amd64.rpm'. Wer den ersten Treffer
    nimmt, laedt auf einem normalen PC das ARM-Paket — es installiert sich
    sogar, startet aber nie.
    """
    pytest.importorskip("PySide6.QtCore")
    import appimage_installer as appimg
    assets = [{"name": n, "browser_download_url": "https://example.invalid/" + n}
              for n in ("SlimeVR-aarch64.AppImage", "SlimeVR-aarch64.deb",
                        "SlimeVR-aarch64.rpm", "SlimeVR-amd64.AppImage",
                        "SlimeVR-amd64.deb", "SlimeVR-amd64.rpm")]
    _url, name = appimg._pick_appimage_asset(assets, ".rpm")
    assert name == "SlimeVR-amd64.rpm"


def test_rpm_sicht_aendert_das_original_nicht():
    """OscGoesBrrr hat AppImage UND RPM — die Muster duerfen sich nicht mischen."""
    pytest.importorskip("PySide6.QtCore")
    import appimage_installer as appimg
    tool = _tool("oscgoesbrrr")
    view = appimg.rpm_tool_view(tool)
    assert view["asset_match"] == ".rpm"
    assert tool["asset_match"] == ".AppImage"


def test_rpm_nur_mit_dnf(monkeypatch):
    """Auf Arch waere ein RPM sinnlos — die Methode darf dort nicht auftauchen."""
    pytest.importorskip("PySide6.QtCore")
    import appimage_installer as appimg
    monkeypatch.setattr(appimg, "dnf_available", lambda: False)
    monkeypatch.setattr(appimg, "available_aur_helpers", lambda: [])
    monkeypatch.setattr(appimg, "flatpak_available", lambda: False)
    assert "rpm" not in appimg.detect_install_methods(_tool("slimevr-bin"))

    monkeypatch.setattr(appimg, "dnf_available", lambda: True)
    assert "rpm" in appimg.detect_install_methods(_tool("slimevr-bin"))
