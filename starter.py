#!/usr/bin/env python3
import sys
import os

# Prozessname für Linux-Taskmanager setzen (muss VOR QApplication passieren)
sys.argv[0] = "yakuda-connect"

# 1) setproctitle: ersetzt die komplette Kommandozeile (htop/btop-Detailansicht)
try:
    from setproctitle import setproctitle
    setproctitle("yakuda-connect")
except ImportError:
    pass

# 2) prctl: setzt den Kernel-Prozessnamen /proc/self/comm
#    (die Namens-Spalte in btop; max. 15 Zeichen — "yakuda-connect" hat 14)
try:
    import ctypes
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    libc.prctl(15, b"yakuda-connect", 0, 0, 0)  # 15 = PR_SET_NAME
except Exception:
    pass

# Füge das 'core'-Verzeichnis zum Python-Pfad hinzu
sys.path.append(os.path.join(os.path.dirname(__file__), 'core'))

# Logging als ERSTES einrichten — vor allen anderen Projekt-Importen.
# Grund: Module wie config_manager loggen bereits beim Import. Wird das Setup
# später gemacht, gehen genau die frühen Meldungen verloren, die bei
# Startproblemen am interessantesten sind.
from logging_setup import setup_logging, install_excepthook  # noqa: E402
_log = setup_logging()
install_excepthook()   # Abstürze landen im Log statt auf einer Konsole,
                       # die beim Start per Desktop-Icon gar nicht existiert.

from core.main import VRApp                       # noqa: E402
from PySide6.QtWidgets import QApplication        # noqa: E402
from PySide6.QtGui import QIcon                   # noqa: E402

if __name__ == "__main__":
    from version import APP_VERSION

    # --version / --selftest: kleine Kommandozeilenschalter, KEIN vollwertiges
    # CLI. --selftest wird von build_appimage.sh benutzt, um zu pruefen, ob das
    # gebaute Paket ueberhaupt hochfaehrt (Python da? PySide6 gebundelt? alle
    # Module importierbar?) — ohne dass ein Fenster aufgeht.
    if "--version" in sys.argv:
        print(f"yakuda-connect {APP_VERSION}")
        sys.exit(0)

    if "--selftest" in sys.argv:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QMessageBox

            # Ohne das haengt der Test: fehlen VR-Komponenten, zeigt VRApp
            # beim Start ein MODALES Fenster ("Components are missing") und
            # wartet auf einen Klick. Auf einem Build-Server klickt niemand.
            for _name in ("warning", "information", "critical"):
                setattr(QMessageBox, _name, staticmethod(lambda *a, **k: QMessageBox.Ok))
            QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

            app = QApplication([sys.argv[0]])
            VRApp()                   # baut die komplette UI auf
            print(f"selftest ok — yakuda-connect {APP_VERSION}")
            sys.exit(0)
        except Exception:
            _log.exception("Selbsttest fehlgeschlagen")
            print("selftest FEHLGESCHLAGEN — Details siehe Log", file=sys.stderr)
            sys.exit(1)

    _log.info("yakuda-connect %s startet (Python %s)",
              APP_VERSION, sys.version.split()[0])

    app = QApplication(sys.argv)
    app.setApplicationName("yakuda-connect")
    app.setApplicationDisplayName("yakuda-connect")
    app.setDesktopFileName("yakuda-connect")

    # Icon setzen — SVG (skaliert auf jeder Auflösung sauber)
    icon_path = os.path.join(os.path.dirname(__file__), "assets", "yakuda_icon.svg")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = VRApp()
    window.show()
    sys.exit(app.exec())
