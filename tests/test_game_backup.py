#!/usr/bin/env python3
"""
tests/test_game_backup.py — Config-Backup/-Restore (v1.1.9)
===========================================================
Der Restore-Pfad ist die gefaehrlichste Stelle der ganzen App: er schreibt in
ein Steam-Prefix. In v1.1.4 hat genau dort ein 'rm -rf' auf Fedora Steam
zerlegt. Die Tests hier halten die Zusagen fest, die das verhindern sollen —
additiv kopieren, vorhandene Dateien beiseitelegen, nie ein Verzeichnis
ersetzen.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import vr_environment as venv        # noqa: E402
import game_backup as gb             # noqa: E402

APPID = "438100"


class BackupTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ycbackup")
        self.steam = os.path.join(self.tmp, ".local/share/Steam")
        self.user_dir = os.path.join(
            self.steam, "steamapps/compatdata", APPID,
            "pfx/drive_c/users/steamuser")
        self._orig_roots = venv.steam_data_roots
        self._orig_root = gb.BACKUP_ROOT
        venv.steam_data_roots = lambda: [self.steam]
        gb.BACKUP_ROOT = os.path.join(self.tmp, "backups")

    def tearDown(self):
        venv.steam_data_roots = self._orig_roots
        gb.BACKUP_ROOT = self._orig_root
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, content):
        path = os.path.join(self.user_dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return path

    def read(self, rel):
        with open(os.path.join(self.user_dir, rel)) as f:
            return f.read()


class TestWhatGetsBackedUp(BackupTestBase):
    def test_config_files_are_included(self):
        self.write("AppData/LocalLow/VRChat/VRChat/config.json", "{}")
        self.write("AppData/Roaming/Game/settings.ini", "a=1")
        self.write("Documents/save1.dat", "SAVE")
        count, _size = gb.estimate_size(APPID)
        self.assertEqual(count, 3)

    def test_logs_are_skipped(self):
        # VRChat-Logs sind gross und beim naechsten Start ohnehin neu da.
        self.write("AppData/LocalLow/VRChat/VRChat/config.json", "{}")
        self.write("AppData/LocalLow/VRChat/VRChat/output_log_2026.txt", "x" * 5000)
        self.write("AppData/LocalLow/VRChat/VRChat/crash.log", "x")
        count, _ = gb.estimate_size(APPID)
        self.assertEqual(count, 1, "Logs wurden mitgesichert")

    def test_tools_dir_is_skipped(self):
        # Tools/ enthaelt Binaries, die VRChat beim Login neu anlegt.
        self.write("AppData/LocalLow/VRChat/VRChat/config.json", "{}")
        self.write("AppData/LocalLow/VRChat/VRChat/Tools/yt-dlp.exe", "bin")
        count, _ = gb.estimate_size(APPID)
        self.assertEqual(count, 1, "Tools/ wurde mitgesichert")

    def test_missing_prefix_reports_nothing(self):
        count, size = gb.estimate_size("999999")
        self.assertEqual((count, size), (0, 0))

    def test_backup_without_prefix_fails_cleanly(self):
        ok, msg = gb.create_backup("999999")
        self.assertFalse(ok)
        self.assertEqual(msg, "no_prefix")


class TestRestoreIsNonDestructive(BackupTestBase):
    """Die Zusagen, die den v1.1.4-Fehler ausschliessen."""

    def _prepare(self):
        self.write("AppData/LocalLow/VRChat/VRChat/config.json", '{"fov":90}')
        self.write("Documents/save1.dat", "ORIGINAL")
        ok, _ = gb.create_backup(APPID, "VRChat", "proton-rtsp")
        self.assertTrue(ok)

    def test_restore_brings_files_back_after_prefix_reset(self):
        self._prepare()
        shutil.rmtree(os.path.join(self.user_dir, "AppData"))
        shutil.rmtree(os.path.join(self.user_dir, "Documents"))
        ok, msg = gb.restore_backup(APPID)
        self.assertTrue(ok, msg)
        self.assertEqual(self.read("AppData/LocalLow/VRChat/VRChat/config.json"),
                         '{"fov":90}')
        self.assertEqual(self.read("Documents/save1.dat"), "ORIGINAL")

    def test_existing_file_is_set_aside_not_overwritten_blindly(self):
        self._prepare()
        self.write("Documents/save1.dat", "NEUER STAND")
        gb.restore_backup(APPID)
        self.assertEqual(self.read("Documents/save1.dat"), "ORIGINAL")
        self.assertEqual(self.read("Documents/save1.dat.vor-restore"), "NEUER STAND",
                         "Der vorherige Stand wurde nicht gesichert")

    def test_unrelated_files_survive_the_restore(self):
        # Nichts ausserhalb des Backups darf angefasst werden.
        self._prepare()
        self.write("Documents/fremde_datei.txt", "NICHT ANFASSEN")
        self.write("AppData/Local/etwas.dat", "AUCH NICHT")
        gb.restore_backup(APPID)
        self.assertEqual(self.read("Documents/fremde_datei.txt"), "NICHT ANFASSEN")
        self.assertEqual(self.read("AppData/Local/etwas.dat"), "AUCH NICHT")

    def test_restore_without_backup_fails_cleanly(self):
        ok, msg = gb.restore_backup(APPID)
        self.assertFalse(ok)
        self.assertEqual(msg, "no_backup")

    def test_restore_without_prefix_fails_cleanly(self):
        # Der haeufigste Fall: direkt nach dem Proton-Wechsel, Spiel noch
        # nicht gestartet. Muss eine klare Meldung geben, nicht werfen.
        self._prepare()
        shutil.rmtree(os.path.join(
            self.steam, "steamapps/compatdata", APPID))
        ok, msg = gb.restore_backup(APPID)
        self.assertFalse(ok)
        self.assertEqual(msg, "no_prefix")

    def test_restore_is_repeatable(self):
        self._prepare()
        gb.restore_backup(APPID)
        ok, _ = gb.restore_backup(APPID)
        self.assertTrue(ok, "Zweiter Restore schlug fehl")
        self.assertEqual(self.read("Documents/save1.dat"), "ORIGINAL")


class TestBackupIsNotSelfDestructive(BackupTestBase):
    def test_second_backup_does_not_destroy_the_first(self):
        # Sonst zerstoert ein versehentlicher zweiter Klick genau das
        # Backup, das man gleich brauchen wuerde.
        self.write("Documents/save1.dat", "ERSTER STAND")
        gb.create_backup(APPID, "VRChat", "v1")
        self.write("Documents/save1.dat", "ZWEITER STAND")
        gb.create_backup(APPID, "VRChat", "v2")

        old = [d for d in os.listdir(gb.BACKUP_ROOT)
               if d.startswith(f"{APPID}.alt-")]
        self.assertEqual(len(old), 1, "Altes Backup wurde nicht beiseitegelegt")
        with open(os.path.join(gb.BACKUP_ROOT, old[0], "files",
                               "Documents/save1.dat")) as f:
            self.assertEqual(f.read(), "ERSTER STAND")

    def test_metadata_records_what_was_saved(self):
        self.write("Documents/save1.dat", "X")
        gb.create_backup(APPID, "VRChat", "proton-rtsp-11.0")
        info = gb.backup_info(APPID)
        self.assertEqual(info["name"], "VRChat")
        self.assertEqual(info["proton"], "proton-rtsp-11.0")
        self.assertEqual(info["files"], 1)
        self.assertTrue(info["created"])

    def test_has_backup_reflects_reality(self):
        self.assertFalse(gb.has_backup(APPID))
        self.write("Documents/save1.dat", "X")
        gb.create_backup(APPID)
        self.assertTrue(gb.has_backup(APPID))


class TestPicturesBackupLocation(unittest.TestCase):
    """Der Bilder-Backup-Ordner darf NICHT unter ~/Bilder/VRChat liegen.

    Sobald der Picture Fix gesetzt ist, ist ~/Bilder/VRChat ein Symlink ins
    Proton-Prefix. Ein Backup darunter laege im Prefix — also genau dort, wo
    es beim naechsten Proton-Wechsel mit geloescht wuerde.
    """

    def test_backup_is_a_sibling_of_the_symlink(self):
        pics = "/home/test/Bilder"
        backup = gb.pictures_backup_dir(pics)
        self.assertEqual(os.path.dirname(backup), pics)
        self.assertNotEqual(backup, os.path.join(pics, "VRChat"))
        self.assertFalse(backup.startswith(os.path.join(pics, "VRChat") + os.sep),
                         "Backup liegt im symlinkten Ordner und damit im Prefix")


if __name__ == "__main__":
    unittest.main()


class TestCacheIsNotBackedUp(BackupTestBase):
    """Der Grund fuer diese Klasse: mit einer Liste exakter Verzeichnisnamen
    rutschte VRChats "Cache-WindowsPlayer" durch — ein Backup war dadurch
    ~3,7 GB statt weniger Kilobyte gross. Fast alles davon laedt das Spiel
    beim naechsten Start ohnehin neu herunter.
    """

    def test_vrchat_world_cache_is_skipped(self):
        self.write("AppData/LocalLow/VRChat/VRChat/config.json", "{}")
        self.write("AppData/LocalLow/VRChat/VRChat/Cache-WindowsPlayer/w1.dat",
                   "x" * 100000)
        count, size = gb.estimate_size(APPID)
        self.assertEqual(count, 1)
        self.assertLess(size, 1000, "Cache wurde mitgesichert")

    def test_various_cache_dir_names_are_skipped(self):
        self.write("AppData/LocalLow/Game/config.json", "{}")
        for name in ("HTTPCache", "ShaderCache", "Cache-WindowsPlayer",
                     "il2cpp_cache", "Crashes", "Logs", "Temp"):
            self.write(f"AppData/LocalLow/Game/{name}/file.dat", "x" * 5000)
        count, _ = gb.estimate_size(APPID)
        self.assertEqual(count, 1, "Mindestens ein Cache-Ordner rutschte durch")

    def test_oversized_files_are_skipped(self):
        # Wer 100 MB in einer Datei hat, hat kein Konfigurationsfile erwischt.
        self.write("AppData/LocalLow/Game/config.json", "{}")
        big = self.write("AppData/LocalLow/Game/asset.dat", "")
        with open(big, "wb") as f:
            f.truncate(gb.MAX_FILE_BYTES + 1)
        count, _ = gb.estimate_size(APPID)
        self.assertEqual(count, 1)

    def test_normal_config_files_still_survive_the_filter(self):
        # Der Filter darf nicht so grob sein, dass echte Configs wegfallen.
        for rel in ("AppData/LocalLow/Game/settings.json",
                    "AppData/LocalLow/Game/Cookies",
                    "AppData/Roaming/Game/prefs.ini",
                    "Documents/save01.sav"):
            self.write(rel, "data")
        count, _ = gb.estimate_size(APPID)
        self.assertEqual(count, 4)


class TestNewestProtonWins(unittest.TestCase):
    """Die games.json nennt zwangslaeufig einen Stand von gestern. Liegt eine
    neuere passende Version in compatibilitytools.d, muss sie gewinnen —
    sonst bleibt der Nutzer auf einer alten Version sitzen, obwohl die neue
    daneben liegt."""

    def setUp(self):
        import games as games_db
        self.games_db = games_db
        self.tmp = tempfile.mkdtemp(prefix="ct")
        self._orig = games_db.compat_tools_dirs
        games_db.compat_tools_dirs = lambda: [self.tmp]

    def tearDown(self):
        self.games_db.compat_tools_dirs = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _install(self, *names):
        for n in names:
            os.makedirs(os.path.join(self.tmp, n), exist_ok=True)

    def test_newer_build_beats_the_pinned_one(self):
        proton = {"protonplus_runner": "proton-ge-rtsp",
                  "version": "proton-rtsp-11.0-20260703"}
        self._install("proton-rtsp-11.0-20260703", "proton-rtsp-11.0-20260815")
        tool, found, kind = self.games_db.resolve_steam_tool(proton)
        self.assertTrue(found)
        self.assertEqual(tool, "proton-rtsp-11.0-20260815")
        self.assertEqual(kind, "newer")

    def test_pinned_build_is_used_when_it_is_the_newest(self):
        proton = {"protonplus_runner": "proton-ge-rtsp",
                  "version": "proton-rtsp-11.0-20260815"}
        self._install("proton-rtsp-11.0-20260609-2", "proton-rtsp-11.0-20260815")
        tool, _found, kind = self.games_db.resolve_steam_tool(proton)
        self.assertEqual(tool, "proton-rtsp-11.0-20260815")
        self.assertEqual(kind, "exact")

    def test_only_matching_flavour_is_considered(self):
        # GE-Proton darf nicht als rtsp-Build durchgehen.
        proton = {"protonplus_runner": "proton-ge-rtsp", "version": "proton-rtsp-x"}
        self._install("GE-Proton10-26", "proton-cachyos-11.0-20260703")
        _tool, found, _kind = self.games_db.resolve_steam_tool(proton)
        self.assertFalse(found)

    def test_nothing_installed_reports_not_installed(self):
        proton = {"protonplus_runner": "proton-ge", "version": "GE-Proton10-26"}
        tool, found, kind = self.games_db.resolve_steam_tool(proton)
        self.assertIsNone(tool)
        self.assertFalse(found)
        self.assertEqual(kind, "not_installed")

    def test_valve_proton_still_means_steam_default(self):
        tool, found, kind = self.games_db.resolve_steam_tool(
            {"protonplus_runner": None, "version": "Proton 11"})
        self.assertIsNone(tool)
        self.assertTrue(found)
        self.assertEqual(kind, "steam_default")


class TestVRCVideoCacherInstall(unittest.TestCase):
    """Der Installer legt eine ausfuehrbare Datei an und traegt sie in eine
    Desktop-Verknuepfung ein. Wenn dort etwas anderes ankommt als eine
    Linux-Binary — GitHub liefert bei Problemen HTML mit Status 200 — wuerde
    die App eine Fehlerseite ausfuehrbar machen. Deshalb die ELF-Pruefung.
    """

    def setUp(self):
        import vrcvideocacher_install as vci
        self.vci = vci
        self.tmp = tempfile.mkdtemp(prefix="vci")
        self._orig = {k: getattr(vci, k) for k in
                      ("INSTALL_DIR", "BINARY_PATH", "DESKTOP_DIR",
                       "DESKTOP_FILE", "ICON_DIR", "ICON_FILE")}
        vci.INSTALL_DIR = os.path.join(self.tmp, "tools")
        vci.BINARY_PATH = os.path.join(vci.INSTALL_DIR, "VRCVideoCacher")
        vci.DESKTOP_DIR = os.path.join(self.tmp, "applications")
        vci.DESKTOP_FILE = os.path.join(vci.DESKTOP_DIR, "yakuda-vrcvideocacher.desktop")
        vci.ICON_DIR = os.path.join(self.tmp, "icons")
        vci.ICON_FILE = os.path.join(vci.ICON_DIR, "yakuda-vrcvideocacher.svg")

    def tearDown(self):
        for k, v in self._orig.items():
            setattr(self.vci, k, v)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fake_binary(self, content=None):
        os.makedirs(self.vci.INSTALL_DIR, exist_ok=True)
        with open(self.vci.BINARY_PATH, "wb") as f:
            f.write(content if content is not None
                    else b"\x7fELF" + b"\0" * self.vci.MIN_BINARY_BYTES)
        os.chmod(self.vci.BINARY_PATH, 0o755)

    def test_html_error_page_is_rejected(self):
        # Der Fall, der ohne Pruefung eine Webseite ausfuehrbar machen wuerde.
        path = os.path.join(self.tmp, "page.html")
        with open(path, "w") as f:
            f.write("<html><body>404</body></html>")
        self.assertFalse(self.vci._looks_like_elf(path))

    def test_truncated_download_is_rejected(self):
        path = os.path.join(self.tmp, "short")
        with open(path, "wb") as f:
            f.write(b"\x7fELF" + b"\0" * 100)      # ELF, aber viel zu klein
        self.assertFalse(self.vci._looks_like_elf(path))

    def test_real_looking_binary_is_accepted(self):
        path = os.path.join(self.tmp, "bin")
        with open(path, "wb") as f:
            f.write(b"\x7fELF" + b"\0" * self.vci.MIN_BINARY_BYTES)
        self.assertTrue(self.vci._looks_like_elf(path))

    def test_is_installed_requires_executable_bit(self):
        self._fake_binary()
        self.assertTrue(self.vci.is_installed())
        os.chmod(self.vci.BINARY_PATH, 0o644)
        self.assertFalse(self.vci.is_installed())

    def test_desktop_entry_points_at_the_installed_binary(self):
        self._fake_binary()
        ok, _path = self.vci.create_desktop_entry()
        self.assertTrue(ok)
        with open(self.vci.DESKTOP_FILE) as f:
            content = f.read()
        self.assertIn(f"Exec={self.vci.BINARY_PATH}", content)
        self.assertIn("Type=Application", content)
        self.assertIn("Icon=yakuda-vrcvideocacher", content)
        self.assertTrue(os.path.isfile(self.vci.ICON_FILE))

    def test_icon_is_valid_svg(self):
        import xml.etree.ElementTree as ET
        self._fake_binary()
        self.vci.create_desktop_entry()
        ET.parse(self.vci.ICON_FILE)      # wirft bei kaputtem XML

    def test_no_desktop_entry_without_binary(self):
        ok, msg = self.vci.create_desktop_entry()
        self.assertFalse(ok)
        self.assertEqual(msg, "not_installed")

    def test_uninstall_removes_what_was_installed(self):
        self._fake_binary()
        self.vci.create_desktop_entry()
        self.vci.uninstall()
        self.assertFalse(os.path.exists(self.vci.BINARY_PATH))
        self.assertFalse(os.path.exists(self.vci.DESKTOP_FILE))
        self.assertFalse(os.path.exists(self.vci.ICON_FILE))

    def test_app_finds_its_own_installation(self):
        # Sonst installiert die App etwas, das sie selbst nicht sieht, und
        # der Autostart-Schalter bliebe ausgegraut.
        import games as games_db
        self._fake_binary()
        games_db.refresh_vrcvideocacher_path()
        self.assertEqual(games_db.find_vrcvideocacher(), self.vci.BINARY_PATH)
        games_db.refresh_vrcvideocacher_path()
