#!/usr/bin/env python3
"""
core/tabs/dashboard_mixin.py — Dashboard: Headsets, USB und die WiVRn-App
=========================================================================
Ausgelagert aus core/main.py, das mit ueber 4500 Zeilen wieder an dem Punkt
war, an dem man Aenderungen darin nicht mehr gern macht. Dritter Schnitt
nach games_mixin und tools_mixin, gleiches Muster.

Das ist ein MIXIN, keine eigenstaendige Klasse: die Methoden hier arbeiten
weiterhin auf demselben Objekt wie vorher (self.ui, self.server_process,
...). VRApp erbt davon, am Verhalten aendert sich nichts — genau deshalb
konnten die Rumpfe unveraendert umziehen.

Zustaendig fuer alles, was zwischen PC und Brille passiert:

  * die USB-Ampel unter der Headset-Liste (haengt eine Brille am Kabel, und
    kaeme WiVRn per adb an sie heran?)
  * die Liste gekoppelter Headsets, Kopplungsmodus und Trennen
  * "Verbinden (USB)" — adb reverse plus Intent, wie WiVRns Dashboard
  * den adb-Doktor (Diagnose und Reparatur nach Systemupdates)
  * Herunterladen und Installieren der WiVRn-APK

Die Worker-Klassen wandern mit: sie werden ausschliesslich hier gebraucht,
und blieben sie in main.py, muesste dieses Modul von dort importieren —
waehrend main.py dieses Modul importiert. Ein Ringimport, den Python beim
Start mit einem ImportError quittiert.

Die Attribute (self._usb_worker, self._adb_updated, ...) werden weiterhin in
VRApp.__init__ gesetzt. Das ist bei Mixins ueblich, aber man muss es wissen:
wer hier ein neues Attribut braucht, legt es dort an. Ebenso lebt
``_release_worker_on_finish`` als allgemeine Infrastruktur weiter in VRApp.
"""
import os
import re
import shutil
import subprocess
import time

from PySide6.QtWidgets import (QFileDialog, QListWidgetItem, QMessageBox)
from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal as QtSignal
from PySide6.QtGui import QDesktopServices

import adb_doctor as adbdoc
import proc
import usb_headsets as usbhs
import wivrn_dashboard as wivrn_dash
import wivrn_server
import wivrn_apk as wapk
from translations import tr

from logging_setup import get_logger

log = get_logger("dashboard_tab")


class ApkWorker(QThread):
    """
    Holt die WiVRn-APK und installiert sie per adb — oder legt sie nur ab.

    ``mode="install"``   Download in den Zwischenspeicher, danach adb install
    ``mode="download"``  Download in ``target_dir``, danach ist Schluss

    Dass beides derselbe Worker ist, hat einen Grund: die ersten drei
    Schritte (passendes Release suchen, Asset finden, herunterladen) sind
    identisch, und die Versionslogik soll es nur EINMAL geben. Sonst laedt
    der eine Knopf die passende und der andere die neueste APK.

    Welche Version die richtige ist, entscheidet ``wivrn_apk.pick_release()``
    anhand des installierten Servers — siehe dortiger Modul-Kopf.
    """
    status_signal   = QtSignal(str)    # Statustext (bereits uebersetzt)
    warning_signal  = QtSignal(str)    # Versions-Warnung, gelb
    finished_signal = QtSignal(bool)   # Erfolg/Fehler
    saved_signal    = QtSignal(str)    # Ablageort (nur im Download-Modus)

    def __init__(self, mode="install", target_dir=None):
        super().__init__()
        self.mode = mode
        self.target_dir = target_dir
        self._cancel = False
        self._last_progress = 0.0

    def cancel(self):
        self._cancel = True

    # -- Fortschritt ------------------------------------------------------ #
    def _progress(self, done, total):
        """
        Statuszeile hoechstens vier Mal pro Sekunde aktualisieren.

        Ohne Bremse kaemen bei 64-KiB-Bloecken mehrere hundert Signale pro
        Sekunde im GUI-Thread an — der macht dann nichts anderes mehr, als
        einen Text neu zu zeichnen, den ohnehin niemand so schnell liest.
        """
        now = time.monotonic()
        if now - self._last_progress < 0.25 and done != total:
            return
        self._last_progress = now
        if total:
            self.status_signal.emit(tr("apk_status_downloading").format(
                done=f"{done / 1_000_000:.1f}", total=f"{total / 1_000_000:.1f}"))
        else:
            self.status_signal.emit(tr("apk_status_downloading_nototal").format(
                done=f"{done / 1_000_000:.1f}"))

    # -- Ablauf ----------------------------------------------------------- #
    def run(self):
        try:
            self._run()
        except wapk.Cancelled:
            self.status_signal.emit(tr("apk_status_cancelled"))
            self.finished_signal.emit(False)
        except wapk.DownloadError as exc:
            self.status_signal.emit(tr(exc.key).format(**exc.params))
            self.finished_signal.emit(False)
        except Exception as exc:
            log.warning("ApkWorker: %s", exc)
            self.status_signal.emit(tr("apk_status_error").format(err=exc))
            self.finished_signal.emit(False)

    def _run(self):
        # 1. Passendes Release suchen (nicht einfach das neueste!)
        self.status_signal.emit(tr("apk_status_lookup"))
        release, matched, server = wapk.pick_release()
        if not release:
            self.status_signal.emit(tr("apk_status_no_release"))
            self.finished_signal.emit(False)
            return

        tag = str(release.get("tag_name", "?"))
        asset = wapk.asset_for(release)
        if not asset:
            self.status_signal.emit(tr("apk_status_no_asset").format(tag=tag))
            self.finished_signal.emit(False)
            return
        asset_name, url, _size = asset

        # 2. Sagen, WARUM es diese Version ist. Der Nutzer soll nicht raten
        #    muessen, ob hier gerade die passende oder irgendeine laedt.
        if matched:
            self.status_signal.emit(tr("apk_match_server").format(server=server, tag=tag))
        elif matched is False:
            self.warning_signal.emit(tr("apk_no_match_server").format(server=server, tag=tag))
        else:
            self.status_signal.emit(tr("apk_server_unknown").format(tag=tag))

        if self._cancel:
            raise wapk.Cancelled()

        # 3. Herunterladen
        filename = wapk.suggested_filename(release, asset_name)
        if self.mode == "download":
            dest = os.path.join(self.target_dir or os.path.expanduser("~"), filename)
        else:
            dest = wapk.cache_apk_path(filename)

        wapk.download(url, dest, progress=self._progress,
                      cancel=lambda: self._cancel)

        if self.mode == "download":
            self.status_signal.emit(tr("apk_status_saved").format(path=dest))
            self.saved_signal.emit(dest)
            self.finished_signal.emit(True)
            return

        # 4. Brille suchen. Bewusst ueber usb_headsets: das kennt auch
        #    'unauthorized' und zaehlt es nicht als bereit.
        if self._cancel:
            raise wapk.Cancelled()
        self.status_signal.emit(tr("apk_status_search_headset"))
        serial = wapk.ready_serial()
        if not serial:
            self.status_signal.emit(tr("apk_status_no_headset"))
            self.finished_signal.emit(False)
            return

        # 5. Installieren. Ab hier wirkt Abbrechen nicht mehr — ein laufendes
        #    'adb install' mittendrin abzuschiessen hinterlaesst auf der
        #    Brille eine halb installierte App.
        self.status_signal.emit(tr("apk_status_installing").format(serial=serial))
        res = proc.run(["adb", "-s", serial, "install", "-r", dest],
                       timeout=proc.LONG_TIMEOUT)

        if res.returncode == 0:
            self.status_signal.emit(tr("apk_status_installed").format(tag=tag))
            self.finished_signal.emit(True)
        else:
            detail = (res.stderr or res.stdout or "").strip()
            self.status_signal.emit(tr("apk_status_install_failed").format(err=detail))
            self.finished_signal.emit(False)


class UsbConnectWorker(QThread):
    """
    Verbindet ueber das Kabel — und laesst sich davon nicht abschrecken,
    dass die Brille erst einmal schweigt.

    Hintergrund: die PICO 4 blockiert adb, solange die USB-Schnittstelle im
    Dateiuebertragungs-Modus verhakt ist. adb antwortet dann gar nicht, und
    ein einziger Aufruf endet mit "timeout" — obwohl der Nutzer das Problem
    in diesem Moment selbst loest, indem er an der Brille kurz auf "Nur
    Laden" und zurueck auf "Dateiuebertragung" stellt. Das offizielle
    Dashboard verbindet genau deshalb "sofort", sobald man umschaltet: es
    fragt einfach weiter.

    Also fragt dieser Worker auch weiter — bis zur Frist oder bis zum
    Abbruch. ``status_signal`` traegt Uebersetzungs-Schluessel, damit der
    Worker keine Texte kennen muss.
    """
    result_signal = QtSignal(bool, str, str)   # ok, grund/detail, paket
    status_signal = QtSignal(str)              # Uebersetzungs-Schluessel

    # Grosszuegig: der Nutzer muss die Brille aufsetzen, ins Menue gehen und
    # zweimal umschalten. Wer das in 20 Sekunden schafft, ist schneller als
    # die meisten.
    DEADLINE = 90
    ROUND_PAUSE = 2.0

    def __init__(self, deadline=DEADLINE):
        super().__init__()
        self.deadline = deadline
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _cancelled(self):
        return self._cancel

    def _on_retry(self, attempt, total):
        # Erst ab dem zweiten Anlauf melden: der erste Timeout ist noch
        # Alltag, ab dem zweiten wird der Hinweis zur Brille interessant.
        self.status_signal.emit("usb_connect_waiting")

    def run(self):
        end = time.monotonic() + self.deadline
        last_detail = ""
        try:
            while True:
                if self._cancel:
                    self.result_signal.emit(False, "cancelled", "")
                    return

                serial = wapk.ready_serial()
                if not serial:
                    # Beim Umschalten an der Brille verschwindet das Geraet
                    # kurz aus 'adb devices'. Das ist kein Fehler, das ist
                    # der Vorgang, auf den wir warten.
                    last_detail = "no_device"
                    if time.monotonic() >= end:
                        self.result_signal.emit(False, "no_device", "")
                        return
                    self.status_signal.emit("usb_connect_waiting")
                    wapk._sleep(self.ROUND_PAUSE, self._cancelled)
                    continue

                res = wapk.connect_usb(serial, cancel=self._cancelled,
                                       on_retry=self._on_retry)
                if res["ok"]:
                    self.result_signal.emit(
                        True, "uncertain" if res["uncertain"] else "",
                        res["package"])
                    return

                last_detail = res["detail"]
                if not wapk.retryable(last_detail) or time.monotonic() >= end:
                    self.result_signal.emit(False, last_detail, "")
                    return

                self.status_signal.emit("usb_connect_waiting")
                wapk._sleep(self.ROUND_PAUSE, self._cancelled)

        except wapk.Cancelled:
            self.result_signal.emit(False, "cancelled", "")
        except Exception as exc:
            log.warning("UsbConnectWorker: %s", exc)
            self.result_signal.emit(False, str(exc) or last_detail, "")


class AdbDoctorWorker(QThread):
    """
    Diagnose und Reparatur des adb-Handshakes im Hintergrund.

    Beides in einem Worker, weil die Reparatur mit einer Diagnose endet —
    und weil beide Wege Paketmanager-Aufrufe machen, die im GUI-Thread
    nichts verloren haben (``pacman -Q`` haengt an einer Lock-Datei, wenn
    gerade ein Update laeuft, und genau dann fragt der Nutzer hier nach).

    ``mode="probe"``   nur nachsehen, aendert nichts
    ``mode="repair"``  Server neu starten, bei Bedarf udev neu laden
    """
    probe_signal = QtSignal(dict)
    repair_signal = QtSignal(bool, list)

    def __init__(self, mode="probe", state="", with_udev=False):
        super().__init__()
        self.mode = mode
        self.state = state
        self.with_udev = with_udev

    def run(self):
        try:
            if self.mode == "repair":
                ok, steps = adbdoc.repair(self.state, with_udev=self.with_udev)
                self.repair_signal.emit(ok, steps)
            else:
                info = adbdoc.probe()
                info["mtp_busy"] = adbdoc.mtp_busy()
                self.probe_signal.emit(info)
        except Exception as exc:
            log.warning("AdbDoctorWorker (%s): %s", self.mode, exc)
            if self.mode == "repair":
                self.repair_signal.emit(False, ["adb_fix_step_still_broken"])
            else:
                self.probe_signal.emit({})


class PairingPinWorker(QThread):
    """
    Liest die PIN-Zeile von ``wivrnctl pair``.

    Ein winziger Thread fuer genau eine Zeile — aber genau die hat vorher
    die Oberflaeche blockiert (siehe ``toggle_pairing_mode``). Das
    Popen-Objekt wird uebergeben und hier NICHT beendet: das Abschalten des
    Kopplungsmodus gehoert dem Fenster.
    """
    pin_signal = QtSignal(str)

    def __init__(self, process):
        super().__init__()
        self._process = process

    def run(self):
        try:
            line = self._process.stdout.readline()
        except Exception as exc:
            log.debug("PairingPinWorker: %s", exc)
            self.pin_signal.emit("")
            return
        if "PIN:" in (line or ""):
            self.pin_signal.emit(line.replace("PIN:", "").strip())
        else:
            self.pin_signal.emit("")


class WivrnVersionWorker(QThread):
    """
    Vergleicht die WiVRn-Version auf der Brille (per adb) mit dem
    installierten ``wivrn-server``.

    Das ist DER Klassiker im Support: Server per Paketmanager aktualisiert,
    App auf der Brille noch alt — und die Brille verbindet einfach nicht,
    ohne verstaendliche Fehlermeldung. ``dumpsys`` kann ein paar Sekunden
    dauern, deshalb im Hintergrund und nur einmal pro angesteckter Brille.
    """
    result_signal = QtSignal(dict)   # client, server, match (True/False/None)

    def run(self):
        res = {"client": "", "server": "", "match": None}
        try:
            serial = wapk.ready_serial()
            if serial:
                package = wapk.detect_package(serial)
                res["client"] = wapk.client_version(serial, package)
            res["server"] = wapk.server_version()
            res["match"] = wapk.versions_match(res["client"], res["server"])
        except Exception as exc:  # noqa: BLE001 — Hinweis darf nie abstuerzen
            log.debug("WiVRn-Versionsvergleich fehlgeschlagen: %s", exc)
        self.result_signal.emit(res)


class UsbHeadsetWorker(QThread):
    """
    Sucht im Hintergrund nach einer per USB angeschlossenen Brille.

    Warum ein eigener Thread: der Teil ueber sysfs ist zwar sofort fertig,
    der anschliessende ``adb devices``-Aufruf kann aber Sekunden brauchen —
    adb startet dabei ggf. erst seinen Daemon. Im GUI-Thread wuerde das
    Fenster genau so lange haengen, und zwar alle paar Sekunden erneut.
    """
    result_signal = QtSignal(dict)

    def run(self):
        try:
            info = usbhs.scan()
            # Gleich mitnehmen: laeuft das WiVRn-Dashboard? Das ist ein
            # pgrep-Aufruf, der im GUI-Thread nichts verloren hat, und der
            # Tooltip des USB-Hakens haengt davon ab.
            info["dashboard_running"] = wivrn_dash.dashboard_is_running()
            self.result_signal.emit(info)
        except Exception as exc:  # noqa: BLE001 — Anzeige darf nie abstuerzen
            log.debug("USB-Erkennung fehlgeschlagen: %s", exc)
            self.result_signal.emit({"devices": [], "headset": None,
                                     "state": "none", "adb_state": "",
                                     "dashboard_running": False,
                                     "profile": usbhs.profile_for(None)})


# ------------------------------------------------------------------------- #
#  Das Mixin
# ------------------------------------------------------------------------- #
class DashboardMixin:
    """Headset-, USB- und APK-Logik des Dashboards (siehe Modulkopf)."""

    # ------------------------------------------------------------------ #
    #  Diagnose: Logdatei                                                 #
    # ------------------------------------------------------------------ #
    # ------------------------------------------------------------------ #
    #  Auto-Connect per USB (WiVRn-Dashboard-Einstellung)                 #
    # ------------------------------------------------------------------ #
    def load_usb_autoconnect(self):
        """
        Zustand aus wivrn-dashboard.conf uebernehmen. Bewusst NICHT aus
        unserer eigenen Konfiguration: die Datei des Dashboards ist die
        Wahrheit — der Nutzer kann die Option ja auch dort umstellen.
        """
        self.ui.check_usb_autoconnect.blockSignals(True)
        self.ui.check_usb_autoconnect.setChecked(wivrn_dash.get_auto_connect_usb())
        self.ui.check_usb_autoconnect.blockSignals(False)
        self._update_usb_tooltip()

    def _update_usb_tooltip(self, running=None):
        """
        Tooltip des Hakens "Automatisch per USB verbinden".

        Laeuft das WiVRn-Dashboard gerade, wird der Hinweis angehaengt, dass
        es seine Einstellungen beim Beenden zurueckschreibt und diese
        Aenderung damit wieder kassieren kann. Frueher stand das als
        dauerhafte gelbe Zeile im Dashboard — fuer einen Sonderfall zu viel
        Platz. Im Tooltip steht es genau dort, wo man ohnehin hinschaut,
        bevor man den Haken setzt.

        ``running=None`` heisst "selbst nachsehen". Der Aufrufer kann das
        Ergebnis auch mitgeben, wenn er es (etwa aus dem Hintergrund-Thread)
        schon hat — dann laeuft hier kein zweites pgrep.
        """
        if running is None:
            running = wivrn_dash.dashboard_is_running()
        tip = f'{tr("streaming_usb_autoconnect_tip")}\n\n{tr("streaming_usb_autoconnect_self")}'
        if running:
            # Der uebersetzte Text bringt sein Warnzeichen selbst mit.
            tip = f"{tip}\n\n{tr('streaming_usb_dashboard_running')}"
        self.ui.check_usb_autoconnect.setToolTip(tip)

    def on_usb_autoconnect_toggled(self, checked):
        """Schreibt die Option direkt in die Dashboard-Konfiguration."""
        if not wivrn_dash.set_auto_connect_usb(checked):
            # Zurueckstellen, damit der Haken nicht etwas anzeigt, was nicht
            # gespeichert wurde.
            self.ui.check_usb_autoconnect.blockSignals(True)
            self.ui.check_usb_autoconnect.setChecked(not checked)
            self.ui.check_usb_autoconnect.blockSignals(False)
            QMessageBox.warning(self, tr("streaming_usb_autoconnect"),
                                tr("streaming_usb_write_failed").format(
                                    path=wivrn_dash.dashboard_config_file()))
            return
        self._update_usb_tooltip()

    # ------------------------------------------------------------------ #
    #  USB-Ampel: haengt eine Brille am Kabel — und wuerde sie verbinden?  #
    # ------------------------------------------------------------------ #
    def check_usb_headset(self):
        """
        Startet einen Erkennungslauf im Hintergrund. Laeuft noch einer, wird
        NICHT nachgelegt — sonst stapeln sich bei langsamem adb die Threads.
        """
        if self._usb_worker is not None and self._usb_worker.isRunning():
            return
        self._usb_worker = UsbHeadsetWorker()
        self._usb_worker.result_signal.connect(self._on_usb_scan_done)
        self._usb_worker.start()

    def _on_usb_scan_done(self, info):
        self._render_usb_state(info)
        self._maybe_auto_connect_usb(info)

    def _maybe_auto_connect_usb(self, info):
        """
        "Automatisch per USB verbinden" — und zwar wirklich.

        ----------------------------------------------------------------------
        Warum das hier stehen MUSS
        ----------------------------------------------------------------------
        Der Haken schreibt die Option in wivrn-dashboard.conf. Gelesen und
        AUSGEFUEHRT wird sie aber vom WiVRn-Dashboard: das pollt adb, und
        sobald eine Brille am Kabel auftaucht, legt es den Tunnel und
        schickt den Intent. Wer Yakuda Connect statt des Dashboards
        benutzt — also der Normalfall — hatte damit einen Haken, der eine
        Einstellung setzt, die niemand ausfuehrt. Man musste trotzdem zum
        PC laufen und klicken.

        Also pollen wir selbst. Den Takt gibt es schon: ``usb_poll_timer``
        ruft alle vier Sekunden ``check_usb_headset()``, dessen Ergebnis
        hier landet.

        ----------------------------------------------------------------------
        Warum "einmal pro Ansteckvorgang" und nicht "solange bereit"
        ----------------------------------------------------------------------
        ``_usb_auto_armed`` ist eine Kante, kein Zustand. Wuerde bei jedem
        Durchlauf verbunden, solange die Brille bereit ist, dann:

          * feuerte alle vier Sekunden ein Intent, auch mitten im Spielen,
          * und ein absichtliches "Trennen" waere nach vier Sekunden wieder
            rueckgaengig gemacht — der Nutzer kaeme gegen sein eigenes
            Programm nicht an.

        Scharf wird die Kante erst wieder, wenn die Brille verschwindet
        (Kabel ab, adb weg). Genau das ist die Geste, die "ich will
        verbinden" bedeutet.
        """
        if not info or not self.ui.check_usb_autoconnect.isChecked():
            return

        if info.get("state") != "ready":
            # Kabel ab oder adb nicht bereit: Kante fuer das naechste
            # Anstecken scharf machen.
            self._usb_auto_armed = True
            return

        if not self._usb_auto_armed:
            return

        # Laeuft das offizielle Dashboard, macht es dasselbe. Zwei Intents
        # schaden zwar nicht, aber doppelte Arbeit an einer Brille, die
        # gerade ohnehin beschaeftigt ist, ist unnoetig.
        if wivrn_dash.dashboard_is_running():
            return

        # Ohne Server waere der Tunnel sinnlos — die Brille landete in einem
        # Verbindungsversuch ins Leere. Die Kante bleibt scharf: wird der
        # Server gleich gestartet, greift der naechste Durchlauf.
        if not wivrn_server.is_running(self.server_process):
            return

        if self._connect_worker is not None and self._connect_worker.isRunning():
            return

        if self.is_headset_connected():
            # Schon in VR. Nichts zu tun — aber die Kante entschaerfen,
            # damit nach dem Trennen nicht sofort nachgefeuert wird.
            self._usb_auto_armed = False
            return

        self._usb_auto_armed = False
        log.info("Auto-Connect: Brille am Kabel erkannt, verbinde selbst")
        self._set_usb_notice(tr("usb_auto_connecting"), "#88c0d0",
                             seconds=UsbConnectWorker.DEADLINE + 10)
        self.connect_usb_headset()

    def _render_usb_state(self, info):
        """
        Zeichnet die kompakte USB-Zeile unter den gekoppelten Headsets.

        Sichtbar wird sie NUR, wenn es etwas zu tun gibt: Kabel steckt, aber
        WiVRn kaeme per adb nicht dran. Laeuft alles (gruen) oder haengt gar
        nichts am Kabel (grau), bleibt die Zeile weg — dass eine Brille per
        USB da ist, steht dann schon als "· USB" an ihrem Listeneintrag.

        Bewusst getrennt vom Scan: nach einem Sprachwechsel wird nur neu
        gezeichnet, ohne erneut zu suchen — dafuer merkt sich diese Methode
        den zuletzt gezeichneten Zustand.
        """
        vorher = self._usb_device_names()
        if info:
            self._usb_last_info = info

        info = self._usb_last_info
        state = (info or {}).get("state", "none")
        headset = (info or {}).get("headset") or {}
        name = headset.get("name", "")

        if state == "unauthorized":
            color, text = "#ebcb8b", tr("usb_state_unauthorized").format(name=name)
        elif state == "usb_only":
            color, text = "#ebcb8b", tr("usb_state_usb_only").format(name=name)
        elif state == "no_adb":
            color, text = "#ebcb8b", tr("usb_state_no_adb").format(name=name)
        elif state == "ready":
            color, text = "#a3be8c", ""
        else:
            color, text = "#4c566a", ""

        # Eine frische Rueckmeldung des Verbinden-Knopfes hat Vorrang vor der
        # Dauer-Anzeige: sie ist die Antwort auf einen Klick, der gerade
        # passiert ist.
        notice_text, notice_color, notice_until = self._usb_notice
        if notice_text and time.monotonic() < notice_until:
            color, text = notice_color, notice_text
        elif notice_text:
            self._usb_notice = ("", "", 0.0)

        # Klemmt adb, einmal genauer nachsehen — vor allem, OB seit dem
        # letzten funktionierenden Handshake ein Paketupdate lief. Genau das
        # ist die haeufigste Erklaerung fuer "gestern ging es noch", und sie
        # gehoert in die Meldung statt in ein Forum.
        problem = state in ("unauthorized", "usb_only", "no_adb")
        if problem and self._adb_updated is None:
            self._start_adb_probe()
        elif state == "ready":
            self._adb_updated = None          # naechstes Problem neu bewerten
            self._note_adb_success()

        # WiVRn-Version Brille <-> PC: einmal pro angesteckter Brille
        # vergleichen. Passt sie nicht, wird die sonst unsichtbare gruene
        # Zeile gelb und sagt, was zu tun ist.
        if state == "ready":
            if self._wivrn_ver_state is None:
                self._start_wivrn_version_check()
            mismatch = self._wivrn_ver_state
            if mismatch and not text:
                color = "#ebcb8b"
                text = tr("usb_state_version_mismatch").format(
                    client=mismatch[0], server=mismatch[1])
        else:
            self._wivrn_ver_state = None      # neu ansteckt = neu pruefen

        if problem and self._adb_updated:
            old_ver, new_ver = self._adb_updated
            text = f"{text} {tr('usb_state_after_update').format(old=old_ver, new=new_ver)}"
        if problem and self._adb_mtp_busy:
            text = f"{text} {tr('usb_state_mtp_busy')}"

        self.ui.lbl_usb_led.setStyleSheet(f"color:{color}; font-size:14px;")
        self.ui.lbl_usb_state.setText(text)
        self.ui.usb_state_widget.setVisible(bool(text))

        # Der Reparatur-Knopf gehoert nur neben ein echtes Problem. Bei
        # "kein adb installiert" waere er sinnlos — da fehlt ein Paket, das
        # kein Serverneustart herbeizaubert.
        fixable = problem and state != "no_adb" and not self._doctor_running()
        self.ui.btn_usb_repair.setVisible(bool(text) and problem and state != "no_adb")
        self.ui.btn_usb_repair.setEnabled(fixable)

        self._update_connect_button()

        self._apply_refresh_profile((info or {}).get("profile"))
        # Tooltip des USB-Hakens aktuell halten (Dashboard kann zwischendurch
        # gestartet oder beendet worden sein).
        if info is not None and "dashboard_running" in info:
            self._update_usb_tooltip(info["dashboard_running"])

        # Liste nur dann neu einlesen, wenn sich am Kabel wirklich etwas
        # geaendert hat — sonst liefe alle vier Sekunden ein wivrnctl-Aufruf
        # ins Leere.
        if self._usb_device_names() != vorher:
            self.refresh_headset_list()

    def _usb_device_names(self):
        """Namen der aktuell per USB erkannten Brillen (klein geschrieben)."""
        info = self._usb_last_info or {}
        return tuple(sorted(
            (d.get("name") or "").strip().lower()
            for d in info.get("devices", []) if d.get("name")))

    def _apply_refresh_profile(self, profile):
        """
        Zeigt, welche Bildwiederholraten die erkannte Brille beherrscht.

        Bewusst nur eine Anzeige: Die Rate laesst sich vom PC aus gar nicht
        setzen — WiVRns Server-Konfiguration hat dafuer keinen Schluessel,
        der Client im Headset bestimmt sie (siehe core/config_manager.py).
        Frueher stand hier ein Auswahlfeld, dessen Wert wirkungslos in WiVRns
        config.json landete.
        """
        rates = (profile or {}).get("rates") or usbhs.ALL_RATES
        model = (profile or {}).get("model", "")

        if model:
            self.ui.lbl_refresh_value.setText(
                tr("refresh_supported").format(
                    name=model,
                    rates=", ".join(f"{r}" for r in rates)))
        else:
            self.ui.lbl_refresh_value.setText(tr("refresh_no_headset"))
        self.ui.lbl_refresh_hint.setText(tr("refresh_where"))

    # ------------------------------------------------------------------ #
    #  WiVRn-APK: herunterladen und/oder installieren                     #
    # ------------------------------------------------------------------ #
    def start_apk_install(self):
        """Passende WiVRn-APK laden und per adb auf die Brille spielen."""
        self._start_apk_worker(mode="install")

    def start_apk_download(self):
        """
        Nur herunterladen, nicht installieren.

        Der Ordner wird gefragt statt festgelegt: Wer die APK per SideQuest
        aufspielt, will sie meist woanders haben als im Download-Ordner, und
        ein stillschweigend abgelegter Download ist eine Datei, die man
        hinterher sucht.
        """
        if self._apk_worker and self._apk_worker.isRunning():
            return
        start_dir = self._download_dir()
        target = QFileDialog.getExistingDirectory(
            self, tr("apk_choose_folder"), start_dir)
        if not target:
            return
        self._start_apk_worker(mode="download", target_dir=target)

    def _download_dir(self):
        """
        Der lokalisierte Download-Ordner des Nutzers.

        ``xdg-user-dir`` kennt ihn auch, wenn er "Téléchargements" heisst —
        ein fest eingebautes "~/Downloads" waere auf jedem nicht-englischen
        System daneben. Faellt der Aufruf aus, tut es das Heimatverzeichnis.
        """
        path = proc.output_of(["xdg-user-dir", "DOWNLOAD"],
                              timeout=proc.DEFAULT_TIMEOUT).strip()
        if path and os.path.isdir(path):
            return path
        return os.path.expanduser("~")

    def _start_apk_worker(self, mode, target_dir=None):
        if self._apk_worker and self._apk_worker.isRunning():
            return

        # adb braucht nur der Installationsweg. Beim reinen Download waere
        # es albern, deswegen abzulehnen — die Datei landet ja bloss im
        # Dateisystem.
        if mode == "install" and not shutil.which("adb"):
            self.ui.lbl_apk_status.setText(tr("apk_no_adb"))
            self.ui.lbl_apk_status.setStyleSheet(
                "color: #ebcb8b; font-size: 11px; font-weight: bold;")
            return

        self.ui.btn_apk_install.setEnabled(False)
        self.ui.btn_apk_download.setEnabled(False)
        self.ui.btn_apk_cancel.setVisible(True)
        self.ui.lbl_apk_warn.setVisible(False)
        self.ui.lbl_apk_status.setText(tr("apk_starting"))
        self.ui.lbl_apk_status.setStyleSheet("color: #88c0d0; font-size: 11px;")

        self._apk_worker = ApkWorker(mode=mode, target_dir=target_dir)
        self._apk_worker.status_signal.connect(self.ui.lbl_apk_status.setText)
        self._apk_worker.warning_signal.connect(self._on_apk_warning)
        self._apk_worker.saved_signal.connect(self._on_apk_saved)
        self._apk_worker.finished_signal.connect(self._on_apk_finished)
        self._release_worker_on_finish("_apk_worker")
        self._apk_worker.start()

    def cancel_apk_install(self):
        if self._apk_worker:
            self._apk_worker.cancel()

    def _on_apk_warning(self, text):
        """Versions-Warnung — bleibt stehen, bis der naechste Lauf beginnt."""
        self.ui.lbl_apk_warn.setText(text)
        self.ui.lbl_apk_warn.setVisible(True)

    def _on_apk_saved(self, path):
        """
        Nach dem reinen Download den Ordner im Dateimanager oeffnen.

        Geoeffnet wird der ORDNER, nicht die Datei: ein Doppelklick auf eine
        APK unter Linux fuehrt bestenfalls zu einem Archivprogramm.
        """
        folder = os.path.dirname(path)
        if os.path.isdir(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _on_apk_finished(self, success):
        if success:
            self._wivrn_ver_state = None    # neue APK drauf -> neu vergleichen
        self.ui.btn_apk_install.setEnabled(True)
        self.ui.btn_apk_download.setEnabled(True)
        self.ui.btn_apk_cancel.setVisible(False)
        if success:
            self.ui.lbl_apk_status.setStyleSheet(
                "color: #a3be8c; font-size: 11px; font-weight: bold;")
        else:
            self.ui.lbl_apk_status.setStyleSheet(
                "color: #bf616a; font-size: 11px;")

    def refresh_headset_list(self):
        """
        Gekoppelte Headsets auflisten. Haengt eines davon gerade am USB-Kabel,
        bekommt sein Eintrag ein "· USB" angehaengt — die Information steht
        damit direkt am Geraet statt in einer eigenen Zeile weiter oben.

        Jeder ECHTE Eintrag traegt seine wivrnctl-Nummer als ``Qt.UserRole``
        bei sich. Frueher wurde dafuer der angezeigte Text durchsucht ("steht
        'Keine' drin? Dann ist es ein Platzhalter"), was nur auf Deutsch
        funktionierte: auf Englisch heisst der Platzhalter anders, und ein
        Klick auf "Headset loeschen" haette versucht, ihn zu entkoppeln.
        """
        self.ui.list_headsets.clear()
        if not wivrn_server.is_running(self.server_process):
            self.ui.list_headsets.addItem(tr("dashboard_no_server"))
            self._update_connect_button()
            return

        res = proc.run(["wivrnctl", "list-paired"], timeout=proc.DEFAULT_TIMEOUT)
        if res.returncode == 0:
            for line in (res.stdout or "").strip().split("\n"):
                line = line.strip()
                if not line or "Headset name" in line:
                    continue
                item = QListWidgetItem(self._tag_usb(line))
                match = re.match(r"^(\d+)", line)
                if match:
                    item.setData(Qt.UserRole, match.group(1))
                self.ui.list_headsets.addItem(item)

        if self.ui.list_headsets.count() == 0:
            self.ui.list_headsets.addItem(tr("dashboard_no_paired"))

        self._update_connect_button()

    def _tag_usb(self, line):
        """
        Haengt "· USB" an, wenn der Name des Listeneintrags zu einer per USB
        erkannten Brille passt.

        Verglichen wird ueber den Namen, nicht ueber die Reihenfolge: sind
        mehrere Brillen gekoppelt, darf die Markierung nicht an der falschen
        landen. Passt kein Name, bleibt der Eintrag unveraendert — dann sagt
        die Statuszeile unter der Liste, was am Kabel haengt.
        """
        low = line.lower()
        for name in self._usb_device_names():
            if name and name in low:
                return f"{line}   · USB"
        return line

    def remove_selected_headset(self):
        item = self.ui.list_headsets.currentItem()
        headset_id = item.data(Qt.UserRole) if item else None
        if not headset_id:
            # Platzhalterzeile ("kein Server", "keine gekoppelten Headsets")
            # oder nichts markiert — beides ist nichts zum Entkoppeln.
            return
        if QMessageBox.question(self, tr("headset_unpair_title"),
                                tr("headset_unpair_text").format(name=item.text()),
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            proc.run(["wivrnctl", "unpair", headset_id], timeout=proc.DEFAULT_TIMEOUT)
            self.refresh_headset_list()

    # ------------------------------------------------------------------ #
    #  Verbinden ueber das Kabel                                          #
    # ------------------------------------------------------------------ #
    def _update_connect_button(self):
        """
        Der Verbinden-Knopf ist nur dann aktiv, wenn er auch etwas bewirken
        kann: Brille per adb erreichbar UND Server laeuft.

        Der Tooltip nennt den jeweils fehlenden Teil. Ein ausgegrauter Knopf
        ohne Begruendung ist die haeufigste Ursache fuer "das Programm macht
        nichts" — hier steht beim Druebergehen, woran es liegt.

        Ueber WLAN gibt es diesen Knopf bewusst nicht: dort kann der PC die
        Verbindung gar nicht ausloesen, da klickt immer die Brille.
        """
        info = self._usb_last_info or {}
        usb_ready = info.get("state") == "ready"
        server_running = wivrn_server.is_running(self.server_process)
        busy = self._connect_worker is not None and self._connect_worker.isRunning()

        # Waehrend eines laufenden Versuchs wird der Knopf zum
        # Abbrechen-Knopf, statt ausgegraut dazustehen: der Versuch darf bis
        # zu anderthalb Minuten dauern, und so lange soll niemand einem
        # toten Bedienelement zusehen.
        if busy:
            self.ui.btn_connect_headset.setText(tr("usb_connect_cancel_btn"))
            self.ui.btn_connect_headset.setEnabled(True)
            self.ui.btn_connect_headset.setToolTip(tr("usb_connect_cancel_tip"))
            return

        self.ui.btn_connect_headset.setText(tr("dashboard_connect_btn"))
        self.ui.btn_connect_headset.setEnabled(bool(usb_ready and server_running))

        if not usb_ready:
            tip = tr("dashboard_connect_tip_nousb")
        elif not server_running:
            tip = tr("dashboard_connect_tip_noserver")
        else:
            tip = tr("dashboard_connect_tip")
        self.ui.btn_connect_headset.setToolTip(tip)

    # ------------------------------------------------------------------ #
    #  adb-Handshake: Diagnose und Reparatur                              #
    # ------------------------------------------------------------------ #
    def _doctor_running(self):
        return self._doctor_worker is not None and self._doctor_worker.isRunning()

    def _start_adb_probe(self):
        """
        Einmalige Nachschau, sobald adb klemmt. Aendert nichts am System.

        Das Ergebnis wird gemerkt (``_adb_updated``), damit die Zeile alle
        vier Sekunden neu gezeichnet werden kann, ohne jedes Mal den
        Paketmanager zu befragen.
        """
        if self._doctor_running():
            return
        self._adb_updated = ()        # "laeuft" — verhindert Doppelstarts
        self._doctor_worker = AdbDoctorWorker(mode="probe")
        self._doctor_worker.probe_signal.connect(self._on_adb_probe_done)
        self._release_worker_on_finish("_doctor_worker")
        self._doctor_worker.start()

    def _start_wivrn_version_check(self):
        """Startet den Versionsvergleich (siehe ``WivrnVersionWorker``)."""
        if self._wivrn_ver_worker is not None and self._wivrn_ver_worker.isRunning():
            return
        self._wivrn_ver_state = ()      # "laeuft" — verhindert Doppelstarts
        self._wivrn_ver_worker = WivrnVersionWorker()
        self._wivrn_ver_worker.result_signal.connect(self._on_wivrn_version_done)
        self._release_worker_on_finish("_wivrn_ver_worker")
        self._wivrn_ver_worker.start()

    def _on_wivrn_version_done(self, res):
        # Nur bei einem SICHEREN "passt nicht" warnen. Unbekannt (None) heisst
        # schweigen — lieber keine Warnung als eine falsche.
        if res.get("match") is False:
            log.warning("WiVRn-Version passt nicht: Brille %s, PC %s",
                        res.get("client"), res.get("server"))
            self._wivrn_ver_state = (res.get("client"), res.get("server"))
        else:
            self._wivrn_ver_state = ()
        self._render_usb_state(None)

    def _on_adb_probe_done(self, info):
        self._adb_updated = tuple(info.get("updated") or ())
        self._adb_mtp_busy = bool(info.get("mtp_busy"))
        self._adb_probe_state = info.get("state", "")
        self._render_usb_state(None)

    def _note_adb_success(self):
        """
        Merkt sich nach einem gelungenen Handshake die Paketversion — die
        Vergleichsgroesse fuer "seit dem letzten Mal wurde aktualisiert".

        Nur einmal pro Sitzung: der Aufruf kostet einen Paketmanager-Aufruf,
        und die Version aendert sich nicht, waehrend die App laeuft.
        """
        if self._adb_success_noted or self._doctor_running():
            return
        self._adb_success_noted = True
        try:
            adbdoc.remember_success()
        except Exception as exc:
            log.debug("_note_adb_success: ignoriert — %s", exc)

    def repair_adb_handshake(self):
        """
        Startet die Reparatur: adb-Server neu, bei Rechteproblemen zusaetzlich
        die udev-Regeln neu laden.

        Vorher wird gefragt, wenn eine Passwortabfrage ansteht — ein
        unangekuendigter Polkit-Dialog nach einem Klick auf "Reparieren"
        sieht aus, als wollte das Programm etwas Grosses tun.
        """
        if self._doctor_running():
            return

        state = getattr(self, "_adb_probe_state", "")
        with_udev = state == adbdoc.NO_PERMISSION

        question = tr("adb_fix_confirm_udev") if with_udev else tr("adb_fix_confirm")
        if QMessageBox.question(self, tr("adb_fix_btn"), question,
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        self.ui.btn_usb_repair.setEnabled(False)
        self._set_usb_notice(tr("adb_fix_running"), "#88c0d0", seconds=60)

        self._doctor_worker = AdbDoctorWorker(mode="repair", state=state,
                                              with_udev=with_udev)
        self._doctor_worker.repair_signal.connect(self._on_adb_repair_done)
        self._release_worker_on_finish("_doctor_worker")
        self._doctor_worker.start()

    def _on_adb_repair_done(self, ok, steps):
        # Nach der Reparatur ist die Vorgeschichte hinfaellig: neu bewerten.
        self._adb_updated = None
        self._adb_success_noted = False

        detail = "\n".join(f"• {tr(key)}" for key in steps)
        if ok:
            self._set_usb_notice(tr("adb_fix_ok"), "#a3be8c")
            QMessageBox.information(self, tr("adb_fix_btn"),
                                    f"{tr('adb_fix_ok')}\n\n{detail}")
        else:
            self._set_usb_notice(tr("adb_fix_failed_short"), "#ebcb8b")
            QMessageBox.warning(self, tr("adb_fix_btn"),
                                f"{tr('adb_fix_failed')}\n\n{detail}")

        # Frisch nachsehen statt auf den naechsten Vier-Sekunden-Takt warten.
        self.check_usb_headset()
        self.refresh_headset_list()

    def connect_usb_headset(self):
        """
        Verbindung ueber das Kabel starten — oder einen laufenden Versuch
        abbrechen.

        Derselbe Knopf fuer beides, weil der Versuch bis zu anderthalb
        Minuten laeuft: waehrenddessen muss man ihn abwuergen koennen, ohne
        auf ein zweites Bedienelement zu zielen, das es sonst nie gibt.
        """
        if self._connect_worker is not None and self._connect_worker.isRunning():
            self._connect_worker.cancel()
            # Wer abbricht, will nicht, dass der Auto-Connect vier Sekunden
            # spaeter von vorn anfaengt.
            self._usb_auto_armed = False
            self._set_usb_notice(tr("usb_connect_cancelling"), "#ebcb8b", seconds=5)
            return

        self._set_usb_notice(tr("usb_connect_running"), "#88c0d0",
                             seconds=UsbConnectWorker.DEADLINE + 10)

        self._connect_worker = UsbConnectWorker()
        self._connect_worker.result_signal.connect(self._on_usb_connect_done)
        self._connect_worker.status_signal.connect(self._on_usb_connect_status)
        self._release_worker_on_finish("_connect_worker")
        self._connect_worker.start()
        self._update_connect_button()

    def _on_usb_connect_status(self, key):
        """
        Zwischenstand aus dem Worker. Der Hinweis auf die USB-Optionen der
        Brille steht bewusst hier und nicht erst in der Fehlermeldung: dort
        kaeme er zu spaet, denn genau dieses Umschalten IST die Loesung,
        solange der Versuch noch laeuft.
        """
        self._set_usb_notice(tr(key), "#ebcb8b",
                             seconds=UsbConnectWorker.DEADLINE + 10)

    def _on_usb_connect_done(self, ok, detail, package):
        if ok:
            # Kein Meldungsfenster bei Erfolg: der Nutzer setzt jetzt die
            # Brille auf und will keinen Dialog wegklicken muessen.
            if detail == "uncertain":
                # Die adb-Shell kam nicht zurueck, der Intent ist aber raus.
                # Vorsichtiger formulieren statt Erfolg zu behaupten —
                # entscheiden kann das nur, wer die Brille aufhat.
                self._set_usb_notice(tr("usb_connect_probably"), "#a3be8c", seconds=20)
            elif package:
                self._set_usb_notice(tr("usb_connect_ok").format(package=package), "#a3be8c")
            else:
                self._set_usb_notice(tr("usb_connect_ok_generic"), "#a3be8c")
            QTimer.singleShot(1500, self.refresh_headset_list)

        elif detail == "cancelled":
            self._set_usb_notice(tr("usb_connect_cancelled"), "#4c566a", seconds=5)

        elif detail == "no_device":
            self._set_usb_notice(tr("usb_connect_no_device"), "#bf616a")

        elif "unable to resolve intent" in (detail or "").lower():
            # Jetzt ist die Aussage belastbar: es wurde jeder bekannte
            # Paketname UND der Weg ohne Paketangabe probiert. Wenn Android
            # das Schema niemandem zuordnen kann, fehlt die App wirklich.
            self._set_usb_notice(tr("usb_connect_no_package_short"), "#bf616a")
            QMessageBox.information(self, tr("dashboard_connect_btn"),
                                    tr("usb_connect_no_package"))

        elif "timeout" in (detail or "").lower():
            # Der PICO-Fall. Die Fehlermeldung nennt den Handgriff, der
            # hilft, statt nur "adb meldet: timeout" zu wiederholen.
            self._set_usb_notice(tr("usb_connect_timeout_short"), "#ebcb8b")
            QMessageBox.information(self, tr("dashboard_connect_btn"),
                                    tr("usb_connect_timeout"))

        else:
            self._set_usb_notice(tr("usb_connect_failed_short"), "#bf616a")
            QMessageBox.warning(self, tr("dashboard_connect_btn"),
                                tr("usb_connect_failed").format(err=detail or "?"))

        self._update_connect_button()

    def _set_usb_notice(self, text, color, seconds=8):
        """
        Kurzmeldung in die USB-Zeile schreiben.

        Mit Ablaufzeit, weil ``_render_usb_state()`` die Zeile alle vier
        Sekunden neu zeichnet: ohne Vorrang waere die Meldung sofort weg,
        ohne Ablauf bliebe sie fuer immer stehen.
        """
        self._usb_notice = (text, color, time.monotonic() + seconds)
        self._render_usb_state(None)

    def disconnect_current_headset(self):
        """
        Laufende Verbindung trennen.

        Entschaerft zusaetzlich die Auto-Connect-Kante: wer trennt, will
        getrennt sein. Ohne das waere die Brille vier Sekunden spaeter
        wieder verbunden, und der Nutzer kaeme gegen sein eigenes Programm
        nicht an. Scharf wird sie erst wieder, wenn das Kabel ab war.
        """
        self._usb_auto_armed = False
        proc.run(["wivrnctl", "disconnect"], timeout=proc.DEFAULT_TIMEOUT)
        self.refresh_headset_list()

    def toggle_pairing_mode(self, checked):
        """
        Kopplungsmodus an/aus. Die PIN kommt ueber einen Worker herein.

        Hier stand frueher ein ``stdout.readline()`` direkt im GUI-Thread.
        Das las genau eine Zeile von ``wivrnctl pair`` — und bis die kam,
        reagierte das Fenster nicht. Auf einem gesunden System sind das
        Millisekunden, aber sobald wivrnctl haengt (Server gerade beim Start,
        Avahi noch nicht da), friert die ganze App ein, ohne dass irgendetwas
        darauf hindeutet.
        """
        if checked:
            if not wivrn_server.is_running(self.server_process):
                self.ui.chk_pairing.setChecked(False)
                return
            self.ui.txt_code.setText(tr("pairing_waiting"))
            self.pairing_process = subprocess.Popen(
                ["wivrnctl", "pair"], stdout=subprocess.PIPE, text=True)
            self._pin_worker = PairingPinWorker(self.pairing_process)
            self._pin_worker.pin_signal.connect(self._on_pairing_pin)
            self._pin_worker.start()
        else:
            if self.pairing_process:
                self.pairing_process.terminate()
                self.pairing_process = None
            self.ui.txt_code.setText("")

    def _on_pairing_pin(self, pin):
        # Zwischenzeitlich abgeschaltet? Dann die PIN eines beendeten
        # Vorgangs nicht mehr anzeigen.
        if not self.ui.chk_pairing.isChecked():
            return
        self.ui.txt_code.setText(pin or tr("pairing_active"))

