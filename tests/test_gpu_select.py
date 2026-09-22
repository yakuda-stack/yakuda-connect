#!/usr/bin/env python3
"""
tests/test_gpu_select.py — Grafikkarte fuer WiVRn festlegen
===========================================================
Auf Rechnern mit zwei Grafikeinheiten sucht sich Vulkan selbst eine aus, oft
die integrierte. Der Streaming-Tab laesst die Karte festlegen; gesetzt wird
sie ueber Umgebungsvariablen beim Start des Servers.

Geprueft wird:
  * die Erkennung liest /sys/class/drm (ohne Zusatzpaket) und mischt Namen
    aus vulkaninfo dazu
  * die Variablen entsprechen der Mesa-Doku (Rufzeichen = nur diese Karte)
  * eine ausgebaute Karte verschwindet nicht still aus der Auswahl
  * der vaapi-Encoder bekommt zusaetzlich den Render-Knoten in WiVRns config
"""
import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import gpu_select  # noqa: E402


# --------------------------------------------------------------------------- #
#  Ein System mit zwei Karten nachbauen
# --------------------------------------------------------------------------- #
def _fake_sysfs(tmp_path, cards):
    """
    /sys/class/drm nachbauen. cards: [(name, vendor, device, pci, render)]
    Gibt die Funktion zurueck, die glob.glob ersetzt.
    """
    root = tmp_path / "drm"
    for name, vendor, device, pci, render in cards:
        dev = tmp_path / "pci" / pci
        (dev / "drm" / render).mkdir(parents=True)
        (dev / "vendor").write_text(vendor + "\n")
        (dev / "device").write_text(device + "\n")
        card = root / name
        card.mkdir(parents=True)
        (card / "device").symlink_to(dev)

    import glob as _glob
    real_glob = _glob.glob

    def fake_glob(pattern):
        if pattern == "/sys/class/drm/card[0-9]*":
            return sorted(str(p) for p in root.iterdir())
        if pattern.endswith("/drm/renderD*"):
            base = pathlib.Path(pattern[:-len("/renderD*")])
            return [str(p) for p in base.iterdir()] if base.is_dir() else []
        # alles Uebrige (Vulkan-Treiberdateien) echt beantworten
        return real_glob(pattern)

    return fake_glob


@pytest.fixture
def two_gpus(tmp_path, monkeypatch):
    """Prozessorgrafik (Intel) + dedizierte Karte (AMD)."""
    fake_glob = _fake_sysfs(tmp_path, [
        ("card0", "0x8086", "0x9bc4", "0000:00:02.0", "renderD128"),
        ("card1", "0x1002", "0x73df", "0000:03:00.0", "renderD129"),
    ])
    monkeypatch.setattr(gpu_select.glob, "glob", fake_glob)
    monkeypatch.setattr(gpu_select, "_vulkan_devices", lambda: {
        "8086:9bc4": {"name": "Intel UHD Graphics", "kind": "integrated"},
        "1002:73df": {"name": "AMD Radeon RX 6700 XT", "kind": "discrete"}})
    return None


def test_list_gpus_reads_sysfs_and_sorts_discrete_first(two_gpus):
    gpus = gpu_select.list_gpus()
    assert [g["id"] for g in gpus] == ["1002:73df", "8086:9bc4"]
    dgpu, igpu = gpus
    assert dgpu["name"] == "AMD Radeon RX 6700 XT"
    assert dgpu["vendor"] == "amd" and dgpu["kind"] == "discrete"
    assert dgpu["pci"] == "0000:03:00.0"
    assert dgpu["render_node"] == "/dev/dri/renderD129"
    assert igpu["kind"] == "integrated"


def test_list_gpus_works_without_vulkaninfo(tmp_path, monkeypatch):
    """Ohne vulkaninfo bleibt die Liste stehen — nur der Name ist schlichter."""
    fake_glob = _fake_sysfs(tmp_path, [
        ("card0", "0x10de", "0x2482", "0000:01:00.0", "renderD128")])
    monkeypatch.setattr(gpu_select.glob, "glob", fake_glob)
    monkeypatch.setattr(gpu_select, "_vulkan_devices", lambda: {})
    monkeypatch.setattr(gpu_select, "_lspci_names", lambda: {})
    gpus = gpu_select.list_gpus()
    assert len(gpus) == 1
    assert gpus[0]["vendor"] == "nvidia"
    assert "NVIDIA" in gpus[0]["name"]


def test_env_forces_exactly_one_card(two_gpus, monkeypatch):
    """Rufzeichen = die Karte ist die einzige, die das Programm sieht."""
    monkeypatch.setattr(gpu_select, "_vendors_with_icd", lambda: {"amd"})
    gpu = gpu_select.find_gpu("1002:73df")
    env = gpu_select.env_for(gpu)
    assert env["MESA_VK_DEVICE_SELECT"] == "1002:73df!"
    assert env["MESA_VK_DEVICE_SELECT_FORCE_DEFAULT_DEVICE"] == "1"
    assert env["DRI_PRIME"] == "pci-0000_03_00_0"
    # Nur ein Hersteller hat Treiber -> keine Einschraenkung noetig
    assert "VK_DRIVER_FILES" not in env


def test_env_restricts_driver_when_two_vendors(two_gpus, monkeypatch, tmp_path):
    """Fehlt der Mesa-Layer, soll wenigstens der falsche Treiber wegbleiben."""
    icd = tmp_path / "icd"
    icd.mkdir()
    (icd / "radeon_icd.x86_64.json").write_text("{}")
    (icd / "nvidia_icd.json").write_text("{}")
    monkeypatch.setattr(gpu_select, "ICD_DIRS", (str(icd),))
    env = gpu_select.env_for(gpu_select.find_gpu("1002:73df"))
    assert env["VK_DRIVER_FILES"].endswith("radeon_icd.x86_64.json")
    assert env["VK_ICD_FILENAMES"] == env["VK_DRIVER_FILES"]


def test_nvidia_gets_prime_offload(tmp_path, monkeypatch):
    fake_glob = _fake_sysfs(tmp_path, [
        ("card0", "0x10de", "0x2482", "0000:01:00.0", "renderD128")])
    monkeypatch.setattr(gpu_select.glob, "glob", fake_glob)
    monkeypatch.setattr(gpu_select, "_vulkan_devices", lambda: {})
    monkeypatch.setattr(gpu_select, "_lspci_names", lambda: {})
    monkeypatch.setattr(gpu_select, "_vendors_with_icd", lambda: {"nvidia"})
    env = gpu_select.env_for(gpu_select.find_gpu("10de:2482"))
    assert env["__NV_PRIME_RENDER_OFFLOAD"] == "1"
    assert env["__GLX_VENDOR_LIBRARY_NAME"] == "nvidia"


def test_automatic_sets_nothing(two_gpus):
    assert gpu_select.env_for_id(gpu_select.AUTO) == {}
    base = {"PATH": "/usr/bin"}
    assert gpu_select.apply_to(base, "") == base


def test_apply_to_keeps_the_rest_of_the_environment(two_gpus, monkeypatch):
    monkeypatch.setattr(gpu_select, "_vendors_with_icd", lambda: {"amd"})
    env = gpu_select.apply_to({"PATH": "/usr/bin", "HOME": "/home/x"}, "1002:73df")
    assert env["PATH"] == "/usr/bin" and env["HOME"] == "/home/x"
    assert env["MESA_VK_DEVICE_SELECT"] == "1002:73df!"


# --------------------------------------------------------------------------- #
#  Oberflaeche
# --------------------------------------------------------------------------- #
class _FakeMain:
    """
    Das Noetigste, was der Streaming-Tab von der Hauptanwendung erwartet.

    Der Tab reicht beim Speichern auch Werte durch, die anderswo stehen
    (Tracking, Autostart) — ohne sie kaeme das Speichern nicht bis zur
    Datei, und genau das soll hier geprueft werden.
    """

    def __init__(self, qwidget):
        from types import SimpleNamespace
        self.is_loading = False
        self._stored_refresh_rate = "Auto"
        self.autostart_rows = []
        self.ui = SimpleNamespace(
            chk_steamvr_tracker=SimpleNamespace(isChecked=lambda: False),
            num_apps=SimpleNamespace(text=lambda: "0"))
        self._qwidget = qwidget

    def tracking_flags(self):
        return False, True


@pytest.fixture
def tab(qapp, tmp_path, monkeypatch, two_gpus):
    os.environ["HOME"] = str(tmp_path / "home")
    os.makedirs(os.environ["HOME"], exist_ok=True)
    from streaming_tab import StreamingTab
    gpu_select.list_gpus(refresh=True)        # vorab erkennen: Liste steht sofort
    widget = StreamingTab()
    widget.main_app = _FakeMain(widget)
    yield widget
    import shiboken6
    widget.close()
    shiboken6.delete(widget)
    qapp.processEvents()


def test_dropdown_lists_automatic_and_every_card(tab):
    texts = [tab.combo_gpu.itemText(i) for i in range(tab.combo_gpu.count())]
    data = [tab.combo_gpu.itemData(i) for i in range(tab.combo_gpu.count())]
    assert data == ["", "1002:73df", "8086:9bc4"]
    assert "Radeon" in texts[1] and "(" in texts[1]      # Name + dediziert/integriert
    assert tab.current_gpu_id() == ""                    # Standard: automatisch


def test_choice_is_saved_and_comes_back(tab, qapp):
    tab.combo_gpu.setCurrentIndex(1)
    tab._on_gpu_picked(1)
    from config_manager import load_saved_settings
    assert load_saved_settings()["gpu_device"] == "1002:73df"
    tab.apply_loaded_streaming_settings()
    assert tab.current_gpu_id() == "1002:73df"


def test_missing_card_stays_in_the_list_with_a_warning(tab):
    """Karte ausgebaut: Auswahl bleibt sichtbar statt still auf Auto zu fallen."""
    tab.reload_gpu_options(select="dead:beef")
    assert tab.current_gpu_id() == "dead:beef"
    assert "⚠" in tab.lbl_gpu_hint.text()


# --------------------------------------------------------------------------- #
#  WiVRns eigene Konfiguration
# --------------------------------------------------------------------------- #
def test_vaapi_encoder_gets_the_render_node(two_gpus, tmp_path, monkeypatch):
    """vaapi kennt ein eigenes 'device' — sonst kodiert die falsche Karte."""
    import config_manager as cm
    import vr_environment as venv

    wivrn = tmp_path / "wivrn.json"
    monkeypatch.setattr(venv, "wivrn_config_file", lambda: str(wivrn))
    monkeypatch.setattr(venv, "wivrn_at_least", lambda *a: True)

    cm.sync_with_wivrn({"encoder": "vaapi", "codec": "Automatic",
                        "gpu_device": "1002:73df"})
    assert json.loads(wivrn.read_text())["encoder"]["device"] == "/dev/dri/renderD129"

    # nvenc kennt den Schluessel nicht -> er wird auch nicht geschrieben
    cm.sync_with_wivrn({"encoder": "nvenc", "codec": "Automatic",
                        "gpu_device": "1002:73df"})
    assert "device" not in json.loads(wivrn.read_text())["encoder"]


# --------------------------------------------------------------------------- #
#  Erkennung nur einmal und nie im Haupt-Thread
# --------------------------------------------------------------------------- #
def test_detection_runs_once_per_session(tmp_path, monkeypatch):
    calls = []
    fake_glob = _fake_sysfs(tmp_path, [("card0", "0x1002", "0x73df", "0000:03:00.0", "renderD128")])
    monkeypatch.setattr(gpu_select.glob, "glob", fake_glob)
    monkeypatch.setattr(gpu_select, "_vulkan_devices", lambda: calls.append(1) or {})
    monkeypatch.setattr(gpu_select, "_lspci_names", lambda: {})
    assert gpu_select.cached_gpus() is None
    first = gpu_select.list_gpus()
    first[0]["name"] = "veraendert"               # Kopie — Cache bleibt heil
    assert gpu_select.list_gpus()[0]["name"] != "veraendert"
    assert calls == [1]
    gpu_select.list_gpus(refresh=True)
    assert calls == [1, 1]


def test_tab_detects_in_background(qapp, tmp_path, monkeypatch, two_gpus):
    """Ohne gemerkte Liste: sofort 'wird erkannt', Auswahl bleibt, Liste kommt nach."""
    import threading
    import time

    os.environ["HOME"] = str(tmp_path / "home")
    os.makedirs(os.environ["HOME"], exist_ok=True)
    gate = threading.Event()
    real = gpu_select._detect_gpus
    main_thread = threading.current_thread()
    seen = []

    def slow():
        seen.append(threading.current_thread() is main_thread)
        gate.wait(5)
        return real()
    monkeypatch.setattr(gpu_select, "_detect_gpus", slow)

    from streaming_tab import StreamingTab
    widget = StreamingTab()
    widget.main_app = _FakeMain(widget)
    widget.reload_gpu_options(select="1002:73df")
    assert widget.current_gpu_id() == "1002:73df"          # gemerkte Auswahl steht
    assert not widget.btn_gpu_rescan.isEnabled()
    gate.set()
    for _ in range(200):
        qapp.processEvents()
        if widget.combo_gpu.count() == 3:
            break
        time.sleep(0.01)
    data = [widget.combo_gpu.itemData(i) for i in range(widget.combo_gpu.count())]
    assert data == ["", "1002:73df", "8086:9bc4"]
    assert widget.current_gpu_id() == "1002:73df"
    assert widget.btn_gpu_rescan.isEnabled()
    assert seen and not any(seen)                          # nie im Haupt-Thread
    import shiboken6
    widget.close()
    shiboken6.delete(widget)
    qapp.processEvents()
