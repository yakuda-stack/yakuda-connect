import shutil

import appimage_installer as appimg


def _arch(monkeypatch, which_map, config):
    monkeypatch.setattr(appimg, "is_arch_based", lambda: True)
    monkeypatch.setattr(appimg, "is_steamos", lambda: False)
    monkeypatch.setattr(appimg, "_read_config", lambda: dict(config))
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: which_map.get(name))


def test_valid_helper_name():
    assert appimg.valid_helper_name("pikaur")
    assert appimg.valid_helper_name("aura-bin")
    assert not appimg.valid_helper_name("")
    assert not appimg.valid_helper_name("a b")
    assert not appimg.valid_helper_name("x;rm")
    assert not appimg.valid_helper_name("/usr/bin/yay")


def test_arch_without_helper_is_missing(monkeypatch):
    _arch(monkeypatch, {}, {})
    assert appimg.available_update_methods() == []
    assert appimg.arch_helper_missing()


def test_custom_helper_is_used(monkeypatch):
    _arch(monkeypatch, {"pikaur": "/usr/bin/pikaur"}, {appimg.AUR_HELPER_CONFIG_KEY: "pikaur"})
    assert appimg.available_update_methods() == ["pikaur"]
    assert appimg.is_aur_helper("pikaur")
    assert not appimg.arch_helper_missing()


def test_flatpak_choice(monkeypatch):
    _arch(monkeypatch, {"flatpak": "/usr/bin/flatpak"}, {appimg.ARCH_CHOICE_CONFIG_KEY: "flatpak"})
    assert appimg.available_update_methods() == ["flatpak"]
    assert not appimg.arch_helper_missing()


def test_invalid_custom_name_is_ignored(monkeypatch):
    _arch(monkeypatch, {}, {appimg.AUR_HELPER_CONFIG_KEY: "x;rm -rf"})
    assert appimg.custom_aur_helper_name() == ""


def test_shelly_counts_as_method(monkeypatch):
    _arch(monkeypatch, {"shelly": "/usr/bin/shelly"}, {})
    assert appimg.available_update_methods() == ["shelly"]
    assert not appimg.arch_helper_missing()
    assert appimg.default_update_method(["shelly"]) == "shelly"
    assert not appimg.is_aur_helper("shelly")


def test_reserved_names_are_rejected():
    for name in ("shelly", "yay", "paru", "pacman", "flatpak", "dnf", "sudo"):
        assert not appimg.valid_helper_name(name)


def test_custom_shelly_does_not_duplicate(monkeypatch):
    _arch(monkeypatch, {"shelly": "/usr/bin/shelly"}, {appimg.AUR_HELPER_CONFIG_KEY: "shelly"})
    assert appimg.available_update_methods() == ["shelly"]


def test_default_prefers_paru_then_yay_then_shelly(monkeypatch):
    monkeypatch.setattr(appimg, "is_cachyos", lambda: True)
    assert appimg.default_update_method(["yay", "paru", "shelly"]) == "paru"
    assert appimg.default_update_method(["yay", "shelly"]) == "yay"
    assert appimg.default_update_method(["shelly"]) == "shelly"


def test_custom_helper_beats_shelly(monkeypatch):
    monkeypatch.setattr(appimg, "_read_config", lambda: {appimg.AUR_HELPER_CONFIG_KEY: "pikaur"})
    assert appimg.default_update_method(["pikaur", "shelly"]) == "pikaur"


def test_paru_is_listed_before_yay(monkeypatch):
    _arch(monkeypatch, {"yay": "/usr/bin/yay", "paru": "/usr/bin/paru",
                        "shelly": "/usr/bin/shelly"}, {})
    assert appimg.available_update_methods() == ["paru", "yay", "shelly"]


def test_hint_only_for_shelly_without_helper(monkeypatch):
    _arch(monkeypatch, {"shelly": "/usr/bin/shelly"}, {})
    assert appimg.should_offer_helper_for_update("shelly")
    assert not appimg.should_offer_helper_for_update("paru")


def test_no_hint_when_a_helper_is_installed(monkeypatch):
    _arch(monkeypatch, {"shelly": "/usr/bin/shelly", "yay": "/usr/bin/yay"}, {})
    assert not appimg.should_offer_helper_for_update("shelly")


def test_hint_can_be_hidden(monkeypatch):
    _arch(monkeypatch, {"shelly": "/usr/bin/shelly"}, {appimg.SHELLY_HINT_HIDDEN_KEY: True})
    assert not appimg.should_offer_helper_for_update("shelly")


def test_no_hint_on_steamos(monkeypatch):
    _arch(monkeypatch, {"shelly": "/usr/bin/shelly"}, {})
    monkeypatch.setattr(appimg, "is_steamos", lambda: True)
    assert not appimg.should_offer_helper_for_update("shelly")


def test_helper_install_commands():
    import pytest
    repo, aur = appimg.helper_install_commands("paru")
    assert repo == "sudo pacman -S --needed paru"
    assert "git clone https://aur.archlinux.org/paru.git" in aur
    assert aur.endswith("makepkg -si")
    with pytest.raises(ValueError):
        appimg.helper_install_commands("x;rm")
    assert appimg.helper_url("paru") == appimg.PARU_URL
    assert appimg.helper_url("yay") == appimg.YAY_URL


def test_missing_installable_helpers(monkeypatch):
    _arch(monkeypatch, {"yay": "/usr/bin/yay"}, {})
    assert appimg.missing_installable_helpers() == ["paru"]


def test_helper_install_bash_tries_pacman_first():
    import install_worker
    script = install_worker.helper_install_bash("yay")
    assert script.index("pacman -Si yay") < script.index("sudo pacman -S --needed yay")
    assert script.index("sudo pacman -S --needed yay") < script.index("aur.archlinux.org/yay.git")
    assert "makepkg -si" in script
    import pytest
    with pytest.raises(ValueError):
        install_worker.helper_install_bash("x; rm -rf /")


def test_tools_tab_offers_shelly(monkeypatch):
    _arch(monkeypatch, {"shelly": "/usr/bin/shelly"}, {})
    tool = {"pkg": "some-tool", "methods": ["aur"]}
    monkeypatch.setattr(appimg, "supported_methods", lambda t: ["aur"])
    assert appimg.detect_install_methods(tool) == ["shelly"]


def test_tools_default_prefers_shelly_on_cachyos(monkeypatch):
    monkeypatch.setattr(appimg, "is_cachyos", lambda: True)
    assert appimg.default_method(["yay", "shelly"]) == "shelly"
    assert appimg.default_method(["appimage", "shelly"]) == "appimage"
    monkeypatch.setattr(appimg, "is_cachyos", lambda: False)
    assert appimg.default_method(["yay", "shelly"]) == "yay"


def test_remove_with_shelly_uses_pacman():
    import install_worker
    w = install_worker.RemoveWorker(["some-tool"], helper="shelly")
    assert w._remove_cmd("some-tool") == "sudo pacman -Rns some-tool"
    w = install_worker.RemoveWorker(["some-tool"], helper="yay")
    assert w._remove_cmd("some-tool") == "yay -Rns some-tool"


SHELLY_TABLE = """┌─────────────────────────────┬─────────────────┬───────────────┬──────────┐
│ Name                        │ Installed       │ Available     │ Desc     │
├─────────────────────────────┼─────────────────┼───────────────┼──────────┤
│ lib32-gstreamer             │ 1.28.5-1        │ 1.28.7-1      │ core     │
│ opencomposite-git           │ r1232.cff07db-1 │ latest-commit │ OpenVR   │
└─────────────────────────────┴─────────────────┴───────────────┴──────────┘
AUR Total: 2 packages need updates
"""


def test_parse_shelly_table():
    names, ok = appimg.parse_shelly_updates(SHELLY_TABLE)
    assert ok
    assert names == {"lib32-gstreamer", "opencomposite-git"}


def test_parse_shelly_json_and_garbage():
    assert appimg.parse_shelly_updates('[{"name": "opencomposite-git"}]') == ({"opencomposite-git"}, True)
    assert appimg.parse_shelly_updates('{"packages": [{"Name": "x"}]}') == ({"x"}, True)
    assert appimg.parse_shelly_updates("error: unknown option") == (set(), False)
    assert appimg.parse_shelly_updates("") == (set(), False)


SHELLY_JSON = (
    '[{"Name":"lib32-gst-plugins-base-libs","Version":"1.28.5-1","NewVersion":"1.28.7-1",'
    '"DownloadSize":0,"Url":"https://gstreamer.freedesktop.org/","PackageBase":"lib32-gstreamer",'
    '"Description":"Multimedia graph framework (32-bit) - base"},'
    '{"Name":"opencomposite-git","Version":"r1232.cff07db-1","NewVersion":"latest-commit",'
    '"DownloadSize":0,"Url":"https://gitlab.com/znixian/OpenOVR","PackageBase":"opencomposite-git",'
    '"Description":"Reimplementation of OpenVR, translating calls to OpenXR."}]\n'
)


def test_parse_real_shelly_json():
    names, ok = appimg.parse_shelly_updates(SHELLY_JSON)
    assert ok
    assert names == {"lib32-gst-plugins-base-libs", "opencomposite-git"}


def test_parse_shelly_json_empty_list():
    assert appimg.parse_shelly_updates("[]") == (set(), True)
