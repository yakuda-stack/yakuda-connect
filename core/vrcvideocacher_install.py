#!/usr/bin/env python3
"""
core/vrcvideocacher_install.py — VRCVideoCacher einrichten
===========================================================
Laedt die Linux-Binary aus dem GitHub-Release, legt sie unter
~/.config/yakuda-connect/tools/ ab, macht sie ausfuehrbar und erzeugt eine
Desktop-Verknuepfung samt Symbol. Danach findet ``games.find_vrcvideocacher()``
sie, und der Autostart-Schalter in den Startparametern wird benutzbar.

Zur Herkunft der Datei
----------------------
Das Projekt veroeffentlicht fuer Linux eine einzelne Binary unter dem festen
Pfad ``releases/latest/download/VRCVideoCacher``. Genau diesen Weg empfiehlt
auch die CachyOS-VR-Anleitung (wget + chmod a+x).

Das ist bewusst etwas anderes als das Nachladen eines Shell-Skripts aus einem
beweglichen Branch, das an anderer Stelle abgelehnt wurde: hier laedt der
Nutzer auf ausdruecklichen Knopfdruck ein versioniertes Release-Artefakt eines
Programms, das er ohnehin benutzen will — statt dass die App bei jedem Klick
im Hintergrund fremden Code ausfuehrt. Trotzdem wird geprueft, dass wirklich
eine Linux-Binary ankam und nicht eine Fehlerseite (siehe ``_looks_like_elf``);
ohne diese Pruefung wuerde im Fehlerfall eine HTML-Seite ausfuehrbar gemacht.
"""
import os
import shutil
import tempfile
import urllib.request

from logging_setup import get_logger

log = get_logger("vrcvideocacher")

HOME = os.path.expanduser("~")
INSTALL_DIR = os.path.join(HOME, ".config/yakuda-connect/tools")
BINARY_PATH = os.path.join(INSTALL_DIR, "VRCVideoCacher")

DOWNLOAD_URL = ("https://github.com/EllyVR/VRCVideoCacher/releases/"
                "latest/download/VRCVideoCacher")

LOG_FILE = os.path.join(HOME, ".cache/yakuda-connect/vrcvideocacher.log")
DESKTOP_DIR = os.path.join(HOME, ".local/share/applications")
DESKTOP_FILE = os.path.join(DESKTOP_DIR, "yakuda-vrcvideocacher.desktop")
ICON_DIR = os.path.join(HOME, ".local/share/icons/hicolor/scalable/apps")
ICON_FILE = os.path.join(ICON_DIR, "yakuda-vrcvideocacher.svg")

# Eine offensichtlich zu kleine Datei ist keine Binary, sondern eine
# Fehlerseite oder ein abgebrochener Download.
MIN_BINARY_BYTES = 1024 * 1024        # 1 MiB

# Eigenes Symbol, bewusst nicht das Logo des Projekts: fremde Logos duerfen
# wir nicht einfach mitliefern. Ein Play-Dreieck ueber einem Datentraeger —
# erkennbar genug, um es in der Anwendungsliste zu finden.
ICON_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect x="4" y="4" width="56" height="56" rx="12" fill="#3b4252"/>
  <rect x="4" y="4" width="56" height="56" rx="12" fill="none"
        stroke="#5e81ac" stroke-width="2"/>
  <path d="M26 20 L46 32 L26 44 Z" fill="#a3be8c"/>
  <rect x="14" y="47" width="36" height="5" rx="2.5" fill="#5e81ac"/>
  <circle cx="19" cy="49.5" r="1.6" fill="#eceff4"/>
</svg>
"""

DESKTOP_TEMPLATE = """[Desktop Entry]
Type=Application
Name=VRCVideoCacher
GenericName=VRChat video player fix
Comment=Caches VRChat videos locally and fixes YouTube playback
Exec={exec_path}
Icon=yakuda-vrcvideocacher
Terminal=true
Categories=Game;Utility;
Keywords=VRChat;VR;Video;YouTube;
StartupNotify=false
X-Created-By=yakuda-connect
"""


def is_installed():
    return os.path.isfile(BINARY_PATH) and os.access(BINARY_PATH, os.X_OK)


def installed_size():
    try:
        return os.path.getsize(BINARY_PATH)
    except OSError:
        return 0


def _looks_like_elf(path):
    """Ist das wirklich eine Linux-Binary?

    GitHub liefert bei Problemen eine HTML-Seite mit Status 200 aus. Ohne
    diese Pruefung wuerde die App eine Fehlerseite nach ~/.config legen,
    ausfuehrbar machen und in eine Desktop-Verknuepfung eintragen.
    """
    try:
        if os.path.getsize(path) < MIN_BINARY_BYTES:
            return False
        with open(path, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


def download(progress=None):
    """Laedt die Binary und installiert sie. (ok, meldung).

    ``progress`` wird mit (geladen, gesamt) in Bytes aufgerufen; gesamt ist
    0, wenn der Server keine Groesse meldet.
    """
    os.makedirs(INSTALL_DIR, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=INSTALL_DIR, prefix=".download-")
    os.close(tmp_fd)
    try:
        req = urllib.request.Request(
            DOWNLOAD_URL, headers={"User-Agent": "yakuda-connect"})
        with urllib.request.urlopen(req, timeout=30) as r:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)

        if not _looks_like_elf(tmp_path):
            os.unlink(tmp_path)
            return False, "not_a_binary"

        # mkstemp legt mit 0600 an; ein blosses Hinzufuegen der x-Bits ergaebe
        # 0711 (ausfuehrbar, aber nicht lesbar fuer Gruppe/Andere). 0755
        # explizit setzen, wie es fuer ein Programm ueblich ist.
        os.chmod(tmp_path, 0o755)
        # os.replace ist atomar: entweder die alte oder die neue Datei, nie
        # eine halbe. Wichtig, falls das Programm gerade laeuft.
        os.replace(tmp_path, BINARY_PATH)
    except Exception as exc:
        log.warning("Download fehlgeschlagen: %s", exc)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return False, str(exc)

    log.info("VRCVideoCacher installiert: %s (%.1f MiB)",
             BINARY_PATH, installed_size() / 1048576)
    return True, BINARY_PATH


def create_desktop_entry():
    """Legt Symbol und .desktop-Datei an. (ok, pfad).

    Funktioniert auf KDE, GNOME, XFCE und allem anderen, was sich an die
    freedesktop-Spezifikation haelt — es ist derselbe Ordner, in den auch
    Paketmanager Anwendungen eintragen.
    """
    if not is_installed():
        return False, "not_installed"
    try:
        os.makedirs(ICON_DIR, exist_ok=True)
        with open(ICON_FILE, "w", encoding="utf-8") as f:
            f.write(ICON_SVG)

        os.makedirs(DESKTOP_DIR, exist_ok=True)
        with open(DESKTOP_FILE, "w", encoding="utf-8") as f:
            f.write(DESKTOP_TEMPLATE.format(exec_path=BINARY_PATH))
        os.chmod(DESKTOP_FILE, 0o755)
    except Exception as exc:
        log.warning("Desktop-Eintrag fehlgeschlagen: %s", exc)
        return False, str(exc)

    # Anwendungsmenue aktualisieren, damit der Eintrag sofort auftaucht.
    # Fehlt das Werkzeug, ist der Eintrag spaetestens nach dem naechsten
    # Anmelden da — kein Grund, die Installation als gescheitert zu melden.
    for cmd in (["update-desktop-database", DESKTOP_DIR],
                ["kbuildsycoca6", "--noincremental"]):
        if shutil.which(cmd[0]):
            try:
                from proc import run
                run(cmd, timeout=20)
            except Exception:
                pass
            break

    return True, DESKTOP_FILE


def has_desktop_entry():
    return os.path.isfile(DESKTOP_FILE)


def is_running():
    """Laeuft VRCVideoCacher gerade?

    ``pgrep -x`` auf den exakten Prozessnamen — NICHT ``-f`` auf die ganze
    Kommandozeile. Sonst matcht jeder Prozess, der den Namen bloss als
    Argument fuehrt, und meldet "laeuft", obwohl nichts laeuft.
    """
    from proc import run
    return run(["pgrep", "-x", "VRCVideoCacher"], timeout=10).returncode == 0


def start():
    """Startet VRCVideoCacher losgeloest von Yakuda Connect. (ok, meldung).

    ``start_new_session`` haengt den Prozess in eine eigene Sitzung: er
    ueberlebt das Beenden von Yakuda Connect und bekommt kein SIGHUP mit.
    Die Ausgabe geht in eine Logdatei — bliebe sie an unseren Pipes haengen,
    koennte das den Beenden-Vorgang der App blockieren.
    """
    import subprocess

    if not is_installed():
        return False, "not_installed"
    if is_running():
        return True, "already_running"

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    try:
        logfile = open(LOG_FILE, "ab")
        subprocess.Popen(
            [BINARY_PATH],
            cwd=INSTALL_DIR,
            stdout=logfile, stderr=logfile, stdin=subprocess.DEVNULL,
            start_new_session=True)
    except Exception as exc:
        log.warning("Start fehlgeschlagen: %s", exc)
        return False, str(exc)
    log.info("VRCVideoCacher gestartet")
    return True, "started"


def stop():
    """Beendet VRCVideoCacher freundlich (SIGTERM).

    Kein SIGKILL: das Programm stellt beim Beenden VRChats yt-dlp.exe
    zurueck. Wird es hart abgeschossen, bleibt der Stub liegen und VRChat
    hat dauerhaft ein fremdes yt-dlp.
    """
    from proc import run
    if not is_running():
        return True, "not_running"
    run(["pkill", "-TERM", "-x", "VRCVideoCacher"], timeout=10)
    return True, "stopped"


def uninstall():
    """Entfernt Binary, Symbol und Verknuepfung. Die Konfiguration und der
    Video-Cache von VRCVideoCacher selbst bleiben unangetastet — die gehoeren
    dem Programm, nicht uns."""
    removed = []
    for path in (BINARY_PATH, DESKTOP_FILE, ICON_FILE):
        try:
            if os.path.exists(path):
                os.unlink(path)
                removed.append(path)
        except OSError as exc:
            log.warning("Konnte %s nicht entfernen: %s", path, exc)
    return True, len(removed)
