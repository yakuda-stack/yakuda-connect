# yakuda-connect

**Eine einfache GUI für WiVRn — Linux VR Streaming leicht gemacht.**

yakuda-connect hilft dir, WiVRn auf Arch-basierten Linux-Systemen zu konfigurieren und zu starten, ohne das Terminal anfassen zu müssen.

![yakuda-connect Screenshot](assets/yakuda_icon.png)

---

## Features

- **Ein-Klick Installation** aller WiVRn-Abhängigkeiten
- **Dashboard** zum Starten/Stoppen des WiVRn-Servers
- **Streaming-Einstellungen** direkt in der UI (Encoder, OpenVR Kompatibilität, OpenXR Runtime)
- **Tools-Tab** mit nützlichen VR-Begleitprogrammen (WayVR, OSC-Tools, ...)
- **Backup & Restore** der VR-Laufumgebung
- Unterstützt **KDE, GNOME, Hyprland** und andere Desktop-Umgebungen

---

## Installation

### Via AUR (empfohlen)
```bash
yay -S yakuda-connect
```

### Manuell
```bash
git clone https://github.com/DEIN_USERNAME/yakuda-connect.git
cd yakuda-connect
bash install.sh
```

---

## Voraussetzungen

- Arch Linux oder Arch-basierte Distribution (Manjaro, EndeavourOS, ...)
- `python` + `python-pyside6`
- `yay` (AUR-Helper)

---

## Starten

Nach der Installation:
- Im **Anwendungsmenü** nach `yakuda-connect` suchen
- Oder im Terminal: `yakuda-connect`

---

## Lizenz

MIT
