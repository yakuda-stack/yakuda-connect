# Maintainer: Dein Name <deine@email.de>
pkgname=yakuda-connect
pkgver=1.0.0
pkgrel=1
pkgdesc="WiVRn Manager — einfache GUI für Linux VR Streaming"
arch=('any')
url="https://github.com/DEIN_USERNAME/yakuda-connect"
license=('MIT')
depends=('python' 'python-pyside6')
optdepends=(
    'wivrn-server: WiVRn VR Streaming Server'
    'wivrn-dashboard: WiVRn Dashboard'
    'yay: AUR-Helper für Tool-Installation'
)
source=("$pkgname-$pkgver.tar.gz::$url/archive/refs/tags/v$pkgver.tar.gz")
sha256sums=('SKIP')

package() {
    cd "$srcdir/$pkgname-$pkgver"

    # Programmdateien installieren
    install -dm755 "$pkgdir/opt/$pkgname"
    cp -r assets core ui starter.py "$pkgdir/opt/$pkgname/"
    chmod +x "$pkgdir/opt/$pkgname/starter.py"

    # Desktop-Eintrag
    install -Dm644 "$pkgname.desktop" \
        "$pkgdir/usr/share/applications/$pkgname.desktop"

    # Icon
    install -Dm644 "assets/yakuda_icon.png" \
        "$pkgdir/usr/share/pixmaps/$pkgname.png"

    # Startbefehl im PATH
    install -dm755 "$pkgdir/usr/bin"
    ln -s "/opt/$pkgname/starter.py" "$pkgdir/usr/bin/$pkgname"
}
