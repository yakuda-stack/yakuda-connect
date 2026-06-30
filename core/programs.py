#!/usr/bin/env python3
"""
programs.py — Zentrale Programmliste für yakuda-connect
========================================================
Felder:
  key       : Eindeutiger interner Schlüssel
  name      : Anzeigename
  pkg       : AUR-Paketname (für yay/paru)
  desc      : Beschreibung (Deutsch)
  desc_eng  : Beschreibung (Englisch)
  start_cmd : Startbefehl
  link      : Webseite

Installationsmethoden (distro-abhängig automatisch gefiltert):
  install_methods : Liste erlaubter Methoden, Teilmenge von
                    {"appimage", "aur", "flatpak"}. Fehlt das Feld, wird aus
                    install_type/Feldern abgeleitet.
                      * "aur"     -> nur auf Arch-Distros, wenn yay oder paru da ist
                      * "appimage"-> überall, wenn github_repo/appimage_url gesetzt
                      * "flatpak" -> überall, wenn flatpak installiert + flatpak_id gesetzt
                    Sind mehrere Methoden verfügbar, zeigt die Karte ein
                    Dropdown. Vorauswahl: AppImage; sonst yay; sonst die erste.
  github_repo      : "owner/repo" -> neueste passende Release wird automatisch geholt
  appimage_url     : feste Download-URL (Alternative zu github_repo)
  version          : feste Version (nur bei fester appimage_url)
  asset_match      : Welche AppImage-Datei genommen wird (nur bei github_repo):
                     ".AppImage" (Arch automatisch) | "_x64.AppImage" | "x86_64.AppImage"
  include_prerelease: True/False -> auch Vorab-Versionen berücksichtigen
  flatpak_id       : Flatpak-App-ID (z. B. "com.vysp3r.ProtonPlus")
  config_dirs      : Ordnernamen in ~/.config zur Erkennung/zum Löschen
  icon_url         : Icon (GitHub blob- oder raw-URL)
  launch_args      : Zusätzliche Startargumente für die AppImage
                     (z. B. VRCX: "--no-install --no-desktop").
  remove_entries   : Vom Programm selbst angelegte .desktop-/Autostart-Dateien,
                     die bei Installation/Deinstallation entfernt werden (Pfade mit ~).

Hinweis zur Distro-Logik:
  Es gibt bewusst KEINE getrennten Listen pro Distro. Stattdessen entscheidet
  zur Laufzeit detect_install_methods(): Arch-Distros bekommen yay/paru, alle
  Distros AppImage/Flatpak – je nachdem, was vorhanden ist.
"""

INSTALL_PACKAGES = {
    "WiVRn / Monado": ["wivrn-server", "lib32-wivrn-server"],
    "WiVRn Dashboard": ["wivrn-dashboard"],
    "xrizer": ["xrizer", "xrizer-common"],
    "opencomposite": ["opencomposite-git"],
}

# Runtime-Quelle für Nicht-Arch-Systeme (Installations-Tab):
#   flatpak : Flatpak-App-IDs (flatpak install -y flathub <id>)
INSTALL_FLATPAK = ["io.github.wivrn.wivrn"]

TOOLS_APPS = [
    {
        "key":          "wayvr",
        "name":         "WayVR",
        "pkg":          "wayvr",
        "desc":         "Ein Desktop-Overlay für Wayland desktops mit integriertem Playspace Mover (wie XSOverlay).",
        "desc_eng":     "A desktop overlay for Wayland with integrated Playspace Mover (like XSOverlay).",
        "start_cmd":    "wayvr",
        "link":         "https://github.com/wayvr-org/wayvr",
        # AppImage / yay / paru — Vorauswahl AppImage
        "install_methods": ["appimage", "aur"],
        "github_repo":  "wayvr-org/wayvr",
        "asset_match":  "-x86_64.AppImage",
        "include_prerelease": False,
        "icon_url":     "https://raw.githubusercontent.com/wayvr-org/wayvr/main/wayvr/wayvr.png",
        "config_dirs":  ["wayvr"],
    },
    {
        "key":          "vrcx",
        "name":         "VRCX",
        "pkg":          "vrcx",
        "desc":         "Freundschafts-Verwaltungstool für VRChat (basiert auf Electron).",
        "desc_eng":     "Friendship management tool for VRChat (built with Electron).",
        "start_cmd":    "vrcx",
        "link":         "https://github.com/vrcx-team/VRCX",
        # AppImage / yay / paru — Vorauswahl AppImage
        "install_methods": ["appimage", "aur"],
        "github_repo":  "vrcx-team/VRCX",
        "asset_match":  "_x64.AppImage",
        "include_prerelease": False,
        "config_dirs":  ["VRCX"],
        # Verhindert, dass VRCX sich nach ~/Applications verschiebt / eigene .desktop anlegt
        "launch_args":  "--no-install --no-desktop",
        "icon_url":     "https://raw.githubusercontent.com/vrcx-team/VRCX/master/images/VRCX.png",
        "remove_entries": [
            "~/.local/share/applications/VRCX.desktop",
            "~/.config/autostart/VRCX.desktop",
        ],
    },
    {
        "key":          "protonplus",
        "name":         "ProtonPlus",
        "pkg":          "protonplus",
        "desc":         "Damit viele Spiele gut und performance-freundlich laufen. Für VRChat ist Proton GE RTSP empfohlen.",
        "desc_eng":     "Helps many games run well and performance-friendly. Proton GE RTSP is recommended for VRChat.",
        "start_cmd":    "protonplus",
        "link":         "https://github.com/Vysp3r/ProtonPlus",
        # yay / paru / Flatpak
        "install_methods": ["aur", "flatpak"],
        "flatpak_id":   "com.vysp3r.ProtonPlus",
    },
    {
        "key":          "slimevr-bin",
        "name":         "SlimeVR FBT",
        "pkg":          "slimevr-bin",
        "desc":         "VR Full Body Tracking System.",
        "desc_eng":     "VR Full Body Tracking System.",
        "start_cmd":    "slimevr",
        "link":         "https://slimevr.dev/",
        # nur AUR (yay/paru)
        "install_methods": ["aur"],
    },
    {
        "key":          "unityhub",
        "name":         "Unity Hub (for Alcom)",
        "pkg":          "unityhub",
        "desc":         "Der offizielle Unity Hub – wird zwingend für die Nutzung von Alcom benötigt.",
        "desc_eng":     "The official Unity Hub — required for using Alcom.",
        "start_cmd":    "unityhub",
        "link":         "https://docs.unity.com/en-us/hub",
        # yay / paru / Flatpak
        "install_methods": ["aur", "flatpak"],
        "flatpak_id":   "com.unity.UnityHub",
    },
    {
        "key":          "alcom",
        "name":          "Alcom (VRChat Creator Companion)",
        "pkg":          "alcom",
        "desc":         "Eine schnelle, quelloffene Alternative zum offiziellen VRChat Creator Companion (VCC).",
        "desc_eng":     "A fast, open-source alternative to the official VRChat Creator Companion (VCC).",
        "start_cmd":    "alcom",
        "link":         "https://vrc-get.anatawa12.com/de/alcom/",
        # AppImage / yay / paru — feste URL, weil im Release zwei Projekte liegen (vrc-get + alcom)
        "install_methods": ["appimage", "aur"],
        "appimage_url": "https://github.com/vrc-get/vrc-get/releases/download/gui-v1.1.6/alcom-1.1.6-x86_64.AppImage",
        "version":      "1.1.6",
    },
    {
        "key":          "intiface-central",
        "name":         "Intiface Central",
        "pkg":          "intiface-central",
        "desc":         "Steuerzentrale für deine Toys. Kann alternativ auf dem Handy installiert werden: Handy-IP in OscGoesBrrr eintragen.",
        "desc_eng":     "Control hub for your toys. Can also run on your phone — just enter the phone IP in OscGoesBrrr.",
        "start_cmd":    "intiface-central",
        "link":         "https://intiface.com/#intiface-central",
        # yay / paru / Flatpak
        "install_methods": ["aur", "flatpak"],
        "flatpak_id":   "com.nonpolynomial.intiface_central",
    },
    {
        "key":          "android-tools",
        "name":         "android-tools (ADB)",
        "pkg":          "android-tools",
        "desc":         "VR-App per Kabel auf dem Headset installieren (Android-basiert).",
        "desc_eng":     "Install VR apps directly on your headset via USB cable (Android-based).",
        "start_cmd":    "android-tools",
        "link":         "https://developer.android.com/tools?hl=de",
        # AppImage / yay / paru — feste URL (pkgforge AppImage-Build)
        "install_methods": ["appimage", "aur"],
        "appimage_url": "https://github.com/pkgforge-dev/android-tools-AppImage/releases/download/37.0.0%402026-06-22_1782134919/Android_Tools-37.0.0-anylinux-x86_64.AppImage",
        "version":      "37.0.0",
    },
]

TOOLS_OSC = [
    {
        "key":          "oscleash",
        "name":         "OSC Leash",
        "pkg":          "oscleash",
        "desc":         "OSC-Tool, um dich an einer virtuellen Leine hinterherzuziehen. Erfordert eine entsprechende Funktion im Avatar.",
        "desc_eng":     "OSC tool to pull you around on a virtual leash. Requires a compatible avatar setup.",
        "start_cmd":    "oscleash_app",
        "link":         "https://github.com/yakuda-stack/OSCLeash",
        # nur AppImage (feste URL)
        "install_methods": ["appimage"],
        "version":      "2.2.0.1",
        "appimage_url": "https://github.com/yakuda-stack/OSCLeash/releases/download/v2.2.0.1/OSCLeash-x86_64.AppImage",
        "icon_url":     "https://raw.githubusercontent.com/ZenithVal/OSCLeash/main/Resources/VRChatOSCLeash.png",
        "config_dirs":  ["OSCLeash"],
    },
    {
        "key":          "oscgoesbrrr",
        "name":         "OSCGoesBrrr",
        "pkg":          "oscgoesbrrr",
        "desc":         "Echtes haptisches Feedback für VRChat. Unterstützt Lovense-Toys (kompatibel mit VRCFury).",
        "desc_eng":     "Real haptic feedback for VRChat. Supports Lovense toys (compatible with VRCFury).",
        "start_cmd":    "oscgoesbrrr",
        "link":         "https://github.com/OscToys/OscGoesBrrr/releases",
        # AppImage / yay / paru — Vorauswahl AppImage
        "install_methods": ["appimage", "aur"],
        "github_repo":  "OscToys/OscGoesBrrr",
        "asset_match":  ".AppImage",
        "include_prerelease": True,
        "config_dirs":  ["OscGoesBrrr"],
        "icon_url":     "https://raw.githubusercontent.com/OscToys/OscGoesBrrr/main/src/icons/ogb-logo.png",
    },
]
