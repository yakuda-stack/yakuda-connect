# Entwickler-Notizen — yakuda-connect

Kurzüberblick über den Aufbau, vor allem über die Bausteine, die seit v1.1.5
dazugekommen sind. Wer etwas ändert, sollte die vier Regeln ganz unten kennen.

## Aufbau

```
starter.py              Einstiegspunkt: richtet Logging ein, startet VRApp
core/
  version.py            Versionsnummer (EINE Quelle der Wahrheit)
  paths.py              Pfade (XDG-konform, mit Alt-Ordner-Erkennung)
  logging_setup.py      Logging + Logdatei
  jsonio.py             JSON sicher lesen/schreiben (atomar)
  proc.py               externe Programme mit Zeitlimit aufrufen
  main.py               Hauptfenster: Installation, Dashboard, Streaming,
                        OpenXR, Autostart, Server
  tabs/
    games_mixin.py      Games-Tab (Steam-Scan, Kacheln, Proton, Start)
    tools_mixin.py      Tools-Tab (WayVR, VRCX, ProtonPlus, ...)
  games.py              Steam-Bibliothek und Spiele-Datenbank
  config_manager.py     Einstellungen + WiVRn-Sync
  backup_manager.py     VR-Umgebung sichern/wiederherstellen
  openxr_manager.py     OpenXR-Manifeste prüfen und reparieren
  ...
ui/ui_main.py           Aufbau der Oberfläche (Widgets, Layout)
locales/                Texte der Oberfläche (en.json, de.json)
tests/
  smoke.py              Startet die App wirklich, 11 Prüfungen
  test_core.py          16 Unit-Tests (ohne Qt)
scripts/bump_version.py Version an allen Stellen setzen
```

`VRApp` erbt von `GamesTabMixin` und `ToolsTabMixin`. Das sind **Mixins**,
keine eigenständigen Klassen: die Methoden arbeiten auf demselben `self` wie
vorher. Der Split diente nur der Übersicht — `main.py` hatte rund 3.600
Zeilen in einer Klasse. Attribute (`self._games_scan_worker`, …) werden
weiterhin in `VRApp.__init__` angelegt; wer in einem Mixin ein neues braucht,
legt es dort an.

## Die vier Regeln

**1. Externe Programme nur über `proc`.**

```python
import proc
if proc.run_ok(["pgrep", "wivrn-server"]):
    ...
text = proc.output_of(["wivrn-server", "--version"])
```

`proc.run` hat immer ein Zeitlimit und wirft nie — weder bei Timeout noch bei
fehlendem Programm. Ein `subprocess.run()` ohne `timeout=` lässt den
Smoke-Test fehlschlagen; das ist Absicht. Ohne Zeitlimit friert die Oberfläche
ein, sobald `pacman` an einer Sperrdatei hängt oder das Headset im Standby ist.

**2. JSON nur über `jsonio`.**

```python
from jsonio import read_json, update_json
data = read_json(pfad, default={})
update_json(pfad, {"key": wert})     # liest, ändert, schreibt atomar
```

Nie `json.dump` direkt in die Zieldatei: das kürzt sie zuerst auf null Bytes.
Ein Absturz in diesem Moment kostet den Nutzer seine Einstellungen — bei
WiVRns `config.json` sogar dessen Startfähigkeit. `update_json` erhält
außerdem unbekannte Schlüssel; genau daran krankte das Speichern vor v1.1.5.

**3. Kein stilles `except: pass`.**

```python
except Exception as exc:
    log.debug("was hier passierte: %s", exc)
```

Ein verschluckter Fehler kostet später eine Stunde Support, eine Logzeile
kostet nichts. Logger holen mit `from logging_setup import get_logger`.

**4. Neue Hintergrund-Threads in `VRApp._BACKGROUND_WORKERS` eintragen.**

Wird ein laufender `QThread` zerstört, beendet Qt den Prozess hart mit
SIGABRT — der Nutzer sieht beim Schließen einen Absturz. `closeEvent` wartet
auf alle dort eingetragenen Worker.

**5. Neue Texte gehören nach `locales/en.json` — und in jede weitere Sprache.**

`tr("mein_key")` im Code, der Text in die JSON-Dateien. Smoke-Test und
Unit-Tests prüfen, dass keine Sprache Schlüssel vermisst und dass Platzhalter
(`{name}`, `{path}`) in allen Sprachen identisch sind — ein vergessener
Platzhalter führt sonst zur Laufzeit zu einem `KeyError` an genau der Stelle.

Wird `locales/` beim Paketieren vergessen, startet die App nicht. PKGBUILD und
`build_appimage.sh` kopieren den Ordner mit; ein Test wacht darüber.

## Tests

```bash
QT_QPA_PLATFORM=offscreen python3 tests/smoke.py   # startet die App wirklich
python3 -m pytest tests/ -q                        # Unit-Tests, ohne Qt
ruff check core ui tests scripts                   # Linter
```

Der Smoke-Test ruft die Games- und Tools-Methoden **wirklich auf**, nicht nur
den Konstruktor. Das ist wichtig: diese Methoden laufen erst, wenn der Nutzer
den Tab öffnet — beim Mixin-Split fiel deshalb zunächst nicht auf, dass dort
Importe fehlten. Die App startete sauber und wäre erst beim Klick auf „Games"
abgestürzt.

Endet der Smoke-Test mit Exitcode 134 statt 0, läuft beim Schließen noch ein
Thread (siehe Regel 4).

## Release

Siehe `UPDATE-ANLEITUNG-yakuda-connect.md`. Kurz:

```bash
python3 scripts/bump_version.py 1.3.0    # setzt version.py, main.py, PKGBUILD
# CHANGELOG-Block schreiben, committen, taggen, pushen
bash build_appimage.sh                   # beide AppImage-Varianten
```

**`APP_VERSION` in `core/main.py` niemals entfernen.** Der Update-Checker
aller Clients bis v1.1.4 sucht per regulärem Ausdruck genau diese Zeile in der
von GitHub geladenen Datei. Fehlt sie, melden alle installierten Versionen für
immer „aktuell" und finden nie wieder ein Update. `bump_version.py` pflegt sie
mit, Smoke-Test und CI prüfen sie.

## Konfiguration und Log

```
~/.config/yakuda-connect/config/     Einstellungen
~/.cache/yakuda-connect/app.log      Log (rotierend, max. 1 MB, 3 Generationen)
```

`XDG_CONFIG_HOME`/`XDG_CACHE_HOME` werden berücksichtigt — außer der alte
Ordner `~/.config/yakuda-connect` existiert bereits, dann bleibt dieser in
Benutzung, damit bestehende Einstellungen nicht verlorengehen.

Mehr Details im Log: `YAKUDA_LOG_LEVEL=DEBUG yakuda-connect`
