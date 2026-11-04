#!/usr/bin/env python3
"""Tests fuer die Einmal-Frage im Controls-Tab (controls_setup_mixin) und
ihr Zusammenspiel mit Tour und Erst-Einrichtung."""
import json
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "core"))

import pytest  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from test_exit_guard import window, _FakeProc, exit_guard, wivrn_server  # noqa: E402,F401


@pytest.fixture
def ctl(window, monkeypatch):
    import vr_optimize as vopt
    from ui import controls_setup_dialog as dlgmod
    w = window
    w.installation_running = lambda: False
    w.are_critical_packages_missing = lambda: False
    with open(vopt.APP_CONFIG_FILE, "w") as fh:
        json.dump({}, fh)
    w._controls_setup_checked = False
    shown, installed = [], []
    answer = {"choice": dlgmod.INSTALL, "keys": ["xrbinder", "obah"]}

    def fake_exec(self):
        shown.append([k for k, *_ in self._items])
        self.choice = answer["choice"]
        return 1
    orig_init = dlgmod.ControlsSetupDialog.__init__

    def init(self, parent, items):
        self._items = items
        orig_init(self, parent, items)
    monkeypatch.setattr(dlgmod.ControlsSetupDialog, "__init__", init)
    monkeypatch.setattr(dlgmod.ControlsSetupDialog, "exec", fake_exec)
    monkeypatch.setattr(dlgmod.ControlsSetupDialog, "selected", lambda self: answer["keys"])
    w.controls_install = lambda keys: installed.append(list(keys))
    w.controls_setup_items = lambda: [("xrbinder", "xrBinder", "", False, True),
                                      ("obah", "obah", "", False, True),
                                      ("xr-hotas", "XR HOTAS", "", False, False)]
    w.resize(1200, 800)
    w.show()
    QTest.qWait(50)
    return w, shown, installed, answer


def _open_controls(w):
    w.ui.pages.setCurrentIndex(w._controls_tab_index())
    w.maybe_offer_controls_setup()


def test_first_visit_asks_and_installs(ctl):
    import vr_optimize as vopt
    w, shown, installed, _a = ctl
    _open_controls(w)
    _open_controls(w)                           # zweiter Klick: nichts doppelt
    QTest.qWait(700)
    assert len(shown) == 1 and installed == [["xrbinder", "obah"]]
    with open(vopt.APP_CONFIG_FILE) as fh:
        assert json.load(fh).get("controls_setup_asked")
    w._controls_setup_checked = False
    _open_controls(w)                           # schon beantwortet
    QTest.qWait(500)
    assert len(shown) == 1


def test_later_asks_again_next_start(ctl):
    from ui.controls_setup_dialog import LATER
    w, shown, installed, answer = ctl
    answer["choice"] = LATER
    _open_controls(w)
    QTest.qWait(600)
    _open_controls(w)
    QTest.qWait(600)
    assert len(shown) == 1 and installed == []  # diese Sitzung nicht mehr
    w._controls_setup_checked = False           # „naechster Start“
    _open_controls(w)
    QTest.qWait(600)
    assert len(shown) == 2


def test_never_asks_again(ctl):
    from ui.controls_setup_dialog import NEVER
    w, shown, installed, answer = ctl
    answer["choice"] = NEVER
    _open_controls(w)
    QTest.qWait(600)
    w._controls_setup_checked = False
    _open_controls(w)
    QTest.qWait(600)
    assert len(shown) == 1 and installed == []


def test_no_popup_during_tour(ctl):
    w, shown, _i, _a = ctl
    w._tour = object()                          # Tour wechselt selbst auf den Tab
    _open_controls(w)
    QTest.qWait(600)
    assert shown == [] and not w._controls_setup_checked
    w._tour = None
    _open_controls(w)                           # spaeter echter Besuch
    QTest.qWait(600)
    assert len(shown) == 1


def test_tour_starting_while_popup_pending(ctl):
    w, shown, _i, _a = ctl
    _open_controls(w)                           # Frage geplant …
    w._tour = object()                          # … dann startet die Tour
    QTest.qWait(700)
    assert shown == [] and not w._controls_setup_checked
    w._tour = None


def test_no_popup_during_first_run_or_install(ctl):
    w, shown, _i, _a = ctl
    w._first_run_busy = True
    _open_controls(w)
    QTest.qWait(500)
    w._first_run_busy = False
    w.installation_running = lambda: True
    _open_controls(w)
    QTest.qWait(500)
    assert shown == [] and not w._controls_setup_checked


def test_left_tab_before_popup(ctl):
    w, shown, _i, _a = ctl
    _open_controls(w)
    w.ui.pages.setCurrentIndex(1)               # sofort wieder weg
    QTest.qWait(600)
    assert shown == [] and not w._controls_setup_checked


def test_nothing_missing_no_popup(ctl):
    import vr_optimize as vopt
    w, shown, _i, _a = ctl
    w.controls_setup_items = lambda: [("xrbinder", "xrBinder", "", True, True),
                                      ("obah", "obah", "", True, True)]
    _open_controls(w)
    QTest.qWait(600)
    assert shown == []
    with open(vopt.APP_CONFIG_FILE) as fh:
        assert json.load(fh).get("controls_setup_asked")


def test_dialog_widget(qapp):
    from ui.controls_setup_dialog import INSTALL, ControlsSetupDialog
    d = ControlsSetupDialog(None, [("xrbinder", "xrBinder", "Deadzone", False, True),
                                   ("obah", "obah", "SteamVR", True, True),
                                   ("xr-hotas", "XR HOTAS", "Flug", False, False)])
    assert set(d.checks) == {"xrbinder", "xr-hotas"}        # obah schon installiert
    assert d.selected() == ["xrbinder"]
    d.checks["xrbinder"].setChecked(False)
    assert not d.btn_install.isEnabled()
    d.checks["xr-hotas"].setChecked(True)
    d.btn_install.click()
    assert d.choice == INSTALL and d.selected() == ["xr-hotas"]
    d.deleteLater()


def test_controls_install_order_and_xrbinder_last():
    """Fehlende Werkzeuge nacheinander, Installiertes nur einschalten,
    xrBinder erst ganz am Ende — und nur, wenn gewaehlt."""
    from tabs.controls_setup_mixin import ControlsSetupMixin

    class UI:
        controls_rows = {"xr-hotas": {}, "obah": {}}
        tool_cards = {"xr-hotas": {"methods": ["yay"]}, "obah": {"methods": ["yay"]}}
        xrbinder_card = None

    class W(ControlsSetupMixin):
        def __init__(self):
            self.ui = UI()
            self.log = []
            self._controls_pending = set()
            self.installed = {"obah"}

        def _control_installed(self, k):
            return k in self.installed

        def _control_tool(self, k):
            return {"name": k}

        def _set_control_toggle(self, k, on):
            self.log.append(("toggle", k))

        def _save_control_state(self, k, on):
            pass

        def _render_control(self, k, inst, installing=False):
            pass

        def _start_control_install(self, k, method):
            self.log.append(("install", k, method))
            self._controls_pending.add(k)

        def _install_all_xrbinder(self):
            self.log.append("xrbinder")

    w = W()
    w.controls_install(["xrbinder", "obah", "xr-hotas"])
    assert ("toggle", "obah") in w.log and ("install", "xr-hotas", "yay") in w.log
    assert "xrbinder" not in w.log                   # wartet auf HOTAS
    w._controls_pending.clear()
    w._install_all_next()                            # HOTAS fertig
    assert w.log[-1] == "xrbinder" and w._install_all_queue is None

    w2 = W()
    w2.installed = {"obah", "xr-hotas"}
    w2.controls_install(["obah"])
    assert "xrbinder" not in w2.log
