#!/usr/bin/env python3
"""
core/cli.py — Terminal-Modus (ohne Oberflaeche)
==============================================
Fuer alle, die unter VR jedes MB RAM brauchen: die wichtigsten Schalter
ohne Qt. Dieses Modul (und alles, was es importiert) darf PySide6 NIE
laden — sonst ist der ganze Sinn weg. tests/test_cli.py prueft das.

Aufruf:
    yakuda-connect --cli                 interaktives Menue
    yakuda-connect --cli <befehl> [wert] einzelner Befehl

Kurzbefehle (legt core/cli_install.py an, bzw. AUR/install.sh):
    YC-help, YC-status, YC-wivrn-toggle, YC-openvr, YC-encoder, YC-GPU,
    YC-killapps, YC-autostart-reset, YC-pairing

Mit Wert laeuft ein Befehl ohne Rueckfrage (gut fuer Skripte):
    YC-encoder vaapi     YC-GPU 2     YC-openvr 0
"""
import os
import select
import shutil
import subprocess
import sys
import time

import autostart_runner
import cli_install
import config_manager
import gpu_select
import paths
import vr_environment as venv
import wivrn_server
from jsonio import update_json
from logging_setup import get_logger
from translations import set_language, tr
from version import APP_VERSION

log = get_logger("cli")

SERVER_LOG = paths.cache_file("wivrn-server.log")

# Gleiche Liste wie im Streaming-Tab. Der Text ist zugleich der Wert, der
# gespeichert wird (config_manager.sync_with_wivrn macht .lower() daraus).
ENCODERS = ["Auto", "nvenc", "vaapi", "Vulkan", "x264"]
ENCODER_HINTS = {
    "Auto": "streaming_enc_auto",
    "nvenc": "streaming_enc_nvenc",
    "vaapi": "streaming_enc_vaapi",
    "Vulkan": "streaming_enc_vulkan",
    "x264": "streaming_enc_x264",
}


# --------------------------------------------------------------------------- #
#  Ausgabe-Helfer
# --------------------------------------------------------------------------- #
def _color(code, text):
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return f"\033[{code}m{text}\033[0m"


def green(t): return _color("32", t)
def red(t): return _color("31", t)
def yellow(t): return _color("33", t)
def bold(t): return _color("1", t)
def dim(t): return _color("2", t)


def _interactive():
    return sys.stdin.isatty()


def _ask(prompt):
    """Eingabe lesen. Strg+C / Strg+D = abbrechen (None)."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def _yes(prompt):
    answer = _ask(f"{prompt} [{tr('cli_yes_key')}/N] ")
    return bool(answer) and answer.lower()[0] in ("y", "j")


def _pick(entries, current_index, value=None):
    """
    Nummerierte Liste zeigen und eine Nummer abfragen.

    ``entries``: Liste von (text, hinweis). ``value``: bereits mitgegebene
    Auswahl (Nummer) — dann wird nicht gefragt. Gibt den Index oder None
    zurueck.
    """
    if value is not None:
        # Direkt mitgegeben: ohne Liste, ausser die Nummer passt nicht.
        if value.isdigit() and 0 <= int(value) < len(entries):
            print(f"→ {entries[int(value)][0]}")
            return int(value)
        print(red(tr("cli_bad_choice").format(value=value)))
        value = None
    for i, (text, hint) in enumerate(entries):
        mark = green("●") if i == current_index else " "
        print(f"  {mark} {bold(str(i))}  {text}")
        if hint:
            print(f"        {dim(hint)}")
    if value is None:
        if not _interactive():
            return None
        value = _ask(f"\n{tr('cli_pick_prompt')} ")
        if not value:
            return None
    try:
        index = int(value)
    except ValueError:
        return None
    return index if 0 <= index < len(entries) else None


def _settings():
    return config_manager.load_saved_settings()


def _save(changes):
    """Eigene Config aktualisieren und WiVRns config.json nachziehen."""
    if not update_json(config_manager.CONFIG_FILE, changes):
        print(red(tr("cli_save_failed")))
        return False
    config_manager.sync_with_wivrn(_settings())
    return True


def _offer_restart():
    """Aenderungen wirken erst beim naechsten Serverstart — anbieten."""
    if not wivrn_server.is_running():
        print(dim(tr("streaming_openvr_restart_hint")))
        return
    if _interactive() and _yes(tr("cli_restart_ask")):
        if _stop_server():
            _start_server()
    else:
        print(yellow(tr("cli_restart_hint")))


# --------------------------------------------------------------------------- #
#  Server
# --------------------------------------------------------------------------- #
def _start_server():
    """
    Server starten wie der Dashboard-Schalter — aber abgekoppelt.

    start_new_session: der Server gehoert danach nicht mehr zu diesem
    Terminal. Schliesst man das Fenster, laeuft VR weiter (sonst wuerde das
    SIGHUP beim Schliessen den Server mitreissen).
    """
    if not venv.wivrn_server_binary():
        print(red(tr("cli_no_server_binary")))
        return False
    env = gpu_select.apply_to(os.environ, _settings().get("gpu_device", ""))
    try:
        os.makedirs(os.path.dirname(SERVER_LOG), exist_ok=True)
        out = open(SERVER_LOG, "w")
    except OSError as exc:
        log.warning("Server-Log nicht anlegbar (%s) — starte ohne Log.", exc)
        out = subprocess.DEVNULL
    try:
        proc = subprocess.Popen(["wivrn-server"], stdin=subprocess.DEVNULL,
                                stdout=out, stderr=subprocess.STDOUT,
                                env=env, start_new_session=True)
    except OSError as exc:
        print(red(f"{tr('cli_start_failed')} ({exc})"))
        return False
    finally:
        if out is not subprocess.DEVNULL:
            out.close()              # das Kind hat seine eigene Kopie

    # Kurz warten: ein falscher Encoder laesst den Server sofort abstuerzen.
    time.sleep(1.5)
    if proc.poll() is not None:
        print(red(tr("cli_start_failed")))
        print(dim(tr("cli_see_log").format(path=SERVER_LOG)))
        return False
    log.info("[CLI] Server gestartet (PID %s).", proc.pid)
    print(green("● " + tr("cli_server_started")))
    # Wie die Oberflaeche: Autostart-Programme erst, wenn das Headset da ist.
    _arm_autostart(quiet_if_none=True)
    return True


def _arm_autostart(quiet_if_none=False):
    """Hintergrund-Waechter starten (siehe core/autostart_runner.py)."""
    env = dict(os.environ)
    if cli_install.install_kind() == "appimage":
        for key in ("PYTHONPATH", "PYTHONHOME", "LD_LIBRARY_PATH"):
            env.pop(key, None)
    result = autostart_runner.arm(_settings(), cli_install.cli_argv("_autostart-watch"), env)
    if result == "armed":
        print(tr("cli_autostart_armed"))
    elif not quiet_if_none:
        print(dim(tr("cli_autostart_none")))
    return result


def _stop_server():
    # Wie der Dashboard-Schalter: erst Autostart-Programme weg, dann Server.
    autostart_runner.stop_watcher()
    if autostart_runner.running_apps():
        count = autostart_runner.kill_apps(_settings())
        print(tr("cli_killapps_done").format(count=count))
    print(tr("cli_server_stopping"))
    if wivrn_server.stop_blocking():
        print(red("○ ") + tr("cli_server_stopped"))
        return True
    print(red(tr("dashboard_stop_failed_text")))
    return False


# --------------------------------------------------------------------------- #
#  Befehle
# --------------------------------------------------------------------------- #
def cmd_help(_arg=None):
    print(bold(f"Yakuda Connect {APP_VERSION} — {tr('cli_title')}"))
    print()
    rows = [
        ("YC-help", tr("cli_help_help")),
        ("YC-status", tr("cli_help_status")),
        ("YC-wivrn-toggle", tr("cli_help_toggle")),
        ("YC-openvr [nr]", tr("cli_help_openvr")),
        ("YC-encoder [nr|name]", tr("cli_help_encoder")),
        ("YC-GPU [nr]", tr("cli_help_gpu")),
        ("YC-killapps", tr("cli_help_killapps")),
        ("YC-autostart-reset", tr("cli_help_autostart_reset")),
        ("YC-pairing", tr("cli_help_pairing")),
    ]
    for name, text in rows:
        print(f"  {bold(name.ljust(22))} {text}")
    print()
    print(dim(tr("cli_help_footer")))
    return 0


def cmd_status(_arg=None):
    data = _settings()
    running = wivrn_server.is_running()
    state = green("● " + tr("dashboard_active")) if running else red("○ " + tr("dashboard_inactive"))
    print(f"{bold('WiVRn'.ljust(14))} {state}")

    mode, path = venv.current_openvr_compat()
    if mode == venv.OPENVR_DISABLED:
        ovr = tr("streaming_openvr_off")
    elif mode == venv.OPENVR_PATH:
        ovr = path
    else:
        ovr = tr("streaming_openvr_default")
    print(f"{bold('OpenVR'.ljust(14))} {ovr}")
    print(f"{bold('Encoder'.ljust(14))} {data.get('encoder', 'Auto')}")

    gpu_id = data.get("gpu_device", "")
    if not gpu_id:
        gpu = tr("streaming_gpu_auto")
    else:
        found = gpu_select.find_gpu(gpu_id)
        gpu = gpu_select.label_for(found, _kind_names()) if found else \
            tr("streaming_gpu_missing").format(id=gpu_id)
    print(f"{bold(tr('streaming_gpu').ljust(14))} {gpu}")

    state = autostart_runner.load_state()
    apps = autostart_runner.running_apps(state)
    if apps:
        auto = green(tr("cli_autostart_running").format(count=len(apps)))
    elif autostart_runner.watcher_running(state):
        auto = yellow(tr("cli_autostart_waiting"))
    elif not autostart_runner.configured_apps(data):
        auto = dim(tr("cli_autostart_none_short"))
    else:
        auto = tr("cli_autostart_idle")
    print(f"{bold('Autostart'.ljust(14))} {auto}")
    return 0


def cmd_toggle(_arg=None):
    if wivrn_server.is_running():
        return 0 if _stop_server() else 1
    return 0 if _start_server() else 1


def cmd_openvr(arg=None):
    mode, path = venv.current_openvr_compat()
    found = venv.openvr_compat_candidates()

    auto = venv.wivrn_autodetect_path() or tr("streaming_openvr_default_none")
    entries = [(tr("streaming_openvr_default"), auto)]
    keys = [("default", "")]
    for e in found:
        text = f"{e['label']}  ({e['path']})"
        if not e["complete"]:
            text += "  " + yellow("⚠ " + tr("streaming_openvr_incomplete"))
        entries.append((text, ""))
        keys.append(("path", e["path"]))
    entries.append((tr("streaming_openvr_custom"), ""))
    keys.append(("custom", ""))
    entries.append((tr("streaming_openvr_off"), ""))
    keys.append(("disabled", ""))

    current = 0
    if mode == venv.OPENVR_DISABLED:
        current = len(keys) - 1
    elif mode == venv.OPENVR_PATH:
        current = next((i for i, k in enumerate(keys) if k == ("path", path)), len(keys) - 2)

    print(bold(tr("cli_openvr_title")))
    index = _pick(entries, current, arg)
    if index is None:
        print(dim(tr("cli_unchanged")))
        return 0

    kind, chosen = keys[index]
    if kind == "custom":
        folder = _ask(tr("cli_openvr_custom_prompt") + " ") if _interactive() else None
        if not folder:
            print(dim(tr("cli_unchanged")))
            return 0
        folder = venv.normalize_compat_path(os.path.expanduser(folder))
        if not venv.looks_like_openvr_compat(folder):
            print(yellow(tr("streaming_openvr_custom_invalid").format(
                path=folder, file=venv.openvr_lib_file(folder))))
            if not _yes(""):
                print(dim(tr("cli_unchanged")))
                return 0
        ok = venv.set_openvr_compat(venv.OPENVR_PATH, folder)
        saved = {"openvr_compat": f"path:{folder}", "openvr_compat_custom": folder}
    elif kind == "disabled":
        ok = venv.set_openvr_compat(venv.OPENVR_DISABLED)
        saved = {"openvr_compat": "disabled"}
    elif kind == "path":
        ok = venv.set_openvr_compat(venv.OPENVR_PATH, chosen)
        saved = {"openvr_compat": f"path:{chosen}"}
    else:
        ok = venv.set_openvr_compat(venv.OPENVR_DEFAULT)
        saved = {"openvr_compat": "default"}

    if not ok:
        print(red(tr("streaming_openvr_write_failed").format(path=venv.wivrn_config_file())))
        return 1
    # Nur unsere Config — WiVRns Datei hat set_openvr_compat schon geschrieben.
    update_json(config_manager.CONFIG_FILE, saved)
    print(green("✓ " + tr("cli_saved")))
    _offer_restart()
    return 0


def cmd_encoder(arg=None):
    current_name = _settings().get("encoder", "Auto")
    current = next((i for i, n in enumerate(ENCODERS)
                    if n.lower() == str(current_name).lower()), 0)
    # Name statt Nummer erlaubt: "YC-encoder vaapi"
    if arg is not None and not arg.isdigit():
        match = [i for i, n in enumerate(ENCODERS) if n.lower() == arg.lower()]
        arg = str(match[0]) if match else "-1"

    print(bold(tr("cli_encoder_title")))
    entries = [(name, tr(ENCODER_HINTS[name])) for name in ENCODERS]
    index = _pick(entries, current, arg)
    if index is None:
        print(dim(tr("cli_unchanged")))
        return 0
    if not _save({"encoder": ENCODERS[index]}):
        return 1
    print(green("✓ " + tr("cli_saved")))
    _offer_restart()
    return 0


def _kind_names():
    return {"discrete": tr("streaming_gpu_discrete"),
            "integrated": tr("streaming_gpu_integrated"),
            "cpu": tr("streaming_gpu_software")}


def cmd_gpu(arg=None):
    print(dim(tr("streaming_gpu_detecting")))
    gpus = gpu_select.list_gpus()
    current_id = _settings().get("gpu_device", "")

    entries = [(tr("streaming_gpu_auto"), tr("streaming_gpu_auto_hint"))]
    ids = [""]
    for g in gpus:
        entries.append((gpu_select.label_for(g, _kind_names()), g.get("render_node", "")))
        ids.append(g["id"])
    if current_id and current_id not in ids:
        entries.append((tr("streaming_gpu_missing").format(id=current_id), ""))
        ids.append(current_id)
    current = ids.index(current_id) if current_id in ids else 0

    print(bold(tr("cli_gpu_title")))
    index = _pick(entries, current, arg)
    if index is None:
        print(dim(tr("cli_unchanged")))
        return 0
    if not _save({"gpu_device": ids[index]}):
        return 1
    if ids[index] and not gpu_select.device_select_layer_available():
        print(yellow("⚠ " + tr("streaming_gpu_no_layer")))
    print(green("✓ " + tr("cli_saved")))
    _offer_restart()
    return 0


def cmd_killapps(_arg=None):
    """Besen-Knopf: Autostart-Programme schliessen, Server laeuft weiter."""
    count = autostart_runner.kill_apps(_settings())
    print(green("✓ ") + tr("cli_killapps_done").format(count=count))
    print(dim(tr("cli_killapps_hint")))
    return 0


def cmd_autostart_reset(_arg=None):
    """'Timer zuruecksetzen': laufende Programme weg, Waechter neu scharf."""
    if not wivrn_server.is_running():
        print(yellow(tr("autostart_reset_no_server")))
        return 1
    if autostart_runner.running_apps():
        autostart_runner.kill_apps(_settings())
    result = _arm_autostart()
    return 0 if result == "armed" else 1


def cmd_pairing(_arg=None):
    """
    Kopplungsmodus: ``wivrnctl pair`` starten, PIN gross anzeigen und
    offen halten, bis Enter/Strg+C gedrueckt wird oder wivrnctl endet.
    """
    if not wivrn_server.is_running():
        print(yellow(tr("cli_pairing_no_server")))
        return 1
    if not shutil.which("wivrnctl"):
        print(red(tr("cli_pairing_no_wivrnctl")))
        return 1
    print(dim(tr("pairing_waiting")))
    proc = subprocess.Popen(["wivrnctl", "pair"], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    try:
        pin = None
        # Enter zaehlt erst, wenn die PIN da ist — sonst beendet ein zu
        # frueh gedruecktes Enter die Kopplung, bevor man sie sieht.
        watch = [proc.stdout]
        while proc.poll() is None:
            ready, _, _ = select.select(watch, [], [], 0.5)
            if proc.stdout in ready:
                line = proc.stdout.readline()
                if not line:
                    break
                if "PIN:" in line and pin is None:
                    pin = line.split("PIN:", 1)[1].strip()
                    print()
                    print("   " + bold(green(f"PIN:  {pin}")))
                    print()
                    print(tr("cli_pairing_hint"))
                    if _interactive():
                        try:            # vorher Getipptes verwerfen
                            import termios
                            termios.tcflush(sys.stdin, termios.TCIFLUSH)
                        except Exception:  # noqa: BLE001
                            pass
                        watch.append(sys.stdin)
                elif line.strip():
                    print(dim(line.rstrip()))
            if sys.stdin in ready:
                sys.stdin.readline()
                break
        if pin is None and proc.poll() is not None:
            print(red(tr("cli_pairing_failed")))
            return 1
    except KeyboardInterrupt:
        print()
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
    print(tr("cli_pairing_off"))
    return 0


def cmd_autostart_watch(_arg=None):
    """Intern: der Hintergrund-Waechter (siehe autostart_runner.watch)."""
    return autostart_runner.watch(_settings(), cli_install.terminal_command)


# Befehlsname -> Funktion. Gross-/Kleinschreibung egal ("GPU" == "gpu").
COMMANDS = {
    "help": cmd_help,
    "status": cmd_status,
    "wivrn-toggle": cmd_toggle,
    "toggle": cmd_toggle,
    "openvr": cmd_openvr,
    "openvrcomp": cmd_openvr,
    "encoder": cmd_encoder,
    "gpu": cmd_gpu,
    "killapps": cmd_killapps,
    "autostart-reset": cmd_autostart_reset,
    "reset-timer": cmd_autostart_reset,
    "pairing": cmd_pairing,
    "pair": cmd_pairing,
    "_autostart-watch": cmd_autostart_watch,
}


# --------------------------------------------------------------------------- #
#  Interaktives Menue (Knopf "Im Terminal starten")
# --------------------------------------------------------------------------- #
MENU = [
    ("1", "status"), ("2", "wivrn-toggle"), ("3", "openvr"),
    ("4", "encoder"), ("5", "gpu"), ("6", "killapps"),
    ("7", "autostart-reset"), ("8", "pairing"), ("h", "help"),
]


def menu():
    print(bold(f"Yakuda Connect {APP_VERSION} — {tr('cli_title')}"))
    while True:
        print()
        cmd_status()
        print()
        labels = {"status": tr("cli_help_status"), "wivrn-toggle": tr("cli_help_toggle"),
                  "openvr": tr("cli_help_openvr"), "encoder": tr("cli_help_encoder"),
                  "gpu": tr("cli_help_gpu"), "killapps": tr("cli_help_killapps"),
                  "autostart-reset": tr("cli_help_autostart_reset"),
                  "pairing": tr("cli_help_pairing"), "help": tr("cli_help_help")}
        for key, name in MENU:
            print(f"  {bold(key)}  {labels[name]}")
        print(f"  {bold('q')}  {tr('cli_quit')}")
        choice = _ask(f"\n{tr('cli_pick_prompt')} ")
        if choice is None or choice.lower() in ("q", "quit", "exit"):
            return 0
        name = dict(MENU).get(choice.lower())
        if name:
            print()
            COMMANDS[name]()


# --------------------------------------------------------------------------- #
#  Einstieg
# --------------------------------------------------------------------------- #
def main(argv):
    """argv: alles nach '--cli', z. B. ['encoder', 'vaapi']."""
    set_language(_settings().get("language", "en"))
    if not argv:
        return menu()
    name = argv[0].lower()
    if name.startswith("yc-"):                  # "YC-GPU" direkt uebergeben
        name = name[3:]
    func = COMMANDS.get(name)
    if func is None:
        print(red(tr("cli_unknown").format(name=argv[0])))
        cmd_help()
        return 2
    try:
        return func(argv[1] if len(argv) > 1 else None)
    except KeyboardInterrupt:
        print()
        return 130
    except BrokenPipeError:
        # Ausgabe in "| head" o. ae. umgeleitet und vorzeitig geschlossen.
        sys.stdout = open(os.devnull, "w")
        return 0
