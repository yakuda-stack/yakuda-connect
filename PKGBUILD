# Maintainer: DEIN NAME <deine@mail>
# PKGBUILD fuer yakuda-connect — VR-Launcher fuer WiVRn/WayVR (Arch Linux)
#
# Installieren (zieht alle Abhaengigkeiten automatisch):  yay -S yakuda-connect-git

pkgname=yakuda-connect-git
pkgver=r1
pkgrel=1
pkgdesc="VR-Launcher fuer WiVRn/WayVR/SlimeVR auf Arch Linux"
arch=('any')
url="https://github.com/DEINNAME/yakuda-connect"
license=('MIT')                       # ggf. an deine Lizenz anpassen
# Pflicht-Abhaengigkeiten -> werden automatisch mitinstalliert:
depends=('python' 'pyside6')
# Optionale Laufzeit-Werkzeuge (dein Tool ruft sie auf, falls vorhanden):
optdepends=('iproute2: Headset-Verbindungserkennung (ss)'
            'libpulse: Headset-Verbindungserkennung (pactl)'
            'polkit: Wiederherstellen von System-VR-Dateien (pkexec)'
            'git: Herunterladen des WayVR-Overlay-Designs'
            'playerctl: Media-Tasten in der WayVR-Watch')
makedepends=('git')
provides=('yakuda-connect')
conflicts=('yakuda-connect')
source=("$pkgname::git+https://github.com/DEINNAME/yakuda-connect.git")
sha256sums=('SKIP')

pkgver() {
    cd "$srcdir/$pkgname"
    printf "r%s.%s" "$(git rev-list --count HEAD)" "$(git rev-parse --short HEAD)"
}

package() {
    cd "$srcdir/$pkgname"
    local dest="$pkgdir/usr/share/yakuda-connect"

    # Programmdateien installieren (nur, was existiert)
    install -d "$dest"
    for item in core ui overlay assets starter.py; do
        [ -e "$item" ] && cp -r "$item" "$dest/"
    done

    # Startbefehl /usr/bin/yakuda-connect anlegen
    install -d "$pkgdir/usr/bin"
    cat > "$pkgdir/usr/bin/yakuda-connect" <<'LAUNCH'
#!/bin/sh
cd /usr/share/yakuda-connect || exit 1
exec python starter.py "$@"
LAUNCH
    chmod 755 "$pkgdir/usr/bin/yakuda-connect"

    # .desktop-Eintrag
    install -Dm644 "$srcdir/yakuda-connect.desktop" \
        "$pkgdir/usr/share/applications/yakuda-connect.desktop"

    # Icon installieren, falls eines in assets/ liegt
    local icon
    icon="$(find assets -maxdepth 1 -iname '*.png' 2>/dev/null | head -1)"
    if [ -n "$icon" ]; then
        install -Dm644 "$icon" \
            "$pkgdir/usr/share/icons/hicolor/256x256/apps/yakuda-connect.png"
    fi
}
