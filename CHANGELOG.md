# yakuda-connect

**A sleek and intuitive GUI for WiVRn — Linux VR streaming made easy.**

`yakuda-connect` is a powerful configuration hub and dashboard designed for Arch-based Linux systems. It eliminates the need for terminal commands, allowing you to manage, configure, and launch your WiVRn environment with a single click.

![yakuda-connect Screenshot](assets/dashboard.png)
![yakuda-connect Screenshot](assets/installation.png)
![yakuda-connect Screenshot](assets/streaming.png)
![yakuda-connect Screenshot](assets/tools.png)
![yakuda-connect Screenshot](assets/settings.png)
![yakuda-connect Screenshot](assets/settings2.png)

---
im usiing ai claude and gemini
## Key Features

- **Centralized Dashboard:** Start and stop your WiVRn server instantly with a clean, easy-to-use interface.
- **Advanced Autostart Chain:** Don't limit yourself to just one program. Launch multiple VR companion tools (such as WayVR, VRCX, OpenComposite, SlimeVR, or OSC tools) automatically in a custom sequence.
- **One-Click Environment Setup:** Automated installation of essential WiVRn dependencies and network/firewall configuration (Port 9757).
- **Headset Client Installer:** Easily install and sideload the companion Android client (.apk) directly onto your standalone VR headset (Pico / Quest) via USB.
- **Stream Fine-Tuning:** Configure encoders, toggle OpenVR compatibility, and manage your OpenXR runtimes directly from the UI.
- **Backup & Restore:** Instantly save or recover your entire VR environment configuration.
- **Desktop Compatibility:** Runs smoothly across various desktop environments including KDE Plasma, GNOME, and Hyprland.

---

## Installation

Choose one of the two available methods to get `yakuda-connect` running on your system:

### Method 1: AppImage (Recommended & Easiest)
No installation required. Run the software completely isolated as a standalone executable.

1. Navigate to the [Releases](https://github.com/yakuda-stack/yakuda-connect/releases) section.
2. Download the latest `yakuda-connect-x86_64.AppImage`.
3. Make the file executable:
   - **Via GUI:** Right-click the file -> *Properties* -> *Permissions* -> Check **Allow executing file as program**.
   - **Via Terminal:** Run `chmod +x yakuda-connect-*.AppImage`
4. Double-click the file to launch!


### Method 2: 1 terminal command

install
terminal open 
``` 
bash <(curl -s https://raw.githubusercontent.com/yakuda-stack/yakuda-connect/main/install.sh)
```
start : 
``` 
yakuda-connect
```


### Method 3: Manual Installation (From Source)
If you prefer to run the application directly from the source code, use the following commands:

```bash
# Clone the repository
git clone [https://github.com/yakuda-stack/yakuda-connect.git](https://github.com/yakuda-stack/yakuda-connect.git)

# Enter the project directory
cd yakuda-connect

# Run the automated setup script
bash install.sh



```
# yakuda-connect v1.0.2-alpha

## 🇬🇧 English

### Added
- ** Autostart by connect headset.
- ** Autostart writing in wivrn deltet im using my autostart funktion
- ** Custom ui 1 click for wayvr
- ** wayvr custom design butten for slimevr user

### Changed
- ** Langue fix
- **  autostart fix an kill programms on disconnect from pc

# yakuda-connect v1.0.3-alpha

## 🇩🇪 Deutsch

### Neu 
- **VR-Priorität im Streaming-Tab:** Im Streaming-Tab lässt sich jetzt die VR-Priorität aktivieren (`CAP_SYS_NICE` / Async Reprojection). Damit bekommt der VR-Prozess höhere Scheduler-Priorität für ruckelfreieres Streaming.

### Geändert
- **Server-Status ohne Timer:** Die Server-Status-Anzeige läuft nicht mehr über einen Sekunden-Timer (Polling), sondern wird – genau wie bereits beim Autostart – nur noch ereignisbasiert aktualisiert. Spart Ressourcen und vermeidet unnötige Last.
- **Autostart über WiVRn:** Die Autostart-Programme werden nicht mehr per eigenem Polling gestartet, sondern direkt über WiVRn angesteuert. WiVRn ruft beim Verbinden des Headsets ein Launcher-Skript auf, das alle aktiven Autostart-Einträge startet – keine doppelten Instanzen mehr, kein Sekunden-Polling.

---

## 🇬🇧 English

### Added
- **VR priority in the streaming tab:** You can now enable VR priority (`CAP_SYS_NICE` / async reprojection) from the streaming tab, giving the VR process higher scheduler priority for smoother streaming.

### Changed
- **Server status without timer:** The server status display no longer relies on a per-second polling timer. Like the autostart already does, it now updates purely event-based — lighter on resources, no needless load.
- **Autostart driven by WiVRn:** Autostart programs are no longer launched by our own polling loop; they are now triggered directly through WiVRn. On headset connect, WiVRn runs a launcher script that starts every active autostart entry — no more duplicate instances and no second-by-second polling.



