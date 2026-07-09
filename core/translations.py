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
        "dashboard_check":       "Check Server Status",
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
        "dashboard_autostart_reset": "Reset start Timer",
        "dashboard_autostart_kill":  "🧹 Kill Apps",
        "autostart_kill_tip":        "Close all running autostart apps now (server keeps running)",
        "autostart_kill_done":       "✓ Closed",
        "autostart_reset_title":     "Autostart readiness",
        "autostart_reset_no_server": "Please start the server first — there is nothing to arm yet.",
        "autostart_reset_done":      "✓ Armed",
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
        "streaming_prio":        "VR Priority (Async Reprojection)",
        "streaming_prio_desc":    "Grants wivrn-server the CAP_SYS_NICE permission so it can run reprojection at high priority. Helps keep motion smooth when frames are dropped. Needs to be re-applied after a WiVRn update.",
        "streaming_prio_btn":     "Enable VR Priority",
        "streaming_prio_on":      "✔ Enabled (CAP_SYS_NICE set)",
        "streaming_prio_off":     "Not enabled",
        "streaming_prio_missing": "wivrn-server not found",
        "streaming_prio_unsupported": "Not applicable (Nix/Flatpak install)",
        "streaming_prio_ok_title": "VR Priority enabled",
        "streaming_prio_ok_text": "wivrn-server now has high-priority permission. Restart the server for it to take effect.",
        "streaming_prio_err":     "Could not set VR priority:",
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

        # App self-update (arrow next to the app version)
        "app_version_label":      "App Version:",
        "app_update_tooltip":     "Update available: {version} — click to update yakuda-connect",
        "app_update_title":       "yakuda-connect Update",
        "app_update_confirm":     "A new version ({version}) is available.\n\nUpdate yakuda-connect now? A terminal window will open and may ask for your password.",
        "app_update_restart":     "Update complete. Restart yakuda-connect now to load the new version?",
        "app_update_failed":      "The update could not be completed. Please check the terminal output, or run the installer manually.",

        # Community & Updates (Settings, top)
        "community_group":        "Community & Updates",
        "community_check_btn":    "🔄 Check for updates",
        "community_discord_btn":  "💬 Discord",
        "community_donate_btn":   "❤️ Donate (PayPal)",
        "community_version":      "Current version: {version}",
        "community_checking":     "Checking for updates ...",
        "community_uptodate":     "You are already on the latest version ({version}).",
        "community_check_failed": "Could not check for updates. No connection to GitHub?",

        # Performance-Tipps (Streaming-Tab, unter VR-Priorität)
        "perf_tips":              ("<b>More latency tips:</b><br>"
                                   "• Use a dedicated 5&nbsp;GHz / 6&nbsp;GHz WiFi (headset as the only client, PC on LAN cable)<br>"
                                   "• Streaming tab: prefer the hardware encoder (vaapi/nvenc) instead of x264<br>"
                                   "• H.265/AV1 at 80–120 Mbps is usually smoother than H.264 at very high bitrates<br>"
                                   "• Foveated encoding reduces encode time — 50% is a good start<br>"
                                   "• Set your GPU power profile to performance while playing"),

        # Custom kill commands (Settings, at the bottom)
        "killcmd_group":          "Custom kill commands (Autostart)",
        "killcmd_desc":           ("The <b>Kill apps</b> button on the dashboard already terminates all "
                                   "autostart programs the normal way (SIGTERM → SIGKILL). Some apps ignore "
                                   "that though — Electron apps (VRCX) fork into several processes, some "
                                   "AppImages run under a different process name, and a few tools want to be "
                                   "closed with their own command. Add such special cases here: they run "
                                   "in addition to the normal kill, right before it."),
        "killcmd_col_label":      "Name / note",
        "killcmd_col_command":    "Command (shell)",
        "killcmd_placeholder_lbl":"e.g. VRCX",
        "killcmd_placeholder_cmd":"e.g. pkill -f VRCX.AppImage",
        "killcmd_add_btn":        "＋ Add",
        "killcmd_del_tooltip":    "Remove this entry",
        "killcmd_save_btn":       "💾 Save",
        "killcmd_saved":          "Saved.",
        "killcmd_warn":           ("⚠ These commands are executed as a shell — only enter commands you trust. "
                                   "Missing entries are simply skipped."),

        "pkg_incomplete":         "⚠ Not fully installed",
        "tools_installing":       "Installing...",
        "tools_install_error":    "Installation error",
        "tools_retry":            "Retry",
        "tools_delete":           "🗑 Remove",
        "tools_deleting":         "Removing...",
        "tools_update_btn":       "⬆ Update",
        "tools_updating":         "Updating...",
        "tools_appimage_ok":      "Installed (AppImage)",
        "tools_pm_ok":            "Installed ({helper})",
        "tools_flatpak_ok":       "Installed (Flatpak)",
        "native_update_title":    "Manual update required",
        "native_update_text":     "WiVRn is installed natively (managed by you / your distro). yakuda-connect can't update it automatically.\n\nPlease update it the same way you installed it (your package manager or your build).",
        "native_install_title":   "Native installation",
        "native_install_text":    "WiVRn is already installed natively and managed by you. There's nothing for yakuda-connect to install here.\n\nIf you'd rather use Flatpak, pick 'Flatpak' from the dropdown.",
        "nixos_title":            "NixOS detected",
        "nixos_no_flatpak_text":  "yakuda-connect installs apps via Flatpak or AppImage on NixOS.\n\nFlatpak isn't enabled yet. To enable it, add this to your configuration.nix:\n\n    services.flatpak.enable = true;\n\nthen run 'sudo nixos-rebuild switch' and add Flathub:\n\n    flatpak remote-add --if-not-exists --user flathub https://flathub.org/repo/flathub.flatpakrepo\n\nAfter that, restart yakuda-connect.",
        "nixos_add_flathub_title":"Set up Flathub?",
        "nixos_add_flathub_text": "Flatpak is available, but the Flathub remote is missing.\n\nShould yakuda-connect add the Flathub remote now (per user, no root needed)?",
        "nixos_flathub_ok":       "Flathub remote added successfully.",
        "nixos_flathub_fail":     "Could not add the Flathub remote. Please add it manually.",
        "tools_no_method":        "⚠ Only on Arch (yay/paru)",
        "tools_native":           "⚠ Existing config found",
        "tools_delete_title":     "Removed",
        "tools_delete_text":      "{name} (AppImage), the launcher and the desktop entry were removed.\n\nNote: the config folder{path} was NOT deleted. If you also want to remove it, please do so manually.",
        "tools_delete_config_title": "Delete configuration?",
        "tools_delete_config_text":  "Do you also want to delete the configuration folder{path} of {name}?\n\nYes = remove it as well, No = keep it.",
        "tools_native_title":     "Existing configuration found",
        "tools_native_text":      "A config folder for {name} already exists{path}, so it may already be set up on this system.\n\nInstalling the AppImage on top can cause conflicts. Install the AppImage anyway?",
        "backup_title":           "VR Environment Backup & Restore",
        "backup_btn":             "Create / Restore Backup",
        "backup_create_btn":      "Create XR/VR Environment Backup",
        "backup_restore_btn":     "Restore XR/VR Environment",

        # Settings Tab
        "settings_title":        "Settings",
        "settings_general":      "General",
        "settings_vrchat_title": "VRChat Picture Folder Fix",
        "settings_vrchat_desc":  "Creates a symlink from the VRChat screenshot folder inside Proton to your Linux Pictures folder.\nAfter this, VRChat screenshots will appear directly in ~/Pictures/VRChat.",
        "settings_vrchat_desc_short": "Connects your VRChat pictures folder with your Linux pictures folder via a symlink to easily access your VR screenshots.",
        "settings_vrchat_btn":   "🔗 Create Symlink",
        "settings_controls":     "Controls",
        "openxr_group":          "OpenXR Runtime (Steam Fix)",
        "openxr_desc":           ("Fixes the Steam/pressure-vessel \"invalid Elf handle\" error by writing a correct "
                                  "OpenXR runtime file (absolute paths to the WiVRn libraries). "
                                  "Click the button — your previous file is backed up automatically. "
                                  "Tip: also add this Steam launch option:\n"
                                  "XR_RUNTIME_JSON=$HOME/.config/openxr/1/active_runtime.json PRESSURE_VESSEL_IMPORT_OPENXR_1_RUNTIMES=1 %command%"),
        "openxr_fix_btn":        "🔧 Fix now (automatic)",
        "openxr_manual_show":    "▸ Manual fix (show)",
        "openxr_manual_hide":    "▾ Manual fix (hide)",
        "openxr_manual_hint":    "If the automatic fix fails (permissions), do it manually: open the file below and replace its whole content.",
        "openxr_fix_root_ask":   "Writing the file failed (permission problem — the file or folder probably belongs to root).\n\nRetry with administrator rights? A password prompt will appear, and afterwards the folder is handed back to your user so future fixes work without root.",
        "openxr_fix_cancelled":  "The fix was cancelled (no administrator password entered).",
        "openxr_path_title":     "File path (open this file):",
        "openxr_content_title":  "Paste this into the file:",
        "openxr_copy_btn":       "Copy",
        "streaming_flatpak_launch_title": "Steam launch option (Flatpak)",
        "streaming_flatpak_launch_desc":  "Because WiVRn runs as a Flatpak, Steam needs read/write access to the WiVRn Flatpak. Add this launch option to each VR game (Steam → game → Properties → Launch Options), then click Copy:",
        "openxr_copied":         "Copied!",
        "openxr_fix_done":       "OpenXR runtime fixed.\nWritten with absolute paths to:\n{path}",
        "openxr_fix_backup":     "Your previous file was backed up to:\n{backup}",
        "openxr_fix_no_libs":    "Could not find the WiVRn libraries (libopenxr_wivrn.so). Is WiVRn installed?",
        "openxr_fix_not_elf":    "The found file is not a valid library:\n{path}",
        "openxr_fix_error":      "Could not write the OpenXR runtime file:",
        "openxr_status_ok":      "Status: OK — absolute paths, ready for Steam.",
        "openxr_status_broken":  "Status: broken — fix recommended (current file has a wrong/relative path).",
        "openxr_status_missing": "Status: no custom runtime file — using system default (relative paths; may fail under Steam).",
        "oscquery_group":         "Quick OSC Query Fix",
        "oscquery_desc":          ("If OSC bugs occur (parameters not arriving, tools not reacting), this enables OSCQuery "
                                   "directly in the config of every supported program — all other settings in the file stay "
                                   "untouched. Only existing configs are changed (start the program once first)."),
        "oscquery_fix_btn":       "🔧 Fix OSCQuery",
        "oscquery_show_programs": "▸ Show supported programs ({n})",
        "oscquery_hide_programs": "▾ Hide supported programs",
        "oscquery_detail_path":   "path:     ",
        "oscquery_detail_param":  "parameter:",
        "oscquery_msg_fixed":      "fixed",
        "oscquery_msg_already":    "already set",
        "oscquery_msg_not_found":  "config not found — program not installed or never started",
        "oscquery_msg_unreadable": "config unreadable",
        "oscquery_msg_write_failed": "could not write config",
        "oscquery_restart_hint":  "↻ Restart the programs to apply the change.",

        # Games Tab
        "nav_games":              "Games",
        "games_title":            "VR Games",
        "games_subtitle":         ("Your installed Steam VR games with recommended Proton versions and launch "
                                   "options. Detected games are saved, so Steam is not re-scanned on every visit."),
        "games_scan_btn":         "🔍 Scan games",
        "games_click_hint":       "Click a game tile to expand its Proton recommendations, launch options and fixes.",
        "games_fixes_section":    "Fixes:",
        "games_section_tested":   "Tested VR Games",
        "games_section_untested": "Untested VR Games (Auto-Recommendation)",
        "games_untested_suffix":  "(untested)",
        "games_role_alt_ge":      "Alternative (Recommended for Video/Codec fixes)",
        "games_play_btn":         "▶ Play",
        "games_use_btn":          "Use",
        "games_active_badge":     "✓ Active",
        "games_use_applied":      "Proton set for this game: {tool}",
        "games_use_default":      "Steam default Proton set for this game.",
        "games_tool_missing":     "This Proton version is not installed yet — install it first (e.g. via ProtonPlus).",
        "games_steam_restart_hint": "Steam is currently running — the change takes effect after a Steam restart.",
        "games_play_starting":    "Launch options saved — starting {name} via Steam...",
        "games_play_failed":      "Could not launch Steam (steam not found?).",
        "games_options_failed":   "Warning: launch options could not be written ({err}).",
        "games_params_placeholder": "No launch options stored for this game — enter your own here if needed.",
        "games_info_tooltip":     "How do I change the Proton version and launch options in Steam?",
        "games_scanning":         "Scanning Steam libraries...",
        "games_found":            "{n} supported VR game(s) detected.",
        "games_none":             "No supported VR games found. Is Steam installed and are the games downloaded?",
        "games_recommended":      "⭐ Recommended for you",
        "games_recommended_cachyos": "⭐ Recommended (CachyOS)",
        "games_role_main":        "Recommended (default)",
        "games_role_cachyos":     "Recommended for CachyOS users",
        "games_role_alt":         "Alternative",
        "games_proton_section":   "Proton versions:",
        "games_params_section":   "Launch options ({gpu} GPU detected):",
        "games_params_section_unknown": "Launch options:",
        "games_gpu_amd":          "AMD",
        "games_gpu_nvidia":       "NVIDIA",
        "games_copy_btn":         "Copy",
        "games_copied":           "Copied!",
        "games_pp_install_btn":   "⬇ Install via ProtonPlus",
        "games_pp_missing":       "Install ProtonPlus (Tools tab) to install Proton versions directly from here.",
        "games_pp_running":       "ProtonPlus is running in the terminal — pick the version listed above.",
        "games_pp_done":          "ProtonPlus finished. Now select the version in Steam (see the i button at the top).",
        "games_pp_steam_note":    "Comes with Steam itself (Steam → Settings → Compatibility).",
        "games_info_title":       "Proton version & launch options in Steam",
        "games_info_text": (
            "<b>Change the Proton version of a game:</b><br>"
            "1. Open Steam and right-click the game in your library<br>"
            "2. <i>Properties…</i> → <i>Compatibility</i><br>"
            "3. Check <i>Force the use of a specific Steam Play compatibility tool</i><br>"
            "4. Pick the recommended version from the dropdown (e.g. installed via ProtonPlus)<br>"
            "5. If a freshly installed version is missing from the list: restart Steam first<br><br>"
            "<b>Set launch options:</b><br>"
            "1. Right-click the game → <i>Properties…</i> → <i>General</i><br>"
            "2. Paste the copied launch options into the <i>Launch Options</i> field at the bottom<br><br>"
            "<i>Tip: the Copy buttons on each game card put the right values into your clipboard.</i>"
        ),
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
        "flatpak_firstrun_title": "Almost done – start WiVRn once",
        "flatpak_firstrun_text":  "WiVRn was installed via Flatpak.\n\nPlease start WiVRn once and click through the setup wizard, then you can close it again. Only the first launch creates all the needed folders (config, OpenXR, OpenVR) correctly.\n\nAfter that, yakuda-connect can write its settings properly.",
        "flatpak_firstrun_launch":"Start WiVRn now",
        "flatpak_firstrun_later": "I'll do it myself",
        "flatpak_firstrun_launch_fail": "Could not start WiVRn: ",
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
        "dashboard_check":       "Serverstatus prüfen",
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
        "dashboard_autostart_reset": "Timer zurücksetzen",
        "dashboard_autostart_kill":  "🧹 Apps schließen",
        "autostart_kill_tip":        "Alle laufenden Autostart-Apps sofort schließen (Server läuft weiter)",
        "autostart_kill_done":       "✓ Geschlossen",
        "autostart_reset_title":     "Autostart-Bereitschaft",
        "autostart_reset_no_server": "Bitte zuerst den Server starten — es gibt noch nichts scharfzuschalten.",
        "autostart_reset_done":      "✓ Scharf",
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
        "streaming_prio":        "VR-Priorität (Async Reprojection)",
        "streaming_prio_desc":    "Gibt wivrn-server die Berechtigung CAP_SYS_NICE, damit er die Reprojektion mit hoher Priorität fahren kann. Hält die Bewegung flüssig, wenn Frames ausfallen. Muss nach einem WiVRn-Update erneut gesetzt werden.",
        "streaming_prio_btn":     "VR-Priorität aktivieren",
        "streaming_prio_on":      "✔ Aktiv (CAP_SYS_NICE gesetzt)",
        "streaming_prio_off":     "Nicht aktiv",
        "streaming_prio_missing": "wivrn-server nicht gefunden",
        "streaming_prio_unsupported": "Nicht nötig/möglich (Nix-/Flatpak-Installation)",
        "streaming_prio_ok_title": "VR-Priorität aktiviert",
        "streaming_prio_ok_text": "wivrn-server hat jetzt die Hochprioritäts-Berechtigung. Starte den Server neu, damit es wirkt.",
        "streaming_prio_err":     "VR-Priorität konnte nicht gesetzt werden:",
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

        # Selbst-Update der App (Pfeil neben der App-Version)
        "app_version_label":      "App-Version:",
        "app_update_tooltip":     "Update verfügbar: {version} — klicken, um yakuda-connect zu aktualisieren",
        "app_update_title":       "yakuda-connect Update",
        "app_update_confirm":     "Eine neue Version ({version}) ist verfügbar.\n\nyakuda-connect jetzt aktualisieren? Es öffnet sich ein Terminal-Fenster, das ggf. nach deinem Passwort fragt.",
        "app_update_restart":     "Update abgeschlossen. yakuda-connect jetzt neu starten, um die neue Version zu laden?",
        "app_update_failed":      "Das Update konnte nicht abgeschlossen werden. Bitte prüfe die Terminal-Ausgabe oder führe den Installer manuell aus.",

        # Community & Updates (Settings, ganz oben)
        "community_group":        "Community & Updates",
        "community_check_btn":    "🔄 Nach Updates suchen",
        "community_discord_btn":  "💬 Discord",
        "community_donate_btn":   "❤️ Spenden (PayPal)",
        "community_version":      "Aktuelle Version: {version}",
        "community_checking":     "Suche nach Updates ...",
        "community_uptodate":     "Du bist bereits auf der neuesten Version ({version}).",
        "community_check_failed": "Update-Prüfung fehlgeschlagen. Keine Verbindung zu GitHub?",

        # Performance-Tipps (Streaming-Tab, unter VR-Priorität)
        "perf_tips":              ("<b>Weitere Latenz-Tipps:</b><br>"
                                   "• Eigenes 5&nbsp;GHz / 6&nbsp;GHz WLAN nutzen (Headset als einziger Client, PC per LAN-Kabel)<br>"
                                   "• Streaming-Tab: Hardware-Encoder (vaapi/nvenc) statt x264 bevorzugen<br>"
                                   "• H.265/AV1 mit 80–120 Mbit/s läuft meist runder als H.264 mit sehr hoher Bitrate<br>"
                                   "• Foveated Encoding senkt die Encode-Zeit — 50% ist ein guter Start<br>"
                                   "• GPU-Powerprofil beim Spielen auf Performance stellen"),

        # Eigene Kill-Befehle (Settings, ganz unten)
        "killcmd_group":          "Eigene Kill-Befehle (Autostart)",
        "killcmd_desc":           ("Der <b>Apps schließen</b>-Button im Dashboard beendet die Autostart-Programme "
                                   "bereits auf normalem Weg (SIGTERM → SIGKILL). Manche Apps ignorieren das "
                                   "aber — Electron-Apps (VRCX) forken sich in mehrere Prozesse, manche "
                                   "AppImages laufen unter anderem Prozessnamen, und einzelne Tools wollen mit "
                                   "einem eigenen Befehl geschlossen werden. Solche Sonderfälle kommen hier "
                                   "rein: sie laufen zusätzlich zum normalen Kill, direkt davor."),
        "killcmd_col_label":      "Name / Notiz",
        "killcmd_col_command":    "Befehl (Shell)",
        "killcmd_placeholder_lbl":"z. B. VRCX",
        "killcmd_placeholder_cmd":"z. B. pkill -f VRCX.AppImage",
        "killcmd_add_btn":        "＋ Hinzufügen",
        "killcmd_del_tooltip":    "Diesen Eintrag entfernen",
        "killcmd_save_btn":       "💾 Speichern",
        "killcmd_saved":          "Gespeichert.",
        "killcmd_warn":           ("⚠ Die Befehle werden als Shell ausgeführt — nur eingeben, was du dir "
                                   "vertraust. Leere Einträge werden einfach übersprungen."),

        "pkg_incomplete":         "⚠ Nicht vollständig im System",
        "tools_installing":       "Wird installiert...",
        "tools_install_error":    "Fehler bei Installation",
        "tools_retry":            "Erneut versuchen",
        "tools_delete":           "🗑 Löschen",
        "tools_deleting":         "Wird gelöscht...",
        "tools_update_btn":       "⬆ Aktualisieren",
        "tools_updating":         "Wird aktualisiert...",
        "tools_appimage_ok":      "Installiert (AppImage)",
        "tools_pm_ok":            "Installiert ({helper})",
        "tools_flatpak_ok":       "Installiert (Flatpak)",
        "native_update_title":    "Manuelles Update nötig",
        "native_update_text":     "WiVRn ist nativ installiert (von dir bzw. deiner Distribution verwaltet). yakuda-connect kann es nicht automatisch aktualisieren.\n\nBitte aktualisiere es auf demselben Weg, wie du es installiert hast (dein Paketmanager oder dein eigener Build).",
        "native_install_title":   "Native Installation",
        "native_install_text":    "WiVRn ist bereits nativ installiert und wird von dir selbst verwaltet. yakuda-connect muss hier nichts installieren.\n\nWenn du lieber Flatpak nutzen möchtest, wähle im Dropdown 'Flatpak'.",
        "nixos_title":            "NixOS erkannt",
        "nixos_no_flatpak_text":  "yakuda-connect installiert Programme auf NixOS über Flatpak oder AppImage.\n\nFlatpak ist noch nicht aktiviert. Zum Aktivieren füge dies in deine configuration.nix ein:\n\n    services.flatpak.enable = true;\n\nführe dann 'sudo nixos-rebuild switch' aus und füge Flathub hinzu:\n\n    flatpak remote-add --if-not-exists --user flathub https://flathub.org/repo/flathub.flatpakrepo\n\nStarte danach yakuda-connect neu.",
        "nixos_add_flathub_title":"Flathub einrichten?",
        "nixos_add_flathub_text": "Flatpak ist vorhanden, aber das Flathub-Remote fehlt.\n\nSoll yakuda-connect das Flathub-Remote jetzt hinzufügen (pro Benutzer, ohne root)?",
        "nixos_flathub_ok":       "Flathub-Remote erfolgreich hinzugefügt.",
        "nixos_flathub_fail":     "Flathub-Remote konnte nicht hinzugefügt werden. Bitte manuell hinzufügen.",
        "tools_no_method":        "⚠ Nur auf Arch (yay/paru)",
        "tools_native":           "⚠ Konfiguration vorhanden",
        "tools_delete_title":     "Entfernt",
        "tools_delete_text":      "{name} (AppImage), der Startbefehl und der Desktop-Eintrag wurden entfernt.\n\nHinweis: Der Konfigurationsordner{path} wurde NICHT gelöscht. Wenn du ihn auch entfernen möchtest, musst du das selbst tun.",
        "tools_delete_config_title": "Konfiguration löschen?",
        "tools_delete_config_text":  "Möchtest du auch den Konfigurationsordner{path} von {name} löschen?\n\nJa = ebenfalls löschen, Nein = behalten.",
        "tools_native_title":     "Konfiguration bereits vorhanden",
        "tools_native_text":      "Für {name} existiert bereits ein Konfigurationsordner{path} – das Programm ist also evtl. schon auf diesem System eingerichtet.\n\nDie AppImage zusätzlich zu installieren kann zu Konflikten führen. AppImage trotzdem installieren?",
        "backup_title":           "VR-Umgebung Sicherung & Wiederherstellung",
        "backup_btn":             "Backup erstellen / Wiederherstellen",
        "backup_create_btn":      "XR/VR Umgebung backup machen",
        "backup_restore_btn":     "XR/VR Umgebung wiederherstellen",

        # Settings Tab
        "settings_title":        "Einstellungen",
        "settings_general":      "Allgemein",
        "settings_vrchat_title": "VRChat Bilderordner-Fix",
        "settings_vrchat_desc":  "Erstellt einen Symlink vom VRChat-Screenshot-Ordner in Proton zu deinem Linux-Bilderordner.\nDanach erscheinen VRChat-Screenshots direkt in ~/Pictures/VRChat.",
        "settings_vrchat_desc_short": "Verbindet deinen VRChat-Bilderordner über einen Symlink mit deinem Linux-Bilderordner, damit du einfach auf deine VR-Screenshots zugreifen kannst.",
        "settings_vrchat_btn":   "🔗 Symlink erstellen",
        "settings_controls":     "Steuerung",
        "openxr_group":          "OpenXR-Runtime (Steam-Fix)",
        "openxr_desc":           ("Behebt den Steam-/pressure-vessel-Fehler \"invalid Elf handle\", indem eine korrekte "
                                  "OpenXR-Runtime-Datei mit absoluten Pfaden zu den WiVRn-Bibliotheken geschrieben wird. "
                                  "Einfach auf den Button klicken — deine bisherige Datei wird automatisch gesichert. "
                                  "Tipp: zusaetzlich diese Steam-Startoption:\n"
                                  "XR_RUNTIME_JSON=$HOME/.config/openxr/1/active_runtime.json PRESSURE_VESSEL_IMPORT_OPENXR_1_RUNTIMES=1 %command%"),
        "openxr_fix_btn":        "🔧 Jetzt fixen (automatisch)",
        "openxr_manual_show":    "▸ Manueller Fix (anzeigen)",
        "openxr_manual_hide":    "▾ Manueller Fix (ausblenden)",
        "openxr_manual_hint":    "Falls der automatische Fix scheitert (Rechte), geht es manuell: die Datei unten oeffnen und ihren kompletten Inhalt ersetzen.",
        "openxr_fix_root_ask":   "Das Schreiben der Datei ist fehlgeschlagen (Rechteproblem — die Datei oder der Ordner gehoert vermutlich root).\n\nMit Administrator-Rechten erneut versuchen? Es erscheint eine Passwortabfrage, danach wird der Ordner wieder deinem Benutzer uebergeben, damit kuenftige Fixes ohne Root funktionieren.",
        "openxr_fix_cancelled":  "Der Fix wurde abgebrochen (kein Administrator-Passwort eingegeben).",
        "openxr_path_title":     "Dateipfad (diese Datei oeffnen):",
        "openxr_content_title":  "Das in die Datei eintragen:",
        "openxr_copy_btn":       "Kopieren",
        "streaming_flatpak_launch_title": "Steam-Startoption (Flatpak)",
        "streaming_flatpak_launch_desc":  "Da WiVRn als Flatpak läuft, braucht Steam Lese-/Schreibzugriff auf das WiVRn-Flatpak. Füge diese Startoption bei jedem VR-Spiel hinzu (Steam → Spiel → Eigenschaften → Startoptionen) und klicke dann auf Kopieren:",
        "openxr_copied":         "Kopiert!",
        "openxr_fix_done":       "OpenXR-Runtime repariert.\nMit absoluten Pfaden geschrieben nach:\n{path}",
        "openxr_fix_backup":     "Deine vorherige Datei wurde gesichert unter:\n{backup}",
        "openxr_fix_no_libs":    "WiVRn-Bibliotheken (libopenxr_wivrn.so) nicht gefunden. Ist WiVRn installiert?",
        "openxr_fix_not_elf":    "Die gefundene Datei ist keine gültige Bibliothek:\n{path}",
        "openxr_fix_error":      "OpenXR-Runtime-Datei konnte nicht geschrieben werden:",
        "openxr_status_ok":      "Status: OK — absolute Pfade, bereit für Steam.",
        "openxr_status_broken":  "Status: defekt — Reparatur empfohlen (aktuelle Datei hat einen falschen/relativen Pfad).",
        "openxr_status_missing": "Status: keine eigene Runtime-Datei — System-Standard aktiv (relative Pfade; kann unter Steam scheitern).",
        "oscquery_group":         "Quick OSC Query Fix",
        "oscquery_desc":          ("Falls OSC-Bugs auftreten (Parameter kommen nicht an, Tools reagieren nicht), aktiviert das "
                                   "OSCQuery direkt in der Config jedes unterstützten Programms — alle anderen Einstellungen "
                                   "der Datei bleiben erhalten. Es werden nur vorhandene Configs geändert (Programm vorher "
                                   "einmal starten)."),
        "oscquery_fix_btn":       "🔧 OSCQuery fixen",
        "oscquery_show_programs": "▸ Unterstützte Programme anzeigen ({n})",
        "oscquery_hide_programs": "▾ Unterstützte Programme ausblenden",
        "oscquery_detail_path":   "Pfad:     ",
        "oscquery_detail_param":  "Parameter:",
        "oscquery_msg_fixed":      "repariert",
        "oscquery_msg_already":    "war bereits gesetzt",
        "oscquery_msg_not_found":  "Config nicht gefunden — Programm nicht installiert oder nie gestartet",
        "oscquery_msg_unreadable": "Config nicht lesbar",
        "oscquery_msg_write_failed": "Config konnte nicht geschrieben werden",
        "oscquery_restart_hint":  "↻ Programme neu starten, damit die Änderung wirkt.",

        # Games Tab
        "nav_games":              "Games",
        "games_title":            "VR-Spiele",
        "games_subtitle":         ("Deine installierten Steam-VR-Spiele mit empfohlenen Proton-Versionen und "
                                   "Startparametern. Erkannte Spiele werden gespeichert — Steam wird nicht bei "
                                   "jedem Besuch neu gescannt."),
        "games_scan_btn":         "🔍 Spiele scannen",
        "games_click_hint":       "Klicke auf eine Spiel-Kachel, um Proton-Empfehlungen, Startparameter und Fixes auszuklappen.",
        "games_fixes_section":    "Fixes:",
        "games_section_tested":   "Getestete VR-Spiele",
        "games_section_untested": "Ungetestete VR-Spiele (Automatische Empfehlung)",
        "games_untested_suffix":  "(ungetestet)",
        "games_role_alt_ge":      "Alternative (Empfohlen bei Video-/Codec-Problemen)",
        "games_play_btn":         "▶ Spielen",
        "games_use_btn":          "Verwenden",
        "games_active_badge":     "✓ Aktiv",
        "games_use_applied":      "Proton für dieses Spiel gesetzt: {tool}",
        "games_use_default":      "Steam-Standard-Proton für dieses Spiel gesetzt.",
        "games_tool_missing":     "Diese Proton-Version ist noch nicht installiert — bitte zuerst installieren (z. B. über ProtonPlus).",
        "games_steam_restart_hint": "Steam läuft gerade — die Änderung greift erst nach einem Steam-Neustart.",
        "games_play_starting":    "Startparameter gespeichert — starte {name} über Steam...",
        "games_play_failed":      "Steam konnte nicht gestartet werden (steam nicht gefunden?).",
        "games_options_failed":   "Achtung: Startparameter konnten nicht geschrieben werden ({err}).",
        "games_params_placeholder": "Für dieses Spiel sind keine Startparameter hinterlegt — bei Bedarf hier eigene eintragen.",
        "games_info_tooltip":     "Wie ändere ich Proton-Version und Startparameter in Steam?",
        "games_scanning":         "Scanne Steam-Bibliotheken...",
        "games_found":            "{n} unterstützte(s) VR-Spiel(e) erkannt.",
        "games_none":             "Keine unterstützten VR-Spiele gefunden. Ist Steam installiert und sind die Spiele heruntergeladen?",
        "games_recommended":      "⭐ Für dich empfohlen",
        "games_recommended_cachyos": "⭐ Empfohlen (CachyOS)",
        "games_role_main":        "Empfehlung (Standard)",
        "games_role_cachyos":     "Empfehlung für CachyOS-Nutzer",
        "games_role_alt":         "Alternative",
        "games_proton_section":   "Proton-Versionen:",
        "games_params_section":   "Startparameter ({gpu}-GPU erkannt):",
        "games_params_section_unknown": "Startparameter:",
        "games_gpu_amd":          "AMD",
        "games_gpu_nvidia":       "NVIDIA",
        "games_copy_btn":         "Kopieren",
        "games_copied":           "Kopiert!",
        "games_pp_install_btn":   "⬇ Über ProtonPlus installieren",
        "games_pp_missing":       "Installiere ProtonPlus (Tools-Tab), um Proton-Versionen direkt von hier zu installieren.",
        "games_pp_running":       "ProtonPlus läuft im Terminal — wähle dort die oben genannte Version aus.",
        "games_pp_done":          "ProtonPlus fertig. Wähle die Version jetzt in Steam aus (siehe i-Knopf oben).",
        "games_pp_steam_note":    "Kommt direkt mit Steam (Steam → Einstellungen → Kompatibilität).",
        "games_info_title":       "Proton-Version & Startparameter in Steam",
        "games_info_text": (
            "<b>Proton-Version eines Spiels ändern:</b><br>"
            "1. Steam öffnen und in der Bibliothek mit Rechtsklick auf das Spiel klicken<br>"
            "2. <i>Eigenschaften…</i> → <i>Kompatibilität</i><br>"
            "3. Haken bei <i>Verwendung eines bestimmten Steam Play-Kompatibilitätstools erzwingen</i> setzen<br>"
            "4. Im Dropdown die empfohlene Version auswählen (z. B. über ProtonPlus installiert)<br>"
            "5. Fehlt eine frisch installierte Version in der Liste: Steam vorher neu starten<br><br>"
            "<b>Startparameter eintragen:</b><br>"
            "1. Rechtsklick auf das Spiel → <i>Eigenschaften…</i> → <i>Allgemein</i><br>"
            "2. Die kopierten Startparameter unten in das Feld <i>Startoptionen</i> einfügen<br><br>"
            "<i>Tipp: Die Kopieren-Knöpfe auf jeder Spiel-Karte legen dir die richtigen Werte in die Zwischenablage.</i>"
        ),
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
        "flatpak_firstrun_title": "Fast fertig – WiVRn einmal starten",
        "flatpak_firstrun_text":  "WiVRn wurde per Flatpak installiert.\n\nBitte starte WiVRn einmal und klicke dich durch den Einrichtungs-Wizard, danach kannst du es wieder schließen. Erst durch den ersten Start werden alle nötigen Ordner (Config, OpenXR, OpenVR) korrekt angelegt.\n\nDanach kann yakuda-connect seine Einstellungen sauber schreiben.",
        "flatpak_firstrun_launch":"WiVRn jetzt starten",
        "flatpak_firstrun_later": "Mache ich selbst",
        "flatpak_firstrun_launch_fail": "WiVRn konnte nicht gestartet werden: ",
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
