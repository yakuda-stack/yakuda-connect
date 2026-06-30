#!/bin/bash
# yakuda-connect — AppImage Builder
# Benötigt: appimagetool, python3, pip
# Verwendung: bash build_appimage.sh

set -e

APP="yakuda-connect"
VERSION="1.0.5"
ARCH="x86_64"
BUILD_DIR="$(pwd)/AppDir"
OUT="$(pwd)/${APP}-${VERSION}-${ARCH}.AppImage"

echo "=== yakuda-connect AppImage Builder ==="
echo "Version: $VERSION"
echo ""

# 1. appimagetool prüfen
if ! command -v appimagetool &>/dev/null; then
    echo "[Info] appimagetool nicht gefunden — lade herunter..."
    wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" \
        -O /tmp/appimagetool
    chmod +x /tmp/appimagetool
    APPIMAGETOOL="/tmp/appimagetool"
else
    APPIMAGETOOL="appimagetool"
fi

# FUSE-Workaround: appimagetool ohne FUSE ausführen
export APPIMAGE_EXTRACT_AND_RUN=1

# 2. AppDir Struktur anlegen
echo "[1/5] Erstelle AppDir Struktur..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/usr/bin"
mkdir -p "$BUILD_DIR/usr/lib/yakuda-connect"
mkdir -p "$BUILD_DIR/usr/share/applications"
mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/256x256/apps"

# 3. Programmdateien kopieren
echo "[2/5] Kopiere Programmdateien..."
cp -r assets core ui "$BUILD_DIR/usr/lib/yakuda-connect/"
cp starter.py "$BUILD_DIR/usr/lib/yakuda-connect/"

# Wrapper-Script in /usr/bin
cat > "$BUILD_DIR/usr/bin/yakuda-connect" << 'WRAPPER'
#!/bin/bash
cd "$(dirname "$0")/../lib/yakuda-connect"
exec python3 starter.py "$@"
WRAPPER
chmod +x "$BUILD_DIR/usr/bin/yakuda-connect"

# 4. Icon und Desktop-Datei
echo "[3/5] Setze Icon und Desktop-Eintrag..."
cp assets/yakuda_icon.png "$BUILD_DIR/usr/share/icons/hicolor/256x256/apps/yakuda-connect.png"
cp assets/yakuda_icon.png "$BUILD_DIR/yakuda-connect.png"

cat > "$BUILD_DIR/usr/share/applications/yakuda-connect.desktop" << EOF
[Desktop Entry]
Name=yakuda-connect
Comment=WiVRn Manager for Linux VR
Exec=yakuda-connect
Icon=yakuda-connect
Terminal=false
Type=Application
Categories=Utility;
StartupWMClass=yakuda-connect
EOF

cp "$BUILD_DIR/usr/share/applications/yakuda-connect.desktop" "$BUILD_DIR/yakuda-connect.desktop"

# 5. Python-Abhängigkeiten ins AppDir bundeln
echo "[4/5] Bundele Python-Abhängigkeiten..."
mkdir -p "$BUILD_DIR/usr/lib/python3"
pip install --target="$BUILD_DIR/usr/lib/python3" PySide6 2>/dev/null || \
    echo "[Warn] PySide6 konnte nicht gebundelt werden — muss auf dem System vorhanden sein."

# AppRun Script
cat > "$BUILD_DIR/AppRun" << 'APPRUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
export PYTHONPATH="$HERE/usr/lib/python3:$PYTHONPATH"
export PATH="$HERE/usr/bin:$PATH"
exec "$HERE/usr/bin/yakuda-connect" "$@"
APPRUN
chmod +x "$BUILD_DIR/AppRun"

# 6. AppImage bauen
echo "[5/5] Baue AppImage..."
ARCH=x86_64 "$APPIMAGETOOL" "$BUILD_DIR" "$OUT"

echo ""
echo "✔ Fertig: $OUT"
echo "   Zum Starten: chmod +x $OUT && ./$OUT"
