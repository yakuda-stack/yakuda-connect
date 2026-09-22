#!/usr/bin/env python3
"""
core/xrbinder_ipc.py — mit laufenden Spielen reden (xrBinder-IPC)
=================================================================
xrBinder spricht UDP ueber einen kleinen Vermittler (ipc_server, "bus mode"):
Spiele und Werkzeuge melden sich dort an, Pakete werden weitergereicht. Das
Paketformat sind rohe C-Structs aus xrBinder/src/layer_events.h. Die Offsets
unten sind nicht geraten, sondern mit offsetof() aus genau diesen Headern
ausgelesen (x86-64, gcc):

    EventHeader   24 Byte   target u8 | type u8 | displayName char[13] |
                            instance u8 | targetPid i32 | sourcePid i32
    Command      256 Byte   ctype i32 | args 4x(u32 oder 2x u16) |
                            datasize u16 | gui bool | pad | data char[232]
    AppReg        68 Byte   name[32] | version u32 | engine[32]
    AppAction    216 Byte   handle u64 | session u64 | actionType i32 |
                            setName[32] | actName[128] | description[32] | mask u8
    AppBinding   304 Byte   index i32 | actName[128] | setName[32] | pad4 |
                            session u64 | path[64] | description[64]
    AppActionMap 200 Byte   ... actName[128] @20 | hand u8 @160 | override bool @196

Ablauf:
  * Beim Start (und alle paar Sekunden erneut) meldet sich der Thread als
    Client an. Jedes laufende Spiel antwortet mit AppReg -> Spieleliste.
    Startet ein Spiel, waehrend wir angemeldet sind, kommt sein AppReg mit dem
    VOLLEN Namen; die Antwort auf unsere Anmeldung traegt nur displayName
    (max. 12 Zeichen).
  * dump:  dumpAppBindings + dumpLayerBindings -> Aktionen des Spiels mit
           ihren Tasten und die Quellen des Layers, die im aktiven Profil
           gebunden sind.
  * apply: erst dumpActionMaps (welche Aktionen sind GERADE umgelegt?), dann
           reloadConfig — aber nur, wenn keine davon wegfaellt. Sonst stuerzt
           das Spiel ab (siehe Kopf von xrbinder.py). Dann gilt: naechster Start.
"""
import os
import queue
import socket
import struct
import time

import xrbinder as xb

from logging_setup import get_logger

log = get_logger("xrbinder_ipc")

# EventType (layer_events.h)
EV_APP_REGISTER = 0
EV_APP_ACTION = 2
EV_APP_ACTION_MAP = 6
EV_APP_BINDING = 8
EV_DIAGMSG = 11
EV_COMMAND = 12
EV_CLIENT_REGISTER = 13
EV_APP_DESTROY = 14

# CommandType
CMD_RELOAD_CONFIG = 2
CMD_DUMP_APP_BINDINGS = 9
CMD_DUMP_LAYER_BINDINGS = 10
CMD_DUMP_ACTION_MAPS = 13

TARGET_APP = 1 << 0
TARGET_BUS = 1 << 1
TARGET_CLI = 1 << 2
TARGET_ALL = 0x0F

LAYER_SET = "layer_action_set"
HAND_KEYS = {0: "left", 1: "right", 4: ""}     # eUserPaths; head/gamepad lassen wir aus

_HDR = struct.Struct("<BB13sBii")
_ACTION = struct.Struct("<QQi32s128s32sB")
_BINDING = struct.Struct("<i128s32s4xQ64s64s")
HEADER_SIZE = _HDR.size          # 24
COMMAND_SIZE = 256
COMMAND_DATA = 232


def _cstr(raw):
    return raw.split(b"\0", 1)[0].decode("utf-8", "replace")


def build_packet(target, ev_type, payload, target_pid=0, source_pid=None, name="yakuda"):
    head = _HDR.pack(target, ev_type, name.encode()[:12], 0, int(target_pid),
                     int(source_pid if source_pid is not None else os.getpid()))
    return head + payload


def build_command(ctype, strings=()):
    """Command-Payload (256 Byte). Strings landen hintereinander in data[],
    args[i] haelt (Anfang, Ende) als zwei u16."""
    data = b""
    args = []
    for s in strings:
        b = s.encode("utf-8")
        args.append(struct.pack("<HH", len(data), len(data) + len(b)))
        data += b
    if len(data) > COMMAND_DATA:
        raise ValueError("command too long")
    while len(args) < 4:
        args.append(b"\0\0\0\0")
    return (struct.pack("<i", ctype) + b"".join(args) + struct.pack("<HBx", len(data), 0)
            + data.ljust(COMMAND_DATA, b"\0"))


def parse_packet(raw):
    """Rohes UDP-Paket -> dict oder None."""
    if len(raw) < HEADER_SIZE:
        return None
    _target, ev, dname, _inst, tpid, spid = _HDR.unpack_from(raw)
    p = raw[HEADER_SIZE:]
    out = {"type": ev, "pid": spid, "target_pid": tpid, "display_name": _cstr(dname)}
    try:
        if ev == EV_APP_REGISTER:
            out["name"] = _cstr(p[0:32]) if len(p) >= 32 else ""
        elif ev == EV_APP_ACTION and len(p) >= _ACTION.size:
            _h, _s, atype, setn, actn, desc, mask = _ACTION.unpack_from(p)
            out.update(action_type=atype, set=_cstr(setn), action=_cstr(actn),
                       description=_cstr(desc), mask=mask)
        elif ev == EV_APP_BINDING and len(p) >= _BINDING.size:
            _i, actn, setn, _s, path, desc = _BINDING.unpack_from(p)
            out.update(action=_cstr(actn), set=_cstr(setn), path=_cstr(path),
                       description=_cstr(desc))
        elif ev == EV_APP_ACTION_MAP and len(p) >= 198:
            out.update(action=_cstr(p[20:148]), hand=p[160], override=bool(p[196]))
        elif ev == EV_DIAGMSG and len(p) >= 72:
            out["message"] = _cstr(p[8:72])
    except struct.error:
        return None
    return out


class IpcClient:
    """Blanke Socket-Seite, ohne Qt (fuer Tests und den Thread unten)."""

    def __init__(self, port):
        self.port = int(port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.connect(("127.0.0.1", self.port))

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def _send(self, data):
        try:
            self.sock.send(data)
            return True
        except OSError:          # ipc_server laeuft nicht (ECONNREFUSED)
            return False

    def register(self):
        return self._send(build_packet(TARGET_ALL, EV_CLIENT_REGISTER, b"\0"))

    def command(self, pid, ctype, strings=()):
        return self._send(build_packet(TARGET_APP, EV_COMMAND, build_command(ctype, strings),
                                       target_pid=pid))

    def recv(self, timeout):
        self.sock.settimeout(max(0.01, timeout))
        try:
            return parse_packet(self.sock.recv(4096))
        except (TimeoutError, BlockingIOError):
            return None
        except OSError:
            time.sleep(min(timeout, 0.2))
            return None


def collect_dump(packets):
    """Pakete aus dumpAppBindings/dumpLayerBindings -> Datenstruktur fuer die UI.

    actions: [{name, set, type, description, hands}]
    bindings: {aktion: [pfade]}          (Tasten des Spiels)
    sources:  {quelle: [pfade]}          (im aktiven Profil gebundene Quellen)
    """
    actions = []
    seen = set()
    bindings = {}
    sources = {}
    for p in packets:
        if p["type"] == EV_APP_ACTION:
            if p["set"] == LAYER_SET:
                sources.setdefault(p["action"], [])
                continue
            key = (p["set"], p["action"])
            if key in seen:
                continue
            seen.add(key)
            hands = [HAND_KEYS[i] for i in (0, 1) if p["mask"] & (1 << i)]
            if not hands:
                hands = [""]
            actions.append({"name": p["action"], "set": p["set"], "type": p["action_type"],
                            "description": p["description"], "hands": hands})
        elif p["type"] == EV_APP_BINDING:
            target = sources if p["set"] == LAYER_SET else bindings
            lst = target.setdefault(p["action"], [])
            if p["path"] and p["path"] not in lst:
                lst.append(p["path"])
    return {"actions": actions, "bindings": bindings, "sources": sources}


def overridden_keys(packets):
    """(aktion, hand) aller gerade umgelegten Aktionen aus dumpActionMaps."""
    keys = set()
    answered = False
    for p in packets:
        if p["type"] != EV_APP_ACTION_MAP:
            continue
        answered = True
        if p["override"] and p["hand"] in HAND_KEYS:
            keys.add((p["action"], HAND_KEYS[p["hand"]]))
    return answered, keys


def reload_is_safe(overridden, new_keys):
    """
    Live neu laden nur, wenn jede gerade umgelegte Aktion auch danach noch
    umgelegt ist. Aktionen ohne Hand ('') gelten fuer alle Haende.
    """
    new = set(new_keys)
    for action, hand in overridden:
        if (action, hand) in new or (action, "") in new:
            continue
        return False
    return True


def _make_thread_class():
    from PySide6.QtCore import QThread, Signal

    class XrBinderIpcThread(QThread):
        """
        Dauerhafter IPC-Client im Hintergrund. Die UI stellt Auftraege mit
        request_dump()/request_apply(); Ergebnisse kommen als Signale.
        """
        apps_changed = Signal(object)          # {pid: name} (int-Schluessel: kein dict-Signal)
        dump_ready = Signal(int, object)       # pid, collect_dump(...)
        apply_done = Signal(int, str)          # pid, "live" | "restart" | "no_answer" | "offline"
        bus_state = Signal(bool)               # ipc_server erreichbar?

        REREGISTER_S = 4.0
        QUIET_S = 0.35                          # so lange Stille = Antwort vollstaendig

        def __init__(self, port):
            super().__init__()
            self.port = port
            self._jobs = queue.Queue()
            self._running = True
            self.apps = {}                      # pid -> name
            self._full_names = {}               # pid -> voller Name (AppReg beim Spielstart)
            self._last_seen = {}                # pid -> Zeitpunkt der letzten Antwort
            self._bus_ok = None

        def stop(self):
            self._running = False

        def request_dump(self, pid):
            self._jobs.put(("dump", int(pid), None))

        def request_apply(self, pid, new_keys):
            self._jobs.put(("apply", int(pid), set(new_keys)))

        # -- intern ------------------------------------------------------ #
        def _note_app(self, pkt):
            pid = pkt["pid"]
            if pkt.get("name") and pid not in self._full_names:
                # AppReg traegt hoechstens 31 Zeichen — lange Namen (xrizer:
                # Pfad des Spiels) aus der Befehlszeile vervollstaendigen
                self._full_names[pid] = xb.expand_app_name(pkt["name"], pid)
            name = self._full_names.get(pid) or pkt["display_name"]
            self._last_seen[pid] = time.time()
            if name and self.apps.get(pid) != name:
                self.apps[pid] = name
                return True
            return False

        def _handle_background(self, pkt):
            """Pakete, die nicht zu einem Auftrag gehoeren."""
            if pkt["type"] == EV_APP_REGISTER:
                return self._note_app(pkt)
            if pkt["type"] == EV_APP_DESTROY and pkt["pid"] in self.apps:
                del self.apps[pkt["pid"]]
                return True
            return False

        def _collect(self, client, pid, max_s=3.0):
            """Pakete dieses Spiels sammeln, bis QUIET_S lang nichts mehr kommt."""
            got = []
            end = time.time() + max_s
            last = time.time()
            while self._running and time.time() < end and time.time() - last < self.QUIET_S:
                pkt = client.recv(0.05)
                if not pkt:
                    continue
                if pkt["pid"] == pid and pkt["type"] != EV_APP_REGISTER:
                    got.append(pkt)
                    last = time.time()
                elif self._handle_background(pkt):
                    self.apps_changed.emit(dict(self.apps))
            return got

        def _set_bus(self, ok):
            if ok != self._bus_ok:
                self._bus_ok = ok
                self.bus_state.emit(ok)

        def run(self):
            try:
                client = IpcClient(self.port)
            except OSError as exc:
                log.warning("IPC-Socket nicht anlegbar: %s", exc)
                self._set_bus(False)
                return
            next_reg = 0.0
            try:
                while self._running:
                    now = time.time()
                    if now >= next_reg:
                        self._set_bus(client.register())
                        next_reg = now + self.REREGISTER_S
                        # Spiele, die auf zwei Anmeldungen nicht geantwortet
                        # haben, sind weg (abgestuerzt, ohne AppDestroy).
                        stale = [p for p, t in self._last_seen.items()
                                 if now - t > 2.5 * self.REREGISTER_S]
                        for p in stale:
                            self._last_seen.pop(p, None)
                            if self.apps.pop(p, None) is not None:
                                self.apps_changed.emit(dict(self.apps))
                    try:
                        job, pid, arg = self._jobs.get_nowait()
                    except queue.Empty:
                        job = None
                    if job == "dump":
                        ok = client.command(pid, CMD_DUMP_APP_BINDINGS)
                        ok = client.command(pid, CMD_DUMP_LAYER_BINDINGS) and ok
                        packets = self._collect(client, pid) if ok else []
                        self.dump_ready.emit(pid, collect_dump(packets))
                        continue
                    if job == "apply":
                        self.apply_done.emit(pid, self._apply(client, pid, arg))
                        continue
                    pkt = client.recv(0.2)
                    if pkt and self._handle_background(pkt):
                        self.apps_changed.emit(dict(self.apps))
            finally:
                client.close()

        def _apply(self, client, pid, new_keys):
            if not client.command(pid, CMD_DUMP_ACTION_MAPS):
                return "offline"
            answered, current = overridden_keys(self._collect(client, pid))
            if not answered:
                return "no_answer"
            if not reload_is_safe(current, new_keys):
                return "restart"
            client.command(pid, CMD_RELOAD_CONFIG)
            return "live"

    return XrBinderIpcThread


_THREAD_CLASS = None


def make_ipc_thread(port):
    global _THREAD_CLASS
    if _THREAD_CLASS is None:
        _THREAD_CLASS = _make_thread_class()
    return _THREAD_CLASS(port)
