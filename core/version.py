#!/usr/bin/env python3
"""
core/version.py — Die EINE Quelle der Wahrheit fuer die Versionsnummer
======================================================================
Hier — und nur hier — wird die Version von Hand gepflegt. Alles andere
(main.py, PKGBUILD, AppImage-Dateiname, Update-Check) leitet sich davon ab.

Zum Hochsetzen NICHT diese Datei allein editieren, sondern:

    python3 scripts/bump_version.py 1.1.5

Das Skript setzt die Nummer hier, im Kompatibilitaets-Anker in core/main.py
und in packaging/aur/PKGBUILD gleichzeitig — genau die drei Stellen aus der
Update-Anleitung. Der Smoke-Test prueft danach, dass alle uebereinstimmen.

----------------------------------------------------------------------
Warum in core/main.py trotzdem noch eine Versionszeile steht
----------------------------------------------------------------------
Der Update-Checker ALTER Clients (bis v1.1.4) laedt core/main.py von GitHub
und sucht darin per regulaerem Ausdruck nach:

    APP_VERSION = "v1.1.4"

Verschwindet diese Zeile, sehen alle bereits installierten Versionen nie
wieder ein Update — sie melden dauerhaft "aktuell". Deshalb bleibt in
core/main.py ein Anker mit genau diesem Muster stehen. Neue Clients lesen
bevorzugt diese Datei hier.
"""

# --------------------------------------------------------------------- #
#  HIER wird die Version gepflegt (ohne fuehrendes 'v').
# --------------------------------------------------------------------- #
VERSION = "1.1.7"

# Mit 'v' davor — so, wie die App sie anzeigt und wie die Git-Tags heissen.
APP_VERSION = "v" + VERSION


def version_tuple(text: str = None):
    """
    Wandelt "v1.1.5" / "1.1.5_alpha" in (1, 1, 5) fuer numerische Vergleiche.
    Gibt bei nicht parsbaren Eingaben None zurueck, damit der Aufrufer auf
    einen reinen Textvergleich zurueckfallen kann.
    """
    import re
    raw = VERSION if text is None else str(text)
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", raw)
    if not m:
        return None
    return tuple(int(g) for g in m.groups())
