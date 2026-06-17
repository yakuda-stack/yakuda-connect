#!/usr/bin/env python3
"""
programs.py — Zentrale Programmliste für yakuda-connect
========================================================
Felder:
  key       : Eindeutiger interner Schlüssel
  name      : Anzeigename
  pkg       : AUR-Paketname
  desc      : Beschreibung (Deutsch)
  desc_eng  : Beschreibung (Englisch)
  start_cmd : Startbefehl
  link      : Webseite
"""

INSTALL_PACKAGES = {
    "WiVRn / Monado": ["wivrn-server", "lib32-wivrn-server"],
    "WiVRn Dashboard": ["wivrn-dashboard"],
    "xrizer": ["xrizer", "xrizer-common"],
    "opencomposite": ["opencomposite-git"],
}

TOOLS_APPS = [
    {
        "key":       "wayvr",
        "name":      "WayVR",
        "pkg":       "wayvr",
        "desc":      "Ein Desktop-Overlay für Wayland desktops mit integriertem Playspace Mover (wie XSOverlay).",
        "desc_eng":  "A desktop overlay for Wayland with integrated Playspace Mover (like XSOverlay).",
        "start_cmd": "wayvr",
        "link":      "https://github.com/olekolek1000/wayvr",
    },
    {
        "key":       "vrcx",
        "name":      "VRCX",
        "pkg":       "vrcx",
        "desc":      "Freundschafts-Verwaltungstool für VRChat (basiert auf Electron).",
        "desc_eng":  "Friendship management tool for VRChat (built with Electron).",
        "start_cmd": "vrcx",
        "link":      "https://github.com/vrcx-team/VRCX",
    },
    {
        "key":       "protonplus",
        "name":      "ProtonPlus",
        "pkg":       "protonplus",
        "desc":      "Damit viele Spiele gut und performance-freundlich laufen. Für VRChat ist Proton GE RTSP empfohlen.",
        "desc_eng":  "Helps many games run well and performance-friendly. Proton GE RTSP is recommended for VRChat.",
        "start_cmd": "protonplus",
        "link":      "https://github.com/nicholasgasior/protonplus",
    },
    {
        "key":       "slimevr-bin",
        "name":      "SlimeVR FBT",
        "pkg":       "slimevr-bin",
        "desc":      "VR Full Body Tracking System.",
        "desc_eng":  "VR Full Body Tracking System.",
        "start_cmd": "slimevr",
        "link":      "https://slimevr.dev/",
    },
    {
        "key":       "unityhub",
        "name":      "Unity Hub (for Alcom)",
        "pkg":       "unityhub",
        "desc":      "Der offizielle Unity Hub – wird zwingend für die Nutzung von Alcom benötigt.",
        "desc_eng":  "The official Unity Hub — required for using Alcom.",
        "start_cmd": "unityhub",
        "link":      "https://docs.unity.com/en-us/hub",
    },
    {
        "key":       "alcom",
        "name":      "Alcom (VRChat Creator Companion)",
        "pkg":       "alcom",
        "desc":      "Eine schnelle, quelloffene Alternative zum offiziellen VRChat Creator Companion (VCC).",
        "desc_eng":  "A fast, open-source alternative to the official VRChat Creator Companion (VCC).",
        "start_cmd": "alcom",
        "link":      "https://vrc-get.anatawa12.com/de/alcom/",
    },
    {
        "key":       "intiface-central",
        "name":      "Intiface Central",
        "pkg":       "intiface-central",
        "desc":      "Steuerzentrale für deine Toys. Kann alternativ auf dem Handy installiert werden: Handy-IP in OscGoesBrrr eintragen.",
        "desc_eng":  "Control hub for your toys. Can also run on your phone — just enter the phone IP in OscGoesBrrr.",
        "start_cmd": "intiface-central",
        "link":      "https://intiface.com/#intiface-central",
    },
    {
        "key":       "android-tools",
        "name":      "android-tools (ADB)",
        "pkg":       "android-tools",
        "desc":      "VR-App per Kabel auf dem Headset installieren (Android-basiert).",
        "desc_eng":  "Install VR apps directly on your headset via USB cable (Android-based).",
        "start_cmd": "",
        "link":      "https://developer.android.com/tools?hl=de",
    },
]

TOOLS_OSC = [
    {
        "key":       "oscleash",
        "name":      "OSC Leash",
        "pkg":       "oscleash",
        "desc":      "OSC-Tool, um dich an einer virtuellen Leine hinterherzuziehen. Erfordert eine entsprechende Funktion im Avatar.",
        "desc_eng":  "OSC tool to pull you around on a virtual leash. Requires a compatible avatar setup.",
        "start_cmd": "oscleash",
        "link":      "https://github.com/sakuras/oscleash",
    },
    {
        "key":       "oscgoesbrrr",
        "name":      "OSCGoesBrrr",
        "pkg":       "oscgoesbrrr",
        "desc":      "Echtes haptisches Feedback für VRChat. Unterstützt Lovense-Toys (kompatibel mit VRCFury).",
        "desc_eng":  "Real haptic feedback for VRChat. Supports Lovense toys (compatible with VRCFury).",
        "start_cmd": "oscgoesbrrr",
        "link":      "https://github.com/nullstalgia/OscGoesBrrr",
    },
]
