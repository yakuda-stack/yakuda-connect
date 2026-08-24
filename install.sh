#!/bin/bash
# yakuda-connect — Installer & Updater (Arch, Fedora, Debian/Ubuntu, openSUSE)
#
# Installieren ODER aktualisieren mit EINEM Befehl:
#   bash <(curl -s https://raw.githubusercontent.com/yakuda-stack/yakuda-connect/main/install.sh)
#
# Re-Run = Update: holt den aktuellen main-Stand und ersetzt /opt/yakuda-connect.
# Deine Einstellungen unter ~/.config/yakuda-connect bleiben unangetastet.
set -e

INSTALL_DIR="/opt/yakuda-connect"
VENV_DIR="/opt/yakuda-connect-venv"   # nur Fallback, wenn es kein Distro-PySide6 gibt
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

# --------------------------------------------------------------------------- #
#  Paketmanager erkennen
#
#  Die App selbst kann Arch (yay/paru) UND Fedora (dnf) — der Installer konnte
#  bisher nur pacman und ist auf allem anderen mit
#  "pacman: command not found" ausgestiegen. Genau das behebt dieser Block.
# --------------------------------------------------------------------------- #
if command -v pacman &>/dev/null; then
    PM="pacman"; DISTRO_NAME="Arch-basiert"
elif command -v dnf &>/dev/null; then
    PM="dnf";    DISTRO_NAME="Fedora-basiert"
elif command -v apt-get &>/dev/null; then
    PM="apt";    DISTRO_NAME="Debian/Ubuntu-basiert"
elif command -v zypper &>/dev/null; then
    PM="zypper"; DISTRO_NAME="openSUSE"
else
    PM="unknown"; DISTRO_NAME="unbekannt"
fi
echo "[Info] Erkanntes System: $DISTRO_NAME (Paketmanager: $PM)"

# Pakete mit dem erkannten Paketmanager installieren.
# Gibt den Exit-Code zurueck, statt das Skript zu beenden — der Aufrufer
# entscheidet, ob ein Fehlschlag toedlich ist oder ob es einen Plan B gibt.
pm_install() {
    case "$PM" in
        pacman) sudo pacman -S --needed --noconfirm "$@" ;;
        dnf)    sudo dnf install -y "$@" ;;
        apt)    sudo apt-get update -qq && sudo apt-get install -y "$@" ;;
        zypper) sudo zypper --non-interactive install "$@" ;;
        *)      return 1 ;;
    esac
}

# --- Grundwerkzeuge pruefen ---
if ! command -v git &>/dev/null; then
    echo "[Info] git wird benoetigt – installiere es..."
    if ! pm_install git; then
        echo "[Fehler] git konnte nicht automatisch installiert werden."
        echo "         Bitte git von Hand installieren und das Skript erneut starten."
        exit 1
    fi
fi
if ! command -v python3 &>/dev/null; then
    echo "[Fehler] Python3 ist nicht installiert."
    case "$PM" in
        pacman) echo "         Arch:     sudo pacman -S python" ;;
        dnf)    echo "         Fedora:   sudo dnf install python3" ;;
        apt)    echo "         Ubuntu:   sudo apt install python3" ;;
        zypper) echo "         openSUSE: sudo zypper install python3" ;;
    esac
    exit 1
fi

# Standard-Interpreter. Wird nur dann auf das venv umgebogen, wenn PySide6
# nicht aus den Distro-Repos kommt (siehe unten).
PY_BIN="$(command -v python3)"

# --------------------------------------------------------------------------- #
#  PySide6 sicherstellen
#
#  Wichtig: NICHT nur "import PySide6" pruefen. Debian/Ubuntu splittet PySide6
#  in Einzelpakete auf — dort kann der Basis-Import klappen, waehrend
#  QtWidgets fehlt. Deshalb wird gegen die Module geprueft, die die App
#  wirklich importiert.
# --------------------------------------------------------------------------- #
have_pyside() {
    "$PY_BIN" -c "import PySide6.QtWidgets, PySide6.QtGui, PySide6.QtCore" &>/dev/null
}

if ! have_pyside; then
    echo "[Info] PySide6 nicht gefunden – installiere es..."
    case "$PM" in
        pacman)
            pm_install base-devel || true
            pm_install pyside6 || true
            ;;
        dnf)
            # Fedora/Nobara: ein Sammelpaket, enthaelt alle Qt-Module.
            pm_install python3-pyside6 || true
            ;;
        apt)
            # Debian/Ubuntu: aufgeteilte Pakete. qtsvg wird fuer das SVG-Icon
            # gebraucht, qtnetwork fuer den Update-Check.
            pm_install python3-pyside6.qtwidgets python3-pyside6.qtgui \
                       python3-pyside6.qtcore python3-pyside6.qtsvg \
                       python3-pyside6.qtnetwork || true
            ;;
        zypper)
            # Tumbleweed/Leap benennen das Paket je nach Version anders.
            pm_install python3-PySide6 || pm_install python3-pyside6 || true
            ;;
    esac
fi

# Immer noch nichts? Dann ein eigenes venv bauen. Das funktioniert auf JEDER
# Distribution und fasst das System-Python nicht an (kein
# --break-system-packages, kein Konflikt mit PEP 668).
if ! have_pyside; then
    echo "[Info] Kein PySide6 aus den Distro-Repos – lege ein venv unter $VENV_DIR an..."
    if ! "$PY_BIN" -c "import venv" &>/dev/null; then
        case "$PM" in
            dnf)    pm_install python3-devel || true ;;
            apt)    pm_install python3-venv python3-pip || true ;;
            zypper) pm_install python3-venv python3-pip || true ;;
        esac
    fi
    sudo rm -rf "$VENV_DIR"
    sudo "$PY_BIN" -m venv "$VENV_DIR"
    sudo "$VENV_DIR/bin/python3" -m pip install --upgrade pip
    sudo "$VENV_DIR/bin/python3" -m pip install "PySide6>=6.5" setproctitle
    PY_BIN="$VENV_DIR/bin/python3"

    if ! have_pyside; then
        echo "[Fehler] PySide6 konnte nicht installiert werden."
        echo "         Alternative: das AppImage von"
        echo "         $REPO/releases  – das bringt PySide6 bereits mit."
        exit 1
    fi
fi
echo "[Info] PySide6 OK (Interpreter: $PY_BIN)"

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
# Es wird der oben ermittelte Interpreter fest eingetragen — "python" gibt es
# auf Fedora nur, wenn python-unversioned-command installiert ist, und bei der
# venv-Variante muss ohnehin der venv-Interpreter laufen.
sudo tee "$BIN_LINK" >/dev/null <<LAUNCH
#!/bin/sh
cd "$INSTALL_DIR" || exit 1
exec "$PY_BIN" starter.py "\$@"
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
