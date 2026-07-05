#!/bin/bash
# yakuda-connect — Installer & Updater (Arch-basierte Systeme)
#
# Installieren ODER aktualisieren mit EINEM Befehl:
#   bash <(curl -s https://raw.githubusercontent.com/yakuda-stack/yakuda-connect/main/install.sh)
#
# Re-Run = Update: holt den aktuellen main-Stand und ersetzt /opt/yakuda-connect.
# Deine Einstellungen unter ~/.config/yakuda-connect bleiben unangetastet.
set -e

APP="yakuda-connect"
INSTALL_DIR="/opt/yakuda-connect"
DESKTOP_FILE="/usr/share/applications/yakuda-connect.desktop"
ICON_DIR="/usr/share/icons/hicolor/256x256/apps"
BIN_LINK="/usr/local/bin/yakuda-connect"
REPO="https://github.com/yakuda-stack/yakuda-connect"
BRANCH="main"

# Installation oder Update?
if [ -d "$INSTALL_DIR" ]; then
    MODE="Aktualisiere"
else
    MODE="Installiere"
fi
echo "=== yakuda-connect: $MODE ==="
echo ""

# --- Grundwerkzeuge pruefen ---
if ! command -v git &>/dev/null; then
    echo "[Info] git wird benoetigt – installiere es..."
    sudo pacman -S --needed --noconfirm git
fi
if ! command -v python3 &>/dev/null; then
    echo "[Fehler] Python3 ist nicht installiert."
    exit 1
fi

# --- PySide6 sicherstellen ---
if ! python3 -c "import PySide6" &>/dev/null; then
    echo "[Info] PySide6 nicht gefunden – installiere es..."
    if command -v pacman &>/dev/null; then
        sudo pacman -S --needed --noconfirm base-devel
        sudo pacman -S --needed --noconfirm pyside6
    else
        echo "[Fehler] Kein pacman gefunden. Dieser Installer ist fuer Arch-basierte"
        echo "         Systeme (Arch, CachyOS, EndeavourOS, Manjaro)."
        exit 1
    fi
fi

# --- Quellcode holen (immer aktueller main-Branch) ---
echo "[1/4] Lade aktuellen Stand herunter..."
TMP_DIR="$(mktemp -d)"
git clone --depth 1 --branch "$BRANCH" "$REPO.git" "$TMP_DIR/src"
SRC_DIR="$TMP_DIR/src"
NEW_VER="$(git -C "$SRC_DIR" rev-parse --short HEAD 2>/dev/null || echo '?')"

# --- Ins Installationsverzeichnis kopieren (Code ersetzen, Configs bleiben separat) ---
echo "[2/4] $MODE nach $INSTALL_DIR  (Version: $NEW_VER) ..."
sudo rm -rf "$INSTALL_DIR"
sudo cp -r "$SRC_DIR" "$INSTALL_DIR"
sudo rm -rf "$INSTALL_DIR/.git"

# --- Wrapper-Startbefehl (cd ins Verzeichnis, dann starten) ---
sudo tee "$BIN_LINK" >/dev/null <<'LAUNCH'
#!/bin/sh
cd /opt/yakuda-connect || exit 1
exec python starter.py "$@"
LAUNCH
sudo chmod 755 "$BIN_LINK"

# --- Desktop-Eintrag + Icon ---
echo "[3/4] Aktualisiere Menue-Eintrag & Icon..."
SVG_ICON_DIR="/usr/share/icons/hicolor/scalable/apps"
if [ -f "$INSTALL_DIR/assets/yakuda_icon.svg" ]; then
    sudo install -Dm644 "$INSTALL_DIR/assets/yakuda_icon.svg" "$SVG_ICON_DIR/yakuda-connect.svg"
    # Altes PNG-Icon aus frueheren Versionen entfernen (sonst gewinnt es je nach Theme)
    sudo rm -f "$ICON_DIR/yakuda-connect.png"
    ICON="yakuda-connect"
elif [ -f "$INSTALL_DIR/assets/yakuda_icon.png" ]; then
    sudo install -Dm644 "$INSTALL_DIR/assets/yakuda_icon.png" "$ICON_DIR/yakuda-connect.png"
    ICON="yakuda-connect"
else
    ICON="applications-games"
fi
sudo gtk-update-icon-cache -f /usr/share/icons/hicolor 2>/dev/null || true
sudo tee "$DESKTOP_FILE" >/dev/null <<DESK
[Desktop Entry]
Name=yakuda-connect
Comment=WiVRn Manager for Linux VR
Exec=$BIN_LINK
Icon=$ICON
Terminal=false
Type=Application
Categories=Game;Utility;
StartupWMClass=yakuda-connect
DESK
sudo update-desktop-database /usr/share/applications 2>/dev/null || true

# --- Aufraeumen ---
echo "[4/4] Raeume auf..."
rm -rf "$TMP_DIR"

echo ""
echo "[OK] yakuda-connect ist auf Version $NEW_VER ($MODE abgeschlossen)."
echo ""
echo "Starten:"
echo "  - Im Anwendungsmenue: nach 'yakuda-connect' suchen"
echo "  - Im Terminal: yakuda-connect"
