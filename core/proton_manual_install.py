#!/usr/bin/env python3
"""
core/proton_manual_install.py — Download manuell verteilter Proton-Builds
=========================================================================
Nicht jede empfohlene Proton-Version kommt ueber die AUR oder ProtonPlus.
Proton-RTSP-Wayland-GE zum Beispiel gibt es ausschliesslich als Tarball am
GitHub-Release. Dieser Worker holt so einen Build, prueft ihn und entpackt
ihn nach compatibilitytools.d.

Drei Dinge, die hier bewusst so geloest sind:

1. Es wird das BINARY-Archiv geladen, nicht das "-source"-Archiv. Projekte
   unter LGPL legen ihren Releases ein Corresponding-Source-Archiv bei; das
   enthaelt nur vorbereiteten Quellcode und keine compatibilitytool.vdf.
   Entpackt landet es zwar im Ordner, Steam zeigt aber nichts an.
   _reject_source_archive() faengt eine falsch gepflegte URL deshalb ab,
   bevor ueberhaupt geladen wird.

2. Das Zielverzeichnis kommt aus games.compat_tools_install_dir() und ist
   nicht hartkodiert. Ein fest eingetragener Flatpak-Pfad wuerde bei nativem
   Steam — dem Normalfall auf Arch/CachyOS — ins Leere entpacken.

3. Die .sha512sum wird geprueft, wenn das Release eine mitliefert. Der
   Download wird anschliessend als Proton-Runtime ausgefuehrt; ein abgebrochener
   Transfer soll nicht als halbes Compat-Tool liegenbleiben.
"""
import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
import urllib.request

from PySide6.QtCore import QThread, Signal as QtSignal

import games as games_db
from logging_setup import get_logger

log = get_logger("proton_manual")

_UA = {"User-Agent": "yakuda-connect"}
_CHUNK = 256 * 1024


def _reject_source_archive(url):
    """True, wenn die URL auf ein Corresponding-Source-Archiv zeigt."""
    name = os.path.basename(url).lower()
    return "-source.tar" in name or name.endswith("-source.tar.gz")


def _download(url, dest, progress=None):
    """Laedt url nach dest und meldet Fortschritt in Prozent (oder -1)."""
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(_CHUNK)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(int(done * 100 / total) if total else -1)
    return dest


def _expected_sha512(checksum_url):
    """Holt die erwartete Pruefsumme aus einer .sha512sum-Datei.

    Format ist das von sha512sum: '<hex>  <dateiname>'. Es wird nur das
    erste Feld gebraucht; der Dateiname darin kann vom heruntergeladenen
    Namen abweichen, wenn der Maintainer umbenannt hat.
    """
    req = urllib.request.Request(checksum_url, headers=_UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read(8192).decode("utf-8", "ignore")
    for line in text.splitlines():
        parts = line.split()
        if parts and len(parts[0]) == 128:
            return parts[0].lower()
    return None


def _sha512_of(path):
    h = hashlib.sha512()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _tool_root(tar):
    """Der gemeinsame oberste Ordner im Archiv, oder None.

    Ein Proton-Tarball entpackt sich normalerweise in genau ein Verzeichnis.
    Faellt das weg (Dateien liegen flach im Archiv), wird spaeter ein eigener
    Ordner angelegt, sonst kippt der Inhalt direkt in compatibilitytools.d.
    """
    roots = set()
    for member in tar.getmembers():
        head = member.name.split("/", 1)[0]
        if head in ("", ".", ".."):
            return None
        roots.add(head)
        if len(roots) > 1:
            return None
    return next(iter(roots), None)


def _safe_extract(tar, target):
    """Entpackt tar nach target und weist Pfade ausserhalb davon zurueck.

    Ein praeparierter Tarball kann mit '../' oder absoluten Pfaden Dateien
    ausserhalb des Zielordners schreiben. Python 3.12 bringt dafuer den
    'data'-Filter mit; auf aelteren Versionen wird von Hand geprueft.
    """
    try:
        tar.extractall(target, filter="data")
        return
    except TypeError:
        pass
    base = os.path.realpath(target)
    for member in tar.getmembers():
        dest = os.path.realpath(os.path.join(target, member.name))
        if not (dest == base or dest.startswith(base + os.sep)):
            raise RuntimeError(f"Archiv enthaelt unerlaubten Pfad: {member.name}")
    tar.extractall(target)


_ARCHIVE_EXTS = (".tar.gz", ".tar.xz", ".tar.zst", ".tgz")


def _strip_archive_ext(name):
    for ext in _ARCHIVE_EXTS:
        if name.endswith(ext):
            return name[:-len(ext)]
    return name


# x86-64-Level nach psABI. proton-cachyos gibt es als x86_64 und x86_64_v3;
# v3 laeuft auf CPUs ohne AVX2 & Co. gar nicht (Illegal instruction).
_X86_LEVEL_FLAGS = {
    2: {"cx16", "lahf_lm", "popcnt", "sse4_1", "sse4_2", "ssse3"},
    3: {"avx", "avx2", "bmi1", "bmi2", "f16c", "fma", "abm", "movbe", "xsave"},
    4: {"avx512f", "avx512bw", "avx512cd", "avx512dq", "avx512vl"},
}


def cpu_x86_level():
    """Hoechster x86-64-Level dieser CPU (1-4), 0 wenn nicht x86_64."""
    if os.uname().machine not in ("x86_64", "amd64"):
        return 0
    flags = set()
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("flags"):
                    flags = set(line.split(":", 1)[1].split())
                    break
    except OSError:
        return 1
    level = 1
    for lvl in (2, 3, 4):
        if _X86_LEVEL_FLAGS[lvl] <= flags:
            level = lvl
        else:
            break
    return level


def _asset_rank(name, machine, x86_level):
    """Wie gut passt ein Build-Archiv zu diesem Rechner? None = gar nicht.

    Archive ohne Architektur im Namen (proton-rtsp, Wayland-GE) passen
    immer. Sonst: arm64/aarch64 nur auf ARM, x86_64 auf x86_64, und
    x86_64_vN nur, wenn die CPU Level N kann — der hoechste passende gewinnt.
    """
    low = name.lower()
    is_arm = "arm64" in low or "aarch64" in low
    is_x86 = "x86_64" in low or "amd64" in low
    on_arm = machine in ("aarch64", "arm64")
    if is_arm:
        return 1 if on_arm else None
    if is_x86:
        if on_arm:
            return None
        for lvl in (4, 3, 2):
            if f"_v{lvl}" in low:
                return lvl if x86_level >= lvl else None
        return 1
    return 0


def _pick_build(names):
    machine = os.uname().machine
    level = cpu_x86_level()
    best, best_rank = None, None
    for n in names:
        if not n.endswith(_ARCHIVE_EXTS) or _reject_source_archive(n):
            continue
        rank = _asset_rank(n, machine, level)
        if rank is None:
            continue
        if best_rank is None or rank > best_rank:
            best, best_rank = n, rank
    return best


def resolve_latest(repo):
    """Neuestes Release eines GitHub-Repos als Download-Felder — oder None.

    Die games.json nennt immer einen Stand von gestern; proton-rtsp und der
    Wayland-Fork erscheinen aber im Wochentakt. Deshalb wird beim Klick auf
    Installieren das aktuelle Release gefragt. Klappt das nicht (offline,
    API-Limit), bleiben die in der games.json eingetragenen URLs der Rueckfall.

    Stabile Releases gehen vor; nur wenn es keins gibt, zaehlt auch eine
    Vorabversion.
    """
    url = f"https://api.github.com/repos/{repo}/releases?per_page=10"
    try:
        req = urllib.request.Request(
            url, headers={**_UA, "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            releases = json.loads(r.read().decode("utf-8", "ignore"))
    except Exception as exc:
        log.warning("Neuestes Release von %s nicht abrufbar — %s", repo, exc)
        return None
    if not isinstance(releases, list):
        return None
    usable = [r for r in releases if isinstance(r, dict) and not r.get("draft")]
    stable = [r for r in usable if not r.get("prerelease")]
    for rel in (stable or usable):
        assets = {a.get("name", ""): a.get("browser_download_url", "")
                  for a in rel.get("assets") or []}
        build = _pick_build(assets)
        if not build:
            continue
        out = {
            "version": _strip_archive_ext(build),
            "download_url": assets[build],
            "release_url": rel.get("html_url", ""),
            "tool_root": _strip_archive_ext(build),
        }
        checksum = assets.get(build + ".sha512sum") \
            or assets.get(_strip_archive_ext(build) + ".sha512sum")
        out["checksum_url"] = checksum or ""
        return out
    return None


_ARCH_SUFFIX = re.compile(r"[-_](x86_64(_v\d)?|amd64|aarch64|arm64)$", re.IGNORECASE)


def _already_installed(root):
    """Liegt dieses Release schon in einem compatibilitytools.d?

    Der Ordner im Archiv heisst nicht immer wie das Archiv: GE packt
    „GE-Proton11-12-x86_64.tar.gz“ nach „GE-Proton11-12“. Deshalb wird auch
    der Name ohne Architektur-Endung geprueft.
    """
    names = {root, _ARCH_SUFFIX.sub("", root)}
    for d in games_db.compat_tools_dirs():
        for n in names:
            if os.path.isfile(os.path.join(d, n, "compatibilitytool.vdf")):
                return True
    return False


def install_manual_proton(proton, progress=None, status=None, skip_if_current=False):
    """Laedt, prueft und entpackt einen manuell verteilten Proton-Build.

    Mit ``github_repo`` im Eintrag wird immer das NEUESTE Release geholt.
    ``skip_if_current``: liegt genau dieses Release schon da, wird nichts
    geladen (Optimieren-Knopf — sonst bei jedem Klick ein Gigabyte).

    Rueckgabe: (ok: bool, meldung_oder_ordnername: str, schon_aktuell: bool)
    """
    if proton.get("github_repo"):
        if status:
            status("resolve")
        latest = resolve_latest(proton["github_repo"])
        if latest:
            if skip_if_current and _already_installed(latest["tool_root"]):
                return True, latest["tool_root"], True
            proton = {**proton, **latest}
            if not latest.get("checksum_url"):
                proton.pop("checksum_url", None)

    ok, msg = _install_from_url(proton, progress, status)
    return ok, msg, False


def _install_from_url(proton, progress=None, status=None):
    url = proton.get("download_url")
    if not url:
        return False, "keine download_url hinterlegt"
    if _reject_source_archive(url):
        return False, ("die hinterlegte URL zeigt auf das Source-Archiv "
                       "(-source.tar.gz), nicht auf den Build")

    target_dir = games_db.compat_tools_install_dir()
    if not target_dir:
        return False, "kein Steam-Verzeichnis fuer compatibilitytools.d gefunden"

    tmp = tempfile.mkdtemp(prefix="yakuda-proton-")
    archive = os.path.join(tmp, os.path.basename(url))
    try:
        if status:
            status("download")
        _download(url, archive, progress)

        checksum_url = proton.get("checksum_url")
        if checksum_url:
            if status:
                status("verify")
            try:
                expected = _expected_sha512(checksum_url)
            except Exception as exc:
                log.warning("Pruefsumme nicht abrufbar — %s", exc)
                expected = None
            if expected:
                actual = _sha512_of(archive)
                if actual != expected:
                    return False, "Pruefsumme stimmt nicht — Download verworfen"

        if status:
            status("extract")
        with tarfile.open(archive) as tar:
            root = _tool_root(tar)
            if root:
                dest = os.path.join(target_dir, root)
                # Eine aeltere Installation desselben Builds wird ersetzt.
                # Druebergepackt entstuenden sonst Mischordner aus zwei
                # Versionen, die niemand mehr auseinanderhaelt.
                if os.path.isdir(dest):
                    shutil.rmtree(dest)
                _safe_extract(tar, target_dir)
            else:
                root = os.path.splitext(os.path.splitext(
                    os.path.basename(url))[0])[0]
                dest = os.path.join(target_dir, root)
                if os.path.isdir(dest):
                    shutil.rmtree(dest)
                os.makedirs(dest, exist_ok=True)
                _safe_extract(tar, dest)

        vdf = os.path.join(target_dir, root, "compatibilitytool.vdf")
        if not os.path.isfile(vdf):
            return False, ("entpackt, aber ohne compatibilitytool.vdf — "
                           "Steam wird den Build nicht anzeigen")
        return True, root
    except Exception as exc:
        log.warning("install_manual_proton: %s", exc)
        return False, str(exc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class ManualProtonInstallWorker(QThread):
    """Haelt den Download aus dem GUI-Thread heraus."""
    progress_signal = QtSignal(int)
    status_signal = QtSignal(str)
    finished_signal = QtSignal(bool, str)

    def __init__(self, proton, skip_if_current=False):
        super().__init__()
        self.proton = proton
        self.skip_if_current = skip_if_current
        self.already_current = False

    def run(self):
        ok, msg, current = install_manual_proton(
            self.proton,
            progress=self.progress_signal.emit,
            status=self.status_signal.emit,
            skip_if_current=self.skip_if_current,
        )
        self.already_current = current
        self.finished_signal.emit(ok, msg)
