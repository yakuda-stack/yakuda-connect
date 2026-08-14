# Eine Sprache beitragen / Contributing a translation

**Deutsch unten.**

---

## English

All interface texts live in `locales/`. You do **not** need to know Python.

1. Copy `locales/en.json` to `locales/<code>.json`
   (`fr.json` for French, `es.json` for Spanish, `nl.json` for Dutch, …)
2. Translate **only the values on the right**. Keep the keys on the left exactly as they are.
3. Keep placeholders like `{name}`, `{path}`, `{version}` — they are replaced at runtime.
4. Open a pull request.

```json
{
  "nav_dashboard": "Dashboard",
  "diag_copied": "Log copied to clipboard ({lines} lines)."
}
```
becomes, for example in French:
```json
{
  "nav_dashboard": "Tableau de bord",
  "diag_copied": "Journal copié dans le presse-papiers ({lines} lignes)."
}
```

**Check your file before sending it:**
```bash
python3 -m pytest tests/ -q
```
This verifies that no key is missing and that every placeholder matches the
English reference. A missing placeholder would crash the app at that exact
message, so this check matters.

Notes:
* A missing key is not fatal — the English text is used instead.
* Emoji in the texts (📄, ⬆) are part of the interface; keep them.
* Some keys are deliberately English even in German (`nav_settings`), because
  the terms are established. Translate what makes sense in your language.

---

## Deutsch

Alle Texte der Oberfläche liegen in `locales/`. Python-Kenntnisse sind **nicht**
nötig.

1. `locales/en.json` nach `locales/<code>.json` kopieren
   (`fr.json` für Französisch, `es.json` für Spanisch, `nl.json` für Niederländisch, …)
2. **Nur die Werte rechts** übersetzen. Die Schlüssel links bleiben unverändert.
3. Platzhalter wie `{name}`, `{path}`, `{version}` müssen erhalten bleiben —
   sie werden zur Laufzeit ersetzt.
4. Pull Request aufmachen.

**Vor dem Absenden prüfen:**
```bash
python3 -m pytest tests/ -q
```
Das prüft, ob Schlüssel fehlen und ob alle Platzhalter zur englischen Referenz
passen. Ein vergessener Platzhalter würde die App genau bei dieser Meldung
abstürzen lassen — die Prüfung ist also nicht bloß Formsache.

Hinweise:
* Ein fehlender Schlüssel ist kein Beinbruch — dann erscheint der englische Text.
* Emoji in den Texten (📄, ⬆) gehören zur Oberfläche und sollten bleiben.
* Manche Schlüssel sind auch auf Deutsch bewusst englisch (`nav_settings`), weil
  die Begriffe eingebürgert sind. Übersetze, was in deiner Sprache sinnvoll ist.
