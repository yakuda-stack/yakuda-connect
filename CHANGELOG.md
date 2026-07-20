# Changelog - Yakuda Connect

### 🚀 v1.1.1

#### 🇬🇧 English

**Highlights:** Fedora and Ubuntu support · Flatpak dropped from the Installation tab (native only) · WayVR design back on cubee-cb with the SlimeVR row built in · colour picker for the WayVR palette · cover art for every game.

* **Added** | **Fedora support (native, from the official repos)**: the Installation tab now detects Fedora and its derivatives (Nobara, Bazzite, …) and installs **`wivrn`**, **`wivrn-dashboard`** and **`opencomposite`** with **`dnf`** — all three ship in Fedora's official repositories, so no COPR, no third-party repo and no Flatpak is needed. The status rows are named exactly as on Arch, so the tab looks the same on both.
* **Added** | **Update button uses the Fedora software centre**: on Fedora the update button no longer runs `dnf upgrade` in a terminal — it opens the software centre you already use (**GNOME Software**, **KDE Discover** or **dnfdragora**, whichever is installed). That is the route Fedora users expect and it avoids typing a sudo password into a terminal window. If no software centre is found, the app shows the `dnf` command instead.
* **Added** | **xrizer hint for Fedora**: xrizer is **not** in Fedora's official repositories — only in the COPR **`@xr-sig/xrizer`**. The app points this out and shows the two commands to enable it, but never enables a third-party repo on its own. Note that `envision-xrizer` is *not* xrizer: it only contains the build dependencies Envision needs to compile it.
* **Added** | **Ubuntu / Debian**: since there are no VR packages in the official repositories, the install button now shows a short, copyable build guide instead of failing silently. The update button is hidden entirely on these distributions — there would be nothing for it to update.
* **Changed** | **No more Flatpak in the Installation tab**: the WiVRn runtime is installed natively only (Arch: AUR, Fedora: dnf, Ubuntu: guide). Native is leaner and performs better, and it removes the sandbox problems that came with it — the Steam launch option `PRESSURE_VESSEL_FILESYSTEMS_RW` is gone, and `openvr-compat-path` now always points at a real host path. **The Tools tab keeps Flatpak** for ProtonPlus, Unity Hub and Intiface, where it makes sense.
* **Fixed** | **Config paths for WiVRn**: the config is now always read from `~/.config/wivrn`, instead of guessing at a Flatpak sandbox path. `opencomposite` and `xrizer` are also found in Fedora's `/usr/lib64/…` locations now.
* **Added** | **Cover art for every game**: games that Steam has no local artwork for — untested ones and anything never launched — now get their cover from Steam's CDN. It is fetched in the background, so the window never freezes, cached in `~/.cache/yakuda-connect/covers`, and without a connection you simply get the placeholder instead of an error.
* **Fixed** | **VR games in large installs were not detected**: the scan gave up after 400 folders and reported "no VR game" when it ran out of budget before reaching the loader — **Wanderer: The Fragments of Fate** was affected, and it did not even show up as untested. The scan now checks the usual engine paths (UE4/5, Unity, Godot) directly first, searches deeper, and no longer treats running out of budget as a definite "no".
* **Changed** | **WayVR design comes from cubee-cb again**: the base design is downloaded from [cubee-cb / linux-vr-compat](https://github.com/cubee-cb/linux-vr-compat) — now under GPL-3.0, the same licence as this project. Two changes are applied afterwards: the two placeholder timezones under the clock are removed (leaving your own time and date), and **the SlimeVR reset buttons take exactly that spot**, so the watch keeps its size and nothing shifts around. If the design ever changes upstream and the timezone row can no longer be found, nothing is touched and the app says so.
* **Added** | **Show SlimeVR buttons** checkbox: shows or hides the reset row. Deliberately here rather than as a button inside VR — WayVR resolves the target ID of `::ElementSetDisplay` while parsing, so two buttons toggling each other always leave one forward reference, which fails silently and lets the state change in one direction only.
* **Added** | **Colour picker for the WayVR palette**: Settings → *WayVR Colours* writes `~/.config/wayvr/palettes/yakuda.json`. Since WayVR colours the watch **and the keyboard** from the same palette, both change together. The text colours are derived automatically from their background (WCAG brightness), so key labels stay readable whatever you pick, and the palette is validated before writing — an invalid one would make WayVR fall back silently.
* **Changed** | **Design button renamed** to *Update WayVR custom Cubee-cb design*, and the credits box is back: cubee-cb (GPL-3.0), **sapphire** for the SlimeVR buttons, and the WayVR community.

#### 🇩🇪 Deutsch

**Highlights:** Fedora- und Ubuntu-Unterstützung · Flatpak raus aus dem Installations-Tab (nur noch nativ) · WayVR-Design wieder von cubee-cb, mit eingebauter SlimeVR-Reihe · Farbwähler für die WayVR-Palette · Coverbilder für jedes Spiel.

* **Neu** | **Fedora-Unterstützung (nativ, aus den offiziellen Repos)**: Der Installations-Tab erkennt jetzt Fedora und seine Ableger (Nobara, Bazzite, …) und installiert **`wivrn`**, **`wivrn-dashboard`** und **`opencomposite`** per **`dnf`** — alle drei liegen in Fedoras offiziellen Repositories, es braucht also weder COPR noch Fremdrepo noch Flatpak. Die Statuszeilen heißen genauso wie auf Arch, der Tab sieht auf beiden Distros gleich aus.
* **Neu** | **Update-Knopf nutzt das Fedora-Software-Center**: Auf Fedora fährt der Update-Knopf kein `dnf upgrade` mehr im Terminal, sondern öffnet das Software-Center, das du ohnehin benutzt (**GNOME Software**, **KDE Discover** oder **dnfdragora**, je nachdem was installiert ist). Das ist der Weg, den Fedora-Nutzer erwarten, und es erspart die sudo-Passworteingabe im Terminalfenster. Wird kein Software-Center gefunden, zeigt die App stattdessen den `dnf`-Befehl an.
* **Neu** | **xrizer-Hinweis für Fedora**: xrizer liegt **nicht** in Fedoras offiziellen Repos — nur im COPR **`@xr-sig/xrizer`**. Die App weist darauf hin und zeigt die beiden nötigen Befehle, aktiviert ein Fremdrepo aber nie von sich aus. Wichtig: `envision-xrizer` ist *kein* xrizer, sondern enthält nur die Build-Abhängigkeiten, die Envision zum Selberbauen braucht.
* **Neu** | **Ubuntu / Debian**: Da es in den offiziellen Paketquellen keine VR-Pakete gibt, zeigt der Installations-Knopf jetzt eine kurze, kopierbare Bau-Anleitung, statt still zu scheitern. Der Update-Knopf ist auf diesen Distros komplett ausgeblendet — er hätte nichts zu aktualisieren.
* **Geändert** | **Kein Flatpak mehr im Installations-Tab**: Die WiVRn-Runtime wird nur noch nativ installiert (Arch: AUR, Fedora: dnf, Ubuntu: Anleitung). Nativ ist schlanker, läuft besser und erspart die Sandbox-Probleme — die Steam-Startoption `PRESSURE_VESSEL_FILESYSTEMS_RW` entfällt, und `openvr-compat-path` zeigt jetzt immer auf einen echten Host-Pfad. **Der Tools-Tab behält Flatpak** für ProtonPlus, Unity Hub und Intiface, wo es sinnvoll ist.
* **Behoben** | **Config-Pfade von WiVRn**: Die Config wird jetzt immer aus `~/.config/wivrn` gelesen, statt auf einen Flatpak-Sandbox-Pfad zu raten. `opencomposite` und `xrizer` werden zusätzlich unter Fedoras `/usr/lib64/…` gefunden.
* **Neu** | **Coverbilder für jedes Spiel**: Spiele, für die Steam lokal kein Artwork hat — ungetestete und nie gestartete — holen ihr Cover jetzt vom Steam-CDN. Das läuft im Hintergrund, das Fenster friert also nicht ein, landet im Cache unter `~/.cache/yakuda-connect/covers`, und ohne Verbindung gibt es einfach den Platzhalter statt eines Fehlers.
* **Behoben** | **VR-Spiele in großen Installationen wurden nicht erkannt**: Der Scan gab nach 400 Ordnern auf und meldete „kein VR-Spiel", wenn das Budget aufgebraucht war, bevor er den Loader fand — betroffen war **Wanderer: The Fragments of Fate**, das nicht einmal als ungetestet auftauchte. Der Scan prüft jetzt zuerst direkt die üblichen Engine-Pfade (UE4/5, Unity, Godot), sucht tiefer und wertet ein aufgebrauchtes Budget nicht mehr als sicheres „nein".
* **Geändert** | **WayVR-Design kommt wieder von cubee-cb**: Das Basis-Design wird von [cubee-cb / linux-vr-compat](https://github.com/cubee-cb/linux-vr-compat) geladen — inzwischen unter GPL-3.0, derselben Lizenz wie dieses Projekt. Danach greifen zwei Anpassungen: Die zwei Platzhalter-Zeitzonen unter der Uhr fallen weg (übrig bleiben deine eigene Uhrzeit und das Datum), und **die SlimeVR-Reset-Buttons rücken genau an diese Stelle** — die Watch behält dadurch ihre Größe und nichts verrutscht. Ändert sich das Design upstream und die Zeitzonen-Zeile ist nicht mehr auffindbar, wird nichts angefasst und die App sagt Bescheid.
* **Neu** | Schalter **„SlimeVR-Buttons anzeigen"**: blendet die Reset-Reihe ein oder aus. Bewusst hier und nicht als Knopf in VR — WayVR löst die Ziel-ID von `::ElementSetDisplay` schon beim Parsen auf, zwei Buttons, die sich gegenseitig umschalten, haben deshalb immer eine Vorwärtsreferenz. Die schlägt still fehl, und der Zustand ließe sich nur in eine Richtung wechseln.
* **Neu** | **Farbwähler für die WayVR-Palette**: Einstellungen → *WayVR-Farben* schreibt `~/.config/wayvr/palettes/yakuda.json`. Weil WayVR die Watch **und die Tastatur** aus derselben Palette färbt, ändert sich beides gemeinsam. Die Textfarben werden automatisch aus ihrem Hintergrund abgeleitet (WCAG-Helligkeit), damit die Tastenbeschriftung bei jeder Wahl lesbar bleibt, und die Palette wird vor dem Schreiben geprüft — eine ungültige ließe WayVR stillschweigend zurückfallen.
* **Geändert** | **Design-Knopf umbenannt** in *WayVR-Custom-Design von Cubee-cb aktualisieren*, und die Credits-Box ist zurück: cubee-cb (GPL-3.0), **sapphire** für die SlimeVR-Buttons und die WayVR-Community.

---

### 🚀 v1.1.0

#### 🇬🇧 English

**Highlights:** a Play button right in the window · a new window structure for the game panel · more supported VR games.

* **Added** | **Play button right on the tile**: every game tile now has its own play button, so you can start a game with its saved Proton version and launch options without expanding anything first. The rest of the tile still opens the details, and the tooltip shows which Proton will be used. Both play buttons now use a hand-drawn play triangle instead of the Unicode arrow, so they look identical and crisp on every distribution.
* **Changed** | **New window structure for the game panel**: launch options are now built from three clearly separated parts — the stored base parameters, toggle switches for **`--force-openxr`** (game argument) and **`mullvad-exclude`** (VPN wrapper), and a free text field for your own parameters. Everything is merged position-aware (wrappers before `%command%`, game arguments after it) and the resulting string is shown live, copyable, and used by Play. Toggles and custom parameters are remembered per game.
* **Added** | **More supported VR games**: **Arizona Sunshine 2**, **Arizona Sunshine Remake**, **Metro Awakening**, **Thief VR: Legacy of Shadow** and **Beat Saber** joined the tested games — each with its own Proton recommendation (Steam's Proton 11 by default, `proton-cachyos` on CachyOS, Proton-GE as the alternative; Metro Awakening recommends Proton-GE instead). Adding a new game is now a one-liner in `core/games.py`.

#### 🇩🇪 Deutsch

**Highlights:** Play-Knopf direkt im Fenster · neue Fenster-Struktur im Spiel-Panel · mehr unterstützte VR-Spiele.

* **Neu** | **Play-Knopf direkt auf der Kachel**: Jede Spiel-Kachel hat jetzt einen eigenen Play-Knopf — so startest du ein Spiel mit der gemerkten Proton-Version und den gespeicherten Startparametern, ohne vorher etwas aufklappen zu müssen. Der Rest der Kachel öffnet weiterhin die Details, und der Tooltip verrät, welches Proton benutzt wird. Beide Play-Knöpfe zeigen jetzt ein selbst gezeichnetes Play-Dreieck statt des Unicode-Pfeils und sehen dadurch auf jeder Distribution gleich sauber aus.
* **Geändert** | **Neue Fenster-Struktur im Spiel-Panel**: Die Startparameter bestehen jetzt aus drei klar getrennten Teilen — den hinterlegten Basis-Parametern, Schaltern für **`--force-openxr`** (Spiel-Argument) und **`mullvad-exclude`** (VPN-Wrapper) sowie einem freien Feld für eigene Parameter. Alles wird positionsbewusst zusammengebaut (Wrapper vor `%command%`, Spiel-Argumente dahinter), und der fertige String steht live und kopierbar im Panel und wird von Play benutzt. Schalter und eigene Parameter werden pro Spiel gemerkt.
* **Neu** | **Mehr unterstützte VR-Spiele**: **Arizona Sunshine 2**, **Arizona Sunshine Remake**, **Metro Awakening**, **Thief VR: Legacy of Shadow** und **Beat Saber** sind zu den getesteten Spielen dazugekommen — jeweils mit eigener Proton-Empfehlung (standardmäßig Steams Proton 11, auf CachyOS `proton-cachyos`, Proton-GE als Alternative; bei Metro Awakening ist Proton-GE die Empfehlung). Ein neues Spiel hinzuzufügen ist jetzt ein Einzeiler in `core/games.py`.

---

### 🚀 v1.0.9-alpha

#### 🇬🇧 English
* **Added** | New **Games** tab: scans all your Steam libraries (native, Flatpak and extra library folders) and shows every detected VR game as a compact cover tile — using the vertical artwork straight from your local Steam cache, no downloads needed. Results are saved to the config, so Steam is only re-scanned when you hit the "Scan games" button (the first visit scans automatically).
* **Added** | Two sections in the Games tab: **Tested VR Games** with curated profiles (Proton recommendations, launch options and game-specific fixes — starting with VRChat) and **Untested VR Games (auto-recommendation)** for everything else. VR games are detected fully offline via their OpenVR/OpenXR loader files in the install folder.
* **Added** | Clicking a tile expands an **inline detail panel** right under its row — it sticks to the game instead of jumping to the bottom of the list, and only one game is open at a time (accordion).
* **Added** | **▶ Play** button next to the game name: writes the current launch options into Steam (`localconfig.vdf`) and starts the game via `steam -applaunch` — with Flatpak-Steam and `steam://` fallbacks.
* **Added** | **Use** button on every Proton entry: sets that version as the active one for the game by writing Steam's `CompatToolMapping` (the same mechanism ProtonPlus uses), remembers your choice in the config and marks it with a green "✓ Active" badge. Every VDF write creates a timestamped backup first, and the app warns you when Steam is running (changes apply after a Steam restart).
* **Added** | Automatic Proton recommendations for untested games: on CachyOS you get ⭐ `proton-cachyos`, on standard distros Steam's default Proton — plus **Proton-GE** as a universal alternative whenever in-game videos or audio codecs act up. "Proton-GE" and "proton-cachyos" resolve automatically to the newest installed build in `compatibilitytools.d`.
* **Added** | **ProtonPlus integration**: recommended Proton builds (GE / RTSP / CachyOS) can be installed straight from the game panel — a terminal opens with the interactive ProtonPlus CLI (works with native and Flatpak ProtonPlus).
* **Added** | GPU-aware launch options: the app detects AMD vs. NVIDIA and shows the matching parameters with a copy button; untested games get an empty, editable field for your own options.
* **Added** | Small **(i)** button in the Games tab with a step-by-step guide on forcing a Proton version and entering launch options in Steam.
* **Added** | **Quick OSC Query Fix** in Settings: enables OSCQuery in the configs of supported OSC tools (OSC Leash, OscGoesBrrr) with one click — existing settings stay untouched, and the supported-programs list is expandable with per-tool details.
* **Changed** | The **headset APK installer** moved from Settings to the **Installation** tab, where it belongs in the setup flow.
* **Changed** | The **VRChat Picture Folder Fix** moved from Settings into the expanded VRChat panel in the Games tab; the now-empty "General" settings box was removed.
* **Changed** | On CachyOS, plain Valve Proton is hidden for VRChat — `proton-cachyos` and `proton-rtsp` are all you need there.
* **Fixed** | Saving settings no longer wipes the new config keys (game scan cache, per-game Proton selection) — the config whitelist was extended accordingly.

#### 🇩🇪 Deutsch
* **Neu** | Neuer **Games**-Tab: scannt alle Steam-Bibliotheken (nativ, Flatpak und zusätzliche Bibliotheksordner) und zeigt jedes erkannte VR-Spiel als kompakte Cover-Kachel — mit dem vertikalen Artwork direkt aus deinem lokalen Steam-Cache, ganz ohne Downloads. Die Ergebnisse werden in der Config gespeichert, Steam wird also nur beim Klick auf „Spiele scannen" neu durchsucht (der erste Besuch scannt automatisch).
* **Neu** | Zwei Sektionen im Games-Tab: **Getestete VR-Spiele** mit kuratierten Profilen (Proton-Empfehlungen, Startparameter und spielspezifische Fixes — den Anfang macht VRChat) und **Ungetestete VR-Spiele (Automatische Empfehlung)** für alles andere. VR-Spiele werden komplett offline über ihre OpenVR-/OpenXR-Loader-Dateien im Installationsordner erkannt.
* **Neu** | Klick auf eine Kachel klappt ein **Inline-Detail-Panel** direkt unter ihrer Reihe auf — es klebt am Spiel, statt ans Listenende zu springen, und es ist immer nur ein Spiel gleichzeitig offen (Akkordeon).
* **Neu** | **▶ Spielen**-Knopf direkt neben dem Spielnamen: schreibt die aktuellen Startparameter in Steam (`localconfig.vdf`) und startet das Spiel per `steam -applaunch` — mit Flatpak-Steam- und `steam://`-Fallbacks.
* **Neu** | **Verwenden**-Knopf an jeder Proton-Version: setzt sie als aktive Version für das Spiel, indem Steams `CompatToolMapping` geschrieben wird (derselbe Mechanismus wie bei ProtonPlus), merkt sich die Wahl in der Config und markiert sie mit grünem „✓ Aktiv"-Badge. Vor jedem VDF-Schreiben wird ein Zeitstempel-Backup angelegt, und die App warnt, wenn Steam gerade läuft (Änderungen greifen nach einem Steam-Neustart).
* **Neu** | Automatische Proton-Empfehlungen für ungetestete Spiele: Auf CachyOS gibt's ⭐ `proton-cachyos`, auf Standard-Distros Steams Standard-Proton — plus **Proton-GE** als universelle Alternative, falls In-Game-Videos oder Audio-Codecs zicken. „Proton-GE" und „proton-cachyos" lösen automatisch auf die neueste installierte Version in `compatibilitytools.d` auf.
* **Neu** | **ProtonPlus-Integration**: Empfohlene Proton-Versionen (GE / RTSP / CachyOS) lassen sich direkt aus dem Spiel-Panel installieren — es öffnet sich ein Terminal mit der interaktiven ProtonPlus-CLI (funktioniert mit nativem und Flatpak-ProtonPlus).
* **Neu** | GPU-bewusste Startparameter: Die App erkennt AMD vs. NVIDIA und zeigt die passenden Parameter mit Kopieren-Knopf; ungetestete Spiele bekommen ein leeres, editierbares Feld für eigene Optionen.
* **Neu** | Kleiner **(i)**-Knopf im Games-Tab mit Schritt-für-Schritt-Anleitung, wie man in Steam eine Proton-Version erzwingt und Startparameter einträgt.
* **Neu** | **Quick OSC Query Fix** in den Settings: aktiviert OSCQuery in den Configs der unterstützten OSC-Tools (OSC Leash, OscGoesBrrr) mit einem Klick — bestehende Einstellungen bleiben erhalten, und die Liste der unterstützten Programme ist mit Details pro Tool ausklappbar.
* **Geändert** | Der **Headset-APK-Installer** ist von den Settings in den **Installation**-Tab umgezogen, wo er im Einrichtungsablauf hingehört.
* **Geändert** | Der **VRChat Picture Folder Fix** ist von den Settings in das ausgeklappte VRChat-Panel im Games-Tab umgezogen; die dadurch leere „General"-Box in den Settings wurde entfernt.
* **Geändert** | Auf CachyOS wird das normale Valve-Proton für VRChat ausgeblendet — dort reichen `proton-cachyos` und `proton-rtsp` völlig.
* **Behoben** | Beim Speichern der Einstellungen gehen die neuen Config-Werte (Spiele-Scan-Cache, Proton-Auswahl pro Spiel) nicht mehr verloren — die Config-Whitelist wurde entsprechend erweitert.

---

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
