#!/usr/bin/env python3
"""
cargo_installer.py — Tools per 'cargo install' einrichten
==========================================================
Fuer Werkzeuge, die es nur als Rust-Crate gibt (z. B. obah) oder deren
AUR-Paket auf Nicht-Arch-Systemen nicht verfuegbar ist.

Ablauf fuer obah (key="obah", crate="obah", start_cmd="obah"):

  1. Ordner anlegen:
        ~/.config/yakuda-connect/tools/cargo/obah/

  2. Dort ein Skript install.sh schreiben und in einem SICHTBAREN Terminal
     ausfuehren. Das Skript
        * zieht einen C-Compiler nach, falls keiner da ist (Rust braucht ihn
          als Linker),
        * installiert Rust/Cargo, falls es fehlt oder zu alt ist,
        * baut das Crate mit
              cargo install --locked obah --root <ordner>
        * verlinkt ~/.local/bin/obah -> <ordner>/bin/obah

  3. Jede Ausgabe landet zusaetzlich in <ordner>/install.log.

Git-Quellen und Systembibliotheken (z. B. XR HOTAS):
  "cargo_git"      -> cargo install --git <url> statt vom crates.io-Index.
                      Update-Check vergleicht den installierten Commit mit
                      dem neuesten auf dem Server.
  "cargo_sys_deps" -> {"arch": [...], "fedora": [...], "debian": [...],
                      "suse": [...]} — Pakete, die vor dem Build da sein
                      muessen (XR HOTAS linkt gegen libopenxr_loader).
                      Fehlende werden im Terminal per sudo nachinstalliert.

Warum --root?
  'cargo install' schert sich nicht um das aktuelle Verzeichnis — ohne
  --root landet die Binary in ~/.cargo/bin, egal wo man gerade steht. Mit
  --root gehoert alles zum Tool-Ordner: Status erkennen (.crates2.json),
  Loeschen (Ordner weg) und Aktualisieren (nochmal installieren) werden
  damit trivial.

Warum ein Terminal?
  Die Installation kann sudo brauchen (Compiler, Distro-Rust) und dauert je
  nach Rechner mehrere Minuten. Wer auf einen stummen Knopf starrt, bricht
  ab. Im Terminal sieht man jeden Schritt — und bei einem Fehler bleibt das
  Fenster offen, bis Enter gedrueckt wird.
"""
import json
import os
import shlex
import shutil
import subprocess
import time
import urllib.error
import urllib.request

from PySide6.QtCore import QThread, Signal

from appimage_installer import TOOLS_DIR, LOCAL_BIN, _ensure_local_bin_on_path
from logging_setup import get_logger

log = get_logger("cargo_installer")

CARGO_TOOLS_DIR = os.path.join(TOOLS_DIR, "cargo")

# obah nutzt Rust-Edition 2024 -> braucht mindestens Rust 1.85.
# Ubuntu 24.04 liefert per apt nur 1.75; dann springt rustup ein.
MIN_RUST = (1, 85)

SCRIPT_NAME = "install.sh"
LOG_NAME    = "install.log"
STATUS_NAME = ".yakuda-status"   # "ok" | "fail" — vom Skript geschrieben
PID_NAME    = ".yakuda-pid"      # PID des Skripts, solange es laeuft

# Wie lange hoechstens gewartet wird. Ein Rust-Build auf einem schwachen
# Rechner kann dauern, aber nicht ewig.
MAX_WAIT_S = 3 * 3600


# --------------------------------------------------------------------------- #
#  Pfade
# --------------------------------------------------------------------------- #
def crate_name(tool):
    return tool.get("crate") or tool["key"]


def git_url(tool):
    """Git-Repository fuer 'cargo install --git', sonst ''."""
    return tool.get("cargo_git") or ""


def sys_deps(tool):
    """{"arch": [...], "fedora": [...], "debian": [...], "suse": [...]}"""
    deps = tool.get("cargo_sys_deps") or {}
    return {k: list(v) for k, v in deps.items() if isinstance(v, list) and v}


def binary_name(tool):
    return tool.get("start_cmd") or crate_name(tool)


def tool_root(tool):
    """~/.config/yakuda-connect/tools/cargo/<key>"""
    return os.path.join(CARGO_TOOLS_DIR, tool["key"])


def binary_path(tool):
    return os.path.join(tool_root(tool), "bin", binary_name(tool))


def link_path(tool):
    return os.path.join(LOCAL_BIN, binary_name(tool))


def log_path(tool):
    return os.path.join(tool_root(tool), LOG_NAME)


# --------------------------------------------------------------------------- #
#  Status
# --------------------------------------------------------------------------- #
def _install_key(tool):
    """
    Eintrag aus <root>/.crates2.json — die Buchfuehrung von cargo selbst:
      'obah 0.1.1 (registry+https://github.com/rust-lang/crates.io-index)'
      'xr-hotas 0.1.0 (git+https://github.com/galister/xr-hotas.git#ade19009...)'
    """
    path = os.path.join(tool_root(tool), ".crates2.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return ""
    name = crate_name(tool)
    for key in (data.get("installs") or {}):
        parts = key.split()
        if len(parts) >= 2 and parts[0] == name:
            return key
    return ""


def installed_version(tool):
    key = _install_key(tool)
    return key.split()[1] if key else ""


def installed_revision(tool):
    """Commit-Hash einer Git-Installation (Teil nach '#'), sonst ''."""
    key = _install_key(tool)
    if "#" not in key:
        return ""
    return key.rsplit("#", 1)[1].rstrip(")").strip()


def display_version(tool):
    """'0.1.1' bzw. bei Git '0.1.0 · ade1900' — Versionsnummern aendern sich
    bei Git-Projekten selten, der Commit schon."""
    ver = installed_version(tool)
    rev = installed_revision(tool)
    return f"{ver} · {rev[:7]}" if ver and rev else ver


def local_status(tool):
    """(installiert, version) — rein lokal, ohne Netz."""
    installed = os.path.isfile(binary_path(tool)) and os.access(binary_path(tool), os.X_OK)
    return installed, (display_version(tool) if installed else "")


def latest_version(tool, timeout=8):
    """Neueste Version laut crates.io, '' bei Fehler (kein Netz o. Ae.)."""
    if git_url(tool):
        return ""
    url = f"https://crates.io/api/v1/crates/{crate_name(tool)}"
    # crates.io lehnt Anfragen ohne User-Agent ab.
    req = urllib.request.Request(url, headers={"User-Agent": "yakuda-connect"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        crate = data.get("crate") or {}
        return crate.get("max_stable_version") or crate.get("max_version") or ""
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        log.debug("crates.io nicht erreichbar: %s", exc)
        return ""


def latest_revision(tool, timeout=8):
    """Neuester Commit (HEAD) des Git-Repos, '' bei Fehler."""
    url = git_url(tool)
    if not url:
        return ""
    if shutil.which("git"):
        try:
            res = subprocess.run(["git", "ls-remote", url, "HEAD"],
                                 capture_output=True, text=True, timeout=timeout)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.split()[0]
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.debug("git ls-remote fehlgeschlagen: %s", exc)
    # Ohne git: GitHub-API (nur fuer github.com-URLs)
    prefix = "https://github.com/"
    if url.startswith(prefix):
        repo = url[len(prefix):].removesuffix(".git").strip("/")
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/commits/HEAD",
            headers={"User-Agent": "yakuda-connect", "Accept": "application/vnd.github+json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "ignore")).get("sha", "")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            log.debug("GitHub-API nicht erreichbar: %s", exc)
    return ""


def update_available(tool):
    """True, wenn es eine neuere Version (crates.io) bzw. einen neueren Commit gibt.
    Kein Netz -> False (lieber kein Update anzeigen als ein falsches)."""
    if git_url(tool):
        have = installed_revision(tool)
        latest = latest_revision(tool)
        return bool(have and latest and not (latest.startswith(have) or have.startswith(latest)))
    have = installed_version(tool)
    latest = latest_version(tool)
    return bool(have and latest and latest != have)


def uninstall(tool):
    """Symlink und Tool-Ordner entfernen. Die Rust-Toolchain bleibt."""
    link = link_path(tool)
    try:
        # Nur UNSEREN Link entfernen — eine fremde Datei gleichen Namens
        # (z. B. aus dem AUR-Paket) bleibt unangetastet.
        if os.path.islink(link) and os.path.realpath(link) == os.path.realpath(binary_path(tool)):
            os.remove(link)
    except OSError as exc:
        log.debug("uninstall: Link ignoriert — %s", exc)
    shutil.rmtree(tool_root(tool), ignore_errors=True)


# --------------------------------------------------------------------------- #
#  Installationsskript
# --------------------------------------------------------------------------- #
_TEXTS = {
    "de": {
        "title":    "Installiere {crate} mit Cargo",
        "step_cc":  "C-Compiler (Rust braucht ihn als Linker)",
        "step_deps": "Systembibliotheken",
        "step_rust": "Rust & Cargo (mindestens {minver})",
        "step_build": "cargo install {crate}  (kann einige Minuten dauern)",
        "err_deps": "Benoetigte Systembibliotheken konnten nicht installiert werden.",
        "no_deps_pm": "Unbekannte Distribution — bitte diese Bibliothek von Hand installieren: {hint}",
        "found":    "gefunden",
        "missing":  "fehlt — wird installiert (sudo-Passwort noetig)",
        "rustup":   "Installiere aktuelles Rust ueber rustup (nur fuer deinen Benutzer, kein sudo)",
        "too_old":  "Vorhandenes Rust ist zu alt",
        "no_pm":    "Unbekannte Distribution — bitte gcc von Hand installieren und erneut versuchen.",
        "steamos":  "SteamOS: Das System ist schreibgeschuetzt und hat keinen C-Compiler bzw. keine Entwicklerpakete. Baue das Tool in einer Distrobox (z. B. Arch) oder nimm eine fertige AppImage-Version, falls es eine gibt.",
        "no_curl":  "Weder curl noch wget gefunden — bitte eins davon installieren.",
        "err_cc":   "Kein C-Compiler verfuegbar.",
        "err_rust": "Rust/Cargo konnte nicht eingerichtet werden.",
        "err_build": "'cargo install' ist fehlgeschlagen (Fehlermeldung siehe oben).",
        "err_bin":  "Build meldet Erfolg, aber die Datei fehlt:",
        "failed":   "Installation fehlgeschlagen",
        "logfile":  "Komplettes Protokoll:",
        "enter":    "Enter druecken zum Schliessen ... ",
        "done":     "Fertig! Startbefehl:",
        "closing":  "Dieses Fenster schliesst sich gleich automatisch ...",
    },
    "en": {
        "title":    "Installing {crate} with Cargo",
        "step_cc":  "C compiler (Rust needs it as linker)",
        "step_deps": "System libraries",
        "step_rust": "Rust & Cargo (at least {minver})",
        "step_build": "cargo install {crate}  (may take a few minutes)",
        "err_deps": "Required system libraries could not be installed.",
        "no_deps_pm": "Unknown distribution — please install this library manually: {hint}",
        "found":    "found",
        "missing":  "missing — installing (sudo password required)",
        "rustup":   "Installing current Rust via rustup (for your user only, no sudo)",
        "too_old":  "Installed Rust is too old",
        "no_pm":    "Unknown distribution — please install gcc manually and try again.",
        "steamos":  "SteamOS: the system is read-only and has no C compiler or development packages. Build the tool inside a Distrobox (e.g. Arch) or use a ready-made AppImage if there is one.",
        "no_curl":  "Neither curl nor wget found — please install one of them.",
        "err_cc":   "No C compiler available.",
        "err_rust": "Could not set up Rust/Cargo.",
        "err_build": "'cargo install' failed (see error message above).",
        "err_bin":  "Build reported success, but the file is missing:",
        "failed":   "Installation failed",
        "logfile":  "Full log:",
        "enter":    "Press Enter to close ... ",
        "done":     "Done! Start command:",
        "closing":  "This window will close automatically ...",
    },
}


def build_script(tool, lang="de"):
    """
    Der Inhalt von install.sh. Eigene Funktion, damit Tests ihn pruefen
    koennen, ohne ein Terminal zu oeffnen.
    """
    t = _TEXTS.get(lang, _TEXTS["en"])
    crate = crate_name(tool)
    minver = f"{MIN_RUST[0]}.{MIN_RUST[1]}"
    q = shlex.quote

    def msg(key, **kw):
        return q(t[key].format(crate=crate, minver=minver, **kw))

    deps = sys_deps(tool)
    names = ["step_cc"] + (["step_deps"] if deps else []) + ["step_rust", "step_build"]
    total = len(names)

    def step(key):
        n = names.index(key) + 1
        return q(f"{n}/{total}  " + t[key].format(crate=crate, minver=minver))

    # cargo install: Registry-Crate oder Git-Repo. Bei Git immer --force,
    # sonst baut cargo einen neueren Commit u. U. nicht neu.
    if git_url(tool):
        install_args = f'--git {q(git_url(tool))} --force'
        if tool.get("crate"):
            install_args += f' {q(tool["crate"])}'
    else:
        install_args = '"$CRATE"'

    if deps:
        def arr(key):
            return " ".join(q(p) for p in deps.get(key, []))
        hint = " / ".join(" ".join(v) for v in deps.values())
        deps_block = f"""
# --------------------------------------------------- Systembibliotheken
step {step("step_deps")}
MISSING=()
if   is_arch;   then for p in {arr("arch")};   do pacman -Q "$p" >/dev/null 2>&1 || MISSING+=("$p"); done
elif is_fedora; then for p in {arr("fedora")}; do rpm -q "$p"    >/dev/null 2>&1 || MISSING+=("$p"); done
elif is_debian; then for p in {arr("debian")}; do dpkg -s "$p"   >/dev/null 2>&1 || MISSING+=("$p"); done
elif is_suse;   then for p in {arr("suse")};   do rpm -q "$p"    >/dev/null 2>&1 || MISSING+=("$p"); done
else fail {q(t["no_deps_pm"].format(hint=hint))}
fi
if [ ${{#MISSING[@]}} -eq 0 ]; then
    ok {q(t["found"])}
else
    echo {msg("missing")}: "${{MISSING[*]}}"
    is_steamos && fail {msg("steamos")}
    if   is_arch;   then sudo pacman -S --needed --noconfirm "${{MISSING[@]}}"
    elif is_fedora; then sudo dnf install -y "${{MISSING[@]}}"
    elif is_debian; then
        # Kein '&&': ein kaputtes Fremd-Repo (alte PPA o. Ae.) laesst
        # 'apt-get update' scheitern, die Paketlisten der Distro sind aber
        # trotzdem aktuell — installieren klappt dann meist trotzdem.
        sudo apt-get update; sudo apt-get install -y "${{MISSING[@]}}"
    elif is_suse;   then sudo zypper install -y "${{MISSING[@]}}"
    fi || fail {msg("err_deps")}
    ok "${{MISSING[*]}}"
fi
"""
    else:
        deps_block = ""

    return f"""#!/usr/bin/env bash
# Automatisch erzeugt von yakuda-connect — Cargo-Installation von {crate}.
# Kann jederzeit von Hand erneut gestartet werden:  bash {SCRIPT_NAME}

ROOT={q(tool_root(tool))}
CRATE={q(crate)}
BIN={q(binary_path(tool))}
LINK={q(link_path(tool))}
LOG="$ROOT/{LOG_NAME}"
STATUS="$ROOT/{STATUS_NAME}"
MIN_MAJOR={MIN_RUST[0]}
MIN_MINOR={MIN_RUST[1]}

mkdir -p "$ROOT" && cd "$ROOT" || exit 1
rm -f "$STATUS"
echo $$ > "$ROOT/{PID_NAME}"
trap 'rm -f "$ROOT/{PID_NAME}"' EXIT

# Alles zusaetzlich ins Protokoll schreiben.
exec > >(tee "$LOG") 2>&1
export CARGO_TERM_COLOR=always

step() {{ echo; printf '\\033[1;36m=== %s ===\\033[0m\\n' "$1"; }}
ok()   {{ printf '\\033[1;32m✔\\033[0m %s\\n' "$1"; }}

fail() {{
    echo
    printf '\\033[1;31m✖ %s\\033[0m\\n' {msg("failed")}
    echo "  $1"
    echo
    echo {msg("logfile")} "$LOG"
    echo fail > "$STATUS"
    echo
    read -rp {msg("enter")} _
    exit 1
}}

# rustup aus einem frueheren Lauf einbinden — die App selbst hat ~/.cargo/bin
# oft nicht im PATH, weil sie nicht aus einer Login-Shell gestartet wurde.
[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"

OS_IDS=""
if [ -r /etc/os-release ]; then
    . /etc/os-release
    OS_IDS="$ID $ID_LIKE"
fi
# SteamOS (und andere schreibgeschuetzte Arch-Abkoemmlinge): pacman ist da,
# darf aber nichts installieren. Muss VOR is_arch geprueft werden.
is_steamos() {{ [[ " $OS_IDS " == *" steamos "* || " $OS_IDS " == *" chimeraos "* ]]; }}
is_arch()   {{ [[ "$OS_IDS" == *arch* ]] || command -v pacman >/dev/null; }}
is_fedora() {{ [[ "$OS_IDS" == *fedora* || "$OS_IDS" == *rhel* ]] || command -v dnf >/dev/null; }}
is_debian() {{ [[ "$OS_IDS" == *debian* || "$OS_IDS" == *ubuntu* ]] || command -v apt-get >/dev/null; }}
is_suse()   {{ [[ "$OS_IDS" == *suse* ]] || command -v zypper >/dev/null; }}

rust_new_enough() {{
    local v major rest minor
    v=$(rustc --version 2>/dev/null | awk '{{print $2}}')
    [ -n "$v" ] || return 1
    major=${{v%%.*}}; rest=${{v#*.}}; minor=${{rest%%.*}}
    [ "$major" -gt "$MIN_MAJOR" ] || {{ [ "$major" -eq "$MIN_MAJOR" ] && [ "$minor" -ge "$MIN_MINOR" ]; }}
}}
rust_ready() {{ command -v cargo >/dev/null && rust_new_enough; }}

install_rustup() {{
    echo {msg("rustup")}
    if command -v rustup >/dev/null; then
        rustup toolchain install stable --profile minimal && rustup default stable
    elif command -v curl >/dev/null; then
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
    elif command -v wget >/dev/null; then
        wget -qO- https://sh.rustup.rs | sh -s -- -y --profile minimal
    else
        fail {msg("no_curl")}
    fi
    [ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
}}

printf '\\033[1m%s\\033[0m\\n' {msg("title")}
echo "→ $ROOT"

# ---------------------------------------------------------------- Linker
step {step("step_cc")}
if command -v cc >/dev/null; then
    ok "cc {t['found']}"
else
    echo {msg("missing")}
    if   is_steamos; then fail {msg("steamos")}
    elif is_arch;   then sudo pacman -S --needed --noconfirm gcc
    elif is_fedora; then sudo dnf install -y gcc
    elif is_debian; then sudo apt-get update; sudo apt-get install -y build-essential
    elif is_suse;   then sudo zypper install -y gcc
    else fail {msg("no_pm")}
    fi
    command -v cc >/dev/null || fail {msg("err_cc")}
    ok "cc"
fi

{deps_block}
# ---------------------------------------------------------- Rust & Cargo
step {step("step_rust")}
if ! rust_ready; then
    if command -v cargo >/dev/null; then
        echo {msg("too_old")}: "$(rustc --version 2>/dev/null)"
    elif ! is_steamos && {{ is_arch || is_fedora; }}; then
        # Arch und Fedora liefern aktuelles Rust aus den eigenen Repos.
        # Ubuntu/Debian sind zu alt -> dort direkt rustup (ohne sudo).
        echo {msg("missing")}
        if is_arch; then sudo pacman -S --needed --noconfirm rust
        else             sudo dnf install -y cargo rust
        fi
    fi
    rust_ready || install_rustup
fi
rust_ready || fail {msg("err_rust")}
ok "$(cargo --version)"

# ------------------------------------------------------------ Build
step {step("step_build")}
# $ROOT/bin kurz in den PATH, sonst warnt cargo "add ... to your PATH" —
# unnoetig, der Startbefehl kommt ueber den Link in ~/.local/bin.
PATH="$ROOT/bin:$PATH" cargo install --locked {install_args} --root "$ROOT" || fail {msg("err_build")}
[ -x "$BIN" ] || fail {msg("err_bin")}" $BIN"

mkdir -p "$(dirname "$LINK")"
ln -sfn "$BIN" "$LINK"

echo ok > "$STATUS"
echo
ok {msg("done")}" $(basename "$LINK")"
echo {msg("closing")}
sleep 4
"""


# --------------------------------------------------------------------------- #
#  Worker
# --------------------------------------------------------------------------- #
def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def terminal_command(terminal, exec_flags, script):
    """
    Startbefehl fuer das Terminal.

    gnome-terminal kehrt ohne --wait sofort zurueck (das Fenster gehoert dem
    gnome-terminal-server) — wir wuerden dann 'fertig' melden, waehrend der
    Build noch laeuft. Fuer alle anderen Terminals faengt die PID-Datei das ab.
    """
    flags = list(exec_flags or [])
    if terminal == "gnome-terminal":
        flags = ["--wait"] + flags
    return [terminal] + flags + ["bash", script]


class CargoInstallWorker(QThread):
    """Schreibt install.sh in den Tool-Ordner und fuehrt es im Terminal aus."""
    status_signal = Signal(str)
    finished_signal = Signal(bool)

    def __init__(self, tool, lang="de"):
        super().__init__()
        self.tool = tool
        self.lang = lang

    def run(self):
        from install_worker import find_terminal
        from translations import tr

        root = tool_root(self.tool)
        script = os.path.join(root, SCRIPT_NAME)
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
            with open(script, "w", encoding="utf-8") as fh:
                fh.write(build_script(self.tool, self.lang))
            os.chmod(script, 0o755)
            _ensure_local_bin_on_path()
        except OSError as exc:
            log.warning("install.sh nicht schreibbar: %s", exc)
            self.status_signal.emit(f"{tr('tools_install_error')}: {exc}")
            self.finished_signal.emit(False)
            return

        self.status_signal.emit(tr("tools_cargo_running"))
        cmd = terminal_command(terminal, exec_flags, script)
        started = time.time()
        try:
            subprocess.Popen(cmd).wait()
        except OSError as exc:
            log.warning("Terminal '%s' nicht startbar: %s", terminal, exc)
            self.status_signal.emit(f"{tr('tools_install_error')}: {exc}")
            self.finished_signal.emit(False)
            return

        # Manche Terminals kehren sofort zurueck, obwohl das Skript noch
        # laeuft. Entscheidend ist deshalb die Status-Datei, nicht der
        # Returncode: solange die PID lebt, wird gewartet.
        while not os.path.exists(status_file) and time.time() - started < MAX_WAIT_S:
            pid = _read(pid_file)
            if pid.isdigit() and _pid_alive(int(pid)):
                time.sleep(1)
                continue
            if not pid and time.time() - started < 15:
                time.sleep(0.5)   # Skript evtl. noch nicht gestartet
                continue
            break                  # Fenster geschlossen / abgebrochen

        ok = _read(status_file) == "ok" and local_status(self.tool)[0]
        if not ok:
            log.warning("Cargo-Installation von %s fehlgeschlagen — siehe %s",
                        crate_name(self.tool), log_path(self.tool))
        self.finished_signal.emit(ok)
