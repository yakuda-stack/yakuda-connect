#!/usr/bin/env python3
"""
core/logging_setup.py — Zentrales Logging
=========================================
Vorher schrieb die App mit ``print()`` in die Konsole. Startet ein Nutzer sie
per Desktop-Icon (der Normalfall!), gibt es keine Konsole — die Ausgabe war
also genau dann weg, wenn man sie gebraucht haette: im Fehlerfall beim Nutzer.

Jetzt landet alles zusaetzlich in einer rotierenden Logdatei:

    ~/.cache/yakuda-connect/app.log       (aktuell, max. 1 MB)
    ~/.cache/yakuda-connect/app.log.1..3  (aeltere Laeufe)

Damit kann man im Support einfach sagen: "schick mir die Datei" — statt zu
erklaeren, wie man ein Terminal oeffnet.

Benutzung in einem Modul:

    from logging_setup import get_logger
    log = get_logger(__name__)
    log.info("Server gestartet")
    log.warning("pactl nicht gefunden — Mikrofonliste bleibt leer")
    log.exception("Konnte Config nicht schreiben")   # inkl. Traceback

Regel fuer neue ``except``-Bloecke: NIE stillschweigend ``pass``. Mindestens
``log.debug(...)``. Ein verschluckter Fehler kostet spaeter eine Stunde
Support, eine Logzeile kostet nichts.
"""
import logging
import logging.handlers
import os
import sys

import paths

_LOG_FORMAT = "%(asctime)s  %(levelname)-7s  %(name)-18s  %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def setup_logging(level=None, to_console=True):
    """
    Richtet das Wurzel-Logging ein. Mehrfachaufrufe sind ungefaehrlich
    (der zweite tut nichts) — praktisch fuer Tests, die Module einzeln laden.

    level:  Standard INFO. Ueber die Umgebungsvariable YAKUDA_LOG_LEVEL
            (z. B. DEBUG) kann der Nutzer im Supportfall mehr Details
            einschalten, ohne dass wir eine neue Version bauen muessen:

                YAKUDA_LOG_LEVEL=DEBUG yakuda-connect
    """
    global _configured
    if _configured:
        return logging.getLogger("yakuda")

    if level is None:
        env = os.environ.get("YAKUDA_LOG_LEVEL", "").strip().upper()
        level = getattr(logging, env, logging.INFO) if env else logging.INFO

    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(_LOG_FORMAT, _DATE_FORMAT)

    # --- Datei-Handler (rotierend) ---
    # Schlaegt das fehl (kein schreibbares HOME, volle Platte), soll die App
    # trotzdem starten — Logging ist Hilfsmittel, kein Kernfeature.
    try:
        os.makedirs(paths.cache_root(), exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            paths.log_file(), maxBytes=1_000_000, backupCount=3,
            encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except Exception as exc:  # noqa: BLE001 — bewusst breit, siehe oben
        print(f"[Logging] Logdatei nicht schreibbar: {exc}", file=sys.stderr)

    # --- Konsolen-Handler ---
    # Nuetzlich beim Entwickeln und wenn die App aus dem Terminal laeuft.
    if to_console:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    # Qt und urllib sind auf DEBUG sehr geschwaetzig — auf WARNING drosseln.
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _configured = True
    log = logging.getLogger("yakuda")
    log.info("=" * 60)
    log.info("Logging gestartet — Datei: %s", paths.log_file())
    return log


def install_excepthook():
    """
    Faengt Ausnahmen, die niemand behandelt hat, und schreibt sie ins Log
    statt sie auf einer nicht vorhandenen Konsole verpuffen zu lassen.
    Ohne das ist ein Absturz beim Nutzer voellig unsichtbar.
    """
    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.getLogger("yakuda").critical(
            "Unbehandelte Ausnahme", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = _hook


def get_logger(name: str = "yakuda"):
    """
    Logger fuer ein Modul. ``__name__`` ist hier oft 'main', 'games', ...
    — kurz genug fuers Log, daher keine Umbenennung.
    """
    if not _configured:
        setup_logging()
    return logging.getLogger(name)


def read_log_tail(max_bytes: int = 200_000) -> str:
    """
    Letzte Zeilen der Logdatei — fuer den 'Log kopieren'-Knopf.
    Begrenzt, damit die Zwischenablage bei einem lange laufenden Prozess
    nicht mit Megabytes geflutet wird.
    """
    path = paths.log_file()
    try:
        size = os.path.getsize(path)
        with open(path, encoding="utf-8", errors="replace") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
                fh.readline()  # angeschnittene erste Zeile verwerfen
            return fh.read()
    except FileNotFoundError:
        return "(noch keine Logdatei vorhanden)"
    except Exception as exc:  # noqa: BLE001
        return f"(Logdatei nicht lesbar: {exc})"
