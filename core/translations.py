#!/usr/bin/env python3
"""
translations.py — Sprachdateien für yakuda-connect
Standard: Englisch (EN) | Verfügbar: Deutsch (DE)
"""

TRANSLATIONS = {
    "en": {
        # Sidebar
        "nav_installation":  "Installation",
        "nav_dashboard":     "Dashboard",
        "nav_streaming":     "Streaming",
        "nav_tools":         "Tools",
        "nav_settings":      "Settings",

        # Installation Tab
        "install_title":         "System Components & Installation",
        "install_subtitle":      "Check and install all required VR components.",
        "install_btn":           "Install missing components",
        "update_btn":            "Update",
        "pkg_installed":         "Installed",
        "pkg_not_installed":     "Not installed",
        "pkg_checking":          "Checking...",
        "backup_title":          "VR Environment Backup & Restore",
        "backup_btn":            "Create / Restore Backup",

        # Dashboard
        "dashboard_server":      "Server Control",
        "dashboard_start":       "Server Start",
        "dashboard_stop":        "Server Stop",
        "dashboard_active":      "Active / Running",
        "dashboard_inactive":    "Inactive",
        "dashboard_firewall":    "Fix Firewall & Open Port 9757",
        "dashboard_apk_title":   "WiVRn APK — Headset Installation (Meta Quest / Pico)",
        "dashboard_apk_info":    "Installs the WiVRn app directly via USB to your headset. USB debugging must be enabled.",
        "dashboard_apk_btn":     "⬇ Download & Install APK",
        "dashboard_apk_cancel":  "Cancel",
        "dashboard_tracking":    "Tracking & Display Options",
        "dashboard_hand":        "Hand Tracking",
        "dashboard_fbt":         "Full Body Tracking",
        "dashboard_steam":       "Enable Steam VR Tracker Device",
        "dashboard_steam_hint":  "↳ Note: OpenComposite must be active!",
        "dashboard_refresh":     "Refresh Rate:",
        "dashboard_pairing":     "Pairing Mode",
        "dashboard_pair_chk":    "Enable Pairing",
        "dashboard_pair_code":   "Pairing Code:",
        "dashboard_pair_gen":    "Generate Code...",
        "dashboard_autostart":   "Autostart Applications",
        "dashboard_app_count":   "Start programs:",
        "dashboard_headsets":    "Paired Headsets",
        "dashboard_list_btn":    "Refresh List",
        "dashboard_remove_btn":  "Remove Headset",
        "dashboard_disconnect":  "Disconnect",
        "dashboard_no_server":   "Server not running — No headsets available",
        "dashboard_browse":      "Browse...",
        "dashboard_debug":       "Debug",

        # Streaming Tab
        "streaming_title":       "Streaming Settings",
        "streaming_compat":      "Compatibility & Runtime",
        "streaming_openvr":      "OpenVR Compatibility:",
        "streaming_video":       "Video & Encoding",
        "streaming_res":         "Render Resolution per Eye:",
        "streaming_fov":         "Foveated Encoding:",
        "streaming_encoder_grp": "Hardware Encoder & Performance",
        "streaming_encoder":     "Encoder:",
        "streaming_codec":       "Codec:",
        "streaming_bitrate":     "Bitrate:",
        "streaming_openxr":      "OpenXR & Runtime Control",
        "streaming_status":      "Active Status:",
        "streaming_wivrn_btn":   "Set WiVRn as active OpenXR Runtime",
        "streaming_steam_btn":   "Set SteamVR as active OpenXR Runtime",
        "streaming_checking":    "Checking runtime...",

        # Tools Tab
        "tools_title":           "Tools",
        "tools_subtitle":        "Install and launch useful VR companion apps directly from here.",
        "tools_check_btn":       "🔄 Check for Updates",
        "tools_apps":            "Applications",
        "tools_osc":             "OSC",
        "tools_installed":       "✔ Installed",
        "tools_not_installed":   "Not installed",
        "tools_unknown":         "Unknown — please run update check",
        "tools_install_btn":     "Install",
        "tools_already":         "Already installed",
        "tools_copy":            "Copy",
        "tools_update":          "⬆ Update available",
        "tools_no_adb":          "⚠ android-tools not installed — go to Tools and install it first.",
        "tools_checking":        "Checking...",

        "install_deps_title":    "Required Dependencies (Arch Linux / AUR)",
        "install_hints_title":    "Notes & Information",
        "install_check_done":     "System check complete.",
        "install_ready":          "Ready.",
        "install_updates_available": "Some installed components have pending updates.",
        "pkg_incomplete":         "⚠ Not fully installed",
        "tools_installing":       "Installing...",
        "tools_install_error":    "Installation error",
        "tools_retry":            "Retry",
        "backup_title":           "VR Environment Backup & Restore",
        "backup_btn":             "Create / Restore Backup",
        # General
        "lang_label":            "Language:",
        "save":                  "Save",
        "cancel":                "Cancel",
        "error":                 "Error",
        "success":               "Success",
    },

    "de": {
        # Sidebar
        "nav_installation":  "Installation",
        "nav_dashboard":     "Dashboard",
        "nav_streaming":     "Streaming",
        "nav_tools":         "Tools",
        "nav_settings":      "Settings",

        # Installation Tab
        "install_title":         "Systemkomponenten & Installation",
        "install_subtitle":      "Überprüfe und installiere alle benötigten VR-Komponenten.",
        "install_btn":           "Fehlende Komponenten installieren",
        "update_btn":            "Aktualisieren",
        "pkg_installed":         "Installiert",
        "pkg_not_installed":     "Nicht installiert",
        "pkg_checking":          "Prüfe...",
        "backup_title":          "VR-Umgebungssicherung & Wiederherstellung",
        "backup_btn":            "Backup erstellen / Wiederherstellen",

        # Dashboard
        "dashboard_server":      "Server Steuerung",
        "dashboard_start":       "Server Start",
        "dashboard_stop":        "Server Stop",
        "dashboard_active":      "Aktiv / Läuft",
        "dashboard_inactive":    "Ausgeschaltet",
        "dashboard_firewall":    "Firewall fixen  Port 9757 freigeben",
        "dashboard_apk_title":   "WiVRn APK — Headset Installation (Meta Quest / Pico)",
        "dashboard_apk_info":    "Installiert die WiVRn-App direkt per USB auf dein Headset. USB-Debugging muss aktiviert sein.",
        "dashboard_apk_btn":     "⬇ APK herunterladen & installieren",
        "dashboard_apk_cancel":  "Abbrechen",
        "dashboard_tracking":    "Tracking & Display-Optionen",
        "dashboard_hand":        "Hand Tracking",
        "dashboard_fbt":         "Full Body Tracking",
        "dashboard_steam":       "Enable Steam VR Tracker Device",
        "dashboard_steam_hint":  "↳ Hinweis: OpenComposite muss active genutzt werden!",
        "dashboard_refresh":     "Refresh Rate:",
        "dashboard_pairing":     "Pairing Modus",
        "dashboard_pair_chk":    "Pairing aktivieren",
        "dashboard_pair_code":   "Pairing Code:",
        "dashboard_pair_gen":    "Generiere Code...",
        "dashboard_autostart":   "Autostart Applikationen",
        "dashboard_app_count":   "Anzahl zu startender Programme:",
        "dashboard_headsets":    "Gekoppelte Headsets",
        "dashboard_list_btn":    "Liste aktualisieren",
        "dashboard_remove_btn":  "Headset löschen",
        "dashboard_disconnect":  "Verbindung trennen",
        "dashboard_no_server":   "Server läuft nicht - Keine Headsets abrufbar",
        "dashboard_browse":      "Browse...",
        "dashboard_debug":       "Debug",

        # Streaming Tab
        "streaming_title":       "Streaming Einstellungen",
        "streaming_compat":      "Kompatibilität & Laufzeit",
        "streaming_openvr":      "OpenVR Kompatibilität:",
        "streaming_video":       "Video & Enkodierung",
        "streaming_res":         "Render Resolution pro Auge:",
        "streaming_fov":         "Foveated Encoding:",
        "streaming_encoder_grp": "Hardware-Encoder & Performance",
        "streaming_encoder":     "Encoder:",
        "streaming_codec":       "Codec:",
        "streaming_bitrate":     "Bitrate:",
        "streaming_openxr":      "OpenXR & Runtime Steuerung",
        "streaming_status":      "Aktiver Status:",
        "streaming_wivrn_btn":   "WiVRn als aktive OpenXR Runtime setzen",
        "streaming_steam_btn":   "SteamVR als aktive OpenXR Runtime setzen",
        "streaming_checking":    "Prüfe aktive Runtime...",

        # Tools Tab
        "tools_title":           "Tools",
        "tools_subtitle":        "Installiere und starte nützliche VR-Begleitprogramme direkt von hier.",
        "tools_check_btn":       "🔄 Updates prüfen",
        "tools_apps":            "Anwendungen",
        "tools_osc":             "OSC",
        "tools_installed":       "✔ Installiert",
        "tools_not_installed":   "Nicht installiert",
        "tools_unknown":         "Unbekannt — bitte Update-Check starten",
        "tools_install_btn":     "Installieren",
        "tools_already":         "Bereits installiert",
        "tools_copy":            "Kopieren",
        "tools_update":          "⬆ Update verfügbar",
        "tools_no_adb":          "⚠ android-tools nicht installiert — gehe zu Tools und installiere es zuerst.",
        "tools_checking":        "Prüfe...",

        "install_deps_title":    "Erforderliche Abhängigkeiten (Arch Linux / AUR)",
        "install_hints_title":    "Hinweise & Informationen",
        "install_check_done":     "System-Check abgeschlossen.",
        "install_ready":          "Bereit.",
        "install_updates_available": "Einige installierte Komponenten haben ausstehende Updates.",
        "pkg_incomplete":         "⚠ Nicht vollständig im System",
        "tools_installing":       "Wird installiert...",
        "tools_install_error":    "Fehler bei Installation",
        "tools_retry":            "Erneut versuchen",
        "backup_title":           "VR-Umgebung Sicherung & Wiederherstellung",
        "backup_btn":             "Backup erstellen / Wiederherstellen",
        # General
        "lang_label":            "Sprache:",
        "save":                  "Speichern",
        "cancel":                "Abbrechen",
        "error":                 "Fehler",
        "success":               "Erfolg",
    }
}

_current_lang = "en"

def set_language(lang: str):
    global _current_lang
    if lang in TRANSLATIONS:
        _current_lang = lang

def get_language() -> str:
    return _current_lang

def tr(key: str) -> str:
    lang_dict = TRANSLATIONS.get(_current_lang, TRANSLATIONS["en"])
    return lang_dict.get(key, TRANSLATIONS["en"].get(key, key))
