#!/usr/bin/env python3
"""
tests/smoke.py — Startprüfung für yakuda-connect
================================================
Startet die komplette App ohne Bildschirm und ohne Headset und prüft, dass
sie hochfährt und die UI konsistent ist.

    QT_QPA_PLATFORM=offscreen python3 tests/smoke.py

Warum das nötig ist:
    'python -m py_compile' prüft nur die SYNTAX. Fehler wie ein zu spät
    gesetztes Attribut, ein Signal auf eine gelöschte Methode oder ein
    fehlender tr()-Key knallen erst zur LAUFZEIT — also erst, wenn man die
    App wirklich startet.

Läuft NICHT im Betrieb mit: Diese Datei wird von der App nirgends importiert
und ist reines Entwickler-Werkzeug. Sie kostet zur Laufzeit exakt nichts.

Was sie NICHT kann:
    VR-Rendering, WayVR-XML, echte Hardware. Sie sagt "die App startet und
    die UI steht" — nicht "es sieht gut aus".
"""
import os
import re
import sys
import pathlib
import tempfile
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "ui"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_fails = []
_checks = 0


def check(name, ok, detail=""):
    global _checks
    _checks += 1
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}{(' — ' + detail) if detail and not ok else ''}")
    if not ok:
        _fails.append(name)


def main():
    # Eigenes HOME: der Test darf niemals die echte Config anfassen
    fake_home = tempfile.mkdtemp(prefix="yakuda-smoke-")
    os.environ["HOME"] = fake_home
    print(f"Test-HOME: {fake_home}\n")

    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication(sys.argv)

    # Modale Dialoge blockieren ewig, weil hier niemand klickt.
    # Ohne dieses Mocking bleibt der Test am "Components are missing"-Fenster
    # haengen — auf einem Build-Server gibt es keinen Nutzer.
    for m in ("warning", "information", "critical"):
        setattr(QMessageBox, m, staticmethod(lambda *a, **k: QMessageBox.Ok))
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

    print("[1] App starten")
    from main import VRApp
    w = VRApp()
    check("VRApp() startet", True)

    print("\n[2] Übersetzungen")
    import translations
    src = " ".join(p.read_text() for p in
                   list((ROOT / "core").glob("*.py")) + list((ROOT / "ui").glob("*.py")))
    used = set(re.findall(r'tr\(\s*"([^"]+)"', src)) - {"games_toggle_<key>"}
    tf = (ROOT / "core" / "translations.py").read_text()
    defined = set(re.findall(r'^\s{8}"([^"]+)":', tf, re.M))
    missing = sorted(used - defined)
    check("Alle tr()-Keys definiert", not missing, str(missing[:5]))

    en = set(re.findall(r'"([^"]+)":', re.search(r'"en"\s*:\s*\{(.*?)\n    \},', tf, re.S).group(1)))
    de = set(re.findall(r'"([^"]+)":', re.search(r'"de"\s*:\s*\{(.*?)\n    \},?', tf, re.S).group(1)))
    check("EN/DE symmetrisch", en == de, f"nur EN: {sorted(en-de)[:3]} / nur DE: {sorted(de-en)[:3]}")

    print("\n[3] Sprachwechsel (fängt fehlende Attribute in retranslate_ui)")
    for lang in ("en", "de"):
        translations.set_language(lang)
        w.ui.retranslate_ui()
        check(f"retranslate_ui('{lang}')", True)

    print("\n" + "=" * 52)
    if _fails:
        print(f"FEHLGESCHLAGEN: {len(_fails)}/{_checks}")
        for f in _fails:
            print(f"  - {f}")
        return 1
    print(f"SMOKE-TEST BESTANDEN ({_checks} Prüfungen)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
