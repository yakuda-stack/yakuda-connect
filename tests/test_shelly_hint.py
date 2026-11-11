#!/usr/bin/env python3
"""Tests fuer den Shelly-Hinweis beim Update (core/main.py, ui/aur_helper_dialog.py):
paru zuerst, dann yay, zuletzt Shelly."""
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "core"))

import pytest  # noqa: E402
from PySide6.QtWidgets import QPushButton, QCheckBox  # noqa: E402

import appimage_installer as appimg  # noqa: E402
from test_exit_guard import window, _FakeProc, exit_guard, wivrn_server  # noqa: E402,F401


def _fake_dialog(monkeypatch, accepted, choice="", hide=False):
    import ui.aur_helper_dialog as mod

    class Fake:
        def __init__(self, parent=None):
            self.choice = choice
            self.hide_hint = hide

        def exec(self):
            return accepted

    monkeypatch.setattr(mod, "ShellyHintDialog", Fake)


@pytest.fixture
def flow(window, monkeypatch):
    started, launched, saved = [], [], []
    monkeypatch.setattr(window, "_start_helper_install",
                        lambda name: started.append(name) or True)
    monkeypatch.setattr(window, "_launch_update_worker", lambda m: launched.append(m))
    monkeypatch.setattr(appimg, "save_arch_setting", lambda k, v: saved.append((k, v)) or True)
    window._update_after_helper = False
    window._helper_chain = []
    return window, started, launched, saved


def test_dialog_shows_choices_links_and_commands(window):
    from ui.aur_helper_dialog import ShellyHintDialog
    dlg = ShellyHintDialog()
    buttons = [b.text() for b in dlg.findChildren(QPushButton)]
    assert len(buttons) == 4
    assert dlg.findChildren(QCheckBox)
    assert not dlg.hide_hint
    from PySide6.QtWidgets import QLabel
    text = " ".join(l.text() for l in dlg.findChildren(QLabel))
    for name in ("paru", "yay"):
        assert appimg.helper_url(name) in text
        assert f"sudo pacman -S --needed {name}" in text
        assert f"https://aur.archlinux.org/{name}.git" in text


def test_choose_paru_tries_yay_next(flow, monkeypatch):
    w, started, launched, saved = flow
    _fake_dialog(monkeypatch, 1, "paru")
    assert w._offer_helper_before_update() is True
    assert started == ["paru"]
    assert w._helper_chain == ["yay"]
    assert w._update_after_helper
    assert launched == []


def test_choose_yay_tries_paru_next(flow, monkeypatch):
    w, started, launched, saved = flow
    _fake_dialog(monkeypatch, 1, "yay")
    assert w._offer_helper_before_update() is True
    assert started == ["yay"]
    assert w._helper_chain == ["paru"]


def test_choose_shelly_continues_with_shelly(flow, monkeypatch):
    w, started, launched, saved = flow
    _fake_dialog(monkeypatch, 1, "shelly")
    assert w._offer_helper_before_update() is False
    assert started == []


def test_cancel_does_nothing(flow, monkeypatch):
    w, started, launched, saved = flow
    _fake_dialog(monkeypatch, 0, "", hide=True)
    assert w._offer_helper_before_update() is True
    assert started == [] and launched == [] and saved == []


def test_hide_checkbox_is_saved(flow, monkeypatch):
    w, started, launched, saved = flow
    _fake_dialog(monkeypatch, 1, "shelly", hide=True)
    w._offer_helper_before_update()
    assert saved == [(appimg.SHELLY_HINT_HIDDEN_KEY, True)]


def test_installed_helper_runs_the_update(flow):
    w, started, launched, saved = flow
    w._update_after_helper = True
    w._helper_chain = ["yay"]
    w._continue_update_after_helper("paru", True)
    assert launched == ["paru"]
    assert not w._update_after_helper and w._helper_chain == []


def test_failed_helper_tries_the_next_one(flow):
    w, started, launched, saved = flow
    w._update_after_helper = True
    w._helper_chain = ["yay"]
    w._continue_update_after_helper("paru", False)
    assert started == ["yay"]
    assert launched == []
    assert w._update_after_helper and w._helper_chain == []


def test_all_helpers_failed_falls_back_to_shelly(flow):
    w, started, launched, saved = flow
    w._update_after_helper = True
    w._helper_chain = []
    w._continue_update_after_helper("yay", False)
    assert started == []
    assert launched == ["shelly"]
    assert not w._update_after_helper
