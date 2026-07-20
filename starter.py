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

from core.main import VRApp
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

if __name__ == "__main__":
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
