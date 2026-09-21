#!/usr/bin/env python3
"""Tests fuer core/xrbinder.py, core/xrbinder_ipc.py und die Helfer in ui/xrbinder_panel.py.

Das Zusammenspiel mit dem echten Layer (Monado + Testspiel) ist in
CHANGELOG/Etappe beschrieben; hier stehen die Teile, die ohne Headset und
ohne Netz pruefbar sind.
"""
import os
import struct
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "core"))
sys.path.insert(0, ROOT)

import xrbinder as xb  # noqa: E402
import xrbinder_ipc as xipc  # noqa: E402


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(xb, "TOOLS_DIR", str(tmp_path / ".config/yakuda-connect/tools"))
    return tmp_path


# --------------------------------------------------------------------------- #
#  Quellen
# --------------------------------------------------------------------------- #
def test_touch_face_buttons_only_on_their_hand():
    """Touch hat X/Y nur links, A/B nur rechts — ein Pfad auf der falschen
    Hand laesst die Runtime das GANZE Profil ablehnen."""
    src = xb.build_sources()
    touch = "/interaction_profiles/oculus/touch_controller:"
    x = [b for b in src["x_click"]["bindings"] if b.startswith(touch)]
    a = [b for b in src["a_click"]["bindings"] if b.startswith(touch)]
    assert x == [touch + "/user/hand/left/input/x/click"]
    assert a == [touch + "/user/hand/right/input/a/click"]


def test_source_types_and_variants():
    src = xb.build_sources()
    assert src["x_click"]["type"] == "bool"
    assert src["x_click_f"]["type"] == "float"
    assert "x_touch_f" not in src and "thumbstick_x_b" not in src
    assert src["trigger_value"]["type"] == "float"
    assert src["trigger_value_b"]["type"] == "bool"
    assert src["thumbstick"]["type"] == "vector2"
    for t in xb.TYPES:
        off = src[xb.OFF_SOURCE[t]]
        assert off["type"] == t and off["bindings"] == []


def test_only_core_profiles():
    """Keine Profile, die eine Erweiterung brauchen (Suggest wuerde scheitern)."""
    for name, s in xb.build_sources().items():
        for b in s["bindings"]:
            profile = b.split(":", 1)[0]
            assert profile in xb.PROFILES, (name, b)


# --------------------------------------------------------------------------- #
#  Konfiguration
# --------------------------------------------------------------------------- #
def _lines(text):
    return [line for line in text.splitlines() if line and not line.startswith("#")]


def test_root_keys_before_first_section():
    lines = _lines(xb.render_config([]))
    first_section = next(i for i, line in enumerate(lines) if line.startswith("["))
    root = lines[:first_section]
    assert "ipcMode = bus" in root
    assert f"startupProfile = {xb.PROFILE}" in root
    assert any(line.startswith("serverPort") for line in root)


def test_profile_never_empty():
    """Leerer [bindings.*]-Abschnitt = kein Profil = Absturz bei resetAction."""
    lines = _lines(xb.render_config([]))
    i = lines.index(f"[bindings.{xb.PROFILE}]")
    assert lines[i + 1].startswith(xb.PLACEHOLDER_ACTION + " = ")


def test_mappings_are_direct_only():
    maps = [{"action": "menu", "hand": "left", "source": "x_click", "source_hand": "left"},
            {"action": "jump", "hand": "", "source": xb.OFF_SOURCE["bool"], "source_hand": ""}]
    text = xb.render_config(maps)
    lines = _lines(text)
    assert "menu.left = yc_1" in lines
    assert "jump = yc_2" in lines
    i = lines.index("[actionmap.yc_1]")
    assert lines[i + 1] == "map = x_click.left"
    i = lines.index("[actionmap.yc_2]")
    assert lines[i + 1] == "map = yc_off_bool"
    assert "axis1" not in text and "axis2" not in text
    # Abfrage ohne Hand (Unreal) bekommt dieselbe Zuordnung; "jump" hat schon keine Hand
    assert "menu.any = yc_1" in lines
    assert not any(line.startswith("jump.any") for line in lines)


def test_any_prefers_real_button_over_off():
    maps = [{"action": "fire", "hand": "left", "source": xb.OFF_SOURCE["bool"], "source_hand": ""},
            {"action": "fire", "hand": "right", "source": "a_click", "source_hand": "right"}]
    assert "fire.any = yc_2" in _lines(xb.render_config(maps))


def test_invalid_actions_and_sources_skipped():
    maps = [{"action": "a.b", "hand": "left", "source": "x_click", "source_hand": "left"},
            {"action": "ok", "hand": "left", "source": "nope", "source_hand": "left"}]
    lines = _lines(xb.render_config(maps))
    assert not any(line.startswith(("a.b", "ok")) for line in lines)


def test_no_comment_chars_in_values():
    """'#' und ';' leiten im xrBinder-Parser ueberall einen Kommentar ein."""
    for line in _lines(xb.render_config([])):
        assert "#" not in line and ";" not in line


def test_write_app_config_long_name(home):
    name = "Thief VR Legacy of Shadow"
    written = xb.write_app_config(name, [])
    assert [os.path.basename(p) for p in written] == [f"app_{name}.ini", "app_Thief VR Leg.ini"]
    for p in written:
        assert open(p, encoding="utf-8").readline().strip() == xb.MANAGED_MARK


def test_foreign_config_backed_up_once(home):
    path = xb.base_config_path()
    os.makedirs(os.path.dirname(path))
    with open(path, "w") as fh:
        fh.write("serverPort = 1234\n")
    backup = xb.write_base_config()
    assert backup and open(backup).read() == "serverPort = 1234\n"
    assert xb.write_base_config() == ""          # jetzt unsere Datei: keine Sicherung


def test_reject_path_like_app_names(home):
    with pytest.raises(ValueError):
        xb.write_app_config("../evil", [])


def test_manifest_points_to_build(home):
    xb.write_manifest()
    assert xb.layer_enabled()
    import json
    data = json.load(open(xb.manifest_path()))
    assert data["api_layer"]["name"] == xb.LAYER_NAME
    assert os.path.isabs(data["api_layer"]["library_path"])
    assert xb.remove_manifest() and not xb.layer_enabled()


def test_foreign_manifest_detected_and_cleaned(home):
    d = xb.implicit_dir()
    os.makedirs(d)
    import json
    with open(os.path.join(d, "manifest.json"), "w") as fh:
        json.dump({"api_layer": {"name": xb.LAYER_NAME, "library_path": "./libxrBinder_module.so"}}, fh)
    for f in ("libxrBinder_module.so", "ipc_server", "client_gui"):
        open(os.path.join(d, f), "w").close()
    xb.write_manifest()
    found = xb.foreign_manifests()
    assert found == [os.path.join(d, "manifest.json")]
    target = xb.cleanup_manual_copy(found[0])
    assert target and sorted(os.listdir(target)) == ["client_gui", "ipc_server",
                                                     "libxrBinder_module.so", "manifest.json"]
    assert xb.foreign_manifests() == []
    assert os.path.exists(xb.manifest_path())     # unser Manifest bleibt


def test_service_unit_uses_build_path(home):
    text = xb.service_unit_text(9011)
    assert f"ExecStart={xb.ipc_server_path()} 9011" in text


def test_build_script_has_no_gui_and_status(home):
    s = xb.build_script("de")
    assert "-DENABLE_GUI=OFF" in s
    assert "submodule update --init --depth 1 OpenXR-SDK" in s
    assert "echo ok > \"$STATUS\"" in s
    assert "a.subactionMask |= 1U << USER_INVALID;" in s


def test_build_script_patch_applies(home, tmp_path):
    """Die sed-Zeile aus dem Skript muss genau die Stelle in xrBinder treffen."""
    import re
    import subprocess
    src = tmp_path / "layer_shims.cpp"
    src.write_text("\t\t\tfor(int i = 0; i < n; i++)\n"
                   "\t\t\t\ta.subactionMask |= 1U << FindPath(p[i]);\n"
                   "\t\t\tif(a.subactionMask == 0)\n"
                   "\t\t\t\ta.subactionMask = 1U << USER_INVALID;\n"
                   "\t\t\t\t\tact.subactionMask = 1U << FindPath(sub);\n")
    line = next(ln for ln in xb.build_script("de").splitlines() if ln.startswith("sed -i"))
    cmd = re.sub(r'"\$F"$', str(src), line)
    subprocess.run(["bash", "-c", cmd], check=True, timeout=10)
    text = src.read_text()
    assert "a.subactionMask |= 1U << USER_INVALID;" in text
    assert "if(a.subactionMask == 0)" not in text
    assert "act.subactionMask = 1U << FindPath(sub);" in text      # Rest unberuehrt


def test_needs_rebuild(home):
    os.makedirs(xb.out_dir())
    open(xb.library_path(), "w").close()
    open(xb.ipc_server_path(), "w").close()
    os.chmod(xb.ipc_server_path(), 0o755)
    assert xb.needs_rebuild()
    with open(os.path.join(xb.tool_root(), xb.PATCH_FILE), "w") as fh:
        fh.write(xb.PATCH_LEVEL + "\n")
    assert not xb.needs_rebuild()


# --------------------------------------------------------------------------- #
#  Beschriftungen
# --------------------------------------------------------------------------- #
def test_labels():
    assert xb.path_label("/user/hand/left/input/x/click", "de") == "Links · X · drücken"
    assert xb.path_label("/user/hand/right/input/thumbstick", "en") == "Right · Stick · direction"
    assert xb.source_label("trigger_value_b", "right", "de") == "Rechts · Trigger · Stärke (als Knopf)"
    assert xb.source_label("a_click_f", "right", "en") == "Right · A · press (as value)"


# --------------------------------------------------------------------------- #
#  IPC-Paketformat (Offsets aus layer_events.h, per offsetof ermittelt)
# --------------------------------------------------------------------------- #
def test_header_and_command_sizes():
    assert xipc.HEADER_SIZE == 24
    cmd = xipc.build_command(xipc.CMD_RELOAD_CONFIG)
    assert len(cmd) == 256
    pkt = xipc.build_packet(xipc.TARGET_APP, xipc.EV_COMMAND, cmd, target_pid=4242, source_pid=7)
    target, typ, _name, _inst, tpid, spid = struct.unpack_from("<BB13sBii", pkt)
    assert (target, typ, tpid, spid) == (1, 12, 4242, 7)


def test_command_string_args():
    cmd = xipc.build_command(7, ["jump"])
    ctype, = struct.unpack_from("<i", cmd)
    start, end = struct.unpack_from("<HH", cmd, 4)
    datasize, = struct.unpack_from("<H", cmd, 20)
    assert ctype == 7 and (start, end) == (0, 4) and datasize == 4
    assert cmd[24:28] == b"jump"


def _pkt(ev, payload, pid=100, name=b"Game"):
    return struct.pack("<BB13sBii", 4, ev, name, 0, 0, pid) + payload


def test_parse_action_binding_and_map():
    act = struct.pack("<QQi32s128s32sB3x", 1, 2, 1, b"gameplay", b"menu", b"Open menu", 0b11)
    assert len(act) == 216
    p = xipc.parse_packet(_pkt(xipc.EV_APP_ACTION, act))
    assert (p["action"], p["set"], p["action_type"], p["mask"]) == ("menu", "gameplay", 1, 3)

    bnd = struct.pack("<i128s32s4xQ64s64s", 0, b"menu", b"gameplay", 9,
                      b"/user/hand/left/input/x/click", b"Left X")
    assert len(bnd) == 304
    p = xipc.parse_packet(_pkt(xipc.EV_APP_BINDING, bnd))
    assert p["path"] == "/user/hand/left/input/x/click"

    amap = bytearray(200)
    amap[20:24] = b"jump"
    amap[160] = 1
    amap[196] = 1
    p = xipc.parse_packet(_pkt(xipc.EV_APP_ACTION_MAP, bytes(amap)))
    assert (p["action"], p["hand"], p["override"]) == ("jump", 1, True)


def test_collect_dump_splits_game_and_layer():
    def act(name, setn, typ=1, mask=3):
        return {"type": xipc.EV_APP_ACTION, "action": name, "set": setn, "action_type": typ,
                "description": name.title(), "mask": mask}

    def bnd(name, setn, path):
        return {"type": xipc.EV_APP_BINDING, "action": name, "set": setn, "path": path}

    d = xipc.collect_dump([
        act("menu", "gameplay"), bnd("menu", "gameplay", "/user/hand/left/input/y/click"),
        act("pose", "gameplay", typ=4, mask=0),
        act("x_click", xipc.LAYER_SET), bnd("x_click", xipc.LAYER_SET, "/user/hand/left/input/x/click"),
        act("a_click", xipc.LAYER_SET),
    ])
    assert [a["name"] for a in d["actions"]] == ["menu", "pose"]
    assert d["actions"][0]["hands"] == ["left", "right"]
    assert d["actions"][1]["hands"] == [""]
    assert d["bindings"] == {"menu": ["/user/hand/left/input/y/click"]}
    assert d["sources"] == {"x_click": ["/user/hand/left/input/x/click"], "a_click": []}


def test_reload_safety():
    """Live neu laden nur, wenn keine aktive Umbelegung wegfaellt (sonst Absturz)."""
    assert xipc.reload_is_safe(set(), {("menu", "left")})
    assert xipc.reload_is_safe({("menu", "left")}, {("menu", "left"), ("jump", "right")})
    assert not xipc.reload_is_safe({("menu", "left")}, {("jump", "right")})
    assert xipc.reload_is_safe({("menu", "left"), ("menu", "right")}, {("menu", "")})


def test_overridden_keys_needs_answer():
    answered, keys = xipc.overridden_keys([])
    assert not answered and keys == set()
    pk = [{"type": xipc.EV_APP_ACTION_MAP, "action": "jump", "hand": 1, "override": True},
          {"type": xipc.EV_APP_ACTION_MAP, "action": "menu", "hand": 0, "override": False},
          {"type": xipc.EV_APP_ACTION_MAP, "action": "grab", "hand": 2, "override": True}]
    answered, keys = xipc.overridden_keys(pk)
    assert answered and keys == {("jump", "right")}


def test_client_against_fake_bus():
    """Anmelden + Befehl gehen wirklich als UDP raus (Fake-Bus auf localhost)."""
    import socket
    bus = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    bus.bind(("127.0.0.1", 0))
    bus.settimeout(2)
    client = xipc.IpcClient(bus.getsockname()[1])
    try:
        assert client.register()
        data, addr = bus.recvfrom(4096)
        assert data[1] == xipc.EV_CLIENT_REGISTER and data[0] & xipc.TARGET_BUS
        assert client.command(555, xipc.CMD_DUMP_APP_BINDINGS)
        data, _ = bus.recvfrom(4096)
        assert len(data) == 24 + 256 and struct.unpack_from("<i", data, 16)[0] == 555
        # Antwort eines "Spiels" zurueck an den Client
        reg = struct.pack("<BB13sBii", 4, xipc.EV_APP_REGISTER, b"Wanderer", 0, 0, 777) + bytes(68)
        bus.sendto(reg, addr)
        p = client.recv(2)
        assert p["pid"] == 777 and p["display_name"] == "Wanderer"
    finally:
        client.close()
        bus.close()


# --------------------------------------------------------------------------- #
#  Helfer der Oberflaeche
# --------------------------------------------------------------------------- #
def test_resolve_app_name():
    from xrbinder_session import resolve_app_name
    assert resolve_app_name("Thief VR Leg", ["Thief VR Legacy of Shadow"]) == \
        "Thief VR Legacy of Shadow"
    assert resolve_app_name("Wanderer", ["Wanderer 2"]) == "Wanderer"
