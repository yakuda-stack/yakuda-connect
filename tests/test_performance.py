#!/usr/bin/env python3
"""Tests fuer die Performance-Aenderungen (Start ohne Einfrieren, weniger Neu-Polieren)."""
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "core"))


def test_set_style_only_when_changed(qapp):
    from PySide6.QtWidgets import QLabel

    from ui import theme
    w = QLabel()
    assert theme.set_style_if_changed(w, "color: red;")
    assert not theme.set_style_if_changed(w, "color: red;")
    assert theme.set_style_if_changed(w, "")


def test_apply_to_app_skips_identical_and_adds_extra(qapp):
    from PySide6.QtWidgets import QApplication

    from ui import theme
    app = QApplication.instance()
    old = app.styleSheet()
    try:
        theme.remember_app_base("QLabel { color: #d8dee9; }")
        app.setStyleSheet(theme.tint("QLabel { color: #d8dee9; }", allow_opacity=False))
        assert not theme.apply_to_app(app)                    # nichts zu tun
        assert theme.apply_to_app(app, "QFrame { border: 0; }")
        assert app.styleSheet().endswith("QFrame { border: 0; }")
        assert not theme.apply_to_app(app, "QFrame { border: 0; }")
    finally:
        theme.remember_app_base(None)
        app.setStyleSheet(old)


def test_no_wheel_without_app_filter(qapp):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication, QComboBox

    from ui import no_wheel
    combo = QComboBox()                         # schon VOR install() erzeugt
    combo.addItems(["a", "b", "c"])
    no_wheel.install(QApplication.instance())
    ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
                     Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(combo, ev)
    assert combo.currentIndex() == 0
    assert not ev.isAccepted()                  # geht an das Elternfenster weiter


def test_package_check_never_blocks(qapp, monkeypatch):
    """Laeuft schon eine Pruefung, wird vorgemerkt statt gewartet (kein wait())."""
    import main as m

    class Busy:
        def isRunning(self):
            return True

        def wait(self, *_a):
            raise AssertionError("wait() blockiert die Oberflaeche")

    class Fake:
        prog_labels = {}
        _pkgcheck_worker = Busy()

        def _install_method(self):
            return "pacman"

        def _package_groups_for(self, method):
            return {}

    f = Fake()
    m.VRApp.check_system_packages(f)
    assert f._pkgcheck_again is True
    started = []
    f.check_system_packages = lambda: started.append(1)
    m.VRApp._on_package_check_finished(f)
    assert started == [1] and f._pkgcheck_again is False


def test_no_recheck_after_close(qapp):
    import main as m

    class Fake:
        _exit_cleanup_done = True
        _pkgcheck_again = True

        def check_system_packages(self):
            raise AssertionError("nach dem Schliessen kein neuer Thread")

    f = Fake()
    m.VRApp._on_package_check_finished(f)
    assert f._pkgcheck_again is False
