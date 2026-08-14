#!/usr/bin/env python3
"""
tests/test_firewall.py — Erkennung und Befehle der Firewall-Freigabe
====================================================================
Warum diese Tests: Der Fehler, den sie absichern, war nicht sichtbar. Auf
einem Fedora-System mit installiertem (aber ungenutztem) ufw schrieb die App
eine ufw-Regel, meldete "Erfolg" — und die Ports blieben zu, weil firewalld
zustaendig war. Der Nutzer sucht den Fehler dann ueberall, nur nicht hier.

Von Hand braeuchte man vier Distributionen, um das durchzuspielen. Mit
gefaelschtem ``proc`` sind es Millisekunden.

Laeuft ohne Qt, ohne Netz und ohne echte Firewall.
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

import firewall as fw  # noqa: E402


class FakeProc:
    """Ersetzt core/proc.py: welche Programme es gibt, welche Dienste laufen."""

    def __init__(self, binaries=(), running=(), states=None):
        self.binaries = set(binaries)
        self.running = set(running)
        self.states = states or {}
        self.calls = []

    def which(self, name):
        return name in self.binaries

    def run(self, cmd, **kwargs):
        self.calls.append(cmd)
        if cmd[:2] == ["systemctl", "is-active"]:
            unit = cmd[-1]
            return _Res(0 if unit in self.running else 3)
        if cmd[:1] == ["pkexec"]:
            return _Res(0)
        return _Res(1)

    def output_of(self, cmd, timeout=None, default="", **kwargs):
        if cmd[:1] == ["firewall-cmd"] and "--state" in cmd:
            return self.states.get("firewall-cmd", "")
        return default


class _Res:
    def __init__(self, rc, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = rc, stdout, stderr


@pytest.fixture
def fake(monkeypatch):
    def _install(**kwargs):
        f = FakeProc(**kwargs)
        monkeypatch.setattr(fw.proc, "which", f.which)
        monkeypatch.setattr(fw.proc, "run", f.run)
        monkeypatch.setattr(fw.proc, "output_of", f.output_of)
        return f
    return _install


def test_firewalld_wins_over_installed_but_unused_ufw(fake):
    """Der eigentliche Bug: Fedora/Nobara/Bazzite haben firewalld aktiv,
    ufw kann trotzdem installiert sein."""
    fake(binaries=("firewall-cmd", "ufw"), states={"firewall-cmd": "running"})
    info = fw.detect()
    assert info["kind"] == fw.FIREWALLD
    assert info["active"] is True


def test_ufw_detected_when_no_firewalld(fake, monkeypatch):
    fake(binaries=("ufw",), running=("ufw",))
    monkeypatch.setattr(fw, "_ufw_enabled", lambda: True)
    info = fw.detect()
    assert info["kind"] == fw.UFW
    assert info["active"] is True


def test_no_firewall_is_not_an_error(fake):
    """Auf Arch/CachyOS laeuft ab Werk keine Firewall — das darf keine
    Fehlermeldung ausloesen, sondern muss als 'nichts zu tun' ankommen."""
    fake(binaries=())
    assert fw.detect()["kind"] is None


def test_nftables_is_detected_but_not_supported(fake):
    fake(binaries=("nft",), running=("nftables",))
    info = fw.detect()
    assert info["kind"] == fw.NFTABLES
    assert info["kind"] not in fw.SUPPORTED
    with pytest.raises(ValueError):
        fw._script(fw.NFTABLES)          # darf niemals automatisch laufen
    assert any("9757" in c for c in fw.manual_commands(fw.NFTABLES))


def test_installed_but_stopped_firewall_still_gets_a_rule(fake, monkeypatch):
    """Regel hinterlegen lohnt auch bei ausgeschalteter Firewall — sie greift,
    sobald der Nutzer sie einschaltet."""
    fake(binaries=("firewall-cmd",), states={"firewall-cmd": "not running"})
    info = fw.detect()
    assert info["kind"] == fw.FIREWALLD
    assert info["active"] is False


@pytest.mark.parametrize("kind", [fw.UFW, fw.FIREWALLD])
def test_script_opens_all_three_ports(kind):
    """9757/tcp, 9757/udp und mDNS 5353/udp — Letzteres fehlte frueher, und
    ohne mDNS bleibt die Serverliste in der Brille leer."""
    script = fw._script(kind)
    assert "9757" in script
    assert "5353" in script or "mdns" in script


def test_ufw_profile_matches_wivrn_dashboard():
    """Gleicher Pfad und gleicher Profilname wie WiVRns eigenes Dashboard —
    sonst stehen am Ende zwei Regeln fuer dieselbe Sache im System."""
    assert fw.UFW_PROFILE_PATH == "/etc/ufw/applications.d/wivrn"
    assert "[WiVRn]" in fw.UFW_PROFILE
    assert "ufw allow wivrn" in fw._script(fw.UFW)


def test_setup_runs_in_a_single_pkexec_call(fake):
    """Eine Passwortabfrage, nicht zwei."""
    f = fake(binaries=("ufw",))
    ok, err = fw.apply(fw.UFW)
    assert ok and not err
    pkexec_calls = [c for c in f.calls if c[:1] == ["pkexec"]]
    assert len(pkexec_calls) == 1


def test_already_configured_only_answers_where_it_can(tmp_path, monkeypatch):
    """firewalld wird bewusst NICHT abgefragt: 'firewall-cmd --list-services'
    loest auf manchen Systemen eine Passwortabfrage aus (WiVRn hat seine
    eigene Pruefung genau deswegen abgeschaltet)."""
    monkeypatch.setattr(fw, "UFW_PROFILE_PATH", str(tmp_path / "wivrn"))
    assert fw.already_configured(fw.UFW) is False
    (tmp_path / "wivrn").write_text("[WiVRn]\n")
    assert fw.already_configured(fw.UFW) is True
    assert fw.already_configured(fw.FIREWALLD) is False
