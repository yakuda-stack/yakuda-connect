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
                               QFrame, QCheckBox, QSlider)
from PySide6.QtCore import (Qt, QTimer, QSize, QPointF, QThread, QUrl,
                            Signal as QtSignal)
from PySide6.QtGui import (QPixmap, QIcon, QPainter, QPolygonF, QColor,
                           QDesktopServices)

import games as games_db
import vrchat_config as vrc_cfg
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
    """QFrame, das wie ein großer Button funktioniert (für die Spiel-Kacheln).

    Hat die Kachel ein ``_hover``-Widget (Play + Einstellungen), wird es nur
    gezeigt, solange die Maus über der Kachel ist."""
    clicked = QtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def enterEvent(self, event):
        hover = getattr(self, "_hover", None)
        if hover is not None:
            hover.setGeometry(self.rect())
            hover.show()
            hover.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event):
        hover = getattr(self, "_hover", None)
        if hover is not None:
            hover.hide()
        super().leaveEvent(event)


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
    GAMES_TILE_W, GAMES_TILE_H = 150, 222   # Kachelgröße
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
        # Ist das Einstellungs-Popup offen (z. B. Auto-Scan im Hintergrund),
        # bleibt es offen und behaelt seine Verweise.
        if self._games_overlay is None or not self._games_overlay.isVisible():
            self._games_detail_widget = None
            self._clear_detail_refs()
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

        # Hover-Ebene: grosser Play-Knopf + transparenter Einstellungen-
        # Knopf. Erscheint nur, solange die Maus ueber der Kachel ist
        # (ClickableFrame.enterEvent/leaveEvent).
        hover = ClickableFrame(tile)
        hover.setObjectName("tileHover")
        hover.setStyleSheet(
            "QFrame#tileHover { background-color: rgba(20, 23, 28, 150);"
            " border-radius: 8px; border: none; }")
        hv = QVBoxLayout(hover)
        hv.setContentsMargins(10, 10, 10, 34)
        hv.setSpacing(10)
        hv.addStretch()

        btn_tile_play = QPushButton()
        btn_tile_play.setObjectName("tilePlay")
        btn_tile_play.setCursor(Qt.PointingHandCursor)
        btn_tile_play.setFixedSize(64, 64)
        btn_tile_play.setIcon(make_play_icon(28, "#21252b"))
        btn_tile_play.setIconSize(QSize(28, 28))
        btn_tile_play.setToolTip(self._tile_play_tooltip(appid, name))
        btn_tile_play.setStyleSheet("""
            QPushButton#tilePlay { background-color: #a3be8c; border: none; border-radius: 32px; }
            QPushButton#tilePlay:hover { background-color: #b8d19f; }
            QPushButton#tilePlay:pressed { background-color: #8fae76; }
        """)
        btn_tile_play.clicked.connect(lambda _, a=appid: self._play_game_from_tile(a))
        hv.addWidget(btn_tile_play, alignment=Qt.AlignHCenter)
        hv.addStretch()

        btn_tile_set = QPushButton(tr("games_settings_btn"))
        btn_tile_set.setObjectName("tileSettings")
        btn_tile_set.setCursor(Qt.PointingHandCursor)
        btn_tile_set.setStyleSheet("""
            QPushButton#tileSettings { background-color: rgba(236, 239, 244, 40); color: #eceff4;
                                       border: 1px solid rgba(236, 239, 244, 90);
                                       border-radius: 5px; padding: 9px 12px;
                                       font-size: 13px; font-weight: bold; }
            QPushButton#tileSettings:hover { background-color: rgba(136, 192, 208, 110); }
        """)
        btn_tile_set.clicked.connect(lambda _, a=appid: self._on_game_tile_clicked(a))
        hv.addWidget(btn_tile_set)
        hover.clicked.connect(lambda a=appid: self._on_game_tile_clicked(a))
        hover.hide()
        tile._hover = hover
        tile._play_btn = btn_tile_play
        tile._settings_btn = btn_tile_set
        tile._name = name

        tile.clicked.connect(lambda a=appid: self._on_game_tile_clicked(a))
        return tile

    def games_retranslate(self):
        """Nach Sprachwechsel: Kachel-Knöpfe neu beschriften und ein
        offenes Einstellungs-Popup in der neuen Sprache neu aufbauen."""
        for appid, tile in getattr(self, "_games_tiles", {}).items():
            if getattr(tile, "_settings_btn", None) is not None:
                tile._settings_btn.setText(tr("games_settings_btn"))
            if getattr(tile, "_play_btn", None) is not None:
                tile._play_btn.setToolTip(
                    self._tile_play_tooltip(appid, getattr(tile, "_name", "")))
        if self._games_overlay is not None and self._games_overlay.isVisible():
            self._refresh_detail()

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

    def _games_overlay_widget(self):
        """Das Einstellungs-Popup (einmal angelegt, danach wiederverwendet)."""
        if self._games_overlay is None:
            from ui.game_settings_overlay import GameSettingsOverlay
            self._games_overlay = GameSettingsOverlay(self)
            self._games_overlay.closed.connect(self._on_games_overlay_closed)
        return self._games_overlay

    def _on_games_overlay_closed(self):
        self._games_detail_widget = None
        self._clear_detail_refs()
        self._expanded_appid = None

    def _clear_detail_refs(self):
        self._detail_params_edit = None
        self._detail_status_lbl = None
        self._detail_toggles = {}
        self._detail_custom_edit = None
        self._detail_base_params = ""

    def _collapse_detail(self):
        """Schliesst das Einstellungs-Popup (falls offen)."""
        if self._games_overlay is not None:
            self._games_overlay.close_overlay()
        self._games_detail_widget = None
        self._clear_detail_refs()
        self._expanded_appid = None

    def _expand_game(self, appid, keep_scroll=False):
        """Oeffnet das Einstellungs-Popup eines Spiels in der Fenstermitte."""
        game = self._game_data_for(appid)
        if not game:
            return
        self._expanded_appid = appid

        # Spiele mit eigener X11-Empfehlung (VRChat): einmal fragen, ob
        # Wayland genutzt wird — davon haengt die empfohlene Proton-Version ab.
        if game.get("protons_x11") and games_db.get_uses_wayland() is None:
            self._ask_uses_wayland()

        self._games_section_open = self._games_section_states.setdefault(str(appid), {})
        self._clear_detail_refs()
        detail = (self._build_local_game_detail(appid, game["entry"])
                  if game.get("local")
                  else self._build_game_detail(appid, game))
        self._games_detail_widget = detail

        ov = self._games_overlay_widget()
        ov.set_content(game.get("name", ""), detail, keep_scroll=keep_scroll)
        if not game.get("local"):
            btn_play = QPushButton(tr("games_play_btn"))
            btn_play.setObjectName("panelPlay")
            btn_play.setCursor(Qt.PointingHandCursor)
            btn_play.setIcon(make_play_icon(12, "#21252b"))
            btn_play.setIconSize(QSize(12, 12))
            btn_play.setStyleSheet("""
                QPushButton#panelPlay { background-color: #a3be8c; color: #21252b; border: none;
                              font-weight: bold; padding: 5px 16px; border-radius: 4px; font-size: 12px; }
                QPushButton#panelPlay:hover { background-color: #b8d19f; }
            """)
            btn_play.clicked.connect(lambda _, a=appid, g=game: self._play_game(a, g))
            ov.add_head_widget(btn_play)
        if not ov.isVisible():
            ov.open_overlay()

    def _ask_uses_wayland(self):
        """Fragt Wayland/X11 ab und merkt sich die Antwort."""
        guess = games_db.session_looks_wayland()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(tr("games_wayland_title"))
        box.setText(tr("games_wayland_text"))
        box.setInformativeText(tr("games_wayland_detected_yes") if guess
                               else tr("games_wayland_detected_no"))
        yes = box.addButton(tr("games_wayland_yes"), QMessageBox.YesRole)
        no = box.addButton(tr("games_wayland_no"), QMessageBox.NoRole)
        box.setDefaultButton(yes if guess else no)
        self._widen_dialog_buttons(box)
        box.exec()
        clicked = box.clickedButton()
        if clicked is None:              # Fenster geschlossen -> Erkennung nehmen
            games_db.set_uses_wayland(guess)
        else:
            games_db.set_uses_wayland(clicked is yes)

    def _change_uses_wayland(self):
        """Knopf im Panel: Antwort aendern und Panel neu aufbauen."""
        self._ask_uses_wayland()
        self._refresh_detail()

    def _refresh_detail(self):
        """Baut das offene Popup neu auf (z. B. nach 'Use': Aktiv-Badge).
        Bleibt offen, Scrollposition und Abschnitte bleiben erhalten."""
        appid = self._expanded_appid
        if appid is None:
            return
        self._expand_game(appid, keep_scroll=True)

    def _on_game_tile_clicked(self, appid):
        """Klick auf Kachel oder „Einstellungen“: Popup dieses Spiels öffnen."""
        if appid == self._expanded_appid and self._games_overlay is not None \
                and self._games_overlay.isVisible():
            self._refresh_detail()
            return
        self._expand_game(appid)

    # ------------------------------------------------------------------ #
    #  "Use" (Proton wählen) + "Play" (Spiel starten)
    # ------------------------------------------------------------------ #
    def _detail_status(self, text, color="#88c0d0"):
        if self._detail_status_lbl is not None:
            try:
                self._detail_status_lbl.setText(text)
                self._detail_status_lbl.setStyleSheet(
                    f"color: {color}; font-size: 11px; border: none;")
            except RuntimeError:
                self._detail_status_lbl = None

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

        # VRChat: alte Bilder aus dem Prefix retten? Verschoben wird erst,
        # wenn der Wechsel wirklich geschrieben wurde (_apply_proton).
        self._pending_pics_move = False
        if str(appid) == "438100":
            answer = self._ask_keep_vrchat_pictures()
            if answer is None:
                return
            self._pending_pics_move = answer

        if games_db.steam_is_running():
            if not self._ask_close_steam():
                self._detail_status(tr("games_use_cancelled_steam"), "#ebcb8b")
                return
            self._close_steam_then(
                lambda a=appid, p=proton, n=name: self._apply_proton(a, p, n))
            return
        self._apply_proton(appid, proton, name)

    def _ask_keep_vrchat_pictures(self):
        """True = verschieben, False = nicht, None = Abbrechen.
        Liegen keine Bilder im Prefix, wird nicht gefragt (False)."""
        import game_backup
        n = game_backup.count_vrchat_pictures()
        if not n:
            return False
        dest = game_backup.vrchat_backup_root(self._get_pictures_dir())
        box = QMessageBox(self)
        box.setWindowTitle(tr("games_pics_keep_title"))
        box.setIcon(QMessageBox.Question)
        box.setText(tr("games_pics_keep_text").format(n=n, dest=dest))
        btn_yes = box.addButton(tr("games_pics_keep_yes"), QMessageBox.AcceptRole)
        btn_no = box.addButton(tr("games_pics_keep_no"), QMessageBox.DestructiveRole)
        box.addButton(tr("cancel"), QMessageBox.RejectRole)
        box.setDefaultButton(btn_yes)
        self._widen_dialog_buttons(box)
        box.exec()
        clicked = box.clickedButton()
        if clicked is btn_yes:
            return True
        if clicked is btn_no:
            return False
        return None

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
        if getattr(self, "_pending_pics_move", False):
            self._pending_pics_move = False
            import game_backup
            ok_m, n, dest = game_backup.move_vrchat_pictures(self._get_pictures_dir())
            msg += " " + (tr("games_pics_moved").format(n=n, dest=dest) if ok_m
                          else tr("games_pics_move_failed").format(dest=dest))
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
        Inhalt des Einstellungs-Popups (ui/game_settings_overlay.py):

          ▾ Proton-Versionen     (offen)  Beschreibung + ⓘ, Wayland-Schalter,
                                          Dropdown + Verwenden/Kopieren/Installieren
          ▸ Spielspezifisch      (zu)     z. B. VRChat: Cache, Fixes, Bilder,
                                          Config-Backup, aus Liste entfernen
          ▸ Startparameter       (zu)     Schalter, eigene, finaler String

        Der Auf/Zu-Zustand wird in self._games_section_open gemerkt, damit ein
        Neuaufbau (z. B. nach „Verwenden“) nichts wieder zuklappt.
        """
        from PySide6.QtWidgets import QComboBox, QWidget
        from ui.game_settings_overlay import CollapsibleSection

        lang = get_language()
        rec_role = games_db.recommended_role(game)
        gpu = games_db.detect_gpu_vendor()
        pp_available = games_db.find_protonplus() is not None
        state = self._games_section_open

        card = QWidget()
        card.setStyleSheet("background:transparent;")
        box = QVBoxLayout(card)
        box.setContentsMargins(0, 0, 6, 0)
        box.setSpacing(10)

        # Von Hand ergaenzt? Dann sichtbar machen UND zuruecknehmbar.
        if str(appid) in games_db.load_manual_steam_appids():
            man_row = QHBoxLayout()
            lbl_manual = QLabel(tr("games_manual_badge"))
            lbl_manual.setStyleSheet("color: #88c0d0; font-size: 11px; border: none;")
            lbl_manual.setToolTip(tr("games_manual_badge_tip"))
            man_row.addWidget(lbl_manual)
            btn_unmanual = QPushButton(tr("games_manual_remove_btn"))
            btn_unmanual.setCursor(Qt.PointingHandCursor)
            btn_unmanual.setToolTip(tr("games_manual_remove_tip"))
            btn_unmanual.setStyleSheet(self._small_button_style())
            btn_unmanual.clicked.connect(
                lambda _=False, a=appid: self.remove_manual_steam_game(a))
            man_row.addWidget(btn_unmanual)
            man_row.addStretch()
            box.addLayout(man_row)

        if game.get("shortcut"):
            self._add_image_row(box, appid, "shortcut")

        # ================= Proton-Versionen ================= #
        sec = CollapsibleSection(tr("games_proton_section").rstrip(": "), "proton", state, default_open=True)
        protons = list(games_db.visible_protons(game))
        role_labels = {
            "main": tr("games_role_main"),
            "main_cachyos": tr("games_role_cachyos"),
            "alternative": tr("games_role_alt"),
            "alternative_ge": tr("games_role_alt_ge"),
            "safe": tr("games_role_safe"),
        }

        desc_row = QHBoxLayout()
        lbl_desc = QLabel("")
        lbl_desc.setStyleSheet("color: #d8dee9; font-size: 11px; border: none;")
        lbl_desc.setWordWrap(True)
        desc_row.addWidget(lbl_desc, 1)
        btn_info = QPushButton("ⓘ")
        btn_info.setCursor(Qt.PointingHandCursor)
        btn_info.setFixedSize(22, 22)
        btn_info.setStyleSheet("""
            QPushButton { background: transparent; color: #88c0d0; border: none;
                          font-size: 15px; padding: 0; }
            QPushButton:hover { color: #eceff4; }
        """)
        desc_row.addWidget(btn_info, 0, Qt.AlignTop)
        sec.body.addLayout(desc_row)

        lbl_badges = QLabel("")
        lbl_badges.setStyleSheet("color: #ebcb8b; font-size: 11px; font-weight: bold; border: none;")
        sec.body.addWidget(lbl_badges)
        lbl_src = QLabel("")
        lbl_src.setStyleSheet("color: #7b88a1; font-size: 10px; font-style: italic; border: none;")
        lbl_src.setWordWrap(True)
        sec.body.addWidget(lbl_src)

        # Wayland-Schalter: gruen = Wayland, sonst normale Farbe (= X11).
        if game.get("protons_x11"):
            uses_wl = games_db.get_uses_wayland() is not False
            wl_row = QHBoxLayout()
            btn_wl = QPushButton("Wayland")
            btn_wl.setCursor(Qt.PointingHandCursor)
            btn_wl.setToolTip(tr("games_wayland_switch_tip"))
            btn_wl.setStyleSheet(
                "QPushButton { background-color:#a3be8c; color:#21252b; border:none;"
                " font-weight:bold; padding:4px 14px; border-radius:4px; font-size:11px; }"
                " QPushButton:hover { background-color:#b8d19f; }"
                if uses_wl else self._small_button_style())
            btn_wl.clicked.connect(lambda _=False, w=uses_wl: self._toggle_uses_wayland(w))
            wl_row.addWidget(btn_wl)
            lbl_wl = QLabel(tr("games_wayland_on") if uses_wl else tr("games_wayland_off"))
            lbl_wl.setStyleSheet("color: #7b88a1; font-size: 11px; border: none;")
            wl_row.addWidget(lbl_wl)
            wl_row.addStretch()
            sec.body.addLayout(wl_row)

        pick_row = QHBoxLayout()
        combo = QComboBox()
        combo.setMinimumWidth(260)
        active_idx, rec_idx = -1, 0
        tool_names = []
        for i, proton in enumerate(protons):
            installed_tool, found, _kind = games_db.resolve_steam_tool(proton)
            tool_names.append((installed_tool, found))
            text = installed_tool or proton.get("version", "")
            if proton.get("untested"):
                text = f"{text} {tr('games_untested_suffix')}"
            if proton.get("role") == rec_role:
                rec_idx = i
                text = "★ " + text
            sel = self._selected_proton.get(appid)
            if sel and sel in (proton.get("version"), installed_tool):
                active_idx = i
                text += "  ✓"
            combo.addItem(text)
        pick_row.addWidget(combo, 1)

        btn_use = QPushButton(tr("games_use_btn"))
        btn_use.setCursor(Qt.PointingHandCursor)
        btn_use.setStyleSheet(self._fix_button_style())
        btn_copy_ver = QPushButton(tr("games_copy_btn"))
        btn_copy_ver.setCursor(Qt.PointingHandCursor)
        btn_copy_ver.setStyleSheet(self._small_button_style())
        btn_inst = QPushButton(tr("games_install_btn"))
        btn_inst.setCursor(Qt.PointingHandCursor)
        btn_inst.setStyleSheet(self._fix_button_style())
        for b in (btn_use, btn_copy_ver, btn_inst):
            pick_row.addWidget(b)
        sec.body.addLayout(pick_row)

        def current():
            i = combo.currentIndex()
            return protons[i] if 0 <= i < len(protons) else None

        def update_view(_i=None):
            proton = current()
            if proton is None:
                for w in (btn_use, btn_copy_ver, btn_inst, btn_info):
                    w.setEnabled(False)
                return
            i = combo.currentIndex()
            installed_tool, found = tool_names[i]
            desc = proton.get("desc", {})
            lbl_desc.setText(desc.get(lang) or desc.get("en") or desc.get("de") or "")
            url = games_db.proton_info_url(proton)
            btn_info.setVisible(bool(url))
            btn_info.setToolTip(tr("games_proton_info_tip").format(url=url) if url else "")
            btn_info._url = url

            is_rec = proton.get("role") == rec_role
            badge = ((tr("games_recommended_cachyos") if rec_role == "main_cachyos"
                      else tr("games_recommended")) if is_rec
                     else role_labels.get(proton.get("role"), ""))
            if i == active_idx:
                badge = (badge + "   " if badge else "") + tr("games_active_badge")
            lbl_badges.setText(badge)

            btn_use.setEnabled(i != active_idx)
            runner_id = proton.get("protonplus_runner")
            if proton.get("download_url"):
                btn_inst.setVisible(True)
                btn_inst.setText((tr("games_manual_reinstall_btn") if found
                                  else tr("games_manual_install_btn")).replace("&", "&&"))
                lbl_src.setText(tr("games_manual_note"))
                lbl_src.setStyleSheet("color: #7b88a1; font-size: 10px; font-style: italic; border: none;")
            elif runner_id and pp_available:
                btn_inst.setVisible(True)
                btn_inst.setText(tr("games_pp_install_btn").replace("&", "&&"))
                lbl_src.setText("")
            else:
                btn_inst.setVisible(False)
                if runner_id is None:
                    lbl_src.setText(tr("games_pp_steam_note"))
                    lbl_src.setStyleSheet("color: #7b88a1; font-size: 10px; font-style: italic; border: none;")
                else:
                    lbl_src.setText(tr("games_pp_missing"))
                    lbl_src.setStyleSheet("color: #ebcb8b; font-size: 10px; font-style: italic; border: none;")
            lbl_src.setVisible(bool(lbl_src.text()))

        def do_install():
            proton = current()
            if proton is None:
                return
            if proton.get("download_url"):
                self.start_manual_proton_install(proton, btn_inst)
            elif proton.get("protonplus_runner"):
                self.start_protonplus_install(proton["protonplus_runner"])

        combo.currentIndexChanged.connect(update_view)
        btn_use.clicked.connect(lambda _=False: current() and self._use_proton(appid, current()))
        btn_copy_ver.clicked.connect(
            lambda _=False: current() and self._copy_games_text(current().get("version", ""), btn_copy_ver))
        btn_inst.clicked.connect(lambda _=False: do_install())
        btn_info.clicked.connect(
            lambda _=False: btn_info._url and QDesktopServices.openUrl(QUrl(btn_info._url)))
        combo.setCurrentIndex(active_idx if active_idx >= 0 else rec_idx)
        update_view()
        box.addWidget(sec)

        # ================= Spielspezifisch ================= #
        sec = CollapsibleSection(tr("games_specific_section"), "specific", state)
        fixes = game.get("fixes", [])
        self._build_fixes(sec.body, appid, fixes)
        self._build_backup_rows(sec.body, appid)
        box.addWidget(sec)

        # ================= Startparameter ================= #
        sec = CollapsibleSection(tr("games_params_head"), "params", state)
        self._build_launch_params(sec.body, appid, game, gpu)
        box.addWidget(sec)

        # Statuszeile fuer Use-/Play-Feedback (Steam-Neustart-Hinweis usw.)
        self._detail_status_lbl = QLabel("")
        self._detail_status_lbl.setStyleSheet("color: #88c0d0; font-size: 11px; border: none;")
        self._detail_status_lbl.setWordWrap(True)
        box.addWidget(self._detail_status_lbl)
        box.addStretch()
        return card

    @staticmethod
    def _small_button_style():
        return """
            QPushButton { background-color: #2e3440; color: #d8dee9; border: 1px solid #4c566a;
                          padding: 4px 10px; border-radius: 4px; font-size: 11px; }
            QPushButton:hover { background-color: #3b4252; border-color: #5e81ac; }
            QPushButton:disabled { color: #616b7f; }
        """

    def _toggle_uses_wayland(self, current):
        """Wayland-Knopf im Popup: umschalten und neu aufbauen."""
        games_db.set_uses_wayland(not current)
        self._refresh_detail()

    def _build_launch_params(self, box, appid, game, gpu):
        """Startparameter: Basis (GPU-abhängig) + Schalter + eigene + final."""
        params = game.get("launch_params", {})
        if game.get("shortcut"):
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

        games_db.refresh_vrcvideocacher_path()
        game_toggles = games_db.resolved_toggles(game)
        self._detail_game_toggles = game_toggles
        saved_keys, saved_custom = games_db.load_launch_toggles(appid, game_toggles)
        if games_db.has_saved_launch_toggles(appid):
            initial_keys = set(saved_keys)
        else:
            initial_keys = set(game.get("default_on", []))
            initial_keys |= {t["key"] for t in game_toggles if t.get("default")}

        lbl_toggles = QLabel(tr("games_toggles_section"))
        lbl_toggles.setStyleSheet("color: #7b88a1; font-size: 11px; font-weight: bold; border: none;")
        box.addWidget(lbl_toggles)

        TOGGLES_PER_ROW = 3
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

        lbl_custom = QLabel(tr("games_custom_params"))
        lbl_custom.setStyleSheet("color: #7b88a1; font-size: 11px; font-weight: bold; border: none;")
        box.addWidget(lbl_custom)
        self._detail_custom_edit = QLineEdit(saved_custom)
        self._detail_custom_edit.setPlaceholderText(tr("games_custom_placeholder"))
        self._detail_custom_edit.setStyleSheet("font-family: monospace; font-size: 11px;")
        self._detail_custom_edit.textEdited.connect(
            lambda _, a=appid: self._on_launch_opts_changed(a))
        box.addWidget(self._detail_custom_edit)

        lbl_final = QLabel(tr("games_final_params"))
        lbl_final.setStyleSheet("color: #7b88a1; font-size: 11px; font-weight: bold; border: none;")
        box.addWidget(lbl_final)
        param_row = QHBoxLayout()
        txt_params = QLineEdit()
        txt_params.setReadOnly(True)
        txt_params.setStyleSheet("font-family: monospace; font-size: 11px; color: #a3be8c;")
        self._detail_params_edit = txt_params
        param_row.addWidget(txt_params)
        btn_copy = QPushButton(tr("games_copy_btn"))
        btn_copy.setCursor(Qt.PointingHandCursor)
        btn_copy.setStyleSheet(self._fix_button_style())
        btn_copy.clicked.connect(
            lambda _, t=txt_params, b=btn_copy: self._copy_games_text(t.text(), b))
        param_row.addWidget(btn_copy)
        box.addLayout(param_row)
        self._update_final_params()

    def _fix_desc_label(self, key):
        lbl = QLabel(tr(key))
        lbl.setStyleSheet("color: #7b88a1; font-size: 10px; border: none;")
        lbl.setWordWrap(True)
        return lbl

    def _fix_button(self, key, slot):
        btn = QPushButton(tr(f"{key}_btn"))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(tr(f"{key}_tip"))
        btn.setStyleSheet(self._fix_button_style())
        btn.clicked.connect(slot)
        return btn

    def _build_fixes(self, box, appid, fixes):
        """Spielspezifische Fixes — untereinander, je mit kurzer Erklärung."""
        if "vrchat_cache" in fixes:
            self._build_vrchat_cache_row(box)

        if "vrchat_pictures" in fixes:
            btn_pic = self._fix_button("games_fix_pictures", self.create_vrchat_symlink)
            self.ui.btn_vrchat_symlink = btn_pic
            row = QHBoxLayout()
            row.addWidget(btn_pic)
            row.addWidget(self._fix_button("games_pics_open_proton", self.open_vrchat_pictures_folder))
            row.addWidget(self._fix_button("games_pics_open_backup", self.open_vrchat_backup_folder))
            row.addStretch()
            box.addLayout(row)
            box.addWidget(self._fix_desc_label("games_fix_pictures_desc"))

        if "vrchat_videoplayer" in fixes:
            row = QHBoxLayout()
            row.addWidget(self._fix_button("games_fix_video", self.show_vrchat_videoplayer_fix))
            row.addStretch()
            box.addLayout(row)
            box.addWidget(self._fix_desc_label("games_vci_note"))

        if "vrchat_check" in fixes:
            btn_chk = self._fix_button("games_fix_check", self.run_vrchat_check)
            self.ui.btn_vrchat_check = btn_chk
            row = QHBoxLayout()
            row.addWidget(btn_chk)
            row.addStretch()
            box.addLayout(row)

        if fixes:
            lbl_fix_status = QLabel("")
            lbl_fix_status.setStyleSheet("font-size: 11px; border: none;")
            lbl_fix_status.setWordWrap(True)
            lbl_fix_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.ui.lbl_vrchat_status = lbl_fix_status
            box.addWidget(lbl_fix_status)

    def _build_backup_rows(self, box, appid):
        """Config-Backup / -Restore und „Aus Liste entfernen“ (alle Spiele)."""
        import game_backup
        lbl_bk_head = QLabel(tr("backup_cfg_section"))
        lbl_bk_head.setStyleSheet("color: #7b88a1; font-size: 11px; font-weight: bold; border: none;")
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
        if game_backup.has_backup(appid):
            info = game_backup.backup_info(appid)
            btn_rs.setToolTip(tr("restore_cfg_btn_tip").format(
                created=info.get("created", "?"), files=info.get("files", "?")))
        else:
            btn_rs.setEnabled(False)
            btn_rs.setToolTip(tr("restore_cfg_btn_none"))
        bk_row.addWidget(btn_rs)

        btn_del = QPushButton(tr("games_remove_btn"))
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.setToolTip(tr("games_remove_tip"))
        btn_del.setStyleSheet(self._small_button_style())
        btn_del.clicked.connect(lambda _=False, a=appid: self.remove_game_from_list(a))
        bk_row.addWidget(btn_del)
        bk_row.addStretch()
        box.addLayout(bk_row)

    def open_vrchat_pictures_folder(self):
        """Öffnet Pictures/VRChat im Proton-Prefix (Unterordner wie 2026-10)."""
        import game_backup
        path = game_backup.vrchat_pictures_src()
        if not os.path.isdir(path):
            self._detail_status(tr("games_pics_no_folder"), "#ebcb8b")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def open_vrchat_backup_folder(self):
        """Öffnet <Bilder>/Backup_VRchat (wird bei Bedarf angelegt)."""
        import game_backup
        path = game_backup.vrchat_backup_root(self._get_pictures_dir())
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as exc:
            self._detail_status(str(exc), "#bf616a")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ----------------------------------------------------------------- #
    #  VRChat-Fixes
    # ----------------------------------------------------------------- #
    def _build_vrchat_cache_row(self, box):
        """Schieberegler fuer VRChats cache_size (30–130 GB, siehe
        core/vrchat_config.py). Gespeichert wird beim Loslassen."""
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl = QLabel(tr("games_vrc_cache_label"))
        lbl.setToolTip(tr("games_vrc_cache_tip"))
        lbl.setStyleSheet("color: #d8dee9; font-size: 11px; border: none;")

        slider = QSlider(Qt.Horizontal)
        slider.setRange(vrc_cfg.CACHE_MIN, vrc_cfg.CACHE_MAX)
        slider.setSingleStep(1)
        slider.setPageStep(10)
        slider.setToolTip(tr("games_vrc_cache_tip"))
        slider.setValue(vrc_cfg.cache_size())

        lbl_val = QLabel("")
        lbl_val.setMinimumWidth(110)
        lbl_val.setStyleSheet("color: #88c0d0; font-size: 11px; font-weight: bold; border: none;")

        def show(val):
            text = f"{val} GB"
            if val == vrc_cfg.CACHE_DEFAULT:
                text += " " + tr("games_vrc_cache_default")
            lbl_val.setText(text)

        def save():
            val = slider.value()
            ok = vrc_cfg.set_cache_size(val)
            status = getattr(self, "_detail_status_lbl", None)
            if status is not None:
                status.setText(tr("games_vrc_cache_saved" if ok else "games_vrc_cache_failed")
                               .format(gb=val, path=vrc_cfg.config_path()))

        show(slider.value())
        slider.valueChanged.connect(show)
        slider.sliderReleased.connect(save)
        slider.actionTriggered.connect(
            lambda action: QTimer.singleShot(0, save)
            if action != QSlider.SliderMove else None)

        if not vrc_cfg.prefix_exists():
            slider.setEnabled(False)
            lbl_val.setText(tr("games_vrc_cache_no_prefix"))

        row.addWidget(lbl)
        row.addWidget(slider, 1)
        row.addWidget(lbl_val)
        box.addLayout(row)

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
        box.setText(self._wayland_ge_note_html() + tr("games_video_fix_text"))
        box.setIcon(QMessageBox.Information)
        wlge = self._vrchat_wayland_ge()
        btn_wlge = None
        if wlge is not None and not self._is_active_proton("438100", wlge):
            btn_wlge = box.addButton(tr("games_wlge_use_btn"), QMessageBox.ApplyRole)

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
        if btn_wlge is not None and clicked is btn_wlge:
            self._use_wayland_ge()
        elif btn_install is not None and clicked is btn_install:
            self.install_vrcvideocacher()
        elif clicked is btn_open:
            QDesktopServices.openUrl(QUrl("https://github.com/EllyVR/VRCVideoCacher"))
        elif clicked is btn_steam:
            QDesktopServices.openUrl(
                QUrl("https://store.steampowered.com/app/4296960/VRCVideoCacher/"))

    # --- Proton-RTSP-Wayland-GE: macht VRCVideoCacher ueberfluessig ------- #
    @staticmethod
    def _vrchat_wayland_ge():
        """Der Proton-RTSP-Wayland-GE-Eintrag von VRChat — oder None."""
        game = games_db.GAMES.get("438100")
        if not game:
            return None
        for p in games_db.visible_protons(game):
            if "wayland-ge" in (p.get("version") or "").lower():
                return p
        return None

    def _is_active_proton(self, appid, proton):
        installed_tool, _f, _k = games_db.resolve_steam_tool(proton)
        sel = self._selected_proton.get(appid)
        return bool(sel) and sel in (proton.get("version"), installed_tool)

    def _wayland_ge_note_html(self):
        p = self._vrchat_wayland_ge()
        ver = p.get("version") if p else "Proton-RTSP-Wayland-GE-Beta4"
        active = p is not None and self._is_active_proton("438100", p)
        text = tr("games_wlge_note").format(version=ver)
        if active:
            text += "<br>" + tr("games_wlge_active")
        return f'<div style="background:#2e3440;padding:6px;">{text}</div><br>'

    def _use_wayland_ge(self):
        """Setzt Proton-RTSP-Wayland-GE fuer VRChat (normaler „Verwenden“-Weg)."""
        p = self._vrchat_wayland_ge()
        if p is None:
            return
        _tool, found, _k = games_db.resolve_steam_tool(p)
        if not found and p.get("download_url"):
            self.start_manual_proton_install(p)
            return
        self._use_proton("438100", p)

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
            self._refresh_detail()

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
        box.setText(f"<b>{head}</b><br><br>" + "".join(lines)
                    + "<br>" + self._wayland_ge_note_html())
        box.setIcon(QMessageBox.Information if status == vc.OK else QMessageBox.Warning)
        wlge = self._vrchat_wayland_ge()
        btn_wlge = None
        if wlge is not None and not self._is_active_proton("438100", wlge):
            btn_wlge = box.addButton(tr("games_wlge_use_btn"), QMessageBox.ApplyRole)
        box.addButton(QMessageBox.Ok)
        self._widen_dialog_buttons(box)
        box.exec()
        if btn_wlge is not None and box.clickedButton() is btn_wlge:
            self._use_wayland_ge()

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

        # VRChat-Bilder werden beim Proton-Wechsel separat verschoben
        # (_ask_keep_vrchat_pictures), nicht mehr hier kopiert.
        pics = 0

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
        self._refresh_detail()

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
            text = f"{tr('games_manual_downloading')} {percent}%"
            self.ui.lbl_games_status.setText(text)
            self._detail_status(text)

    def _on_manual_status(self, phase):
        key = {"download": "games_manual_downloading",
               "verify":   "games_manual_verifying",
               "extract":  "games_manual_extracting"}.get(phase)
        if key:
            self.ui.lbl_games_status.setText(tr(key))
            self._detail_status(tr(key))

    def _on_manual_install_done(self, ok, msg):
        if getattr(self, "_manual_btn", None):
            try:
                self._manual_btn.setEnabled(True)
            except RuntimeError:
                pass
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
