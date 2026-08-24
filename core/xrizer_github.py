#!/usr/bin/env python3
"""
core/xrizer_github.py — xrizer direkt von GitHub holen
======================================================
Rueckfall, wenn das COPR ``@xr-sig/xrizer`` nicht erreichbar ist. Genau das
passiert regelmaessig: copr.fedorainfracloud.org antwortet dann minutenlang mit
weniger als 1000 Bytes/Sekunde, dnf bricht mit ``Curl error (28): Timeout was
reached`` ab, und die Installation ist gescheitert, ohne dass am System etwas
falsch waere.

Der Weg hier braucht weder ein Repository noch root:

  * geladen wird das Release-ZIP aus https://github.com/Supreeeme/xrizer
  * entpackt wird nach ``~/.local/share/xrizer`` — ein Ort, der in
    EXTRA_OVR_PATHS schon steht und deshalb sofort in der OpenVR-Auswahl
    auftaucht
  * WiVRn findet diesen Ordner NICHT von allein (er steht nicht in dessen
    Suchliste), der Pfad muss also ausdruecklich in die config.json — genau
    das macht der Aufrufer nach erfolgreichem Download

Aufbau des Archivs (an v0.5 geprueft):

    xrizer-v0.5/bin/linux64/vrclient.so
    xrizer-v0.5/bin/version.txt

Es gibt also einen Ordner obendrueber, der beim Entpacken wegfaellt. Das
zweite Asset des Releases, ``dependencies.zip``, ist ausdruecklich NICHT das
Programm und wird uebersprungen.
"""
import json
import os
import platform
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile

import vr_environment as venv
from logging_setup import get_logger

log = get_logger("xrizer_github")

REPO = "Supreeeme/xrizer"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"

# Zielordner. Bewusst im Benutzerverzeichnis: kein sudo, keine Kollision mit
# einem spaeter doch noch installierten RPM unter /usr/lib64.
INSTALL_DIR = os.path.join(
    os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"),
    "xrizer")

# Woher der Ordner stammt — damit die Oberflaeche Version und Herkunft zeigen
# kann und ein Update erkennt, ohne erneut zu laden.
MARKER_FILE = ".yakuda-xrizer.json"

# Groesse des Release-ZIPs liegt bei ~5 MB (v0.5). Alles jenseits von 200 MB
# ist mit Sicherheit nicht das, was wir erwarten — dann lieber abbrechen, als
# die Platte vollzuschreiben.
MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024


class XrizerError(RuntimeError):
    """Fehler, dessen Text direkt der Oberflaeche gezeigt werden darf."""


# --------------------------------------------------------------------------- #
#  Release finden
# --------------------------------------------------------------------------- #
def _is_program_asset(name):
    """
    Ist das der Programm-Download?

    ``dependencies.zip`` liegt im selben Release und enthaelt NICHT das
    Programm — wer es entpackt, hat einen Ordner ohne vrclient.so und wundert
    sich, warum kein Spiel startet.
    """
    low = name.lower()
    if not low.endswith(".zip"):
        return False
    if "dependencies" in low or "source" in low or "debug" in low:
        return False
    return low.startswith("xrizer")


def latest_release(timeout=15):
    """
    (tag, asset_url) des neuesten Releases.

    Der Dateiname enthaelt die Version (``xrizer-v0.5.zip``), es gibt also
    keine feste URL, die immer aufs Aktuelle zeigt: der bekannte Kurzweg
    ``releases/latest/download/xrizer-release.zip`` laeuft ins Leere (404).
    Deshalb wird die API gefragt.
    """
    req = urllib.request.Request(API_LATEST, headers={
        "User-Agent": "yakuda-connect",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise XrizerError(
                "GitHub-API-Limit erreicht (zu viele Anfragen pro Stunde). "
                "Bitte etwas warten oder das ZIP von Hand laden.") from exc
        raise XrizerError(f"GitHub antwortet nicht (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise XrizerError(f"GitHub nicht erreichbar: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise XrizerError("Antwort von GitHub war unlesbar.") from exc

    tag = data.get("tag_name") or "?"
    for asset in data.get("assets") or []:
        name = asset.get("name") or ""
        url = asset.get("browser_download_url")
        if url and _is_program_asset(name):
            return tag, url
    raise XrizerError(
        f"Im Release {tag} liegt kein passendes ZIP. "
        f"Bitte auf {RELEASES_PAGE} nachsehen.")


def installed_info():
    """
    Was liegt im Zielordner? ``{'tag': ..., 'url': ..., 'date': ...}`` oder {}.

    Nur aussagekraeftig fuer Ordner, die von hier stammen — ein selbst
    gebautes xrizer hat keine Markierungsdatei, und dann wird auch nichts
    ueber dessen Version behauptet.
    """
    try:
        with open(os.path.join(INSTALL_DIR, MARKER_FILE), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def supported_platform():
    """
    Das Release enthaelt ausschliesslich ``bin/linux64`` — auf allem anderen
    als x86_64 waere der Download nutzlos.
    """
    return (platform.machine() or "").lower() in ("x86_64", "amd64")


# --------------------------------------------------------------------------- #
#  Herunterladen und entpacken
# --------------------------------------------------------------------------- #
def _download(url, dest, progress=None, cancelled=None, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": "yakuda-connect"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as fh:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                if cancelled and cancelled():
                    raise XrizerError("Abgebrochen.")
                chunk = r.read(65536)
                if not chunk:
                    break
                done += len(chunk)
                if done > MAX_DOWNLOAD_BYTES:
                    raise XrizerError("Download unerwartet gross — abgebrochen.")
                fh.write(chunk)
                if progress:
                    progress(done, total)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise XrizerError(f"Download fehlgeschlagen: {exc}") from exc


def _safe_extract(zip_path, target):
    """
    Entpacken, ohne dem Archiv zu vertrauen.

    Ein ZIP darf Pfade wie ``../../.bashrc`` oder absolute Pfade enthalten.
    ``extractall`` von Python filtert das seit 3.6.2 zwar selbst, aber darauf
    verlassen wir uns hier nicht — die Datei kommt aus dem Netz.
    """
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            if member.startswith("/") or ".." in member.split("/"):
                raise XrizerError(f"Archiv enthaelt einen unzulaessigen Pfad: {member}")
        zf.extractall(target)


def _find_runtime_root(folder):
    """
    Der Ordner, der ``bin/linux64/vrclient.so`` enthaelt.

    Im Archiv liegt alles unter ``xrizer-v0.5/`` — dieser Zwischenordner soll
    nicht mit ins Ziel, sonst zeigt der Eintrag in WiVRns config.json eine
    Ebene zu hoch. Der Name aendert sich mit jeder Version, deshalb wird
    gesucht statt geraten.
    """
    if venv.looks_like_openvr_compat(folder):
        return folder
    try:
        for name in sorted(os.listdir(folder)):
            candidate = os.path.join(folder, name)
            if os.path.isdir(candidate) and venv.looks_like_openvr_compat(candidate):
                return candidate
    except OSError as exc:
        raise XrizerError(f"Entpackter Ordner nicht lesbar: {exc}") from exc
    raise XrizerError("Im Archiv steckt keine bin/linux64/vrclient.so.")


def install(progress=None, status=None, cancelled=None):
    """
    xrizer herunterladen und nach INSTALL_DIR entpacken.

    Rueckgabe: (pfad, tag)

    Der bestehende Ordner wird erst ersetzt, wenn der neue vollstaendig da ist
    und geprueft wurde. Geht unterwegs etwas schief, bleibt die alte
    Installation unangetastet — ein halb entpacktes xrizer waere schlimmer als
    gar keines, weil WiVRn dann auf eine kaputte Bibliothek zeigt.
    """
    def say(text):
        if status:
            status(text)

    if not supported_platform():
        raise XrizerError(
            f"Das Release gibt es nur fuer x86_64, dieses System ist "
            f"{platform.machine()}.")

    say("Suche neuestes Release ...")
    tag, url = latest_release()
    log.info("xrizer %s von %s", tag, url)

    tmp_dir = tempfile.mkdtemp(prefix="yakuda-xrizer-")
    staging = INSTALL_DIR + ".new"
    backup = INSTALL_DIR + ".old"
    try:
        archive = os.path.join(tmp_dir, "xrizer.zip")
        say(f"Lade xrizer {tag} ...")
        _download(url, archive, progress=progress, cancelled=cancelled)

        say("Entpacke ...")
        unpacked = os.path.join(tmp_dir, "unpacked")
        _safe_extract(archive, unpacked)
        runtime = _find_runtime_root(unpacked)

        shutil.rmtree(staging, ignore_errors=True)
        shutil.move(runtime, staging)
        with open(os.path.join(staging, MARKER_FILE), "w", encoding="utf-8") as fh:
            json.dump({"tag": tag, "url": url, "repo": REPO}, fh, indent=2)

        # Tausch: alt zur Seite, neu an den Platz, alt weg. os.replace
        # funktioniert bei Ordnern nicht, deshalb dieser Dreischritt.
        shutil.rmtree(backup, ignore_errors=True)
        if os.path.isdir(INSTALL_DIR):
            os.rename(INSTALL_DIR, backup)
        os.makedirs(os.path.dirname(INSTALL_DIR), exist_ok=True)
        try:
            os.rename(staging, INSTALL_DIR)
        except OSError:
            # Zuruecklegen, was da war — lieber der alte Stand als nichts.
            if os.path.isdir(backup):
                os.rename(backup, INSTALL_DIR)
            raise
        shutil.rmtree(backup, ignore_errors=True)

        if not venv.looks_like_openvr_compat(INSTALL_DIR):
            raise XrizerError("Nach dem Entpacken fehlt die vrclient.so.")
        log.info("xrizer %s installiert: %s", tag, INSTALL_DIR)
        return INSTALL_DIR, tag
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)


def uninstall():
    """Von hier installiertes xrizer wieder entfernen."""
    if not installed_info():
        return False        # nicht von uns — nicht anfassen
    shutil.rmtree(INSTALL_DIR, ignore_errors=True)
    log.info("xrizer aus %s entfernt", INSTALL_DIR)
    return True
