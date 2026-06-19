import pytest

from token_tracker import cli, config
from token_tracker.ui import theme, themes


def test_all_themes_have_complete_base_and_heat():
    # 每个主题必须齐 9 基色 + is_light bool + 5 档热力。
    for name in themes.THEME_NAMES:
        spec = themes.get_theme(name)
        assert set(spec["base"]) == set(themes.BASE_SLOTS), name
        assert isinstance(spec["is_light"], bool), name
        heat = themes.heat_colors(name)
        assert len(heat) == 5, name


def test_heat_interpolation_endpoints():
    # 插值主题（无显式 heat）：首档=cell，末档=green。
    spec = themes.get_theme("frappe")
    heat = themes.heat_colors("frappe")
    assert heat[0] == spec["cell"]
    assert heat[-1] == spec["base"]["green"]


def test_mocha_heat_unchanged():
    # mocha 热力显式硬编码，须与历史像素一致（daily 热力图不回归）。
    assert themes.heat_colors("mocha") == ["#313244", "#475951", "#628168", "#7da87f", "#a6e3a1"]


def test_derive_slots_maps_semantics():
    slots = themes.derive_slots(themes.get_theme("mocha")["base"])
    assert slots["token"] == "#74c7ec"  # sapphire
    assert slots["cost"] == "#f9e2af"  # yellow
    assert slots["accent"] == "bold #a6e3a1"  # bold green
    assert slots["dim"] == "#6c7086"  # overlay0


def test_statusline_ansi_truecolor():
    ansi = themes.theme_to_statusline_ansi("mocha")
    assert set(ansi) == set(themes._STATUSLINE_SLOTS) | {"reset"}
    assert ansi["reset"] == "\033[0m"
    # truecolor 主题：着色 key 都是 38;2 序列。
    assert all("38;2" in v for k, v in ansi.items() if k != "reset")
    assert ansi["tokens"] == "\033[38;2;116;199;236m"  # sapphire #74c7ec


def test_statusline_ansi_default_is_3bit():
    ansi = themes.theme_to_statusline_ansi("default")
    assert ansi["bar_ok"] == "\033[32m"  # green
    assert ansi["bar_danger"] == "\033[31m"  # red
    assert "38;2" not in "".join(ansi.values())


def test_get_theme_unknown_falls_back_to_mocha():
    assert themes.get_theme("nope") is themes.THEMES["mocha"]


def test_resolve_env_alias_and_name(monkeypatch):
    monkeypatch.setattr(config, "load_theme_config", lambda: {})
    monkeypatch.delenv("COLORFGBG", raising=False)
    monkeypatch.setenv("TT_THEME", "light")
    assert config.resolve_theme() == "latte"
    monkeypatch.setenv("TT_THEME", "dark")
    assert config.resolve_theme() == "mocha"
    monkeypatch.setenv("TT_THEME", "nord")
    assert config.resolve_theme() == "nord"


def test_resolve_auto_uses_colorfgbg(monkeypatch):
    monkeypatch.setattr(config, "load_theme_config", lambda: {})
    monkeypatch.setenv("TT_THEME", "auto")
    monkeypatch.setenv("COLORFGBG", "0;15")
    assert config.resolve_theme() == "latte"
    monkeypatch.setenv("COLORFGBG", "15;0")
    assert config.resolve_theme() == "mocha"


def test_resolve_priority_env_over_config(monkeypatch):
    # env 显式主题应盖过配置文件。
    monkeypatch.setattr(config, "load_theme_config", lambda: {"theme": "dracula"})
    monkeypatch.delenv("COLORFGBG", raising=False)
    monkeypatch.setenv("TT_THEME", "nord")
    assert config.resolve_theme() == "nord"
    # env 未知值时落到配置文件。
    monkeypatch.setenv("TT_THEME", "bogus")
    assert config.resolve_theme() == "dracula"


def test_resolve_config_when_env_absent(monkeypatch):
    monkeypatch.setattr(config, "load_theme_config", lambda: {"theme": "frappe"})
    monkeypatch.delenv("TT_THEME", raising=False)
    monkeypatch.delenv("COLORFGBG", raising=False)
    assert config.resolve_theme() == "frappe"


def test_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "cfg" / "theme.json"))
    config.save_theme("nord")
    assert config.load_theme_config()["theme"] == "nord"


def test_s_proxy_follows_active_theme(monkeypatch):
    monkeypatch.setattr(theme, "_ACTIVE_NAME", None)
    theme.set_active_theme("mocha")
    assert theme._S.token == "#74c7ec"  # mocha sapphire
    assert theme._S.accent == "bold #a6e3a1"  # bold green
    theme.set_active_theme("dracula")
    assert theme._S.token == "#8be9fd"  # dracula cyan→sapphire


def test_s_proxy_unknown_attr_raises(monkeypatch):
    monkeypatch.setattr(theme, "_ACTIVE_NAME", "mocha")
    try:
        _ = theme._S.nope
        raise AssertionError("expected AttributeError")
    except AttributeError:
        pass


def test_preview_theme_restores(monkeypatch):
    monkeypatch.setattr(theme, "_ACTIVE_NAME", "mocha")
    before = theme._S.token
    with theme.preview_theme("nord"):
        assert theme._S.token == "#88c0d0"  # nord frost cyan→sapphire
        assert theme.get_active_theme_name() == "nord"
    assert theme._S.token == before
    assert theme.get_active_theme_name() == "mocha"


def test_heat_greens_follows_theme(monkeypatch):
    monkeypatch.setattr(theme, "_ACTIVE_NAME", "mocha")
    assert theme.heat_greens() == ["#313244", "#475951", "#628168", "#7da87f", "#a6e3a1"]
    theme.set_active_theme("default")
    assert theme.heat_greens()[0] == "bright_black"


def test_theme_set_writes_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "theme.json"))
    monkeypatch.setattr(cli, "is_setup", lambda: False)  # 不触发 update_hook
    monkeypatch.delenv("TT_THEME", raising=False)
    monkeypatch.setattr(theme, "_ACTIVE_NAME", None)
    cli.cmd_theme(["set", "nord"])
    assert config.load_theme_config()["theme"] == "nord"
    assert theme.get_active_theme_name() == "nord"


def test_theme_set_unknown_exits(monkeypatch):
    monkeypatch.setattr(cli, "is_setup", lambda: False)
    with pytest.raises(SystemExit):
        cli.cmd_theme(["set", "bogus"])


def test_cmd_theme_show_and_list_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "theme.json"))
    monkeypatch.delenv("TT_THEME", raising=False)
    monkeypatch.delenv("COLORFGBG", raising=False)
    cli.cmd_theme([])  # show
    cli.cmd_theme(["list"])  # list 列出所有主题名
    out = capsys.readouterr().out
    assert "mocha" in out and "dracula" in out


def test_cmd_theme_shorthand_set(tmp_path, monkeypatch):
    # `tt theme frappe` 简写 = set frappe
    monkeypatch.setattr(config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "theme.json"))
    monkeypatch.setattr(cli, "is_setup", lambda: False)
    monkeypatch.delenv("TT_THEME", raising=False)
    monkeypatch.setattr(theme, "_ACTIVE_NAME", None)
    cli.cmd_theme(["frappe"])
    assert config.load_theme_config()["theme"] == "frappe"
