#!/usr/bin/env python3
"""
scripts/bump_version.py — Version an allen Stellen gleichzeitig setzen
=====================================================================
Ersetzt Schritt 1 der Update-Anleitung ("Diese 3 Stellen aendern").
Von Hand war das fehleranfaellig: vergisst man die PKGBUILD, baut das AUR
den alten Tag; vergisst man core/main.py, sehen alte Clients kein Update.

    python3 scripts/bump_version.py 1.1.6      # Version setzen
    python3 scripts/bump_version.py --check    # nur pruefen (nutzt die CI)
    python3 scripts/bump_version.py --check --expect 1.1.6

Gepflegt werden:
  1. core/version.py           -> VERSION = "1.1.6"        (Quelle der Wahrheit)
  2. core/main.py              -> APP_VERSION = "v1.1.6"   (Kompatibilitaets-Anker)
  3. packaging/aur/PKGBUILD    -> pkgver=1.1.6 und pkgrel=1

Zu Punkt 2: Der Update-Checker ALTER Clients (bis v1.1.4) laedt core/main.py
von GitHub und sucht darin per regulaerem Ausdruck nach

    APP_VERSION = "v1.1.4"

Verschwindet diese Zeile, melden alle bereits installierten Versionen fuer
immer "aktuell" und finden nie wieder ein Update. Deshalb bleibt sie stehen
und wird hier mitgepflegt — sie ist kein Ueberbleibsel, sondern Absicht.

Was das Skript NICHT tut (bewusst, siehe Update-Anleitung):
  * keinen Git-Tag setzen und nichts pushen
  * den CHANGELOG-Block nicht schreiben — der Text kommt von dir;
    das Skript erinnert nur daran, wenn der Block fehlt
"""
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

VERSION_PY = ROOT / "core" / "version.py"
MAIN_PY = ROOT / "core" / "main.py"
PKGBUILD = ROOT / "packaging" / "aur" / "PKGBUILD"
CHANGELOG = ROOT / "CHANGELOG.md"

# Erlaubt: 1.1.6 sowie 1.1.6_alpha (Unterstrich!). Ein Bindestrich ist in
# pkgver nicht zulaessig — genau der Fehler Nr. 4 aus der Update-Anleitung.
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(_[A-Za-z0-9]+)?$")


# --------------------------------------------------------------------------- #
#  Lesen
# --------------------------------------------------------------------------- #
def read_version_py():
    m = re.search(r'^VERSION\s*=\s*"([^"]+)"', VERSION_PY.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def read_main_py():
    m = re.search(r'APP_VERSION\s*=\s*"v?([^"]+)"', MAIN_PY.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def read_pkgbuild():
    text = PKGBUILD.read_text(encoding="utf-8")
    m = re.search(r"^pkgver=(.+)$", text, re.M)
    r = re.search(r"^pkgrel=(.+)$", text, re.M)
    return (m.group(1).strip() if m else None,
            r.group(1).strip() if r else None)


# --------------------------------------------------------------------------- #
#  Pruefen
# --------------------------------------------------------------------------- #
def check(expect=None):
    """0 = alles stimmig, 1 = Abweichung. Gibt jede Abweichung einzeln aus."""
    v_ver = read_version_py()
    v_main = read_main_py()
    v_pkg, pkgrel = read_pkgbuild()

    print(f"core/version.py         VERSION     = {v_ver}")
    print(f"core/main.py            APP_VERSION = v{v_main}")
    print(f"packaging/aur/PKGBUILD  pkgver      = {v_pkg}   (pkgrel={pkgrel})")

    problems = []
    if not v_ver:
        problems.append("core/version.py: VERSION nicht gefunden")
    if not v_main:
        problems.append(
            "core/main.py: APP_VERSION-Anker fehlt! Ohne ihn finden alte "
            "Clients (bis v1.1.4) nie wieder ein Update.")
    if not v_pkg:
        problems.append("PKGBUILD: pkgver nicht gefunden")

    for label, value in (("core/main.py", v_main), ("PKGBUILD", v_pkg)):
        if value and v_ver and value != v_ver:
            problems.append(f"{label} steht auf {value}, core/version.py auf {v_ver}")

    if expect and v_ver and v_ver != expect:
        problems.append(f"Erwartet wurde {expect}, im Code steht {v_ver}")

    if v_ver and CHANGELOG.exists():
        if v_ver not in CHANGELOG.read_text(encoding="utf-8"):
            # Bewusst nur ein Hinweis: die CI soll nicht rot werden, nur weil
            # der Changelog-Text noch nicht geschrieben ist.
            print(f"\nHinweis: kein Block fuer {v_ver} in CHANGELOG.md gefunden.")

    if problems:
        print("\nFEHLER:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("\nAlle Versionsangaben stimmen ueberein.")
    return 0


# --------------------------------------------------------------------------- #
#  Setzen
# --------------------------------------------------------------------------- #
def _sub_once(path, pattern, replacement, description):
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.M)
    if count != 1:
        print(f"  !! {description}: Muster nicht gefunden — Datei unveraendert")
        return False
    path.write_text(new_text, encoding="utf-8")
    print(f"  ok {description}")
    return True


def bump(new_version):
    if not VERSION_RE.match(new_version):
        print(f"Ungueltige Version: {new_version}")
        print("Erwartet: 1.2.3 oder 1.2.3_alpha (Unterstrich, kein Bindestrich!)")
        return 1

    old = read_version_py()
    print(f"Version {old} -> {new_version}\n")

    ok = True
    ok &= _sub_once(VERSION_PY, r'^VERSION\s*=\s*"[^"]+"',
                    f'VERSION = "{new_version}"', "core/version.py")
    ok &= _sub_once(MAIN_PY, r'APP_VERSION\s*=\s*"[^"]+"',
                    f'APP_VERSION = "v{new_version}"', "core/main.py (Anker)")
    ok &= _sub_once(PKGBUILD, r"^pkgver=.+$",
                    f"pkgver={new_version}", "PKGBUILD pkgver")
    # pkgrel IMMER auf 1 zuruecksetzen: neue Upstream-Version = neuer Build.
    # (Nur bei reinen Paket-Aenderungen ohne neuen Tag wird pkgrel erhoeht —
    #  das steht in der Update-Anleitung und macht man dann von Hand im
    #  AUR-Ordner, nicht hier.)
    ok &= _sub_once(PKGBUILD, r"^pkgrel=.+$", "pkgrel=1", "PKGBUILD pkgrel")

    if not ok:
        return 1

    print(f"""
Naechste Schritte (siehe UPDATE-ANLEITUNG-yakuda-connect.md):

  1. CHANGELOG.md: neuen Block "### v{new_version}" GANZ OBEN einfuegen
  2. git add -A && git commit -m "v{new_version}: ..."
     git push origin main
     git tag -a v{new_version} -m "v{new_version}" && git push origin v{new_version}
  3. GitHub-Release veroeffentlichen (KEIN Pre-Release-Haken!)
  4. AUR: cd ~/aur/yakuda-connect -> pkgver/pkgrel angleichen ->
     updpkgsums -> makepkg -si -> makepkg --printsrcinfo > .SRCINFO ->
     git push origin master
""")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Version an allen Stellen setzen/pruefen")
    ap.add_argument("version", nargs="?", help="neue Version, z. B. 1.1.6")
    ap.add_argument("--check", action="store_true",
                    help="nur pruefen, nichts aendern (fuer die CI)")
    ap.add_argument("--expect", help="zusaetzlich gegen diese Version pruefen (Tag-Name)")
    args = ap.parse_args()

    if args.check or not args.version:
        return check(expect=args.expect)
    return bump(args.version)


if __name__ == "__main__":
    sys.exit(main())
