#!/usr/bin/env python3
"""
core/firewall.py — Ports fuer WiVRn freigeben, distro-unabhaengig
=================================================================
Was WiVRn wirklich braucht (steht so in WiVRns README):

    9757/tcp + 9757/udp   Verbindung Headset <-> PC
    5353/udp              mDNS/Avahi — DARUEBER FINDET das Headset den PC

Der zweite Punkt fehlte hier bisher komplett. Ist 5353 zu, bleibt die
Serverliste in der Brille leer, obwohl 9757 offen ist — der haeufigste
"WiVRn findet meinen PC nicht"-Fall ueberhaupt.

--------------------------------------------------------------------------
Wie WiVRn es macht (dashboard/firewall.cpp) und was wir davon uebernehmen
--------------------------------------------------------------------------
* Reihenfolge: ZUERST firewalld (laeuft der Dienst?), DANN ufw. Bisher haben
  wir umgekehrt geprueft und nur nachgesehen, ob das ufw-BINARY existiert.
  Auf Fedora/Nobara/Bazzite ist firewalld aktiv, aber ufw kann trotzdem
  installiert sein — dann schrieben wir eine ufw-Regel, die niemand liest,
  und meldeten "Erfolg". Genau umgekehrt zu dem, was noetig war.
* ufw: Anwendungsprofil /etc/ufw/applications.d/wivrn schreiben und
  'ufw allow wivrn' — identisch zu WiVRns do_setup(), damit die Regel
  denselben Namen traegt und nicht doppelt existiert.
* firewalld: bevorzugt den benannten Dienst 'wivrn' (den WiVRn als
  /usr/lib/firewalld/services/wivrn.xml mitliefert) statt roher Ports.
  Fehlt er, werden die Ports einzeln freigegeben.
* Alles in EINEM pkexec-Aufruf pro Firewall. Vorher waren es zwei — der
  Nutzer wurde zweimal nach seinem Passwort gefragt.

--------------------------------------------------------------------------
Was wir zusaetzlich machen
--------------------------------------------------------------------------
* nftables und iptables werden erkannt, aber NICHT automatisch veraendert.
  Dort gibt es keine stabile Stelle, an die man eine Regel haengen koennte
  (Tabellen- und Kettennamen sind bei jeder Distro anders), und eine falsch
  eingehaengte Regel kann ein System vom Netz nehmen. Stattdessen liefern
  wir die fertigen Befehle zum Kopieren.
* "Keine Firewall gefunden" ist ein normaler Zustand, kein Fehler — auf
  Arch/CachyOS ist ab Werk keine aktiv. Das war bisher eine Warnung mit
  rotem Ausrufezeichen (auf GitHub gemeldet).

Das Modul ist bewusst frei von Qt: so laeuft es im Test ohne Anzeige.
"""

import os

import proc
from logging_setup import get_logger

log = get_logger("firewall")

PORT = 9757
MDNS_PORT = 5353

# Anwendungsprofil, exakt wie WiVRns Dashboard es schreibt
# (dashboard/firewall.cpp, class ufw::do_setup).
#
# Warum es genau so aussehen muss:
#   * Der Abschnittsname [WiVRn] ist der Regelname, unter dem die Freigabe
#     spaeter in 'ufw status' und in grafischen Firewall-Werkzeugen steht.
#   * 'title', 'description' und 'ports' sind bei ufw PFLICHTFELDER. Fehlt
#     eines oder ist es leer, lehnt ufw das Profil mit einem Fehler ab
#     (ufw/applications.py, verify_profile).
#   * 'ports=9757' OHNE Protokollangabe bedeutet bei ufw "beide" — die Regel
#     gilt fuer TCP und UDP zugleich und wird als '9757/any' gefuehrt
#     (ufw/applications.py -> util.parse_port_proto). Ein 'ports=9757/tcp'
#     waere also FALSCH: die UDP-Haelfte der WiVRn-Verbindung fehlte dann.
#   * Der Dateiname (klein: 'wivrn') ist der, den WiVRn in need_setup()
#     abfragt. Er darf sich nicht aendern, sonst haelt WiVRns Dashboard die
#     Firewall fuer nicht eingerichtet.
UFW_PROFILE_PATH = "/etc/ufw/applications.d/wivrn"
UFW_PROFILE = (
    "[WiVRn]\\n"
    "title=WiVRn server\\n"
    "description=WiVRn OpenXR streaming server\\n"
    f"ports={PORT}\\n"
)

# Rueckgabewerte von detect()["kind"]
FIREWALLD = "firewalld"
UFW = "ufw"
NFTABLES = "nftables"
IPTABLES = "iptables"
NONE = None

# Welche Firewalls koennen wir selbst einrichten?
SUPPORTED = (FIREWALLD, UFW)


def _service_active(unit: str) -> bool:
    """systemctl is-active <unit> — ohne systemd (Runit/OpenRC) einfach False."""
    return proc.run(["systemctl", "is-active", "--quiet", unit],
                    timeout=5).returncode == 0


def _ufw_enabled() -> bool:
    """ENABLED=yes in /etc/ufw/ufw.conf. Die Datei ist fuer alle lesbar, es
    braucht also kein root — anders als 'ufw status'."""
    try:
        with open("/etc/ufw/ufw.conf", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith("ENABLED="):
                    return line.split("=", 1)[1].strip().strip('"').lower() == "yes"
    except OSError:
        pass
    return _service_active("ufw")


def detect() -> dict:
    """
    Welche Firewall ist auf diesem System zustaendig?

    Rueckgabe:
        {"kind": FIREWALLD|UFW|NFTABLES|IPTABLES|None,
         "active": bool,      # laeuft sie gerade?
         "installed": [...]}  # alles, was gefunden wurde (fuers Log)

    Reihenfolge wie bei WiVRn: laufender Dienst schlaegt vorhandenes Binary.
    """
    installed = [name for name in ("firewall-cmd", "ufw", "nft", "iptables")
                 if proc.which(name)]

    # 1. firewalld — 'firewall-cmd --state' antwortet auch ohne root.
    if proc.which("firewall-cmd"):
        state = proc.output_of(["firewall-cmd", "--state"], timeout=5).strip()
        if state == "running" or _service_active("firewalld"):
            return {"kind": FIREWALLD, "active": True, "installed": installed}

    # 2. ufw
    if proc.which("ufw"):
        return {"kind": UFW, "active": _ufw_enabled(), "installed": installed}

    # 3./4. Bekannt, aber nicht automatisch aenderbar.
    if proc.which("nft") and (_service_active("nftables") or _service_active("nftables.service")):
        return {"kind": NFTABLES, "active": True, "installed": installed}
    if proc.which("iptables") and _service_active("iptables"):
        return {"kind": IPTABLES, "active": True, "installed": installed}

    # firewalld/ufw installiert, aber gestoppt -> trotzdem sinnvoll, die Regel
    # zu hinterlegen: sie greift, sobald jemand die Firewall einschaltet.
    if proc.which("firewall-cmd"):
        return {"kind": FIREWALLD, "active": False, "installed": installed}
    if proc.which("nft"):
        return {"kind": NFTABLES, "active": False, "installed": installed}
    if proc.which("iptables"):
        return {"kind": IPTABLES, "active": False, "installed": installed}

    return {"kind": NONE, "active": False, "installed": installed}


def already_configured(kind) -> bool:
    """
    Ist die Freigabe schon eingerichtet? Nur dort ehrlich beantwortbar, wo es
    ohne root geht:

    * ufw: existiert das Anwendungsprofil? (dieselbe Pruefung wie WiVRn)
    * firewalld: NEIN — 'firewall-cmd --list-services' loest auf manchen
      Systemen eine Passwortabfrage aus. WiVRn hat seine eigene Pruefung
      genau deswegen wieder abgeschaltet; wir fragen also gar nicht erst.
    """
    if kind == UFW:
        return os.path.exists(UFW_PROFILE_PATH)
    return False


def _script(kind) -> str:
    """Das Shell-Skript, das gleich unter pkexec laeuft — ein Aufruf, eine
    Passwortabfrage."""
    if kind == UFW:
        return (
            f"printf '{UFW_PROFILE}' > {UFW_PROFILE_PATH} && "
            f"ufw allow wivrn && "
            # mDNS: ohne das findet die Brille den PC nicht.
            f"ufw allow {MDNS_PORT}/udp"
        )

    if kind == FIREWALLD:
        # --get-services listet alle bekannten Dienste; WiVRn liefert einen
        # eigenen mit. Gibt es ihn nicht (AppImage-Nutzer ohne Distro-Paket),
        # werden die Ports direkt freigegeben.
        return (
            "set -e; "
            "if firewall-cmd --permanent --get-services | tr ' ' '\\n' | grep -qx wivrn; then "
            "  firewall-cmd --permanent --add-service=wivrn; "
            "else "
            f"  firewall-cmd --permanent --add-port={PORT}/tcp; "
            f"  firewall-cmd --permanent --add-port={PORT}/udp; "
            "fi; "
            # mDNS: erst der fertige Dienst, sonst der rohe Port.
            "firewall-cmd --permanent --add-service=mdns || "
            f"firewall-cmd --permanent --add-port={MDNS_PORT}/udp; "
            "firewall-cmd --reload"
        )

    raise ValueError(f"Keine automatische Einrichtung fuer: {kind}")


def manual_commands(kind) -> list:
    """Befehle zum Selbst-Ausfuehren — fuer nftables/iptables (die fassen wir
    nicht an) und als Notnagel, wenn die Automatik scheitert."""
    if kind == NFTABLES:
        return [
            f"sudo nft add rule inet filter input tcp dport {PORT} accept",
            f"sudo nft add rule inet filter input udp dport {PORT} accept",
            f"sudo nft add rule inet filter input udp dport {MDNS_PORT} accept",
            "# to make it permanent, put the same lines in /etc/nftables.conf",
            "# (table/chain names may differ: sudo nft list ruleset)",
        ]
    if kind == IPTABLES:
        return [
            f"sudo iptables -A INPUT -p tcp --dport {PORT} -j ACCEPT",
            f"sudo iptables -A INPUT -p udp --dport {PORT} -j ACCEPT",
            f"sudo iptables -A INPUT -p udp --dport {MDNS_PORT} -j ACCEPT",
            "# to make it permanent: sudo iptables-save | sudo tee /etc/iptables/rules.v4",
        ]
    if kind == UFW:
        # WICHTIG: NICHT einfach 'ufw allow 9757'.
        #
        # Das oeffnet den Port zwar, legt aber eine namenlose Portregel an
        # statt der benannten Regel "WiVRn". Zwei Dinge haengen an dem Namen
        # bzw. an der Profildatei:
        #
        #   * WiVRns eigenes Dashboard prueft in need_setup(), ob
        #     /etc/ufw/applications.d/wivrn EXISTIERT (dashboard/firewall.cpp).
        #     Fehlt die Datei, verlangt es weiter eine Einrichtung — obwohl
        #     der Port laengst offen ist.
        #   * Unser already_configured() prueft dieselbe Datei. Ohne sie
        #     bliebe der Knopf dauerhaft auf "noch nicht eingerichtet".
        #
        # Deshalb sind die Befehle hier Zeile fuer Zeile das, was apply()
        # unter pkexec tut — nur mit sudo davor.
        #
        # 'ufw allow wivrn' kleingeschrieben ist Absicht und funktioniert:
        # ufw loest den Profilnamen in find_application_name() zuerst exakt
        # und danach ohne Ruecksicht auf Gross-/Kleinschreibung auf
        # (ufw/backend.py). WiVRn schreibt es selbst so.
        return [
            f"sudo sh -c \"printf '{UFW_PROFILE}' > {UFW_PROFILE_PATH}\"",
            "sudo ufw allow wivrn",
            f"sudo ufw allow {MDNS_PORT}/udp",
        ]
    if kind == FIREWALLD:
        return [
            "# WiVRn bringt als Distro-Paket einen fertigen Dienst mit:",
            "sudo firewall-cmd --permanent --add-service=wivrn",
            "# Gibt es den Dienst nicht, stattdessen die Ports einzeln:",
            f"sudo firewall-cmd --permanent --add-port={PORT}/tcp",
            f"sudo firewall-cmd --permanent --add-port={PORT}/udp",
            "# mDNS, damit die Brille den PC findet:",
            "sudo firewall-cmd --permanent --add-service=mdns",
            "sudo firewall-cmd --reload",
        ]
    return [
        f"# allow incoming port {PORT} (TCP and UDP) and {MDNS_PORT} (UDP)",
    ]


def apply(kind):
    """
    Richtet die Freigabe ein. Rueckgabe: (ok, fehlertext).

    Laeuft ueber genau EIN pkexec — der Nutzer sieht eine Passwortabfrage,
    nicht zwei wie bisher.
    """
    if kind not in SUPPORTED:
        return False, f"unsupported: {kind}"

    res = proc.run(["pkexec", "sh", "-c", _script(kind)], timeout=proc.LONG_TIMEOUT)
    if res.returncode == 0:
        log.info("Firewall (%s) eingerichtet: %s/tcp+udp, %s/udp",
                 kind, PORT, MDNS_PORT)
        return True, ""

    err = (res.stderr or res.stdout or "").strip()
    # 126 = polkit-Dialog abgebrochen, 127 = pkexec nicht da
    if res.returncode == 126 and not err:
        err = "pkexec: cancelled"
    log.warning("Firewall (%s) fehlgeschlagen (rc=%s): %s", kind, res.returncode, err)
    return False, err or f"exit {res.returncode}"
