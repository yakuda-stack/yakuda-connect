#!/usr/bin/env python3
"""
core/vrchat_check.py — VRChat-Videoplayer-Diagnose
==================================================
Prueft, warum In-Game-Videoplayer in VRChat nicht abspielen, und liefert das
Ergebnis als strukturierte Liste an die UI (Games-Tab -> "Videoplayer Check").

Warum nativ und nicht das check_vrc.sh von Bluscream?
-----------------------------------------------------
Die Vorlage fuer die Pruefungen ist Bluscreams check_vrc.sh
(https://github.com/Bluscream/vrcvt). Das Skript wird ueblicherweise so
benutzt:

    bash <(curl -sSL https://raw.githubusercontent.com/.../main/bin/check_vrc.sh)

Fuer einen einzelnen Nutzer am eigenen Rechner ist das vertretbar. In einer
verteilten App waere es das NICHT: wir wuerden bei jedem Klick von jedem
Nutzer fremden Shell-Code aus einem beweglichen main-Branch nachladen und
ausfuehren. Wer den Branch kontrolliert, kontrolliert damit jede Installation
von Yakuda Connect — ein Lieferketten-Risiko, das wir unseren Nutzern nicht
zumuten. Die Pruefungen sind deshalb hier nachgebaut.

Nebeneffekt: wir bekommen strukturierte Daten statt ASCII-Ausgabe zum Parsen,
koennen die Ergebnisse uebersetzen und ordentlich in der UI darstellen.

Datenschutz
-----------
Die aufgeloeste Stream-URL enthaelt in ihren Parametern die oeffentliche IP
des Nutzers (``ip=``) und Signaturen. Wir zeigen sie NIE vollstaendig an —
Nutzer posten Diagnose-Ausgaben erfahrungsgemaess direkt in Discord. Es
erscheint nur Host + Format (siehe ``_redact_url``).

Alle Pruefungen sind rein lesend. Nichts wird veraendert, installiert oder
gestartet.
"""
import os
import re
import glob

import vr_environment as venv
from proc import run, output_of
from logging_setup import get_logger

log = get_logger("vrchat_check")

VRCHAT_APPID = "438100"

# Ergebnis-Status. Die UI mappt das auf Farbe und Symbol.
OK = "ok"        # gruen  — passt
WARN = "warn"    # gelb   — koennte das Problem sein
ERR = "err"      # rot    — sehr wahrscheinlich das Problem
INFO = "info"    # grau   — nur Information, keine Wertung

# Steam Linux Runtime: AppID -> Anzeigename
SLR_NAMES = {
    "4183110": "SteamLinuxRuntime 4",
    "1391110": "SteamLinuxRuntime sniper",
    "1070560": "SteamLinuxRuntime soldier",
    "1628350": "SteamLinuxRuntime medic",
}


def _result(key, status, detail="", hint=""):
    """Ein Pruefergebnis. ``key`` zeigt auf den Locale-Schluessel des Titels."""
    return {"key": key, "status": status, "detail": detail, "hint": hint}


def _redact_url(url):
    """Aus einer googlevideo-URL nur Host und Format zeigen — nie die
    Parameter. Dort steckt die oeffentliche IP des Nutzers drin."""
    if not url:
        return ""
    host = re.sub(r"^https?://([^/]+)/.*$", r"\1", url)
    itag = re.search(r"[?&]itag=(\d+)", url)
    client = re.search(r"[?&]c=([A-Za-z0-9_]+)", url)
    bits = [host]
    if itag:
        bits.append(f"itag={itag.group(1)}")
    if client:
        bits.append(f"client={client.group(1)}")
    return "  ".join(bits)


# --------------------------------------------------------------------------- #
#  Pfade
# --------------------------------------------------------------------------- #
def vrchat_appdata_dir():
    """.../AppData/LocalLow/VRChat/VRChat im Proton-Prefix."""
    return os.path.join(venv.vrchat_proton_prefix(),
                        "AppData", "LocalLow", "VRChat", "VRChat")


def vrchat_tools_dir():
    return os.path.join(vrchat_appdata_dir(), "Tools")


def latest_log():
    """Neuestes output_log_*.txt oder None."""
    pattern = os.path.join(vrchat_appdata_dir(), "output_log_*.txt")
    logs = sorted(glob.glob(pattern), key=lambda p: os.path.getmtime(p), reverse=True)
    return logs[0] if logs else None


def _read_log(path, max_bytes=6_000_000):
    """Log einlesen. Bei sehr langen Sitzungen nur das Ende — die relevanten
    Zeilen (letztes Video, letzter Fehler) stehen ohnehin hinten."""
    try:
        size = os.path.getsize(path)
        with open(path, encoding="utf-8", errors="replace") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                f.readline()          # angebrochene Zeile verwerfen
            return f.read()
    except Exception as exc:
        log.debug("Log nicht lesbar: %s", exc)
        return ""


# --------------------------------------------------------------------------- #
#  Steam-Konfiguration (VDF)
# --------------------------------------------------------------------------- #
def _find_vdf(filename, subdir):
    for root in venv.steam_data_roots():
        for path in glob.glob(os.path.join(root, subdir, "**", filename),
                              recursive=True):
            return path
    return ""


def configured_proton():
    """Die in Steams config.vdf fuer VRChat hinterlegte Proton-Version."""
    path = _find_vdf("config.vdf", "config")
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return ""
    # Block der AppID suchen, darin den "name"-Eintrag
    m = re.search(r'"%s"\s*\{(.{0,400}?)\}' % VRCHAT_APPID, text, re.S)
    if not m:
        return ""
    n = re.search(r'"name"\s+"([^"]+)"', m.group(1))
    return n.group(1) if n else ""


def configured_launch_options():
    """Die in localconfig.vdf hinterlegten Startparameter fuer VRChat.

    Das Muster fuer den Wert muss escapte Anfuehrungszeichen mitnehmen. Ein
    simples "([^"]*)" bricht am ersten \\" ab — und genau die stehen im
    VRCVideoCacher-Wrapper. Die Folge war eine Falschmeldung: die Pruefung
    sah nur 'PROTON_LOG=1 bash -c ...' und meldete das fehlende
    --enable-avpro-in-proton, obwohl es weiter hinten stand.
    """
    path = _find_vdf("localconfig.vdf", "userdata")
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return ""
    m = re.search(r'"%s"\s*\{(.{0,4000}?)\n\s*\}' % VRCHAT_APPID, text, re.S)
    if not m:
        return ""
    n = re.search(r'"LaunchOptions"\s+"((?:[^"\\]|\\.)*)"', m.group(1))
    if not n:
        return ""
    # VDF-Escapes aufloesen: \" -> "  und  \\ -> \
    return n.group(1).replace('\\"', '"').replace("\\\\", "\\")


# --------------------------------------------------------------------------- #
#  Laufender VRChat-Prozess
# --------------------------------------------------------------------------- #
def _vrchat_pid():
    out = output_of(["pgrep", "-f", "VRChat.exe"])
    for line in (out or "").splitlines():
        if line.strip().isdigit():
            return line.strip()
    return ""


def _proc_environ(pid):
    """Environment eines Prozesses als dict. Nur fuer die Anzeige der
    Proton-/Runtime-Pfade — wir geben NIE das ganze Environment aus."""
    env = {}
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            raw = f.read()
    except Exception:
        return env
    for chunk in raw.split(b"\0"):
        if b"=" in chunk:
            k, _, v = chunk.partition(b"=")
            env[k.decode("utf-8", "replace")] = v.decode("utf-8", "replace")
    return env


# --------------------------------------------------------------------------- #
#  Einzelpruefungen
# --------------------------------------------------------------------------- #
def _check_prefix():
    prefix = venv.vrchat_proton_prefix()
    if os.path.isdir(prefix):
        return _result("vrccheck_prefix", OK, prefix)
    return _result("vrccheck_prefix", ERR, prefix, hint="vrccheck_prefix_hint")


def _last_playback_ok():
    """True/False/None — hat der letzte Abspielversuch geklappt?

    Das ist die harte Wahrheit im Log und schlaegt jede Annahme darueber,
    welcher Proton-Build "eigentlich" funktionieren sollte.
    """
    path = latest_log()
    if not path:
        return None
    text = _read_log(path)
    if not text:
        return None
    played = failed = None
    for m in re.finditer(r"Using playback path:\s*([^\r\n]+)", text):
        played = m.end()
    for m in re.finditer(r"Error: (Loading failed[^\r\n]*)", text):
        failed = m.end()
    if played is None and failed is None:
        return None
    if played is None:
        return False
    if failed is None:
        return True
    return played > failed          # was zuletzt passierte, zaehlt


def _check_proton():
    """Welcher Proton-Build laeuft — und spielt er Videos ab?

    RTSP-Builds sind fuer VRChat-Video die sichere Wahl, aber sie sind NICHT
    die einzige Moeglichkeit: proton-cachyos etwa spielt inzwischen ebenfalls
    ab. Deshalb wird hier nicht mehr pauschal alles ausser RTSP als Fehler
    gemeldet. Zeigt das Log einen erfolgreichen Abspielversuch, ist der
    Build in Ordnung — egal wie er heisst.
    """
    conf = configured_proton()
    pid = _vrchat_pid()
    active = ""
    if pid:
        env = _proc_environ(pid)
        paths = env.get("STEAM_COMPAT_TOOL_PATHS", "")
        if paths:
            active = os.path.basename(paths.split(":")[0])

    shown = active or conf
    if not shown:
        return _result("vrccheck_proton", WARN, "", hint="vrccheck_proton_hint")

    detail = shown
    if active and conf and conf.lower() not in active.lower():
        detail = f"{shown}  (Steam: {conf})"

    if "rtsp" in shown.lower():
        return _result("vrccheck_proton", OK, detail)

    playback = _last_playback_ok()
    if playback is True:
        # Spielt ab. Kein Grund, den Nutzer zu einem Wechsel zu draengen.
        return _result("vrccheck_proton", OK, detail, hint="vrccheck_proton_works")
    if playback is False:
        return _result("vrccheck_proton", ERR, detail, hint="vrccheck_proton_hint")
    # Noch nichts abgespielt -> nur ein Hinweis, keine Diagnose.
    return _result("vrccheck_proton", INFO, detail, hint="vrccheck_proton_untested")


def _check_runtime():
    pid = _vrchat_pid()
    if not pid:
        return _result("vrccheck_runtime", INFO, "", hint="vrccheck_norun_hint")
    env = _proc_environ(pid)
    base = env.get("PRESSURE_VESSEL_RUNTIME_BASE", "")
    if not base:
        return _result("vrccheck_runtime", INFO, "")
    name = os.path.basename(base)
    for appid, label in SLR_NAMES.items():
        if appid in base:
            name = label
            break
    return _result("vrccheck_runtime", OK, name)


def _check_launch_options():
    """--enable-avpro-in-proton schaltet AVPro unter Proton ueberhaupt erst
    frei. Fehlt es, bleiben die meisten Videoplayer stumm."""
    opts = configured_launch_options()
    if not opts:
        return _result("vrccheck_launch", WARN, "", hint="vrccheck_launch_hint")
    if "--enable-avpro-in-proton" in opts:
        return _result("vrccheck_launch", OK, opts)
    return _result("vrccheck_launch", WARN, opts, hint="vrccheck_launch_hint")


def _check_clock():
    """Bei abweichender Systemzeit laufen die signierten googlevideo-URLs
    sofort ab (expire=). Das VRCVideoCacher-README nennt genau das als Fix
    fuer die Meldung 'Loading failed. ... codec not supported ...'."""
    out = output_of(["timedatectl", "show",
                     "-p", "NTPSynchronized", "--value"])
    val = (out or "").strip().lower()
    if val == "yes":
        return _result("vrccheck_clock", OK, "NTP")
    if val == "no":
        return _result("vrccheck_clock", ERR, "", hint="vrccheck_clock_hint")
    return _result("vrccheck_clock", INFO, "")


def _check_tools():
    """VRChat legt sein eigenes (abgespecktes) yt-dlp beim Login in Tools/ an.
    deno/ffmpeg fehlen dort normalerweise und werden erst gebraucht, wenn ein
    vollwertiges yt-dlp uebernimmt (VRCVideoCacher) — ihr Fehlen ist also
    KEIN Fehler, sondern der Normalzustand."""
    tools = vrchat_tools_dir()
    ytdlp = os.path.join(tools, "yt-dlp.exe")
    if not os.path.isdir(tools):
        return _result("vrccheck_tools", WARN, "", hint="vrccheck_tools_hint")
    if not os.path.isfile(ytdlp):
        return _result("vrccheck_tools", WARN, "", hint="vrccheck_tools_hint")

    extras = [n for n in ("deno.exe", "ffmpeg.exe")
              if os.path.isfile(os.path.join(tools, n))]
    detail = "yt-dlp.exe" + (" + " + " + ".join(extras) if extras else "")
    return _result("vrccheck_tools", OK, detail)


def _check_host_ytdlp():
    """Ein systemweites yt-dlp braucht VRChat selbst nicht — aber
    VRCVideoCacher kann darauf zurueckgreifen."""
    from shutil import which
    if not which("yt-dlp"):
        return _result("vrccheck_ytdlp", INFO, "", hint="vrccheck_ytdlp_hint")
    ver = (output_of(["yt-dlp", "--version"]) or "").strip().splitlines()
    return _result("vrccheck_ytdlp", OK, ver[0] if ver else "")


def _check_videocacher():
    """Laeuft VRCVideoCacher? Es ersetzt VRChats yt-dlp-Stub und liefert das
    Video lokal aus — hilfreich, wenn die Aufloesung klappt, das Abspielen
    aber scheitert."""
    if _process_running("VRCVideoCacher"):
        return _result("vrccheck_cacher", OK, "")
    return _result("vrccheck_cacher", INFO, "", hint="vrccheck_cacher_hint")


def _process_running(name):
    """Laeuft ein Prozess mit GENAU diesem Namen?

    Bewusst 'pgrep -x' auf den Prozessnamen und NICHT 'pgrep -f' auf die
    ganze Kommandozeile: sobald der VRCVideoCacher-Autostart in VRChats
    Startparametern steht, enthaelt die Kommandozeile des Wrappers den
    Namen — und '-f' meldete dann "laeuft", obwohl das Programm gar nicht
    installiert ist. Genau diese Falschmeldung stand in der Diagnose.
    """
    res = run(["pgrep", "-x", name])
    return res.returncode == 0


def _check_video_playback():
    """Das eigentliche Ergebnis: hat der letzte Abspielversuch geklappt?

    Massgeblich ist, was ZULETZT passiert ist. Frueher genuegte ein einziger
    Fehler irgendwo im Log, um alles als kaputt zu melden — auch wenn danach
    laengst erfolgreich abgespielt wurde, etwa nach einem Proton-Wechsel
    innerhalb derselben Sitzung.
    """
    path = latest_log()
    if not path:
        return _result("vrccheck_video", INFO, "", hint="vrccheck_norun_hint")

    text = _read_log(path)
    if not text:
        return _result("vrccheck_video", INFO, "")

    # Aufgeloeste Stream-URL (nur zur Anzeige von Host/Format)
    resolved = ""
    for m in re.finditer(r"resolved to '([^']+)'", text):
        resolved = m.group(1)

    failed_txt = played_txt = ""
    for m in re.finditer(r"Error: (Loading failed[^\r\n]*)", text):
        failed_txt = m.group(1).strip()
    for m in re.finditer(r"Using playback path:\s*([^\r\n]+)", text):
        played_txt = m.group(1).strip()

    state = _last_playback_ok()
    if state is True:
        return _result("vrccheck_video", OK, played_txt)
    if state is False:
        return _result("vrccheck_video", ERR,
                       _redact_url(resolved) or failed_txt,
                       hint="vrccheck_video_hint")
    return _result("vrccheck_video", INFO, _redact_url(resolved))


def _check_log_info():
    """VRChat-Build und GPU aus dem Log — reine Information fuer Bugreports."""
    path = latest_log()
    if not path:
        return _result("vrccheck_build", INFO, "")
    text = _read_log(path, max_bytes=200_000)
    build = re.search(r"VRChat Build:\s*([^\r\n]+)", text)
    gpu = re.search(r"Graphics Device Name:\s*([^\r\n]+)", text)
    bits = [b.group(1).strip() for b in (build, gpu) if b]
    return _result("vrccheck_build", INFO, "  |  ".join(bits))


# --------------------------------------------------------------------------- #
#  Oeffentliche API
# --------------------------------------------------------------------------- #
CHECKS = (
    _check_prefix,
    _check_proton,
    _check_runtime,
    _check_launch_options,
    _check_clock,
    _check_tools,
    _check_host_ytdlp,
    _check_videocacher,
    _check_video_playback,
    _check_log_info,
)


def run_all():
    """Alle Pruefungen ausfuehren. Eine kaputte Pruefung darf die anderen
    nicht mitreissen — deshalb jede einzeln abgesichert."""
    results = []
    for fn in CHECKS:
        try:
            results.append(fn())
        except Exception as exc:
            log.warning("Pruefung %s fehlgeschlagen: %s", fn.__name__, exc)
            results.append(_result(fn.__name__, INFO, str(exc)))
    return results


def summarize(results):
    """(status, anzahl_probleme) fuer die Kopfzeile der Ergebnisliste."""
    errs = sum(1 for r in results if r["status"] == ERR)
    warns = sum(1 for r in results if r["status"] == WARN)
    if errs:
        return ERR, errs
    if warns:
        return WARN, warns
    return OK, 0
