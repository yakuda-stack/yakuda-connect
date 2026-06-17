#!/bin/bash
# yakuda-connect — One-Line Installer
# Verwendung: bash <(curl -s https://raw.githubusercontent.com/yakuda-stack/yakuda-connect/main/install.sh)

set -e

APP="yakuda-connect"
INSTALL_DIR="/opt/yakuda-connect"
DESKTOP_FILE="/usr/share/applications/yakuda-connect.desktop"
ICON_DIR="/usr/share/icons/hicolor/256x256/apps"
BIN_LINK="/usr/local/bin/yakuda-connect"
REPO="https://github.com/yakuda-stack/yakuda-connect"
VERSION="1.0.0"

echo "=== yakuda-connect Installer v$VERSION ==="
echo ""

# Prüfen ob python3 vorhanden
if ! command -v python3 &>/dev/null; then
    echo "[Fehler] Python3 ist nicht installiert."
    exit 1
fi

# PySide6 prüfen
if ! python3 -c "import PySide6" &>/dev/null; then
    echo "[Info] PySide6 nicht gefunden..."
    if command -v yay &>/dev/null; then
        echo "[Info] Installiere via yay..."
        yay -S --noconfirm python-pyside6
    elif command -v pacman &>/dev/null; then
        echo "[Info] Installiere via pacman..."
        sudo pacman -S --noconfirm python-pyside6
    elif command -v pip &>/dev/null; then
        echo "[Info] Installiere via pip..."
        pip install PySide6 --break-system-packages
    else
        echo "[Fehler] Konnte PySide6 nicht installieren. Bitte manuell installieren."
        exit 1
    fi
fi

# Quellcode holen
echo "[1/4] Lade yakuda-connect herunter..."
TMP_DIR=$(mktemp -d)
curl -sL "$REPO/archive/refs/tags/v$VERSION.tar.gz" -o "$TMP_DIR/yakuda-connect.tar.gz"
tar -xzf "$TMP_DIR/yakuda-connect.tar.gz" -C "$TMP_DIR"
SRC_DIR="$TMP_DIR/yakuda-connect-$VERSION"

# Ins Installationsverzeichnis kopieren
echo "[2/4] Installiere nach $INSTALL_DIR ..."
sudo rm -rf "$INSTALL_DIR"
sudo cp -r "$SRC_DIR" "$INSTALL_DIR"
sudo chmod +x "$INSTALL_DIR/starter.py"

# Desktop-Eintrag + Icon
echo "[3/4] Erstelle Menü-Eintrag & Icon..."
sudo install -Dm644 "$INSTALL_DIR/assets/yakuda_icon.png" "$ICON_DIR/yakuda-connect.png"
sudo bash -c "cat > $DESKTOP_FILE" << EOF
[Desktop Entry]
Name=yakuda-connect
Comment=WiVRn Manager for Linux VR
Exec=$INSTALL_DIR/starter.py
Icon=yakuda-connect
Terminal=false
Type=Application
Categories=Utility;
StartupWMClass=yakuda-connect
EOF
sudo update-desktop-database /usr/share/applications 2>/dev/null || true

# Symlink für Terminal-Aufruf
echo "[4/4] Erstelle Terminal-Befehl..."
sudo ln -sf "$INSTALL_DIR/starter.py" "$BIN_LINK"

# Aufräumen
rm -rf "$TMP_DIR"

echo ""
echo "✔ yakuda-connect v$VERSION erfolgreich installiert!"
echo ""
echo "Starten:"
echo "  • Im Anwendungsmenü: nach 'yakuda-connect' suchen"
echo "  • Im Terminal: yakuda-connect"
