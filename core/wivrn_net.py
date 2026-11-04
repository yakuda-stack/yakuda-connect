#!/usr/bin/env python3
"""
core/wivrn_net.py — Verbindung & Bildqualitaet (WiVRn-Server-Konfiguration)
===========================================================================
Vier Einstellungen aus WiVRns docs/configuration.md, die es nur in der
config.json gibt (nicht im Headset):

  bit-depth        10 = weniger Farbstreifen. Nur vaapi/nvenc mit h265/av1.
  tcp-only         Nur TCP (VPN, strenge Firewall). Etwas mehr Latenz.
  hostname         Eigener Name in der Serverliste im Headset.
  publish-service  null = keine automatische Erkennung (Avahi), im Headset
                   wird die IP von Hand eingegeben. Dazu passend: port.

Die Oberflaeche liest den Stand direkt aus WiVRns config.json (read_current)
und schreibt ihn ueber config_manager.sync_with_wivrn zurueck (apply). Nicht
gesetzt = Schluessel fehlt = WiVRn-Standard.

Kein Qt — mit einfachen Tests pruefbar.
"""
import socket

DEFAULT_PORT = 9757
TEN_BIT_ENCODERS = ("auto", "nvenc", "vaapi")


def ten_bit_possible(encoder_name):
    """10 Bit geht nur mit vaapi oder nvenc (Auto waehlt eines davon,
    ausser es gibt keine GPU-Kodierung — dann ignoriert WiVRn den Wert)."""
    return (encoder_name or "auto").strip().lower() in TEN_BIT_ENCODERS


def read_current(wivrn_data):
    d = wivrn_data if isinstance(wivrn_data, dict) else {}
    try:
        port = int(d.get("port", DEFAULT_PORT))
    except (TypeError, ValueError):
        port = DEFAULT_PORT
    return {
        "bit10": d.get("bit-depth") == 10,
        "tcp_only": d.get("tcp-only") is True,
        "hostname": d.get("hostname") if isinstance(d.get("hostname"), str) else "",
        "manual": "publish-service" in d and d.get("publish-service") is None,
        "port": port,
    }


def apply(wivrn_data, settings, encoder_name="auto"):
    """settings (aus read_current-Form) in WiVRns config-Dict schreiben."""
    s = settings or {}
    if s.get("bit10") and ten_bit_possible(encoder_name):
        wivrn_data["bit-depth"] = 10
    else:
        wivrn_data.pop("bit-depth", None)
    if s.get("tcp_only"):
        wivrn_data["tcp-only"] = True
    else:
        wivrn_data.pop("tcp-only", None)
    name = (s.get("hostname") or "").strip()
    if name:
        wivrn_data["hostname"] = name
    else:
        wivrn_data.pop("hostname", None)
    if s.get("manual"):
        wivrn_data["publish-service"] = None
    else:
        wivrn_data.pop("publish-service", None)
    try:
        port = int(s.get("port", DEFAULT_PORT))
    except (TypeError, ValueError):
        port = DEFAULT_PORT
    if port != DEFAULT_PORT and 1024 <= port <= 65535:
        wivrn_data["port"] = port
    else:
        wivrn_data.pop("port", None)
    return wivrn_data


def local_ip():
    """IP dieses PCs im lokalen Netz (fuer die manuelle Eingabe im Headset).
    Schickt nichts — UDP-connect legt nur die ausgehende Schnittstelle fest."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.255.255", 9))
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()
