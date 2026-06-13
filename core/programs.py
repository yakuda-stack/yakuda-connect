#!/usr/bin/env python3
"""
programs.py — Zentrale Programmliste für yakuda-connect
========================================================

Hier werden ALLE Programme verwaltet:
  - INSTALL_PACKAGES : Pakete die beim Erststart installiert werden (Installations-Tab)
  - TOOLS_APPS       : Programme im Tools-Tab unter "Anwendungen"
  - TOOLS_OSC        : Programme im Tools-Tab unter "OSC"

--- Tools hinzufügen ---
Einfach einen neuen Eintrag in TOOLS_APPS oder TOOLS_OSC ergänzen:

    {
        "key":       "eindeutiger-schluessel",   # intern, kein Leerzeichen
        "name":      "Anzeigename",              # wird in der UI angezeigt
        "pkg":       "aur-paketname",            # yay -S <pkg>
        "desc":      "Was macht das Programm?",  # kurze Info unter dem Namen
        "start_cmd": "startbefehl",              # z.B. "alvr_launcher"
        "link":      "https://...",              # Webseite der Entwickler (Klick-Link in UI)
    },
"""

# =============================================================================
# INSTALLATIONS-PAKETE (Erststart / Pflicht)
# =============================================================================

INSTALL_PACKAGES = {
    "WiVRn / Monado": [
        "wivrn-server",
        "lib32-wivrn-server",
    ],
    "WiVRn Dashboard": [
        "wivrn-dashboard",
    ],
    "xrizer": [
        "xrizer",
        "xrizer-common",
    ],
    "opencomposite": [
        "opencomposite-git",
    ],
    "Gaming & Vulkan Essentials": [
        "vulkan-tools",
        "vulkan-radeon",
        "lib32-vulkan-radeon",
    ],
}


# =============================================================================
# TOOLS — ANWENDUNGEN
# =============================================================================

TOOLS_APPS = [
    {
        "key":       "wayvr",
        "name":      "WayVR",
        "pkg":       "wayvr",
        "desc":      "Ein Desktop-Overlay für Wayland desktops mit integriertem Playspace Mover (wie XSOverlay)..",
        "start_cmd": "wayvr",
        "link":      "https://github.com/olekolek1000/wayvr",
    },
    {
        "key":       "protonplus",
        "name":      "ProtonPlus",
        "pkg":       "protonplus",
        "desc":      "Damit viele Spiele gut und performance-freundlich laufen. Für VRChat ist Proton GE RTSP empfohlen",
        "start_cmd": "protonplus",
        "link":      "https://github.com/nicholasgasior/protonplus",
    },
    {
        "key":       "Unityhub",
        "name":      "Unityhub for alcom",
        "pkg":       "unityhub",
        "desc":      "Der offizielle Unity Hub – wird zwingend für die Nutzung von Alcom benötigt",
        "start_cmd": "unityhub",
        "link":      "https://docs.unity.com/en-us/hub",
    },
    {
        "key":       "alcom",
        "name":      "alcom (VRChat Creator Companion)",
        "pkg":       "alcom",
        "desc":      "Eine schnelle, quelloffene Alternative zum offiziellen VRChat Creator Companion (VCC).",
        "start_cmd": "alcom",
        "link":      "https://vrc-get.anatawa12.com/de/alcom/",
    },
    {
        "key":       "Intiface Central",
        "name":      "Intiface Central",
        "pkg":       "intiface-central",
        "desc":      "Steuerzentrale für deine Toys. Kann alternativ auf dem Handy installiert werden: Einfach die Handy-IP in OscGoesBrrr eintragen, um Signale per WLAN statt Bluetooth am PC zu empfangen.",
        "start_cmd": "intiface-central",
        "link":      "https://intiface.com/#intiface-central",
    },
    {
        "key":       "android-tools",
        "name":      "android-tools",
        "pkg":       "android-tools",
        "desc":      "VR app per kabel auf VR installieren basiert auf andoid",
        "start_cmd": "",
        "link":      "https://developer.android.com/tools?hl=de",
    },
]


# =============================================================================
# TOOLS — OSC
# =============================================================================

TOOLS_OSC = [
    {
        "key":       "oscleash",
        "name":      "OSC Leash",
        "pkg":       "oscleash",
        "desc":      "OSC-Tool, um dich an einer virtuellen Leine hinterherzuziehen. Erfordert eine entsprechende Funktion im Avatar.",
        "start_cmd": "oscleash",
        "link":      "https://github.com/sakuras/oscleash",
    },
    {
        "key":       "oscgoesbrrr",
        "name":      "OSCGoesBrrr",
        "pkg":       "oscgoesbrrr",
        "desc":      "Echtes haptisches Feedback für VRChat. Unterstützt Lovense-Toys (kompatibel mit VRCFury).",
        "start_cmd": "oscgoesbrrr",
        "link":      "https://github.com/nullstalgia/OscGoesBrrr",
    },
]
