import subprocess
import shutil
import time
from PySide6.QtCore import QThread, Signal

from logging_setup import get_logger

log = get_logger("install_worker")


# Terminalemulatoren nach Priorität — erster gefundener wird benutzt.
# Jeder Eintrag: (binary, argument_um_befehl_auszuführen)
# Die meisten benutzen "-e", kitty/foot benutzen direkt den Befehl ohne Flag.
TERMINAL_CANDIDATES = [
    # KDE
    ("konsole",      ["-e"]),
    # GNOME / GTK
    ("gnome-terminal", ["--"]),
    # Hyprland / wlroots
    ("kitty",        []),
    ("foot",         []),
    ("alacritty",    ["-e"]),
    ("wezterm",      ["start", "--"]),
    # XFCE
    ("xfce4-terminal", ["-e"]),
    # Weitere verbreitete
    ("xterm",        ["-e"]),
    ("lxterminal",   ["-e"]),
    ("tilix",        ["-e"]),
    ("urxvt",        ["-e"]),
]

def find_terminal():
    """Gibt (binary, exec_flag_list) des ersten verfügbaren Terminals zurück."""
    for binary, flags in TERMINAL_CANDIDATES:
        if shutil.which(binary):
            return binary, flags
    return None, None


class RemoveWorker(QThread):
    """
    Entfernt Pakete per yay/paru im Terminal (Tools-Tab, 'Löschen'-Knopf).

    Gleiches Muster wie InstallWorker: das Terminal öffnet sich, damit der
    Nutzer das sudo-Passwort eingeben und die Paketliste sehen kann.
    '-Rns' räumt dabei nicht mehr benötigte Abhängigkeiten und die
    System-Konfiguration des Pakets mit weg (~/.config bleibt unberührt).
    """
    status_signal = Signal(str)
    finished_signal = Signal(bool)

    def __init__(self, packages, helper="yay"):
        super().__init__()
        self.packages = packages
        self.helper = helper if helper in ("yay", "paru") else "yay"

    def run(self):
        if not self.packages:
            self.finished_signal.emit(True)
            return

        terminal, exec_flags = find_terminal()
        if terminal is None:
            self.status_signal.emit("Fehler: Kein unterstütztes Terminal gefunden (konsole, kitty, foot, alacritty ...)!")
            self.finished_signal.emit(False)
            return

        success = True
        for pkg in self.packages:
            self.status_signal.emit(f"Entferne Paket: {pkg}...")
            bash_cmd = (
                f"echo '=== Entferne {pkg} mit {self.helper} ==='; "
                f"{self.helper} -Rns {pkg}; "
                f"echo ''; "
                f"echo 'Fertig. Dieses Fenster schließt sich gleich automatisch...'; "
                f"sleep 2"
            )
            cmd = [terminal] + exec_flags + ["bash", "-c", bash_cmd]
            try:
                process = subprocess.Popen(cmd)
                process.wait()
                if process.returncode != 0:
                    log.warning(f"Fehler oder Abbruch beim Entfernen von: {pkg} (Terminal: {terminal})")
                    success = False
            except Exception as e:
                log.warning(f"Fehler beim Öffnen von '{terminal}' für {pkg}: {e}")
                success = False
            time.sleep(0.5)

        self.finished_signal.emit(success)


class UpdateWorker(QThread):
    """Führt ein System-/Ökosystem-Update über die gewählte Methode im Terminal aus."""
    status_signal = Signal(str)
    finished_signal = Signal(bool)

    def __init__(self, method):
        super().__init__()
        self.method = method

    def run(self):
        terminal, exec_flags = find_terminal()
        if terminal is None:
            self.status_signal.emit("Fehler: Kein unterstütztes Terminal gefunden!")
            self.finished_signal.emit(False)
            return

        # Fedora-Paketliste aus programs ableiten, nicht fest verdrahten —
        # sonst vergisst man beim Ergaenzen eines Pakets das Update. Die
        # COPR-Komponenten (xrizer) gehoeren dazu: das Repo ist nach der
        # Installation dauerhaft aktiviert, ein 'dnf upgrade' aktualisiert es
        # also ganz normal mit.
        try:
            from programs import INSTALL_DNF, INSTALL_DNF_COPR
            names = [p for pkgs in INSTALL_DNF.values() for p in pkgs]
            names += [p for cfg in INSTALL_DNF_COPR.values() for p in cfg["pkgs"]]
            # Nur aktualisieren, was auch installiert ist. Wer die
            # COPR-Rueckfrage verneint hat, hat kein xrizer — 'dnf upgrade
            # xrizer' quittiert das mit einer Fehlermeldung, und die stuende
            # dann mitten in einem ansonsten erfolgreichen Update.
            installed = [p for p in names
                         if subprocess.run(["rpm", "-q", p],
                                           stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL,
                                           timeout=15).returncode == 0]
            dnf_pkgs = " ".join(installed or names)
        except Exception:
            dnf_pkgs = "wivrn opencomposite"

        cmds = {
            "yay":  "yay -Syu",
            "paru": "paru -Syu",
            # Nur die VR-Pakete anfassen, kein volles Systemupdate.
            # Wird normalerweise nicht erreicht: auf Fedora oeffnet der
            # Update-Knopf das Software-Center. Dies ist der Rueckfall, wenn
            # keines gefunden wird.
            "dnf":  f"sudo dnf upgrade --refresh {dnf_pkgs}",
        }
        update_cmd = cmds.get(self.method, "yay -Syu")
        self.status_signal.emit(f"Update läuft ({self.method}) ...")

        bash_cmd = (
            f"echo '=== System-Update ({self.method}) ==='; "
            f"{update_cmd}; "
            f"echo ''; "
            f"echo 'Fertig. Dieses Fenster schließt sich gleich automatisch...'; "
            f"sleep 2"
        )
        cmd = [terminal] + exec_flags + ["bash", "-c", bash_cmd]
        try:
            proc = subprocess.Popen(cmd)
            proc.wait()
            self.status_signal.emit("Update abgeschlossen.")
            self.finished_signal.emit(proc.returncode == 0)
        except Exception as e:
            self.status_signal.emit(f"Fehler beim Update: {e}")
            self.finished_signal.emit(False)


class InstallWorker(QThread):
    status_signal = Signal(str)
    finished_signal = Signal(bool)

    def __init__(self, packages, helper="yay", copr_map=None, ppa=""):
        super().__init__()
        self.packages = packages
        # 'flatpak' ist hier nur noch für den TOOLS-Tab erlaubt (ProtonPlus etc.),
        # die WiVRn-Runtime im Installations-Tab läuft ausschließlich nativ.
        self.helper = helper if helper in ("yay", "paru", "dnf", "apt", "flatpak") else "yay"
        # {paketname: copr-kennung} — nur für dnf. Steht ein Paket hier drin,
        # wird das COPR im selben Terminalfenster aktiviert, bevor installiert
        # wird. Der Nutzer muss also nichts mehr von Hand kopieren.
        self.copr_map = dict(copr_map or {})
        # PPA für apt-Systeme, z. B. 'ppa:lvra/wivrn'. Gleiche Idee wie copr_map,
        # nur gilt sie für den ganzen Durchlauf: eine PPA bringt alle Pakete mit.
        self.ppa = ppa or ""

    def build_bash_command(self, pkg, index, total_pkgs):
        """
        Die Befehlszeile, die im Terminalfenster laeuft.

        Bewusst als eigene Methode (statt inline in run()): so laesst sie sich
        im Test pruefen, ohne dass ein Terminal geoeffnet werden muss.
        """
        tail = ("echo ''; "
                "echo 'Fertig. Dieses Fenster schließt sich gleich automatisch...'; "
                "sleep 2")

        if self.helper == "flatpak":
            # remote-add zuerst: auf Mint ist Flathub eingerichtet, auf einem
            # nackten Debian nicht. '--if-not-exists' aendert nichts, wenn es
            # das Remote schon gibt.
            return (f"echo '=== Installiere {pkg} (Flatpak) ==='; "
                    f"flatpak remote-add --if-not-exists flathub "
                    f"https://flathub.org/repo/flathub.flatpakrepo; "
                    f"flatpak install -y flathub {pkg}; " + tail)

        if self.helper == "apt":
            ppa_cmd = ""
            if self.ppa:
                # 'add-apt-repository' steckt in software-properties-common —
                # auf einer schlanken Debian-Installation fehlt es. Es wird
                # deshalb bei Bedarf vorher nachgezogen.
                #
                # Auf Linux Mint ist ausserdem wichtig, dass genau dieses
                # Werkzeug benutzt wird: 'lsb_release -cs' liefert dort den
                # Mint-Namen (z. B. 'zena'), nicht den Ubuntu-Codenamen
                # ('noble'). Eine von Hand geschriebene sources-Zeile zeigte
                # damit ins Leere; add-apt-repository loest das selbst auf.
                ppa_cmd = (
                    f"echo '--- Aktiviere {self.ppa} ---'; "
                    f"command -v add-apt-repository >/dev/null || "
                    f"sudo apt-get install -y software-properties-common; "
                    f"sudo add-apt-repository -y {self.ppa}; "
                )
            return (f"echo '=== Installiere {pkg} ({index}/{total_pkgs}) mit apt ==='; "
                    f"{ppa_cmd}"
                    f"sudo apt-get update; "
                    f"sudo apt-get install -y {pkg}; " + tail)

        if self.helper == "dnf":
            copr = self.copr_map.get(pkg)
            copr_cmd = ""
            if copr:
                # 'dnf copr' steckt bei dnf4 im Plugin-Paket dnf-plugins-core,
                # bei dnf5 (Fedora 41+) ist es eingebaut. Schlaegt der erste
                # Versuch fehl, wird das Plugin nachinstalliert und ein zweites
                # Mal probiert — sonst saehe der Nutzer auf aelteren Systemen
                # wieder eine Fehlermeldung statt einer Installation.
                copr_cmd = (f"echo '--- Aktiviere COPR {copr} ---'; "
                            f"sudo dnf copr enable -y {copr} || {{ "
                            f"sudo dnf install -y dnf-plugins-core && "
                            f"sudo dnf copr enable -y {copr}; }}; ")
            return (f"echo '=== Installiere {pkg} ({index}/{total_pkgs}) mit dnf ==='; "
                    f"{copr_cmd}sudo dnf install -y {pkg}; " + tail)

        return (f"echo '=== Installiere {pkg} ({index}/{total_pkgs}) mit {self.helper} ==='; "
                f"{self.helper} -S {pkg}; " + tail)

    def run(self):
        if not self.packages:
            self.finished_signal.emit(True)
            return

        terminal, exec_flags = find_terminal()
        if terminal is None:
            self.status_signal.emit("Fehler: Kein unterstütztes Terminal gefunden (konsole, kitty, foot, alacritty ...)!")
            self.finished_signal.emit(False)
            return

        total_pkgs = len(self.packages)
        success = True

        for index, pkg in enumerate(self.packages, start=1):
            self.status_signal.emit(f"Installiere Paket {index} von {total_pkgs}: {pkg}...")

            bash_cmd = self.build_bash_command(pkg, index, total_pkgs)

            # Befehlsaufbau je nach Terminal-Syntax
            cmd = [terminal] + exec_flags + ["bash", "-c", bash_cmd]

            try:
                process = subprocess.Popen(cmd)
                process.wait()

                if process.returncode != 0:
                    log.warning(f"Fehler oder Abbruch bei Paket: {pkg} (Terminal: {terminal})")
                    success = False
            except Exception as e:
                log.warning(f"Fehler beim Öffnen von '{terminal}' für {pkg}: {e}")
                success = False

            time.sleep(0.5)

        if success:
            self.status_signal.emit("Alle ausgewählten Programme erfolgreich installiert!")
            self.finished_signal.emit(True)
        else:
            self.status_signal.emit("Installation abgeschlossen (einige Pakete wurden übersprungen oder abgebrochen).")
            self.finished_signal.emit(False)


# --------------------------------------------------------------------------- #
#  Selbst-Update von yakuda-connect
# --------------------------------------------------------------------------- #
# Quelle der Wahrheit für die Version ist self.APP_VERSION in core/main.py.
# Der Prüf-Worker liest genau diese Zeile aus der main.py auf GitHub und
# vergleicht sie mit der lokal laufenden Version. Der Update-Worker führt das
# vorhandene install.sh aus (das ist zugleich der Updater).
APP_RAW_MAIN_URL   = "https://raw.githubusercontent.com/yakuda-stack/yakuda-connect/main/core/main.py"
APP_INSTALL_SH_URL = "https://raw.githubusercontent.com/yakuda-stack/yakuda-connect/main/install.sh"


def _version_tuple(v):
    """'v1.2.3-alpha' -> (1, 2, 3). Nicht-Zahlen werden ignoriert."""
    import re
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums) if nums else ()


def is_remote_newer(local, remote):
    """
    True, wenn 'remote' eine neuere Version als 'local' ist.
    Erst numerischer Vergleich (1.0.7 > 1.0.6). Sind die Zahlen gleich, wird
    ein reiner Suffix-Unterschied (z. B. alpha -> beta) als Update gewertet.
    Lässt sich gar nichts parsen, gilt: ungleich == Update.
    """
    lt, rt = _version_tuple(local), _version_tuple(remote)
    if lt and rt:
        if rt != lt:
            return rt > lt
        return (remote or "").strip() != (local or "").strip()
    return (remote or "").strip() != (local or "").strip()


class AppUpdateCheckWorker(QThread):
    """Prüft im Hintergrund, ob auf GitHub eine neuere yakuda-connect-Version liegt."""
    # (update_verfügbar: bool, remote_version: str)
    result_signal = Signal(bool, str)

    def __init__(self, local_version):
        super().__init__()
        self.local_version = local_version

    def run(self):
        import re
        import urllib.request
        try:
            req = urllib.request.Request(
                APP_RAW_MAIN_URL, headers={"User-Agent": "yakuda-connect"})
            with urllib.request.urlopen(req, timeout=10) as r:
                text = r.read().decode("utf-8", "ignore")
            m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
            if not m:
                self.result_signal.emit(False, "")
                return
            remote = m.group(1).strip()
            self.result_signal.emit(is_remote_newer(self.local_version, remote), remote)
        except Exception:
            # Kein Netz / GitHub nicht erreichbar -> still, kein Pfeil.
            self.result_signal.emit(False, "")


class GamesDbWorker(QThread):
    """
    Prüft/aktualisiert die Spiele-Datenbank (config/games.json) im Hintergrund.
      mode="check"    -> check_result(update_verfügbar: bool, remote_version: str)
      mode="download" -> apply_result(ok: bool, neue_version: str)
    Netzwerkzugriff läuft im Thread, damit die UI nicht einfriert.
    """
    check_result = Signal(bool, str)
    apply_result = Signal(bool, str)

    def __init__(self, mode="check"):
        super().__init__()
        self.mode = mode

    def run(self):
        import games as games_db
        if self.mode == "check":
            avail, remote = games_db.remote_games_update_available()
            self.check_result.emit(avail, remote)
            return
        try:
            raw, _ = games_db.fetch_remote_games_config()
            new_version = games_db.apply_remote_games_config(raw)
            self.apply_result.emit(True, new_version)
        except Exception:
            self.apply_result.emit(False, "")


class AppUpdateWorker(QThread):
    """
    Führt das Selbst-Update im Terminal aus, indem es das vorhandene install.sh
    holt und startet (es ersetzt /opt/yakuda-connect durch den aktuellen Stand).
    Ein Terminal ist nötig, weil install.sh 'sudo' verwendet (Passwort-Eingabe).
    Erfolg wird über eine Sentinel-Datei erkannt (Terminal-Exitcodes sind
    je nach Emulator unzuverlässig).
    """
    status_signal   = Signal(str)
    finished_signal = Signal(bool)

    def run(self):
        import os
        import tempfile

        terminal, exec_flags = find_terminal()
        if terminal is None:
            self.status_signal.emit("Fehler: Kein unterstütztes Terminal gefunden!")
            self.finished_signal.emit(False)
            return

        sentinel = os.path.join(tempfile.gettempdir(), f"yakuda_update_ok_{os.getpid()}")
        try:
            if os.path.exists(sentinel):
                os.remove(sentinel)
        except Exception as exc:
            log.debug("run: ignoriert — %s", exc)

        self.status_signal.emit("yakuda-connect Update läuft ...")

        # install.sh via curl ODER wget beziehen und mit bash ausführen.
        fetch = (
            "if command -v curl >/dev/null 2>&1; then "
            f"  bash <(curl -fsSL {APP_INSTALL_SH_URL}); "
            "elif command -v wget >/dev/null 2>&1; then "
            f"  bash <(wget -qO- {APP_INSTALL_SH_URL}); "
            "else "
            "  echo 'Fehler: weder curl noch wget installiert.'; exit 1; "
            "fi"
        )
        bash_cmd = (
            "echo '=== yakuda-connect Update ==='; "
            f"{fetch}; "
            "rc=$?; echo ''; "
            f"if [ $rc -eq 0 ]; then touch '{sentinel}'; "
            "echo 'Fertig. Dieses Fenster schließt sich gleich automatisch...'; "
            "else echo 'Update fehlgeschlagen (Details siehe oben).'; fi; "
            "sleep 3"
        )
        cmd = [terminal] + exec_flags + ["bash", "-c", bash_cmd]

        try:
            proc = subprocess.Popen(cmd)
            proc.wait()
        except Exception as e:
            self.status_signal.emit(f"Fehler beim Update: {e}")
            self.finished_signal.emit(False)
            return

        ok = os.path.exists(sentinel)
        try:
            if ok:
                os.remove(sentinel)
        except Exception as exc:
            log.debug("run: ignoriert — %s", exc)

        if ok:
            self.status_signal.emit("Update abgeschlossen.")
        self.finished_signal.emit(ok)


class CoverDownloadWorker(QThread):
    """
    Laedt fehlende Spiel-Cover im Hintergrund vom Steam-CDN.

    Damit hat JEDES erkannte Spiel ein Bild — auch ungetestete und solche, die
    nie gestartet wurden (fuer die Steam also gar kein lokales Cover hat).

    Pro fertigem Cover kommt ein Signal, damit die Kachel sofort aktualisiert
    wird, statt bis zum Ende zu warten.
    """
    cover_ready = Signal(str, str)   # (appid, pfad)
    finished_signal = Signal(int)    # Anzahl geladener Cover

    def __init__(self, appids):
        super().__init__()
        self.appids = list(appids)
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        # Import hier, damit install_worker ohne games.py importierbar bleibt
        import games as games_db
        count = 0
        for appid in self.appids:
            if self._stop:
                break
            try:
                path = games_db.download_cover(appid)
            except Exception:
                path = None
            if path:
                count += 1
                self.cover_ready.emit(str(appid), path)
        self.finished_signal.emit(count)


class XrizerGithubWorker(QThread):
    """
    Laedt xrizer von GitHub und entpackt es nach ~/.local/share/xrizer.

    Kein Terminalfenster, kein sudo: es wird nur in das eigene
    Benutzerverzeichnis geschrieben. Deshalb laeuft das hier im Hintergrund
    mit Fortschritt in der Statuszeile statt in einer Konsole.
    """
    status_signal = Signal(str)
    # (erfolg, pfad_oder_fehlertext, tag)
    finished_signal = Signal(bool, str, str)

    def __init__(self):
        super().__init__()
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        import xrizer_github as xg
        try:
            def progress(done, total):
                if total:
                    self.status_signal.emit(
                        f"Lade xrizer ... {done * 100 // total} % "
                        f"({done // 1024 // 1024} von {total // 1024 // 1024} MB)")
                else:
                    self.status_signal.emit(f"Lade xrizer ... {done // 1024} KB")

            path, tag = xg.install(progress=progress,
                                   status=self.status_signal.emit,
                                   cancelled=lambda: self._cancel)
            self.finished_signal.emit(True, path, tag)
        except xg.XrizerError as exc:
            log.warning("xrizer-Download fehlgeschlagen: %s", exc)
            self.finished_signal.emit(False, str(exc), "")
        except Exception as exc:  # noqa: BLE001 — der Nutzer soll etwas lesen koennen
            log.exception("xrizer-Download abgebrochen")
            self.finished_signal.emit(False, str(exc), "")


class RpmInstallWorker(QThread):
    """
    Laedt das neueste RPM eines Tools aus dessen GitHub-Release und
    installiert es mit dnf in einem sichtbaren Terminalfenster.

    Warum Terminal: dnf braucht root. Das Passwort wird dort eingegeben, wie
    bei allen anderen Systeminstallationen der App auch — kein eigener
    Passwortdialog.

    Die Datei wird bewusst nach /tmp geladen und danach wieder entfernt: ein
    installiertes RPM braucht die Datei nicht mehr, und ein 300-MB-Paket soll
    nicht dauerhaft im Downloadordner liegen.
    """
    status_signal = Signal(str)
    finished_signal = Signal(bool)

    def __init__(self, tool):
        super().__init__()
        self.tool = tool

    def run(self):
        import os
        import tempfile
        import urllib.request

        name = self.tool.get("name", "Tool")
        try:
            import appimage_installer as appimg
            self.status_signal.emit("🔎 Suche RPM ...")
            try:
                url, version = appimg.resolve_rpm(self.tool)
            except appimg.RateLimited as exc:
                self.status_signal.emit(f"Fehler: {exc}")
                self.finished_signal.emit(False)
                return

            if not url:
                import platform
                self.status_signal.emit(
                    f"Fehler: Kein RPM fuer {platform.machine()} im neuesten Release.")
                self.finished_signal.emit(False)
                return

            tmp_dir = tempfile.mkdtemp(prefix="yakuda-rpm-")
            dest = os.path.join(tmp_dir, os.path.basename(url.split("?")[0]))
            self.status_signal.emit(f"⬇ Lade {name} {version} ...")
            req = urllib.request.Request(url, headers={"User-Agent": "yakuda-connect"})
            with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as fh:
                total = int(r.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    fh.write(chunk)
                    done += len(chunk)
                    if total:
                        self.status_signal.emit(
                            f"⬇ Lade {name} ... {done / 1_000_000:.1f} / "
                            f"{total / 1_000_000:.1f} MB")

            terminal, exec_flags = find_terminal()
            if terminal is None:
                self.status_signal.emit("Fehler: Kein unterstuetztes Terminal gefunden!")
                self.finished_signal.emit(False)
                return

            # 'dnf install <datei>' loest die Abhaengigkeiten des Pakets aus den
            # Repos mit auf — anders als 'rpm -i', das bei fehlenden
            # Abhaengigkeiten einfach abbricht.
            bash_cmd = (
                f"echo '=== Installiere {name} {version} aus RPM ==='; "
                f"sudo dnf install -y '{dest}'; "
                f"echo ''; "
                f"echo 'Fertig. Dieses Fenster schließt sich gleich automatisch...'; "
                f"sleep 2"
            )
            cmd = [terminal] + list(exec_flags) + ["bash", "-c", bash_cmd] \
                if exec_flags else [terminal, "bash", "-c", bash_cmd]
            self.status_signal.emit("📦 Installiere (Terminalfenster) ...")
            res = subprocess.run(cmd, timeout=1800)
            ok = res.returncode == 0

            shutil.rmtree(tmp_dir, ignore_errors=True)
            self.status_signal.emit("✔ Fertig installiert." if ok
                                    else "Installation fehlgeschlagen.")
            self.finished_signal.emit(ok)
        except Exception as exc:  # noqa: BLE001 — der Nutzer soll etwas lesen koennen
            log.exception("RPM-Installation fehlgeschlagen")
            self.status_signal.emit(f"Fehler: {exc}")
            self.finished_signal.emit(False)
