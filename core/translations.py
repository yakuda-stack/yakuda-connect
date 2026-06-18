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
        "streaming_rt_wivrn":    "✔ WiVRn (Active)",
        "streaming_rt_steamvr":  "✔ SteamVR (Active)",
        "streaming_rt_other":    "Other runtime active",
        "streaming_rt_none":     "No runtime set (system default)",
        "streaming_rt_error":    "Error while checking: ",
        "streaming_rt_switched": "Runtime switched",
        "streaming_rt_wivrn_ok": "WiVRn was successfully set as the default OpenXR runtime.",
        "streaming_rt_steam_ok": "SteamVR was successfully set as the default OpenXR runtime.",
        "streaming_rt_switch_err": "Could not switch runtime: ",

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
        "backup_create_btn":      "Create XR/VR Environment Backup",
        "backup_restore_btn":     "Restore XR/VR Environment",

        # Settings Tab
        "settings_title":        "Settings",
        "settings_general":      "General",
        "settings_vrchat_title": "VRChat Picture Folder Fix",
        "settings_vrchat_desc":  "Creates a symlink from the VRChat screenshot folder inside Proton to your Linux Pictures folder.\nAfter this, VRChat screenshots will appear directly in ~/Pictures/VRChat.",
        "settings_vrchat_btn":   "🔗 Create Symlink",
        "settings_controls":     "Controls",
        "openxr_group":          "OpenXR Runtime (Steam Fix)",
        "openxr_desc":           ("Fixes the Steam/pressure-vessel \"invalid Elf handle\" error by writing a correct "
                                  "OpenXR runtime file. Because writing this file can hit permission issues, you do it "
                                  "yourself: copy the path below, open that file in a text editor, replace its whole "
                                  "content with the text below and save. Tip: also add this Steam launch option:\n"
                                  "XR_RUNTIME_JSON=$HOME/.config/openxr/1/active_runtime.json PRESSURE_VESSEL_IMPORT_OPENXR_1_RUNTIMES=1 %command%"),
        "openxr_path_title":     "File path (open this file):",
        "openxr_content_title":  "Paste this into the file:",
        "openxr_copy_btn":       "Copy",
        "openxr_copied":         "Copied!",
        "openxr_fix_done":       "OpenXR runtime fixed.\nWritten with absolute paths to:\n{path}",
        "openxr_fix_backup":     "Your previous file was backed up to:\n{backup}",
        "openxr_fix_no_libs":    "Could not find the WiVRn libraries (libopenxr_wivrn.so). Is WiVRn installed?",
        "openxr_fix_not_elf":    "The found file is not a valid library:\n{path}",
        "openxr_fix_error":      "Could not write the OpenXR runtime file:",
        "openxr_status_ok":      "Status: OK — absolute paths, ready for Steam.",
        "openxr_status_broken":  "Status: broken — fix recommended (current file has a wrong/relative path).",
        "openxr_status_missing": "Status: no custom runtime file — using system default (relative paths; may fail under Steam).",
        "settings_touch_title":  "Controller Thumbstick Touch Disable",
        "settings_touch_desc":   "Disables thumbstick touch detection — useful if your controller falsely registers finger contact on the thumbstick (common with worn-out Quest/Pico controllers).",
        "settings_touch_coming": "⏳  Coming soon — waiting for WiVRn/Monado to expose this in their config API.\n    Track progress: github.com/WiVRn/WiVRn/issues/868",
        "overlay_credits": (
            "Built on the work of the WayVR community — please support the people behind it:<br>"
            "• Base watch design: <a href='https://github.com/cubee-cb/linux-vr-compat/tree/master/dotfiles/wayvr'>cubee-cb / linux-vr-compat</a><br>"
            "• SlimeVR buttons by <b>sapphire</b> (<b>#wayvr-custom</b> channel on Discord)<br>"
            "• WayVR Discord: <a href='https://discord.gg/EHAYe3tTYa'>discord.gg/EHAYe3tTYa</a>"
        ),

        # Overlay (WayVR)
        "overlay_group":         "WayVR Overlay (UI Design)",
        "overlay_design_btn":    "Update WayVR Design",
        "overlay_reset_btn":     "Reset WayVR to default",
        "overlay_slimevr_btn":   "WayVR with SlimeVR (reset buttons)",
        "overlay_installing":    "Installing design...",
        "overlay_design_ok":     "WayVR design installed and the performance overlay was activated.",
        "overlay_design_err":    "Could not install the WayVR design:",
        "overlay_reset_confirm_title": "Reset WayVR?",
        "overlay_reset_confirm_text":  "This removes the custom design and restores WayVR's standard look. A safety backup of the current state is created first. Continue?",
        "overlay_reset_ok":      "WayVR was reset to its standard look.",
        "overlay_reset_err":     "Could not reset WayVR:",
        "overlay_slimevr_ok":    "SlimeVR reset buttons were added to the WayVR watch.",
        "overlay_slimevr_off":   "SlimeVR reset buttons were removed from the WayVR watch.",
        "overlay_slimevr_err":   "Could not change the SlimeVR UI:",
        "overlay_need_design":   "Please run 'Update WayVR Design' first.",
        "overlay_popup_title":   "WayVR installed",
        "overlay_popup_text":    "For a nicer UI design and customization, head to Settings → WayVR Overlay. There you can apply the design and add the SlimeVR buttons at the push of a button.",

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
        "dashboard_firewall":    "Firewall fixen & Port 9757 freigeben",
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
        "streaming_rt_wivrn":    "✔ WiVRn (Aktiv)",
        "streaming_rt_steamvr":  "✔ SteamVR (Aktiv)",
        "streaming_rt_other":    "Andere Runtime aktiv",
        "streaming_rt_none":     "Keine Runtime gesetzt (System-Standard)",
        "streaming_rt_error":    "Fehler beim Prüfen: ",
        "streaming_rt_switched": "Runtime gewechselt",
        "streaming_rt_wivrn_ok": "WiVRn wurde erfolgreich als Standard-OpenXR-Runtime gesetzt.",
        "streaming_rt_steam_ok": "SteamVR wurde erfolgreich als Standard-OpenXR-Runtime gesetzt.",
        "streaming_rt_switch_err": "Konnte Runtime nicht wechseln: ",

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
        "backup_create_btn":      "XR/VR Umgebung backup machen",
        "backup_restore_btn":     "XR/VR Umgebung wiederherstellen",

        # Settings Tab
        "settings_title":        "Einstellungen",
        "settings_general":      "Allgemein",
        "settings_vrchat_title": "VRChat Bilderordner-Fix",
        "settings_vrchat_desc":  "Erstellt einen Symlink vom VRChat-Screenshot-Ordner in Proton zu deinem Linux-Bilderordner.\nDanach erscheinen VRChat-Screenshots direkt in ~/Pictures/VRChat.",
        "settings_vrchat_btn":   "🔗 Symlink erstellen",
        "settings_controls":     "Steuerung",
        "openxr_group":          "OpenXR-Runtime (Steam-Fix)",
        "openxr_desc":           ("Behebt den Steam-/pressure-vessel-Fehler \"invalid Elf handle\", indem eine korrekte "
                                  "OpenXR-Runtime-Datei. Da das Schreiben dieser Datei Rechte-Probleme machen kann, machst "
                                  "du es selbst: den Pfad unten kopieren, die Datei im Texteditor oeffnen, ihren Inhalt "
                                  "durch den Text unten ersetzen und speichern. Tipp: zusaetzlich diese Steam-Startoption:\n"
                                  "XR_RUNTIME_JSON=$HOME/.config/openxr/1/active_runtime.json PRESSURE_VESSEL_IMPORT_OPENXR_1_RUNTIMES=1 %command%"),
        "openxr_path_title":     "Dateipfad (diese Datei oeffnen):",
        "openxr_content_title":  "Das in die Datei eintragen:",
        "openxr_copy_btn":       "Kopieren",
        "openxr_copied":         "Kopiert!",
        "openxr_fix_done":       "OpenXR-Runtime repariert.\nMit absoluten Pfaden geschrieben nach:\n{path}",
        "openxr_fix_backup":     "Deine vorherige Datei wurde gesichert unter:\n{backup}",
        "openxr_fix_no_libs":    "WiVRn-Bibliotheken (libopenxr_wivrn.so) nicht gefunden. Ist WiVRn installiert?",
        "openxr_fix_not_elf":    "Die gefundene Datei ist keine gültige Bibliothek:\n{path}",
        "openxr_fix_error":      "OpenXR-Runtime-Datei konnte nicht geschrieben werden:",
        "openxr_status_ok":      "Status: OK — absolute Pfade, bereit für Steam.",
        "openxr_status_broken":  "Status: defekt — Reparatur empfohlen (aktuelle Datei hat einen falschen/relativen Pfad).",
        "openxr_status_missing": "Status: keine eigene Runtime-Datei — System-Standard aktiv (relative Pfade; kann unter Steam scheitern).",
        "settings_touch_title":  "Controller-Thumbstick-Touch deaktivieren",
        "settings_touch_desc":   "Deaktiviert die Touch-Erkennung des Thumbsticks — nützlich, wenn dein Controller fälschlicherweise Fingerkontakt am Thumbstick meldet (häufig bei abgenutzten Quest/Pico-Controllern).",
        "settings_touch_coming": "⏳  Demnächst — wartet darauf, dass WiVRn/Monado dies in der Config-API verfügbar macht.\n    Fortschritt verfolgen: github.com/WiVRn/WiVRn/issues/868",
        "overlay_credits": (
            "Basiert auf der Arbeit der WayVR-Community — bitte unterstütze die Leute dahinter:<br>"
            "• Basis-Watch-Design: <a href='https://github.com/cubee-cb/linux-vr-compat/tree/master/dotfiles/wayvr'>cubee-cb / linux-vr-compat</a><br>"
            "• SlimeVR-Buttons von <b>sapphire</b> (Channel <b>#wayvr-custom</b> auf Discord)<br>"
            "• WayVR-Discord: <a href='https://discord.gg/EHAYe3tTYa'>discord.gg/EHAYe3tTYa</a>"
        ),

        # Overlay (WayVR)
        "overlay_group":         "WayVR Overlay (UI-Design)",
        "overlay_design_btn":    "WayVR-Design aktualisieren",
        "overlay_reset_btn":     "WayVR auf Standard zurücksetzen",
        "overlay_slimevr_btn":   "WayVR mit SlimeVR (Reset-Buttons)",
        "overlay_installing":    "Design wird installiert...",
        "overlay_design_ok":     "WayVR-Design installiert und das Performance-Overlay wurde aktiviert.",
        "overlay_design_err":    "WayVR-Design konnte nicht installiert werden:",
        "overlay_reset_confirm_title": "WayVR zurücksetzen?",
        "overlay_reset_confirm_text":  "Dadurch wird das Custom-Design entfernt und WayVRs Standard-Aussehen wiederhergestellt. Vorher wird eine Sicherheitskopie des aktuellen Zustands angelegt. Fortfahren?",
        "overlay_reset_ok":      "WayVR wurde auf das Standard-Aussehen zurückgesetzt.",
        "overlay_reset_err":     "WayVR konnte nicht zurückgesetzt werden:",
        "overlay_slimevr_ok":    "SlimeVR-Reset-Buttons wurden zur WayVR-Watch hinzugefügt.",
        "overlay_slimevr_off":   "SlimeVR-Reset-Buttons wurden aus der WayVR-Watch entfernt.",
        "overlay_slimevr_err":   "SlimeVR-UI konnte nicht geändert werden:",
        "overlay_need_design":   "Bitte zuerst 'WayVR-Design aktualisieren' ausführen.",
        "overlay_popup_title":   "WayVR installiert",
        "overlay_popup_text":    "Für ein schöneres UI-Design und Anpassungen gehe zu Einstellungen → WayVR Overlay. Dort kannst du per Knopfdruck das Design anwenden und die SlimeVR-Buttons hinzufügen.",

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
