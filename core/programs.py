#!/usr/bin/env python3
"""
programs.py — Zentrale Programmliste für yakuda-connect
========================================================
Felder:
  key       : Eindeutiger interner Schlüssel
  name      : Anzeigename
  pkg       : AUR-Paketname (für yay/paru)
  desc      : Beschreibung (Deutsch)
  desc_eng  : Beschreibung (Englisch)
  start_cmd : Startbefehl
  link      : Webseite

Installationsmethoden (distro-abhängig automatisch gefiltert):
  install_methods : Liste erlaubter Methoden, Teilmenge von
                    {"appimage", "aur", "flatpak", "rpm", "cargo"}. Fehlt das Feld, wird aus
                    install_type/Feldern abgeleitet.
                      * "aur"     -> nur auf Arch-Distros, wenn yay oder paru da ist
                      * "appimage"-> überall, wenn github_repo/appimage_url gesetzt
                      * "flatpak" -> überall, wenn flatpak installiert + flatpak_id gesetzt
                      * "cargo"   -> überall; baut per 'cargo install' nach
                                     ~/.config/yakuda-connect/tools/cargo/<key>/
                                     (Rust/Compiler werden bei Bedarf nachinstalliert)
                    Sind mehrere Methoden verfügbar, zeigt die Karte ein
                    Dropdown. Vorauswahl: AppImage; sonst yay; sonst die erste.
  github_repo      : "owner/repo" -> neueste passende Release wird automatisch geholt
  appimage_url     : feste Download-URL (Alternative zu github_repo)
  version          : feste Version (nur bei fester appimage_url)
  asset_match      : Welche AppImage-Datei genommen wird (nur bei github_repo):
                     ".AppImage" (Arch automatisch) | "_x64.AppImage" | "x86_64.AppImage"
  include_prerelease: True/False -> auch Vorab-Versionen berücksichtigen
  flatpak_id       : Flatpak-App-ID (z. B. "com.vysp3r.ProtonPlus")
  crate            : Name des Rust-Crates fuer "cargo" (Standard: key)
  cargo_git        : Git-URL -> "cargo install --git <url>" statt crates.io
  cargo_sys_deps   : {"arch": [...], "fedora": [...], "debian": [...], "suse": [...]}
                     Systempakete, die vor dem Cargo-Build da sein muessen
  config_dirs      : Ordnernamen in ~/.config zur Erkennung/zum Löschen
  icon_url         : Icon (GitHub blob- oder raw-URL)
  launch_args      : Zusätzliche Startargumente für die AppImage
                     (z. B. VRCX: "--no-install --no-desktop").
  terminal         : true -> der "▶ Starten"-Knopf der Karte öffnet ein
                     Terminalfenster statt das Programm still zu starten.
                     Für Kommandozeilenprogramme (obah ist eine TUI,
                     XR HOTAS und adb schreiben auf die Konsole) — ohne
                     Terminal sähe man von ihnen gar nichts.
                     Gestartet wird über core/tool_launcher.py.
  remove_entries   : Vom Programm selbst angelegte .desktop-/Autostart-Dateien,
                     die bei Installation/Deinstallation entfernt werden (Pfade mit ~).
  note / note_eng  : Optionaler Hinweis (klein, kursiv, gelb) unter der
                     Beschreibung — z. B. Installations-Hinweise für Nutzer,
                     denen keine Methode zur Verfügung steht (kein AppImage
                     auf Nicht-Arch-Systemen o. Ä.).

Hinweis zur Distro-Logik:
  Es gibt bewusst KEINE getrennten Listen pro Distro. Stattdessen entscheidet
  zur Laufzeit detect_install_methods(): Arch-Distros bekommen yay/paru, alle
  Distros AppImage/Flatpak – je nachdem, was vorhanden ist.

  WICHTIG: Flatpak ist NUR noch für Tools erlaubt (dieser Tab hier).
  Die WiVRn-Runtime im Installations-Tab wird ausschließlich nativ
  installiert (Arch: AUR, Fedora: dnf, Ubuntu: Anleitung zum Selbstbauen).
"""
import json
import os

import paths
from logging_setup import get_logger

log = get_logger("programs")

INSTALL_PACKAGES = {
    "WiVRn / Monado": ["wivrn-server", "lib32-wivrn-server"],
    "WiVRn Dashboard": ["wivrn-dashboard"],
    "xrizer": ["xrizer", "xrizer-common"],
    "opencomposite": ["opencomposite-git"],
}

# Runtime-Quelle für Fedora (Installations-Tab, offizielle Repos):
#   wivrn           : https://packages.fedoraproject.org/pkgs/wivrn/wivrn/
#   wivrn-dashboard : Subpaket von wivrn, eigenes RPM
#   opencomposite   : https://packages.fedoraproject.org/pkgs/opencomposite/opencomposite/
#
# Die Schluessel muessen zu INSTALL_PACKAGES passen, damit die Statuszeilen
# im Installations-Tab auf beiden Distros gleich heissen.
#
# NICHT dabei:
#   * xrizer — gibt es in den offiziellen Fedora-Repos NICHT, nur als COPR
#     (@xr-sig/xrizer). Steht deshalb in INSTALL_DNF_COPR statt hier.
#     'envision-xrizer' ist KEIN xrizer, sondern nur die Build-Abhaengigkeiten,
#     die Envision zum Selbstbauen braucht.
#   * lib32-* — Fedora loest 32-Bit ueber Multilib (wivrn.i686) und zieht das
#     bei Bedarf selbst; ein eigenes lib32-Paket wie im AUR gibt es nicht.
INSTALL_DNF = {
    "WiVRn / Monado": ["wivrn"],
    "opencomposite": ["opencomposite"],
}

# Warum steht 'wivrn-dashboard' hier NICHT, obwohl es das RPM gibt?
#   * 'wivrn' zieht es nicht als Abhaengigkeit mit — es waere also eine eigene
#     Zeile noetig, siehe https://packages.fedoraproject.org/pkgs/wivrn/wivrn-dashboard/
#   * das Dashboard macht auf Fedora Aerger (zweite Oberflaeche, die dieselbe
#     config.json und denselben Server anfasst)
#   * und es waere doppelt gemoppelt: wer yakuda-connect nutzt, hat die
#     Steuerung schon.
# Auf Arch bleibt es in INSTALL_PACKAGES — dort ist es Teil der ueblichen
# AUR-Installation und niemand wuerde es vermissen wollen.

# Rueckfall-Erkennung ueber die Binary im PATH: wer WiVRn selbst gebaut oder
# aus einem COPR geholt hat, hat kein passendes RPM — die Statuszeile darf
# dann trotzdem nicht "fehlt" behaupten.
DNF_BINARY_FALLBACK = {
    "WiVRn / Monado": "wivrn-server",
}

# --------------------------------------------------------------------------- #
#  Fedora-Komponenten aus einem COPR
# --------------------------------------------------------------------------- #
# Gleicher Aufbau wie INSTALL_DNF, nur mit der Zusatzangabe, welches COPR
# vorher aktiviert werden muss. Der Installations-Tab zeigt diese Eintraege
# als ganz normale Statuszeile; der Installations-Knopf aktiviert das COPR und
# installiert das Paket im selben sichtbaren Terminalfenster wie jede andere
# Installation auch. Frueher musste der Nutzer die beiden Befehle aus einem
# Hinweisfenster in die Zwischenablage holen und selbst einfuegen.
#
# Weil ein COPR ein FREMDES Repository ist (kein offizielles Fedora-Repo),
# fragt die App vorher einmal nach. Ohne Zustimmung wird der Eintrag einfach
# uebersprungen, der Rest der Installation laeuft normal weiter.
FEDORA_XRIZER_COPR = "@xr-sig/xrizer"

# Belegt auf der COPR-Projektseite selbst: dort steht als Steam-Startoption
#   VR_OVERRIDE=/run/host/usr/lib64/xrizer/runtime %command%
# Das /run/host davor ist nur die Sicht aus dem Steam-Container heraus; auf dem
# System liegt die Runtime also unter /usr/lib64/xrizer/runtime — eine Ebene
# unter dem Ordner, den wir kannten. Genau dafuer gibt es resolve_compat_root().
FEDORA_XRIZER_RUNTIME = "/usr/lib64/xrizer/runtime"

# Ebenfalls von der Projektseite: "This copr will go away after all packages
# have been reviewed and imported into Fedora." Das COPR ist also eine
# Zwischenloesung mit Ablaufdatum — ein Grund mehr, den GitHub-Weg als
# gleichwertige Quelle anzubieten und nicht als Notnagel.
INSTALL_DNF_COPR = {
    "xrizer": {"copr": FEDORA_XRIZER_COPR, "pkgs": ["xrizer"]},
}


# --------------------------------------------------------------------------- #
#  Debian / Ubuntu / Linux Mint
# --------------------------------------------------------------------------- #
# WiVRn liegt NICHT in den offiziellen Ubuntu-Quellen, sondern in der PPA des
# Linux-VR-Adventures-Projekts. Das ist dieselbe Lage wie bei Fedora und
# xrizer: ein Fremdrepository, das erst aktiviert werden muss — und deshalb
# auch dieselbe Rueckfrage, bevor die App das tut.
#
# 'wivrn-dashboard' gibt es dort ebenfalls und es zieht 'wivrn-server' mit.
# Angeboten wird trotzdem nur der Server: das Dashboard ist eine zweite
# Oberflaeche auf derselben config.json und demselben Dienst — wer
# yakuda-connect nutzt, braucht sie nicht (gleiche Begruendung wie auf Fedora).
UBUNTU_WIVRN_PPA = "ppa:lvra/wivrn"

# Zweiter Weg, wenn die PPA fuer die Ubuntu-Ausgabe des Systems nicht baut —
# auf Linux Mint 22.x (Basis noble) genau der Fall: 'Cannot add PPA: This PPA
# does not support noble'. Der Flatpak von Flathub gibt es fuer jede
# Distribution und er bringt xrizer UND OpenComposite gleich mit.
#
# Preis dafuer (steht so auch im Wiki des Projekts): in der Sandbox
# funktionieren SteamVR-Lighthouse-Tracker nicht, und die Konfiguration liegt
# unter ~/.var/app/io.github.wivrn.wivrn/ statt ~/.config/wivrn/. Die
# Steuerung des Servers aus yakuda-connect heraus ist damit eingeschraenkt —
# installieren und erkennen geht, alles Weitere folgt spaeter.
WIVRN_FLATPAK_ID = "io.github.wivrn.wivrn"

# Anleitung fuer die native Installation auf Debian/Ubuntu/Mint.
#
# Auf diesen Systemen ist der native Weg mit so vielen Sonderfaellen behaftet
# (PPA ohne Build fuer die eigene Ausgabe, fehlender OpenVR-Uebersetzer,
# Selbstbau von OpenComposite), dass die App ihn nicht mehr automatisiert.
# Wer ihn trotzdem gehen will, bekommt eine Anleitung — und yakuda-connect
# erkennt das Ergebnis danach von selbst (ueber wivrn-server im PATH,
# siehe APT_BINARY_FALLBACK).
#
# VIDEO leer lassen, solange keines hinterlegt ist: ein toter YouTube-Link ist
# schlimmer als gar keiner. Ist es gesetzt, oeffnet der Knopf das Video, sonst
# die Wiki-Seite.
NATIVE_GUIDE_VIDEO_URL = ""
NATIVE_GUIDE_URL = "https://wiki.vronlinux.org/docs/fossvr/wivrn/#installing-wivrn"


def native_guide_url():
    """Video, wenn eines hinterlegt ist — sonst die Wiki-Anleitung."""
    return NATIVE_GUIDE_VIDEO_URL or NATIVE_GUIDE_URL

INSTALL_APT = {
    "WiVRn / Monado": ["wivrn-server"],
}

# Die PPA enthaelt KEINEN OpenVR-Uebersetzer. Ohne xrizer oder OpenComposite
# startet unter Proton kein einziges SteamVR-Spiel. Fuer xrizer gibt es das
# Release-ZIP auf GitHub (core/xrizer_github.py) — das braucht weder Repo noch
# root und funktioniert auf jeder Distribution gleich. OpenComposite hat kein
# vergleichbares Release-Archiv und wird auf apt-Systemen deshalb nicht
# angeboten; wer es will, baut es selbst und waehlt den Ordner im
# Streaming-Tab von Hand aus.
APT_GITHUB_COMPONENTS = {
    "xrizer": ["xrizer"],
}

# Rueckfall-Erkennung ueber die Binary, analog zu DNF_BINARY_FALLBACK.
APT_BINARY_FALLBACK = {
    "WiVRn / Monado": "wivrn-server",
}


def apt_github_groups():
    """{Anzeigename: [Kennungen]} — Statuszeilen fuer die GitHub-Komponenten."""
    return {name: list(pkgs) for name, pkgs in APT_GITHUB_COMPONENTS.items()}


# --------------------------------------------------------------------------- #
#  Bezugsquellen je Komponente
# --------------------------------------------------------------------------- #
# Manche Komponenten gibt es auf mehreren Wegen. Statt eine Quelle fuer alle
# vorzugeben, entscheidet der Nutzer pro Zeile im Installations-Tab.
#
# Vorauswahl ist bewusst der ERSTE Eintrag der Liste. Bei xrizer auf Fedora
# ist das das COPR: es ist der Weg, den das Projekt selbst vorgibt, und die
# Pakete sind auf dem Weg in die offiziellen Fedora-Repos. Das GitHub-Release
# bleibt als zweite Quelle daneben — fuer den Fall, dass das COPR wieder in
# Zeitueberschreitungen laeuft (Curl error 28) oder, wie auf der Projektseite
# angekuendigt, irgendwann verschwindet.
SOURCE_GITHUB = "github"
SOURCE_COPR = "copr"
SOURCE_PPA = "ppa"
SOURCE_FLATPAK = "flatpak"
SOURCE_GUIDE = "guide"

SOURCE_LABELS = {
    "dnf": "Fedora-Repos",
    SOURCE_COPR: f"COPR {FEDORA_XRIZER_COPR}",
    SOURCE_PPA: f"PPA {UBUNTU_WIVRN_PPA.replace('ppa:', '')}",
    SOURCE_FLATPAK: "Flatpak (Flathub)",
    SOURCE_GUIDE: "Nativ (Anleitung)",
    SOURCE_GITHUB: "GitHub-Release",
    "yay": "AUR (yay)",
    "paru": "AUR (paru)",
    "native": "System",
}


def component_sources(method, name):
    """
    Welche Bezugsquellen hat diese Komponente? Liste von Kennungen, erste =
    Vorauswahl. Eine leere Liste bedeutet: nichts zu installieren.
    """
    if method == "dnf":
        if name in INSTALL_DNF_COPR:
            return [SOURCE_COPR, SOURCE_GITHUB]
        return ["dnf"]
    if method == "apt":
        # Auf Debian-Systemen gibt es je Komponente genau einen Weg: WiVRn aus
        # der PPA, xrizer aus dem GitHub-Release. Ein Dropdown erscheint
        # deshalb nicht — es gaebe nichts auszuwaehlen.
        if name in APT_GITHUB_COMPONENTS:
            return [SOURCE_GITHUB]
        # WiVRn: Flatpak ZUERST und damit Vorauswahl.
        #
        # Der native Weg ist auf Debian-Systemen kein gleichwertiger zweiter
        # Weg, sondern ein Minenfeld: die PPA baut fuer Ubuntu 24.04 ('noble',
        # Basis von Mint 22.x) gar nicht, ein OpenVR-Uebersetzer fehlt dort
        # ohnehin, und OpenComposite muesste selbst gebaut werden. Der Flatpak
        # bringt alles mit und laeuft auf jeder Ausgabe.
        #
        # Die PPA bleibt waehlbar — auf Ausgaben, fuer die sie baut, ist sie
        # der bessere Weg (volle Steuerung, Lighthouse-Tracker). Und wer es
        # ganz von Hand will, bekommt ueber SOURCE_GUIDE die Anleitung.
        return [SOURCE_FLATPAK, SOURCE_PPA, SOURCE_GUIDE]
    if method == "flatpak":
        # SteamOS: nur der Flatpak (xrizer/OpenComposite stecken darin).
        return [SOURCE_FLATPAK]
    if method in ("yay", "paru"):
        # xrizer gibt es auch auf Arch als Release-ZIP — praktisch, wenn der
        # AUR-Build gerade klemmt.
        if name == "xrizer":
            return [method, SOURCE_GITHUB]
        return [method]
    return []



def dnf_copr_groups():
    """{Anzeigename: [Paketnamen]} — fuer die Statuszeilen im Installations-Tab."""
    return {name: list(cfg["pkgs"]) for name, cfg in INSTALL_DNF_COPR.items()}


def dnf_copr_for_package(pkg):
    """COPR-Kennung fuer ein Paket, oder None wenn es aus den Fedora-Repos kommt."""
    for cfg in INSTALL_DNF_COPR.values():
        if pkg in cfg["pkgs"]:
            return cfg["copr"]
    return None

# --------------------------------------------------------------------------- #
#  Werkzeuglisten aus config/tools.json
# --------------------------------------------------------------------------- #
# Die Eintraege standen frueher als Python-Literale hier im Modul. Das hiess:
# jedes neue Tool war eine Code-Aenderung, und wer sich ein eigenes eintragen
# wollte, musste eine installierte .py-Datei editieren — beim naechsten Update
# ueberschrieben.
#
# Jetzt gilt dieselbe Regel wie bei der Spieledatenbank:
#   1. <App-Ordner>/config/tools.json              (mitgeliefert)
#   2. ~/.config/yakuda-connect/config/tools.json  (eigene Ergaenzungen)
# Beide werden gelesen und ADDIERT — die Nutzerdatei ersetzt die mitgelieferte
# also nicht, sondern haengt an bzw. ueberschreibt gezielt einzelne Eintraege
# ueber denselben "key". So bleiben eigene Tools ein App-Update lang bestehen,
# ohne dass der Nutzer die kuratierte Liste mitpflegen muss.
#
# Der Aufbau der Felder ist unveraendert und im Modulkopf oben beschrieben.

APP_DIR           = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_JSON_BUNDLED = os.path.join(APP_DIR, "config", "tools.json")
TOOLS_JSON_USER    = paths.config_file("tools.json")


def _read_tools_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        # Eine kaputte Nutzerdatei darf den Tools-Tab nicht leer lassen.
        log.warning("tools.json nicht lesbar (%s) — %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _merge_tools(base, extra):
    """Haengt extra an base an; gleicher 'key' ersetzt den bestehenden Eintrag.

    Ersetzen statt Anhaengen ist wichtig: wer einen mitgelieferten Eintrag
    korrigieren will (andere AppImage-URL, anderer Startbefehl), soll ihn
    ueberschreiben koennen und nicht dieselbe Karte zweimal sehen.
    """
    out = list(base)
    index = {t.get("key"): i for i, t in enumerate(out) if isinstance(t, dict)}
    for entry in extra:
        if not isinstance(entry, dict) or not entry.get("key"):
            continue
        pos = index.get(entry["key"])
        if pos is None:
            index[entry["key"]] = len(out)
            out.append(entry)
        else:
            out[pos] = entry
    return out


def load_tools_config():
    """Liest die mitgelieferte tools.json und ergaenzt sie um die Nutzerkopie."""
    bundled = _read_tools_json(TOOLS_JSON_BUNDLED)
    user    = _read_tools_json(TOOLS_JSON_USER)
    apps = _merge_tools(bundled.get("apps", []) or [], user.get("apps", []) or [])
    osc  = _merge_tools(bundled.get("osc", [])  or [], user.get("osc", [])  or [])
    return apps, osc


TOOLS_APPS, TOOLS_OSC = load_tools_config()


def reload_tools_config():
    """Werkzeuglisten neu einlesen (nach dem Bearbeiten der Nutzerdatei)."""
    global TOOLS_APPS, TOOLS_OSC
    TOOLS_APPS, TOOLS_OSC = load_tools_config()
    return TOOLS_APPS, TOOLS_OSC


def all_tools():
    """Alle Werkzeuge beider Seiten in einer Liste (Anwendungen + OSC)."""
    return list(TOOLS_APPS) + list(TOOLS_OSC)
