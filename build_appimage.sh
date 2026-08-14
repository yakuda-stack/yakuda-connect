#!/usr/bin/env bash
# yakuda-connect — AppImage Builder (fuse2 + fuse3)
# ============================================================================
# Verwendung:
#   bash build_appimage.sh              # baut BEIDE Varianten (empfohlen)
#   bash build_appimage.sh fuse3        # nur moderne Systeme
#   bash build_appimage.sh fuse2        # nur aeltere Systeme
#
# ----------------------------------------------------------------------------
# Warum zwei Varianten?
# ----------------------------------------------------------------------------
# Eine AppImage ist eine SquashFS-Datei mit einem "Runtime"-Kopf davor. Dieser
# Kopf haengt das Dateisystem per FUSE ein — und genau da gehen die Distros
# auseinander:
#
#   * Der klassische AppImageKit-Runtime braucht libfuse.so.2 auf dem System.
#     Auf aktuellen Distros (Fedora 40+, Ubuntu 24.04, SteamOS) ist libfuse2
#     nicht mehr vorinstalliert -> die AppImage bricht mit der kryptischen
#     Meldung "dlopen(): error loading libfuse.so.2" ab, BEVOR unser Code
#     ueberhaupt laeuft. Wir koennen diesen Fehler also nicht abfangen.
#
#   * Der neuere type2-runtime linkt libfuse3 STATISCH. Er braucht kein
#     libfuse-Paket, nur das Kernelmodul fuse und fusermount3. Damit laeuft er
#     auf allen modernen Systemen ohne Zusatzpaket — auf wirklich alten
#     (nur fusermount aus fuse2, kein fusermount3) dagegen nicht.
#
# Deshalb zwei Dateien, klar benannt. Die fuse3-Variante ist die normale,
# die fuse2-Variante der Rueckfall fuer aeltere Systeme.
#
# Universeller Notausgang fuer BEIDE:
#   ./yakuda-connect-*.AppImage --appimage-extract-and-run
# (entpackt in ein Temp-Verzeichnis und startet ohne FUSE — langsamer beim
#  Start, laeuft aber ueberall).
# ============================================================================

set -euo pipefail

APP="yakuda-connect"
ARCH="x86_64"
BUILD_DIR="$(pwd)/AppDir"

# --- Version aus der EINEN Quelle der Wahrheit lesen: core/version.py -------
VERSION="$(grep -oP '^VERSION\s*=\s*"\K[^"]+' core/version.py | head -1 || true)"
if [ -z "$VERSION" ]; then
    echo "[Fehler] Version konnte nicht aus core/version.py gelesen werden." >&2
    exit 1
fi

# --- Welche Varianten bauen? ------------------------------------------------
VARIANTS="${1:-both}"
case "$VARIANTS" in
    fuse2|fuse3|both) ;;
    *) echo "Unbekannte Variante: $VARIANTS (erlaubt: fuse2, fuse3, both)" >&2; exit 1 ;;
esac

RUNTIME_FUSE3_URL="https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-${ARCH}"
RUNTIME_FUSE2_URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/runtime-${ARCH}"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/yakuda-connect/build"
mkdir -p "$CACHE_DIR"

echo "=== yakuda-connect AppImage Builder ==="
echo "Version:   $VERSION"
echo "Varianten: $VARIANTS"
echo ""

# ---------------------------------------------------------------------------
# 1. appimagetool besorgen
# ---------------------------------------------------------------------------
if command -v appimagetool &>/dev/null; then
    APPIMAGETOOL="appimagetool"
else
    echo "[Info] appimagetool nicht gefunden — lade herunter..."
    TOOL="$CACHE_DIR/appimagetool-${ARCH}.AppImage"
    if [ ! -f "$TOOL" ]; then
        curl -fsSL "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage" -o "$TOOL"
    fi
    chmod +x "$TOOL"
    APPIMAGETOOL="$TOOL"
fi

# appimagetool ist selbst eine AppImage — auf einem Rechner ohne libfuse2
# koennte sie sich nicht starten. Diese Variable entpackt sie stattdessen.
export APPIMAGE_EXTRACT_AND_RUN=1

# ---------------------------------------------------------------------------
# 2. AppDir aufbauen
# ---------------------------------------------------------------------------
echo "[1/6] Erstelle AppDir-Struktur..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/usr/bin" \
         "$BUILD_DIR/usr/lib/yakuda-connect" \
         "$BUILD_DIR/usr/share/applications" \
         "$BUILD_DIR/usr/share/icons/hicolor/scalable/apps" \
         "$BUILD_DIR/usr/share/icons/hicolor/512x512/apps"

echo "[2/6] Kopiere Programmdateien..."
# locales/ nicht vergessen — ohne den Ordner startet die App nicht (Texte).
cp -r assets config core ui locales "$BUILD_DIR/usr/lib/yakuda-connect/"
cp starter.py "$BUILD_DIR/usr/lib/yakuda-connect/"
# Bytecode und Entwicklerreste gehoeren nicht in die Auslieferung
find "$BUILD_DIR/usr/lib/yakuda-connect" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$BUILD_DIR/usr/lib/yakuda-connect" -type f -name '*.py[co]' -delete
# Screenshots aus assets/ wuerden die AppImage nur aufblaehen
rm -f "$BUILD_DIR/usr/lib/yakuda-connect/assets/"{dashboard,games1,games2,installation,settings,settings2,streaming,tools}.png

cat > "$BUILD_DIR/usr/bin/yakuda-connect" << 'WRAPPER'
#!/bin/bash
cd "$(dirname "$(readlink -f "$0")")/../lib/yakuda-connect" || exit 1
exec python3 starter.py "$@"
WRAPPER
chmod +x "$BUILD_DIR/usr/bin/yakuda-connect"

echo "[3/6] Setze Icon und Desktop-Eintrag..."
cp assets/yakuda_icon.svg "$BUILD_DIR/usr/share/icons/hicolor/scalable/apps/yakuda-connect.svg"
cp assets/yakuda_icon_512.png "$BUILD_DIR/usr/share/icons/hicolor/512x512/apps/yakuda-connect.png"
cp assets/yakuda_icon.svg "$BUILD_DIR/yakuda-connect.svg"

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
X-AppImage-Version=$VERSION
EOF
cp "$BUILD_DIR/usr/share/applications/yakuda-connect.desktop" "$BUILD_DIR/yakuda-connect.desktop"

echo "[4/6] Bundele Python-Abhaengigkeiten..."
mkdir -p "$BUILD_DIR/usr/lib/python3"
# PySide6-Essentials statt PySide6: spart mehrere hundert MB (WebEngine, 3D,
# Charts werden nicht gebraucht). Schlaegt es fehl, muss PySide6 auf dem
# Zielsystem vorhanden sein — die AppImage laeuft dann nur dort.
if ! pip install --target="$BUILD_DIR/usr/lib/python3" "PySide6-Essentials>=6.5" --quiet; then
    echo "[Warn] PySide6 konnte nicht gebundelt werden — muss auf dem System vorhanden sein."
fi
find "$BUILD_DIR/usr/lib/python3" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true

# --- AppRun -----------------------------------------------------------------
# Laeuft ERST, nachdem die Runtime das Dateisystem eingehaengt hat. Fehler
# beim Einhaengen selbst kann es also nicht abfangen (siehe Kopf der Datei) —
# aber es sorgt fuer eine saubere Umgebung und eine verstaendliche Meldung,
# falls python3 auf dem Zielsystem fehlt.
cat > "$BUILD_DIR/AppRun" << 'APPRUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
export PYTHONPATH="$HERE/usr/lib/python3:${PYTHONPATH:-}"
export PATH="$HERE/usr/bin:$PATH"

if ! command -v python3 >/dev/null 2>&1; then
    MSG="yakuda-connect braucht Python 3 auf dem System.
Bitte installieren:
  Arch:    sudo pacman -S python
  Fedora:  sudo dnf install python3
  Ubuntu:  sudo apt install python3"
    command -v zenity >/dev/null 2>&1 && zenity --error --text="$MSG" 2>/dev/null
    echo "$MSG" >&2
    exit 1
fi

exec "$HERE/usr/bin/yakuda-connect" "$@"
APPRUN
chmod +x "$BUILD_DIR/AppRun"

# ---------------------------------------------------------------------------
# 3. Bauen — je Variante mit passendem Runtime
# ---------------------------------------------------------------------------
build_variant() {
    local variant="$1" url out runtime
    if [ "$variant" = "fuse3" ]; then
        url="$RUNTIME_FUSE3_URL"
        out="$(pwd)/${APP}-${VERSION}-${ARCH}.AppImage"
    else
        url="$RUNTIME_FUSE2_URL"
        out="$(pwd)/${APP}-${VERSION}-${ARCH}-legacy-fuse2.AppImage"
    fi
    runtime="$CACHE_DIR/runtime-${variant}-${ARCH}"

    if [ ! -f "$runtime" ]; then
        echo "      Lade Runtime ($variant)..."
        if ! curl -fsSL "$url" -o "$runtime"; then
            echo "[Warn] Runtime fuer $variant nicht ladbar — Variante uebersprungen." >&2
            rm -f "$runtime"
            return 1
        fi
    fi
    chmod +x "$runtime"

    ARCH="$ARCH" "$APPIMAGETOOL" --runtime-file "$runtime" "$BUILD_DIR" "$out"
    echo "      -> $(basename "$out")"
}

echo "[5/6] Baue AppImage(s)..."
BUILT=()
if [ "$VARIANTS" = "both" ] || [ "$VARIANTS" = "fuse3" ]; then
    build_variant fuse3 && BUILT+=("${APP}-${VERSION}-${ARCH}.AppImage") || true
fi
if [ "$VARIANTS" = "both" ] || [ "$VARIANTS" = "fuse2" ]; then
    build_variant fuse2 && BUILT+=("${APP}-${VERSION}-${ARCH}-legacy-fuse2.AppImage") || true
fi

if [ ${#BUILT[@]} -eq 0 ]; then
    echo "[Fehler] Keine AppImage gebaut." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# 4. Gegenprobe: startet die gebaute Datei ueberhaupt?
# ---------------------------------------------------------------------------
# Bewusst mit --appimage-extract-and-run: das prueft den INHALT (Python,
# PySide6, unsere Module), unabhaengig davon, ob dieser Rechner FUSE hat.
echo "[6/6] Teste die gebaute AppImage (offscreen)..."
TEST_FILE="${BUILT[0]}"
chmod +x "$TEST_FILE"
if QT_QPA_PLATFORM=offscreen timeout 120 "./$TEST_FILE" --appimage-extract-and-run --selftest >/dev/null 2>&1; then
    echo "      Start-Test bestanden."
else
    echo "      [Hinweis] Automatischer Start-Test nicht eindeutig — bitte einmal von Hand starten."
fi

echo ""
echo "Fertig:"
for f in "${BUILT[@]}"; do
    echo "   $f   ($(du -h "$f" | cut -f1))"
done
cat << EOF

Welche Datei fuer wen?
   ${APP}-${VERSION}-${ARCH}.AppImage
       -> Standard. Moderne Systeme (Arch, CachyOS, Fedora 40+,
          Ubuntu 24.04+, Bazzite, SteamOS). Braucht kein libfuse2.

   ${APP}-${VERSION}-${ARCH}-legacy-fuse2.AppImage
       -> Aeltere Systeme (Ubuntu 22.04 und aelter, Debian 11/12),
          dort ist libfuse2 vorhanden, fusermount3 dagegen oft nicht.

Laeuft eine der beiden nicht, hilft immer:
   ./${APP}-${VERSION}-${ARCH}.AppImage --appimage-extract-and-run
EOF
