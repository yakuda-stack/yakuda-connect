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
    # Die Referenz MUSS gehalten werden: raeumt Python das QApplication-Objekt
    # ab, waehrend noch Widgets leben, stuerzt Qt ab. Deshalb kein '_' und
    # das noqa — ruff sieht nur, dass die Variable nicht gelesen wird.
    app = QApplication(sys.argv)  # noqa: F841

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
    import json as _json
    import translations
    src = " ".join(p.read_text() for p in
                   list((ROOT / "core").glob("*.py")) + list((ROOT / "core" / "tabs").glob("*.py"))
                   + list((ROOT / "ui").glob("*.py")))
    used = set(re.findall(r'tr\(\s*"([^"]+)"', src)) - {"games_toggle_<key>"}

    # Seit v1.1.5 stehen die Texte in locales/*.json statt in einem Dict im
    # Python-Code. Das wird hier direkt geladen statt per regulärem Ausdruck
    # geparst — dadurch prüft der Test wirklich das, was die App zur Laufzeit
    # sieht, und nicht eine Textform davon.
    locales_dir = ROOT / "locales"
    langs = {p.stem: _json.loads(p.read_text(encoding="utf-8"))
             for p in sorted(locales_dir.glob("*.json"))}
    check("Sprachdateien vorhanden", "en" in langs, f"gefunden: {sorted(langs)}")

    defined = set(langs.get("en", {}))
    missing = sorted(used - defined)
    check("Alle tr()-Keys definiert", not missing, str(missing[:5]))

    # Jede Sprache gegen Englisch (die Referenz) prüfen — funktioniert
    # automatisch auch für Sprachen, die später dazukommen.
    for code, data in sorted(langs.items()):
        if code == "en":
            continue
        only_en = sorted(defined - set(data))
        only_other = sorted(set(data) - defined)
        check(f"{code}.json vollständig", not only_en and not only_other,
              f"fehlt: {only_en[:3]} / unbekannt: {only_other[:3]}")

    print("\n[3] Sprachwechsel (fängt fehlende Attribute in retranslate_ui)")
    for lang in ("en", "de"):
        translations.set_language(lang)
        w.ui.retranslate_ui()
        check(f"retranslate_ui('{lang}')", True)

    print("\n[4] Tab-Logik wirklich aufrufen (Mixins aus core/tabs/)")
    # Warum das noetig ist: "VRApp() startet" prueft nur den Aufbau des
    # Fensters. Die Methoden des Games- und Tools-Tabs laufen erst, wenn der
    # Nutzer den Tab OEFFNET. Beim Aufteilen von main.py in Mixins fiel genau
    # deshalb nicht auf, dass dort Importe fehlten — die App startete sauber
    # und waere erst beim Klick auf "Games" mit NameError abgestuermmt.
    #
    # Modale Dialoge muessen zusaetzlich abgefangen werden: QMessageBox(self)
    # .exec() ist eine INSTANZ-Methode, die das Mocking der statischen
    # Methoden oben nicht erwischt — der Test bliebe daran haengen.
    from PySide6.QtWidgets import QDialog
    QMessageBox.exec = lambda self, *a, **k: QMessageBox.Ok
    QDialog.exec = lambda self, *a, **k: 0

    try:
        # 438100 = VRChat; ein erfundener Eintrag deckt die "ungetestet"-Spalte ab
        w.render_games_cards(["438100"], [{"appid": "1234", "name": "Testspiel"}])
        w._on_game_tile_clicked("438100")     # baut das Detailpanel auf
        w._collapse_detail()
        w.show_games_info()
        w._refresh_games_db_version()
        check("Games-Tab rendert", True)
    except Exception as exc:
        check("Games-Tab rendert", False, f"{type(exc).__name__}: {exc}")

    # Die drei Fix-Knoepfe im VRChat-Panel (v1.1.9). Sie entstehen dynamisch
    # aus game["fixes"] — verschwindet ein Eintrag aus der games.json oder
    # benennt jemand einen Locale-Schluessel um, faellt der Knopf lautlos weg
    # und niemand merkt es, weil die App weiterhin startet.
    try:
        from PySide6.QtWidgets import QPushButton, QCheckBox
        from translations import tr
        # Der Block oben hat das Panel absichtlich wieder eingeklappt
        # (_collapse_detail), damit auch dieser Pfad einmal laeuft. Fuer die
        # Inhaltspruefung muss es neu aufgebaut werden.
        w._on_game_tile_clicked("438100")
        panel = getattr(w, "_games_detail_widget", None)
        texts = " ".join(b.text() for b in panel.findChildren(QPushButton)) if panel else ""
        boxes = " ".join(c.text() for c in panel.findChildren(QCheckBox)) if panel else ""
        for label, needle in (("Picture Fix", tr("games_fix_pictures_btn")),
                              ("Videoplayer Fix", tr("games_fix_video_btn")),
                              ("Videoplayer Check", tr("games_fix_check_btn"))):
            check(f"VRChat-Knopf: {label}", needle in texts,
                  f"nicht im Panel gefunden (gefunden: {texts[:80]})")
        check("VRChat-Toggle: PROTON_LOG",
              tr("games_toggle_proton_log") in boxes,
              f"nicht gefunden (gefunden: {boxes[:80]})")
        # Der Autostart-Schalter ist entfernt (v1.1.9, unzuverlaessig).
        # Falls er je zurueckkehrt, soll das auffallen.
        check("Kein VRCVideoCacher-Autostart-Schalter mehr",
              "VRCVideoCacher" not in boxes, f"wieder da: {boxes[:80]}")
        # Handler muessen existieren, sonst knallt erst der Klick beim Nutzer
        for meth in ("create_vrchat_symlink", "show_vrchat_videoplayer_fix",
                     "run_vrchat_check", "_on_vrchat_check_done"):
            check(f"Handler {meth}", callable(getattr(w, meth, None)))
    except Exception as exc:
        check("VRChat-Fix-Knoepfe", False, f"{type(exc).__name__}: {exc}")

    # Die Diagnose selbst: darf auf JEDEM System durchlaufen, auch ohne Steam
    # und ohne VRChat (Build-Server!) — sie ist rein lesend.
    try:
        import vrchat_check
        results = vrchat_check.run_all()
        check("vrchat_check.run_all() laeuft durch",
              len(results) == len(vrchat_check.CHECKS),
              f"{len(results)} von {len(vrchat_check.CHECKS)} Ergebnissen")
        leaks = [r for r in results if re.search(r"\bip=|&sig=|expire=", r.get("detail", ""))]
        check("Diagnose gibt keine IP/Signatur aus", not leaks,
              f"verdaechtig: {leaks[:1]}")
    except Exception as exc:
        check("vrchat_check", False, f"{type(exc).__name__}: {exc}")

    try:
        w.check_tools_status()
        for key in list(w.ui.tool_cards)[:4]:
            w._apply_tool_status(key, {"installed": True, "version": "1.0"})
            w._set_tool_status(key, "Test")
            w._populate_method_combo(w.ui.tool_cards[key])
        check("Tools-Tab rendert", True)
    except Exception as exc:
        check("Tools-Tab rendert", False, f"{type(exc).__name__}: {exc}")

    # Hintergrund-Threads sauber auslaufen lassen: close() loest closeEvent()
    # aus, das auf alle Worker wartet. Ohne das endet der Prozess mit
    # SIGABRT (Exitcode 134) — und die CI waere rot, obwohl alle Pruefungen
    # bestanden haben. Zugleich ist das der einzige Test, der closeEvent
    # ueberhaupt durchlaeuft.
    w.close()

    print("\n[5] Version an allen Stellen gleich")
    # Faengt genau die beiden Fehler, die beim Release am teuersten sind:
    # PKGBUILD vergessen -> AUR baut den alten Tag; Anker in main.py vergessen
    # -> alte Clients (bis v1.1.4) finden nie wieder ein Update.
    import version as version_mod
    anchor = re.search(r'APP_VERSION\s*=\s*"v?([^"]+)"',
                       (ROOT / "core" / "main.py").read_text())
    check("APP_VERSION-Anker in main.py vorhanden", anchor is not None,
          "Ohne ihn sehen alte Clients nie wieder ein Update!")
    if anchor:
        check("Anker == core/version.py", anchor.group(1) == version_mod.VERSION,
              f"main.py={anchor.group(1)} vs version.py={version_mod.VERSION}")

    pkgbuild = ROOT / "packaging" / "aur" / "PKGBUILD"
    if pkgbuild.exists():
        m_pkg = re.search(r"^pkgver=(.+)$", pkgbuild.read_text(), re.M)
        check("PKGBUILD == core/version.py",
              bool(m_pkg) and m_pkg.group(1).strip() == version_mod.VERSION,
              f"PKGBUILD={m_pkg.group(1).strip() if m_pkg else '?'} vs {version_mod.VERSION}")

    print("\n[6] Sicherheitsnetze aktiv")
    # Ein subprocess.run ohne Zeitlimit friert die GUI ein, wenn pacman an
    # einer Lock-Datei haengt oder das Headset im Standby ist. Diese Pruefung
    # verhindert, dass so ein Aufruf spaeter unbemerkt wieder hereinrutscht.
    import ast
    missing = []
    for py in sorted((ROOT / "core").glob("*.py")) + sorted((ROOT / "ui").glob("*.py")):
        if py.name == "proc.py":
            continue
        for node in ast.walk(ast.parse(py.read_text())):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "run"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "subprocess"
                    and not any(k.arg == "timeout" for k in node.keywords)):
                missing.append(f"{py.name}:{node.lineno}")
    check("Kein subprocess.run ohne timeout", not missing, str(missing[:3]))

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
