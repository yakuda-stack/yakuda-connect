#!/usr/bin/env python3
"""
core/gpu_select.py — Grafikkarte für WiVRn auswählen
====================================================
Auf Rechnern mit zwei Grafikeinheiten (Prozessorgrafik + Steckkarte, oder
Notebook mit Optimus/PRIME) sucht sich Vulkan die Karte selbst aus. WiVRn
landet dann gern auf der integrierten Einheit: das Bild ruckelt, der Encoder
ist langsam, und im Log steht nichts davon.

Dieses Modul beantwortet zwei Fragen:

  1. Welche Grafikkarten gibt es?  ``list_gpus()``
  2. Mit welchen Umgebungsvariablen benutzt ein Vulkan-Programm genau eine
     davon?  ``env_for(gpu)``

Erkennung
---------
Grundlage ist ``/sys/class/drm`` — das gibt es immer, ohne Zusatzpaket, und
liefert PCI-Adresse, Hersteller-/Geräte-ID und den Render-Knoten
(``/dev/dri/renderD128``). Ist ``vulkaninfo`` da, werden die Namen und die
Angabe „integriert/dediziert“ von dort übernommen — das sind genau die
Namen, die auch WiVRn sieht. Sonst kommt der Name von ``lspci``, sonst aus
der Hersteller-ID.

Auswahl
-------
``MESA_VK_DEVICE_SELECT=vid:did!`` — das Rufzeichen macht die gewählte Karte
zur EINZIGEN, die das Programm überhaupt zu sehen bekommt (Mesa-Doku,
envvars: „same as MESA_VK_DEVICE_SELECT_FORCE_DEFAULT_DEVICE“). Der
device-select-Layer von Mesa filtert dabei alle Vulkan-Treiber, auch den
proprietären NVIDIA-Treiber — er muss aber installiert sein (Arch:
``vulkan-mesa-layers``). Fehlt er, greift zusätzlich ``VK_DRIVER_FILES``:
damit wird der Treiber des falschen Herstellers gar nicht erst geladen.

Dazu kommen ``DRI_PRIME`` (für die OpenGL-Teile) und bei NVIDIA die
PRIME-Offload-Variablen.

Dieses Modul startet nichts und schreibt keine Konfiguration — es liefert
Listen und Umgebungsvariablen.
"""
import glob
import os
import re
import threading

import proc
from logging_setup import get_logger

log = get_logger("gpu_select")

# Auswahl "Automatisch" — keine Variablen setzen, Vulkan entscheidet selbst.
AUTO = ""

VENDOR_NAMES = {"1002": "AMD", "10de": "NVIDIA", "8086": "Intel",
                "1af4": "Virtio", "15ad": "VMware", "1234": "QEMU"}
VENDOR_KEYS = {"1002": "amd", "10de": "nvidia", "8086": "intel"}

# Vulkan-Treiberdateien je Hersteller. Die Namen sind seit Jahren stabil;
# gefunden wird ueber Muster, damit auch amdvlk (amd_icd64.json) und der
# aeltere Intel-Treiber (intel_hasvk) mitkommen.
ICD_DIRS = ("/usr/share/vulkan/icd.d", "/etc/vulkan/icd.d",
            "/usr/local/share/vulkan/icd.d")
ICD_PATTERNS = {"nvidia": ("nvidia_icd*.json",),
                "amd": ("radeon_icd*.json", "amd_icd*.json"),
                "intel": ("intel_icd*.json", "intel_hasvk*.json")}

# Implicit Layer von Mesa, der MESA_VK_DEVICE_SELECT ueberhaupt auswertet.
DEVICE_SELECT_LAYER = "VkLayer_MESA_device_select.json"
LAYER_DIRS = ("/usr/share/vulkan/implicit_layer.d", "/etc/vulkan/implicit_layer.d",
              "/usr/local/share/vulkan/implicit_layer.d")


# --------------------------------------------------------------------------- #
#  Erkennung
# --------------------------------------------------------------------------- #
def _read(path):
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _hex_id(text):
    """'0x1002' -> '1002'."""
    text = (text or "").strip().lower()
    return text[2:] if text.startswith("0x") else text


def _render_node(device_dir):
    """/dev/dri/renderD128 dieser Karte — oder ""."""
    for node in glob.glob(os.path.join(device_dir, "drm", "renderD*")):
        return os.path.join("/dev/dri", os.path.basename(node))
    return ""


def _lspci_names():
    """{'0000:03:00.0': 'AMD Radeon RX 6700 XT'} — leer, wenn lspci fehlt."""
    import shlex

    res = proc.run(["lspci", "-D", "-mm", "-nn"])
    if res.returncode != 0 or not res.stdout:
        return {}
    names = {}
    for line in res.stdout.splitlines():
        try:
            parts = shlex.split(line)
        except ValueError:
            continue
        if len(parts) < 4:
            continue
        addr, _cls, vendor, device = parts[0], parts[1], parts[2], parts[3]
        vendor = re.sub(r"\s*\[[0-9a-f]{4}\]\s*$", "", vendor)
        device = re.sub(r"\s*\[[0-9a-f]{4}\]\s*$", "", device)
        # "Advanced Micro Devices, Inc. [AMD/ATI]" -> "AMD/ATI"
        short = re.search(r"\[([^\]]+)\]$", vendor)
        if short:
            vendor = short.group(1)
        names[addr] = f"{vendor} {device}".strip()
    return names


def _vulkan_devices():
    """
    {'1002:73df': {'name': ..., 'kind': 'discrete'|'integrated'|''}}

    Aus 'vulkaninfo --summary'. Fehlt das Programm, kommt ein leeres Dict —
    die Liste steht dann trotzdem, nur mit lspci-Namen.
    """
    res = proc.run(["vulkaninfo", "--summary"])
    if res.returncode != 0 or not res.stdout:
        return {}
    found = {}
    cur = {}

    def flush():
        vid, did = cur.get("vendorID"), cur.get("deviceID")
        if vid and did:
            kind = ""
            if "INTEGRATED" in cur.get("deviceType", ""):
                kind = "integrated"
            elif "DISCRETE" in cur.get("deviceType", ""):
                kind = "discrete"
            elif "CPU" in cur.get("deviceType", ""):
                kind = "cpu"
            found[f"{_hex_id(vid)}:{_hex_id(did)}"] = {
                "name": cur.get("deviceName", ""), "kind": kind}

    for line in res.stdout.splitlines():
        if re.match(r"^\s*GPU\d+", line):
            flush()
            cur = {}
            continue
        m = re.match(r"^\s*(\w+)\s*=\s*(.+?)\s*$", line)
        if m and m.group(1) in ("vendorID", "deviceID", "deviceName", "deviceType"):
            cur[m.group(1)] = m.group(2)
    flush()
    return found


# Ergebnis von list_gpus() fuer die ganze Sitzung. 'vulkaninfo --summary'
# kann auf echten Systemen spuerbar dauern (Treiber laden) und lief beim
# Start bis zu dreimal im Haupt-Thread. Grafikkarten wechseln nicht im
# laufenden Betrieb — neu erkannt wird nur ueber den ↻-Knopf (refresh=True).
_cache = None
_cache_lock = threading.Lock()


def cached_gpus():
    """Gemerkte Liste (Kopie) oder None, wenn noch nie erkannt wurde."""
    with _cache_lock:
        return None if _cache is None else [dict(g) for g in _cache]


def clear_cache():
    global _cache
    with _cache_lock:
        _cache = None


def list_gpus(refresh=False):
    """Wie _detect_gpus(), aber einmal pro Sitzung (refresh=True: neu erkennen)."""
    global _cache
    if not refresh:
        cached = cached_gpus()
        if cached is not None:
            return cached
    gpus = _detect_gpus()
    with _cache_lock:
        _cache = [dict(g) for g in gpus]
    return gpus


def _detect_gpus():
    """
    Alle Grafikeinheiten des Systems.

    [{"id": "1002:73df", "name": "AMD Radeon RX 6700 XT",
      "vendor": "amd", "vendor_id": "1002", "device_id": "73df",
      "pci": "0000:03:00.0", "render_node": "/dev/dri/renderD128",
      "kind": "discrete"}]

    Sortiert: dedizierte Karten zuerst, dann der Rest — die dedizierte ist
    in aller Regel die gewuenschte.
    """
    vulkan = _vulkan_devices()
    names = {}
    gpus = []
    seen = set()
    for card in sorted(glob.glob("/sys/class/drm/card[0-9]*")):
        if "-" in os.path.basename(card):      # card0-HDMI-A-1 = Anschluss
            continue
        device_dir = os.path.realpath(os.path.join(card, "device"))
        vid = _hex_id(_read(os.path.join(device_dir, "vendor")))
        did = _hex_id(_read(os.path.join(device_dir, "device")))
        if not vid or not did:
            continue
        pci = os.path.basename(device_dir) if re.match(
            r"^[0-9a-f]{4}:", os.path.basename(device_dir)) else ""
        key = f"{vid}:{did}"
        if (key, pci) in seen:
            continue
        seen.add((key, pci))

        info = vulkan.get(key, {})
        name = info.get("name", "")
        if not name:
            if not names:
                names = _lspci_names()
            name = names.get(pci, "")
        if not name:
            name = f"{VENDOR_NAMES.get(vid, vid)} {did}"
        gpus.append({"id": key, "name": name, "vendor": VENDOR_KEYS.get(vid, vid),
                     "vendor_id": vid, "device_id": did, "pci": pci,
                     "render_node": _render_node(device_dir),
                     "kind": info.get("kind", "")})
    order = {"discrete": 0, "": 1, "integrated": 2, "cpu": 3}
    gpus.sort(key=lambda g: (order.get(g["kind"], 1), g["name"]))
    return gpus


def find_gpu(gpu_id, gpus=None):
    """Eintrag zu einer gemerkten Auswahl — oder None (Karte ausgebaut)."""
    if not gpu_id:
        return None
    for gpu in (gpus if gpus is not None else list_gpus()):
        if gpu["id"] == gpu_id:
            return gpu
    return None


def label_for(gpu, kind_names=None):
    """Anzeigetext: 'AMD Radeon RX 6700 XT (dediziert)'."""
    kind_names = kind_names or {}
    kind = kind_names.get(gpu.get("kind"))
    return f"{gpu['name']} ({kind})" if kind else gpu["name"]


# --------------------------------------------------------------------------- #
#  Umgebung
# --------------------------------------------------------------------------- #
def device_select_layer_available():
    """Ist der Mesa-Layer da, der MESA_VK_DEVICE_SELECT auswertet?"""
    return any(os.path.isfile(os.path.join(d, DEVICE_SELECT_LAYER)) for d in LAYER_DIRS)


def _icd_files(vendor):
    files = []
    for folder in ICD_DIRS:
        for pattern in ICD_PATTERNS.get(vendor, ()):
            files += sorted(glob.glob(os.path.join(folder, pattern)))
    return files


def _vendors_with_icd():
    return {v for v in ICD_PATTERNS if _icd_files(v)}


def env_for(gpu):
    """
    Umgebungsvariablen, die ein Vulkan-Programm auf diese Karte festlegen.

    Leeres Dict bei ``None`` (Automatisch) — dann wird nichts gesetzt und
    alles bleibt, wie es ohne diese Funktion waere.
    """
    if not gpu:
        return {}
    env = {
        # Rufzeichen: nur noch diese Karte wird ueberhaupt aufgezaehlt.
        "MESA_VK_DEVICE_SELECT": f"{gpu['vendor_id']}:{gpu['device_id']}!",
        "MESA_VK_DEVICE_SELECT_FORCE_DEFAULT_DEVICE": "1",
    }
    if gpu.get("pci"):
        env["DRI_PRIME"] = "pci-" + gpu["pci"].replace(":", "_").replace(".", "_")
    if gpu.get("vendor") == "nvidia":
        env["__NV_PRIME_RENDER_OFFLOAD"] = "1"
        env["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
        env["__VK_LAYER_NV_optimus"] = "NVIDIA_only"

    # Zweiter Riegel fuer den Fall, dass der Mesa-Layer fehlt: Treiber
    # anderer Hersteller gar nicht erst laden. Nur sinnvoll, wenn es
    # ueberhaupt Treiber mehrerer Hersteller gibt — sonst wuerde eine
    # Einschraenkung nur Risiko ohne Nutzen bedeuten.
    vendors = _vendors_with_icd()
    own = _icd_files(gpu.get("vendor"))
    if own and len(vendors) > 1:
        env["VK_DRIVER_FILES"] = ":".join(own)
        env["VK_ICD_FILENAMES"] = ":".join(own)    # aeltere Vulkan-Loader
    return env


def env_for_id(gpu_id, gpus=None):
    """Wie env_for, aber ueber die gemerkte Kennung."""
    return env_for(find_gpu(gpu_id, gpus))


def apply_to(environ, gpu_id, gpus=None):
    """Kopie von ``environ`` mit den Variablen der gewaehlten Karte."""
    env = dict(environ)
    extra = env_for_id(gpu_id, gpus)
    if extra:
        log.info("Grafikkarte erzwungen: %s", extra.get("MESA_VK_DEVICE_SELECT"))
    env.update(extra)
    return env
