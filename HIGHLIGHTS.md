# Highlights - Yakuda Connect

### 🚀 v1.3.5 — 2026-09-23

#### 🇩🇪 Deutsch

* **Terminal-Modus – Yakuda Connect ohne Oberfläche.** Spart RAM unter VR: `YC-wivrn-toggle` schaltet den Server an/aus, `YC-openvr`, `YC-encoder` und `YC-GPU` wählen per Nummer, `YC-status` zeigt alles auf einen Blick, `YC-help` erklärt den Rest.
* **Autostart und Kopplung auch im Terminal.** Deine Autostart-Programme starten, sobald das Headset verbunden ist. `YC-killapps` schließt sie, `YC-autostart-reset` setzt den Start-Timer zurück, und `YC-pairing` zeigt dir die PIN zum Koppeln.
* **Passt zu deiner Installation.** Mit AUR und dem curl-Installer sind die Befehle sofort da. Bei AppImage oder Quellcode richtet sie Einstellungen → Erweitert → „Befehle einrichten“ ein.
* **Ein Klick ins Terminal.** „Im Terminal starten“ öffnet das Menü und schließt die Oberfläche – der WiVRn-Server läuft einfach weiter.
* **AppImage aktualisiert sich sparsam.** Mit AppImageUpdate, AppImageLauncher, AppManager oder AM lädt ein Update nur noch die Änderungen statt der ganzen Datei.

#### 🇬🇧 English

* **Terminal mode – Yakuda Connect without the GUI.** Saves RAM in VR: `YC-wivrn-toggle` turns the server on/off, `YC-openvr`, `YC-encoder` and `YC-GPU` pick by number, `YC-status` shows everything at a glance, `YC-help` explains the rest.
* **Autostart and pairing in the terminal too.** Your autostart programs start as soon as the headset connects. `YC-killapps` closes them, `YC-autostart-reset` resets the start timer, and `YC-pairing` shows you the PIN for pairing.
* **Fits how you installed.** With AUR and the curl installer the commands are there right away. For AppImage or source, Settings → Advanced → “Set up commands” sets them up.
* **One click to the terminal.** “Start in terminal” opens the menu and closes the GUI – the WiVRn server just keeps running.
* **AppImage updates use less data.** With AppImageUpdate, AppImageLauncher, AppManager or AM an update only downloads the changes instead of the whole file.

---

### 🚀 v1.3.4 — 2026-09-22

#### 🇩🇪 Deutsch

* **Schneller und leichter.** Yakuda Connect startet rund 3 Sekunden schneller, friert beim Start nicht mehr ein und belastet das System im Betrieb weniger – wichtig, wenn nebenbei VR läuft. Dein gewähltes Design bleibt jetzt auch nach einem Neustart erhalten.
* **Alte SteamVR-Spiele ohne Action-Datei umbelegen.** Spiele wie Gal*Gun 2, bei denen es nichts zum Bearbeiten gibt, lassen sich jetzt über xrizer und xrBinder umbelegen – ohne Community-Bindings.
* **Stick kippen statt drücken.** Für Funktionen auf „Stick drücken“ gibt es im Dialog „⇄ Kippen“: dann reicht schon das Kippen – praktisch für Menüs und Snap-Turn in älteren Spielen.
* **Deadzone gegen Stick-Drift.** Stick anklicken → Tab „◎ Deadzone“ mit Reglern für Links, Rechts und Beide: Läuft oder dreht sich deine Figur von selbst, einfach hochdrehen.
* **Stick-Drücken funktioniert wirklich.** Verschieben und Kippen kamen im Spiel bisher nie an (falscher Pfad für beide Hände) – behoben, deine Belegungen werden beim Start automatisch repariert.

#### 🇬🇧 English

* **Faster and lighter.** Yakuda Connect starts about 3 seconds faster, no longer freezes at startup and puts less load on your system while running – important with VR going on. Your chosen design now also survives a restart.
* **Remap old SteamVR games without an action file.** Games like Gal*Gun 2, which have nothing to edit, can now be remapped via xrizer and xrBinder – no community bindings needed.
* **Tilt the stick instead of clicking.** Functions on “stick press” get a “⇄ Tilt” option in the dialog: just tilting is enough – handy for menus and snap turn in older games.
* **Deadzone against stick drift.** Click the stick → “◎ Deadzone” tab with sliders for left, right and both: if your character walks or turns on its own, just turn it up.
* **Stick remaps actually work.** Moving and tilt never reached the game (wrong path for both hands) – fixed, your bindings are repaired automatically at startup.

---

### 🚀 v1.3.3 — 2026-09-21

#### 🇩🇪 Deutsch

* **OpenXR-Spiele umbelegen – genau wie OpenVR-Spiele.** Spiele ohne SteamVR-Bindings (z. B. viele Unreal-Spiele unter Proton wie Wanderer) stehen jetzt mit „· OpenXR“ in derselben Spieleliste und bekommen dieselbe Controller-Ansicht. Im Hintergrund arbeitet [xrBinder](https://gitlab.com/mittorn/xrBinder) von mittorn.
* **Ein Schalter richtet alles ein.** Die neue Karte „xrBinder“ oben im Controls-Tab baut und aktiviert xrBinder. Danach das Spiel einmal starten – es taucht von selbst in der Liste auf.
* **Taste anklicken, Funktion zuweisen.** Der Dialog zeigt nur die Funktionen deines Controllers; alles für andere Controller steht unten in einem eigenen Menü. „✕“ nimmt eine Funktion weg, „↪“ zeigt, was verschoben wurde.
* **Zurück auf Standard.** Pro Taste im Dialog oder alles auf einmal mit „↺ Alles auf Standard“.
* **Live, wo es geht.** Läuft das Spiel, kommt die neue Belegung nach „Speichern“ sofort an – sonst beim nächsten Start.
* **Aufgeräumte Spieleliste.** Oben OpenVR-Spiele, dann OpenXR-Spiele, ganz unten die ohne Action-Datei.
* **Die App sagt dir, was fehlt.** Ist obah oder xrBinder nicht installiert oder aus, steht das oben im Bereich – mit Knopf zum Installieren bzw. Einschalten.

#### 🇬🇧 English

* **Remap OpenXR games – just like OpenVR games.** Games without SteamVR bindings (e.g. many Unreal games under Proton such as Wanderer) now appear with “· OpenXR” in the same game list and get the same controller view. [xrBinder](https://gitlab.com/mittorn/xrBinder) by mittorn does the work in the background.
* **One switch sets everything up.** The new “xrBinder” card at the top of the Controls tab builds and enables xrBinder. Then start the game once – it shows up in the list by itself.
* **Click a button, assign a function.** The dialog only lists functions of your controller; everything meant for other controllers sits at the bottom in its own menu. “✕” removes a function, “↪” shows what was moved.
* **Back to default.** Per button in the dialog, or everything at once with “↺ All to default”.
* **Live where possible.** If the game is running, the new layout arrives right after “Save” – otherwise on the next start.
* **Tidier game list.** OpenVR games first, then OpenXR games, games without an action file at the bottom.
* **The app tells you what's missing.** If obah or xrBinder isn't installed or is switched off, the section says so at the top – with a button to install or switch it on.

### 🚀 v1.3.2 — 2026-09-21

#### 🇩🇪 Deutsch

* **Neue Controller-Bilder, Linien treffen die Tasten.** Touch, Index, Vive, Focus 3 und Gamepad haben neue Bilder, und jeder Punkt sitzt jetzt genau auf seiner Taste.
* **Action-Datei selbst wählen.** Findet die App keine, suchst du sie mit „📂 Action-Datei …“ aus – sie wird gemerkt. Gesucht wird jetzt auch nach Unreal-Dateien und im Proton-Prefix.
* **Controller sauber nebeneinander.** Links und rechts sind gleich groß und bewegen sich gespiegelt, die Linien liegen obendrauf, und in der Mitte hält eine dünne Linie die Controller auf ihrer Seite.
* **Karten in zwei Spalten.** Zieh eine Karte weit nach außen, und sie bekommt ihre eigene Spalte – auf jeder Höhe, die du willst.
* **Scrollen stellt nichts mehr um.** Das Mausrad über einer Aufklappliste scrollt die Seite statt die Auswahl zu ändern.
* **Alle deine Spiele im Controls-Tab.** Die Spielauswahl zeigt jedes Spiel aus dem Games-Tab – auch Nicht-Steam-Spiele und eigene Einträge. Hat ein Spiel keine OpenVR-Action-Datei, steht es grau da und die App sagt dir, warum.

#### 🇬🇧 English

* **New controller images, lines hit the buttons.** Touch, Index, Vive, Focus 3 and Gamepad have new images, and every point now sits right on its button.
* **Pick the action file yourself.** If the app finds none, choose it with "📂 Action file …" — it's remembered. The search now also covers Unreal files and the Proton prefix.
* **Controllers neatly side by side.** Left and right are the same size and move mirror-wise, lines sit on top, and a thin line in the middle keeps each controller on its side.
* **Cards in two columns.** Drag a card far outwards and it gets its own column — at any height you like.
* **Scrolling changes nothing.** The mouse wheel over a dropdown scrolls the page instead of changing the selection.
* **All your games in the Controls tab.** The game picker lists every game from the Games tab — non-Steam games and your own entries included. If a game has no OpenVR action file, it's greyed out and the app tells you why.

### 🚀 v1.3.1 — 2026-09-19

#### 🇩🇪 Deutsch

* **obah und XR HOTAS mit einem Klick.** Im Tools-Tab gibt es die neue Methode „Cargo“. Sie funktioniert auf jeder Distribution und installiert fehlendes Rust und benötigte Bibliotheken gleich mit.
* **Du siehst, was passiert.** Die Installation läuft in einem Terminal. Geht etwas schief, bleibt das Fenster offen, und ein Protokoll liegt im Tool-Ordner.
* **Updates inklusive.** Gibt es eine neue Version, zeigt die Karte „Aktualisieren“.
* **Neuer Tab „Controls“.** Schalter für XR HOTAS und obah: einschalten, und fehlt das Werkzeug, fragt die App, wie sie es installieren soll – den Rest erledigt sie.
* **obah-Auswahl ohne Terminal.** Spiel, Controller und zu ladende Bindings als Dropdowns – mit Häkchen, was es schon gibt.
* **Bindings wie in SteamVR ansehen und bearbeiten.** Jedes Action Set als Tab, alle sieben Controller gezeichnet, eine Linie von jeder Belegung zur Taste. Voreingestellt: VRChat · Touch · xrizer. Klick auf eine Taste zum Bearbeiten, Speichern als xrizer/VapoR/OpenComposite.
* **Selbst gestalten, ohne Durcheinander.** Karten ziehst du in jede Reihenfolge – die Karte darunter macht Platz, und es überlagert sich nichts. Den Controller verschiebst du für sich allein.
* **Eigene Profile.** Anordnung und Belegung unter einem Namen speichern und jederzeit wieder laden.
* **Posen, Haptik und Chords.** Alles, was in obah unter „Other" und „Chords" steht, gibt es hier in zwei eigenen Kästen – Tastenkombinationen inklusive.
* **Nichts geht verloren.** Beim Schließen mit ungespeicherten Änderungen fragt die App nach.
* **Eigene Controller-Bilder.** Die gezeichneten Controller liegen jetzt als Bilddateien in `assets/controls` und lassen sich austauschen — eigene Bilder kommen nach `~/.config/yakuda-connect/controls/` und überleben jedes Update.
* **Mehr Übersicht, weniger Scrollen.** Beide Controller sitzen mittig im Kasten, „Controls per obah" klappt wirklich alles ein (nicht nur die Auswahl), und Posen/Vibration/Chords haben einen eigenen Aufklapp-Abschnitt, der zu bleibt, bis du ihn brauchst.
* **Aufgeräumt-Modus.** Ein Knopf, und die Karten zeigen nur noch den Namen der Taste statt der ganzen Belegung. Einzelne Karten klappst du per Rechtsklick auf und zu; versteckst du die letzte von Hand, rastet der Knopf von selbst ein.
* **Programme direkt aus dem Tools-Tab starten.** Jede installierte Karte hat jetzt „▶ Starten". Kommandozeilenprogramme wie obah oder XR HOTAS öffnen dabei ein Terminal, alles andere startet einfach.
* **Die richtige Grafikkarte für WiVRn.** Unter Streaming wählst du aus, welche Karte benutzt wird. Auf Rechnern mit Prozessorgrafik und Steckkarte landet WiVRn sonst gern auf der falschen — beim vaapi-Encoder wird auch auf der gewählten Karte kodiert.

#### 🇬🇧 English

* **obah and XR HOTAS in one click.** The Tools tab has a new "Cargo" method. It works on any distribution and installs missing Rust and required libraries along the way.
* **You see what's happening.** The installation runs in a terminal. If something goes wrong, the window stays open and a log is kept in the tool folder.
* **Updates included.** When a new version is out, the card shows "Update".
* **New "Controls" tab.** Switches for XR HOTAS and obah: turn one on, and if the tool is missing, the app asks how to install it and does the rest.
* **obah selection without a terminal.** Game, controller and bindings to load as dropdowns — with checkmarks for what already exists.
* **See and edit bindings like in SteamVR.** Every action set as a tab, all seven controllers drawn, a line from each binding to its button. Preset: VRChat · Touch · xrizer. Click a button to edit, save as xrizer/VapoR/OpenComposite.
* **Arrange it yourself, without the mess.** Drag cards into any order — the card below makes room and nothing overlaps. The controller moves on its own.
* **Your own profiles.** Save arrangement and bindings under a name and load them back any time.
* **Poses, haptics and chords.** Everything obah keeps under "Other" and "Chords" gets its own box here — button combinations included.
* **Nothing gets lost.** Closing the app with unsaved changes asks first.
* **Your own controller images.** The drawn controllers are image files now, in `assets/controls`, and can be swapped — your own go into `~/.config/yakuda-connect/controls/` and survive every update.
* **More overview, less scrolling.** Both controllers sit centred in the box, "Controls via obah" really collapses everything (not just the selection), and poses/haptics/chords get their own collapsible section that stays closed until you need it.
* **Tidy view.** One button and the cards show only the input name instead of the whole binding. Single cards fold and unfold with a right-click; hide the last one by hand and the button latches on by itself.
* **Launch programs straight from the Tools tab.** Every installed card now has "▶ Start". Command-line tools such as obah or XR HOTAS open in a terminal, everything else just starts.
* **The right graphics card for WiVRn.** Under Streaming you pick which card is used. On machines with integrated graphics plus an add-in card WiVRn tends to pick the wrong one — with the vaapi encoder it encodes on the chosen card too.

### 🚀 v1.3.0 — 2026-09-16

#### 🇩🇪 Deutsch

* **VR geht aus, wenn du die App schließt.** Der WiVRn-Server und deine Autostart-Programme werden beendet, egal ob du auf X klickst, die App über die Taskleiste schließt oder sie im Taskmanager beendest. Das klappt sogar, wenn die App abstürzt. Wer das nicht möchte, schaltet es unter Einstellungen → Erweitert / System aus.
* **Nicht-Steam-Spiele im Games-Tab.** Spiele, die du in Steam als Nicht-Steam-Spiel hinzugefügt hast (z. B. über Heroic oder Lutris), findest du jetzt unter „+ Spiel hinzufügen". Sie bekommen dieselben Einstellungen wie Steam-Spiele: Proton-Version, Startparameter, Backup und Play-Knopf.
* **Windows-Spiele mit einem Klick in Steam.** Wählst du beim eigenen Spiel eine .exe, trägt die App sie auf Wunsch direkt als Nicht-Steam-Spiel in Steam ein. So bekommt das Spiel Proton und alle Einstellungen.
* **Eigene Bilder.** Für eigene Spiele und Nicht-Steam-Spiele kannst du jetzt ein Bild für die Kachel wählen. Bei Nicht-Steam-Spielen geht das schon beim Hinzufügen, und Steam zeigt das Bild auch an.
* **Proton-Auswahl, die in Steam wirklich ankommt.** „Use" setzt jetzt zuverlässig den Haken „Kompatibilitätswerkzeug erzwingen" in Steam, auch für Nicht-Steam-Spiele und für Steams eigenes Proton. Läuft Steam, bietet die App an, es kurz zu beenden, weil Steam die Auswahl sonst wieder überschreibt.
* **Changelog und Highlights direkt in der App.** Unter Einstellungen → Allgemein & Updates gibt es zwei neue Knöpfe. Du liest gerade einen davon.
* **Aufgeräumte Einstellungen.** Die Spiele-Einstellungen sind nach „Erweitert / System" umgezogen.

#### 🇬🇧 English

* **VR turns off when you close the app.** The WiVRn server and your autostart programs are stopped, whether you click X, close the app from the taskbar or end it in a task manager. This even works if the app crashes. If you don't want this, turn it off under Settings → Advanced / System.
* **Non-Steam games in the Games tab.** Games you added to Steam as non-Steam games (for example via Heroic or Lutris) now show up under "+ Add Game". They get the same settings as Steam games: Proton version, launch options, backup and play button.
* **Windows games into Steam with one click.** If you pick a .exe as your own game, the app can add it to Steam as a non-Steam game right away, so it gets Proton and all settings.
* **Your own images.** Own games and non-Steam games can now get a tile image. For non-Steam games you can pick it right when adding them, and Steam shows it too.
* **Proton selection that really reaches Steam.** "Use" now reliably ticks "Force the use of a specific compatibility tool" in Steam, also for non-Steam games and Steam's own Proton. If Steam is running, the app offers to close it briefly, because Steam would otherwise overwrite the selection.
* **Changelog and highlights inside the app.** Two new buttons under Settings → General & Updates. You are reading one of them right now.
* **Tidier settings.** The games settings moved to "Advanced / System".

### 🚀 v1.2.9 — 2026-09-16

#### 🇩🇪 Deutsch

* **Der Games-Tab findet deine VR-Spiele zuverlässiger und schneller.** Er fragt jetzt Steam selbst, welche Spiele VR können, statt zu raten.
* **Er sucht von allein.** Beim Öffnen des Tabs wird automatisch gescannt, du musst den Knopf nicht mehr finden.
* **Eigene Spiele hinzufügen.** Fehlt ein Spiel, trägst du es über „+ Spiel hinzufügen" selbst ein, auch Spiele außerhalb von Steam.
* **Spiele entfernen.** Ein falsch erkanntes Spiel nimmst du mit einem Klick aus der Liste. Deinstalliert wird dabei nichts.

#### 🇬🇧 English

* **The Games tab finds your VR games more reliably and faster.** It now asks Steam itself which games support VR instead of guessing.
* **It scans on its own.** Opening the tab starts a scan automatically, no need to find the button.
* **Add your own games.** If a game is missing, add it with "+ Add Game", including games outside Steam.
* **Remove games.** Remove a wrongly detected game with one click. Nothing gets uninstalled.

### 🚀 v1.2.8 — 2026-09-15

#### 🇩🇪 Deutsch

* **Headset per USB verbinden, mit einem Klick.** Neuer Knopf „Verbinden (USB)", und die automatische USB-Verbindung funktioniert jetzt wirklich.
* **„adb reparieren".** Erkennt das Headset am Kabel nicht, findet die App die üblichen Ursachen und behebt sie.
* **Diagnose kopieren.** Ein Klick legt alle wichtigen Infos für den Support in die Zwischenablage, ohne persönliche Daten.
* **WiVRn-App fürs Headset.** Die App lädt jetzt die Version, die zu deinem Server passt, und kann sie auch nur herunterladen.

#### 🇬🇧 English

* **Connect your headset over USB with one click.** New "Connect (USB)" button, and automatic USB connection now really works.
* **"Repair adb".** If the headset isn't recognized over the cable, the app finds the usual causes and fixes them.
* **Copy diagnostics.** One click puts all important support info on your clipboard, without personal data.
* **WiVRn app for the headset.** The app now downloads the version that matches your server, and can also just download it.

### 🚀 v1.2.7 — 2026-09-14

#### 🇩🇪 Deutsch

* **VRChat: dritte Proton-Auswahl „safe"** und ein neuer Schalter für natives Wayland.
* **Tools-Tab mit Suche und Filtern** nach Kategorie und Installationsstatus, dazu vier neue Werkzeuge.
* **Knopf gegen Ruckeln.** „Netzwerkpuffer fixen" im Dashboard vergrößert die Netzwerkpuffer, dauerhaft oder nur für diese Sitzung.
* **Autostart:** Programme werden beim Eintippen vorgeschlagen.

#### 🇬🇧 English

* **VRChat: a third Proton option "safe"** and a new switch for native Wayland.
* **Tools tab with search and filters** by category and install status, plus four new tools.
* **A button against stutter.** "Fix network buffers" on the dashboard enlarges network buffers, permanently or just for this session.
* **Autostart:** programs are suggested while you type.

### 🚀 v1.2.6 — 2026-08-28

#### 🇩🇪 Deutsch

* **Dein Hintergrundbild ist jetzt wirklich zu sehen**, und der Deckkraft-Regler für die Karten funktioniert.

#### 🇬🇧 English

* **Your background image is now actually visible**, and the card opacity slider works.

### 🚀 v1.2.5 — 2026-08-28

#### 🇩🇪 Deutsch

* **WiVRn geht beim ersten Klick aus.** Vorher musste man den Server manchmal zwei- oder dreimal beenden.
* Das Hintergrundbild wird angezeigt, und „Kein Bild" wirkt wieder.

#### 🇬🇧 English

* **WiVRn stops on the first click.** Before, you sometimes had to stop the server two or three times.
* The background image is shown, and "No image" works again.

### 🚀 v1.2.4 — 2026-08-25

#### 🇩🇪 Deutsch

* **Debian, Ubuntu und Linux Mint:** WiVRn lässt sich jetzt direkt aus der App installieren, standardmäßig als Flatpak.

#### 🇬🇧 English

* **Debian, Ubuntu and Linux Mint:** WiVRn can now be installed right from the app, as a Flatpak by default.

### 🚀 v1.2.3 — 2026-08-25

#### 🇩🇪 Deutsch

* **Neuer Bereich „Design".** Wähle ein Farbthema oder ein eigenes Hintergrundbild.
* **Viel besser auf Fedora:** xrizer, OpenComposite und weitere Tools lassen sich aus der App installieren.
* **Installations-Tab aufgeräumt:** Quelle und Knopf pro Programm, Status wird beim Öffnen geprüft.
* Das Installationsskript läuft jetzt auch auf Linux Mint und Ubuntu 24.04.

#### 🇬🇧 English

* **New "Design" section.** Pick a color theme or your own background image.
* **Much better on Fedora:** xrizer, OpenComposite and more tools can be installed from the app.
* **Tidier install tab:** source and button per program, status is checked when you open it.
* The install script now also runs on Linux Mint and Ubuntu 24.04.

### 🚀 v1.2.1 — 2026-08-23

#### 🇩🇪 Deutsch

* **Advanced Mode.** Wer mag, sieht zu vielen Knöpfen, was technisch dahinter passiert.
* Firewall-Knopf und Encoder-Auswahl sind besser erklärt, Info-Symbole sind wieder anklickbar.
* Der Update-Check alter Versionen funktioniert wieder.

#### 🇬🇧 English

* **Advanced Mode.** If you like, many buttons now show what happens behind the scenes.
* The firewall button and encoder choice are explained better, info icons are clickable again.
* The update check of older versions works again.

### 🚀 v1.2.0 — 2026-08-22

#### 🇩🇪 Deutsch

* **Unterstützen jetzt über Ko-fi** statt PayPal.

#### 🇬🇧 English

* **Support now goes through Ko-fi** instead of PayPal.

### 🚀 v1.1.9 — 2026-08-20

#### 🇩🇪 Deutsch

* **VRChat-Videoplayer reparieren.** Neue Knöpfe erklären, prüfen und beheben, warum YouTube-Videos in VRChat nicht laden, inklusive Installation von VRCVideoCacher.
* **Spiel-Einstellungen sichern und zurückspielen.** Praktisch, wenn Steam nach einem Proton-Wechsel alles zurücksetzt.
* „Symlink erstellen" heißt jetzt „Picture Fix".

#### 🇬🇧 English

* **Fix the VRChat video player.** New buttons explain, check and fix why YouTube videos don't load in VRChat, including installing VRCVideoCacher.
* **Back up and restore game settings.** Handy when Steam resets everything after a Proton change.
* "Create symlink" is now called "Picture Fix".

### 🚀 v1.1.8 — 2026-08-18

#### 🇩🇪 Deutsch

* **Umschalten zwischen WiVRn und SteamVR klappt sauberer**, und die App merkt sich deine vorherige Einstellung.
* Einmalig wird automatisch auf xrizer umgestellt, wenn alles dafür bereit ist.

#### 🇬🇧 English

* **Switching between WiVRn and SteamVR works more cleanly**, and the app remembers your previous setting.
* A one-time automatic switch to xrizer happens when everything is ready for it.

### 🚀 v1.1.7 — 2026-08-15

#### 🇩🇪 Deutsch

* **Die Headset-Liste zeigt, welche Brille gerade am USB-Kabel hängt.**
* OpenVR-Kompatibilität und Encoder-Einstellung funktionieren jetzt wie in WiVRn selbst.
* Quest-Nutzer finden unter dem APK-Installer einen Link zum Meta Store.

#### 🇬🇧 English

* **The headset list shows which headset is connected over USB.**
* OpenVR compatibility and encoder settings now work like in WiVRn itself.
* Quest users find a Meta Store link below the APK installer.

### 🚀 v1.1.6 — 2026-08-14

#### 🇩🇪 Deutsch

* **Nur noch eine AppImage**, die auf neuen und älteren Systemen startet.
* **Firewall-Freigabe funktioniert wie bei WiVRn**, das Headset findet den PC jetzt zuverlässig.
* Dialoge sind auf hellen Desktop-Themes lesbar, und die englische Oberfläche ist komplett englisch.
* OpenXR-Fixes und VR-Priorität liegen jetzt unter Einstellungen → VR & OpenXR.

#### 🇬🇧 English

* **Only one AppImage** that starts on new and older systems.
* **The firewall setup works like WiVRn's**, so the headset finds the PC reliably.
* Dialogs are readable on light desktop themes, and the English interface is fully English.
* OpenXR fixes and VR priority now live under Settings → VR & OpenXR.

### 🚀 v1.1.5 — 2026-08-14

#### 🇩🇪 Deutsch

* **Stabiler:** Einstellungen gehen beim Speichern nicht mehr verloren, das Fenster friert nicht mehr ein, und beim Schließen stürzt nichts mehr ab.
* **Logdatei mit Knöpfen zum Öffnen und Kopieren**, damit Hilfe im Fehlerfall leichter ist.
* **Automatisch per USB verbinden** als neue Option im Dashboard.
* Die App startet spürbar schneller.

#### 🇬🇧 English

* **More stable:** settings are no longer lost when saving, the window doesn't freeze, and closing no longer crashes.
* **A log file with buttons to open and copy it**, which makes getting help easier.
* **Connect over USB automatically** as a new dashboard option.
* The app starts noticeably faster.

### 🚀 v1.1.4 — 2026-08-06

#### 🇩🇪 Deutsch

* **Wichtige Reparatur:** Nach einer Wiederherstellung startete Steam auf Nicht-Arch-Distributionen nicht mehr. Das ist behoben.
* Die App prüft beim Start, ob deine OpenXR-Einstellungen Steam kaputtmachen könnten.

#### 🇬🇧 English

* **Important fix:** after a restore, Steam no longer started on non-Arch distributions. This is fixed.
* On startup, the app checks whether your OpenXR settings could break Steam.

### 🚀 v1.1.3 — 2026-07-25

#### 🇩🇪 Deutsch

* **Face- und Eye-Tracking:** VRCFaceTracking und Project Babble sind im OSC-Apps-Tab dabei.
* **Mehr Proton-Auswahl je nach System** und Installation per Klick über ProtonPlus.
* Neuer Schalter, um Spiele mit GameMode zu starten.

#### 🇬🇧 English

* **Face and eye tracking:** VRCFaceTracking and Project Babble are now in the OSC Apps tab.
* **More Proton options depending on your system**, installable with one click via ProtonPlus.
* A new switch to launch games with GameMode.

### 🚀 v1.1.2 — 2026-07-22

#### 🇩🇪 Deutsch

* **Übersichtlichere Einstellungen** mit Unterseiten und Info-Symbolen.
* **Mikrofon-Auswahl**, damit dein Mikrofon auch mit neuem Proton im Spiel ankommt.
* **OSC-DreamChatbox** ist im Tools-Tab dabei.

#### 🇬🇧 English

* **Clearer settings** with sub-pages and info icons.
* **Microphone selection**, so your mic still reaches games with newer Proton.
* **OSC-DreamChatbox** is now in the Tools tab.

### 🚀 v1.1.1 — 2026-07-20

#### 🇩🇪 Deutsch

* **Fedora und Ubuntu werden unterstützt.**
* **Coverbilder für jedes Spiel**, und VR-Spiele in großen Bibliotheken werden gefunden.
* WayVR: Design von cubee-cb, SlimeVR-Knöpfe ein- und ausblendbar, eigene Farben.

#### 🇬🇧 English

* **Fedora and Ubuntu are supported.**
* **Cover art for every game**, and VR games in large libraries are found.
* WayVR: design by cubee-cb, SlimeVR buttons can be shown or hidden, custom colors.

### 🚀 v1.1.0 — 2026-07-09

#### 🇩🇪 Deutsch

* **Play-Knopf direkt auf jeder Spielkachel.**
* Übersichtlichere Startparameter und mehr unterstützte VR-Spiele.

#### 🇬🇧 English

* **A play button right on every game tile.**
* Clearer launch options and more supported VR games.

### 🚀 v1.0.9-alpha — 2026-07-09

#### 🇩🇪 Deutsch

* **Neuer Games-Tab.** Zeigt deine VR-Spiele mit passenden Proton-Empfehlungen und Startparametern, und startet sie mit einem Klick.
* Proton-Versionen lassen sich direkt über ProtonPlus installieren.

#### 🇬🇧 English

* **New Games tab.** Shows your VR games with matching Proton recommendations and launch options, and starts them with one click.
* Proton versions can be installed directly via ProtonPlus.

### 🚀 v1.0.8-alpha — 2026-07-05

#### 🇩🇪 Deutsch

* Kleinere Aufräumarbeiten an der Oberfläche.

#### 🇬🇧 English

* Small interface cleanups.

### 🚀 v1.0.7-alpha — 2026-07-05

#### 🇩🇪 Deutsch

* **Neues App-Icon** und ein Bereich „Community & Updates" in den Einstellungen.
* **OpenXR-Fix für SteamVR mit einem Klick.**
* Die App legt automatisch ein erstes Backup deiner VR-Umgebung an.

#### 🇬🇧 English

* **New app icon** and a "Community & Updates" section in the settings.
* **One-click OpenXR fix for SteamVR.**
* The app automatically creates a first backup of your VR setup.

### 🚀 v1.0.6-alpha — 2026-07-03

#### 🇩🇪 Deutsch

* **Die App kann sich selbst aktualisieren.** Ist ein Update da, klick auf den grünen Pfeil im Dashboard.

#### 🇬🇧 English

* **The app can update itself.** When an update is available, click the green arrow on the dashboard.

### 🚀 v1.0.5-alpha — 2026-06-30

#### 🇩🇪 Deutsch

* **Installation per AUR, Flatpak oder AppImage**, passend zu deiner Distribution.
* WiVRn als Flatpak wird voll unterstützt, und NixOS-Nutzer bekommen eine geführte Einrichtung.

#### 🇬🇧 English

* **Install via AUR, Flatpak or AppImage**, matching your distribution.
* WiVRn as a Flatpak is fully supported, and NixOS users get a guided setup.

### 🚀 v1.0.4-alpha — 2026-06-27

#### 🇩🇪 Deutsch

* **Autostart-Programme starten, sobald dein Headset verbunden ist**, und werden mit dem Server wieder beendet.

#### 🇬🇧 English

* **Autostart programs launch as soon as your headset connects**, and stop together with the server.

### 🚀 v1.0.3-alpha — 2026-06-22

#### 🇩🇪 Deutsch

* **VR-Priorität** für ruckelfreieres Streaming.

#### 🇬🇧 English

* **VR priority** for smoother streaming.

### 🚀 v1.0.2-alpha — 2026-06-17

#### 🇩🇪 Deutsch

* **Autostart beim Verbinden des Headsets** und ein 1-Klick-Design für WayVR.

#### 🇬🇧 English

* **Autostart when the headset connects** and a one-click design for WayVR.
