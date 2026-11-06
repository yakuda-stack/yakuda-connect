#!/usr/bin/env python3
"""Tests fuer die Erst-Einrichtung (core/tabs/first_run_mixin.py):
Performance-Setup → WayVR → Tour, nacheinander und nie doppelt."""
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "core"))

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from test_exit_guard import window, _FakeProc, exit_guard, wivrn_server  # noqa: E402,F401


@pytest.fixture
def chain(window, monkeypatch):
    import vr_optimize as vopt
    w = window
    w.are_critical_packages_missing = lambda: False
    calls = []
    monkeypatch.setattr(vopt, "pending_steps", lambda: [])
    state = {"wayvr_async": False, "installing": False}
    # Echte Paketpruefung/Installation ist umgebungsabhaengig (Dauer, yay …)
    # — hier zaehlt nur die Logik der Kette. installation_running() selbst
    # testet test_installation_running_checks_workers.
    w.installation_running = lambda: state["installing"]

    def fake_wayvr():
        calls.append("wayvr")
        return state["wayvr_async"]
    w.maybe_offer_wayvr = fake_wayvr
    w.maybe_offer_tour = lambda: calls.append("tour")
    w.resize(1200, 800)
    w.show()
    # Die echte Paketpruefung vom Fensterstart abwarten — solange sie
    # laeuft, gilt die Installation (richtig) als nicht fertig.
    QTest.qWait(50)
    # Bis sie wirklich fertig ist: endet sie erst nach dem Zuruecksetzen,
    # startet first_run_after_install die Kette vom Dashboard aus doch noch.
    for _ in range(200):
        if not w._running(getattr(w, "_pkgcheck_worker", None)):
            break
        QTest.qWait(50)
    QTest.qWait(50)
    # Springt die App beim Start selbst aufs Dashboard (alle Pakete da),
    # ist schon ein Schritt geplant — der muss verworfen werden.
    w.reset_first_run_state()
    QTest.qWait(600)
    calls.clear()
    import json
    with open(vopt.APP_CONFIG_FILE, "w") as fh:
        json.dump({}, fh)
    return w, calls, state


def test_chain_runs_once_in_order(chain):
    w, calls, _state = chain
    w.maybe_offer_vr_optimize()
    w.maybe_offer_vr_optimize()               # zweiter Dashboard-Klick
    QTest.qWait(1200)
    w.maybe_offer_vr_optimize()
    QTest.qWait(400)
    assert calls == ["wayvr", "tour"]
    assert not w._first_run_busy


def test_tour_waits_for_wayvr_install(chain):
    w, calls, state = chain
    state["wayvr_async"] = True
    w.maybe_offer_vr_optimize()
    QTest.qWait(1200)
    assert calls == ["wayvr"] and w._first_run_busy
    w.first_run_after_wayvr()                 # Installation + Design fertig
    QTest.qWait(500)
    assert calls == ["wayvr", "tour"] and not w._first_run_busy


def test_no_chain_while_tour_runs(chain):
    w, calls, _state = chain
    w._tour = object()
    w.maybe_offer_vr_optimize()
    QTest.qWait(800)
    assert calls == [] and not w._optimize_checked
    w._tour = None


def test_waits_while_other_dialog_open(chain, monkeypatch):
    from PySide6.QtWidgets import QApplication
    w, calls, _state = chain
    modal = {"open": True}
    monkeypatch.setattr(QApplication, "activeModalWidget",
                        staticmethod(lambda: object() if modal["open"] else None))
    w.maybe_offer_vr_optimize()
    QTest.qWait(1100)
    assert calls == []
    modal["open"] = False
    QTest.qWait(1300)
    assert calls == ["wayvr", "tour"]


def test_stale_start_is_dropped(chain):
    """Wie beim Programmstart: Kette geplant, dann zurueckgesetzt — der alte
    Schritt darf nicht mehr laufen, nur der neue."""
    w, calls, _state = chain
    w.maybe_offer_vr_optimize()               # „Start-Sprung“
    w.reset_first_run_state()
    w.maybe_offer_vr_optimize()               # neuer Dashboard-Klick
    QTest.qWait(1300)
    assert calls == ["wayvr", "tour"]


def test_reset_clears_flags(chain):
    import json
    import vr_optimize as vopt
    w, _calls, _state = chain
    with open(vopt.APP_CONFIG_FILE, "w") as fh:
        json.dump({"dashboard_optimize_asked": "x", "dashboard_wayvr_asked": "x",
                   "tour_asked": "x", "language": "de"}, fh)
    w._optimize_checked = True
    w.reset_first_run()                       # Rueckfrage: Fixture sagt „Ja“
    with open(vopt.APP_CONFIG_FILE) as fh:
        data = json.load(fh)
    assert data == {"language": "de"}
    assert not w._optimize_checked


def test_reset_card_only_in_advanced_mode(chain):
    w, _c, _s = chain
    w.on_advanced_mode_toggled(False)
    assert w.ui.firstrun_card.isHidden()
    w.on_advanced_mode_toggled(True)
    assert not w.ui.firstrun_card.isHidden()
    w.on_advanced_mode_toggled(False)


def test_tour_finish_goes_to_dashboard(chain):
    from tabs.tour_mixin import TourMixin
    w, _c, _s = chain
    w.maybe_offer_tour = TourMixin.maybe_offer_tour.__get__(w)
    w._optimize_checked = True               # Kette beim Dashboard-Sprung nicht starten
    w.ui.sidebar.setCurrentRow(6)
    w.start_tour()
    tour = w._tour
    tour.index = len(tour.steps) - 1
    tour.next()                              # „Fertig“
    QTest.qWait(50)
    assert w._tour is None
    assert w.ui.sidebar.currentRow() == 1


@pytest.fixture
def packages_present(monkeypatch):
    """Wie auf einem fertig eingerichteten Rechner: die App springt beim
    Start selbst aufs Dashboard (muss VOR dem Fenster greifen)."""
    import main
    monkeypatch.setattr(main.VRApp, "are_critical_packages_missing", lambda self: False)


def test_startup_jump_runs_chain_exactly_once(packages_present, window, monkeypatch):
    import json
    import vr_optimize as vopt
    w = window
    w.installation_running = lambda: False
    calls = []
    monkeypatch.setattr(vopt, "pending_steps", lambda: [])
    w.maybe_offer_wayvr = lambda: calls.append("wayvr") or False
    w.maybe_offer_tour = lambda: calls.append("tour")
    with open(vopt.APP_CONFIG_FILE, "w") as fh:
        json.dump({}, fh)
    w.show()
    w.ui.sidebar.setCurrentRow(3)             # Nutzer klickt weg …
    w.ui.sidebar.setCurrentRow(1)             # … und wieder aufs Dashboard
    QTest.qWait(1500)
    assert calls == ["wayvr", "tour"]


class _Busy:
    def __init__(self):
        self.on = True

    def isRunning(self):
        return self.on


def test_no_chain_while_installation_runs(chain):
    """Installation laeuft (z. B. xrizer im Terminal): Dashboard-Klick startet
    nichts und merkt sich nichts. Ist sie fertig und das Dashboard offen,
    startet die Kette von selbst — genau einmal."""
    w, calls, state = chain
    state["installing"] = True
    w.ui.pages.setCurrentIndex(1)
    w.maybe_offer_vr_optimize()
    QTest.qWait(900)
    assert calls == [] and not w._optimize_checked
    state["installing"] = False
    w.first_run_after_install()               # Paketpruefung danach fertig
    w.first_run_after_install()               # zweite Pruefung: nichts doppelt
    QTest.qWait(1300)
    assert calls == ["wayvr", "tour"]


def test_no_auto_start_when_not_on_dashboard(chain):
    w, calls, _state = chain
    w.ui.pages.setCurrentIndex(0)             # Installations-Tab
    w.first_run_after_install()
    QTest.qWait(900)
    assert calls == [] and not w._optimize_checked


def test_no_chain_without_wivrn(chain):
    w, calls, _state = chain
    w.are_critical_packages_missing = lambda: True
    w.maybe_offer_vr_optimize()
    QTest.qWait(900)
    assert calls == [] and not w._optimize_checked


def test_tour_blocked_while_installation_runs(chain):
    w, _calls, state = chain
    state["installing"] = True
    w.start_tour()
    assert getattr(w, "_tour", None) is None


def test_installation_running_checks_workers():
    from tabs.first_run_mixin import FirstRunMixin

    class W(FirstRunMixin):
        pass
    w = W()
    assert not w.installation_running()
    for name in ("worker", "xrizer_worker", "_pkgcheck_worker"):
        busy = _Busy()
        setattr(w, name, busy)
        assert w.installation_running(), name
        busy.on = False
        assert not w.installation_running(), name


@pytest.mark.parametrize("lang,title", [("de", "Willkommen bei Yakuda Connect!"),
                                        ("en", "Welcome to Yakuda Connect!"),
                                        ("fr", "Bienvenue dans Yakuda Connect !")])
def test_welcome_text_in_every_language(window, lang, title):
    from translations import set_language
    set_language(lang)
    window._set_welcome_text()
    window.ui.retranslate_ui()
    text = window.ui.txt_free_info.toPlainText()
    assert window.ui.btn_welcome_toggle.text() == title
    assert "VR Central" not in text and title not in text      # nicht doppelt
    set_language("en")


def test_welcome_collapses_and_is_remembered(window):
    import json
    import paths
    ui = window.ui
    ui.btn_welcome_toggle.click()                 # zuklappen
    assert ui.txt_free_info.isHidden() and ui.btn_welcome_toggle.arrowType() == Qt.RightArrow
    with open(paths.config_file("config.json")) as fh:
        assert json.load(fh)["welcome_collapsed"] is True
    window.apply_loaded_settings()                # wie beim naechsten Start
    assert ui.txt_free_info.isHidden()
    ui.btn_welcome_toggle.click()                 # wieder auf
    assert not ui.txt_free_info.isHidden() and ui.btn_welcome_toggle.arrowType() == Qt.DownArrow


def test_installations_tab_klappt_und_zeigt_ganzen_text(window):
    from PySide6.QtWidgets import QScrollArea
    ui = window.ui
    assert ui.tab_installation.findChild(QScrollArea) is not None
    ui.apk_header.click()
    assert ui.btn_apk_install.parentWidget().isHidden()
    ui.apk_header.click()
    assert not ui.btn_apk_install.parentWidget().isHidden()
    ui.aur_help_header.click()
    assert ui.lbl_aur_help.isHidden()
    ui.aur_help_header.click()
    assert not ui.lbl_aur_help.isHidden()
    assert ui.btn_apk_meta.text()


def test_meta_store_knopf_oeffnet_store(window, monkeypatch):
    from PySide6.QtGui import QDesktopServices
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda u: opened.append(u)))
    window.ui.btn_apk_meta.click()
    assert "meta.com/experiences/wivrn" in opened[0].toString()
