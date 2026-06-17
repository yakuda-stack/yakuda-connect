#!/usr/bin/env python3
import sys
import os

# Prozessname für Linux-Taskmanager setzen (muss VOR QApplication passieren)
sys.argv[0] = "yakuda-connect"

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

    # Icon setzen — relativ zum starter.py Verzeichnis
    icon_path = os.path.join(os.path.dirname(__file__), "assets", "yakuda_icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = VRApp()
    window.show()
    sys.exit(app.exec())
