# Changelog - Yakuda Connect

### 🚀 v1.0.8-alpha

#### 🇬🇧 English
* **Changed** | The version number now lives in exactly one place — `APP_VERSION` in `core/main.py`. The dashboard label, the "Current version" line in Settings and the update check all read from it, so a release only needs that single edit.
* **Changed** | UI polish: the performance/latency tips sit tidily under the "VR Priority" option in the Streaming tab (no separate Settings box anymore).

#### 🇩🇪 Deutsch
* **Geändert** | Die Versionsnummer steht jetzt an genau einer Stelle — `APP_VERSION` in `core/main.py`. Das Dashboard-Label, die „Aktuelle Version“-Zeile in den Settings und die Update-Prüfung lesen alle daraus, ein Release braucht also nur noch diese eine Änderung.
* **Geändert** | UI-Feinschliff: Die Performance-/Latenz-Tipps sitzen aufgeräumt unter der „VR-Priorität“ im Streaming-Tab (keine separate Settings-Box mehr).

---

### 🚀 v1.0.7-alpha

#### 🇬🇧 English
* **Added** | New app icon (SVG): a VR headset with streaming waves in the app's Nord color scheme — scales crisply at every size and is now used everywhere (window, menu entry, AppImage).
* **Added** | "Community & Updates" section at the top of Settings: check-for-updates button (with "you are up to date" feedback), Discord button and PayPal donate button, plus the currently installed version.
* **Added** | One-click OpenXR SteamVR fix: a "Fix now (automatic)" button with a live status indicator (OK / broken / missing). The manual copy-paste instructions are still there — collapsed behind a "Manual fix" toggle.
* **Added** | Root fallback for the OpenXR fix: if writing fails due to permissions, the app asks once and retries via pkexec (graphical password prompt). The old file is backed up with a timestamp and the folder is handed back to your user, so future fixes work without root again.
* **Added** | Latency tips in the Streaming tab: a compact checklist (5 GHz WiFi, hardware encoder, H.265/AV1, foveated encoding, GPU power profile) right below the existing "VR Priority" (CAP_SYS_NICE) option — everything performance-related now lives in one place.
* **Added** | Automatic first backup: on startup the app checks the config — if no backup was ever made but a VR environment already exists (openxr/openvr/wivrn folders, native or Flatpak paths), a backup is created once automatically in the background. The backup state is remembered in the config.
* **Fixed** | Saving dashboard settings no longer wipes other config keys (language, remembered install method, backup flag).
* **Changed** | All icon references switched from `yakuda_icon.png` to `yakuda_icon.svg` (starter, window icon, install.sh, AppImage build).

#### 🇩🇪 Deutsch
* **Neu** | Neues App-Icon (SVG): VR-Headset mit Streaming-Wellen im Nord-Farbschema der App — skaliert gestochen scharf in jeder Größe und wird jetzt überall benutzt (Fenster, Menüeintrag, AppImage).
* **Neu** | „Community & Updates“-Bereich ganz oben in den Settings: Update-Prüfen-Knopf (mit „Du bist aktuell“-Rückmeldung), Discord-Button und PayPal-Spenden-Button, dazu die aktuell installierte Version.
* **Neu** | 1-Klick OpenXR-SteamVR-Fix: „Jetzt fixen (automatisch)“-Knopf mit Live-Statusanzeige (OK / kaputt / fehlt). Die manuelle Kopier-Anleitung gibt es weiterhin — eingeklappt hinter einem „Manueller Fix“-Umschalter.
* **Neu** | Root-Fallback für den OpenXR-Fix: Scheitert das Schreiben an fehlenden Rechten, fragt die App einmal nach und wiederholt den Fix per pkexec (grafische Passwortabfrage). Die alte Datei wird mit Zeitstempel gesichert und der Ordner danach wieder deinem Benutzer übergeben — künftige Fixes laufen dann wieder ohne Root.
* **Neu** | Latenz-Tipps im Streaming-Tab: kompakte Checkliste (5-GHz-WLAN, Hardware-Encoder, H.265/AV1, Foveated Encoding, GPU-Powerprofil) direkt unter der bestehenden „VR-Priorität“ (CAP_SYS_NICE) — alles rund um Performance ist jetzt an einem Ort.
* **Neu** | Automatisches Erst-Backup: Beim Start prüft die App die Config — wurde noch nie ein Backup gemacht, existiert aber bereits eine VR-Umgebung (openxr/openvr/wivrn-Ordner, nativ oder Flatpak-Pfade), wird einmalig automatisch im Hintergrund ein Backup angelegt. Der Backup-Status wird in der Config gemerkt.
* **Behoben** | Beim Speichern der Dashboard-Einstellungen gehen andere Config-Werte nicht mehr verloren (Sprache, gemerkte Installationsmethode, Backup-Flag).
* **Geändert** | Alle Icon-Verweise von `yakuda_icon.png` auf `yakuda_icon.svg` umgestellt (Starter, Fenster-Icon, install.sh, AppImage-Build).

---

### 🚀 v1.0.6-alpha

#### 🇬🇧 English
* **Added** | Updater in dashboard automatic update in yakuda connect

#### 🇩🇪 Deutsch
* **Neu** | aktualisiert die softwäre yakuda connect wenn update verfügbar muss du auf den grünene pfeil im dashboard klicken

---

### 🚀 v1.0.5-alpha

#### 🇬🇧 English
* **Added** | Multi-method installation: WiVRn and companion tools can now be installed via AUR (yay/paru), Flatpak or AppImage, selectable per item from a dropdown — with automatic detection of what's available on your distribution.
* **Added** | System update button on the Installation tab (`yay -Syu` / `paru -Syu` / `flatpak update`), with the method matched to your distro (Arch: yay/paru/flatpak; everything else: Flatpak).
* **Added** | Full Flatpak support for WiVRn: all settings (encoder, bitrate, resolution, OpenVR compatibility) are now written to the correct Flatpak sandbox path (`~/.var/app/io.github.wivrn.wivrn/config/wivrn/config.json`) instead of the native one.
* **Added** | "Native" mode for non-Arch users who installed WiVRn themselves: the tool detects it, checks the native config, and disables the auto-update button (these installs must be updated manually).
* **Added** | First-run reminder after a Flatpak install — prompts you to start WiVRn once and run the wizard (so all folders get created), including a one-click "Start WiVRn now".
* **Added** | Copyable Steam launch option for Flatpak users in the Streaming tab (`PRESSURE_VESSEL_FILESYSTEMS_RW=/var/lib/flatpak/app/io.github.wivrn.wivrn %command%`), required so (sandboxed) Steam can access the WiVRn Flatpak.
* **Added** | NixOS detection with a guided Flatpak/Flathub setup popup, including one-click Flathub remote setup when Flatpak is already present.
* **Added** | OpenXR "SteamFix" now also writes the active runtime into the Flatpak-Steam sandbox config, so Flatpak Steam can find WiVRn.
* **Added** | The chosen install method is now remembered in the config so all paths resolve correctly across sessions.
* **Improved** | Installation-tab status checks now run in a background thread with debouncing — switching between yay/paru/Flatpak is instant and no longer freezes the UI.
* **Improved** | Centralized all path handling in a single resolver (`vr_environment`): WiVRn manifest/libraries, OpenComposite/xrizer, Steam data roots and the VRChat prefix now adapt automatically to native vs. Flatpak.
* **Improved** | The Installation tab shows only a single "WiVRn" row when Flatpak is selected, since everything is bundled in one package.
* **Improved** | VR-environment backup/restore now also covers the Flatpak-Steam OpenXR/OpenVR configuration.
* **Improved** | VR priority (CAP_SYS_NICE) is now correctly skipped for Flatpak/immutable installs where `setcap` can't be applied.
* **Fixed** | The VRChat picture symlink and the start-lock no longer assume a native Arch/Steam setup; they now work with Flatpak Steam and non-Arch systems.
* **Removed** | Nix as a dedicated install method (too much maintenance and path complexity) — NixOS is now treated like Ubuntu/Fedora and uses Flatpak/AppImage (Flatpak, untested on hardware).

#### 🇩🇪 Deutsch
* **Neu** | Multi-Methoden-Installation: WiVRn und die Begleitprogramme lassen sich jetzt per AUR (yay/paru), Flatpak oder AppImage installieren, pro Eintrag über ein Dropdown wählbar — mit automatischer Erkennung, was auf deiner Distribution verfügbar ist.
* **Neu** | Aktualisieren-Knopf im Installations-Tab (`yay -Syu` / `paru -Syu` / `flatpak update`), wobei die Methode zur Distro passt (Arch: yay/paru/flatpak; alles andere: Flatpak).
* **Neu** | Vollständige Flatpak-Unterstützung für WiVRn: Alle Einstellungen (Encoder, Bitrate, Auflösung, OpenVR-Kompatibilität) werden nun in den korrekten Flatpak-Sandbox-Pfad geschrieben (`~/.var/app/io.github.wivrn.wivrn/config/wivrn/config.json`) statt in den nativen.
* **Neu** | „Nativ“-Modus für Nicht-Arch-Nutzer, die WiVRn selbst installiert haben: Das Tool erkennt das, prüft die native Config und deaktiviert den Auto-Update-Knopf (solche Installationen müssen selbst manuell aktualisiert werden).
* **Neu** | Erststart-Hinweis nach einer Flatpak-Installation — fordert dazu auf, WiVRn einmal zu starten und den Einrichtungsassistenten durchzuklicken (damit alle Ordner angelegt werden), inkl. „WiVRn jetzt starten“ per Klick.
* **Neu** | Kopierbare Steam-Startoption für Flatpak-Nutzer im Streaming-Tab (`PRESSURE_VESSEL_FILESYSTEMS_RW=/var/lib/flatpak/app/io.github.wivrn.wivrn %command%`), nötig, damit das (isolierte) Steam auf das WiVRn-Flatpak zugreifen kann.
* **Neu** | NixOS-Erkennung mit geführtem Flatpak/Flathub-Einrichtungs-Popup, inkl. Flathub-Remote-Einrichtung per Klick, wenn Flatpak bereits vorhanden ist.
* **Neu** | Der OpenXR-„SteamFix“ schreibt die aktive Runtime jetzt auch in die Flatpak-Steam-Sandbox-Config, damit Flatpak-Steam WiVRn findet.
* **Neu** | Die gewählte Installationsmethode wird nun in der Config gemerkt, damit alle Pfade über Sitzungen hinweg korrekt aufgelöst werden.
* **Verbessert** | Die Statusprüfung im Installations-Tab läuft jetzt in einem Hintergrund-Thread mit Entprellung (Debouncing) — der Wechsel zwischen yay/paru/Flatpak geschieht sofort und blockiert die Oberfläche nicht mehr.
* **Verbessert** | Sämtliche Pfad-Logik in einem zentralen Resolver gebündelt (`vr_environment`): WiVRn-Manifest/-Bibliotheken, OpenComposite/xrizer, Steam-Datenverzeichnisse und das VRChat-Prefix passen sich nun automatisch an nativ vs. Flatpak an.
* **Verbessert** | Der Installations-Tab zeigt bei Flatpak nur noch eine einzige „WiVRn“-Zeile, da dort alles in einem Paket gebündelt ist.
* **Verbessert** | Das Backup/Restore der VR-Umgebung umfasst nun auch die Flatpak-Steam-OpenXR/OpenVR-Konfiguration.
* **Verbessert** | Die VR-Priorität (CAP_SYS_NICE) wird bei Flatpak-/unveränderlichen (immutable) Installationen korrekt übersprungen, wo `setcap` nicht greifen kann.
* **Behoben** | Der VRChat-Bilder-Symlink und die Start-Sperre setzen kein natives Arch-/Steam-Setup mehr voraus; sie funktionieren jetzt mit Flatpak-Steam und Nicht-Arch-Systemen.
* **Entfernt** | Nix als eigenständige Installationsmethode (zu viel Wartung und Pfad-Komplexität) — NixOS wird jetzt wie Ubuntu/Fedora behandelt und nutzt Flatpak/AppImage (Flatpak, ungetestet auf Hardware).

### 🚀 v1.0.4-alpha

#### 🇬🇧 English
* **Fixed** | Fixed symlink generation for the VRChat picture folder.
* **Removed** | Completely removed the old, file-based autostart script logic (`autostart-launcher.sh`).
* **Added** | Implemented a smart single-use connection timer that automatically triggers the companion apps when the headset links up, and then stops active polling.
* **Added** | Added two compact management buttons next to the app counter: "Reset start Timer" (re-arms the connection check) and "Kill Apps" (instantly terminates active background companion apps).
* **Improved** | Automated Lifetime Management: Companion apps now launch seamlessly on server start and are fully terminated automatically when stopping the WiVRn server, ensuring no zombie processes are left behind.

#### 🇩🇪 Deutsch
* **Behoben** | Erstellung des Symlinks für den VRChat-Bilderordner repariert.
* **Entfernt** | Die alte, dateibasierte Autostart-Skript-Logik (`autostart-launcher.sh`) komplett gelöscht.
* **Neu** | Intelligenten Einweg-Verbindungstimer implementiert, der die Begleitprogramme beim Koppeln des Headsets vollautomatisch zündet und die aktive Erkennung danach beendet.
* **Neu** | Zwei kompakte Steuerungs-Buttons neben der Programmanzahl hinzugefügt: „Starttimer zurücksetzen“ (aktiviert die Verbindungserkennung erneut) und „Apps schließen“ (beendet laufende Hintergrundprogramme sofort manuell).
* **Verbessert** | Automatisches Prozess-Lebenszyklus-Management: Die Autostart-Programme starten nun nahtlos mit dem Serverstart und werden beim Beenden des WiVRn-Servers automatisch komplett geschlossen, um Datenmüll im Systemhintergrund zu verhindern.

---

### 🚀 v1.0.3-alpha

#### 🇬🇧 English
* **Added** | VR Priority (Streaming Tab): Added an option to enable VR priority (`CAP_SYS_NICE` / Async Reprojection), giving the VR process higher scheduler priority for smoother streaming.
* **Changed** | Event-Driven Server Status: Removed the 1-second polling timer. Status updates are now purely event-based to save system resources.
* **Changed** | WiVRn-Driven Autostart: Companion apps are now triggered directly through WiVRn via a launcher script on headset connection. This prevents duplicate instances and eliminates background polling loops.

#### 🇩🇪 Deutsch
* **Neu** | VR-Priorität im Streaming-Tab: Aktivierung von VR-Priorität (`CAP_SYS_NICE` / Async Reprojection) für höhere Scheduler-Priorität und ruckelfreieres Streaming.
* **Geändert** | Ressourcenschonender Server-Status: Statusanzeige läuft nun ereignisbasiert statt über einen Sekunden-Timer (Polling).
* **Geändert** | Autostart über WiVRn: Programme werden direkt über ein WiVRn-Launcher-Skript beim Verbinden des Headsets gestartet. Keine doppelten Instanzen, kein Hintergrund-Polling mehr.

---

### 🚀 v1.0.2-alpha

#### 🇬🇧 English
* **Added** | Connect-driven autostart functionality when the headset links up.
* **Added** | Replaced WiVRn's default autostart routine with our optimized custom autostart engine.
* **Added** | Added a dedicated 1-click UI custom layout for WayVR users.
* **Added** | Custom WayVR design button tailored specifically for SlimeVR setups.
* **Changed** | General language fixes and localizations.
* **Changed** | Fixed autostart behavior to reliably terminate companion programs upon PC disconnection.

#### 🇩🇪 Deutsch
* **Neu** | Verbindungsgesteuerte Autostart-Funktion, sobald das Headset gekoppelt wird.
* **Neu** | Standard-Autostart-Routine von WiVRn durch unsere optimierte, eigene Autostart-Engine ersetzt.
* **Neu** | Spezielles 1-Klick-UI-Layout für WayVR-Nutzer hinzugefügt.
* **Neu** | Spezifischer WayVR-Design-Button, der speziell auf SlimeVR-Setups zugeschnitten ist.
* **Geändert** | Allgemeine Sprachkorrekturen und Lokalisierungen.
* **Geändert** | Autostart-Verhalten korrigiert, um Begleitprogramme beim Trennen der PC-Verbindung zuverlässig zu beenden.
