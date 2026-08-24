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
  note / note_eng  : Optionaler Hinweis (klein, kursiv, gelb) unter der
                     Beschreibung — z. B. Installations-Hinweise für Nutzer,
                     denen keine Methode zur Verfügung steht (kein AppImage
                     auf Nicht-Arch-Systemen o. Ä.).

Hinweis zur Distro-Logik:
  Es gibt bewusst KEINE getrennten Listen pro Distro. Stattdessen entscheidet
  zur Laufzeit detect_install_methods(): Arch-Distros bekommen yay/paru, alle
  Distros AppImage/Flatpak – je nachdem, was vorhanden ist.

  WICHTIG: Flatpak ist NUR noch für Tools erlaubt (dieser Tab hier).
  Die WiVRn-Runtime im Installations-Tab wird ausschließlich nativ
  installiert (Arch: AUR, Fedora: dnf, Ubuntu: Anleitung zum Selbstbauen).
"""

INSTALL_PACKAGES = {
    "WiVRn / Monado": ["wivrn-server", "lib32-wivrn-server"],
    "WiVRn Dashboard": ["wivrn-dashboard"],
    "xrizer": ["xrizer", "xrizer-common"],
    "opencomposite": ["opencomposite-git"],
}

# Runtime-Quelle für Fedora (Installations-Tab, offizielle Repos):
#   wivrn           : https://packages.fedoraproject.org/pkgs/wivrn/wivrn/
#   wivrn-dashboard : Subpaket von wivrn, eigenes RPM
#   opencomposite   : https://packages.fedoraproject.org/pkgs/opencomposite/opencomposite/
#
# Die Schluessel muessen zu INSTALL_PACKAGES passen, damit die Statuszeilen
# im Installations-Tab auf beiden Distros gleich heissen.
#
# NICHT dabei:
#   * xrizer — gibt es in den offiziellen Fedora-Repos NICHT, nur als COPR
#     (@xr-sig/xrizer). Steht deshalb in INSTALL_DNF_COPR statt hier.
#     'envision-xrizer' ist KEIN xrizer, sondern nur die Build-Abhaengigkeiten,
#     die Envision zum Selbstbauen braucht.
#   * lib32-* — Fedora loest 32-Bit ueber Multilib (wivrn.i686) und zieht das
#     bei Bedarf selbst; ein eigenes lib32-Paket wie im AUR gibt es nicht.
INSTALL_DNF = {
    "WiVRn / Monado": ["wivrn"],
    "opencomposite": ["opencomposite"],
}

# Warum steht 'wivrn-dashboard' hier NICHT, obwohl es das RPM gibt?
#   * 'wivrn' zieht es nicht als Abhaengigkeit mit — es waere also eine eigene
#     Zeile noetig, siehe https://packages.fedoraproject.org/pkgs/wivrn/wivrn-dashboard/
#   * das Dashboard macht auf Fedora Aerger (zweite Oberflaeche, die dieselbe
#     config.json und denselben Server anfasst)
#   * und es waere doppelt gemoppelt: wer yakuda-connect nutzt, hat die
#     Steuerung schon.
# Auf Arch bleibt es in INSTALL_PACKAGES — dort ist es Teil der ueblichen
# AUR-Installation und niemand wuerde es vermissen wollen.

# Rueckfall-Erkennung ueber die Binary im PATH: wer WiVRn selbst gebaut oder
# aus einem COPR geholt hat, hat kein passendes RPM — die Statuszeile darf
# dann trotzdem nicht "fehlt" behaupten.
DNF_BINARY_FALLBACK = {
    "WiVRn / Monado": "wivrn-server",
}

# --------------------------------------------------------------------------- #
#  Fedora-Komponenten aus einem COPR
# --------------------------------------------------------------------------- #
# Gleicher Aufbau wie INSTALL_DNF, nur mit der Zusatzangabe, welches COPR
# vorher aktiviert werden muss. Der Installations-Tab zeigt diese Eintraege
# als ganz normale Statuszeile; der Installations-Knopf aktiviert das COPR und
# installiert das Paket im selben sichtbaren Terminalfenster wie jede andere
# Installation auch. Frueher musste der Nutzer die beiden Befehle aus einem
# Hinweisfenster in die Zwischenablage holen und selbst einfuegen.
#
# Weil ein COPR ein FREMDES Repository ist (kein offizielles Fedora-Repo),
# fragt die App vorher einmal nach. Ohne Zustimmung wird der Eintrag einfach
# uebersprungen, der Rest der Installation laeuft normal weiter.
FEDORA_XRIZER_COPR = "@xr-sig/xrizer"

# Belegt auf der COPR-Projektseite selbst: dort steht als Steam-Startoption
#   VR_OVERRIDE=/run/host/usr/lib64/xrizer/runtime %command%
# Das /run/host davor ist nur die Sicht aus dem Steam-Container heraus; auf dem
# System liegt die Runtime also unter /usr/lib64/xrizer/runtime — eine Ebene
# unter dem Ordner, den wir kannten. Genau dafuer gibt es resolve_compat_root().
FEDORA_XRIZER_RUNTIME = "/usr/lib64/xrizer/runtime"

# Ebenfalls von der Projektseite: "This copr will go away after all packages
# have been reviewed and imported into Fedora." Das COPR ist also eine
# Zwischenloesung mit Ablaufdatum — ein Grund mehr, den GitHub-Weg als
# gleichwertige Quelle anzubieten und nicht als Notnagel.
INSTALL_DNF_COPR = {
    "xrizer": {"copr": FEDORA_XRIZER_COPR, "pkgs": ["xrizer"]},
}


# --------------------------------------------------------------------------- #
#  Bezugsquellen je Komponente
# --------------------------------------------------------------------------- #
# Manche Komponenten gibt es auf mehreren Wegen. Statt eine Quelle fuer alle
# vorzugeben, entscheidet der Nutzer pro Zeile im Installations-Tab.
#
# Vorauswahl ist bewusst der ERSTE Eintrag der Liste. Bei xrizer auf Fedora
# ist das das COPR: es ist der Weg, den das Projekt selbst vorgibt, und die
# Pakete sind auf dem Weg in die offiziellen Fedora-Repos. Das GitHub-Release
# bleibt als zweite Quelle daneben — fuer den Fall, dass das COPR wieder in
# Zeitueberschreitungen laeuft (Curl error 28) oder, wie auf der Projektseite
# angekuendigt, irgendwann verschwindet.
SOURCE_GITHUB = "github"
SOURCE_COPR = "copr"

SOURCE_LABELS = {
    "dnf": "Fedora-Repos",
    SOURCE_COPR: f"COPR {FEDORA_XRIZER_COPR}",
    SOURCE_GITHUB: "GitHub-Release",
    "yay": "AUR (yay)",
    "paru": "AUR (paru)",
    "native": "System",
}


def component_sources(method, name):
    """
    Welche Bezugsquellen hat diese Komponente? Liste von Kennungen, erste =
    Vorauswahl. Eine leere Liste bedeutet: nichts zu installieren (z. B.
    Ubuntu, wo nur der Status angezeigt wird).
    """
    if method == "dnf":
        if name in INSTALL_DNF_COPR:
            return [SOURCE_COPR, SOURCE_GITHUB]
        return ["dnf"]
    if method in ("yay", "paru"):
        # xrizer gibt es auch auf Arch als Release-ZIP — praktisch, wenn der
        # AUR-Build gerade klemmt.
        if name == "xrizer":
            return [method, SOURCE_GITHUB]
        return [method]
    return []


def dnf_copr_groups():
    """{Anzeigename: [Paketnamen]} — fuer die Statuszeilen im Installations-Tab."""
    return {name: list(cfg["pkgs"]) for name, cfg in INSTALL_DNF_COPR.items()}


def dnf_copr_for_package(pkg):
    """COPR-Kennung fuer ein Paket, oder None wenn es aus den Fedora-Repos kommt."""
    for cfg in INSTALL_DNF_COPR.values():
        if pkg in cfg["pkgs"]:
            return cfg["copr"]
    return None

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
        # AUR (Arch) / RPM aus dem GitHub-Release (Fedora) / Flathub (ueberall)
        "install_methods": ["aur", "rpm", "flatpak"],
        "github_repo":  "SlimeVR/SlimeVR-Server",
        # ACHTUNG: im Release liegen SlimeVR-aarch64.rpm UND SlimeVR-amd64.rpm,
        # das ARM-Paket zuerst. Das Muster bleibt deshalb bei ".rpm" — die
        # Architektur waehlt _pick_appimage_asset() selbst aus, sonst laedt ein
        # normaler PC das aarch64-Paket.
        "rpm_asset_match": ".rpm",
        "flatpak_id":   "dev.slimevr.SlimeVR",
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
        "key":          "osc-dreamchatbox",
        "name":         "OSC-DreamChatbox",
        "pkg":          "osc-dreamchatbox",
        # Vom Autor dieses Projekts (yakuda-stack) — daher hervorgehoben.
        "desc":         ("Native Linux-Alternative zu MagicChatbox (VRCOSC) – VRChat-OSC-Chatbox-Begleiter: "
                         "Status-Rotation, Now-Playing, Hardware-Monitor, Speech-to-Text und OSCQuery."),
        "desc_eng":     ("Native Linux alternative to MagicChatbox (VRCOSC) — VRChat OSC chatbox companion "
                         "(status, now-playing, hardware, speech-to-text, OSCQuery)."),
        "start_cmd":    "osc-dreamchatbox",
        "link":         "https://github.com/yakuda-stack/OSC-DreamChatbox",
        # Karte optisch hervorheben (Akzent-Rahmen + ★-Badge) — siehe _build_tool_card.
        "featured":     True,
        # AppImage / yay / paru — Vorauswahl AppImage
        "install_methods": ["appimage", "aur"],
        "github_repo":  "yakuda-stack/OSC-DreamChatbox",
        "asset_match":  "-x86_64.AppImage",
        # Releases sind (noch) alpha-getaggt — Prereleases mitberücksichtigen,
        # damit der Update-Check auch künftige Alpha-Builds findet.
        "include_prerelease": True,
        "icon_url":     "https://raw.githubusercontent.com/yakuda-stack/OSC-DreamChatbox/main/assets/icon.png",
        "config_dirs":  ["OSC-DreamChatbox"],
    },
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
        "install_methods": ["appimage", "aur", "rpm"],
        "github_repo":  "OscToys/OscGoesBrrr",
        "asset_match":  ".AppImage",
        "rpm_asset_match": ".rpm",
        "include_prerelease": True,
        "config_dirs":  ["OscGoesBrrr"],
        "icon_url":     "https://raw.githubusercontent.com/OscToys/OscGoesBrrr/main/src/icons/ogb-logo.png",
    },
    {
        "key":          "vrcft-avalonia",
        "name":         "VRCFaceTracking (Avalonia)",
        # AUR-Paket (openlfreak): "extracted AppImage version". Stellt den
        # Befehl `vrcft` bereit — deshalb ist start_cmd auch für die AppImage-
        # Methode "vrcft" (der Starter unter ~/.local/bin/vrcft).
        "pkg":          "vrcft-avalonia-bin",
        "desc":         ("Cross-Plattform-Port von VRCFaceTracking (Avalonia/.NET) — die Brücke zwischen "
                         "Face-/Eye-Tracking-Hardware und VRChat. Für Project Babble hier das "
                         "VRCFT-Babble-Modul installieren."),
        "desc_eng":     ("Cross-platform port of VRCFaceTracking (Avalonia/.NET) — the bridge between "
                         "face/eye-tracking hardware and VRChat. For Project Babble, install the "
                         "VRCFT-Babble module inside it."),
        "start_cmd":    "vrcft",
        "link":         "https://github.com/dfgHiatus/VRCFaceTracking.Avalonia",
        # AppImage (aus dem Release) / yay / paru — Vorauswahl AppImage.
        "install_methods": ["appimage", "aur"],
        "github_repo":  "dfgHiatus/VRCFaceTracking.Avalonia",
        # Release enthält genau ein Linux-AppImage -> ".AppImage" trifft eindeutig.
        "asset_match":  ".AppImage",
        "include_prerelease": False,
        "config_dirs":  ["VRCFaceTracking"],
    },
    {
        "key":          "baballonia",
        "name":         "Project Babble (Baballonia)",
        # Nur AUR: Baballonia (Avalonia/.NET) liefert offiziell KEIN AppImage
        # und kein Flatpak, sondern nur ein Release-Tarball bzw. Nix-Flake.
        # Für Arch/CachyOS ist das AUR-Paket der saubere Weg; Nicht-Arch-
        # Nutzer bekommen den Hinweis unten (note).
        "pkg":          "baballonia",
        "desc":         ("Quelloffenes Eye-/Face-Tracking für Social VR (VRChat, Resonite, ChilloutVR). "
                         "Füttert VRCFaceTracking über das VRCFT-Babble-Modul."),
        "desc_eng":     ("Open-source eye/face tracking for social VR (VRChat, Resonite, ChilloutVR). "
                         "Feeds VRCFaceTracking via the VRCFT-Babble module."),
        "start_cmd":    "baballonia",
        "link":         "https://github.com/Project-Babble/Baballonia",
        # Bewusst NUR AUR — es gibt kein AppImage/Flatpak.
        "install_methods": ["aur"],
        "config_dirs":  ["Baballonia"],
        # Nicht-Arch-Nutzer sehen sonst nur "keine Methode verfügbar" — dieser
        # Hinweis nennt die offiziellen Alternativen (Release-Tarball / Nix).
        "note":         ("Kein AppImage/Flatpak vorhanden. Nicht-Arch-Nutzer: Release-Tarball von GitHub "
                         "entpacken und starten, oder per Nix:  nix run github:Project-Babble/Baballonia"),
        "note_eng":     ("No AppImage/Flatpak available. Non-Arch users: download & extract the release "
                         "tarball from GitHub, or run via Nix:  nix run github:Project-Babble/Baballonia"),
    },
]
