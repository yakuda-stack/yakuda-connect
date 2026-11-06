#!/usr/bin/env python3
"""
core/audio_return.py — Audio zurueck auf den PC, wenn das Headset weg ist (ohne Qt)
==================================================================================
WiVRn legt fuer jede Sitzung ein Ausgabegeraet ``wivrn.sink`` und ein
Mikrofon ``wivrn.source`` an. Geht das Headset in den Standby, pausiert
WiVRn die Sitzung nur: beide Geraete bleiben stehen und bleiben Standard.
Der Ton laeuft dann ins Leere, bis man ihn von Hand umstellt.

Ablauf
------
    HeadsetPresence.update()  alle paar Sekunden, nur /proc + eine Anfrage
        -> "gone"       nach mehreren Fehlschlaegen am Stueck
        -> "connected"  sobald das Headset wieder da ist

    to_pc()            Standard ist ein WiVRn-Geraet -> auf das gemerkte
                       PC-Geraet stellen (sonst das erste andere)
    back_to_headset()  nur was to_pc() umgestellt hat, und nur, wenn der
                       Nutzer inzwischen nichts anderes gewaehlt hat

pactl laeuft nur bei diesen Ereignissen, nie im Takt.

Zustandsdatei (~/.cache/yakuda-connect/audio-return.json):
    {"sink": "<PC-Ausgabe>", "source": "<PC-Mikrofon>",
     "switched": {"sink": "<eingestellt>", "source": "<eingestellt>"}}
Oberflaeche und Terminal-Modus teilen sie sich.
"""
import shutil

import paths
import proc
import process_watch
from jsonio import read_json, write_json_atomic
from logging_setup import get_logger

log = get_logger("audio_return")

SETTING_KEY = "audio_return_on_disconnect"
STATE_FILE = paths.cache_file("audio-return.json")
POLL_S = 5.0
GRACE = 3

WIVRN = {"sink": "wivrn.sink", "source": "wivrn.source"}
_PACTL_TIMEOUT = 3


# --------------------------------------------------------------------------- #
#  Headset da oder weg?
# --------------------------------------------------------------------------- #
class HeadsetPresence:
    """
    Merkt, wann das Headset kommt und geht.

    Wird das Headset ausgeschaltet oder geht es in den Standby, schliesst
    niemand die TCP-Verbindung. Darum wird es zusaetzlich direkt angefragt.
    Schweigen zaehlt nur, wenn das Geraet schon einmal geantwortet hat:
    sonst koennte es Anfragen einfach ignorieren.
    """

    def __init__(self, peers, answers=process_watch.host_answers, grace=GRACE):
        self._peers = peers
        self._answers = answers
        self._grace = grace
        self._dead = set()
        self._answering = set()
        self._misses = 0
        self.present = False

    def reset(self):
        self._dead.clear()
        self._misses = 0
        self.present = False

    def _alive(self, peers):
        for ip, _port in peers:
            if ip.startswith("127.") or ip == "::1":            # USB (adb reverse)
                return True
            if self._answers(ip):
                self._answering.add(ip)
                return True
            if ip not in self._answering:
                return True
        return False

    def update(self):
        """Rueckgabe: "connected", "gone" oder None (nichts Neues)."""
        found = list(self._peers())
        self._dead &= set(found)
        peers = [p for p in found if p not in self._dead]
        if peers and self._alive(peers):
            self._misses = 0
            if self.present:
                return None
            self.present = True
            return "connected"
        if not self.present:
            return None
        self._misses += 1
        if self._misses < self._grace:
            return None
        self._misses = 0
        self._dead |= set(peers)
        self.present = False
        return "gone"


# --------------------------------------------------------------------------- #
#  pactl
# --------------------------------------------------------------------------- #
def available():
    return shutil.which("pactl") is not None


def _pactl(*args):
    res = proc.run(["pactl", *args], timeout=_PACTL_TIMEOUT)
    if res.returncode != 0:
        return None
    return (res.stdout or "").strip()


def default_device(kind):
    return _pactl(f"get-default-{kind}") or ""


def list_devices(kind):
    """Namen aller Ausgaben ("sink") bzw. Eingaben ("source")."""
    out = _pactl("list", f"{kind}s", "short") or ""
    names = []
    for line in out.splitlines():
        cols = line.split("\t")
        if len(cols) > 1 and cols[1]:
            names.append(cols[1])
    return names


def _is_pc_device(kind, name):
    if not name or "wivrn" in name.lower():
        return False
    return not (kind == "source" and name.endswith(".monitor"))


# --------------------------------------------------------------------------- #
#  Zustand
# --------------------------------------------------------------------------- #
def load_state():
    data = read_json(STATE_FILE, default={})
    if not isinstance(data, dict):
        data = {}
    if not isinstance(data.get("switched"), dict):
        data["switched"] = {}
    return data


def save_state(state):
    try:
        write_json_atomic(STATE_FILE, state)
    except OSError as exc:
        log.debug("Zustand nicht speicherbar: %s", exc)


# --------------------------------------------------------------------------- #
#  Aktionen
# --------------------------------------------------------------------------- #
def remember_pc_devices():
    """Aktuelle PC-Geraete merken, solange sie Standard sind."""
    if not available():
        return
    state = load_state()
    changed = False
    for kind in WIVRN:
        current = default_device(kind)
        if _is_pc_device(kind, current) and state.get(kind) != current:
            state[kind] = current
            changed = True
    if changed:
        save_state(state)


def _target(kind, remembered, names):
    if remembered in names and _is_pc_device(kind, remembered):
        return remembered
    return next((n for n in names if _is_pc_device(kind, n)), None)


def to_pc():
    """Standard von WiVRn auf den PC stellen. Rueckgabe: umgestellte Arten."""
    if not available():
        log.info("[Audio] pactl fehlt – Audio bleibt, wie es ist.")
        return []
    state = load_state()
    moved = []
    for kind, wivrn_name in WIVRN.items():
        if default_device(kind) != wivrn_name:
            continue
        target = _target(kind, state.get(kind), list_devices(kind))
        if not target:
            continue
        if _pactl(f"set-default-{kind}", target) is None:
            log.warning("[Audio] %s konnte nicht auf %s gestellt werden.", kind, target)
            continue
        state["switched"][kind] = target
        moved.append(kind)
        log.info("[Audio] Headset weg – %s zurueck auf %s.", kind, target)
    if moved:
        save_state(state)
    return moved


def back_to_headset():
    """Rueckgaengig machen, was to_pc() umgestellt hat."""
    state = load_state()
    if not state["switched"] or not available():
        return []
    moved = []
    for kind, target in list(state["switched"].items()):
        wivrn_name = WIVRN.get(kind)
        state["switched"].pop(kind, None)
        if not wivrn_name or default_device(kind) != target:
            continue
        if wivrn_name not in list_devices(kind):
            continue
        if _pactl(f"set-default-{kind}", wivrn_name) is not None:
            moved.append(kind)
            log.info("[Audio] Headset wieder da – %s zurueck auf %s.", kind, wivrn_name)
    save_state(state)
    return moved


def handle(event):
    """Ereignis aus HeadsetPresence.update() umsetzen."""
    if event == "gone":
        return to_pc()
    if event == "connected":
        return back_to_headset()
    return []
