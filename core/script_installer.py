#!/usr/bin/env python3
"""
core/script_installer.py — Tools ueber ihr eigenes Installationsskript
======================================================================
Installationsmethode "script" im Tools-Tab: fuehrt das offizielle
``curl -fsSL <script_url> | bash`` eines Projekts in einem sichtbaren
Terminal aus (z. B. LinuxVR-ViewShot). Entfernt wird ueber dasselbe Skript
mit ``script_uninstall_args`` (Standard: ``uninstall``).

Felder in config/tools.json:
  script_url            : Roh-URL des install.sh (Pflicht fuer "script")
  script_uninstall_args : Argumente zum Entfernen (Standard: "uninstall")

Warum ein eigener Ordner mit Marker-Datei? Das fremde Skript legt seine
Dateien selbst ab; woran wir "von hier per Skript installiert" erkennen,
muss deshalb bei UNS liegen — sonst wuesste der Loeschen-Knopf nicht, ob er
das Skript oder z. B. yay fragen soll.
"""
import os
import shlex
import shutil
import subprocess
import time

from PySide6.QtCore import QThread, Signal

from logging_setup import get_logger

log = get_logger("script_installer")

SCRIPT_TOOLS_DIR = os.path.join(os.path.expanduser("~"), ".config",
                                "yakuda-connect", "tools", "script")
RUN_NAME = "run.sh"
STATUS_NAME = ".yakuda-status"     # "ok" | "fail" — vom Skript geschrieben
PID_NAME = ".yakuda-pid"
MARKER_NAME = ".installed"
MAX_WAIT_S = 3600


def tool_root(tool):
    """~/.config/yakuda-connect/tools/script/<key>"""
    return os.path.join(SCRIPT_TOOLS_DIR, tool["key"])


def _marker(tool):
    return os.path.join(tool_root(tool), MARKER_NAME)


def available(tool):
    """Kann "script" auf diesem System angeboten werden?"""
    return bool(tool.get("script_url")) and shutil.which("curl") is not None \
        and shutil.which("bash") is not None


def _command_present(tool):
    cmd = tool.get("start_cmd") or tool.get("key", "")
    local = os.path.join(os.path.expanduser("~"), ".local", "bin", cmd)
    return bool(cmd) and (shutil.which(cmd) is not None or os.path.exists(local))


def local_status(tool):
    """(installiert, version) — Version kennt das fremde Skript nicht -> ""."""
    return os.path.exists(_marker(tool)) and _command_present(tool), ""


def build_script(tool, uninstall=False):
    """Inhalt von run.sh — eigene Funktion, damit Tests ihn pruefen koennen."""
    root = tool_root(tool)
    url = tool.get("script_url", "")
    args = ""
    if uninstall:
        args = " -s -- " + (tool.get("script_uninstall_args") or "uninstall")
    marker_cmd = (f"rm -f {shlex.quote(_marker(tool))}" if uninstall
                  else f"touch {shlex.quote(_marker(tool))}")
    name = tool.get("name", tool.get("key", ""))
    return f"""#!/usr/bin/env bash
echo $$ > {shlex.quote(os.path.join(root, PID_NAME))}
set -o pipefail
echo "==> {name}: curl -fsSL {url} | bash{args}"
echo
if curl -fsSL {shlex.quote(url)} | bash{args}; then
    {marker_cmd}
    echo ok > {shlex.quote(os.path.join(root, STATUS_NAME))}
    echo
    echo "✔ OK"
    sleep 2
else
    echo fail > {shlex.quote(os.path.join(root, STATUS_NAME))}
    echo
    echo "✘ Fehler / Error — Enter zum Schliessen / press Enter to close"
    read -r _
fi
rm -f {shlex.quote(os.path.join(root, PID_NAME))}
"""


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class ScriptInstallWorker(QThread):
    """Fuehrt das Projekt-Skript im Terminal aus (installieren oder entfernen)."""
    status_signal = Signal(str)
    finished_signal = Signal(bool)

    def __init__(self, tool, uninstall=False):
        super().__init__()
        self.tool = tool
        self.uninstall = uninstall

    def run(self):
        from install_worker import find_terminal
        from cargo_installer import terminal_command
        from translations import tr

        root = tool_root(self.tool)
        run_sh = os.path.join(root, RUN_NAME)
        status_file = os.path.join(root, STATUS_NAME)
        pid_file = os.path.join(root, PID_NAME)

        terminal, exec_flags = find_terminal()
        if terminal is None:
            self.status_signal.emit(tr("tools_cargo_no_terminal"))
            self.finished_signal.emit(False)
            return
        try:
            os.makedirs(root, exist_ok=True)
            for p in (status_file, pid_file):
                if os.path.exists(p):
                    os.remove(p)
            with open(run_sh, "w", encoding="utf-8") as fh:
                fh.write(build_script(self.tool, self.uninstall))
            os.chmod(run_sh, 0o755)
        except OSError as exc:
            log.warning("run.sh nicht schreibbar: %s", exc)
            self.status_signal.emit(f"{tr('tools_install_error')}: {exc}")
            self.finished_signal.emit(False)
            return

        self.status_signal.emit(tr("tools_script_running"))
        started = time.time()
        try:
            subprocess.Popen(terminal_command(terminal, exec_flags, run_sh)).wait()
        except OSError as exc:
            log.warning("Terminal '%s' nicht startbar: %s", terminal, exc)
            self.status_signal.emit(f"{tr('tools_install_error')}: {exc}")
            self.finished_signal.emit(False)
            return

        # Manche Terminals kehren sofort zurueck -> auf Status/PID warten.
        while not os.path.exists(status_file) and time.time() - started < MAX_WAIT_S:
            pid = _read(pid_file)
            if pid.isdigit() and _pid_alive(int(pid)):
                time.sleep(1)
                continue
            if not pid and time.time() - started < 15:
                time.sleep(0.5)
                continue
            break

        ok = _read(status_file) == "ok"
        if not ok:
            log.warning("Skript-%s von %s fehlgeschlagen",
                        "Deinstallation" if self.uninstall else "Installation",
                        self.tool.get("key"))
        self.finished_signal.emit(ok)
