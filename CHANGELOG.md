# Changelog - Yakuda Connect

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
