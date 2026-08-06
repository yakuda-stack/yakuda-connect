#!/usr/bin/env python3
import os
import json
import shutil
import datetime
import subprocess
from PySide6.QtWidgets import QMessageBox
import vr_environment as venv
import openxr_manager as oxr

HOME = os.path.expanduser("~")
BACKUP_DIR = os.path.join(HOME, ".config/yakuda-connect/backup")
BACKUP_CONFIG_DIR = os.path.join(BACKUP_DIR, "config")
BACKUP_USR_DIR = os.path.join(BACKUP_DIR, "usr")
BACKUP_OPT_DIR = os.path.join(BACKUP_DIR, "opt")
# Separater Ordner für die Configs eines per Flatpak installierten Steam
BACKUP_STEAMFP_DIR = os.path.join(BACKUP_DIR, "steamflatpak")

# Metadaten des Backups (woher, von welchem System). Ohne diese Datei gilt ein
# Backup als "unbekannter Herkunft" -> System-Ordner werden NICHT zurueckgespielt.
BACKUP_META_FILE = os.path.join(BACKUP_DIR, "backup_meta.json")

# App-Config: hier wird gemerkt, OB (und wann) ein Backup erstellt wurde.
APP_CONFIG_FILE = os.path.join(HOME, ".config/yakuda-connect/config/config.json")

# Öffentliches "sauberes" Referenz-Backup auf GitHub (yakuda-stack). Gleiche
# Ordnerstruktur wie das lokale Backup (config/ usr/ opt/), nur ohne die
# user-spezifischen steamflatpak-Configs. Wird als tar.gz gezogen und entpackt.
GITHUB_BACKUP_REPO = "https://github.com/yakuda-stack/openXR-VR-linux-backup"
GITHUB_BACKUP_TARBALL = (
    "https://codeload.github.com/yakuda-stack/openXR-VR-linux-backup/tar.gz/refs/heads/main"
)


# --------------------------------------------------------------------------- #
#  Backup-Flag in der App-Config ("es gibt ein Backup")
# --------------------------------------------------------------------------- #
def _load_app_config():
    try:
        with open(APP_CONFIG_FILE, "r") as f:
            content = f.read().strip()
            return json.loads(content) if content else {}
    except Exception:
        return {}


def _save_app_config(data):
    try:
        os.makedirs(os.path.dirname(APP_CONFIG_FILE), exist_ok=True)
        with open(APP_CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[Backup] Konnte Backup-Flag nicht speichern: {e}")


def mark_backup_created():
    """Schreibt in die Config, dass ein VR-Backup existiert (mit Zeitstempel)."""
    data = _load_app_config()
    data["vr_backup_created"] = datetime.datetime.now().isoformat(timespec="seconds")
    _save_app_config(data)


def has_backup_flag():
    """True, wenn laut Config bereits ein Backup erstellt wurde."""
    return bool(_load_app_config().get("vr_backup_created"))


def auto_backup_on_start():
    """
    Wird beim Programmstart aufgerufen:
      * Backup laut Config vorhanden  -> nichts tun.
      * Kein Backup, aber es existiert bereits eine VR-Umgebung
        (openxr-/wivrn-Ordner — nativ ODER Flatpak-Pfade) -> einmalig
        automatisch ein Backup anlegen und das Flag setzen.
      * Weder Backup noch VR-Umgebung -> nichts tun (frisches System).
    Rückgabe: True, wenn jetzt ein Auto-Backup erstellt wurde.
    """
    if has_backup_flag():
        return False

    # Altbestand: Backup-Ordner existiert schon (ältere Version ohne Flag)
    # -> nur das Flag nachtragen, nichts überschreiben.
    if os.path.isdir(BACKUP_DIR) and os.listdir(BACKUP_DIR):
        mark_backup_created()
        return False

    # Existiert überhaupt schon eine VR-Umgebung? (nativ + Flatpak-Pfade)
    candidates = []
    candidates += venv.openxr_config_dirs()          # ~/.config/openxr/1 (+ Steam-Flatpak)
    candidates += venv.openvr_config_dirs()          # ~/.config/openvr (+ Steam-Flatpak)
    candidates.append(venv.wivrn_config_dir())       # nativ ODER WiVRn-Flatpak-Sandbox
    candidates.append(os.path.join(HOME, ".config/openxr"))
    if not any(os.path.isdir(p) for p in candidates):
        return False

    print("[Backup] Kein Backup vorhanden, VR-Umgebung erkannt — erstelle automatisches Erst-Backup...")
    return create_vr_backup()


# --------------------------------------------------------------------------- #
#  System-Fingerabdruck (Distro + Bibliotheks-Layout)
# --------------------------------------------------------------------------- #
#  Warum: Die Dateien unter /usr/share/openxr/1 enthalten absolute bzw. relative
#  Pfade zu den WiVRn-Bibliotheken - und dieses Layout ist distro-spezifisch:
#      Arch    64 Bit -> /usr/lib/wivrn      32 Bit -> /usr/lib32/wivrn
#      Fedora  64 Bit -> /usr/lib64/wivrn    32 Bit -> /usr/lib/wivrn
#      Debian  64 Bit -> /usr/lib/x86_64-linux-gnu/wivrn
#  Ein Arch-Manifest auf Fedora zeigt also auf eine 32-Bit-.so, wo eine 64-Bit
#  erwartet wird. Steams pressure-vessel liest beim Start JEDES Manifest in
#  /usr/share/openxr/1 ein und bricht dann mit "invalid `Elf' handle" ab
#  -> steamwebhelper-Schleife, Steam startet nicht mehr.
#  Deshalb: System-Ordner nur zurueckspielen, wenn das Backup nachweislich vom
#  selben System stammt.
# --------------------------------------------------------------------------- #
def _distro_id():
    try:
        with open("/etc/os-release", "r") as f:
            data = dict(
                line.strip().split("=", 1)
                for line in f if "=" in line and not line.startswith("#")
            )
        ident = data.get("ID", "").strip('"') or "unknown"
        like = data.get("ID_LIKE", "").strip('"')
        return ident, like
    except Exception:
        return "unknown", ""


def _lib_layout():
    """'lib64' (Fedora/openSUSE), 'multiarch' (Debian/Ubuntu) oder 'lib' (Arch)."""
    if os.path.isdir("/usr/lib64") and not os.path.islink("/usr/lib64"):
        return "lib64"
    if os.path.isdir("/usr/lib/x86_64-linux-gnu"):
        return "multiarch"
    return "lib"


def system_fingerprint():
    ident, like = _distro_id()
    return {
        "hostname": os.uname().nodename,
        "distro_id": ident,
        "distro_like": like,
        "lib_layout": _lib_layout(),
    }


def _write_backup_meta(origin, fingerprint=None, root=None):
    """origin: 'local' (dieses System) oder 'github' (Referenz-Backup)."""
    meta = {
        "origin": origin,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "system": fingerprint if fingerprint is not None else system_fingerprint(),
    }
    path = os.path.join(root or BACKUP_DIR, "backup_meta.json")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(meta, f, indent=4)
    except Exception as e:
        print(f"[Backup] Meta-Datei konnte nicht geschrieben werden: {e}")


def _read_backup_meta(root):
    try:
        with open(os.path.join(root, "backup_meta.json"), "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _may_restore_system_dirs(root):
    """
    True nur, wenn das Backup von DIESEM System stammt (gleiche Distro +
    gleiches Bibliotheks-Layout). Alles andere - insbesondere das
    GitHub-Referenz-Backup - bleibt auf die User-Configs beschraenkt.
    Rueckgabe: (erlaubt: bool, grund: str)
    """
    meta = _read_backup_meta(root)
    if not meta:
        return False, "no_meta"
    if meta.get("origin") != "local":
        return False, "foreign_origin"
    sysinfo = meta.get("system", {})
    now = system_fingerprint()
    if sysinfo.get("distro_id") != now["distro_id"]:
        return False, "distro_mismatch"
    if sysinfo.get("lib_layout") != now["lib_layout"]:
        return False, "layout_mismatch"
    return True, ""


SOURCES = {
    "config": [
        os.path.join(HOME, ".config/openvr"),
        os.path.join(HOME, ".config/openxr"),
        os.path.join(HOME, ".config/wivrn")
    ],
    "usr": [
        "/usr/share/openxr"
    ],
    "opt": [
        "/opt/xrizer",
        "/opt/opencomposite"
    ]
}

def create_vr_backup():
    """Erstellt eine saubere Sicherung der aktuellen VR-Laufumgebung."""
    def safe_copy_tree(src, dest_folder):
        if os.path.exists(src):
            folder_name = os.path.basename(src.rstrip("/"))
            target = os.path.join(dest_folder, folder_name)
            if os.path.exists(target):
                shutil.rmtree(target)
            os.makedirs(dest_folder, exist_ok=True)
            shutil.copytree(src, target)

    try:
        for src in SOURCES["config"]: safe_copy_tree(src, BACKUP_CONFIG_DIR)
        for src in SOURCES["usr"]: safe_copy_tree(src, BACKUP_USR_DIR)
        for src in SOURCES["opt"]: safe_copy_tree(src, BACKUP_OPT_DIR)
        # Zusätzlich: Configs eines Flatpak-Steam (eigene Sandbox-Config)
        if venv.steam_is_flatpak():
            base = venv.STEAM_FLATPAK_BASE
            for sub in (".config/openxr", ".config/openvr"):
                safe_copy_tree(os.path.join(base, sub), BACKUP_STEAMFP_DIR)
        # Herkunft festhalten: dieses Backup stammt von DIESEM System und darf
        # deshalb spaeter auch die System-Ordner zurueckspielen.
        _write_backup_meta("local")
        # In der Config merken: es gibt jetzt ein Backup.
        mark_backup_created()
        return True
    except Exception as e:
        print(f"[Backup Fehler] Sicherung fehlgeschlagen: {e}")
        return False

def restore_vr_environment(parent_window):
    """
    Klickt der User auf den Button, wird geprüft:
    Gibt es ein Backup? -> Wiederherstellen.
    Gibt es KEINES? -> Erstes Backup jetzt anlegen!
    """
    # Falls noch überhaupt kein Backup-Ordner existiert, legen wir jetzt das erste an!
    if not os.path.exists(BACKUP_DIR) or not os.listdir(BACKUP_DIR):
        print("[Backup] Kein Backup gefunden. Erstelle ersten System-Wiederherstellungspunkt...")
        if create_vr_backup():
            QMessageBox.information(parent_window, "Backup erstellt",
                                    "Es wurde erfolgreich ein erster sauberer System-Wiederherstellungspunkt deiner VR-Laufumgebung angelegt!")
        else:
            QMessageBox.critical(parent_window, "Fehler", "Der Wiederherstellungspunkt konnte nicht angelegt werden.")
        return

    # Wenn ein Backup existiert -> Normale Wiederherstellungsabfrage
    reply = QMessageBox.question(
        parent_window, "Laufumgebung wiederherstellen",
        "Möchtest du alle VR/XR Konfigurationen und Runtimes aus deinem gespeicherten Backup wiederherstellen?<br><br>"
        "<i>Hinweis: Aktuelle Änderungen werden dabei überschrieben.</i><br>"
        "<i>System-Ordner (/usr/share/openxr) werden nur angefasst, wenn das "
        "Backup von genau diesem System stammt.</i>",
        QMessageBox.Yes | QMessageBox.No
    )

    if reply == QMessageBox.No:
        return

    try:
        notes = _apply_restore(BACKUP_DIR)
        msg = "Deine VR-Laufumgebung wurde wiederhergestellt!"
        if notes:
            msg += "<br><br><b>Hinweise:</b><br>" + "<br>".join(
                f"&bull; {n}" for n in notes)
        QMessageBox.information(parent_window, "Erfolg", msg)
    except Exception as e:
        QMessageBox.critical(parent_window, "Fehler", f"Wiederherstellung fehlgeschlagen: {e}")


def _apply_restore(root):
    """Spielt eine Backup-Ordnerstruktur (config/ usr/ opt/ [steamflatpak/])
    aus 'root' auf das System zurueck. Wird sowohl vom lokalen Backup als auch
    vom GitHub-Backup genutzt.

    Rueckgabe: Liste von Hinweiszeilen (was uebersprungen/korrigiert wurde).
    Wirft bei echten Fehlern eine Exception weiter.
    """
    notes = []

    # 1. User-Configs wiederherstellen
    config_pairs = [
        ("config/openvr", ".config/openvr"),
        ("config/openxr", ".config/openxr"),
        ("config/wivrn", ".config/wivrn"),
    ]
    for b_sub, sys_sub in config_pairs:
        src = os.path.join(root, b_sub)
        dest = os.path.join(HOME, sys_sub)
        if os.path.exists(src):
            if os.path.exists(dest):
                shutil.rmtree(dest)
            shutil.copytree(src, dest)

    # 1b. Flatpak-Steam-Configs zurueckspielen (nur falls im Backup vorhanden;
    #     das GitHub-Backup hat diesen Ordner bewusst nicht).
    steamfp = os.path.join(root, "steamflatpak")
    if os.path.isdir(steamfp):
        base = venv.STEAM_FLATPAK_BASE
        for name in ("openxr", "openvr"):
            src = os.path.join(steamfp, name)
            dest = os.path.join(base, ".config", name)
            if os.path.exists(src):
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                if os.path.exists(dest):
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)

    # 1c. Zurueckgespielte User-Manifeste auf DIESES System umbiegen.
    #     Ein Backup von einem anderen Rechner/einer anderen Distro enthaelt
    #     fremde Bibliothekspfade - die werden hier gegen die lokal gefundenen
    #     WiVRn-Bibliotheken ersetzt, statt sie ungeprueft zu uebernehmen.
    notes += _heal_user_manifests()

    # 2. System-Ordner: NUR wenn das Backup nachweislich von diesem System
    #    stammt. Fremde Manifeste in /usr/share/openxr/1 legen sonst Steam lahm
    #    (pressure-vessel: "invalid `Elf' handle").
    allowed, reason = _may_restore_system_dirs(root)
    if not allowed:
        notes.append({
            "no_meta": "System-Ordner uebersprungen: Backup ohne Herkunftsangabe.",
            "foreign_origin": "System-Ordner uebersprungen: Das Backup stammt nicht "
                              "von diesem Rechner (z. B. GitHub-Referenz-Backup). "
                              "/usr/share/openxr bleibt unangetastet.",
            "distro_mismatch": "System-Ordner uebersprungen: Das Backup stammt von "
                               "einer anderen Distribution.",
            "layout_mismatch": "System-Ordner uebersprungen: Anderes Bibliotheks-"
                               "Layout (lib/lib64/multiarch).",
        }.get(reason, "System-Ordner uebersprungen."))
        return notes

    # 2b. System-Ordner wiederherstellen via pkexec - aber NICHT mehr per
    #     'rm -rf': /usr/share/openxr gehoert der Paketverwaltung. Es werden
    #     nur die Dateien aus dem Backup dazukopiert, vorhandene vorher
    #     gesichert. Ausserdem wird jedes Runtime-Manifest vorher geprueft.
    usr_src = os.path.join(root, "usr/openxr")
    if os.path.isdir(usr_src):
        notes += _restore_system_openxr(usr_src)

    for b_sub, dest in (("opt/xrizer", "/opt/xrizer"),
                        ("opt/opencomposite", "/opt/opencomposite")):
        src = os.path.join(root, b_sub)
        if os.path.exists(src):
            subprocess.run(["pkexec", "rm", "-rf", dest], check=True)
            subprocess.run(["pkexec", "cp", "-r", src, dest], check=True)

    return notes


def _heal_user_manifests():
    """
    Prueft ~/.config/openxr/1/active_runtime.json (+ Steam-Flatpak-Pendant) und
    ersetzt fremde Bibliothekspfade durch die lokal gefundenen. Liefert
    Hinweiszeilen.
    """
    notes = []
    openxr_so, monado_so = venv.find_wivrn_libs()
    for d in venv.openxr_config_dirs():
        target = os.path.join(d, "active_runtime.json")
        if not os.path.isfile(target):
            continue
        try:
            with open(target, "r") as f:
                data = json.load(f)
            lib = data.get("runtime", {}).get("library_path", "")
        except Exception:
            lib = ""
        abs_lib = lib if os.path.isabs(lib) else os.path.normpath(os.path.join(d, lib or ""))
        if lib and os.path.exists(abs_lib) and venv.is_elf64(abs_lib):
            continue                      # passt bereits
        if not openxr_so:
            notes.append(f"{target}: Pfad passt nicht zu diesem System, und es "
                         f"wurde keine lokale WiVRn-Bibliothek gefunden.")
            continue
        runtime = {"file_format_version": "1.0.0",
                   "runtime": {"name": "Monado", "library_path": openxr_so}}
        if monado_so:
            runtime["runtime"]["MND_libmonado_path"] = monado_so
        try:
            with open(target, "w") as f:
                json.dump(runtime, f, indent=4)
            notes.append(f"{target}: Bibliothekspfad auf dieses System angepasst "
                         f"({openxr_so}).")
        except Exception as e:
            notes.append(f"{target}: konnte nicht angepasst werden ({e}).")
    return notes


def _restore_system_openxr(usr_src):
    """
    Kopiert die Dateien aus <backup>/usr/openxr additiv nach /usr/share/openxr.
    Runtime-Manifeste werden vorher geprueft: zeigt eines auf eine fehlende
    oder falsch-bittige Bibliothek, wird es NICHT kopiert.
    """
    import tempfile

    notes = []
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    staging = tempfile.mkdtemp(prefix="yakuda-usrxr-")
    try:
        copied_any = False
        for base, _dirs, files in os.walk(usr_src):
            rel_dir = os.path.relpath(base, usr_src)
            for name in files:
                src_file = os.path.join(base, name)
                rel = os.path.normpath(os.path.join(rel_dir, name))
                if name.endswith(".json") and not _manifest_is_usable(src_file, name):
                    notes.append(f"Uebersprungen (Pfad passt nicht zu diesem "
                                 f"System): /usr/share/openxr/{rel}")
                    continue
                dest_file = os.path.join(staging, rel)
                os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                shutil.copy2(src_file, dest_file)
                copied_any = True

        if not copied_any:
            notes.append("Keine gueltigen Dateien fuer /usr/share/openxr im Backup.")
            return notes

        script = (
            f"cp -a /usr/share/openxr /usr/share/openxr.bak.{stamp} 2>/dev/null; "
            f"mkdir -p /usr/share/openxr && "
            f"cp -a '{staging}/.' /usr/share/openxr/ && "
            f"chmod -R a+rX /usr/share/openxr"
        )
        res = subprocess.run(["pkexec", "bash", "-c", script],
                             capture_output=True, text=True, timeout=180)
        if res.returncode != 0:
            raise RuntimeError((res.stderr or res.stdout or "").strip())
        notes.append(f"/usr/share/openxr aktualisiert (Sicherung: "
                     f"/usr/share/openxr.bak.{stamp}).")
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return notes


def _manifest_is_usable(path, name):
    """
    True, wenn ein Runtime-Manifest auf diesem System funktioniert:
    library_path existiert und hat die zum Dateinamen passende Bitness.
    Nicht-Runtime-JSONs (API-Layer) werden durchgelassen.
    """
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except Exception:
        return False
    rt = data.get("runtime")
    if not isinstance(rt, dict):
        return True                      # api_layer o. ae. - unkritisch
    lib = rt.get("library_path", "")
    if not lib:
        return False
    # Relative Pfade beziehen sich auf das Zielverzeichnis /usr/share/openxr/1
    if os.path.isabs(lib):
        resolved = os.path.normpath(lib)
    else:
        resolved = os.path.normpath(os.path.join("/usr/share/openxr/1", lib))
    if not os.path.exists(resolved):
        return False
    expected = 32 if any(m in name.lower() for m in (".i686.", ".i386.", ".x86.")) else 64
    return venv.elf_class(resolved) == expected


def sync_backup_from_github(parent_window):
    """Lädt das öffentliche Referenz-Backup von GitHub (yakuda-stack) und legt
    es in das LOKALE Backup-Verzeichnis (~/.config/yakuda-connect/backup). Danach
    kann der Nutzer wie gewohnt auf 'Wiederherstellen' klicken.

    Bewusst getrennt vom eigentlichen Restore:
      * kein pkexec / kein Systemzugriff in diesem Schritt — nur Download + Kopie
        in den User-Ordner,
      * wer noch gar kein Backup hat, bekommt so überhaupt erst einen sauberen
        Wiederherstellungspunkt,
      * ein evtl. vorhandenes lokales Backup wird nur nach Rückfrage überschrieben.
    Braucht Internet."""
    import tempfile
    import tarfile
    import urllib.request

    had_backup = os.path.isdir(BACKUP_DIR) and bool(os.listdir(BACKUP_DIR))
    if had_backup:
        msg = ("Du hast bereits ein lokales Backup. Möchtest du es mit dem sauberen "
               "Referenz-Backup von GitHub <b>überschreiben</b>?")
    else:
        msg = ("Es wird das saubere Referenz-Backup von GitHub in dein lokales "
               "Backup-Verzeichnis geladen.")

    reply = QMessageBox.question(
        parent_window, "Backup von GitHub holen",
        f"{msg}<br><br>"
        "Danach kannst du wie gewohnt auf <b>XR/VR Umgebung wiederherstellen</b> "
        "klicken, um es anzuwenden.<br><br>"
        f"<i>Quelle: {GITHUB_BACKUP_REPO}</i><br>"
        "<i>Es wird eine Internetverbindung benötigt.</i>",
        QMessageBox.Yes | QMessageBox.No
    )
    if reply == QMessageBox.No:
        return

    tmp = tempfile.mkdtemp(prefix="yakuda-ghbackup-")
    try:
        # 1. Tarball laden
        tar_path = os.path.join(tmp, "backup.tar.gz")
        urllib.request.urlretrieve(GITHUB_BACKUP_TARBALL, tar_path)

        # 2. Entpacken (mit Data-Filter gegen Path-Traversal, wo verfügbar)
        with tarfile.open(tar_path, "r:gz") as t:
            try:
                t.extractall(tmp, filter="data")   # Python >= 3.12
            except TypeError:
                t.extractall(tmp)

        # 3. Entpackten Wurzelordner finden (…/openXR-VR-linux-backup-main/)
        roots = [d for d in os.listdir(tmp)
                 if os.path.isdir(os.path.join(tmp, d)) and d != "__MACOSX"]
        if not roots:
            raise RuntimeError("Heruntergeladenes Backup ist leer oder unlesbar.")
        root = os.path.join(tmp, roots[0])

        # 4. Die Ordner config/ usr/ opt/ 1:1 ins lokale Backup-Verzeichnis legen.
        #    Genau diese Struktur erwartet das normale Restore (config/openxr,
        #    usr/openxr, opt/xrizer, opt/opencomposite …).
        copied = 0
        os.makedirs(BACKUP_DIR, exist_ok=True)
        for sub in ("config", "usr", "opt"):
            src = os.path.join(root, sub)
            dest = os.path.join(BACKUP_DIR, sub)
            if os.path.isdir(src):
                if os.path.isdir(dest):
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)
                copied += 1

        if copied == 0:
            raise RuntimeError("Im heruntergeladenen Backup wurden keine bekannten "
                               "Ordner (config/usr/opt) gefunden.")

        # Herkunft festhalten: Referenz-Backup, erstellt auf einem Arch-System.
        # Dadurch spielt das Restore daraus KEINE System-Ordner zurueck - die
        # Arch-Bibliothekspfade wuerden auf Fedora/Debian Steam lahmlegen.
        _write_backup_meta("github", fingerprint={
            "hostname": "yakuda-stack/openXR-VR-linux-backup",
            "distro_id": "arch",
            "distro_like": "arch",
            "lib_layout": "lib",
        })

        # Es gibt jetzt ein lokales Backup -> Flag setzen.
        mark_backup_created()

        QMessageBox.information(
            parent_window, "Fertig",
            "Das GitHub-Referenz-Backup liegt jetzt in deinem lokalen "
            "Backup-Verzeichnis.<br><br>"
            "Klicke auf <b>XR/VR Umgebung wiederherstellen</b>, um es anzuwenden.<br><br>"
            "<i>Hinweis: Aus dem Referenz-Backup werden nur deine Benutzer-Configs "
            "zurückgespielt und dabei automatisch an dein System angepasst. "
            "System-Ordner wie /usr/share/openxr bleiben unangetastet — die gehören "
            "deiner Paketverwaltung.</i>")
    except Exception as e:
        QMessageBox.critical(
            parent_window, "Fehler",
            f"GitHub-Sync fehlgeschlagen: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
