#!/usr/bin/env python3
"""
tests/test_tools_desc_language.py — Tool-Beschreibungen folgen der Sprache
==========================================================================
Fehler bis v1.4.1: Die Tool-Karten wurden beim ersten Oeffnen des Tools-Tabs
immer mit ``tool["desc"]`` (Deutsch) gebaut — auch bei Englisch. Ausserdem
bekam Franzoesisch deutsche Texte, weil nur ``lang == "en"`` Englisch lieferte.

Jetzt laeuft alles ueber ``programs.tool_text()``:
Deutsch nur bei "de", sonst Englisch (Rueckfall: Deutsch).
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

from programs import tool_text  # noqa: E402

TOOL = {"desc": "Deutsch", "desc_eng": "English",
        "note": "Hinweis", "note_eng": "Note"}


def test_german_only_for_de():
    assert tool_text(TOOL, "desc", "de") == "Deutsch"
    assert tool_text(TOOL, "note", "de") == "Hinweis"


def test_english_for_en_and_other_languages():
    for lang in ("en", "fr", "xx"):
        assert tool_text(TOOL, "desc", lang) == "English"
        assert tool_text(TOOL, "note", lang) == "Note"


def test_falls_back_to_german_without_english():
    assert tool_text({"desc": "Nur Deutsch"}, "desc", "en") == "Nur Deutsch"
    assert tool_text({}, "note", "en") == ""


def test_card_build_uses_tool_text():
    """Die Karte darf nicht mehr hart tool["desc"] / tool["note"] nehmen."""
    src = (ROOT / "ui" / "ui_main.py").read_text(encoding="utf-8")
    assert 'QLabel(tool["desc"])' not in src
    assert 'QLabel(tool["note"])' not in src
    assert 'tool_text(tool, "desc"' in src


def test_every_tool_has_english_description():
    data = json.loads((ROOT / "config" / "tools.json").read_text(encoding="utf-8"))
    missing = [t["key"] for t in data.get("apps", []) + data.get("osc", [])
               if t.get("desc") and not t.get("desc_eng")]
    assert not missing, missing
