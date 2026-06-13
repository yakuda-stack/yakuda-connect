#!/bin/bash
# yakuda-connect — One-Line Installer
# Verwendung: bash <(curl -s https://raw.githubusercontent.com/DEIN_USERNAME/yakuda-connect/main/install.sh)

set -e

INSTALL_DIR="/opt/yakuda-connect"
DESKTOP_FILE="/usr/share/applications/yakuda-connect.desktop"
BIN_LINK="/usr/local/bin/yakuda-connect"

echo "=== yakuda-connect Installer ==="
echo ""

# Abhängigkeit prüfen
if ! command -v python3 &>/dev/null; then
    echo "[Fehler] Python3 ist nicht installiert."
    exit 1
fi

if ! python3 -c "import PySide6" &>/dev/null; then
    echo "[Info] PySide6 nicht gefunden — installiere via yay..."
    yay -S --noconfirm python-pyside6
fi

# Ins Installationsverzeichnis kopieren
echo "[1/4] Kopiere Dateien nach $INSTALL_DIR ..."
sudo rm -rf "$INSTALL_DIR"
sudo cp -r "$(dirname "$0")" "$INSTALL_DIR"
sudo chmod +x "$INSTALL_DIR/starter.py"

# Desktop-Eintrag installieren
echo "[2/4] Erstelle Anwendungsmenü-Eintrag ..."
sudo cp "$INSTALL_DIR/yakuda-connect.desktop" "$DESKTOP_FILE"
sudo update-desktop-database /usr/share/applications 2>/dev/null || true

# Symlink für Terminal-Aufruf
echo "[3/4] Erstelle Befehl 'yakuda-connect' ..."
sudo ln -sf "$INSTALL_DIR/starter.py" "$BIN_LINK"

echo "[4/4] Fertig!"
echo ""
echo "Du kannst yakuda-connect jetzt:"
echo "  • Im Anwendungsmenü starten"
echo "  • Im Terminal mit: yakuda-connect"
