#!/usr/bin/env bash
# yakuda-connect — AppImage Builder (EINE Datei, laeuft mit fuse2 UND fuse3)
# ============================================================================
# Verwendung:
#   bash build_appimage.sh
#
# ----------------------------------------------------------------------------
# Warum jetzt nur noch eine Datei?
# ----------------------------------------------------------------------------
# Eine AppImage ist ein SquashFS-Abbild mit einem "Runtime"-Kopf davor. Dieser
# Kopf haengt das Abbild per FUSE ein, bevor irgendein Code von uns laeuft.
# Genau dort gingen die Distros bisher auseinander:
#
#   * Der alte AppImageKit-Runtime laedt zur Laufzeit libfuse.so.2 per dlopen.
#     Auf aktuellen Systemen (Fedora 40+, Ubuntu 24.04+, SteamOS) ist libfuse2
#     nicht mehr installiert -> Abbruch mit "dlopen(): error loading
#     libfuse.so.2", noch bevor AppRun startet.
#
#   * Der type2-runtime linkt libfuse3 STATISCH (static-pie, keine einzige
#     dynamische Bibliothek) und sucht sich sein Mount-Hilfsprogramm selbst:
#     er geht den $PATH durch und nimmt das erste setuid-root-Binary, dessen
#     Name mit "fusermount" beginnt und das auf --version sauber antwortet.
#     Damit passt sowohl "fusermount3" (fuse3) als auch "fusermount" (fuse2).
#
# Ergo: der type2-runtime deckt beide Welten ab. Er braucht KEIN libfuse-Paket,
# nur das Kernelmodul fuse plus irgendein fusermount — egal welcher Generation.
# Deshalb bauen wir nur noch eine Datei statt zwei, und der Schritt
# "runtime pruefen" unten stellt sicher, dass auch wirklich dieser Runtime
# drinsteckt (siehe verify_runtime).
#
# Universeller Notausgang, falls FUSE komplett fehlt (z. B. Container,
# gehaertete Kernel, kein /dev/fuse):
#   ./yakuda-connect-*.AppImage --appimage-extract-and-run
# (entpackt nach /tmp und startet ohne FUSE — langsamer beim Start, laeuft
#  aber ueberall).
# ============================================================================

set -euo pipefail

APP="yakuda-connect"
ARCH="x86_64"
BUILD_DIR="$(pwd)/AppDir"

# Alte Aufrufe (fuse2 / fuse3 / both) sollen nicht hart scheitern.
if [ $# -gt 0 ]; then
    case "$1" in
        fuse2|fuse3|both)
            echo "[Hinweis] '$1' wird nicht mehr gebraucht — es gibt nur noch"
            echo "          eine AppImage, die fuse2 wie fuse3 bedient."
            echo ""
            ;;
        *)
            echo "Unbekanntes Argument: $1 (dieses Skript erwartet keine)" >&2
            exit 1
            ;;
    esac
fi

# --- Version aus der EINEN Quelle der Wahrheit lesen: core/version.py -------
VERSION="$(grep -oP '^VERSION\s*=\s*"\K[^"]+' core/version.py | head -1 || true)"
if [ -z "$VERSION" ]; then
    echo "[Fehler] Version konnte nicht aus core/version.py gelesen werden." >&2
    exit 1
fi

OUT="$(pwd)/${APP}-${VERSION}-${ARCH}.AppImage"
RUNTIME_URL="https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-${ARCH}"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/yakuda-connect/build"
RUNTIME="$CACHE_DIR/runtime-type2-${ARCH}"
mkdir -p "$CACHE_DIR"

echo "=== yakuda-connect AppImage Builder ==="
echo "Version: $VERSION"
echo "Ziel:    $(basename "$OUT")  (fuse2 + fuse3)"
echo ""

# ---------------------------------------------------------------------------
# 0. Runtime besorgen und pruefen
# ---------------------------------------------------------------------------
# Die Pruefung ist der Kern dieses Umbaus: Ein halb geladener oder falscher
# Runtime wuerde eine AppImage ergeben, die auf halben Systemen nicht startet —
# und das faellt beim Bauen auf dem eigenen Rechner nie auf, sondern erst bei
# den Nutzern. Zwei Merkmale unterscheiden die beiden Runtimes eindeutig:
#   * type2-runtime  : enthaelt "FUSERMOUNT_PROG", KEIN "libfuse.so.2"
#   * AppImageKit    : enthaelt "libfuse.so.2",   KEIN "FUSERMOUNT_PROG"
verify_runtime() {
    local f="$1"
    [ -s "$f" ] || return 1
    # ELF-Magic
    [ "$(head -c 4 "$f" | od -An -tx1 | tr -d ' \n')" = "7f454c46" ] || return 1
    # muss die fusermount-Eigensuche haben (deckt fusermount UND fusermount3 ab)
    grep -aq "FUSERMOUNT_PROG" "$f" || return 1
    # darf NICHT der alte, dynamisch gegen libfuse2 gelinkte Runtime sein
    grep -aq "libfuse\.so\.2" "$f" && return 1
    return 0
}

echo "[1/7] Hole AppImage-Runtime (type2, statisches libfuse3)..."
if ! verify_runtime "$RUNTIME"; then
    rm -f "$RUNTIME"
    if ! curl -fsSL "$RUNTIME_URL" -o "$RUNTIME"; then
        echo "[Fehler] Runtime konnte nicht geladen werden:" >&2
        echo "         $RUNTIME_URL" >&2
        echo "         Ohne diesen Runtime gibt es keine fuse2+fuse3-AppImage." >&2
        rm -f "$RUNTIME"
        exit 1
    fi
fi
if ! verify_runtime "$RUNTIME"; then
    echo "[Fehler] Geladener Runtime besteht die Pruefung nicht — er wuerde" >&2
    echo "         nicht auf allen Systemen starten. Abbruch." >&2
    rm -f "$RUNTIME"
    exit 1
fi
chmod +x "$RUNTIME"
echo "      OK ($(du -h "$RUNTIME" | cut -f1), statisch, fusermount-Eigensuche vorhanden)"

# ---------------------------------------------------------------------------
# 1. appimagetool besorgen
# ---------------------------------------------------------------------------
echo "[2/7] Suche appimagetool..."
if command -v appimagetool &>/dev/null; then
    APPIMAGETOOL="appimagetool"
else
    TOOL="$CACHE_DIR/appimagetool-${ARCH}.AppImage"
    if [ ! -s "$TOOL" ]; then
        echo "      nicht gefunden — lade herunter..."
        curl -fsSL "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage" -o "$TOOL"
    fi
    chmod +x "$TOOL"
    APPIMAGETOOL="$TOOL"
fi
# appimagetool ist selbst eine AppImage mit altem Runtime — auf einem Rechner
# ohne libfuse2 koennte sie sich nicht starten. Diese Variable entpackt sie
# stattdessen nach /tmp.
export APPIMAGE_EXTRACT_AND_RUN=1

# ---------------------------------------------------------------------------
# 2. AppDir aufbauen
# ---------------------------------------------------------------------------
echo "[3/7] Erstelle AppDir-Struktur..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/usr/bin" \
         "$BUILD_DIR/usr/lib/yakuda-connect" \
         "$BUILD_DIR/usr/share/applications" \
         "$BUILD_DIR/usr/share/icons/hicolor/scalable/apps" \
         "$BUILD_DIR/usr/share/icons/hicolor/512x512/apps"

echo "[4/7] Kopiere Programmdateien..."
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

echo "      Setze Icon und Desktop-Eintrag..."
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

echo "[5/7] Bundele Python-Abhaengigkeiten..."
mkdir -p "$BUILD_DIR/usr/lib/python3"
# PySide6-Essentials statt PySide6: spart mehrere hundert MB (WebEngine, 3D,
# Charts werden nicht gebraucht). Schlaegt es fehl, muss PySide6 auf dem
# Zielsystem vorhanden sein — die AppImage laeuft dann nur dort.
if ! pip install --target="$BUILD_DIR/usr/lib/python3" "PySide6-Essentials>=6.5" --quiet; then
    echo "[Warn] PySide6 konnte nicht gebundelt werden — muss auf dem System vorhanden sein."
fi
find "$BUILD_DIR/usr/lib/python3" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true

# --- AppRun -----------------------------------------------------------------
# Laeuft ERST, nachdem die Runtime das Abbild eingehaengt hat. Fehler beim
# Einhaengen selbst kann es also nicht abfangen (siehe Kopf der Datei) — aber
# es sorgt fuer eine saubere Umgebung und eine verstaendliche Meldung, falls
# python3 auf dem Zielsystem fehlt.
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
# 3. Bauen
# ---------------------------------------------------------------------------
echo "[6/7] Baue AppImage..."
rm -f "$OUT"
ARCH="$ARCH" "$APPIMAGETOOL" --runtime-file "$RUNTIME" "$BUILD_DIR" "$OUT"
chmod +x "$OUT"

# ---------------------------------------------------------------------------
# 4. Gegenproben
# ---------------------------------------------------------------------------
echo "[7/7] Pruefe das Ergebnis..."

# a) Steckt der richtige Runtime wirklich in der fertigen Datei? Der Kopf ist
#    die erste knappe Megabyte der Datei — dort muessen dieselben Merkmale
#    stehen wie oben geprueft.
head -c 2000000 "$OUT" > "$CACHE_DIR/head.bin"
if grep -aq "FUSERMOUNT_PROG" "$CACHE_DIR/head.bin" && ! grep -aq "libfuse\.so\.2" "$CACHE_DIR/head.bin"; then
    echo "      Runtime in der Datei: type2 (fuse2 + fuse3) — passt."
else
    echo "[Fehler] Die gebaute Datei enthaelt nicht den erwarteten Runtime." >&2
    echo "         Vermutlich hat appimagetool --runtime-file ignoriert." >&2
    rm -f "$CACHE_DIR/head.bin"
    exit 1
fi
rm -f "$CACHE_DIR/head.bin"

# b) Startet der Inhalt? Bewusst mit --appimage-extract-and-run: das prueft
#    Python, PySide6 und unsere Module, unabhaengig davon, ob DIESER Rechner
#    FUSE hat.
if QT_QPA_PLATFORM=offscreen timeout 120 "$OUT" --appimage-extract-and-run --selftest >/dev/null 2>&1; then
    echo "      Start-Test bestanden."
else
    echo "      [Hinweis] Automatischer Start-Test nicht eindeutig — bitte einmal von Hand starten."
fi

# c) Nur zur Information: hat DIESER Rechner ein fusermount, ueber das die
#    Datei nativ starten kann?
FM="$(command -v fusermount3 || command -v fusermount || true)"
if [ -n "$FM" ]; then
    echo "      Auf diesem Rechner nativ startbar (gefunden: $FM)."
else
    echo "      [Hinweis] Kein fusermount auf diesem Rechner — hier nur mit"
    echo "                --appimage-extract-and-run testbar. Das sagt nichts"
    echo "                ueber die Zielsysteme aus."
fi

echo ""
echo "Fertig:"
echo "   $(basename "$OUT")   ($(du -h "$OUT" | cut -f1))"
cat << EOF

Diese eine Datei laeuft auf:
   * Systemen mit fuse3 (Arch, CachyOS, Fedora 40+, Ubuntu 24.04+,
     Bazzite, SteamOS)  -> nutzt fusermount3
   * Systemen mit fuse2 (Ubuntu 22.04 und aelter, Debian 11/12)
     -> nutzt fusermount
   libfuse2 muss NICHT installiert sein: libfuse3 steckt statisch im Runtime.

Fehlt FUSE ganz (Container, gehaerteter Kernel, kein /dev/fuse):
   ./$(basename "$OUT") --appimage-extract-and-run
EOF
