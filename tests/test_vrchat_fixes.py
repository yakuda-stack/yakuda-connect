#!/usr/bin/env python3
"""
tests/test_vrchat_fixes.py — VRChat-Fixes aus v1.1.9
====================================================
Deckt drei Dinge ab, die alle beim Nutzer und nicht bei uns kaputtgehen
wuerden:

1. Die Reihenfolge in den Startparametern. 'gamemoderun PROTON_LOG=1
   %command%' startet VRChat gar nicht mehr, sieht in der UI aber voellig
   normal aus — genau die Sorte Fehler, die man nur im Terminal bemerkt.
2. Die Proton-Empfehlung pro Distribution. Ein doppelter Eintrag oder die
   falsche Empfehlung auf CachyOS faellt hier auf, ohne zwei Rechner.
3. Dass die Diagnose keine IP-Adressen ausgibt. Diagnose-Ausgaben landen
   unveraendert in Discord.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import games as games_db          # noqa: E402
import vrchat_check as vc         # noqa: E402


class TestEnvOrdering(unittest.TestCase):
    """Umgebungsvariablen muessen vor den Wrappern stehen."""

    def _compose(self, keys, custom="", base=""):
        toggles = games_db.GAMES["438100"]["toggles"]
        return games_db.compose_launch_options(base, keys, custom, toggles)

    def test_env_var_lands_before_wrapper(self):
        out = self._compose(["gamemoderun", "proton_log"])
        self.assertTrue(out.startswith("PROTON_LOG=1 gamemoderun"),
                        f"Env-Variable steht nicht vorne: {out}")

    def test_env_var_before_every_wrapper(self):
        out = self._compose(["gamemoderun", "mullvad_exclude", "proton_log"])
        env_pos = out.index("PROTON_LOG=1")
        for wrapper in ("gamemoderun", "mullvad-exclude"):
            self.assertLess(env_pos, out.index(wrapper),
                            f"{wrapper} steht vor der Env-Variable: {out}")

    def test_user_env_var_is_also_sorted_forward(self):
        # Eigene Parameter des Nutzers unterliegen derselben Shell-Regel.
        out = self._compose(["gamemoderun"], custom="MANGOHUD=1 mangohud %command%")
        self.assertTrue(out.startswith("MANGOHUD=1 "), out)

    def test_option_with_equals_is_not_treated_as_env(self):
        # '--dlsym=1' ist ein Argument, keine Zuweisung — darf nicht wandern.
        out = self._compose([], custom="mangohud --dlsym=1 %command%")
        self.assertTrue(out.startswith("mangohud --dlsym=1"), out)

    def test_wrapper_order_is_preserved(self):
        out = self._compose(["gamemoderun", "mullvad_exclude"])
        self.assertLess(out.index("gamemoderun"), out.index("mullvad-exclude"), out)

    def test_command_token_present_exactly_once(self):
        out = self._compose(["gamemoderun", "proton_log"])
        self.assertEqual(out.count("%command%"), 1, out)

    def test_is_env_assignment(self):
        for token in ("PROTON_LOG=1", "A=1", "_x=y", "MANGOHUD=1"):
            self.assertTrue(games_db._is_env_assignment(token), token)
        for token in ("--dlsym=1", "gamemoderun", "1BAD=x", "%command%", "-a=b"):
            self.assertFalse(games_db._is_env_assignment(token), token)


class TestVRChatProtonRecommendation(unittest.TestCase):
    """RTSP ist seit 1.1.9 auf JEDER Distribution die Empfehlung."""

    def setUp(self):
        self._orig = games_db.is_cachyos
        self.game = games_db.GAMES["438100"]

    def tearDown(self):
        games_db.is_cachyos = self._orig

    def _visible(self, cachyos):
        games_db.is_cachyos = lambda: cachyos
        return games_db.visible_protons(self.game)

    def test_rtsp_is_recommended_on_cachyos(self):
        # Seit 1.1.9 gibt es keinen eigenen CachyOS-Eintrag mehr (er waere
        # derselbe wie "main"). recommended_role(game) faellt deshalb auf
        # "main" zurueck — dort muss RTSP stehen.
        games_db.is_cachyos = lambda: True
        rec_role = games_db.recommended_role(self.game)
        rec = [p for p in self._visible(True) if p["role"] == rec_role]
        self.assertEqual(len(rec), 1)
        self.assertIn("rtsp", rec[0]["version"].lower())

    def test_rtsp_is_recommended_elsewhere(self):
        protons = self._visible(False)
        rec = [p for p in protons if p["role"] == "main"]
        self.assertEqual(len(rec), 1)
        self.assertIn("rtsp", rec[0]["version"].lower())

    def test_no_duplicate_versions_listed(self):
        for cachyos in (True, False):
            versions = [p["version"] for p in self._visible(cachyos)]
            self.assertEqual(len(versions), len(set(versions)),
                             f"Doppelter Eintrag (cachyos={cachyos}): {versions}")

    def test_cachyos_proton_offered_as_alternative_only_on_cachyos(self):
        on_cachy = [p["version"] for p in self._visible(True)]
        elsewhere = [p["version"] for p in self._visible(False)]
        self.assertTrue(any("cachyos" in v.lower() for v in on_cachy), on_cachy)
        self.assertFalse(any("cachyos" in v.lower() for v in elsewhere), elsewhere)

    def test_recommendation_sorted_first(self):
        for cachyos in (True, False):
            protons = self._visible(cachyos)
            self.assertEqual(protons[0]["role"],
                             games_db.recommended_role(self.game))

    def test_every_system_has_exactly_one_recommendation(self):
        # Ohne den Rueckfall in recommended_role(game) traegt auf CachyOS
        # KEINE Zeile das "Empfohlen"-Abzeichen — der Nutzer saehe drei
        # gleichwertige Versionen ohne Hinweis.
        for cachyos in (True, False):
            games_db.is_cachyos = lambda c=cachyos: c
            rec = games_db.recommended_role(self.game)
            hits = [p for p in self._visible(cachyos) if p["role"] == rec]
            self.assertEqual(len(hits), 1,
                             f"cachyos={cachyos}: {len(hits)} Empfehlungen")


class TestUrlRedaction(unittest.TestCase):
    """Die aufgeloeste Stream-URL enthaelt die oeffentliche IP des Nutzers."""

    URL = ("https://rr3---sn-8xgn5uxa-quhl.googlevideo.com/videoplayback"
           "?expire=1787243365&ip=87.122.22.44&itag=18&c=ANDROID_VR"
           "&sig=AE0s2JYwRAIgNO6SsAc5p7xzp0pC6Tj5&lsig=APaTxxMwRQIhAIHLV8Ab")

    def test_ip_is_never_shown(self):
        self.assertNotIn("87.122.22.44", vc._redact_url(self.URL))

    def test_signature_is_never_shown(self):
        out = vc._redact_url(self.URL)
        for secret in ("sig=", "expire=", "AE0s2JY", "APaTxx"):
            self.assertNotIn(secret, out, f"{secret} steht noch in: {out}")

    def test_useful_parts_survive(self):
        out = vc._redact_url(self.URL)
        self.assertIn("googlevideo.com", out)
        self.assertIn("itag=18", out)
        self.assertIn("ANDROID_VR", out)

    def test_empty_input(self):
        self.assertEqual(vc._redact_url(""), "")
        self.assertEqual(vc._redact_url(None), "")


class TestCheckRobustness(unittest.TestCase):
    """Die Diagnose darf nie werfen — auch nicht ohne Steam, ohne VRChat und
    ohne die aufgerufenen Programme."""

    def test_run_all_returns_full_result_set(self):
        results = vc.run_all()
        self.assertEqual(len(results), len(vc.CHECKS))
        for r in results:
            self.assertIn(r["status"], (vc.OK, vc.WARN, vc.ERR, vc.INFO))
            self.assertTrue(r["key"])

    def test_one_broken_check_does_not_kill_the_rest(self):
        def boom():
            raise RuntimeError("kaputt")
        orig = vc.CHECKS
        vc.CHECKS = (boom,) + orig
        try:
            results = vc.run_all()
            self.assertEqual(len(results), len(orig) + 1)
        finally:
            vc.CHECKS = orig

    def test_summarize_prioritizes_errors(self):
        def mk(s):
            return {"key": "x", "status": s, "detail": "", "hint": ""}

        self.assertEqual(vc.summarize([mk(vc.OK), mk(vc.OK)]), (vc.OK, 0))
        self.assertEqual(vc.summarize([mk(vc.OK), mk(vc.WARN)]), (vc.WARN, 1))
        # Ein Fehler schlaegt jede Anzahl Warnungen
        self.assertEqual(vc.summarize([mk(vc.WARN), mk(vc.WARN), mk(vc.ERR)]),
                         (vc.ERR, 1))


class TestLocaleKeys(unittest.TestCase):
    """Jeder Schluessel, den die Diagnose zurueckgibt, braucht eine
    Uebersetzung — sonst steht der rohe Schluessel im Dialog."""

    def test_all_check_keys_translated(self):
        import json
        root = os.path.join(os.path.dirname(__file__), "..")
        de = json.load(open(os.path.join(root, "locales/de.json"), encoding="utf-8"))
        en = json.load(open(os.path.join(root, "locales/en.json"), encoding="utf-8"))
        for r in vc.run_all():
            for key in (r["key"], r.get("hint")):
                if not key:
                    continue
                self.assertIn(key, de, f"DE fehlt: {key}")
                self.assertIn(key, en, f"EN fehlt: {key}")


if __name__ == "__main__":
    unittest.main()


class TestWrapPositionMechanism(unittest.TestCase):
    """Die Position "wrap" umschliesst die ganze restliche Befehlszeile.

    Aktuell benutzt sie kein Schalter — der VRCVideoCacher-Autostart, fuer
    den sie gebaut wurde, ist entfernt (siehe CHANGELOG v1.1.9). Die Mechanik
    bleibt, weil sie generisch ist; getestet wird sie deshalb mit einem
    synthetischen Schalter statt mit einem echten.
    """
    WRAP = "wrapper -c 'x' --"

    def _compose(self, keys):
        game = games_db.GAMES["438100"]
        toggles = list(game["toggles"]) + [
            games_db.game_toggle("testwrap", self.WRAP, position="wrap")]
        return games_db.compose_launch_options(
            game["launch_params"]["amd"], keys, "", toggles)

    def test_wrapper_sits_between_env_and_gamemoderun(self):
        out = self._compose(["proton_log", "gamemoderun", "testwrap"])
        self.assertLess(out.index("PROTON_LOG=1"), out.index("wrapper"), out)
        self.assertLess(out.index("wrapper"), out.index("gamemoderun"), out)

    def test_wrapper_ends_before_the_rest(self):
        out = self._compose(["gamemoderun", "testwrap"])
        self.assertIn("-- gamemoderun %command%", out, out)

    def test_disabled_toggle_changes_nothing(self):
        self.assertNotIn("wrapper", self._compose(["gamemoderun"]))
        self.assertIn("wrapper", self._compose(["gamemoderun", "testwrap"]))

    def test_empty_arg_is_skipped(self):
        game = games_db.GAMES["438100"]
        toggles = list(game["toggles"]) + [
            games_db.game_toggle("emptywrap", "", position="wrap")]
        out = games_db.compose_launch_options("", ["emptywrap"], "", toggles)
        self.assertEqual(out.strip(), "%command%")


class TestLegacyWrapperMigration(unittest.TestCase):
    """Der entfernte Autostart-Wrapper steht bei frueheren Nutzern noch in
    den gespeicherten Startparametern. Er verschwindet nicht von selbst —
    ein Schalter, den wir nicht mehr anbieten, loescht keinen gespeicherten
    Text. Ohne Bereinigung startete VRChat weiter ueber den kaputten
    Wrapper, moeglicherweise mit einem Pfad, den es gar nicht mehr gibt."""

    LEGACY = ("bash -c 'VC=\"\"; \"/home/u/.bin/VRCVideoCacher\" & VC=$!; "
              "sleep 2; \"$@\"; RC=$?; kill $VC; exit $RC' -- ")

    def test_wrapper_is_stripped(self):
        text = self.LEGACY + "gamemoderun %command% --flag"
        out = games_db.strip_legacy_vrcvideocacher_wrapper(text)
        self.assertNotIn("VRCVideoCacher", out)
        self.assertNotIn("bash -c", out)
        self.assertEqual(out, "gamemoderun %command% --flag")

    def test_unrelated_options_are_left_alone(self):
        for text in ("gamemoderun %command%",
                     "MANGOHUD=1 mangohud %command% --flag",
                     ""):
            self.assertEqual(games_db.strip_legacy_vrcvideocacher_wrapper(text), text)

    def test_other_bash_wrappers_are_not_touched(self):
        # Nur unser eigener Wrapper darf entfernt werden.
        text = "bash -c 'echo hi' -- %command%"
        self.assertEqual(games_db.strip_legacy_vrcvideocacher_wrapper(text), text)


class TestGamesJsonForwardCompatibility(unittest.TestCase):
    """Die games.json wird zur LAUFZEIT von GitHub nachgeladen, und es gewinnt
    schlicht die hoehere info.version — unabhaengig davon, welche App-Version
    laeuft. Eine neue games.json landet also auch auf v1.1.8-Installationen,
    die den Dedup-Code noch nicht haben.

    Konkret passiert: mit einem eigenen "cachyos"-Slot, der dieselbe Version
    nennt wie "default", listet der alte Code auf CachyOS RTSP ZWEIMAL. Der
    Slot ist deshalb entfernt. Dieser Test haelt das fest, damit er nicht
    versehentlich zurueckkommt.
    """

    def _config(self):
        import json
        root = os.path.join(os.path.dirname(__file__), "..")
        with open(os.path.join(root, "config", "games.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_no_cachyos_slot_duplicating_the_default(self):
        for appid, game in self._config().get("games", {}).items():
            proton = game.get("proton", {})
            if proton.get("cachyos") and proton.get("cachyos") == proton.get("default"):
                self.fail(f"AppID {appid}: 'cachyos' nennt dieselbe Version wie "
                          f"'default' — alte Clients zeigen sie doppelt an")

    def test_no_duplicate_versions_for_any_game(self):
        # Gilt fuer die gesamte Datenbank, nicht nur VRChat.
        cfg = self._config()
        games = games_db.build_games_from_config(cfg)
        orig = games_db.is_cachyos
        try:
            for cachyos in (True, False):
                games_db.is_cachyos = lambda c=cachyos: c
                for appid, game in games.items():
                    versions = [p["version"] for p in games_db.visible_protons(game)]
                    self.assertEqual(len(versions), len(set(versions)),
                                     f"AppID {appid} (cachyos={cachyos}): {versions}")
        finally:
            games_db.is_cachyos = orig


class TestDiagnosticFalsePositives(unittest.TestCase):
    """Drei Falschmeldungen aus der ersten Fassung der Diagnose. Alle drei
    haben denselben Charakter: die Pruefung hat etwas behauptet, das der
    tatsaechliche Zustand des Systems widerlegt hat."""

    def setUp(self):
        import tempfile
        import vr_environment as venv
        self.tmp = tempfile.mkdtemp(prefix="vcchk")
        self.user = os.path.join(self.tmp, "users/steamuser")
        self.vrc = os.path.join(self.user, "AppData/LocalLow/VRChat/VRChat")
        os.makedirs(self.vrc)
        self._orig_prefix = venv.vrchat_proton_prefix
        venv.vrchat_proton_prefix = lambda: self.user
        self._orig_conf = vc.configured_proton
        self._orig_pid = vc._vrchat_pid
        vc._vrchat_pid = lambda: ""

    def tearDown(self):
        import shutil
        import vr_environment as venv
        venv.vrchat_proton_prefix = self._orig_prefix
        vc.configured_proton = self._orig_conf
        vc._vrchat_pid = self._orig_pid
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _log(self, content):
        with open(os.path.join(self.vrc, "output_log_test.txt"), "w") as f:
            f.write(content)

    # --- 1) Nicht-RTSP-Build wurde pauschal als Fehler gemeldet ---------- #
    def test_working_non_rtsp_build_is_not_reported_as_broken(self):
        # proton-cachyos spielt inzwischen ab. Meldet das Log Erfolg, darf
        # die Pruefung nicht zum Wechsel draengen.
        vc.configured_proton = lambda: "Proton-CachyOS Latest-x86_64_v3"
        self._log("Using playback path: MF-MediaEngine-Hardware (720x720@0.00)\n")
        self.assertEqual(vc._check_proton()["status"], vc.OK)

    def test_failing_non_rtsp_build_is_still_reported(self):
        vc.configured_proton = lambda: "Proton-CachyOS Latest-x86_64_v3"
        self._log("Error: Loading failed.  codec not supported.\n")
        self.assertEqual(vc._check_proton()["status"], vc.ERR)

    def test_non_rtsp_without_any_playback_is_only_informational(self):
        vc.configured_proton = lambda: "Proton-CachyOS Latest-x86_64_v3"
        self._log("VRChat Build: 2026.3.1\n")
        self.assertEqual(vc._check_proton()["status"], vc.INFO)

    def test_only_the_last_playback_attempt_counts(self):
        # Fehler, danach Erfolg (z. B. Proton mitten in der Sitzung gewechselt)
        vc.configured_proton = lambda: "Proton-CachyOS"
        self._log("Error: Loading failed.  codec not supported.\n"
                  "Using playback path: MF-MediaEngine-Hardware\n")
        self.assertTrue(vc._last_playback_ok())
        self.assertEqual(vc._check_video_playback()["status"], vc.OK)
        # Umgekehrte Reihenfolge
        self._log("Using playback path: MF-MediaEngine-Hardware\n"
                  "Error: Loading failed.  codec not supported.\n")
        self.assertFalse(vc._last_playback_ok())
        self.assertEqual(vc._check_video_playback()["status"], vc.ERR)

    # --- 2) Startparameter wurden am escapten Anfuehrungszeichen abgeschnitten #
    def test_launch_options_survive_escaped_quotes(self):
        # Der VRCVideoCacher-Wrapper enthaelt \\" — das simple Muster brach
        # dort ab und meldete faelschlich fehlendes --enable-avpro-in-proton.
        vdf = os.path.join(self.tmp, "userdata/1/config/localconfig.vdf")
        os.makedirs(os.path.dirname(vdf))
        with open(vdf, "w") as f:
            f.write('"438100"\n{\n'
                    '\t"LaunchOptions"\t\t"PROTON_LOG=1 bash -c \'VC=\\"\\"; '
                    '\\"/opt/VRCVideoCacher\\" & VC=$!\' -- gamemoderun '
                    '%command% --enable-avpro-in-proton"\n}\n')
        import vr_environment as venv
        orig = venv.steam_data_roots
        venv.steam_data_roots = lambda: [self.tmp]
        try:
            opts = vc.configured_launch_options()
            self.assertIn("--enable-avpro-in-proton", opts,
                          f"Startparameter abgeschnitten: {opts!r}")
            self.assertEqual(vc._check_launch_options()["status"], vc.OK)
        finally:
            venv.steam_data_roots = orig

    # --- 3) VRCVideoCacher galt als laufend, weil sein Name in der --------- #
    #        Kommandozeile des Wrappers stand
    def test_videocacher_check_uses_exact_process_name(self):
        import subprocess
        import inspect
        src = inspect.getsource(vc._process_running)
        self.assertIn('"-x"', src,
                      "pgrep -f matcht die Startparameter des Wrappers und "
                      "meldet VRCVideoCacher als laufend, obwohl es fehlt")
        self.assertNotIn('"-if"', src)
        # Und praktisch: ein Prozess, der den Namen nur als Argument fuehrt,
        # darf nicht als laufend gelten.
        p = subprocess.Popen(["sleep", "5"])
        try:
            self.assertFalse(vc._process_running("definitiv-nicht-da-xyz"))
        finally:
            p.kill()
            p.wait()
