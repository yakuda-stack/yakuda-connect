#!/usr/bin/env python3
"""
core/autostart_name.py — Anzeigename einer Autostart-Zeile
==========================================================
Gespeichert wird nur ein Name, den der Nutzer selbst eintraegt. Sonst kommt
er aus dem Befehl, damit alte Configs und geaenderte Befehle stimmen:

    wayvr                              -> WayVR (Eintrag im Tools-Tab)
    flatpak run org.vrcx.App           -> App
    /home/u/Apps/VRCX.AppImage         -> VRCX

Kein Qt — mit einfachen Tests pruefbar.
"""
import os
import re

import killcmd_suggest as ks


def _flatpak_id(cmd):
    toks = ks._tokens(cmd)
    if toks and os.path.basename(toks[0]) == "flatpak" and "run" in toks:
        rest = [t for t in toks[toks.index("run") + 1:] if not t.startswith("-")]
        return rest[0] if rest else ""
    return ""


def _plain(name):
    name = (name or "").lower()
    return name[:-len(".appimage")] if name.endswith(".appimage") else name


def _is_steam_start(cmd, tool):
    """Startet der Befehl dieses Tool ueber Steam (-applaunch <AppID>)?"""
    appid = tool.get("steam_appid")
    return bool(appid and re.search(rf"-applaunch\s+{appid}\b", cmd))


def find_tool(cmd, mode="CMD", tools=()):
    """Eintrag aus dem Tools-Tab, zu dem der Befehl gehoert, oder None."""
    if not (cmd or "").strip():
        return None
    program = _plain(ks.program_name(cmd, mode))
    flatpak = _flatpak_id(cmd) if mode == "CMD" else ""
    for tool in tools:
        start = (tool.get("start_cmd") or "").strip()
        if _is_steam_start(cmd, tool):
            return tool
        if flatpak and flatpak == tool.get("flatpak_id"):
            return tool
        if start and program and _plain(ks.program_name(start)) == program:
            return tool
    return None


def is_tool_command(cmd, tools=()):
    """Ist das genau der Startbefehl eines Programms aus dem Tools-Tab?"""
    cmd = (cmd or "").strip()
    if not cmd:
        return False
    for tool in tools:
        start = f"{tool.get('start_cmd') or ''} {tool.get('launch_args') or ''}".strip()
        if start == cmd or _is_steam_start(cmd, tool):
            return True
    return False


def display_name(cmd, mode="CMD", name="", tools=()):
    """Name fuer die Zeile: eigener Name, Tool-Name oder aus dem Befehl."""
    if (name or "").strip():
        return name.strip()
    if not (cmd or "").strip():
        return ""
    tool = find_tool(cmd, mode, tools)
    if tool:
        return tool.get("name", "")
    program = ks.program_name(cmd, mode)
    flatpak = _flatpak_id(cmd) if mode == "CMD" else ""
    if flatpak:
        return flatpak.rsplit(".", 1)[-1]
    if program.lower().endswith(".appimage"):
        return program[:-len(".appimage")]
    return program
