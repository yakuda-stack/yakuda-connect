#!/usr/bin/env python3
"""
core/tabs/games_mixin.py — Games-Tab
====================================
Ausgelagert aus core/main.py, das mit ~3600 Zeilen und rund 150 Methoden in
einer Klasse kaum noch zu ueberblicken war.

Das ist ein MIXIN, keine eigenstaendige Klasse: die Methoden hier arbeiten
weiterhin auf demselben Objekt wie vorher (self.ui, self.APP_VERSION, ...).
VRApp erbt davon, sonst aendert sich am Verhalten nichts — genau deshalb
konnte der Umzug ohne Umschreiben der Methodenrumpfe passieren.

Zustaendig fuer: Steam-Bibliothek scannen, Spielekacheln mit Cover, das
ausklappbare Detailpanel, Proton-Auswahl, Startparameter und den Spielstart.

Die Attribute (self._games_scan_worker, self._selected_proton, ...) werden
weiterhin in VRApp.__init__ gesetzt. Das ist bei Mixins ueblich, aber man
muss es wissen: wer hier ein neues Attribut braucht, legt es dort an.
"""
import os
import subprocess

from PySide6.QtWidgets import (QApplication, QLabel, QMessageBox, QHBoxLayout,
                               QVBoxLayout, QLineEdit, QPushButton,
                               QFrame, QCheckBox)
from PySide6.QtCore import (Qt, QTimer, QSize, QPointF, QThread, QUrl,
                            Signal as QtSignal)
from PySide6.QtGui import (QPixmap, QIcon, QPainter, QPolygonF, QColor,
                           QDesktopServices)

import games as games_db
from install_worker import CoverDownloadWorker, GamesDbWorker
from proton_manual_install import ManualProtonInstallWorker
from translations import tr, get_language

from logging_setup import get_logger

log = get_logger("games_tab")


# --------------------------------------------------------------------------- #
#  Hilfsklassen des Games-Tabs
# --------------------------------------------------------------------------- #
# Lagen frueher in core/main.py, werden aber ausschliesslich hier gebraucht.
# Sie wandern deshalb mit um — sonst muesste das Mixin aus main.py importieren,
# und main.py importiert das Mixin: ein Ringimport, den Python beim Start mit
# einem ImportError quittiert.

def make_play_icon(size=14, color="#21252b"):
    """
    Zeichnet ein gefülltes Play-Dreieck als Icon.

    Bewusst selbst gezeichnet statt des Unicode-Zeichens "▶": Das Zeichen
    fehlt in manchen System-Schriften oder wird als Kästchen/hauchdünner
    Pfeil gerendert. Ein gemaltes Dreieck sieht auf jeder Distro identisch
    und klar nach "Play" aus.
    """
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    # Leicht eingerückt, damit das Dreieck optisch mittig sitzt
    inset = size * 0.14
    tri = QPolygonF([
        QPointF(inset * 1.6, inset),               # oben links
        QPointF(size - inset, size / 2.0),         # Spitze rechts (Mitte)
        QPointF(inset * 1.6, size - inset),        # unten links
    ])
    p.drawPolygon(tri)
    p.end()
    return QIcon(pm)


class ClickableFrame(QFrame):
    """QFrame, das wie ein großer Button funktioniert (für die Spiel-Kacheln)."""
    clicked = QtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class GameScanWorker(QThread):
    """Scannt die Steam-Bibliotheken im Hintergrund nach ALLEN VR-Spielen."""
    result_signal = QtSignal(object)  # (tested: [appid], untested: [{appid,name}])

    def run(self):
        try:
            result = games_db.scan_installed_games()
        except Exception as e:
            log.warning(f"[Games] Scan fehlgeschlagen: {e}")
            result = ([], [])
        self.result_signal.emit(result)


class VRCVideoCacherInstallWorker(QThread):
    """Laedt VRCVideoCacher herunter und legt die Desktop-Verknuepfung an.

    Die Binary ist einige Dutzend MB gross — im GUI-Thread waere die App
    waehrenddessen eingefroren.
    """
    progress_signal = QtSignal(int, int)      # geladen, gesamt (Bytes)
    done_signal = QtSignal(bool, str, bool)   # ok, meldung, desktop_ok

    def run(self):
        try:
            import vrcvideocacher_install as vci
            ok, msg = vci.download(
                progress=lambda d, t: self.progress_signal.emit(d, t))
            desktop_ok = False
            if ok:
                desktop_ok, _ = vci.create_desktop_entry()
        except Exception as e:
            log.warning(f"[Games] VRCVideoCacher-Installation: {e}")
            ok, msg, desktop_ok = False, str(e), False
        self.done_signal.emit(ok, msg, desktop_ok)


class VRChatCheckWorker(QThread):
    """Fuehrt die VRChat-Videoplayer-Diagnose im Hintergrund aus.

    Die Pruefungen lesen Logdateien (bis einige MB) und rufen pgrep/timedatectl
    auf. Einzeln schnell, zusammen aber genug, um die GUI sichtbar haengen zu
    lassen — deshalb ein eigener Thread.
    """
    result_signal = QtSignal(object)   # Liste von Pruefergebnissen

    def run(self):
        try:
            import vrchat_check
            results = vrchat_check.run_all()
        except Exception as e:
            log.warning(f"[Games] VRChat-Check fehlgeschlagen: {e}")
            results = []
        self.result_signal.emit(results)


class ProtonPlusInstallWorker(QThread):
    """
    Öffnet ein Terminal ("in deine Fresse") mit der interaktiven
    ProtonPlus-CLI-Installation eines Runners, z. B.:
        protonplus install steam-system proton-ge-rtsp
    Ohne 'latest' listet ProtonPlus alle Releases auf und der Nutzer
    wählt die empfohlene Version per Nummer aus.
    """
    finished_signal = QtSignal(bool)

    def __init__(self, cli_cmd):
        super().__init__()
        self.cli_cmd = cli_cmd  # Liste, z. B. ["protonplus", "install", ...]

    def run(self):
        from install_worker import find_terminal
        terminal, exec_flags = find_terminal()
        if terminal is None or not self.cli_cmd:
            self.finished_signal.emit(False)
            return
        cli_str = " ".join(self.cli_cmd)
        bash_cmd = (
            f"echo '=== ProtonPlus: {cli_str} ==='; "
            f"{cli_str}; "
            "echo ''; echo 'Fertig. Dieses Fenster schliesst sich gleich automatisch...'; "
            "sleep 3"
        )
        cmd = [terminal] + exec_flags + ["bash", "-c", bash_cmd]
        try:
            proc = subprocess.Popen(cmd)
            proc.wait()
            self.finished_signal.emit(proc.returncode == 0)
        except Exception as e:
            log.warning(f"[Games] ProtonPlus-Terminal konnte nicht geöffnet werden: {e}")
            self.finished_signal.emit(False)


class GamesTabMixin:
    """Alles rund um den Games-Tab. Wird von VRApp geerbt."""

    def on_games_tab_opened(self):
        """
        Jeder Klick auf den Tab: erst den Cache zeigen, dann im Hintergrund
        nachsehen.

        Bis v1.2.8 passierte hier nur beim ALLERERSTEN Besuch etwas; danach
        musste man den "Spiele scannen"-Knopf treffen. Den haben viele
        schlicht übersehen und standen vor einer unvollständigen oder leeren
        Liste — der häufigste Grund für "erkennt meine Spiele nicht".

        Jetzt gilt:
          1. Gecachte Spiele sofort anzeigen (kein Warten, kein Flackern).
          2. Wenn der Auto-Scan an ist (Standard), im Hintergrund neu scannen.
             Das kostet nur Millisekunden, weil der Scanner Steams eigene
             Kennzeichnung liest statt Verzeichnisse zu durchsuchen.
          3. Die Kacheln werden NUR neu gebaut, wenn sich wirklich etwas
             geändert hat — sonst würde ein aufgeklapptes Spiel bei jedem
             Tab-Wechsel zuklappen.

        Abschaltbar unter Einstellungen -> Erweitert / System -> Spiele.
        """
        first_visit = not self._games_tab_visited
        self._games_tab_visited = True

        tested, untested, was_scanned = games_db.load_cached_games()
        if was_scanned and first_visit:
            self.render_games_cards(tested, untested)

        if not was_scanned:
            self.start_games_scan()          # noch nie gescannt: immer
        elif games_db.auto_scan_enabled():
            self.start_games_scan(quiet=True)

    def start_games_scan(self, quiet=False):
        """
        Startet den Steam-Scan im Hintergrund.

        ``quiet=True`` ist der Auto-Scan beim Öffnen des Tabs: die Statuszeile
        bleibt zurückhaltend und die Kacheln werden nur bei einer echten
        Änderung neu gebaut. Der Knopf bleibt dabei bedienbar — ein Scan, den
        der Nutzer gar nicht angestoßen hat, darf ihm nicht die Oberfläche
        sperren.
        """
        if self._games_scan_worker and self._games_scan_worker.isRunning():
            return
        self._games_scan_quiet = bool(quiet)
        if not quiet:
            self.ui.btn_games_scan.setEnabled(False)
            self.ui.lbl_games_status.setText(tr("games_scanning"))
        self._games_scan_worker = GameScanWorker()
        self._games_scan_worker.result_signal.connect(self._on_games_scan_done)
        self._games_scan_worker.start()

    @staticmethod
    def _games_signature(tested, untested, local):
        """Vergleichsschlüssel eines Scan-Ergebnisses.

        Damit lässt sich "hat sich etwas geändert?" beantworten, ohne die
        Kacheln zu vergleichen. Enthält bewusst auch die NAMEN: benennt Steam
        ein Spiel um, soll die Kachel das mitbekommen.
        """
        return (
            tuple(sorted(str(a) for a in tested)),
            tuple(sorted((g["appid"], g["name"]) for g in untested)),
            tuple(sorted((g["id"], g["name"]) for g in local)),
        )

    def _on_games_scan_done(self, result):
        """Scan fertig: Ergebnis fest in die Config schreiben + anzeigen."""
        tested, untested = result
        games_db.save_cached_games(tested, untested)
        self.ui.btn_games_scan.setEnabled(True)

        quiet = getattr(self, "_games_scan_quiet", False)
        self._games_scan_quiet = False
        signature = self._games_signature(tested, untested,
                                          games_db.load_local_games())
        if quiet and signature == getattr(self, "_rendered_games_key", None):
            return          # nichts Neues -> offenes Panel nicht zerstören
        self.render_games_cards(tested, untested)

    def refresh_games_cards(self):
        """Kacheln aus dem Cache neu aufbauen (nach dem Hinzufügen/Entfernen
        eines Eintrags). Ohne Scan — die Änderung kommt ja von uns selbst."""
        tested, untested, _was = games_db.load_cached_games()
        self.render_games_cards(tested, untested)

    # ------------------------------------------------------------------ #
    #  "+ Spiel hinzufügen"
    # ------------------------------------------------------------------ #
    def open_add_game_dialog(self):
        """Öffnet den zweispaltigen Dialog (Steam-Spiel / eigenes Spiel).

        Ein von Hand ergänztes STEAM-Spiel muss anschließend einmal durch den
        Scan: erst der liest Name und Installationsort aus der Bibliothek und
        schreibt beides in den Cache, aus dem die Kacheln entstehen. Ein
        eigenes Spiel steht dagegen vollständig in der Config — dort genügt
        ein Neuaufbau.
        """
        from games_add_dialog import AddGameDialog

        dialog = AddGameDialog(self)
        dialog.game_added.connect(self.refresh_games_cards)
        dialog.exec()
        if dialog.changed:
            self.start_games_scan()

    # --- Kachel-Grid + Akkordeon -------------------------------------- #
    GAMES_TILES_PER_ROW = 4          # Kacheln pro Zeile
    GAMES_TILE_W, GAMES_TILE_H = 150, 240   # Kachelgröße
    GAMES_COVER_W, GAMES_COVER_H = 126, 189 # Coverfläche (2:3 wie Steam-Capsule)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # ----- Spiele-Datenbank (config/games.json): Version + Update ----------- #
    def _refresh_games_db_version(self):
        """Setzt das Versions-Label der Spiele-DB (games.json)."""
        try:
            self.ui.lbl_games_db_ver.setText(
                f"{tr('games_db_version_label')} {games_db.games_config_version()}")
        except Exception as exc:
            log.debug("_refresh_games_db_version: ignoriert — %s", exc)

    def _check_games_db_update(self):
        """Hintergrund-Check, ob auf GitHub eine neuere games.json liegt."""
        from main import startup_netcheck_disabled
        if startup_netcheck_disabled():
            return
        self._games_db_check_worker = GamesDbWorker(mode="check")
        self._games_db_check_worker.check_result.connect(self._on_games_db_checked)
        self._games_db_check_worker.start()

    def _on_games_db_checked(self, available, remote_version):
        self._games_db_remote_version = remote_version or ""
        if available and remote_version:
            self.ui.btn_games_db_update.setVisible(True)
            self.ui.btn_games_db_update.setToolTip(
                tr("games_db_update_available").format(version=remote_version))
        else:
            self.ui.btn_games_db_update.setVisible(False)

    def start_games_db_update(self):
        """Klick auf den Update-Button: neue games.json laden und neu einlesen."""
        self.ui.btn_games_db_update.setEnabled(False)
        self.ui.lbl_games_status.setText(tr("games_db_updating"))
        self._games_db_dl_worker = GamesDbWorker(mode="download")
        self._games_db_dl_worker.apply_result.connect(self._on_games_db_updated)
        self._games_db_dl_worker.start()

    def _on_games_db_updated(self, ok, new_version):
        self.ui.btn_games_db_update.setEnabled(True)
        if ok:
            self.ui.btn_games_db_update.setVisible(False)
            self._refresh_games_db_version()
            self.ui.lbl_games_status.setText(
                tr("games_db_updated").format(version=new_version))
            # Kacheln mit der neuen DB neu aufbauen (nur wenn schon gescannt).
            if getattr(self, "_games_tiles", None):
                self.start_games_scan()
        else:
            self.ui.lbl_games_status.setText(tr("games_db_update_failed"))

    def render_games_cards(self, tested, untested):
        """
        Baut die Kacheln in ZWEI Sektionen untereinander:
          * "Getestete VR-Spiele"  : kuratierte Profile aus core/games.py
          * "Ungetestete VR-Spiele": alle übrigen erkannten VR-Spiele —
            bekommen beim Aufklappen automatisch generierte Proton-
            Empfehlungen (games_db.dynamic_protons()).
        Dem Nutzer wird immer der NAME angezeigt, nie die AppID. Leere
        Sektionen bleiben samt Überschrift ausgeblendet.
        """
        # Laufenden Cover-Download stoppen und alte Label-Referenzen verwerfen:
        # die Widgets darunter werden gleich zerstoert.
        if getattr(self, "_cover_worker", None) is not None and self._cover_worker.isRunning():
            self._cover_worker.stop()
            self._cover_worker.wait(2000)
        self._pending_covers = {}

        self._clear_layout(self.ui.games_grid_tested)
        self._clear_layout(self.ui.games_grid_untested)
        self._clear_layout(self.ui.games_grid_local)
        self._games_tiles = {}
        self._games_tile_pos = {}
        self._games_untested_names = {}
        self._games_local_entries = {}
        self._games_detail_widget = None
        self._detail_params_edit = None
        self._detail_status_lbl = None
        self._detail_toggles = {}
        self._detail_custom_edit = None
        self._detail_base_params = ""
        self._expanded_appid = None
        self._selected_proton = games_db.load_selected_protons()

        local = games_db.load_local_games()
        # Was gerade auf dem Schirm steht — daran erkennt der Auto-Scan, ob
        # ein Neuaufbau überhaupt nötig ist.
        self._rendered_games_key = self._games_signature(tested, untested, local)

        total = len(tested) + len(untested) + len(local)
        if total == 0:
            self.ui.lbl_games_tested_header.setVisible(False)
            self.ui.lbl_games_untested_header.setVisible(False)
            self.ui.lbl_games_local_header.setVisible(False)
            self.ui.lbl_games_status.setText(tr("games_none"))
            return
        self.ui.lbl_games_status.setText(tr("games_found").format(n=total))

        # Kacheln liegen auf den GERADEN Grid-Zeilen (row*2); die ungeraden
        # Zeilen dazwischen sind für das Inline-Detail-Panel reserviert, das
        # beim Klick direkt unter der Reihe der Kachel erscheint.
        # Sektion 1: getestete Spiele (Profil vorhanden)
        self.ui.lbl_games_tested_header.setVisible(bool(tested))
        for idx, appid in enumerate(tested):
            game = games_db.GAMES.get(appid)
            if not game:
                continue
            tile = self._build_game_tile(appid, game["name"])
            self._games_tiles[appid] = tile
            row, col = divmod(idx, self.GAMES_TILES_PER_ROW)
            self._games_tile_pos[appid] = (self.ui.games_grid_tested, row, col)
            self.ui.games_grid_tested.addWidget(tile, row * 2, col)

        # Sektion 2: ungetestete Spiele (automatische Empfehlung)
        self.ui.lbl_games_untested_header.setVisible(bool(untested))
        for idx, entry in enumerate(untested):
            appid, name = entry["appid"], entry["name"]
            self._games_untested_names[appid] = name
            tile = self._build_game_tile(appid, name)
            self._games_tiles[appid] = tile
            row, col = divmod(idx, self.GAMES_TILES_PER_ROW)
            self._games_tile_pos[appid] = (self.ui.games_grid_untested, row, col)
            self.ui.games_grid_untested.addWidget(tile, row * 2, col)

        # Sektion 3: eigene Spiele (ohne Steam, ohne AppID)
        self.ui.lbl_games_local_header.setVisible(bool(local))
        for idx, entry in enumerate(local):
            gid, name = entry["id"], entry["name"]
            self._games_local_entries[gid] = entry
            tile = self._build_game_tile(gid, name)
            self._games_tiles[gid] = tile
            row, col = divmod(idx, self.GAMES_TILES_PER_ROW)
            self._games_tile_pos[gid] = (self.ui.games_grid_local, row, col)
            self.ui.games_grid_local.addWidget(tile, row * 2, col)

        # Fehlende Cover jetzt im Hintergrund vom Steam-CDN holen
        self._start_cover_downloads()

    # ----------------------------------------------------------------- #
    #  Spiel-Cover aus dem Netz nachladen
    # ----------------------------------------------------------------- #
    def _start_cover_downloads(self):
        """
        Startet den Hintergrund-Download für alle Kacheln ohne Bild.
        Läuft in einem QThread, damit das Fenster nicht einfriert.
        """
        if not self._pending_covers:
            return
        if self._cover_worker is not None and self._cover_worker.isRunning():
            self._cover_worker.stop()
            self._cover_worker.wait(2000)
        self._cover_worker = CoverDownloadWorker(list(self._pending_covers.keys()))
        self._cover_worker.cover_ready.connect(self._on_cover_ready)
        self._cover_worker.start()

    def _on_cover_ready(self, appid, path):
        """Ein Cover ist da -> Platzhalter der Kachel durch das Bild ersetzen."""
        lbl = self._pending_covers.pop(str(appid), None)
        if lbl is None:
            return
        try:
            pix = QPixmap(path)
            if pix.isNull():
                return
            # Platzhalter-Styling zurücknehmen (feste Größe + 🎮-Schrift)
            lbl.setText("")
            lbl.setStyleSheet("background: transparent; border: none;")
            lbl.setFixedSize(self.GAMES_COVER_W, self.GAMES_COVER_H)
            lbl.setPixmap(pix.scaled(
                self.GAMES_COVER_W, self.GAMES_COVER_H,
                Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except RuntimeError:
            # Kachel wurde inzwischen neu aufgebaut -> Label existiert nicht mehr
            pass

    def _tile_css(self, selected):
        if selected:
            return """
                QFrame#gameTile { background-color: #2e3440; border: 2px solid #88c0d0;
                                  border-radius: 8px; }
            """
        return """
            QFrame#gameTile { background-color: #21252b; border: 1px solid #2e3440;
                              border-radius: 8px; }
            QFrame#gameTile:hover { background-color: #282c34; border-color: #5e81ac; }
        """

    def _build_game_tile(self, appid, name):
        """
        Das "kleine Viereck" (150x240) — für getestete UND ungetestete
        Spiele identisch: vertikales Steam-Cover aus dem lokalen Cache
        (find_game_cover), Spielname darüber, Pfeil darunter. Die ganze
        Kachel ist klickbar.
        """
        tile = ClickableFrame()
        tile.setObjectName("gameTile")
        tile.setFixedSize(self.GAMES_TILE_W, self.GAMES_TILE_H)
        tile.setCursor(Qt.PointingHandCursor)
        tile.setStyleSheet(self._tile_css(selected=False))

        box = QVBoxLayout(tile)
        box.setContentsMargins(8, 8, 8, 6)
        box.setSpacing(4)

        # Name (sauberer Text über dem Cover)
        lbl_name = QLabel(name)
        lbl_name.setStyleSheet(
            "font-weight: bold; color: #eceff4; font-size: 12px; background: transparent; border: none;")
        lbl_name.setAlignment(Qt.AlignHCenter)
        lbl_name.setWordWrap(True)
        box.addWidget(lbl_name)

        # Vertikales Coverbild aus dem Steam-Cache; Fallback: 🎮-Platzhalter
        lbl_cover = QLabel()
        lbl_cover.setAlignment(Qt.AlignCenter)
        lbl_cover.setStyleSheet("background: transparent; border: none;")
        # Ohne Download: was lokal da ist, erscheint SOFORT (Steam-Cache oder
        # frueher geladenes Cover). Fehlt das Bild, merken wir uns das Label
        # und holen es im Hintergrund vom Steam-CDN nach.
        cover_path = games_db.get_game_cover(appid, allow_download=False)
        pix = QPixmap(cover_path) if cover_path else QPixmap()
        if not pix.isNull():
            lbl_cover.setPixmap(pix.scaled(
                self.GAMES_COVER_W, self.GAMES_COVER_H,
                Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            lbl_cover.setText("🎮")
            lbl_cover.setStyleSheet(
                "font-size: 48px; background-color: #2e3440; border-radius: 6px; border: none;")
            lbl_cover.setFixedSize(self.GAMES_COVER_W, self.GAMES_COVER_H)
            # Nur fuer echte Steam-Spiele nachladen. Eigene Eintraege haben
            # keine AppID — ein Download-Versuch koennte dort nur scheitern
            # und wuerde den Worker mit sinnlosen Anfragen belasten.
            # Nicht-Steam-Spiele ebenso wenig: Steams Bildserver kennt sie nicht.
            if (games_db.steam_appinfo.is_steam_appid(appid)
                    and not games_db.steam_shortcuts.is_shortcut_id(appid)):
                self._pending_covers[str(appid)] = lbl_cover
        box.addWidget(lbl_cover, alignment=Qt.AlignHCenter)

        # Fußzeile der Kachel: [▶ Starten]  ...  [▾ aufklappen]
        # Der ▶-Knopf startet das Spiel SOFORT (gemerkte Proton-Version +
        # gespeicherte Startparameter), ohne dass man aufklappen muss.
        # Der Klick bleibt am Knopf hängen und klappt die Kachel NICHT auf.
        foot = QHBoxLayout()
        foot.setContentsMargins(0, 0, 0, 0)
        foot.setSpacing(4)

        # Grün gefüllter Knopf mit gemaltem Dreieck -> unmissverständlich "Play"
        btn_tile_play = QPushButton()
        btn_tile_play.setObjectName("tilePlay")
        btn_tile_play.setCursor(Qt.PointingHandCursor)
        btn_tile_play.setFixedSize(34, 24)
        btn_tile_play.setIcon(make_play_icon(13, "#21252b"))
        btn_tile_play.setIconSize(QSize(13, 13))
        btn_tile_play.setToolTip(self._tile_play_tooltip(appid, name))
        btn_tile_play.setStyleSheet("""
            QPushButton#tilePlay { background-color: #a3be8c; border: none; border-radius: 4px; }
            QPushButton#tilePlay:hover { background-color: #b8d19f; }
            QPushButton#tilePlay:pressed { background-color: #8fae76; }
        """)
        btn_tile_play.clicked.connect(lambda _, a=appid: self._play_game_from_tile(a))
        foot.addWidget(btn_tile_play)
        foot.addStretch()

        # Kleiner Pfeil: zeigt an, dass die Kachel aufklappbar ist
        lbl_arrow = QLabel("▾")
        lbl_arrow.setStyleSheet(
            "color: #7b88a1; font-size: 12px; background: transparent; border: none;")
        foot.addWidget(lbl_arrow)
        foot.addStretch()
        # Platzhalter, damit der Pfeil trotz ▶-Knopf mittig bleibt
        spacer = QLabel("")
        spacer.setFixedSize(34, 24)
        spacer.setStyleSheet("background: transparent; border: none;")
        foot.addWidget(spacer)

        box.addLayout(foot)
        tile._arrow = lbl_arrow      # zum Umschalten ▾/▴
        tile._play_btn = btn_tile_play

        tile.clicked.connect(lambda a=appid: self._on_game_tile_clicked(a))
        return tile

    def _tile_play_tooltip(self, appid, name):
        """Tooltip des ▶-Knopfs: zeigt, mit welcher Proton-Version gestartet wird."""
        if games_db.is_local_id(appid):
            # Eigene Spiele laufen ohne Proton — eine Versionsangabe waere
            # hier schlicht gelogen.
            return tr("games_local_play_tip").format(name=name)
        version = self._selected_proton.get(appid)
        if version:
            return tr("games_tile_play_tip").format(name=name, proton=version)
        return tr("games_tile_play_tip_default").format(name=name)

    def _game_data_for(self, appid):
        """
        Spieldaten für die Detail-Sektion:
          * getestet   -> kuratierter Eintrag aus games_db.GAMES
          * ungetestet -> synthetischer Eintrag mit automatisch generierten
                          Proton-Empfehlungen und LEEREN Startparametern
                          (der Nutzer kann eigene eintragen).
          * eigenes    -> Eintrag aus der Config, ohne Proton und ohne
                          Steam-Startparameter (kein Steam im Spiel).
        """
        if games_db.is_local_id(appid):
            entry = self._games_local_entries.get(appid) or games_db.local_game(appid)
            if entry is None:
                return None
            return {"name": entry["name"], "local": True, "entry": entry,
                    "protons": [], "launch_params": {}, "fixes": []}

        game = games_db.GAMES.get(appid)
        if game:
            return game
        name = self._games_untested_names.get(appid)
        if name is None:
            return None
        data = {
            "name": name,
            "untested": True,
            "protons": games_db.dynamic_protons(),
            "launch_params": {},
            "fixes": [],
        }
        if games_db.steam_shortcuts.is_shortcut_id(appid):
            # Nicht-Steam-Spiel: dieselben Einstellungen wie ein Steam-Spiel.
            # Die Startparameter, die der Eintrag in Steam schon hatte,
            # werden zur Basis — sonst ueberschriebe der erste Play-Klick
            # z. B. den Heroic-/Lutris-Aufruf, ohne den nichts mehr startet.
            data["shortcut"] = True
            base = games_db.shortcut_base_options(appid)
            data["launch_params"] = {"base": base} if base else {}
        return data

    def _collapse_detail(self):
        """Klappt das aktuell offene Inline-Panel zu (falls eines offen ist)."""
        if self._games_detail_widget is not None:
            self._games_detail_widget.setParent(None)
            self._games_detail_widget.deleteLater()
            self._games_detail_widget = None
        self._detail_params_edit = None
        self._detail_status_lbl = None
        self._detail_toggles = {}
        self._detail_custom_edit = None
        self._detail_base_params = ""
        for a, tile in self._games_tiles.items():
            tile.setStyleSheet(self._tile_css(selected=False))
            if getattr(tile, "_arrow", None):
                tile._arrow.setText("▾")
        self._expanded_appid = None

    def _expand_game(self, appid):
        """
        Klappt das Detail-Panel INLINE auf: es wird in dieselbe Grid-Sektion
        gesetzt, direkt in die (reservierte ungerade) Zeile unter der Reihe
        der angeklickten Kachel — über die volle Breite. So klebt das Panel
        immer am richtigen Spiel, statt global unter der Liste zu hängen.
        """
        game = self._game_data_for(appid)
        pos = self._games_tile_pos.get(appid)
        if not game or not pos:
            return
        grid, row, _col = pos

        self._expanded_appid = appid
        tile = self._games_tiles.get(appid)
        if tile:
            tile.setStyleSheet(self._tile_css(selected=True))
            if getattr(tile, "_arrow", None):
                tile._arrow.setText("▴")

        detail = (self._build_local_game_detail(appid, game["entry"])
                  if game.get("local")
                  else self._build_game_detail(appid, game))
        self._games_detail_widget = detail
        grid.addWidget(detail, row * 2 + 1, 0, 1, self.GAMES_TILES_PER_ROW)

    def _refresh_detail(self):
        """Baut das offene Panel neu auf (z. B. nach 'Use': Aktiv-Badge)."""
        appid = self._expanded_appid
        if appid is None:
            return
        self._collapse_detail()
        self._expand_game(appid)

    def _on_game_tile_clicked(self, appid):
        """
        Akkordeon: Klick klappt das Panel inline unter der Kachel-Reihe auf.
        Erneuter Klick auf dieselbe Kachel (oder Klick auf eine andere)
        klappt das alte Panel wieder zu.
        """
        was_expanded = (appid == self._expanded_appid)
        self._collapse_detail()
        if not was_expanded:
            self._expand_game(appid)

    # ------------------------------------------------------------------ #
    #  "Use" (Proton wählen) + "Play" (Spiel starten)
    # ------------------------------------------------------------------ #
    def _detail_status(self, text, color="#88c0d0"):
        if self._detail_status_lbl is not None:
            self._detail_status_lbl.setText(text)
            self._detail_status_lbl.setStyleSheet(
                f"color: {color}; font-size: 11px; border: none;")

    def _current_toggle_keys(self):
        return [k for k, cb in self._detail_toggles.items() if cb.isChecked()]

    def _update_final_params(self):
        """Baut den finalen Parameter-String neu (Basis + Toggles + Eigene)."""
        if self._detail_params_edit is None:
            return ""
        custom = self._detail_custom_edit.text() if self._detail_custom_edit else ""
        final = games_db.compose_launch_options(
            self._detail_base_params, self._current_toggle_keys(), custom,
            extra_toggles=getattr(self, "_detail_game_toggles", None))
        self._detail_params_edit.setText(final)
        return final

    def _on_launch_opts_changed(self, appid):
        """Toggle geklickt oder eigene Parameter getippt: finalen String neu
        bauen und die Auswahl dauerhaft für dieses Spiel merken."""
        self._update_final_params()
        custom = self._detail_custom_edit.text() if self._detail_custom_edit else ""
        games_db.save_launch_toggles(appid, self._current_toggle_keys(), custom)

    # Wie lange auf das Ende von Steam gewartet wird. Steam speichert beim
    # Beenden Bibliothek und Cloud-Stand — auf langsamen Platten dauert das.
    STEAM_SHUTDOWN_TIMEOUT_MS = 30000
    STEAM_SHUTDOWN_POLL_MS = 500

    def _use_proton(self, appid, proton):
        """
        'Use': setzt diese Proton-Version als aktive Version für das Spiel.

        Geschrieben wird in Steams config.vdf -> CompatToolMapping (gleicher
        Weg wie ProtonPlus). Dieser Eintrag IST der Haken „Die Verwendung
        eines bestimmten Kompatibilitätswerkzeugs erzwingen" in Steams
        Eigenschaften. Damit er wirklich gesetzt ist, müssen drei Dinge
        stimmen:

          1. **Steam darf nicht laufen.** Steam hält config.vdf im Speicher
             und schreibt sie beim Beenden zurück — ein Eintrag von außen
             ist danach weg. Ein Neustart hilft deshalb NICHT, er ist genau
             der Moment, in dem überschrieben wird. Läuft Steam, bietet die
             App an, es zu beenden.
          2. **Der interne Tool-Name**, nicht der Ordnername
             (games_db.compat_mapping_name). Einen unbekannten Namen
             ignoriert Steam, der Haken bleibt aus.
          3. **Auch Valves Proton wird eingetragen.** Früher hieß „Standard"
             „Eintrag entfernen" — Nicht-Steam-Spiele starteten dann ganz
             ohne Proton.

        Danach wird die Datei noch einmal gelesen. Steht der Name nicht
        drin, sagt die App das, statt Erfolg zu melden.
        """
        name, err = games_db.compat_mapping_name(proton)
        if err == "not_installed":
            self._detail_status(tr("games_tool_missing"), "#ebcb8b")
            return
        if err == "valve_missing":
            self._detail_status(tr("games_valve_proton_missing"), "#ebcb8b")
            return

        # Vor dem Wechsel sichern anbieten. Steam legt beim naechsten Start
        # haeufig ein frisches Prefix an — Spielstaende und Einstellungen sind
        # dann weg. Nur fragen, wenn ueberhaupt etwas zu sichern ist.
        if not self._offer_config_backup(appid, proton):
            return          # Nutzer hat abgebrochen

        if games_db.steam_is_running():
            if not self._ask_close_steam():
                self._detail_status(tr("games_use_cancelled_steam"), "#ebcb8b")
                return
            self._close_steam_then(
                lambda a=appid, p=proton, n=name: self._apply_proton(a, p, n))
            return
        self._apply_proton(appid, proton, name)

    def _ask_close_steam(self, text_key="games_close_steam_text"):
        """Rückfrage: Steam beenden, damit die Änderung nicht verloren geht."""
        import steam_close
        return steam_close.ask(self, text_key, widen=self._widen_dialog_buttons)

    def _close_steam_then(self, callback, keys=None):
        """Beendet Steam und ruft ``callback`` auf, sobald es weg ist (steam_close.py)."""
        import steam_close

        def remember(timer):
            self._steam_close_timer = timer

        return steam_close.close_then(
            self, callback, self._detail_status,
            timeout_ms=self.STEAM_SHUTDOWN_TIMEOUT_MS,
            poll_ms=self.STEAM_SHUTDOWN_POLL_MS,
            on_timer=remember, keys=keys)

    def _apply_proton(self, appid, proton, name):
        """Schreibt den Eintrag (Steam läuft nicht) und prüft das Ergebnis."""
        ok, err = games_db.set_steam_compat_tool(appid, name)
        if not ok:
            self._detail_status(f"Steam-Config: {err}", "#bf616a")
            return
        if games_db.get_steam_compat_tool(appid) != name:
            log.warning("[Games] CompatToolMapping fuer %s nach dem Schreiben "
                        "nicht gefunden (erwartet: %s)", appid, name)
            self._detail_status(tr("games_use_not_saved"), "#bf616a")
            return

        version = proton.get("version", "")
        self._selected_proton[appid] = version
        games_db.save_selected_proton(appid, version)
        g = self._game_data_for(appid)
        game_name_for_tooltip = g.get("name", "") if g else ""

        msg = tr("games_use_applied").format(tool=name)
        # Tooltip des ▶-Knopfs auf der Kachel nachziehen (neue Proton-Version)
        tile = self._games_tiles.get(appid)
        if tile is not None and getattr(tile, "_play_btn", None):
            tile._play_btn.setToolTip(
                self._tile_play_tooltip(appid, game_name_for_tooltip))

        # Panel neu bauen, damit das ✓-Aktiv-Badge umzieht — Status danach setzen
        self._refresh_detail()
        self._detail_status(msg, "#a3be8c")

    def _saved_launch_options(self, appid, game):
        """
        Baut die Startparameter eines Spiels aus den GESPEICHERTEN Angaben —
        ohne dass das Panel offen sein muss (für den ▶-Knopf auf der Kachel).
        Basis (GPU-abhängig) + gemerkte Toggles + eigene Parameter.
        """
        params = game.get("launch_params", {})
        gpu = games_db.detect_gpu_vendor()
        if params:
            base = params.get(gpu) or params.get("amd") or next(iter(params.values()), "")
        else:
            base = ""
        # resolved_toggles(): fuellt dynamische Befehle (VRCVideoCacher-Pfad).
        game_toggles = games_db.resolved_toggles(game)
        keys, custom = games_db.load_launch_toggles(appid, game_toggles)
        # Noch nie gespeichert -> Spiel-Vorgaben anwenden (gleiche Logik wie im Panel),
        # damit z. B. VRChat auch über den ▶-Knopf mit gamemoderun + HW-Dekodierung startet.
        if not games_db.has_saved_launch_toggles(appid):
            keys = list(game.get("default_on", [])) + \
                   [t["key"] for t in game_toggles if t.get("default")]
        return games_db.compose_launch_options(base, keys, custom, extra_toggles=game_toggles)

    def _launch_game(self, appid, game, params, status):
        """
        Gemeinsame Start-Routine für beide Play-Knöpfe (Kachel + Panel):
        schreibt die Startparameter in Steams LaunchOptions und startet das
        Spiel per Steam-CLI. Die per "Use" gewählte Proton-Version steht
        bereits in Steams CompatToolMapping.
          status: Callback(text, farbe) für die jeweilige Statuszeile.
        """
        ok, err = games_db.set_steam_launch_options(appid, (params or "").strip())
        warn = "" if ok else " " + tr("games_options_failed").format(err=err)

        cmd = games_db.steam_launch_cmd(appid)
        if not cmd:
            status(tr("games_play_failed") + warn, "#bf616a")
            return
        try:
            subprocess.Popen(cmd)
        except Exception:
            status(tr("games_play_failed") + warn, "#bf616a")
            return

        msg = tr("games_play_starting").format(name=game.get("name", ""))
        if ok and games_db.steam_is_running():
            # Bei Nicht-Steam-Spielen reicht ein Neustart nicht immer: Steam
            # schreibt shortcuts.vdf selbst neu, sobald man dort einen
            # Eintrag bearbeitet, und die Aenderung waere wieder weg.
            hint = ("games_shortcut_steam_running" if game.get("shortcut")
                    else "games_steam_restart_hint")
            msg += " " + tr(hint)
        status(msg + warn, "#a3be8c" if ok else "#ebcb8b")

    def _play_game(self, appid, game):
        """▶ im aufgeklappten Panel: nimmt die AKTUELLEN Werte aus dem Panel."""
        params = (self._update_final_params() or "").strip()
        self._launch_game(appid, game, params, self._detail_status)

    def _play_game_from_tile(self, appid):
        """
        ▶ direkt auf der Kachel: startet das Spiel, ohne es aufzuklappen.
        Benutzt die gespeicherten Toggles/Parameter und die per "Use"
        gewählte Proton-Version. Rückmeldung in der Statuszeile oben.
        """
        game = self._game_data_for(appid)
        if not game:
            return

        def status(text, color):
            self.ui.lbl_games_status.setText(text)
            self.ui.lbl_games_status.setStyleSheet(
                f"color: {color}; font-size: 12px; font-weight: bold;")

        if game.get("local"):
            self._launch_local_game(game["entry"], status)
            return

        # Ist das Spiel gerade offen, gelten die (evtl. ungespeicherten)
        # Panel-Werte — sonst die gespeicherten.
        if appid == self._expanded_appid and self._detail_params_edit is not None:
            params = (self._update_final_params() or "").strip()
        else:
            params = self._saved_launch_options(appid, game)

        self._launch_game(appid, game, params, status)

    # ------------------------------------------------------------------ #
    #  Eigene Spiele (ohne Steam)
    # ------------------------------------------------------------------ #
    def _launch_local_game(self, entry, status):
        """
        Startet ein eigenes Spiel als eigenständigen Prozess.

        Das Arbeitsverzeichnis wird bewusst auf den Ordner der Programmdatei
        gesetzt: Unity- und Godot-Builds suchen ihre Datenordner relativ zum
        Arbeitsverzeichnis und starten sonst mit schwarzem Bild oder gar
        nicht — ein Fehler, den der Nutzer niemals bei uns suchen würde.
        """
        cmd, err = games_db.local_launch_cmd(entry)
        if cmd is None:
            status(tr(f"games_local_err_{err}"), "#bf616a")
            return
        try:
            subprocess.Popen(cmd, cwd=os.path.dirname(entry["exe"]) or None)
        except Exception as exc:
            log.warning("[Games] Eigenes Spiel konnte nicht gestartet werden: %s", exc)
            status(tr("games_local_err_launch").format(err=exc), "#bf616a")
            return
        status(tr("games_local_started").format(name=entry["name"]), "#a3be8c")

    def _save_local_field(self, gid, field, value):
        """Ein Feld eines eigenen Spiels sofort merken (Tippen im Panel)."""
        games_db.update_local_game(gid, **{field: value})
        entry = games_db.local_game(gid)
        if entry is not None:
            self._games_local_entries[gid] = entry

    def _browse_local_exe(self, gid, line_edit):
        from PySide6.QtWidgets import QFileDialog
        start = os.path.dirname(line_edit.text().strip()) or os.path.expanduser("~")
        path, _f = QFileDialog.getOpenFileName(
            self, tr("games_add_file_dialog_title"), start,
            f"{tr('games_add_filter_games')} "
            "(*.exe *.sh *.AppImage *.appimage *.x86_64 *.x86 *.bin *.run);;"
            f"{tr('games_add_filter_all')} (*)")
        if path:
            line_edit.setText(path)
            self._save_local_field(gid, "exe", path)
            self._detail_status(tr("games_local_saved"), "#a3be8c")

    def remove_local_game(self, gid):
        """'Entfernen' im Panel eines eigenen Spiels — mit Rückfrage.

        Gelöscht wird nur der EINTRAG, nie die Datei auf der Platte. Das steht
        auch so im Rückfragetext: ein Löschdialog, bei dem man raten muss, was
        gleich verschwindet, ist keiner.
        """
        entry = games_db.local_game(gid)
        if entry is None:
            return
        box = QMessageBox(self)
        box.setWindowTitle(tr("games_local_remove_title"))
        box.setIcon(QMessageBox.Question)
        box.setText(tr("games_local_remove_text").format(name=entry["name"]))
        btn_go = box.addButton(tr("games_local_remove_btn"), QMessageBox.DestructiveRole)
        box.addButton(tr("cancel"), QMessageBox.RejectRole)
        self._widen_dialog_buttons(box)
        box.exec()
        if box.clickedButton() is not btn_go:
            return
        games_db.remove_local_game(gid)
        self._collapse_detail()
        self.refresh_games_cards()

    def remove_manual_steam_game(self, appid):
        """Nimmt einen von Hand ergänzten Steam-Eintrag zurück.

        Das Spiel kann danach trotzdem in der Liste bleiben — nämlich dann,
        wenn Steam es ohnehin als VR führt. Deshalb wird anschließend neu
        gescannt und nicht einfach die Kachel entfernt: die Anzeige soll den
        echten Zustand zeigen, nicht den erwarteten.
        """
        games_db.remove_manual_steam_appid(appid)
        self._collapse_detail()
        self.start_games_scan()

    def remove_game_from_list(self, appid):
        """'Entfernen' im Panel: nimmt ein Steam-Spiel dauerhaft aus der Liste.

        Mit Rückfrage, und die sagt deutlich, was NICHT passiert: das Spiel
        bleibt installiert, nur der Eintrag verschwindet. Ein Knopf mit der
        Aufschrift "Entfernen" neben einer Spielekachel kann sonst leicht als
        "deinstallieren" gelesen werden — und das wäre ein Schreckmoment, den
        niemand braucht.
        """
        game = self._game_data_for(appid)
        if not game:
            return
        box = QMessageBox(self)
        box.setWindowTitle(tr("games_remove_title"))
        box.setIcon(QMessageBox.Question)
        box.setText(tr("games_remove_text").format(name=game.get("name", appid)))
        btn_go = box.addButton(tr("games_remove_btn"), QMessageBox.DestructiveRole)
        box.addButton(tr("cancel"), QMessageBox.RejectRole)
        self._widen_dialog_buttons(box)
        box.exec()
        if box.clickedButton() is not btn_go:
            return

        games_db.hide_game(appid)
        self._collapse_detail()
        # Aus dem Cache neu aufbauen statt zu scannen: das Spiel ist ja noch
        # installiert, ein Scan würde es nur erneut finden und wieder
        # herausfiltern — dieselbe Liste, nur langsamer.
        tested, untested, _was = games_db.load_cached_games()
        tested = [a for a in tested if a != appid]
        untested = [g for g in untested if g["appid"] != appid]
        games_db.save_cached_games(tested, untested)
        self.render_games_cards(tested, untested)

    def reset_games_list(self):
        """Einstellungen -> Spiele -> 'Games-Tab zurücksetzen'.

        Holt alle entfernten Spiele zurück. Danach wird neu gescannt, damit
        die Liste wieder dem entspricht, was wirklich installiert ist — und
        nicht dem Stand, der beim Entfernen zufällig im Cache lag.
        """
        count = len(games_db.load_hidden_games())
        if not count:
            QMessageBox.information(self, tr("games_reset_title"),
                                    tr("games_reset_nothing"))
            return

        box = QMessageBox(self)
        box.setWindowTitle(tr("games_reset_title"))
        box.setIcon(QMessageBox.Question)
        box.setText(tr("games_reset_text").format(n=count))
        btn_go = box.addButton(tr("games_reset_btn"), QMessageBox.AcceptRole)
        box.addButton(tr("cancel"), QMessageBox.RejectRole)
        self._widen_dialog_buttons(box)
        box.exec()
        if box.clickedButton() is not btn_go:
            return

        restored = games_db.clear_hidden_games()
        self._collapse_detail()
        self.start_games_scan()
        QMessageBox.information(self, tr("games_reset_title"),
                                tr("games_reset_done").format(n=restored))

    # ------------------------------------------------------------------ #
    #  Bilder (eigene Spiele + Nicht-Steam-Spiele)
    # ------------------------------------------------------------------ #
    def _add_image_row(self, box, key, kind):
        """Zeile „Bild (optional): [Bild wählen …] [Bild entfernen]".

        kind "local"   : Kopie in der App-Config (games.set_local_game_image)
        kind "shortcut": Steams grid-Ordner — erscheint auch in Steam
        """
        row = QHBoxLayout()
        lbl = QLabel(tr("games_image_label"))
        lbl.setStyleSheet("color: #7b88a1; font-size: 11px; font-weight: bold; border: none;")
        if kind == "shortcut":
            lbl.setToolTip(tr("games_image_shortcut_tip"))
        row.addWidget(lbl)

        btn_choose = QPushButton(tr("games_image_choose_btn"))
        btn_choose.setCursor(Qt.PointingHandCursor)
        btn_choose.setStyleSheet(self._fix_button_style())
        btn_choose.clicked.connect(lambda _=False, k=key, t=kind: self._choose_game_image(k, t))
        row.addWidget(btn_choose)

        has_image = games_db.get_game_cover(key, allow_download=False) is not None
        btn_clear = QPushButton(tr("games_image_remove_btn"))
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.setStyleSheet(self._fix_button_style())
        btn_clear.setEnabled(has_image)
        btn_clear.clicked.connect(lambda _=False, k=key, t=kind: self._clear_game_image(k, t))
        row.addWidget(btn_clear)
        row.addStretch()
        box.addLayout(row)
        self._detail_image_buttons = (btn_choose, btn_clear)

    def _choose_game_image(self, key, kind, path=None):
        if path is None:
            from PySide6.QtWidgets import QFileDialog
            path, _f = QFileDialog.getOpenFileName(
                self, tr("games_image_dialog_title"), os.path.expanduser("~"),
                f"{tr('games_image_filter')} (*.png *.jpg *.jpeg)")
            if not path:
                return
        if kind == "local":
            ok, err = games_db.set_local_game_image(key, path)
        else:
            ok, err = games_db.set_shortcut_image(key, path)
        if not ok:
            self._detail_status(tr(f"games_image_err_{err}"), "#bf616a")
            return
        self._rerender_keep_open(key, tr("games_image_set"))

    def _clear_game_image(self, key, kind):
        if kind == "local":
            games_db.clear_local_game_image(key)
        else:
            games_db.clear_shortcut_image(key)
        self._rerender_keep_open(key, tr("games_image_removed"))

    def _rerender_keep_open(self, key, message):
        """Kacheln neu aufbauen (neues Cover) und das Panel wieder aufklappen."""
        self._collapse_detail()
        self.refresh_games_cards()
        if key in self._games_tiles:
            self._expand_game(key)
        self._detail_status(message, "#a3be8c")

    # ------------------------------------------------------------------ #
    #  Eigenes Windows-Spiel -> Nicht-Steam-Spiel
    # ------------------------------------------------------------------ #
    def move_local_game_to_steam(self, gid):
        """„In Steam eintragen" im Panel eines eigenen .exe-Spiels.

        Der eigene Eintrag wird danach entfernt: sonst stuende dasselbe Spiel
        zweimal in der Liste, einmal mit und einmal ohne Proton.
        """
        entry = games_db.local_game(gid)
        if entry is None:
            return
        if games_db.steam_is_running():
            if not self._ask_close_steam("games_close_steam_text_add"):
                self._detail_status(tr("games_add_to_steam_cancelled"), "#ebcb8b")
                return
            self._close_steam_then(
                lambda g=gid: self._do_move_local_to_steam(g),
                keys={"waiting": "games_add_to_steam_waiting",
                      "timeout": "games_add_to_steam_timeout",
                      "failed": "games_add_to_steam_failed_close"})
            return
        self._do_move_local_to_steam(gid)

    def _do_move_local_to_steam(self, gid):
        entry = games_db.local_game(gid)
        if entry is None:
            return
        appid, err = games_db.register_in_steam(
            entry["name"], entry["exe"], entry.get("launch_options", ""),
            entry.get("image", ""))
        if appid is None:
            self._detail_status(tr(f"games_add_err_{err}"), "#bf616a")
            return
        games_db.remove_local_game(gid)
        self._collapse_detail()
        self.start_games_scan()
        QMessageBox.information(self, tr("games_add_to_steam_btn"),
                                tr("games_local_moved_to_steam").format(name=entry["name"]))

    def _build_local_game_detail(self, gid, entry):
        """
        Detail-Panel eines eigenen Spiels.

        Bewusst viel schlanker als das Steam-Panel: ohne AppID gibt es kein
        CompatToolMapping, keine Proton-Auswahl und keine Steam-Startparameter.
        Alles, was hier nicht steht, könnte für diesen Eintrag auch gar nichts
        bewirken — es anzuzeigen wäre eine Zusage, die wir nicht halten.
        """
        card = QFrame()
        card.setObjectName("settingsCard")
        card.setStyleSheet("""
            QFrame#settingsCard {
                background-color: #21252b;
                border: 1px solid #88c0d0;
                border-radius: 6px;
            }
        """)
        box = QVBoxLayout(card)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(8)

        name_row = QHBoxLayout()
        lbl_name = QLabel(entry["name"])
        lbl_name.setStyleSheet(
            "font-weight: bold; color: #eceff4; font-size: 15px; border: none;")
        name_row.addWidget(lbl_name)

        lbl_badge = QLabel(tr("games_local_badge"))
        lbl_badge.setStyleSheet("color: #88c0d0; font-size: 11px; border: none;")
        name_row.addWidget(lbl_badge)

        btn_play = QPushButton(tr("games_play_btn"))
        btn_play.setObjectName("panelPlay")
        btn_play.setCursor(Qt.PointingHandCursor)
        btn_play.setIcon(make_play_icon(12, "#21252b"))
        btn_play.setIconSize(QSize(12, 12))
        btn_play.setStyleSheet("""
            QPushButton#panelPlay { background-color: #a3be8c; color: #21252b; border: none;
                          font-weight: bold; padding: 5px 16px; border-radius: 4px; font-size: 12px; }
            QPushButton#panelPlay:hover { background-color: #b8d19f; }
            QPushButton#panelPlay:pressed { background-color: #8fae76; }
        """)
        btn_play.clicked.connect(
            lambda _=False, g=gid: self._launch_local_game(
                self._games_local_entries.get(g) or games_db.local_game(g),
                self._detail_status))
        name_row.addWidget(btn_play)
        name_row.addStretch()
        box.addLayout(name_row)

        # --- Programmdatei ---
        lbl_exe = QLabel(tr("games_add_exe_label"))
        lbl_exe.setStyleSheet("color: #7b88a1; font-size: 11px; font-weight: bold; border: none;")
        box.addWidget(lbl_exe)

        exe_row = QHBoxLayout()
        txt_exe = QLineEdit(entry["exe"])
        txt_exe.setStyleSheet("font-family: monospace; font-size: 11px;")
        txt_exe.textEdited.connect(
            lambda text, g=gid: self._save_local_field(g, "exe", text))
        exe_row.addWidget(txt_exe)

        btn_browse = QPushButton(tr("games_add_browse_btn"))
        btn_browse.setCursor(Qt.PointingHandCursor)
        btn_browse.setStyleSheet(self._fix_button_style())
        btn_browse.clicked.connect(
            lambda _=False, g=gid, t=txt_exe: self._browse_local_exe(g, t))
        exe_row.addWidget(btn_browse)
        box.addLayout(exe_row)

        # Fehlt die Datei, sagen wir es JETZT — nicht erst, wenn der Start
        # scheitert. Nach einem Spiele-Umzug ist das der Normalfall.
        if not os.path.isfile(os.path.expanduser(entry["exe"])):
            lbl_warn = QLabel(tr("games_local_err_not_found"))
            lbl_warn.setStyleSheet("color: #ebcb8b; font-size: 11px; border: none;")
            lbl_warn.setWordWrap(True)
            box.addWidget(lbl_warn)

        # --- Startparameter ---
        lbl_opts = QLabel(tr("games_add_opts_label"))
        lbl_opts.setStyleSheet("color: #7b88a1; font-size: 11px; font-weight: bold; border: none;")
        box.addWidget(lbl_opts)

        txt_opts = QLineEdit(entry.get("launch_options", ""))
        txt_opts.setPlaceholderText(tr("games_add_opts_placeholder"))
        txt_opts.setStyleSheet("font-family: monospace; font-size: 11px;")
        txt_opts.textEdited.connect(
            lambda text, g=gid: self._save_local_field(g, "launch_options", text))
        box.addWidget(txt_opts)

        self._add_image_row(box, gid, "local")

        # Windows-Programm aus der Zeit vor v1.3.0: nicht still loeschen,
        # aber sagen, dass es ueber Steam besser geht — und den Weg anbieten.
        if games_db.is_windows_exe(entry["exe"]):
            hint_row = QHBoxLayout()
            lbl_hint = QLabel(tr("games_local_exe_hint"))
            lbl_hint.setWordWrap(True)
            lbl_hint.setStyleSheet("color: #ebcb8b; font-size: 11px; border: none;")
            hint_row.addWidget(lbl_hint, 1)
            btn_to_steam = QPushButton(tr("games_add_to_steam_btn"))
            btn_to_steam.setCursor(Qt.PointingHandCursor)
            btn_to_steam.setToolTip(tr("games_add_to_steam_tip"))
            btn_to_steam.setStyleSheet(self._fix_button_style())
            btn_to_steam.clicked.connect(
                lambda _=False, g=gid: self.move_local_game_to_steam(g))
            hint_row.addWidget(btn_to_steam)
            box.addLayout(hint_row)

        # --- Entfernen ---
        foot = QHBoxLayout()
        btn_remove = QPushButton(tr("games_local_remove_btn"))
        btn_remove.setCursor(Qt.PointingHandCursor)
        btn_remove.setToolTip(tr("games_local_remove_tip"))
        btn_remove.setStyleSheet("""
            QPushButton { background-color: #bf616a; color: white; border: none;
                          font-weight: bold; padding: 6px 12px; border-radius: 4px; font-size: 11px; }
            QPushButton:hover { background-color: #d08770; }
        """)
        btn_remove.clicked.connect(lambda _=False, g=gid: self.remove_local_game(g))
        foot.addWidget(btn_remove)
        foot.addStretch()
        box.addLayout(foot)

        self._detail_status_lbl = QLabel("")
        self._detail_status_lbl.setStyleSheet("color: #88c0d0; font-size: 11px; border: none;")
        self._detail_status_lbl.setWordWrap(True)
        box.addWidget(self._detail_status_lbl)

        return card

    def _build_game_detail(self, appid, game):
        """
        Ausgeklappte Detail-Sektion einer Kachel:
          * Proton-Versionen (auf CachyOS ohne das normale Valve-Proton)
            mit Beschreibung, Kopieren- und ProtonPlus-Install-Knopf
          * Startparameter passend zur erkannten GPU mit Kopieren-Knopf
          * Spiel-spezifische Fixes (z. B. VRChat Picture Folder Fix)
        """
        lang = get_language()
        # game mitgeben: Spiele ohne eigenen CachyOS-Eintrag (VRChat seit
        # 1.1.9) sollen dort trotzdem ein "Empfohlen" an der Liste haben.
        rec_role = games_db.recommended_role(game)
        gpu = games_db.detect_gpu_vendor()
        pp_available = games_db.find_protonplus() is not None

        card = QFrame()
        card.setObjectName("settingsCard")
        card.setStyleSheet("""
            QFrame#settingsCard {
                background-color: #21252b;
                border: 1px solid #88c0d0;
                border-radius: 6px;
            }
        """)
        box = QVBoxLayout(card)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(8)

        # Kopfzeile: Spielname + "Play"-Button direkt daneben.
        # Play startet das Spiel per Steam-CLI mit der per "Use" gewählten
        # Proton-Version und den Startparametern aus dem Textfeld unten.
        name_row = QHBoxLayout()
        lbl_name = QLabel(game["name"])
        lbl_name.setStyleSheet("font-weight: bold; color: #eceff4; font-size: 15px; border: none;")
        name_row.addWidget(lbl_name)

        btn_play = QPushButton(tr("games_play_btn"))
        btn_play.setObjectName("panelPlay")
        btn_play.setCursor(Qt.PointingHandCursor)
        btn_play.setIcon(make_play_icon(12, "#21252b"))
        btn_play.setIconSize(QSize(12, 12))
        btn_play.setStyleSheet("""
            QPushButton#panelPlay { background-color: #a3be8c; color: #21252b; border: none;
                          font-weight: bold; padding: 5px 16px; border-radius: 4px; font-size: 12px; }
            QPushButton#panelPlay:hover { background-color: #b8d19f; }
            QPushButton#panelPlay:pressed { background-color: #8fae76; }
        """)
        btn_play.clicked.connect(lambda _, a=appid, g=game: self._play_game(a, g))
        name_row.addWidget(btn_play)

        # Von Hand ergaenzt? Dann sichtbar machen UND zuruecknehmbar. Ohne
        # diesen Knopf haette ein Fehlgriff im Dialog (falsches Spiel
        # ausgewaehlt) keine Umkehrung ausser dem Bearbeiten der Config.
        if str(appid) in games_db.load_manual_steam_appids():
            lbl_manual = QLabel(tr("games_manual_badge"))
            lbl_manual.setStyleSheet(
                "color: #88c0d0; font-size: 11px; border: none;")
            lbl_manual.setToolTip(tr("games_manual_badge_tip"))
            name_row.addWidget(lbl_manual)

            btn_unmanual = QPushButton(tr("games_manual_remove_btn"))
            btn_unmanual.setCursor(Qt.PointingHandCursor)
            btn_unmanual.setToolTip(tr("games_manual_remove_tip"))
            btn_unmanual.setStyleSheet("""
                QPushButton { background-color: #2e3440; color: #d8dee9; border: 1px solid #4c566a;
                              padding: 3px 10px; border-radius: 4px; font-size: 11px; }
                QPushButton:hover { background-color: #3b4252; border-color: #bf616a; }
            """)
            btn_unmanual.clicked.connect(
                lambda _=False, a=appid: self.remove_manual_steam_game(a))
            name_row.addWidget(btn_unmanual)

        name_row.addStretch()
        box.addLayout(name_row)

        if game.get("shortcut"):
            self._add_image_row(box, appid, "shortcut")

        # --- Proton-Versionen (gefiltert + Empfehlung zuerst) ---
        lbl_proton = QLabel(tr("games_proton_section"))
        lbl_proton.setStyleSheet("color: #7b88a1; font-size: 11px; font-weight: bold; border: none;")
        box.addWidget(lbl_proton)

        role_labels = {
            "main": tr("games_role_main"),
            "main_cachyos": tr("games_role_cachyos"),
            "alternative": tr("games_role_alt"),
            "alternative_ge": tr("games_role_alt_ge"),
            "safe": tr("games_role_safe"),
        }

        for proton in games_db.visible_protons(game):
            row_frame = QFrame()
            row_frame.setObjectName("protonrow")
            is_rec = proton.get("role") == rec_role
            row_frame.setStyleSheet(
                "QFrame#protonrow { background-color: #2e3440; border-radius: 4px; border: none; }"
                if is_rec else
                "QFrame#protonrow { background-color: transparent;"
                " border: 1px solid #2e3440; border-radius: 4px; }")
            row = QVBoxLayout(row_frame)
            row.setContentsMargins(10, 8, 10, 8)
            row.setSpacing(4)

            head = QHBoxLayout()
            # Die INSTALLIERTE Version anzeigen, nicht die in der games.json
            # eingetragene. Die Datenbank nennt zwangslaeufig einen Stand von
            # gestern — proton-rtsp und GE erscheinen im Wochentakt. Stuende
            # hier der gepinnte Name, waehrend ein neuerer Build daneben
            # liegt und auch benutzt wird, zeigte die App etwas anderes an
            # als sie tut.
            installed_tool, _found, _kind = games_db.resolve_steam_tool(proton)
            ver_text = installed_tool or proton.get("version", "")
            if proton.get("untested"):
                ver_text = f"{ver_text} {tr('games_untested_suffix')}"
            lbl_ver = QLabel(ver_text)
            lbl_ver.setStyleSheet(
                "color: #a3be8c; font-family: monospace; font-size: 12px; font-weight: bold; border: none;")
            lbl_ver.setTextInteractionFlags(Qt.TextSelectableByMouse)
            head.addWidget(lbl_ver)

            badge_text = (tr("games_recommended_cachyos")
                          if is_rec and rec_role == "main_cachyos"
                          else tr("games_recommended")) if is_rec \
                else role_labels.get(proton.get("role"), "")
            lbl_badge = QLabel(badge_text)
            lbl_badge.setStyleSheet(
                "color: #ebcb8b; font-size: 11px; font-weight: bold; border: none;" if is_rec
                else "color: #7b88a1; font-size: 11px; border: none;")
            head.addWidget(lbl_badge)

            # Per "Use" als aktiv gewählte Version markieren
            is_active = self._selected_proton.get(appid) in (
                proton.get("version"), installed_tool)
            if is_active:
                lbl_active = QLabel(tr("games_active_badge"))
                lbl_active.setStyleSheet(
                    "color: #a3be8c; font-size: 11px; font-weight: bold; border: none;")
                head.addWidget(lbl_active)
            head.addStretch()

            # "Use": setzt diese Version als aktive Version für den Play-Button
            # (schreibt sie in Steams CompatToolMapping und merkt sie dauerhaft)
            btn_use = QPushButton(tr("games_use_btn"))
            btn_use.setCursor(Qt.PointingHandCursor)
            btn_use.setEnabled(not is_active)
            btn_use.setStyleSheet("""
                QPushButton { background-color: #5e81ac; color: white; border: none;
                              font-weight: bold; padding: 3px 12px; border-radius: 4px; font-size: 11px; }
                QPushButton:hover { background-color: #81a1c1; }
                QPushButton:disabled { background-color: #3b4252; color: #a3be8c; }
            """)
            btn_use.clicked.connect(
                lambda _, a=appid, p=proton: self._use_proton(a, p))
            head.addWidget(btn_use)

            btn_copy_ver = QPushButton(tr("games_copy_btn"))
            btn_copy_ver.setCursor(Qt.PointingHandCursor)
            btn_copy_ver.setStyleSheet("""
                QPushButton { background-color: #2e3440; color: #d8dee9; border: 1px solid #4c566a;
                              padding: 3px 10px; border-radius: 4px; font-size: 11px; }
                QPushButton:hover { background-color: #3b4252; border-color: #5e81ac; }
            """)
            btn_copy_ver.clicked.connect(
                lambda _, v=proton.get("version", ""), b=btn_copy_ver:
                self._copy_games_text(v, b))
            head.addWidget(btn_copy_ver)

            runner_id = proton.get("protonplus_runner")
            # Manuell verteilte Builds (weder AUR noch ProtonPlus): eigener
            # Knopf, der Tarball laedt, Pruefsumme prueft und entpackt.
            if proton.get("download_url"):
                btn_dl = QPushButton(
                    tr("games_manual_reinstall_btn") if _found
                    else tr("games_manual_install_btn"))
                btn_dl.setCursor(Qt.PointingHandCursor)
                btn_dl.setStyleSheet("""
                    QPushButton { background-color: #5e81ac; color: white; border: none;
                                  font-weight: bold; padding: 3px 10px; border-radius: 4px; font-size: 11px; }
                    QPushButton:hover { background-color: #81a1c1; }
                    QPushButton:disabled { background-color: #3b4252; color: #7b88a1; }
                """)
                btn_dl.clicked.connect(
                    lambda _, p=proton, b=btn_dl: self.start_manual_proton_install(p, b))
                head.addWidget(btn_dl)
            elif runner_id and pp_available:
                btn_pp = QPushButton(tr("games_pp_install_btn"))
                btn_pp.setCursor(Qt.PointingHandCursor)
                btn_pp.setStyleSheet("""
                    QPushButton { background-color: #5e81ac; color: white; border: none;
                                  font-weight: bold; padding: 3px 10px; border-radius: 4px; font-size: 11px; }
                    QPushButton:hover { background-color: #81a1c1; }
                    QPushButton:disabled { background-color: #3b4252; color: #7b88a1; }
                """)
                btn_pp.clicked.connect(
                    lambda _, r=runner_id: self.start_protonplus_install(r))
                head.addWidget(btn_pp)
            row.addLayout(head)

            desc = proton.get("desc", {})
            lbl_desc = QLabel(desc.get(lang) or desc.get("en") or desc.get("de") or "")
            lbl_desc.setStyleSheet("color: #d8dee9; font-size: 11px; border: none;")
            lbl_desc.setWordWrap(True)
            row.addWidget(lbl_desc)

            if proton.get("download_url"):
                lbl_src = QLabel(tr("games_manual_note"))
                lbl_src.setStyleSheet("color: #7b88a1; font-size: 10px; font-style: italic; border: none;")
                lbl_src.setWordWrap(True)
                row.addWidget(lbl_src)
            elif runner_id is None:
                lbl_src = QLabel(tr("games_pp_steam_note"))
                lbl_src.setStyleSheet("color: #7b88a1; font-size: 10px; font-style: italic; border: none;")
                row.addWidget(lbl_src)
            elif not pp_available:
                lbl_src = QLabel(tr("games_pp_missing"))
                lbl_src.setStyleSheet("color: #ebcb8b; font-size: 10px; font-style: italic; border: none;")
                lbl_src.setWordWrap(True)
                row.addWidget(lbl_src)

            box.addWidget(row_frame)

        # --- Startparameter: Basis (GPU-abhängig) + Zusatz-Optionen ---
        # Aufbau: hinterlegte Basis-Parameter  ->  Toggle-Schalter
        #         ->  eigene Parameter  ->  finaler, kopierbarer String.
        # Der finale String wird live neu berechnet und ist genau das, was
        # "Play" in Steams LaunchOptions schreibt.
        params = game.get("launch_params", {})
        if game.get("shortcut"):
            # Nicht-Steam-Spiel: Basis sind die Parameter aus Steam, nicht
            # GPU-abhaengige Vorgaben.
            lbl_params = QLabel(tr("games_params_section_shortcut"))
            self._detail_base_params = params.get("base", "")
            if self._detail_base_params:
                lbl_params.setToolTip(tr("games_shortcut_base_tip").format(
                    params=self._detail_base_params))
        elif params and gpu in ("amd", "nvidia"):
            gpu_name = tr("games_gpu_amd") if gpu == "amd" else tr("games_gpu_nvidia")
            lbl_params = QLabel(tr("games_params_section").format(gpu=gpu_name))
            self._detail_base_params = params.get(gpu, "")
        else:
            lbl_params = QLabel(tr("games_params_section_unknown"))
            self._detail_base_params = (params.get("amd", "")
                                        or next(iter(params.values()), "")) if params else ""
        lbl_params.setStyleSheet("color: #7b88a1; font-size: 11px; font-weight: bold; border: none;")
        box.addWidget(lbl_params)

        # Panel wird neu aufgebaut -> Pfadsuche einmal frisch machen.
        # Dadurch reicht Panel zu / Panel auf, nachdem man
        # VRCVideoCacher installiert hat.
        games_db.refresh_vrcvideocacher_path()
        game_toggles = games_db.resolved_toggles(game)
        self._detail_game_toggles = game_toggles
        saved_keys, saved_custom = games_db.load_launch_toggles(appid, game_toggles)

        # Beim ERSTEN Öffnen (noch nichts gespeichert) greifen die Spiel-
        # Vorgaben (z. B. gamemoderun + HW-Video-Dekodierung sind bei VRChat
        # per Default an). Danach ist die gespeicherte Auswahl maßgeblich —
        # der Nutzer kann die Vorgaben also ganz normal wieder abschalten.
        if games_db.has_saved_launch_toggles(appid):
            initial_keys = set(saved_keys)
        else:
            initial_keys = set(game.get("default_on", []))
            initial_keys |= {t["key"] for t in game_toggles if t.get("default")}

        # Toggle-Schalter: globale (LAUNCH_TOGGLES) + spiel-eigene (game['toggles'])
        lbl_toggles = QLabel(tr("games_toggles_section"))
        lbl_toggles.setStyleSheet("color: #7b88a1; font-size: 11px; font-weight: bold; border: none;")
        box.addWidget(lbl_toggles)

        # Zwei Zeilen statt einer: bei schmalem Fenster schob die einzelne
        # QHBoxLayout-Reihe die hinteren Schalter aus dem sichtbaren Bereich —
        # "VRCVideoCacher Autostart" als letzter war praktisch nicht mehr
        # erreichbar. Ab dem vierten Schalter wird jetzt umgebrochen.
        TOGGLES_PER_ROW = 4
        toggle_rows = [QHBoxLayout()]
        toggle_rows[0].setSpacing(16)
        self._detail_toggles = {}
        for t in list(games_db.LAUNCH_TOGGLES) + list(game_toggles):
            cb = QCheckBox(tr(f"games_toggle_{t['key']}"))
            cb.setCursor(Qt.PointingHandCursor)
            cb.setChecked(t["key"] in initial_keys)
            cb.setToolTip(tr(f"games_toggle_{t['key']}_tip"))
            cb.setStyleSheet(
                "QCheckBox { color: #d8dee9; font-size: 11px; font-family: monospace; border: none; }")
            # Ein Schalter ohne Befehl kann nichts tun (z. B. VRCVideoCacher-
            # Autostart, wenn das Programm gar nicht installiert ist). Ihn
            # anklickbar zu lassen waere die schlechtere Variante: der Nutzer
            # setzt den Haken, in den Startparametern passiert nichts, und er
            # sucht den Fehler beim Spiel. Also ausgrauen und sagen warum.
            if not t.get("arg"):
                cb.setChecked(False)
                cb.setEnabled(False)
                cb.setToolTip(tr(f"games_toggle_{t['key']}_missing"))
                cb.setStyleSheet(
                    "QCheckBox { color: #7b88a1; font-size: 11px; "
                    "font-family: monospace; border: none; }")
            cb.toggled.connect(lambda _, a=appid: self._on_launch_opts_changed(a))
            self._detail_toggles[t["key"]] = cb
            if toggle_rows[-1].count() >= TOGGLES_PER_ROW:
                row = QHBoxLayout()
                row.setSpacing(16)
                toggle_rows.append(row)
            toggle_rows[-1].addWidget(cb)
        for row in toggle_rows:
            row.addStretch()
            box.addLayout(row)

        # Eigene Parameter (auch der Platz für ungetestete Spiele ohne Profil)
        lbl_custom = QLabel(tr("games_custom_params"))
        lbl_custom.setStyleSheet("color: #7b88a1; font-size: 11px; font-weight: bold; border: none;")
        box.addWidget(lbl_custom)

        self._detail_custom_edit = QLineEdit(saved_custom)
        self._detail_custom_edit.setPlaceholderText(tr("games_custom_placeholder"))
        self._detail_custom_edit.setStyleSheet("font-family: monospace; font-size: 11px;")
        self._detail_custom_edit.textEdited.connect(
            lambda _, a=appid: self._on_launch_opts_changed(a))
        box.addWidget(self._detail_custom_edit)

        # Finaler String (schreibgeschützt, wird live gebaut) + Kopieren
        lbl_final = QLabel(tr("games_final_params"))
        lbl_final.setStyleSheet("color: #7b88a1; font-size: 11px; font-weight: bold; border: none;")
        box.addWidget(lbl_final)

        param_row = QHBoxLayout()
        txt_params = QLineEdit()
        txt_params.setReadOnly(True)
        txt_params.setStyleSheet("font-family: monospace; font-size: 11px; color: #a3be8c;")
        self._detail_params_edit = txt_params   # Play liest hieraus
        param_row.addWidget(txt_params)

        btn_copy = QPushButton(tr("games_copy_btn"))
        btn_copy.setCursor(Qt.PointingHandCursor)
        btn_copy.setStyleSheet("""
            QPushButton { background-color: #5e81ac; color: white; border: none;
                          font-weight: bold; padding: 6px 12px; border-radius: 4px; font-size: 11px; }
            QPushButton:hover { background-color: #81a1c1; }
        """)
        btn_copy.clicked.connect(
            lambda _, t=txt_params, b=btn_copy: self._copy_games_text(t.text(), b))
        param_row.addWidget(btn_copy)
        box.addLayout(param_row)

        self._update_final_params()   # Startwert berechnen

        # --- Config-Backup: gilt fuer JEDES Spiel, nicht nur VRChat -------- #
        # Steht bewusst vor den spielspezifischen Fixes: nach einem
        # Proton-Wechsel ist "Config zurueckspielen" der naechste Schritt,
        # den man sucht.
        import game_backup
        lbl_bk_head = QLabel(tr("backup_cfg_section"))
        lbl_bk_head.setStyleSheet(
            "color: #7b88a1; font-size: 11px; font-weight: bold; border: none;")
        box.addWidget(lbl_bk_head)

        bk_row = QHBoxLayout()
        bk_row.setSpacing(8)

        btn_bk = QPushButton(tr("backup_cfg_btn"))
        btn_bk.setCursor(Qt.PointingHandCursor)
        btn_bk.setToolTip(tr("backup_cfg_btn_tip"))
        btn_bk.setStyleSheet(self._fix_button_style())
        btn_bk.clicked.connect(lambda _=False, a=appid: self._manual_config_backup(a))
        bk_row.addWidget(btn_bk)

        btn_rs = QPushButton(tr("restore_cfg_btn"))
        btn_rs.setCursor(Qt.PointingHandCursor)
        btn_rs.setStyleSheet(self._fix_button_style())
        btn_rs.clicked.connect(lambda _=False, a=appid: self.restore_game_config(a))
        # Ohne Backup gibt es nichts zurueckzuspielen -> ausgrauen statt
        # den Nutzer auf eine Fehlermeldung laufen zu lassen.
        if game_backup.has_backup(appid):
            info = game_backup.backup_info(appid)
            btn_rs.setToolTip(tr("restore_cfg_btn_tip").format(
                created=info.get("created", "?"), files=info.get("files", "?")))
        else:
            btn_rs.setEnabled(False)
            btn_rs.setToolTip(tr("restore_cfg_btn_none"))
        bk_row.addWidget(btn_rs)

        # --- Aus der Liste entfernen -------------------------------------- #
        # Steht bewusst NEBEN den Backup-Knoepfen und nicht bei den Fixes:
        # es ist die einzige Aktion im Panel, die die Liste selbst aendert.
        btn_del = QPushButton(tr("games_remove_btn"))
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.setToolTip(tr("games_remove_tip"))
        btn_del.setStyleSheet("""
            QPushButton { background-color: #2e3440; color: #d8dee9; border: 1px solid #4c566a;
                          padding: 6px 12px; border-radius: 4px; font-size: 11px; }
            QPushButton:hover { background-color: #3b4252; border-color: #bf616a; color: #eceff4; }
        """)
        btn_del.clicked.connect(lambda _=False, a=appid: self.remove_game_from_list(a))
        bk_row.addWidget(btn_del)

        bk_row.addStretch()
        box.addLayout(bk_row)

        # --- Spiel-spezifische Fixes (Umzug aus Settings -> "General") ---
        fixes = game.get("fixes", [])
        if fixes:
            lbl_fix_head = QLabel(tr("games_fixes_section"))
            lbl_fix_head.setStyleSheet("color: #7b88a1; font-size: 11px; font-weight: bold; border: none;")
            box.addWidget(lbl_fix_head)

            fix_row = QHBoxLayout()
            fix_row.setSpacing(8)

            # --- Picture Fix (frueher "Symlink erstellen") ---------------- #
            # Umbenannt, weil "Symlink erstellen" beschreibt, WIE es gemacht
            # wird, nicht WAS es bringt. Was es bringt, steht jetzt im Tooltip.
            if "vrchat_pictures" in fixes:
                btn_pic = QPushButton(tr("games_fix_pictures_btn"))
                btn_pic.setCursor(Qt.PointingHandCursor)
                btn_pic.setToolTip(tr("games_fix_pictures_tip"))
                btn_pic.setStyleSheet(self._fix_button_style())
                # Die bestehende Symlink-Logik (create_vrchat_symlink) schreibt
                # in self.ui.btn_vrchat_symlink / self.ui.lbl_vrchat_status —
                # wir haengen die dynamischen Widgets dort ein, dann laeuft
                # alles unveraendert weiter.
                self.ui.btn_vrchat_symlink = btn_pic
                btn_pic.clicked.connect(self.create_vrchat_symlink)
                fix_row.addWidget(btn_pic)

            # --- Videoplayer Fix (Info-Popup zu VRCVideoCacher) ----------- #
            if "vrchat_videoplayer" in fixes:
                btn_vp = QPushButton(tr("games_fix_video_btn"))
                btn_vp.setCursor(Qt.PointingHandCursor)
                btn_vp.setToolTip(tr("games_fix_video_tip"))
                btn_vp.setStyleSheet(self._fix_button_style())
                btn_vp.clicked.connect(self.show_vrchat_videoplayer_fix)
                fix_row.addWidget(btn_vp)

            # --- Videoplayer Check (Diagnose) ----------------------------- #
            if "vrchat_check" in fixes:
                btn_chk = QPushButton(tr("games_fix_check_btn"))
                btn_chk.setCursor(Qt.PointingHandCursor)
                btn_chk.setToolTip(tr("games_fix_check_tip"))
                btn_chk.setStyleSheet(self._fix_button_style())
                self.ui.btn_vrchat_check = btn_chk
                btn_chk.clicked.connect(self.run_vrchat_check)
                fix_row.addWidget(btn_chk)

            fix_row.addStretch()
            box.addLayout(fix_row)

            # Hinweis statt Autostart-Schalter. Der Wrapper ueber VRChats
            # Startparameter war unzuverlaessig und ist entfernt; stattdessen
            # startet man VRCVideoCacher im Dashboard, VOR VRChat.
            if "vrchat_videoplayer" in fixes:
                lbl_vci = QLabel(tr("games_vci_note"))
                lbl_vci.setStyleSheet("color: #7b88a1; font-size: 10px; border: none;")
                lbl_vci.setWordWrap(True)
                box.addWidget(lbl_vci)

            # Gemeinsame Statuszeile: Symlink-Rueckmeldung UND Check-Ergebnis
            lbl_fix_status = QLabel("")
            lbl_fix_status.setStyleSheet("font-size: 11px; border: none;")
            lbl_fix_status.setWordWrap(True)
            lbl_fix_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.ui.lbl_vrchat_status = lbl_fix_status
            box.addWidget(lbl_fix_status)

        # Statuszeile für Use-/Play-Feedback (Steam-Neustart-Hinweis usw.)
        self._detail_status_lbl = QLabel("")
        self._detail_status_lbl.setStyleSheet("color: #88c0d0; font-size: 11px; border: none;")
        self._detail_status_lbl.setWordWrap(True)
        box.addWidget(self._detail_status_lbl)

        return card

    # ----------------------------------------------------------------- #
    #  VRChat-Fixes
    # ----------------------------------------------------------------- #
    @staticmethod
    def _widen_dialog_buttons(box):
        """Verhindert abgeschnittene Beschriftungen in QMessageBox.

        Qt verteilt die Knoepfe auf die Dialogbreite, die sich am Text
        orientiert — bei drei Knoepfen mit laengeren Beschriftungen reicht
        das nicht und die Texte werden beschnitten ("Sichern und fortfa...").
        Jeder Knopf bekommt deshalb mindestens die Breite, die sein eigener
        Text braucht, plus Innenabstand.
        """
        from PySide6.QtWidgets import QPushButton
        for btn in box.findChildren(QPushButton):
            needed = btn.fontMetrics().horizontalAdvance(btn.text()) + 32
            btn.setMinimumWidth(max(needed, 96))

    @staticmethod
    def _fix_button_style():
        """Einheitlicher Stil der Fix-Knoepfe (dreimal derselbe String war
        vorher dreimal dieselbe Stelle zum Vergessen beim Aendern)."""
        return """
            QPushButton { background-color: #5e81ac; color: white; font-weight: bold;
                          padding: 6px 12px; border-radius: 4px; border: none; font-size: 11px; }
            QPushButton:hover { background-color: #81a1c1; }
            QPushButton:disabled { background-color: #3b4252; color: #7b88a1; }
        """

    def show_vrchat_videoplayer_fix(self):
        """Erklaert VRCVideoCacher und verlinkt darauf.

        Bewusst nur Information + Link, kein Ein-Klick-Installer: das Tool
        greift in VRChats Tools-Ordner ein und kann optional Browser-Cookies
        einlesen. Solche Entscheidungen trifft der Nutzer selbst, nachdem er
        gelesen hat, worum es geht — nicht wir im Hintergrund fuer ihn.
        """
        box = QMessageBox(self)
        box.setWindowTitle(tr("games_video_fix_title"))
        box.setTextFormat(Qt.RichText)
        box.setText(tr("games_video_fix_text"))
        box.setIcon(QMessageBox.Information)

        import vrcvideocacher_install as vci
        btn_install = None
        if not vci.is_installed():
            # Der bequemste Weg zuerst: die App kann es selbst einrichten.
            btn_install = box.addButton(tr("vci_install_btn"), QMessageBox.YesRole)
        btn_open = box.addButton(tr("games_video_fix_open"), QMessageBox.AcceptRole)
        btn_steam = box.addButton(tr("games_video_fix_steam"), QMessageBox.ActionRole)
        box.addButton(tr("close"), QMessageBox.RejectRole)
        self._widen_dialog_buttons(box)
        box.exec()

        clicked = box.clickedButton()
        if btn_install is not None and clicked is btn_install:
            self.install_vrcvideocacher()
        elif clicked is btn_open:
            QDesktopServices.openUrl(QUrl("https://github.com/EllyVR/VRCVideoCacher"))
        elif clicked is btn_steam:
            QDesktopServices.openUrl(
                QUrl("https://store.steampowered.com/app/4296960/VRCVideoCacher/"))

    def install_vrcvideocacher(self):
        """Laedt VRCVideoCacher und richtet die Verknuepfung ein."""
        if getattr(self, "_vci_worker", None) and self._vci_worker.isRunning():
            return
        self._detail_status(tr("vci_downloading"), "#88c0d0")
        self._vci_worker = VRCVideoCacherInstallWorker()
        self._vci_worker.progress_signal.connect(self._on_vci_progress)
        self._vci_worker.done_signal.connect(self._on_vci_done)
        self._vci_worker.start()

    def _on_vci_progress(self, done, total):
        if total:
            pct = int(done * 100 / total)
            self._detail_status(tr("vci_progress").format(
                pct=pct, mb=f"{done / 1048576:.0f}", total=f"{total / 1048576:.0f}"),
                "#88c0d0")
        else:
            self._detail_status(tr("vci_progress_nosize").format(
                mb=f"{done / 1048576:.0f}"), "#88c0d0")

    def _on_vci_done(self, ok, msg, desktop_ok):
        if not ok:
            key = "vci_failed_notbinary" if msg == "not_a_binary" else "vci_failed"
            self._detail_status(tr(key).format(err=msg), "#bf616a")
            return

        # Pfadsuche verwerfen, sonst bliebe der Autostart-Schalter ausgegraut,
        # obwohl das Programm jetzt da ist.
        games_db.refresh_vrcvideocacher_path()
        note = tr("vci_done")
        if desktop_ok:
            note += " " + tr("vci_done_desktop")
        self._detail_status(note, "#a3be8c")

        # Panel neu aufbauen -> der Autostart-Schalter wird benutzbar.
        appid = getattr(self, "_expanded_appid", None)
        if appid:
            self._on_game_tile_clicked(appid)
            self._on_game_tile_clicked(appid)

    def run_vrchat_check(self):
        """Startet die Diagnose im Hintergrund."""
        if getattr(self, "_vrc_check_worker", None) and self._vrc_check_worker.isRunning():
            return
        if hasattr(self.ui, "btn_vrchat_check"):
            self.ui.btn_vrchat_check.setEnabled(False)
        self.ui.lbl_vrchat_status.setText(tr("games_check_running"))
        self.ui.lbl_vrchat_status.setStyleSheet("color: #88c0d0; font-size: 11px; border: none;")

        self._vrc_check_worker = VRChatCheckWorker()
        self._vrc_check_worker.result_signal.connect(self._on_vrchat_check_done)
        self._vrc_check_worker.start()

    def _on_vrchat_check_done(self, results):
        """Ergebnis als Dialog anzeigen und in der Statuszeile zusammenfassen."""
        if hasattr(self.ui, "btn_vrchat_check"):
            self.ui.btn_vrchat_check.setEnabled(True)

        if not results:
            self.ui.lbl_vrchat_status.setText(tr("games_check_failed"))
            self.ui.lbl_vrchat_status.setStyleSheet("color: #bf616a; font-size: 11px; border: none;")
            return

        import vrchat_check as vc

        symbols = {vc.OK: "✔", vc.WARN: "⚠", vc.ERR: "✘", vc.INFO: "•"}
        colors = {vc.OK: "#a3be8c", vc.WARN: "#ebcb8b", vc.ERR: "#bf616a", vc.INFO: "#7b88a1"}

        lines = []
        for r in results:
            sym = symbols.get(r["status"], "•")
            col = colors.get(r["status"], "#d8dee9")
            title = tr(r["key"])
            detail = r.get("detail", "")
            row = (f'<div style="margin-bottom:6px;">'
                   f'<span style="color:{col};"><b>{sym} {title}</b></span>')
            if detail:
                row += f'<br><span style="color:#d8dee9;font-family:monospace;">{detail}</span>'
            if r.get("hint"):
                row += f'<br><span style="color:#7b88a1;">{tr(r["hint"])}</span>'
            row += "</div>"
            lines.append(row)

        status, count = vc.summarize(results)
        if status == vc.OK:
            head = tr("games_check_head_ok")
        elif status == vc.WARN:
            head = tr("games_check_head_warn").format(n=count)
        else:
            head = tr("games_check_head_err").format(n=count)

        box = QMessageBox(self)
        box.setWindowTitle(tr("games_check_title"))
        box.setTextFormat(Qt.RichText)
        box.setText(f"<b>{head}</b><br><br>" + "".join(lines))
        box.setIcon(QMessageBox.Information if status == vc.OK else QMessageBox.Warning)
        box.exec()

        self.ui.lbl_vrchat_status.setText(head)
        self.ui.lbl_vrchat_status.setStyleSheet(
            f"color: {colors.get(status, '#d8dee9')}; font-size: 11px; border: none;")

    # ----------------------------------------------------------------- #
    #  Config-Backup / -Restore (alle Spiele)
    # ----------------------------------------------------------------- #
    def _offer_config_backup(self, appid, proton):
        """Fragt vor einem Proton-Wechsel, ob gesichert werden soll.

        Rueckgabe False = Nutzer hat abgebrochen, der Wechsel unterbleibt.
        Gibt es nichts zu sichern (Prefix noch gar nicht vorhanden), wird
        kommentarlos durchgewinkt — dann kann auch nichts verloren gehen.
        """
        import game_backup

        files, size = game_backup.estimate_size(appid)
        if not files:
            return True

        g = self._game_data_for(appid) or {}
        mb = size / 1048576
        box = QMessageBox(self)
        box.setWindowTitle(tr("backup_cfg_title"))
        box.setIcon(QMessageBox.Question)
        text = tr("backup_cfg_text").format(
            game=g.get("name", appid), files=files, size=f"{mb:.0f}")
        if size > game_backup.LARGE_BACKUP_BYTES:
            text += "\n\n" + tr("backup_cfg_large")
        box.setText(text)
        btn_yes = box.addButton(tr("backup_cfg_yes"), QMessageBox.AcceptRole)
        btn_no = box.addButton(tr("backup_cfg_no"), QMessageBox.DestructiveRole)
        box.addButton(tr("cancel"), QMessageBox.RejectRole)
        box.setDefaultButton(btn_yes)
        self._widen_dialog_buttons(box)
        box.exec()

        clicked = box.clickedButton()
        if clicked is btn_no:
            return True
        if clicked is not btn_yes:
            return False           # Abbrechen

        ok, msg = game_backup.create_backup(
            appid, g.get("name", ""), proton.get("version", ""))

        # Bei VRChat zusaetzlich die Screenshots sichern — die liegen nicht
        # unter AppData, sondern in Pictures/VRChat im Prefix.
        pics = 0
        if str(appid) == "438100":
            _pok, pics = game_backup.backup_vrchat_pictures(self._get_pictures_dir())

        if ok:
            note = tr("backup_cfg_done").format(files=msg)
            if pics:
                note += " " + tr("backup_cfg_pics").format(n=pics)
            self._detail_status(note, "#a3be8c")
        else:
            self._detail_status(tr("backup_cfg_failed").format(err=msg), "#bf616a")
        return True

    def _manual_config_backup(self, appid):
        """'Config sichern' ohne Proton-Wechsel — derselbe Ablauf, nur direkt
        angestossen. Nuetzlich vor einem Spiel-Update oder einfach so."""
        proton = {"version": self._selected_proton.get(appid, "")}
        import game_backup
        files, _size = game_backup.estimate_size(appid)
        if not files:
            self._detail_status(tr("backup_cfg_nothing"), "#ebcb8b")
            return
        self._offer_config_backup(appid, proton)
        # Restore-Knopf ist jetzt evtl. benutzbar -> Panel neu aufbauen
        self._on_game_tile_clicked(appid)
        self._on_game_tile_clicked(appid)

    def restore_game_config(self, appid):
        """'Config zurueckspielen' — additiv, es wird nichts geloescht."""
        import game_backup

        if not game_backup.has_backup(appid):
            self._detail_status(tr("restore_cfg_none"), "#ebcb8b")
            return

        info = game_backup.backup_info(appid)
        if not game_backup.prefix_user_dir(appid):
            # Der haeufigste Fall direkt nach einem Proton-Wechsel: das neue
            # Prefix entsteht erst beim ersten Spielstart.
            self._detail_status(tr("restore_cfg_no_prefix"), "#ebcb8b")
            return

        box = QMessageBox(self)
        box.setWindowTitle(tr("restore_cfg_title"))
        box.setIcon(QMessageBox.Question)
        box.setText(tr("restore_cfg_text").format(
            created=info.get("created", "?"), files=info.get("files", "?"),
            proton=info.get("proton", "?")))
        btn_go = box.addButton(tr("restore_cfg_go"), QMessageBox.AcceptRole)
        box.addButton(tr("cancel"), QMessageBox.RejectRole)
        self._widen_dialog_buttons(box)
        box.exec()
        if box.clickedButton() is not btn_go:
            return

        ok, msg = game_backup.restore_backup(appid)
        if ok:
            self._detail_status(tr("restore_cfg_done").format(files=msg), "#a3be8c")
        else:
            self._detail_status(tr("restore_cfg_failed").format(err=msg), "#bf616a")

    def _copy_games_text(self, text, button):
        """Text in die Zwischenablage + kurzes 'Kopiert!'-Feedback am Knopf."""
        QApplication.clipboard().setText(text)
        original = button.text()
        button.setText(tr("games_copied"))
        QTimer.singleShot(1200, lambda: button.setText(original))

    def start_protonplus_install(self, runner_id):
        """
        Öffnet die interaktive ProtonPlus-Installation im Terminal.
        Dort listet ProtonPlus alle Releases; der Nutzer wählt die auf der
        Karte empfohlene Version per Nummer aus.
        """
        if self._pp_worker and self._pp_worker.isRunning():
            return
        cmd = games_db.protonplus_install_cmd(runner_id)
        if not cmd:
            self.ui.lbl_games_status.setText(tr("games_pp_missing"))
            return
        self.ui.lbl_games_status.setText(tr("games_pp_running"))
        self._pp_worker = ProtonPlusInstallWorker(cmd)
        self._pp_worker.finished_signal.connect(self._on_pp_install_done)
        self._pp_worker.start()

    def _on_pp_install_done(self, ok):
        self.ui.lbl_games_status.setText(tr("games_pp_done") if ok else tr("games_pp_missing"))

    def start_manual_proton_install(self, proton, button=None):
        """Laedt einen manuell verteilten Proton-Build (Tarball vom Release).

        Laeuft im Worker-Thread: der Download ist je nach Build ueber ein
        Gigabyte gross und wuerde die Oberflaeche sonst einfrieren.
        """
        if getattr(self, "_manual_worker", None) and self._manual_worker.isRunning():
            return
        self._manual_btn = button
        if button:
            button.setEnabled(False)
        self.ui.lbl_games_status.setText(tr("games_manual_downloading"))

        self._manual_worker = ManualProtonInstallWorker(proton)
        self._manual_worker.progress_signal.connect(self._on_manual_progress)
        self._manual_worker.status_signal.connect(self._on_manual_status)
        self._manual_worker.finished_signal.connect(self._on_manual_install_done)
        self._manual_worker.start()

    def _on_manual_progress(self, percent):
        if percent >= 0:
            self.ui.lbl_games_status.setText(
                f"{tr('games_manual_downloading')} {percent}%")

    def _on_manual_status(self, phase):
        key = {"download": "games_manual_downloading",
               "verify":   "games_manual_verifying",
               "extract":  "games_manual_extracting"}.get(phase)
        if key:
            self.ui.lbl_games_status.setText(tr(key))

    def _on_manual_install_done(self, ok, msg):
        if getattr(self, "_manual_btn", None):
            self._manual_btn.setEnabled(True)
            self._manual_btn = None
        if not ok:
            self.ui.lbl_games_status.setText(tr("games_manual_failed").format(error=msg))
            QMessageBox.warning(self, tr("games_manual_failed_title"),
                                tr("games_manual_failed").format(error=msg))
            return

        self.ui.lbl_games_status.setText(tr("games_manual_done").format(tool=msg))
        box = QMessageBox(self)
        box.setWindowTitle(tr("games_manual_done_title"))
        box.setIcon(QMessageBox.Information)
        box.setText(tr("games_manual_restart_steam").format(tool=msg))
        box.exec()
        # Panel neu aufbauen, damit die Karte den Build jetzt als installiert
        # zeigt und "Use" auswaehlbar wird.
        self._refresh_detail()

    def show_games_info(self):
        """Das kleine (i): erklärt, wo man in Steam Proton-Version und
        Startparameter einträgt."""
        box = QMessageBox(self)
        box.setWindowTitle(tr("games_info_title"))
        box.setTextFormat(Qt.RichText)
        box.setText(tr("games_info_text"))
        box.setIcon(QMessageBox.Information)
        box.exec()
