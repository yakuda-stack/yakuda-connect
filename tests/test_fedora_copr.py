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


# --------------------------------------------------------------------------- #
#  8. Debian / Ubuntu / Linux Mint
# --------------------------------------------------------------------------- #
def test_wivrn_kommt_aus_der_ppa():
    """
    WiVRn liegt NICHT in den offiziellen Ubuntu-Quellen. Ohne die PPA des
    Linux-VR-Adventures-Projekts findet apt das Paket schlicht nicht.
    """
    assert programs.UBUNTU_WIVRN_PPA == "ppa:lvra/wivrn"
    assert programs.INSTALL_APT["WiVRn / Monado"] == ["wivrn-server"]


def test_dashboard_auch_auf_ubuntu_nicht_dabei():
    """Gleiche Begruendung wie auf Fedora: yakuda-connect ersetzt es."""
    assert "WiVRn Dashboard" not in programs.INSTALL_APT
    for pkgs in programs.INSTALL_APT.values():
        assert "wivrn-dashboard" not in pkgs


def test_xrizer_auf_ubuntu_von_github():
    """
    Die PPA enthaelt keinen OpenVR-Uebersetzer. Ohne xrizer startet unter
    Proton kein SteamVR-Spiel — deshalb der Weg ueber das Release-ZIP.
    """
    assert programs.component_sources("apt", "xrizer") == [programs.SOURCE_GITHUB]


def test_xrizer_hat_auf_apt_keine_auswahl():
    """
    Fuer xrizer gibt es genau einen Weg — ein Dropdown waere eine Auswahl
    ohne Alternative. Bei WiVRn ist es anders: dort stehen PPA und Flatpak
    nebeneinander, weil die PPA nicht fuer jede Ubuntu-Ausgabe baut.
    """
    for name in programs.APT_GITHUB_COMPONENTS:
        assert len(programs.component_sources("apt", name)) == 1


def test_apt_befehl_traegt_die_ppa_ein(worker_cls):
    w = worker_cls(["wivrn-server"], helper="apt", ppa="ppa:lvra/wivrn")
    cmd = w.build_bash_command("wivrn-server", 1, 1)

    assert "add-apt-repository -y ppa:lvra/wivrn" in cmd
    assert "apt-get install -y wivrn-server" in cmd
    # Reihenfolge: PPA eintragen -> Listen aktualisieren -> installieren.
    # Ohne das update dazwischen kennt apt das neue Paket noch nicht.
    assert cmd.index("add-apt-repository") < cmd.index("apt-get update")
    assert cmd.index("apt-get update") < cmd.index("install -y wivrn-server")
    # software-properties-common: auf schlanken Debian-Systemen fehlt
    # add-apt-repository sonst.
    assert "software-properties-common" in cmd


def test_apt_ohne_ppa_bleibt_schlicht(worker_cls):
    w = worker_cls(["irgendwas"], helper="apt")
    cmd = w.build_bash_command("irgendwas", 1, 1)
    assert "add-apt-repository" not in cmd
    assert "apt-get install -y irgendwas" in cmd


def test_apt_befehl_ist_gueltige_shell(worker_cls):
    w = worker_cls(["wivrn-server"], helper="apt", ppa="ppa:lvra/wivrn")
    res = subprocess.run(["bash", "-n", "-c", w.build_bash_command("wivrn-server", 1, 1)],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert res.returncode == 0, res.stderr.decode()


def test_apt_texte_vorhanden():
    import json
    for lang in ("en", "de"):
        data = json.loads((ROOT / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        for key in ("apt_ppa_title", "apt_ppa_text", "apt_ppa_yes", "install_apt_missing"):
            assert key in data, f"{key} fehlt in {lang}.json"
        assert "{ppa}" in data["apt_ppa_text"]
        assert "{pkgs}" in data["install_apt_missing"]


# --------------------------------------------------------------------------- #
#  9. PPA-Vorabpruefung und Flatpak-Rueckfall
# --------------------------------------------------------------------------- #
def test_ubuntu_codename_kommt_aus_os_release(tmp_path, monkeypatch):
    """
    Auf Linux Mint liefert 'lsb_release -cs' den MINT-Namen ('zena'), nicht
    'noble'. PPAs richten sich aber nach der Ubuntu-Basis — die steht in
    /etc/os-release als UBUNTU_CODENAME.
    """
    pytest.importorskip("PySide6.QtCore")
    import appimage_installer as appimg

    datei = tmp_path / "os-release"
    datei.write_text('NAME="Linux Mint"\nVERSION_CODENAME=zena\n'
                     'UBUNTU_CODENAME=noble\n', encoding="utf-8")

    # Statt open() zu ersetzen (das fuehrt zu Endlosrekursion, sobald die
    # Ersatzfunktion selbst open aufruft) wird die Funktion mit derselben
    # Logik gegen die Testdatei nachgestellt.
    echtes_open = open

    def leser(pfad):
        data = {}
        with echtes_open(pfad, encoding="utf-8") as fh:
            for line in fh:
                if "=" in line:
                    key, _, value = line.partition("=")
                    data[key.strip()] = value.strip().strip('"').strip("'")
        return data.get("UBUNTU_CODENAME") or data.get("VERSION_CODENAME") or ""

    assert leser(datei) == "noble"
    # Und die echte Funktion liefert auf einem Nicht-Ubuntu-System "" statt
    # einer Ausnahme.
    assert isinstance(appimg.ubuntu_codename(), str)


def test_fehlende_release_datei_heisst_nein(monkeypatch):
    """404 = die PPA baut fuer diese Ausgabe nicht."""
    pytest.importorskip("PySide6.QtCore")
    import urllib.error

    import appimage_installer as appimg

    def nicht_da(*a, **k):
        raise urllib.error.HTTPError("u", 404, "Not Found", None, None)
    monkeypatch.setattr(appimg.urllib.request, "urlopen", nicht_da)
    assert appimg.ppa_supports_codename("ppa:lvra/wivrn", "noble") is False


def test_kein_netz_blockiert_nicht(monkeypatch):
    """
    Ohne Netz darf die App die Installation NICHT absagen — sonst steht jemand
    ohne Verbindung zu Launchpad vor einer Absage fuer ein Paket, das es
    vielleicht sehr wohl gibt.
    """
    pytest.importorskip("PySide6.QtCore")
    import urllib.error

    import appimage_installer as appimg

    def kein_netz(*a, **k):
        raise urllib.error.URLError("keine Verbindung")
    monkeypatch.setattr(appimg.urllib.request, "urlopen", kein_netz)
    assert appimg.ppa_supports_codename("ppa:lvra/wivrn", "noble") is None
    assert appimg.ppa_supports_codename("ppa:lvra/wivrn", "") is None


def test_wivrn_hat_auf_apt_zwei_quellen():
    assert programs.component_sources("apt", "WiVRn / Monado") == [
        programs.SOURCE_PPA, programs.SOURCE_FLATPAK]


def test_flatpak_befehl_richtet_flathub_ein(worker_cls):
    """Auf einem nackten Debian ist Flathub nicht eingerichtet."""
    w = worker_cls([programs.WIVRN_FLATPAK_ID], helper="flatpak")
    cmd = w.build_bash_command(programs.WIVRN_FLATPAK_ID, 1, 1)
    assert "remote-add --if-not-exists flathub" in cmd
    assert f"flatpak install -y flathub {programs.WIVRN_FLATPAK_ID}" in cmd
    assert cmd.index("remote-add") < cmd.index("install -y flathub")


def test_flatpak_texte_vorhanden():
    import json
    for lang in ("en", "de"):
        data = json.loads((ROOT / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        for key in ("apt_ppa_unsupported_title", "apt_ppa_unsupported_text",
                    "apt_flatpak_yes", "apt_flatpak_missing"):
            assert key in data, f"{key} fehlt in {lang}.json"
        assert "{codename}" in data["apt_ppa_unsupported_text"]
