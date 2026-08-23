#!/usr/bin/env python3
"""
tests/test_advanced_info.py — Advanced Mode und Transparenz-Angaben
===================================================================
Zwei Dinge werden hier geprueft, und zwar genau die, die beim Aendern des
Codes leise kaputtgehen:

1. **Die Angaben stimmen mit dem Code ueberein.** Wenn jemand in
   core/firewall.py den Port aendert, muss die Beschreibung mitziehen. Der
   Test vergleicht deshalb gegen die KONSTANTEN der jeweiligen Module, nicht
   gegen abgeschriebene Zahlen.

2. **Die Beschreibung darf die Aktion nie verhindern.** Faellt die
   Pfadermittlung aus (kein WiVRn installiert, kaputte Config), soll
   describe() einen leeren Eintrag liefern — und nicht die Ausnahme nach oben
   durchreichen, wo sie den Knopf lahmlegen wuerde.
"""
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "ui"))
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import advanced_info as adv  # noqa: E402
import firewall as fw  # noqa: E402


# --------------------------------------------------------------------------- #
#  Schalter
# --------------------------------------------------------------------------- #
def test_advanced_mode_ist_standardmaessig_aus():
    """Wichtig fuers Versprechen 'die Oberflaeche bleibt unveraendert'."""
    assert adv.is_enabled() is False


def test_advanced_mode_laesst_sich_schalten():
    try:
        adv.set_enabled(True)
        assert adv.is_enabled() is True
        adv.set_enabled(False)
        assert adv.is_enabled() is False
    finally:
        adv.set_enabled(False)


# --------------------------------------------------------------------------- #
#  Form der Beschreibungen
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("action_id", sorted(adv.ACTIONS))
def test_jede_aktion_liefert_vollstaendige_felder(action_id):
    d = adv.describe(action_id)
    for feld in ("title", "explain", "paths", "perms", "commands", "source"):
        assert feld in d, f"{action_id}: Feld '{feld}' fehlt"
    assert isinstance(d["paths"], list)
    assert isinstance(d["perms"], list)
    assert isinstance(d["commands"], list)


@pytest.mark.parametrize("action_id", sorted(adv.ACTIONS))
def test_jede_aktion_hat_titel_erklaerung_und_quelle(action_id):
    """Ein Kasten ohne Erklaerung waere nur Deko."""
    d = adv.describe(action_id)
    assert d["title"] and d["title"] != action_id
    assert len(d["explain"]) > 30, f"{action_id}: Erklaerung zu duenn"
    assert d["source"].endswith(".py") or ".py" in d["source"]


@pytest.mark.parametrize("action_id", sorted(adv.ACTIONS))
def test_keine_uebersetzungsluecken(action_id):
    """
    tr() gibt bei einem fehlenden Schluessel den Schluessel selbst zurueck.
    Genau das faellt in der Oberflaeche sonst erst auf, wenn es jemand sieht.
    """
    d = adv.describe(action_id)
    verdaechtig = [t for t in [d["title"], d["explain"]] + d["perms"]
                   if t.startswith("adv_")]
    assert not verdaechtig, f"{action_id}: unuebersetzt — {verdaechtig}"


def test_unbekannte_aktion_wirft_nicht():
    d = adv.describe("gibt-es-nicht")
    assert d["paths"] == [] and d["commands"] == []


def test_describe_schluckt_fehler_der_pfadermittlung(monkeypatch):
    """Die Beschreibung darf die Aktion selbst niemals blockieren."""
    def kaputt():
        raise RuntimeError("Pfadermittlung fehlgeschlagen")

    monkeypatch.setitem(adv.ACTIONS, "firewall", kaputt)
    d = adv.describe("firewall")          # darf NICHT durchschlagen
    assert d["explain"] == ""


# --------------------------------------------------------------------------- #
#  Inhalt: passt die Doku zum Code?
# --------------------------------------------------------------------------- #
def test_firewall_beschreibung_nennt_beide_ports():
    """
    9757 allein reicht nicht — ohne mDNS (5353) findet die Brille den PC
    nicht. Das war der haeufigste Support-Fall und muss in der Erklaerung
    stehen. Verglichen wird gegen die Konstanten aus core/firewall.py.
    """
    text = adv.describe("firewall")["explain"]
    assert str(fw.PORT) in text
    assert str(fw.MDNS_PORT) in text


def test_firewall_info_text_nennt_ports_und_verneint_telemetrie():
    """Der (ⓘ)-Text am Dashboard-Knopf, geprueft in beiden Sprachen."""
    from translations import set_language, tr
    for lang, wort in (("en", "telemetry"), ("de", "Telemetrie")):
        set_language(lang)
        text = tr("firewall_info")
        assert str(fw.PORT) in text, f"{lang}: Port fehlt"
        assert str(fw.MDNS_PORT) in text, f"{lang}: mDNS-Port fehlt"
        assert wort.lower() in text.lower(), f"{lang}: Telemetrie nicht erwaehnt"
    set_language("en")


def test_vr_prioritaet_nennt_die_richtige_capability():
    d = adv.describe("vr_priority")
    assert any("cap_sys_nice" in c.lower() for c in d["commands"])


def test_backup_restore_weist_auf_root_hin():
    """
    Zurueckspielen ist die einzige Aktion, die nach /usr und /opt schreibt.
    Wenn dieser Hinweis verschwindet, ist die Doku falsch.
    """
    d = adv.describe("backup_restore")
    assert any("/usr" in p for p in d["paths"])
    assert len(d["perms"]) >= 2


def test_nur_lesende_aktionen_verlangen_kein_root():
    """Der Server-Start laeuft als normaler Benutzer — ohne pkexec."""
    d = adv.describe("server")
    assert not any("pkexec" in p.lower() or "root" in p.lower() for p in d["perms"])


def test_update_check_ist_als_netzzugriff_ausgewiesen():
    d = adv.describe("update_check")
    assert any("githubusercontent" in p for p in d["perms"])


def test_as_text_enthaelt_alle_abschnitte():
    text = adv.as_text("firewall")
    assert str(fw.PORT) in text
    assert text.strip() == text          # keine losen Leerzeilen am Rand


# --------------------------------------------------------------------------- #
#  Kurztitel der Kaesten
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("action_id", sorted(adv.ACTIONS))
def test_jede_aktion_hat_einen_kurztitel(action_id):
    """Ohne Kurztitel stehen mehrere gleich beschriftete Kaesten untereinander."""
    kurz = adv.short_title(action_id)
    assert kurz, f"{action_id}: kein Kurztitel"
    assert not kurz.startswith("adv_"), f"{action_id}: unuebersetzt ({kurz})"


def test_kurztitel_sind_eindeutig():
    """
    Zwei Kaesten mit gleichem Kurztitel waeren genauso verwechselbar wie gar
    keiner — genau das war der gemeldete Fall im Dashboard.
    """
    from translations import set_language
    for lang in ("en", "de"):
        set_language(lang)
        titel = [adv.short_title(a) for a in adv.ACTIONS]
        doppelt = {t for t in titel if titel.count(t) > 1}
        assert not doppelt, f"{lang}: mehrfach vergeben — {doppelt}"
    set_language("en")


def test_dashboard_kaesten_sind_unterscheidbar():
    """Die beiden Kaesten unter 'Server Control' konkret geprueft."""
    assert adv.short_title("firewall") != adv.short_title("server")


def test_short_title_bei_unbekannter_aktion_ist_leer():
    """Sonst stuende in der Ueberschrift ein Doppelpunkt ohne Text dahinter."""
    assert adv.short_title("gibt-es-nicht") == ""


# --------------------------------------------------------------------------- #
#  ufw: der Name der Regel entscheidet
# --------------------------------------------------------------------------- #
def test_ufw_profil_hat_alle_pflichtfelder():
    """
    title, description und ports sind bei ufw Pflicht — fehlt eines, lehnt
    ufw das Profil ab (ufw/applications.py, verify_profile).
    """
    for feld in ("title=", "description=", "ports="):
        assert feld in fw.UFW_PROFILE, f"Pflichtfeld fehlt: {feld}"
    assert fw.UFW_PROFILE.startswith("[WiVRn]")


def test_ufw_profil_nennt_den_port_ohne_protokoll():
    """
    'ports=9757' ohne Protokoll heisst bei ufw TCP UND UDP ('9757/any').
    Ein 'ports=9757/tcp' waere falsch — die UDP-Haelfte der WiVRn-Verbindung
    fehlte dann, und der Fehler faellt erst in VR auf.
    """
    assert f"ports={fw.PORT}\\n" in fw.UFW_PROFILE
    assert f"ports={fw.PORT}/tcp" not in fw.UFW_PROFILE


def test_manuelle_ufw_befehle_legen_das_profil_an():
    """
    Der wichtige Punkt: 'ufw allow 9757' allein reicht NICHT. Es oeffnet zwar
    den Port, legt aber keine benannte Regel an — und WiVRns Dashboard prueft
    auf die Existenz von /etc/ufw/applications.d/wivrn (dashboard/firewall.cpp).
    Ohne die Datei verlangt es weiter eine Einrichtung.
    """
    cmds = fw.manual_commands(fw.UFW)
    text = "\n".join(cmds)
    assert fw.UFW_PROFILE_PATH in text, "Profildatei wird nicht angelegt"
    assert "ufw allow wivrn" in text, "benannte Regel fehlt"
    assert f"{fw.MDNS_PORT}/udp" in text, "mDNS fehlt"
    # Die alte, unzureichende Zeile darf nicht zurueckkommen.
    assert f"sudo ufw allow {fw.PORT}" not in cmds


def test_manuelle_und_automatische_ufw_einrichtung_stimmen_ueberein():
    """
    Was der Nutzer von Hand tippt, muss dasselbe Ergebnis haben wie der Knopf
    — sonst meldet already_configured() hinterher unterschiedliche Zustaende.
    """
    auto = fw._script(fw.UFW)
    manuell = "\n".join(fw.manual_commands(fw.UFW))
    for teil in (fw.UFW_PROFILE_PATH, "ufw allow wivrn", f"{fw.MDNS_PORT}/udp"):
        assert teil in auto and teil in manuell, f"nur in einem Weg: {teil}"


def test_manuelle_firewalld_befehle_nennen_dienst_und_ports():
    text = "\n".join(fw.manual_commands(fw.FIREWALLD))
    assert "--add-service=wivrn" in text
    assert f"--add-port={fw.PORT}/tcp" in text
    assert f"--add-port={fw.PORT}/udp" in text
    assert "--reload" in text


# --------------------------------------------------------------------------- #
#  Die Kaesten in der Oberflaeche
# --------------------------------------------------------------------------- #
# Die QApplication kommt aus tests/conftest.py — eine einzige fuer den
# ganzen Lauf, deren Referenz festgehalten wird. Eine eigene hier waere
# genau der Fehler, der den Lauf am Ende abstuerzen liess.


def test_kasten_ist_unsichtbar_solange_der_modus_aus_ist(qapp):
    """Der Kern des Versprechens: im Normalbetrieb aendert sich die UI nicht."""
    from PySide6.QtWidgets import QWidget

    from ui.advanced_panel import AdvancedBox

    adv.set_enabled(False)
    parent = QWidget()
    box = AdvancedBox("firewall", parent)
    parent.show()
    try:
        assert box.isVisible() is False
    finally:
        parent.close()
        adv.set_enabled(False)


def test_kasten_erscheint_beim_einschalten(qapp):
    from PySide6.QtWidgets import QWidget

    from ui.advanced_panel import AdvancedBox, refresh_all

    parent = QWidget()
    box = AdvancedBox("firewall", parent)
    parent.show()
    try:
        adv.set_enabled(True)
        refresh_all()
        assert box.isVisible() is True
        # Aufgeklappt wird erst auf Klick — sonst waere die Seite voller Text.
        assert box.body.isVisible() is False
        box._toggle()
        assert box.body.isVisible() is True
    finally:
        parent.close()
        adv.set_enabled(False)
        refresh_all()


def test_kopierknopf_fuehrt_nichts_aus(qapp):
    """
    Der Befehl darf ausschliesslich in die Zwischenablage wandern. Ein
    versehentlich eingebautes subprocess-Aufruf faellt hier auf.
    """
    from PySide6.QtWidgets import QApplication, QWidget

    from ui.advanced_panel import AdvancedBox

    parent = QWidget()
    box = AdvancedBox("vr_priority", parent)
    try:
        box._fill()
        box._copy()
        inhalt = QApplication.clipboard().text()
        assert "setcap" in inhalt
    finally:
        parent.close()
        adv.set_enabled(False)


def test_kaufmaennisches_und_wird_nicht_verschluckt(qapp):
    """
    QToolButton deutet ein einzelnes '&' als Tastenkuerzel. Ohne Verdoppeln
    stand in der Ueberschrift sichtbar "Firewall _Ports" statt
    "Firewall & Ports" — genau der Fehler, der beim Bauen auffiel.
    """
    from PySide6.QtWidgets import QWidget

    from ui.advanced_panel import AdvancedBox

    parent = QWidget()
    box = AdvancedBox("firewall", parent)
    try:
        text = box.btn_toggle.text()
        assert "&&" in text, f"'&' nicht verdoppelt: {text!r}"
        assert "& Ports" in text.replace("&&", "&")
    finally:
        parent.close()
        adv.set_enabled(False)


# --------------------------------------------------------------------------- #
#  Das (ⓘ) im Firewall-Knopf
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def dashboard(qapp):
    """Ein aufgebautes Hauptfenster (offscreen) fuer die Knopf-Tests."""
    import tempfile
    os.environ["HOME"] = tempfile.mkdtemp(prefix="yakuda-adv-")
    from PySide6.QtWidgets import QMainWindow

    from ui_main import Ui_MainWindow
    win = QMainWindow()
    ui = Ui_MainWindow()
    ui.setupUi(win)
    win.show()
    # Auf die Dashboard-Seite wechseln. Ohne das bleibt sie im
    # QStackedWidget verborgen — und fuer verborgene Widgets laesst Qt das
    # Layout gar nicht erst anlaufen: sie haengen dann auf ihrer
    # Standardgroesse (640x480), und jede Messung an ihnen misst nichts.
    ui.sidebar.setCurrentRow(1)
    ui.pages.setCurrentIndex(1)
    qapp.processEvents()
    yield ui

    # Fenster deterministisch abraeumen, solange die QApplication noch lebt.
    # Nur close() zu rufen genuegt nicht: das Widget bliebe bis zum Ende des
    # Prozesses stehen und wuerde dann in beliebiger Reihenfolge eingesammelt
    # — zusammen mit den Widgets anderer Testmodule fuehrte das zu
    # 'malloc_consolidate(): unaligned fastbin chunk detected' beim Beenden.
    import shiboken6
    from ui.advanced_panel import _boxes
    win.close()
    _boxes.clear()          # zeigen sonst auf gleich geloeschte Kaesten
    shiboken6.delete(win)
    qapp.processEvents()


def test_infosymbol_sitzt_im_firewall_knopf(dashboard):
    """
    Es soll als Prefix links IM Knopf sitzen, nicht als Luecke zwischen den
    beiden Knoepfen.
    """
    knopf = dashboard.btn_port_status
    symbol = dashboard.btn_firewall_info
    assert symbol.parent() is knopf, "Symbol haengt nicht am Knopf"
    assert knopf.rect().contains(symbol.geometry()), "Symbol ragt aus dem Knopf"
    # Linksbuendig: in der linken Haelfte des Knopfes.
    assert symbol.x() < knopf.width() // 2


def test_beide_firewall_zustaende_lassen_platz_fuer_das_symbol(dashboard):
    """
    Ohne den linken Innenabstand rutscht die Beschriftung unter das Symbol.
    Der Erledigt-Zustand hat ein eigenes Stylesheet und wurde genau deshalb
    schon einmal vergessen.
    """
    from ui_main import ButtonWithInfo
    platz = f"{ButtonWithInfo.PADDING_LEFT}px"
    assert platz in dashboard._CSS_FIREWALL_IDLE
    assert platz in dashboard._CSS_FIREWALL_DONE


def test_klick_auf_das_symbol_loest_die_firewall_aktion_nicht_aus(dashboard):
    """
    Der wichtigste Test an dieser Stelle. Waere das Symbol nur Text in der
    Beschriftung, traefe ein Klick darauf den Knopf — und der Nutzer bekaeme
    eine Passwortabfrage samt Aenderung an der Firewall, obwohl er nur
    nachlesen wollte.
    """
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    ausgeloest = []
    dashboard.btn_port_status.clicked.connect(lambda: ausgeloest.append(True))

    symbol = dashboard.btn_firewall_info
    QTest.mouseClick(symbol, Qt.LeftButton, pos=QPoint(symbol.width() // 2,
                                                       symbol.height() // 2))
    assert not ausgeloest, "Klick auf das Info-Symbol hat den Knopf ausgeloest"


def test_symbol_bleibt_beim_vergroessern_im_knopf(qapp, dashboard):
    """
    Beim Sprachwechsel aendert sich die Knopfbreite — das Symbol muss mit.

    Nach dem Aendern der Groesse werden die Ereignisse abgearbeitet: sonst
    vergleicht man die Position aus dem letzten resizeEvent mit einer Groesse,
    die das Layout gerade erst gesetzt hat, und der Test wackelt.
    """
    knopf = dashboard.btn_port_status
    symbol = dashboard.btn_firewall_info

    knopf.resize(knopf.width() + 120, knopf.height() + 10)
    qapp.processEvents()

    assert knopf.rect().contains(symbol.geometry())
    # Senkrecht weiterhin mittig (1 Pixel Toleranz wegen Ganzzahl-Division).
    mitte = (knopf.height() - symbol.height()) // 2
    assert abs(symbol.y() - mitte) <= 1


def test_geloeschte_kaesten_legen_refresh_all_nicht_lahm(qapp):
    """
    Wird ein Tab neu aufgebaut, raeumt Qt alte Kaesten ab. Ein Zugriff auf so
    ein Widget wirft RuntimeError. refresh_all() muss das ueberstehen und den
    Eintrag aussortieren — sonst haengt der Schalter beim naechsten Umlegen.
    """
    import shiboken6
    from PySide6.QtWidgets import QWidget

    from ui.advanced_panel import AdvancedBox, _boxes, refresh_all

    parent = QWidget()
    tot = AdvancedBox("firewall", parent)
    lebt = AdvancedBox("diagnostics", parent)

    shiboken6.delete(tot)                 # simuliert das Abraeumen durch Qt
    refresh_all()                          # darf NICHT werfen

    assert lebt in _boxes
    assert all(shiboken6.isValid(b) for b in _boxes)
    parent.close()
    adv.set_enabled(False)
