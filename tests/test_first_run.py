#!/usr/bin/env python3
"""Tests fuer die Erst-Einrichtung (core/tabs/first_run_mixin.py):
Performance-Setup → WayVR → Tour, nacheinander und nie doppelt."""
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "core"))

import pytest  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from test_exit_guard import window, _FakeProc, exit_guard, wivrn_server  # noqa: E402,F401


@pytest.fixture
def chain(window, monkeypatch):
    import vr_optimize as vopt
    w = window
    w.are_critical_packages_missing = lambda: False
    calls = []
    monkeypatch.setattr(vopt, "pending_steps", lambda: [])
    state = {"wayvr_async": False}

    def fake_wayvr():
        calls.append("wayvr")
        return state["wayvr_async"]
    w.maybe_offer_wayvr = fake_wayvr
    w.maybe_offer_tour = lambda: calls.append("tour")
    w.resize(1200, 800)
    w.show()
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
