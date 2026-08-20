#!/usr/bin/env python3
"""
core/game_backup.py — Spiel-Konfiguration im Proton-Prefix sichern
==================================================================
Wechselt man die Proton-Version, legt Steam beim naechsten Start haeufig ein
frisches Prefix an. Alles, was das Spiel dort gespeichert hat — Einstellungen,
Avatar-Favoriten, VRChats gesamter LocalLow-Ordner — ist dann weg. Deshalb
bietet die App beim "Use"-Klick an, vorher zu sichern.

Wichtig ist die Reihenfolge, und die ist nicht offensichtlich: das neue
Prefix existiert erst, NACHDEM das Spiel einmal gestartet wurde. Wiederher-
stellen kann man also nicht sofort. Darum ist Sichern und Zurueckspielen hier
getrennt — Backup beim Wechsel, "Config zurueckspielen" spaeter per Knopf.

Warum NICHT ins Bilder-Verzeichnis gesichert wird
--------------------------------------------------
Naheliegend waere ~/Bilder/VRChat/VRChat_backup/. Das ist eine Falle: sobald
der Picture-Fix gesetzt ist, IST ~/Bilder/VRChat ein Symlink ins Prefix. Ein
Backup darunter laege also im Prefix — genau in dem Ordner, dessen Verlust es
abfangen soll. Loescht Steam das Prefix, ist das Backup mit weg.

Deshalb:
  Konfiguration : ~/.config/yakuda-connect/games_backup/<appid>/
  VRChat-Bilder : ~/Bilder/VRChat_backup/   (NEBEN dem Symlink, nicht darin)

Sicherheit beim Zurueckspielen
------------------------------
Es wird NICHTS geloescht. Vorhandene Dateien werden vor dem Ueberschreiben
unter <name>.vor-restore beiseitegelegt, und es wird pro Datei gemischt statt
Ordner zu ersetzen. Grund ist der Fehler aus v1.1.4: ein 'rm -rf' im
Restore-Pfad hat damals auf Fedora Steam zerlegt. Additiv ist langsamer und
kann nicht dasselbe anrichten.
"""
import os
import shutil
import time

import vr_environment as venv
from jsonio import read_json, write_json_atomic
from logging_setup import get_logger

log = get_logger("game_backup")

HOME = os.path.expanduser("~")
BACKUP_ROOT = os.path.join(HOME, ".config/yakuda-connect/games_backup")

# Diese Teilbaeume des Prefixes werden gesichert. Alles andere im Prefix ist
# entweder von Steam/Proton neu erzeugbar (Wine-Systemdateien, Registry) oder
# gehoert dem Spiel selbst (Programmdateien liegen ohnehin ausserhalb).
CONFIG_SUBDIRS = (
    "AppData/LocalLow",
    "AppData/Roaming",
    "Documents",
    "Saved Games",
)

# Nicht mitsichern: gross, nutzlos, oder beim naechsten Start neu erzeugt.
#
# Exakte Namen reichen hier NICHT. VRChat legt seinen Welten- und
# Avatar-Cache unter "Cache-WindowsPlayer" ab, Unity-Spiele nutzen
# "HTTPCache", "ShaderCache", "il2cpp_cache" und aehnliche. Mit einer Liste
# exakter Namen rutschte genau das durch: ein VRChat-Backup war dadurch
# ~3,7 GB gross statt weniger Kilobyte — fast ausschliesslich Cache, den das
# Spiel beim naechsten Start ohnehin neu herunterlaedt. Deshalb wird auf
# Teilzeichenketten geprueft.
SKIP_DIR_PARTS = ("cache", "crash", "gpucache", "logs", "temp", "tmp")
SKIP_DIRS = {"Tools"}
SKIP_SUFFIXES = (".log", ".dmp", ".tmp", ".vrcasset", ".pak")
SKIP_PREFIXES = ("output_log_",)

# Einzelne sehr grosse Dateien sind praktisch nie Konfiguration. Wer 200 MB
# in einer Datei hat, hat einen Cache oder ein Asset erwischt.
MAX_FILE_BYTES = 64 * 1024 ** 2         # 64 MiB

# Ueber dieser Groesse wird nachgefragt statt einfach loszukopieren.
LARGE_BACKUP_BYTES = 2 * 1024 ** 3      # 2 GiB


def backup_dir(appid):
    return os.path.join(BACKUP_ROOT, str(appid))


def meta_path(appid):
    return os.path.join(backup_dir(appid), "backup_meta.json")


def prefix_user_dir(appid):
    """.../compatdata/<appid>/pfx/drive_c/users/steamuser oder ""."""
    rel = f"steamapps/compatdata/{appid}/pfx/drive_c/users/steamuser"
    for root in venv.steam_data_roots():
        path = os.path.join(root, rel)
        if os.path.isdir(path):
            return path
    return ""


def _skip(name, is_dir):
    if is_dir:
        if name in SKIP_DIRS:
            return True
        low = name.lower()
        return any(part in low for part in SKIP_DIR_PARTS)
    return (name.startswith(SKIP_PREFIXES) or name.endswith(SKIP_SUFFIXES))


def _walk_sources(user_dir):
    """(quelle, relativer_pfad) fuer alles, was gesichert wird."""
    for sub in CONFIG_SUBDIRS:
        base = os.path.join(user_dir, sub)
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not _skip(d, True)]
            for f in files:
                if _skip(f, False):
                    continue
                src = os.path.join(root, f)
                if os.path.islink(src):
                    continue           # Symlinks nicht mitschleppen
                try:
                    if os.path.getsize(src) > MAX_FILE_BYTES:
                        continue
                except OSError:
                    continue
                rel = os.path.relpath(src, user_dir)
                yield src, rel


def estimate_size(appid):
    """(anzahl_dateien, bytes) dessen, was gesichert wuerde."""
    user_dir = prefix_user_dir(appid)
    if not user_dir:
        return 0, 0
    count = total = 0
    for src, _rel in _walk_sources(user_dir):
        try:
            total += os.path.getsize(src)
            count += 1
        except OSError:
            pass
    return count, total


def has_backup(appid):
    return os.path.isfile(meta_path(appid))


def backup_info(appid):
    """Metadaten eines vorhandenen Backups oder {}."""
    return read_json(meta_path(appid)) or {}


def create_backup(appid, game_name="", proton_version=""):
    """Sichert die Konfiguration eines Spiels. (ok, meldung).

    Ein vorhandenes Backup wird nicht ueberschrieben, sondern unter
    <appid>.alt-<zeitstempel> zur Seite gelegt — sonst zerstoert ein zweiter
    Klick genau das Backup, das man gerade brauchen wuerde.
    """
    user_dir = prefix_user_dir(appid)
    if not user_dir:
        return False, "no_prefix"

    dest = backup_dir(appid)
    if os.path.isdir(dest):
        old = f"{dest}.alt-{time.strftime('%Y%m%d-%H%M%S')}"
        try:
            os.rename(dest, old)
            log.info("Vorheriges Backup nach %s verschoben", old)
        except OSError as exc:
            return False, f"rename_failed: {exc}"

    files = size = 0
    try:
        os.makedirs(dest, exist_ok=True)
        for src, rel in _walk_sources(user_dir):
            target = os.path.join(dest, "files", rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(src, target)
            files += 1
            try:
                size += os.path.getsize(src)
            except OSError:
                pass
    except Exception as exc:
        log.warning("Backup fehlgeschlagen: %s", exc)
        return False, str(exc)

    write_json_atomic(meta_path(appid), {
        "appid": str(appid),
        "name": game_name,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "proton": proton_version,
        "source": user_dir,
        "files": files,
        "bytes": size,
        "subdirs": list(CONFIG_SUBDIRS),
    })
    log.info("Backup %s: %d Dateien, %.1f MiB", appid, files, size / 1048576)
    return True, f"{files}"


def restore_backup(appid):
    """Spielt ein Backup additiv zurueck. (ok, meldung).

    Es wird NICHTS geloescht: pro Datei kopiert, und was schon da ist, wird
    vorher als <name>.vor-restore gesichert. Das Prefix muss existieren —
    das Spiel also nach dem Proton-Wechsel einmal gestartet worden sein.
    """
    if not has_backup(appid):
        return False, "no_backup"
    user_dir = prefix_user_dir(appid)
    if not user_dir:
        return False, "no_prefix"

    src_root = os.path.join(backup_dir(appid), "files")
    if not os.path.isdir(src_root):
        return False, "no_backup"

    restored = 0
    try:
        for root, _dirs, files in os.walk(src_root):
            for f in files:
                src = os.path.join(root, f)
                rel = os.path.relpath(src, src_root)
                target = os.path.join(user_dir, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                if os.path.exists(target):
                    keep = target + ".vor-restore"
                    if os.path.exists(keep):
                        os.remove(keep)
                    os.replace(target, keep)
                shutil.copy2(src, target)
                restored += 1
    except Exception as exc:
        log.warning("Restore fehlgeschlagen: %s", exc)
        return False, str(exc)

    log.info("Restore %s: %d Dateien", appid, restored)
    return True, f"{restored}"


# --------------------------------------------------------------------------- #
#  VRChat-Bilder
# --------------------------------------------------------------------------- #
def pictures_backup_dir(pictures_dir):
    """~/Bilder/VRChat_backup — bewusst NEBEN dem Symlink ~/Bilder/VRChat,
    nicht darunter. Darunter laege es im Prefix und waere beim naechsten
    Proton-Wechsel mit weg."""
    return os.path.join(str(pictures_dir), "VRChat_backup")


def backup_vrchat_pictures(pictures_dir):
    """Kopiert die VRChat-Screenshots aus dem Prefix ins Bilder-Backup.
    (ok, anzahl_neuer_dateien). Schon vorhandene Bilder werden uebersprungen,
    damit wiederholtes Sichern nicht jedes Mal alles neu kopiert."""
    src = os.path.join(venv.vrchat_proton_prefix(), "Pictures", "VRChat")
    if not os.path.isdir(src):
        return False, 0
    dest = pictures_backup_dir(pictures_dir)
    copied = 0
    try:
        os.makedirs(dest, exist_ok=True)
        for root, _dirs, files in os.walk(src):
            for f in files:
                s = os.path.join(root, f)
                if os.path.islink(s):
                    continue
                rel = os.path.relpath(s, src)
                t = os.path.join(dest, rel)
                if os.path.exists(t) and os.path.getsize(t) == os.path.getsize(s):
                    continue          # schon gesichert
                os.makedirs(os.path.dirname(t), exist_ok=True)
                shutil.copy2(s, t)
                copied += 1
    except Exception as exc:
        log.warning("Bilder-Backup fehlgeschlagen: %s", exc)
        return False, copied
    return True, copied
