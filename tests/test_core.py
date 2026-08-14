#!/usr/bin/env python3
"""
tests/test_core.py — Unit-Tests fuer die Kernbausteine
======================================================
Laufen OHNE Qt, ohne Headset, ohne Netz:

    pytest tests/

Warum diese Tests? Der Smoke-Test sagt "die App startet". Er sagt nicht,
ob beim Speichern Schluessel verloren gehen oder ob ein haengender Prozess
sauber abgebrochen wird — also genau das, was den Nutzer trifft und was man
von Hand kaum reproduziert.

Jeder Test bekommt ueber die Fixture ein eigenes HOME. Kein Test darf jemals
die echte Konfiguration des Entwicklers anfassen.
"""
import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))


@pytest.fixture(autouse=True)
def fake_home(tmp_path, monkeypatch):
    """Eigenes HOME pro Test — und die Pfad-Caches der Module zuruecksetzen."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    return tmp_path


# --------------------------------------------------------------------------- #
#  jsonio — atomares Schreiben und Zusammenfuehren
# --------------------------------------------------------------------------- #
def test_write_read_roundtrip(tmp_path):
    import jsonio
    target = tmp_path / "cfg.json"
    assert jsonio.write_json_atomic(str(target), {"a": 1, "b": "zwei"})
    assert jsonio.read_json(str(target)) == {"a": 1, "b": "zwei"}


def test_update_json_preserves_unknown_keys(tmp_path):
    """
    Der Kern der Config-Reparatur: fremde Schluessel duerfen NICHT verschwinden.
    Frueher rettete save_all_settings alte Schluessel ueber eine handgepflegte
    Liste — was dort fehlte, war beim naechsten Speichern still weg.
    """
    import jsonio
    target = tmp_path / "cfg.json"
    jsonio.write_json_atomic(str(target), {
        "bekannt": 1,
        "irgendein_neuer_key": {"tief": [1, 2, 3]},
    })
    jsonio.update_json(str(target), {"bekannt": 2})
    data = jsonio.read_json(str(target))
    assert data["bekannt"] == 2
    assert data["irgendein_neuer_key"] == {"tief": [1, 2, 3]}


def test_no_temp_files_left_behind(tmp_path):
    """Nach dem Schreiben darf keine .tmp-Datei uebrig bleiben."""
    import jsonio
    target = tmp_path / "cfg.json"
    jsonio.write_json_atomic(str(target), {"x": 1})
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_broken_json_is_quarantined_not_overwritten(tmp_path):
    """
    Eine kaputte Datei wird zur Seite gelegt (.broken), damit man im
    Supportfall noch hineinschauen kann — statt sie stumm zu ueberschreiben.
    """
    import jsonio
    target = tmp_path / "cfg.json"
    target.write_text("{ das ist kein JSON", encoding="utf-8")
    assert jsonio.read_json(str(target), default={"fallback": True}) == {"fallback": True}
    assert (tmp_path / "cfg.json.broken").exists()


def test_write_to_unwritable_path_returns_false(tmp_path):
    """Fehlschlag muss False liefern, nicht die App abschiessen."""
    import jsonio
    blocked = tmp_path / "nur_datei"
    blocked.write_text("x", encoding="utf-8")
    # Unterhalb einer DATEI kann kein Ordner angelegt werden.
    assert jsonio.write_json_atomic(str(blocked / "sub" / "cfg.json"), {"a": 1}) is False


# --------------------------------------------------------------------------- #
#  config_manager — Einstellungen speichern
# --------------------------------------------------------------------------- #
def test_save_all_settings_keeps_foreign_keys(tmp_path, monkeypatch):
    """
    Regressionstest fuer den urspruenglichen Bug: ein Schluessel, den
    save_all_settings gar nicht kennt, muss ein Speichern ueberleben.
    """
    import config_manager as cm
    import jsonio

    cfg = tmp_path / "config.json"
    monkeypatch.setattr(cm, "CONFIG_FILE", str(cfg))
    # WiVRn-Sync im Test abschalten — der schreibt fremde Dateien.
    monkeypatch.setattr(cm, "sync_with_wivrn", lambda *_a, **_k: None)

    jsonio.write_json_atomic(str(cfg), {
        "language": "de",
        "detected_games": ["438100"],
        "ein_key_den_niemand_kennt": 42,
    })

    cm.save_all_settings(True, False, False, "90", "2", [], setup_state=None)

    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["hand_tracking"] is True          # neu geschrieben
    assert data["language"] == "de"               # erhalten
    assert data["detected_games"] == ["438100"]   # erhalten
    assert data["ein_key_den_niemand_kennt"] == 42  # erhalten (frueher weg!)


def test_load_settings_fills_defaults(tmp_path, monkeypatch):
    """Fehlende Schluessel werden ergaenzt, damit Aufrufer kein None bekommen."""
    import config_manager as cm
    import jsonio

    cfg = tmp_path / "config.json"
    monkeypatch.setattr(cm, "CONFIG_FILE", str(cfg))
    jsonio.write_json_atomic(str(cfg), {"language": "de"})

    settings = cm.load_saved_settings()
    assert settings["language"] == "de"
    assert settings["refresh_rate"] == "90"
    assert settings["hand_tracking"] is False


# --------------------------------------------------------------------------- #
#  proc — externe Programme
# --------------------------------------------------------------------------- #
def test_missing_program_does_not_raise():
    """Fehlt ein optionales Werkzeug (playerctl, adb ...), darf die App
    nicht abstuerzen — es gibt nur einen Fehlercode."""
    import proc
    res = proc.run(["dieses-programm-gibt-es-nicht-12345"])
    assert res.returncode == proc.RC_NOT_FOUND
    assert proc.run_ok(["dieses-programm-gibt-es-nicht-12345"]) is False


def test_timeout_is_caught_not_raised():
    """
    Der eigentliche Punkt der Umstellung: ein haengender Aufruf gibt auf,
    statt die GUI einzufrieren ODER eine Ausnahme zu werfen.
    """
    import proc
    res = proc.run(["sleep", "10"], timeout=1)
    assert res.returncode == proc.RC_TIMEOUT


def test_output_of_returns_default_on_failure():
    import proc
    assert proc.output_of(["false"], default="leer") == "leer"
    assert proc.output_of(["echo", "hallo"]).strip() == "hallo"


def test_run_captures_stdout():
    import proc
    res = proc.run(["echo", "test123"])
    assert res.returncode == 0
    assert "test123" in res.stdout


# --------------------------------------------------------------------------- #
#  paths — XDG mit Rueckwaertskompatibilitaet
# --------------------------------------------------------------------------- #
def test_legacy_config_dir_wins(tmp_path, monkeypatch):
    """
    Existiert der alte Ordner ~/.config/yakuda-connect, muss er weiter
    benutzt werden — sonst waeren die Einstellungen bestehender Nutzer nach
    einem Update scheinbar verschwunden.
    """
    legacy = tmp_path / ".config" / "yakuda-connect"
    legacy.mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "woanders"))

    import importlib
    import paths
    importlib.reload(paths)          # HOME wird beim Import ausgewertet
    assert paths.config_root() == str(legacy)


def test_xdg_used_for_fresh_install(tmp_path, monkeypatch):
    """Ohne Altbestand gilt XDG_CONFIG_HOME."""
    xdg = tmp_path / "meine-configs"
    xdg.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))

    import importlib
    import paths
    importlib.reload(paths)
    assert paths.config_root() == str(xdg / "yakuda-connect")


# --------------------------------------------------------------------------- #
#  version — Konsistenz ueber alle Dateien
# --------------------------------------------------------------------------- #
def test_version_anchor_matches_version_module():
    """
    Der Anker in core/main.py muss zu core/version.py passen. Fehlt oder
    weicht er ab, finden alte Clients (bis v1.1.4) nie wieder ein Update.
    """
    import re
    import version
    text = (ROOT / "core" / "main.py").read_text(encoding="utf-8")
    m = re.search(r'APP_VERSION\s*=\s*"v?([^"]+)"', text)
    assert m, "APP_VERSION-Anker fehlt in core/main.py!"
    assert m.group(1) == version.VERSION


def test_pkgbuild_version_matches():
    import re
    import version
    pkgbuild = ROOT / "packaging" / "aur" / "PKGBUILD"
    m = re.search(r"^pkgver=(.+)$", pkgbuild.read_text(encoding="utf-8"), re.M)
    assert m and m.group(1).strip() == version.VERSION


def test_pkgver_has_no_dash():
    """Fehler Nr. 4 der Update-Anleitung: pkgver darf keinen Bindestrich
    enthalten (ein Alpha hiesse 1.1.5_alpha)."""
    import re
    pkgbuild = ROOT / "packaging" / "aur" / "PKGBUILD"
    m = re.search(r"^pkgver=(.+)$", pkgbuild.read_text(encoding="utf-8"), re.M)
    assert "-" not in m.group(1).strip()


# --------------------------------------------------------------------------- #
#  Sprachdateien (locales/*.json)
# --------------------------------------------------------------------------- #
def test_all_languages_have_same_keys():
    """
    Fehlt in einer Uebersetzung ein Schluessel, faellt tr() auf Englisch
    zurueck — die App bleibt benutzbar, aber die Stelle sieht falsch aus.
    Dieser Test macht solche Luecken bei einem Beitrag sofort sichtbar.
    """
    import json
    locales = ROOT / "locales"
    files = sorted(locales.glob("*.json"))
    assert files, "keine Sprachdateien in locales/ gefunden"

    reference = json.loads((locales / "en.json").read_text(encoding="utf-8"))
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        missing = set(reference) - set(data)
        extra = set(data) - set(reference)
        assert not missing, f"{path.name}: {len(missing)} Schluessel fehlen, z. B. {sorted(missing)[:5]}"
        assert not extra, f"{path.name}: unbekannte Schluessel {sorted(extra)[:5]}"


def test_placeholders_match_across_languages():
    """
    Platzhalter wie {name} oder {path} werden zur Laufzeit per .format()
    ersetzt. Wird einer in einer Uebersetzung vergessen oder verschrieben,
    stuerzt die App an genau dieser Stelle mit KeyError ab — oft erst Monate
    spaeter, wenn jemand die betroffene Meldung ausloest.
    """
    import json
    import re
    locales = ROOT / "locales"
    reference = json.loads((locales / "en.json").read_text(encoding="utf-8"))

    def placeholders(text):
        return set(re.findall(r"\{(\w+)\}", text)) if isinstance(text, str) else set()

    for path in sorted(locales.glob("*.json")):
        if path.name == "en.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, ref_text in reference.items():
            if key not in data:
                continue
            expected, actual = placeholders(ref_text), placeholders(data[key])
            assert expected == actual, (
                f"{path.name} / '{key}': Platzhalter weichen ab "
                f"(erwartet {sorted(expected)}, gefunden {sorted(actual)})")


def test_locales_are_shipped_by_packaging():
    """
    locales/ muss in AUR-Paket UND AppImage landen. Fehlt der Ordner, bricht
    translations.py beim Start ab — und zwar erst beim Nutzer, nicht hier.
    """
    pkgbuild = (ROOT / "packaging" / "aur" / "PKGBUILD").read_text(encoding="utf-8")
    assert "locales" in pkgbuild, "PKGBUILD kopiert locales/ nicht mit!"
    build_script = (ROOT / "build_appimage.sh").read_text(encoding="utf-8")
    assert "locales" in build_script, "build_appimage.sh kopiert locales/ nicht mit!"
