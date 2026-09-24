#!/usr/bin/env python3
"""
scripts/bump_version.py — Version an allen Stellen gleichzeitig setzen
=====================================================================
Ersetzt Schritt 1 der Update-Anleitung ("Diese 3 Stellen aendern").
Von Hand war das fehleranfaellig: vergisst man die PKGBUILD, baut das AUR
den alten Tag; vergisst man core/main.py, sehen alte Clients kein Update.

    python3 scripts/bump_version.py 1.1.6      # Version setzen
    python3 scripts/bump_version.py 1.1.6 --date 2026-09-30
    python3 scripts/bump_version.py --check    # nur pruefen (nutzt die CI)
    python3 scripts/bump_version.py --check --expect 1.1.6   # vor dem Release

Gepflegt werden:
  1. core/version.py           -> VERSION = "1.1.6"        (Quelle der Wahrheit)
  2. core/main.py              -> APP_VERSION = "v1.1.6"   (Kompatibilitaets-Anker)
  3. packaging/aur/PKGBUILD    -> pkgver=1.1.6 und pkgrel=1
  4. packaging/aur/.SRCINFO    -> pkgver, pkgrel und source-Zeile
  5. README.md                -> Versions-Badge (shields.io)
  6. CHANGELOG.md / HIGHLIGHTS.md -> nur die Ueberschrift
                                  "### 🚀 v1.1.6 — JJJJ-MM-TT" ganz oben
                                  (den Text schreibst du selbst)

--check prueft alle sechs. Bei CHANGELOG/HIGHLIGHTS muss die aktuelle
Version der OBERSTE Block sein. Ein noch leerer Block ist beim normalen
--check nur ein Hinweis; mit --expect (Release) ist er ein Fehler.

Zu Punkt 2: Der Update-Checker ALTER Clients (bis v1.1.4) laedt core/main.py
von GitHub und sucht darin per regulaerem Ausdruck nach

    APP_VERSION = "v1.1.4"

Verschwindet diese Zeile, melden alle bereits installierten Versionen fuer
immer "aktuell" und finden nie wieder ein Update. Deshalb bleibt sie stehen
und wird hier mitgepflegt — sie ist kein Ueberbleibsel, sondern Absicht.

Was das Skript NICHT tut (bewusst, siehe Update-Anleitung):
  * keinen Git-Tag setzen und nichts pushen
  * keinen CHANGELOG-/HIGHLIGHTS-Text schreiben — nur die Ueberschrift
    mit Versionsnummer und Datum; der Inhalt kommt von dir
"""
import argparse
import datetime
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

VERSION_PY = ROOT / "core" / "version.py"
MAIN_PY = ROOT / "core" / "main.py"
PKGBUILD = ROOT / "packaging" / "aur" / "PKGBUILD"
SRCINFO = ROOT / "packaging" / "aur" / ".SRCINFO"
CHANGELOG = ROOT / "CHANGELOG.md"
HIGHLIGHTS = ROOT / "HIGHLIGHTS.md"
README = ROOT / "README.md"
# [![Version](https://img.shields.io/badge/Version-v1.3.7-81a1c1?...)]
BADGE_RE = re.compile(r"(badge/Version-v)([0-9A-Za-z._]+?)(-[0-9a-fA-F]{6})")
NOTES = (CHANGELOG, HIGHLIGHTS)

# "### 🚀 v1.3.6 — 2026-09-23"
HEADING_RE = re.compile(r"^###\s+(?:🚀\s+)?v(\S+)\s+—\s+(\S+)\s*$", re.M)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Erlaubt: 1.1.6 sowie 1.1.6_alpha (Unterstrich!). Ein Bindestrich ist in
# pkgver nicht zulaessig — genau der Fehler Nr. 4 aus der Update-Anleitung.
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(_[A-Za-z0-9]+)?$")


# --------------------------------------------------------------------------- #
#  Lesen
# --------------------------------------------------------------------------- #
def read_version_py():
    m = re.search(r'^VERSION\s*=\s*"([^"]+)"', VERSION_PY.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def read_main_py():
    m = re.search(r'APP_VERSION\s*=\s*"v?([^"]+)"', MAIN_PY.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def read_pkgbuild():
    text = PKGBUILD.read_text(encoding="utf-8")
    m = re.search(r"^pkgver=(.+)$", text, re.M)
    r = re.search(r"^pkgrel=(.+)$", text, re.M)
    return (m.group(1).strip() if m else None,
            r.group(1).strip() if r else None)


def read_srcinfo():
    """(pkgver, pkgrel, [source-Zeilen]) — oder None, wenn die Datei fehlt."""
    if not SRCINFO.exists():
        return None
    text = SRCINFO.read_text(encoding="utf-8")
    m = re.search(r"^\s*pkgver\s*=\s*(\S+)", text, re.M)
    r = re.search(r"^\s*pkgrel\s*=\s*(\S+)", text, re.M)
    sources = re.findall(r"^\s*source\s*=\s*(\S+)", text, re.M)
    return (m.group(1) if m else None, r.group(1) if r else None, sources)


def read_top_block(path):
    """(Version, Datum, Inhalt) des obersten Blocks — oder None."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    heads = list(HEADING_RE.finditer(text))
    if not heads:
        return None
    first = heads[0]
    end = heads[1].start() if len(heads) > 1 else len(text)
    body = text[first.end():end]
    # Nur Ueberschriften/Trenner zaehlen nicht als Inhalt
    content = [ln for ln in body.splitlines()
               if ln.strip() and not ln.strip().startswith("#") and ln.strip() != "---"]
    return first.group(1), first.group(2), content


def read_badge():
    if not README.exists():
        return None
    m = BADGE_RE.search(README.read_text(encoding="utf-8"))
    # shields.io: "_" im Text muss als "__" stehen
    return m.group(2).replace("__", "_") if m else None


def has_heading(path, version):
    if not path.exists():
        return False
    return any(m.group(1) == version
               for m in HEADING_RE.finditer(path.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- #
#  Pruefen
# --------------------------------------------------------------------------- #
def check(expect=None):
    """0 = alles stimmig, 1 = Abweichung. Gibt jede Abweichung einzeln aus."""
    v_ver = read_version_py()
    v_main = read_main_py()
    v_pkg, pkgrel = read_pkgbuild()

    print(f"core/version.py         VERSION     = {v_ver}")
    print(f"core/main.py            APP_VERSION = v{v_main}")
    print(f"packaging/aur/PKGBUILD  pkgver      = {v_pkg}   (pkgrel={pkgrel})")

    problems = []
    if not v_ver:
        problems.append("core/version.py: VERSION nicht gefunden")
    if not v_main:
        problems.append(
            "core/main.py: APP_VERSION-Anker fehlt! Ohne ihn finden alte "
            "Clients (bis v1.1.4) nie wieder ein Update.")
    if not v_pkg:
        problems.append("PKGBUILD: pkgver nicht gefunden")

    for label, value in (("core/main.py", v_main), ("PKGBUILD", v_pkg)):
        if value and v_ver and value != v_ver:
            problems.append(f"{label} steht auf {value}, core/version.py auf {v_ver}")

    if expect and v_ver and v_ver != expect:
        problems.append(f"Erwartet wurde {expect}, im Code steht {v_ver}")

    # --- .SRCINFO (muss zur PKGBUILD passen, sonst zeigt das AUR Altes) ---
    srcinfo = read_srcinfo()
    if srcinfo is None:
        print("packaging/aur/.SRCINFO  fehlt")
        problems.append("packaging/aur/.SRCINFO fehlt — im AUR-Ordner: "
                        "makepkg --printsrcinfo > .SRCINFO, dann hierher kopieren")
    else:
        s_ver, s_rel, s_sources = srcinfo
        print(f"packaging/aur/.SRCINFO  pkgver      = {s_ver}   (pkgrel={s_rel})")
        if v_pkg and s_ver != v_pkg:
            problems.append(f".SRCINFO pkgver steht auf {s_ver}, PKGBUILD auf {v_pkg}")
        if pkgrel and s_rel != pkgrel:
            problems.append(f".SRCINFO pkgrel steht auf {s_rel}, PKGBUILD auf {pkgrel}")
        if v_pkg and not any(f"v{v_pkg}.tar.gz" in src for src in s_sources):
            problems.append(f".SRCINFO source zeigt nicht auf den Tag v{v_pkg}")

    # --- README-Badge ---
    badge = read_badge()
    print(f"README.md               Badge       = v{badge}")
    if badge is None:
        problems.append("README.md: Versions-Badge nicht gefunden")
    elif v_ver and badge != v_ver:
        problems.append(f"README.md-Badge steht auf {badge}, core/version.py auf {v_ver}")

    # --- CHANGELOG.md / HIGHLIGHTS.md: aktuelle Version = oberster Block ---
    hints = []
    for path in NOTES:
        label = path.name
        top = read_top_block(path)
        if top is None:
            print(f"{label:<23} kein Versionsblock")
            problems.append(f"{label}: keine Ueberschrift '### 🚀 vX.Y.Z — JJJJ-MM-TT' gefunden")
            continue
        n_ver, n_date, content = top
        print(f"{label:<23} oben        = v{n_ver} — {n_date}")
        if v_ver and n_ver != v_ver:
            where = "steht weiter unten" if has_heading(path, v_ver) else "fehlt"
            problems.append(f"{label}: oberster Block ist v{n_ver}, v{v_ver} {where}")
            continue
        if not DATE_RE.match(n_date):
            problems.append(f"{label}: Datum '{n_date}' ist nicht JJJJ-MM-TT")
        if not content:
            msg = f"{label}: Block v{n_ver} ist noch leer"
            # Beim Release (--expect) Fehler, sonst nur Hinweis: die CI soll
            # nicht rot werden, nur weil der Text noch nicht geschrieben ist.
            (problems if expect else hints).append(msg)

    if hints:
        print("\nHinweis:")
        for h in hints:
            print(f"  - {h}")

    if problems:
        print("\nFEHLER:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("\nAlle Versionsangaben stimmen ueberein.")
    return 0


# --------------------------------------------------------------------------- #
#  Setzen
# --------------------------------------------------------------------------- #
def _sub_once(path, pattern, replacement, description):
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.M)
    if count != 1:
        print(f"  !! {description}: Muster nicht gefunden — Datei unveraendert")
        return False
    path.write_text(new_text, encoding="utf-8")
    print(f"  ok {description}")
    return True


def add_heading(path, version, date):
    """Nur die Ueberschrift "### 🚀 vX — Datum" ganz oben einfuegen (Text macht der Autor)."""
    label = path.name
    if not path.exists():
        print(f"  -- {label} fehlt — uebersprungen")
        return
    if has_heading(path, version):
        print(f"  -- {label}: Block v{version} gibt es schon — unveraendert")
        return
    text = path.read_text(encoding="utf-8")
    heading = f"### 🚀 v{version} — {date}\n\n"
    # HIGHLIGHTS trennt die Versionen mit '---', CHANGELOG nicht
    if path == HIGHLIGHTS:
        heading += "---\n\n"
    m = HEADING_RE.search(text)
    pos = m.start() if m else len(text)
    if not m and not text.endswith("\n\n"):
        heading = ("\n" if text.endswith("\n") else "\n\n") + heading
    path.write_text(text[:pos] + heading + text[pos:], encoding="utf-8")
    print(f"  ok {label}: Ueberschrift v{version} — {date}")


def bump(new_version, date=None):
    date = date or datetime.date.today().isoformat()
    if not DATE_RE.match(date):
        print(f"Ungueltiges Datum: {date} (erwartet JJJJ-MM-TT)")
        return 1
    if not VERSION_RE.match(new_version):
        print(f"Ungueltige Version: {new_version}")
        print("Erwartet: 1.2.3 oder 1.2.3_alpha (Unterstrich, kein Bindestrich!)")
        return 1

    old = read_version_py()
    print(f"Version {old} -> {new_version}\n")

    ok = True
    ok &= _sub_once(VERSION_PY, r'^VERSION\s*=\s*"[^"]+"',
                    f'VERSION = "{new_version}"', "core/version.py")
    ok &= _sub_once(MAIN_PY, r'APP_VERSION\s*=\s*"[^"]+"',
                    f'APP_VERSION = "v{new_version}"', "core/main.py (Anker)")
    ok &= _sub_once(PKGBUILD, r"^pkgver=.+$",
                    f"pkgver={new_version}", "PKGBUILD pkgver")
    # pkgrel IMMER auf 1 zuruecksetzen: neue Upstream-Version = neuer Build.
    # (Nur bei reinen Paket-Aenderungen ohne neuen Tag wird pkgrel erhoeht —
    #  das steht in der Update-Anleitung und macht man dann von Hand im
    #  AUR-Ordner, nicht hier.)
    ok &= _sub_once(PKGBUILD, r"^pkgrel=.+$", "pkgrel=1", "PKGBUILD pkgrel")

    if SRCINFO.exists():
        ok &= _sub_once(SRCINFO, r"^(\s*)pkgver\s*=.*$",
                        rf"\g<1>pkgver = {new_version}", ".SRCINFO pkgver")
        ok &= _sub_once(SRCINFO, r"^(\s*)pkgrel\s*=.*$",
                        r"\g<1>pkgrel = 1", ".SRCINFO pkgrel")
        text = SRCINFO.read_text(encoding="utf-8")
        new_text, n = re.subn(
            r"^(\s*source\s*=\s*.*?)\d+\.\d+\.\d+(?:_[A-Za-z0-9]+)?(\.tar\.gz::.*/v)"
            r"\d+\.\d+\.\d+(?:_[A-Za-z0-9]+)?(\.tar\.gz)\s*$",
            rf"\g<1>{new_version}\g<2>{new_version}\g<3>", text, flags=re.M)
        if n:
            SRCINFO.write_text(new_text, encoding="utf-8")
            print("  ok .SRCINFO source")
        else:
            print("  !! .SRCINFO source: Muster nicht gefunden — Zeile unveraendert")
            ok = False
    else:
        print("  -- .SRCINFO fehlt (packaging/aur/) — uebersprungen")

    if README.exists() and BADGE_RE.search(README.read_text(encoding="utf-8")):
        text = README.read_text(encoding="utf-8")
        README.write_text(BADGE_RE.sub(
            lambda m: m.group(1) + new_version.replace("_", "__") + m.group(3), text, count=1),
            encoding="utf-8")
        print("  ok README.md Badge")
    else:
        print("  !! README.md Badge: Muster nicht gefunden — Datei unveraendert")
        ok = False

    for path in NOTES:
        add_heading(path, new_version, date)

    if not ok:
        return 1

    print(f"""
Naechste Schritte (siehe UPDATE-ANLEITUNG-yakuda-connect.md):

  1. CHANGELOG.md + HIGHLIGHTS.md: Text unter "### 🚀 v{new_version} — {date}"
     schreiben, dann: python3 scripts/bump_version.py --check --expect {new_version}
  2. git add -A && git commit -m "v{new_version}: ..."
     git push origin main
     git tag -a v{new_version} -m "v{new_version}" && git push origin v{new_version}
  3. GitHub-Release veroeffentlichen (KEIN Pre-Release-Haken!)
  4. AUR: cd ~/aur/yakuda-connect -> pkgver/pkgrel angleichen ->
     updpkgsums -> makepkg -si -> makepkg --printsrcinfo > .SRCINFO ->
     git push origin master
""")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Version an allen Stellen setzen/pruefen")
    ap.add_argument("version", nargs="?", help="neue Version, z. B. 1.1.6")
    ap.add_argument("--check", action="store_true",
                    help="nur pruefen, nichts aendern (fuer die CI)")
    ap.add_argument("--expect", help="zusaetzlich gegen diese Version pruefen (Tag-Name)")
    ap.add_argument("--date", help="Datum fuer CHANGELOG/HIGHLIGHTS (Standard: heute, JJJJ-MM-TT)")
    args = ap.parse_args()

    if args.check or not args.version:
        return check(expect=args.expect)
    return bump(args.version, date=args.date)


if __name__ == "__main__":
    sys.exit(main())
