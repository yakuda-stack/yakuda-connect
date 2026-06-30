# yakuda-connect

**A sleek and intuitive GUI for WiVRn — Linux VR streaming made easy.**

[![Discord](https://img.shields.io/badge/Join_Our_Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/ZHa3rR2Z8k)

`yakuda-connect` is a powerful configuration hub and dashboard designed for Arch-based Linux systems. It eliminates the need for complex terminal commands, allowing you to manage, configure, and launch your WiVRn environment with a single click.

### 📸 Interface Preview

<table>
  <tr>
    <td><b>Dashboard</b><br><img src="assets/dashboard.png" alt="Dashboard" width="300"/></td>
    <td><b>Installation</b><br><img src="assets/installation.png" alt="Installation" width="300"/></td>
    <td><b>Streaming Settings</b><br><img src="assets/streaming.png" alt="Streaming" width="300"/></td>
  </tr>
  <tr>
    <td><b>Tools Hub</b><br><img src="assets/tools.png" alt="Tools" width="300"/></td>
    <td><b>General Settings</b><br><img src="assets/settings.png" alt="Settings" width="300"/></td>
    <td><b>Advanced Settings</b><br><img src="assets/settings2.png" alt="Settings 2" width="300"/></td>
  </tr>
</table>

---

## 🚀 Key Features

* **Centralized Dashboard:** Start and stop your WiVRn server instantly with a clean, easy-to-use interface.
* **Advanced Autostart Chain:** Launch multiple VR companion tools (such as WayVR, VRCX, OpenComposite, SlimeVR, or OSC tools) automatically in a custom sequence.
* **One-Click Environment Setup:** Automated installation of essential WiVRn dependencies and network/firewall configuration (Port 9757).
* **Headset Client Installer:** Easily install and sideload the companion Android client (.apk) directly onto your standalone VR headset (Pico / Quest) via USB.
* **Stream Fine-Tuning:** Configure encoders, toggle OpenVR compatibility, and manage your OpenXR runtimes directly from the UI.
* **Backup & Restore:** Instantly save or recover your entire VR environment configuration.
* **Desktop Compatibility:** Runs smoothly across various desktop environments including KDE Plasma, GNOME, and Hyprland.

---

> 🤖 **Transparency Note:** This project and its documentation are proudly developed and optimized with the support of AI coding assistants (**Claude by Anthropic** & **Gemini**).

---

## 📦 Installation & Setup

Whether you are a Linux newcomer or a power user, there are two straightforward ways to get `yakuda-connect` up and running.

### Method 1: Express Installation (AppImage & Terminal)

Choose one of the two options below to get started as quickly as possible:

#### Option A: One-Click Terminal Command (Fastest Method)
Open your terminal and paste the following command. It will automatically download the setup script, install the tool, and launch it immediately:

```bash
bash <(curl -s https://raw.githubusercontent.com/yakuda-stack/yakuda-connect/main/install.sh) && yakuda-connect
```

#### Option B: Manual AppImage (No Installation Required)
1. Navigate to the **Releases** section on GitHub[cite: 2].
2. Download the latest `yakuda-connect-x86_64.AppImage`[cite: 2].
3. Make the file executable[cite: 2]:
   - **Via GUI:** Right-click the file -> Properties -> Permissions -> Enable "Allow executing file as program"[cite: 2].
   - **Via Terminal:** `chmod +x yakuda-connect-*.AppImage`[cite: 2].
4. Double-click the file to launch the dashboard![cite: 2]

---

### Method 2: Manual Installation (From Source)

If you prefer to clone the repository and run the application directly from the source code, execute these commands in your terminal sequence:

1. Clone the repository[cite: 2]:
```bash
git clone https://github.com/yakuda-stack/yakuda-connect.git
```

2. Change to the project directory[cite: 2]:
```bash
cd yakuda-connect
```

3. Run the installation script[cite: 2]:
```bash
bash install.sh
```

---

## 📝 Changelog



# Changelog - Yakuda Connect


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

