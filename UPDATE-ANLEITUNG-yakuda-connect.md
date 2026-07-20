# AUR-Anleitung – Yakuda Connect

Nach dem osc-dreamchatbox-Verfahren, Platzhalter ausgefüllt mit den
echten Werten (verifiziert am Code):
  - depends: python, pyside6   (PySide6, NICHT PyQt6 – nur Stdlib sonst)
  - Entry-Point: starter.py  ->  Launcher /usr/bin/yakuda-connect
  - Version: 1.1.1, Git-Tag v1.1.1 (kein Alpha-Suffix -> KEIN Unterstrich nötig)
  - Beschreibung: "WiVRn VR management software with gaming optimization
    and OpenXR/OpenVR fixes"

WICHTIGSTE REGEL: Reihenfolge einhalten – erst GitHub, dann AUR.
Es gibt ZWEI PKGBUILDs:
  - im Projekt-Repo (packaging/aur/PKGBUILD)  = nur Kopie
  - ~/yakuda-connect/PKGBUILD                 = das ECHTE AUR-Paket
ACHTUNG Ordner-Verwechslung: Wenn dein Projekt auch ~/yakuda-connect
heißt, kloniere das AUR-Repo z.B. nach ~/aur/yakuda-connect.

====================================================================
TEIL A: ERSTVERÖFFENTLICHUNG (einmalig – yakuda-connect war noch nie im AUR)
====================================================================

## 0. SSH-Verbindung testen (ist schon eingerichtet)
    ssh aur@aur.archlinux.org
  -> "Welcome to AUR, yakuda!" = alles gut. Standard-Key id_ed25519,
     keine ssh/config nötig. KEIN neuer Key.

## 1. Vorher: depends verifizieren (schon erledigt, zur Kontrolle)
    pacman -Si pyside6           # extra/pyside6 – existiert
    pacman -Si python            # core/python – existiert
  Mehr braucht Yakuda Connect nicht (alle anderen Imports sind
  Standardbibliothek). Kein pyaudio, kein python-osc – nichts erfinden!

## 2. GitHub vorbereiten
  - APP_VERSION in core/main.py auf "v1.1.1" setzen (die EINE Quelle)
  - CHANGELOG-Block v1.1.1 ist schon oben drin, README verlinkt nur noch
  - committen, pushen:
      git add -A
      git commit -m "v1.1.1: Fedora/Ubuntu support, cubee-cb WayVR design, colour picker, cover art"
      git push origin main
  - Tag setzen und pushen:
      git tag -a v1.1.1 -m "v1.1.1"
      git push origin v1.1.1
  - GitHub-Release zum Tag v1.1.1 anlegen (KEIN Pre-Release-Haken,
    sonst sieht der eingebaute Update-Checker es nicht)

## 3. AUR-Repo klonen (leer -> erster Push legt das Paket an)
    mkdir -p ~/aur && cd ~/aur
    git clone ssh://aur@aur.archlinux.org/yakuda-connect.git
    cd yakuda-connect
  ("leeres Repository geklont" ist NORMAL)

## 4. PKGBUILD reinlegen + Maintainer-E-Mail prüfen
    cp ~/Pfad/zum/projekt/packaging/aur/PKGBUILD .
    nano PKGBUILD    # Zeile 1: E-Mail steht drin (yakuda@outlook.de, öffentlich!)

## 5. Checksumme + Testbuild
    updpkgsums                   # lädt Tag v1.1.1 von GitHub, ersetzt SKIP
    makepkg -si                  # bauen + installieren
    yakuda-connect               # starten & testen (Menü-Eintrag, Icon,
                                 #  Prozessname in btop = yakuda-connect)
    namcap PKGBUILD              # optional: Lint

## 6. .SRCINFO erzeugen (PFLICHT)
    makepkg --printsrcinfo > .SRCINFO

## 7. .gitignore + veröffentlichen
    printf "src/\npkg/\n*.pkg.tar.zst\n*.tar.gz\n" > .gitignore
    git add PKGBUILD .SRCINFO .gitignore
    git commit -m "Initial release v1.1.1"
    git push origin master       # AUR nutzt master, nicht main!

  -> live: https://aur.archlinux.org/packages/yakuda-connect
     Installation für alle: yay -S yakuda-connect

====================================================================
TEIL B: UPDATE (bei neuer Version, z.B. 1.1.1 -> 1.3.0)
====================================================================

## 1. Projekt: Version hochsetzen
  - APP_VERSION in core/main.py
  - CHANGELOG: neuen Block GANZ OBEN (alte nie umbenennen oder mergen)
  - Projekt-PKGBUILD (packaging/aur/): pkgver hoch, pkgrel=1
    committen, pushen, taggen, Tag pushen, GitHub-Release anlegen

## 2. AUR aktualisieren (ZUERST muss der GitHub-Tag online sein!)
    cd ~/aur/yakuda-connect
    nano PKGBUILD                        # pkgver hoch, pkgrel=1
    updpkgsums
    makepkg -si                          # testen: yakuda-connect starten
    makepkg --printsrcinfo > .SRCINFO    # PFLICHT
    git add PKGBUILD .SRCINFO
    git commit -m "Update to v1.3.0"
    git push origin master

## Nur Packaging ändern (z.B. pkgdesc, gleiche App-Version)
  Kein neuer GitHub-Tag nötig. Im AUR-Ordner:
  Änderung + pkgrel um 1 ERHÖHEN (statt zurücksetzen),
  .SRCINFO neu, committen, push origin master.

====================================================================
DIE HÄUFIGSTEN FEHLER
====================================================================
1. updpkgsums gibt 404      -> GitHub-Tag existiert noch nicht.
                               Erst Tag pushen, dann updpkgsums.
2. .SRCINFO vergessen       -> AUR lehnt den Push ab. Nach JEDER
                               PKGBUILD-Änderung neu erzeugen.
3. Falscher Ordner          -> AUR-Push NUR aus ~/aur/yakuda-connect.
                               Das Projekt-PKGBUILD ist nur die Kopie.
4. pkgver mit Bindestrich   -> bei 1.1.1 kein Thema. Falls je wieder
                               ein Alpha kommt: 1.x.y_alpha (Unterstrich)
                               und Tag via _tag="v${pkgver/_/-}" bauen.
5. Branch verwechselt       -> Projekt = push origin main,
                               AUR = push origin master.
6. Erfundene depends        -> jeden Paketnamen mit pacman -Si prüfen.
                               (Lektion: python-python-osc gab es nie.)
7. yay -Ss findet es nicht  -> normal, Cache-Index braucht Stunden.
                               yay -S yakuda-connect geht sofort.

====================================================================
CHAOTIC-AUR (optional, wie beim letzten Projekt)
====================================================================
Sobald im AUR: github.com/chaotic-aur/packages -> Issues -> Package
request. Package-Feld: AUR-Link. Purpose: WiVRn VR management for
Linux VR gaming (Arch/CachyOS). License: GPL-3.0-or-later.
Die 3 Checklist-Haken setzen. Dann bauen sie es als Binärpaket.
