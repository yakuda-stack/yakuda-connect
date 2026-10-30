#!/usr/bin/env python3
"""Tests fuer die App-Tour (core/tour_steps.py, ui/tour.py, tour_mixin)."""
import json
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "core"))

from tour_steps import STEPS  # noqa: E402
from test_exit_guard import window, _FakeProc, exit_guard, wivrn_server  # noqa: E402,F401


def test_every_step_has_texts_in_all_languages():
    for lang in ("de", "en", "fr"):
        with open(os.path.join(HERE, "..", "locales", f"{lang}.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        for step in STEPS:
            for part in ("title", "text"):
                assert f"tour_{step['id']}_{part}" in data, (lang, step["id"], part)
            if step.get("action"):
                assert f"tour_action_{step['action']}" in data


def test_tour_walks_all_steps(window):
    from PySide6.QtWidgets import QApplication
    w = window
    w.are_critical_packages_missing = lambda: False
    w.resize(1400, 900)
    w.show()
    w.start_tour()
    tour = w._tour
    seen = []
    for i, step in enumerate(STEPS):
        tour._focus_target()
        QApplication.processEvents()
        if step["target"] is not None:
            assert tour._target is not None, step["id"]
            assert tour.marker.isVisible() and tour.frame.isVisible(), step["id"]
        assert tour.card.isVisible()
        card = tour.card.geometry()
        assert w.rect().contains(card), step["id"]
        seen.append(step["id"])
        if i < len(STEPS) - 1:
            tour.next()
    tour.next()                               # „Fertig“
    QApplication.processEvents()
    assert w._tour is None
    assert len(seen) == len(STEPS)


def test_language_flags_switch_app_language(window):
    from PySide6.QtWidgets import QApplication
    from translations import get_language, tr
    w = window
    w.are_critical_packages_missing = lambda: False
    w.resize(1400, 900)
    w.show()
    w.start_tour()
    card = w._tour.card
    assert card.lang_row.isVisible() and not card.btn_action.isVisible()
    card.lang_buttons["fr"].click()
    QApplication.processEvents()
    assert get_language() == "fr"
    assert w._tour.card.lbl_title.text() == tr("tour_intro_title")
    assert w._tour.card.lang_buttons["fr"].isChecked()
    w._tour.card.lang_buttons["de"].click()
    assert get_language() == "de"
    w._tour.stop()


def test_games_step_shows_wide_image():
    from tour_steps import STEPS
    from ui.tour import step_image
    games = next(s for s in STEPS if s["id"] == "games")
    assert step_image(games).endswith(os.path.join("tour", "games.png"))
