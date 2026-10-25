#!/usr/bin/env python3
"""
tests/test_startup_speed.py — Start-Bremsen (v1.4.4)
====================================================
Beim Programmstart liefen bis v1.4.3 im GUI-Thread u. a.:
  12x yay/paru -Q obah-git   (Controls-Tab, mehrfach dieselbe Frage)
   4x flatpak info <id>      (Autostart-Vorschlagsliste)
   2x pactl                  (Mikrofonliste in den Settings)
   1x wivrn-server --version (Versionszeile)
Je nach System kostete das mehrere Sekunden, bevor das Fenster erschien.
Diese Tests halten die Abkuerzungen fest, damit sie nicht still verloren
gehen.
"""
import os
import sys
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# --------------------------------------------------------------------------- #
#  Flatpak: Ordner-Pruefung statt 'flatpak info'
# --------------------------------------------------------------------------- #
def _no_subprocess(monkeypatch, module):
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, "", "")
    monkeypatch.setattr(module.proc, "run", fake_run)
    return calls


def test_flatpak_installiert_per_ordner(monkeypatch, tmp_path):
    import appimage_installer as appimg
    user = tmp_path / "user"
    (user / "app" / "org.example.App" / "x86_64" / "stable" / "active").mkdir(parents=True)
    (user / "app" / "org.example.App" / "current").symlink_to("x86_64/stable")
    monkeypatch.setenv("FLATPAK_USER_DIR", str(user))
    monkeypatch.setenv("FLATPAK_SYSTEM_DIR", str(tmp_path / "system"))
    monkeypatch.setattr(appimg.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(appimg, "_flatpak_has_extra_installations", lambda: False)
    calls = _no_subprocess(monkeypatch, appimg)

    assert appimg.flatpak_app_installed("org.example.App") is True
    assert appimg.flatpak_app_installed("org.example.Missing") is False
    assert calls == [], f"kein Subprozess erwartet, waren: {calls}"


def test_flatpak_ohne_flatpak_ist_nichts_installiert(monkeypatch, tmp_path):
    import appimage_installer as appimg
    monkeypatch.setattr(appimg.shutil, "which", lambda name: None)
    assert appimg.flatpak_app_installed("org.example.App") is False


def test_flatpak_rueckfall_bei_extra_installationen(monkeypatch, tmp_path):
    """Eigene Installationsorte kennt nur flatpak selbst -> dann doch fragen."""
    import appimage_installer as appimg
    monkeypatch.setenv("FLATPAK_USER_DIR", str(tmp_path / "u"))
    monkeypatch.setenv("FLATPAK_SYSTEM_DIR", str(tmp_path / "s"))
    monkeypatch.setattr(appimg.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(appimg, "_flatpak_has_extra_installations", lambda: True)
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(appimg.proc, "run", fake_run)
    assert appimg.flatpak_app_installed("org.example.App") is True
    assert calls == [["flatpak", "info", "org.example.App"]]


# --------------------------------------------------------------------------- #
#  AUR-Paket: ein pacman-Aufruf statt yay UND paru
# --------------------------------------------------------------------------- #
def _aur_tool():
    return {"key": "demo", "pkg": "demo-git", "methods": ["aur"]}


def test_installed_locally_fragt_pacman_genau_einmal(monkeypatch):
    import appimage_installer as appimg
    monkeypatch.setattr(appimg, "supported_methods", lambda tool: ["aur"])
    monkeypatch.setattr(appimg, "available_aur_helpers", lambda: ["yay", "paru"])
    monkeypatch.setattr(appimg.shutil, "which",
                        lambda name: "/usr/bin/pacman" if name == "pacman" else None)
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, "", "")
    monkeypatch.setattr(appimg.proc, "run", fake_run)

    assert appimg.installed_locally(_aur_tool()) is False
    assert calls == [["pacman", "-Q", "demo-git"]]


def test_installed_locally_findet_aur_paket(monkeypatch):
    import appimage_installer as appimg
    monkeypatch.setattr(appimg, "supported_methods", lambda tool: ["aur"])
    monkeypatch.setattr(appimg, "available_aur_helpers", lambda: ["paru"])
    monkeypatch.setattr(appimg.shutil, "which",
                        lambda name: "/usr/bin/pacman" if name == "pacman" else None)
    monkeypatch.setattr(appimg.proc, "run",
                        lambda cmd, *a, **k: subprocess.CompletedProcess(cmd, 0, "", ""))
    assert appimg.installed_locally(_aur_tool()) is True


def test_installed_locally_ohne_aur_helfer_fragt_nicht(monkeypatch):
    """Kein Arch (keine Helfer) -> wie bisher gar keine Paketabfrage."""
    import appimage_installer as appimg
    monkeypatch.setattr(appimg, "supported_methods", lambda tool: ["aur"])
    monkeypatch.setattr(appimg, "available_aur_helpers", lambda: [])
    monkeypatch.setattr(appimg.shutil, "which", lambda name: None)
    calls = _no_subprocess(monkeypatch, appimg)
    assert appimg.installed_locally(_aur_tool()) is False
    assert calls == []


# --------------------------------------------------------------------------- #
#  Controls-Tab: waehrend des Aufbaus nur einmal fragen
# --------------------------------------------------------------------------- #
class _Ctl:
    """Minimaler Traeger fuer ControlsMixin._control_installed."""
    def __init__(self, answers):
        self.answers = answers
        self.asked = []

    def _control_tool(self, key):
        return {"key": key}


def _bind(obj):
    from tabs.controls_mixin import ControlsTabMixin
    obj._control_installed = ControlsTabMixin._control_installed.__get__(obj)
    obj._control_installed_uncached = ControlsTabMixin._control_installed_uncached.__get__(obj)
    return obj


def test_control_installed_merkt_sich_nur_beim_laden(monkeypatch):
    import appimage_installer as appimg
    ctl = _bind(_Ctl({}))
    state = {"n": 0, "installed": False}

    def fake(tool):
        state["n"] += 1
        return state["installed"]
    monkeypatch.setattr(appimg, "installed_locally", fake)

    ctl.is_loading = True
    for _ in range(6):
        assert ctl._control_installed("obah") is False
    assert state["n"] == 1, "waehrend des Ladens nur EINE echte Pruefung"

    # Nach dem Laden (main.py verwirft den Speicher) wieder jedes Mal frisch —
    # sonst saehe der Schalter eine gerade abgeschlossene Installation nicht.
    ctl.is_loading = False
    ctl._control_installed_cache = None
    state["installed"] = True
    assert ctl._control_installed("obah") is True
    assert ctl._control_installed("obah") is True
    assert state["n"] == 3


# --------------------------------------------------------------------------- #
#  WiVRn-Version und Mikrofonliste kommen aus Hintergrund-Threads
# --------------------------------------------------------------------------- #
def test_paketpruefung_liefert_version_vor_ergebnis(qapp, monkeypatch):
    import main as app_main
    monkeypatch.setattr(app_main, "wivrn_version_text", lambda: "26.1")
    monkeypatch.setattr(app_main.proc, "output_of", lambda cmd, **k: "")
    monkeypatch.setattr(app_main.shutil, "which", lambda _n: "/usr/bin/yay")

    worker = app_main.PackageCheckWorker("yay", {"WiVRn / Monado": ["wivrn-server"]})
    order = []
    worker.version_signal.connect(lambda v: order.append(("version", v)))
    worker.result_signal.connect(lambda r, u: order.append(("result", r)))
    worker.run()
    assert order[0] == ("version", "26.1")
    assert order[1][0] == "result"


def test_paketpruefung_ueberlebt_versionsfehler(qapp, monkeypatch):
    import main as app_main

    def boom():
        raise RuntimeError("kaputt")
    monkeypatch.setattr(app_main, "wivrn_version_text", boom)
    monkeypatch.setattr(app_main.proc, "output_of", lambda cmd, **k: "")
    monkeypatch.setattr(app_main.shutil, "which", lambda _n: "/usr/bin/yay")
    worker = app_main.PackageCheckWorker("yay", {"WiVRn / Monado": ["wivrn-server"]})
    got = []
    worker.result_signal.connect(lambda r, u: got.append(r))
    worker.run()
    assert got, "Paketstatus muss trotz Versionsfehler ankommen"


def test_mikrofon_scan_worker(qapp):
    import main as app_main
    w = app_main.MicScanWorker(lambda: ([("a", "Mic A", "mic")], "a"))
    got = []
    w.done.connect(got.append)
    w.run()
    assert got == [([("a", "Mic A", "mic")], "a")]

    def boom():
        raise RuntimeError("pactl weg")
    w2 = app_main.MicScanWorker(boom)
    got2 = []
    w2.done.connect(got2.append)
    w2.run()
    assert got2 == [([], None)]
