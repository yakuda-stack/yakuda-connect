# Architektur – Yakuda Connect

Kurzer Wegweiser: **welcher Tab wo seine Logik hat**, welche Datei was macht
und **welche Dateien man für eine Änderung braucht**.
Stand: v1.3.7

---

## 1. Grundaufbau

```
starter.py                 Einstieg (Prozessname, Logging, --cli / --version / --selftest)
 ├─ --cli …  ──────────►   core/cli.py            Terminal-Modus, lädt NIE Qt
 └─ sonst    ──────────►   core/main.py  VRApp    Hauptfenster (Qt)
                             ├─ ui/ui_main.py      baut ALLE Widgets (nur Aufbau, keine Logik)
                             ├─ core/tabs/*_mixin  Logik je Tab (erben alle in VRApp)
                             └─ core/*.py          Fachlogik ohne/mit wenig Qt
```

**Regeln, die überall gelten**

| Regel | Wo |
|---|---|
| Widgets werden **nur** in `ui/ui_main.py` gebaut (`self.ui.<name>`), Logik hängt in `core/main.py` bzw. einem Mixin | alle Tabs |
| Mixins sind **keine** eigenen Klassen: sie arbeiten auf demselben `self` wie `VRApp`. Neue Attribute in `VRApp.__init__` anlegen | `core/tabs/` |
| Signale verbinden: `VRApp.init_logic_connections()` bzw. `setup_*()` im Mixin | `core/main.py` |
| Texte **nie** fest im Code – immer `tr("schluessel")`, Texte in `locales/de.json` + `locales/en.json` (beide pflegen!) | `core/translations.py` |
| Sprachwechsel zur Laufzeit: `Ui_MainWindow.retranslate…` in `ui/ui_main.py` + `VRApp.apply_translations()` | – |
| Einstellungen speichern: `config_manager.save_all_settings()` / `trigger_auto_save()` → `~/.config/yakuda-connect/config.json` | `core/config_manager.py` |
| JSON immer atomar schreiben: `jsonio.write_json_atomic` / `update_json` | `core/jsonio.py` |
| Externe Programme nur über `proc.run(...)` (mit Timeout) | `core/proc.py` |
| Pfade (XDG) nur über `paths.*`, installationsabhängige Pfade (nativ/Flatpak/Nix) über `vr_environment` | `core/paths.py`, `core/vr_environment.py` |
| Logging: `get_logger("name")` → `~/.cache/yakuda-connect/app.log` | `core/logging_setup.py` |
| Advanced-Mode-Infos (Erklärung, Dateien, Befehl) je Aktion | `core/advanced_info.py`, `ui/advanced_panel.py` |

---

## 2. Tabs → Dateien

Reihenfolge der Seiten in `ui/ui_main.py` (`self.pages`, Index 0–6).

### 0 · Installation
| Was | Datei |
|---|---|
| UI-Aufbau | `ui/ui_main.py` → `setup_installation_tab()` |
| Paketstatus, Installationsmethode, Distro-Regeln, Installieren/Update | `core/main.py` (Abschnitt „Paketstatus im Installations-Tab“, `check_system_packages`, `start_package_installation`, `_apply_distro_ui_rules` …) |
| Paketlisten je Distro (`INSTALL_PACKAGES`, `INSTALL_DNF`, COPR, apt …) | `core/programs.py` |
| Installation im Terminal (Worker) | `core/install_worker.py` |
| xrizer direkt von GitHub (wenn COPR hängt) | `core/xrizer_github.py` |
| Distro-/Installationsart erkennen (nativ, Flatpak, SteamOS, Nix) | `core/vr_environment.py` |
| Einmalige Auto-Einrichtung (Erst-Backup, xrizer) | `core/vr_autotune.py` |

### 1 · Dashboard
| Was | Datei |
|---|---|
| UI-Aufbau (Server, Tracking, Kopplung, Autostart, Headsets) | `ui/ui_main.py` → `setup_dashboard_tab()` |
| WiVRn-Server starten/stoppen, Status | `core/main.py` (`start_wivrn_server`, `stop_wivrn_server`, `on_server_toggled`) + `core/wivrn_server.py` |
| VR-Autostart (Programme beim Verbinden starten, `+ Programm`/✕) | `core/main.py` (`update_autostart_fields`, `_vr_add_row`, `launch_autostart_apps`, `kill_autostart_apps` …) |
| Headsets, USB-Ampel, „Verbinden (USB)“, Kopplung, WiVRn-APK | `core/tabs/dashboard_mixin.py` |
| USB-Erkennung ohne Root | `core/usb_headsets.py` |
| adb-Diagnose/-Reparatur | `core/adb_doctor.py` |
| APK passend zum Server laden/installieren | `core/wivrn_apk.py` |
| Firewall-Ports (9757, mDNS) | `core/firewall.py` |
| UDP-Netzwerkpuffer | `core/netbuffers.py` |
| Einstellungen des WiVRn-Dashboards (INI) | `core/wivrn_dashboard.py` |

### 2 · Streaming
| Was | Datei |
|---|---|
| Encoder, Auflösung, Bitrate, FOV, OpenVR-Kompatibilität, Grafikkarte (eigenes Widget) | `core/streaming_tab.py` (`StreamingTab`) |
| Grafikkarten-Erkennung/Auswahl | `core/gpu_select.py` |
| **Autostart-Profile** (unten im Tab) | `core/tabs/autostart_profiles_mixin.py` |
| Profil-Regeln ohne Qt (auch Terminal-Modus) | `core/autostart_profiles.py` |
| Läuft Prozess X? (`/proc`, kein pgrep) | `core/process_watch.py` |

### 3 · Tools
| Was | Datei |
|---|---|
| UI-Aufbau, Unter-Tabs „Anwendungen“ / „OSC-Apps“, Tool-Karten | `ui/ui_main.py` → `setup_tools_tab()`, `_build_tool_card()` |
| Status, Installieren, Entfernen, Update-Check | `core/tabs/tools_mixin.py` |
| Liste aller Tools (Felder: key, name, install_type …) | `core/programs.py` + `config/tools.json` |
| AppImage-Installation | `core/appimage_installer.py` |
| `cargo install` (obah, XR HOTAS) | `core/cargo_installer.py` |
| Tools starten (Startbefehl finden) | `core/tool_launcher.py` |
| VRCVideoCacher | `core/vrcvideocacher_install.py` |
| Proton-Builds per Tarball | `core/proton_manual_install.py` |

### 4 · Games
| Was | Datei |
|---|---|
| UI-Grundgerüst (Scan, Hinzufügen, DB-Update, Kachel-Raster) | `ui/ui_main.py` → `setup_games_tab()` |
| Scan, Kacheln, Detailpanel, Proton-Auswahl, Startparameter, Spielstart | `core/tabs/games_mixin.py` |
| Spieledatenbank + Steam-Scanner | `core/games.py` + `config/games.json` |
| Steams VR-Kennzeichnung (`appinfo.vdf`) | `core/steam_appinfo.py` |
| Nicht-Steam-Spiele (`shortcuts.vdf`) | `core/steam_shortcuts.py` |
| „Spiel hinzufügen“-Dialog | `core/games_add_dialog.py` |
| Steam beenden, bevor .vdf geschrieben wird | `core/steam_close.py` |
| Spielstände im Proton-Prefix sichern | `core/game_backup.py` |
| VRChat-Videoplayer-Check | `core/vrchat_check.py` |

### 5 · Controls
| Was | Datei |
|---|---|
| UI-Aufbau, Karten XR HOTAS / obah / xrBinder, Controller-Editor | `ui/ui_main.py` → `setup_controls_tab()`, `_build_obah_panel()` |
| Schalter (installieren über Tools-Tab), **OpenVR-Spiele** (obah) | `core/tabs/controls_mixin.py` |
| obah-Auswahlschritte (Spiel, Controller, Quelle) | `core/obah_bindings.py` |
| obah-Bindings lesen/bearbeiten/speichern | `core/obah_editor.py` |
| Controller-Zeichnung + Karten + Linien | `ui/controller_view.py` (Bilder: `assets/controls/`) |
| Dialog „Taste bearbeiten“ (OpenVR) | `ui/binding_dialog.py` |
| **OpenXR-Spiele** in derselben Ansicht, „Alles auf Standard“, **„OpenXR-Vorlage verwenden“** | `core/tabs/xr_controls_mixin.py` |
| Regeln OpenXR ↔ Karten, Umbelegungen, Kippen/Deadzone, **Vorlage** (`template_mappings`) | `core/xr_bindings.py` (ohne Qt, gut testbar) |
| xrBinder bauen, INI schreiben, Zustand je Spiel, xrizer-Standardbelegung | `core/xrbinder.py` |
| Laufende Spiele + gespeicherter Stand | `core/xrbinder_session.py` |
| UDP-IPC mit dem Layer | `core/xrbinder_ipc.py` |
| Karte „xrBinder“ (Einrichtung) | `ui/xrbinder_panel.py` |
| Dialog „Taste belegen“ (OpenXR) | `ui/xr_button_dialog.py` |

### 6 · Einstellungen (Unter-Tabs)
| Unter-Tab | Inhalt → Datei |
|---|---|
| **Allgemein & Updates** | Sprache, Community & Updates (Selbst-Update, Discord, Ko-fi), Changelog/Highlights, Diagnose & Log, Backup → `core/main.py` (Abschnitte „Selbst-Update“, „Community & Updates“), `core/release_notes.py`, `ui/release_notes_dialog.py`, `core/diagnostics.py`, `core/backup_manager.py` |
| **Design** | Themen, Farben, Hintergrundbild → `ui/customization_widget.py`, `ui/theme.py`, `ui/background.py` |
| **VR & OpenXR** | WayVR-Design → `core/overlay_manager.py`; Runtime umschalten + VR-Priorität → `ui/vr_runtime_widget.py`; OpenXR-Steam-Fix → `core/openxr_manager.py` + `core/main.py`; Quick OSC Query Fix → `core/queryfix.py`, `ui/queryfix_widget.py` |
| **Audio** | Mikrofon/Standardquelle (`pactl`) → `core/main.py` (Abschnitt „Mikrofon / Audio-Quelle“) |
| **Erweitert / System** | Server mit App beenden → `core/exit_guard.py`; Terminal-Modus/Befehle einrichten → `core/cli_install.py`; Spiele zurücksetzen; eigene Kill-Befehle → `core/main.py` |

Advanced-Mode-Schalter (unten links in der Seitenleiste): `core/main.py` → `on_advanced_mode_toggled`.

---

## 3. Terminal-Modus (ohne Qt)

| Datei | Aufgabe |
|---|---|
| `core/cli.py` | Befehle `YC-help`, `YC-status`, `YC-wivrn-toggle`, `YC-openvr`, `YC-encoder`, `YC-GPU`, `YC-killapps`, `YC-autostart-reset`, `YC-pairing` |
| `core/cli_install.py` | Kurzbefehle nach `~/.local/bin` legen, Terminal öffnen |
| `core/autostart_runner.py` | Autostart-Wächter + `_profile-watch` im Hintergrund |

⚠️ Alles, was `cli.py` importiert, darf **kein PySide6** laden (`tests/test_cli.py` prüft das).

---

## 4. Daten & Dateien

| Pfad | Inhalt |
|---|---|
| `~/.config/yakuda-connect/config.json` | alle App-Einstellungen |
| `~/.config/yakuda-connect/config/games.json` | heruntergeladenes Spiele-DB-Update (sonst `config/games.json` im App-Ordner) |
| `~/.config/wivrn/config.json` | WiVRn-Server (Encoder, Bitrate …), Flatpak: `~/.var/app/io.github.wivrn.wivrn/…` |
| `~/.config/openxr/1/active_runtime.json` | aktive OpenXR-Runtime |
| `~/.cache/yakuda-connect/app.log` | Log (rotiert bei 1 MB) |
| xrBinder-Zustand/INI je Spiel | Pfade in `core/xrbinder.py` (`state_path`, `app_config_path`) |

Im Repo:

| Ordner/Datei | Inhalt |
|---|---|
| `locales/` | Texte DE/EN (`CONTRIBUTING.md` = neue Sprache hinzufügen) |
| `config/games.json`, `config/tools.json` | mitgelieferte Datenbanken |
| `assets/` | Icons, Screenshots, Controller-Bilder (`assets/controls/`) |
| `tests/` | pytest (Qt-Tests laufen offscreen; `conftest.py` setzt ein Wegwerf-HOME, schaltet Update-Checks beim Start ab (`YAKUDA_NO_STARTUP_NETCHECK`) und wartet am Ende auf laufende QThreads) |

---

## 5. Version, Release, Pakete

| Datei | Aufgabe |
|---|---|
| `core/version.py` | **einzige** Quelle der Versionsnummer |
| `core/main.py` → `APP_VERSION = "v…"` | Anker für alte Clients (bis v1.1.4) – **nicht löschen** |
| `scripts/bump_version.py` | setzt/prüft Version in version.py, main.py, PKGBUILD, `.SRCINFO`, README-Badge; legt in CHANGELOG/HIGHLIGHTS nur die Überschrift an |
| `packaging/aur/PKGBUILD` + `.SRCINFO` | Kopie fürs Projekt (echtes AUR-Repo liegt separat) |
| `build_appimage.sh` | AppImage + `.zsync` |
| `install.sh` | curl-Installer (Arch, Fedora, Debian/Ubuntu, openSUSE) |
| `CHANGELOG.md` / `HIGHLIGHTS.md` | ausführlich / für Nutzer, jeweils DE + EN, in der App lesbar |

```bash
python3 scripts/bump_version.py 1.3.8            # Version setzen
python3 scripts/bump_version.py --check           # prüfen
python3 scripts/bump_version.py --check --expect 1.3.8   # vor dem Release (leere Blöcke = Fehler)
QT_QPA_PLATFORM=offscreen python3 -m pytest -q tests     # alle Tests
python3 tests/smoke.py                                    # Smoke-Test
```

---

## 6. Welche Dateien für welche Änderung schicken?

Immer mitschicken: **diese Datei**, dazu je nach Thema:

| Änderung an … | Diese Dateien |
|---|---|
| Text/Übersetzung | `locales/de.json`, `locales/en.json` |
| neuer Knopf/Widget in einem Tab | `ui/ui_main.py` + Logik-Datei des Tabs (siehe Abschnitt 2) + beide `locales/*.json` |
| Dashboard: Server/Autostart | `core/main.py`, `core/wivrn_server.py`, `ui/ui_main.py` |
| Dashboard: USB/Headsets/APK | `core/tabs/dashboard_mixin.py`, `core/usb_headsets.py`, `core/wivrn_apk.py`, `core/adb_doctor.py` |
| Streaming | `core/streaming_tab.py`, `core/gpu_select.py` |
| Autostart-Profile | `core/tabs/autostart_profiles_mixin.py`, `core/autostart_profiles.py`, `core/process_watch.py`, `core/autostart_runner.py` |
| Tools | `core/tabs/tools_mixin.py`, `core/programs.py`, `config/tools.json` (+ Installer-Modul) |
| Games | `core/tabs/games_mixin.py`, `core/games.py`, `config/games.json` |
| Controls OpenVR (obah) | `core/tabs/controls_mixin.py`, `core/obah_editor.py`, `core/obah_bindings.py`, `ui/controller_view.py`, `ui/binding_dialog.py` |
| Controls OpenXR (xrBinder) | `core/tabs/xr_controls_mixin.py`, `core/xr_bindings.py`, `core/xrbinder.py`, `ui/xr_button_dialog.py` |
| Einstellungen | `core/main.py`, `ui/ui_main.py` (+ Widget-Datei aus Abschnitt 2) |
| Terminal-Modus | `core/cli.py`, `core/cli_install.py`, `core/autostart_runner.py` |
| Version/Release | `scripts/bump_version.py`, `packaging/aur/PKGBUILD`, `packaging/aur/.SRCINFO` |
| Installation/Pakete | `core/main.py`, `core/programs.py`, `core/install_worker.py`, `core/vr_environment.py` |

Tests dazu liegen meist unter `tests/test_<modulname>.py` – gerne mitschicken.

---

## 7. Hinweise

* `core/main.py` (~4000 Zeilen) und `ui/ui_main.py` (~2800 Zeilen) sind die größten Dateien. Neue Logik lieber in ein eigenes Modul bzw. Mixin unter `core/tabs/` auslagern.
* `core/palette_editor.py` (WayVR-Farbpalette) ist aktuell nirgends eingebunden.
* Die Dateien `*.patch` im Hauptordner werden vom Code nicht benutzt.
* Wenn sich ein Tab oder Modul ändert: diese Datei kurz mitpflegen.
