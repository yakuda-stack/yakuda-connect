# assets/controls — Controller-Texturen

Die Bilder in diesem Ordner zeigt der Controls-Tab (Bereich „Controls per obah“)
anstelle der eingebauten Zeichnung. Sie lassen sich frei austauschen — es muss
nur der Dateiname stimmen.

## Dateinamen

| Datei | Wofuer |
|---|---|
| `<controller_type>_left.png`  | linke Hand |
| `<controller_type>_right.png` | rechte Hand |
| `<controller_type>.png`       | Fallback fuer beide Seiten; rechts spiegelt die App das Bild selbst |

Vorhandene `controller_type`-Werte (aus obahs Profilen):

`oculus_touch`, `knuckles`, `vive_controller`, `vive_focus3_controller`,
`svl_hand_interaction_augmented`, `gamepad`, `rift`

Erlaubte Endungen: `.png`, `.svg`, `.webp`, `.jpg`, `.jpeg` — in dieser
Reihenfolge wird gesucht. Fehlt eine Datei, zeichnet die App wie bisher selbst.

## Eigene Bilder ohne Aenderung am Programm

Wer die mitgelieferten Bilder behalten, aber eigene benutzen will, legt sie
unter demselben Namen in

    ~/.config/yakuda-connect/controls/

ab. Dieser Ordner hat Vorrang vor `assets/controls` und bleibt bei Updates
unangetastet.

## Punkte auf dem Bild (`points.json`)

Wo die Punkte der Eingaben (Trigger, Stick, Tasten) auf einem Bild sitzen,
steht in `points.json` **im selben Ordner wie das Bild** — je Bild
(Dateiname ohne Endung) die Pixel jeder Eingabe:

```json
"knuckles_left": {
  "size": [1108, 1419],
  "points": { "/input/trigger": [935, 540], "/input/a": [798, 405] }
}
```

* `size` = Groesse des Bildes, fuer das die Pixel gelten. Wird das Bild im
  selben Seitenverhaeltnis vergroessert/verkleinert, rechnet die App um.
  Passt das Seitenverhaeltnis nicht, werden die Punkte ignoriert.
* Linke und rechte Bilder brauchen je einen eigenen Eintrag. Gibt es nur
  ein Bild ohne Seite (`knuckles.png`), wird es rechts samt Punkten gespiegelt.
* Die App schneidet nichts zu. Schneide das Bild knapp zu und gib linkem
  und rechtem Bild **dieselbe Groesse** (Controller jeweils zur Mitte hin) —
  dann sind beide auf dem Schirm exakt gleich gross und spiegelbildlich.
* Fehlt eine Eingabe im Eintrag, wird ihr Profilpunkt anteilig aufs Bild gelegt.

Fuer eigene Bilder in `~/.config/yakuda-connect/controls/` legst du dort
eine eigene `points.json` dazu. Die Pixel liest man am einfachsten in GIMP
o. Ae. ab (Mauszeiger ueber die Taste, Koordinaten unten links).

**Ohne Eintrag** gilt das alte Verfahren: Das Bild wird in die
Zeichenflaeche des Profils eingepasst, die Punkte kommen aus obahs Profil.
Dann sollte das Bild dasselbe Seitenverhaeltnis haben wie die Zeichnung:

| Controller | Seitenverhaeltnis der Zeichnung |
|---|---|
| `oculus_touch` | 1000 × 1280 |
| `knuckles` | 528 × 864 |
| `vive_controller` | 544 × 1120 |
| `vive_focus3_controller` | 480 × 624 |
| `svl_hand_interaction_augmented` | 560 × 656 |
| `gamepad` | 1680 × 1136 |
| `rift` | 1520 × 1008 |

Mitgelieferte Punkte gibt es fuer `oculus_touch`, `knuckles`,
`vive_controller`, `vive_focus3_controller` (je links/rechts) und `gamepad`.

Transparenter Hintergrund sieht am besten aus — der Kasten scheint dann durch.

## Standardbilder neu erzeugen

```bash
python3 scripts/render_controller_textures.py            # alle
python3 scripts/render_controller_textures.py knuckles   # nur einen
```

Das Skript rendert die eingebauten Vektor-Zeichnungen aus
`ui/controller_view.py` in diesen Ordner — praktisch als Vorlage zum
Uebermalen.
