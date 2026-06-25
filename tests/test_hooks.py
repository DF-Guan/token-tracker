import json
import os
import re
import shutil
import subprocess
import sys

import pytest

from token_tracker import hooks


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _run_statusline(script_path, project_dir):
    data = {
        "workspace": {"project_dir": str(project_dir)},
        "context_window": {"used_percentage": 30, "context_window_size": 200000,
                           "total_input_tokens": 100, "total_output_tokens": 50},
    }
    r = subprocess.run([sys.executable, str(script_path)], input=json.dumps(data),
                       text=True, capture_output=True)
    return r.stdout.splitlines()[0] if r.stdout.strip() else ""


def test_rendered_hook_script_has_single_version_source():
    # HOOK_VERSION 是唯一版本来源：渲染后脚本里的 __version__ 必须等于它，
    # 且占位符不能残留（否则 needs_update 永远判不相等，每次都重写文件）。
    rendered = hooks._render_hook_script()
    assert f'__version__ = "{hooks.HOOK_VERSION}"' in rendered
    assert "__HOOK_VERSION__" not in rendered


def test_installed_version_parser_roundtrips(tmp_path, monkeypatch):
    # _installed_hook_version 读回的版本应与写入的 HOOK_VERSION 一致，
    # 保证 needs_update 不会因解析偏差而误判。
    script_path = tmp_path / "tt-statusline.py"
    script_path.write_text(hooks._render_hook_script(), encoding="utf-8")
    monkeypatch.setattr(hooks, "HOOK_SCRIPT_PATH", str(script_path))
    assert hooks._installed_hook_version() == hooks.HOOK_VERSION


def test_statusline_script_bakes_theme_colors(monkeypatch):
    # statusline 脚本在烘焙时注入当前主题 truecolor + default 3-bit 兜底；占位符不残留、语法正确。
    monkeypatch.setenv("TT_THEME", "dracula")
    monkeypatch.delenv("COLORFGBG", raising=False)
    rendered = hooks._render_hook_script()
    assert "__STATUSLINE_TRUECOLOR__" not in rendered
    assert "__STATUSLINE_COLOR256__" not in rendered
    assert "38;2;80;250;123" in rendered  # dracula green（truecolor）注入
    assert "38;5;" in rendered  # 256 色兜底注入
    compile(rendered, "<statusline>", "exec")  # 注入后语法正确


def test_codex_statusline_render_injects_version():
    # Codex 伪 statusline 脚本：版本号 + 主题配色注入、占位符不残留、语法正确（无 __TT_PYTHON__ 需求）。
    rendered = hooks._render_codex_statusline_hook()
    assert f'__version__ = "{hooks.STATUSLINE_HOOK_VERSION}"' in rendered
    assert "__STATUSLINE_HOOK_VERSION__" not in rendered
    assert "__STATUSLINE_TRUECOLOR__" not in rendered  # 配色占位符已替换
    assert "'reset'" in rendered and "38;2" in rendered  # 注入了 truecolor 配色 dict（跟随主题）
    compile(rendered, "<codex-statusline>", "exec")


def test_codex_statusline_install_uninstall_roundtrip(tmp_path, monkeypatch):
    # 末尾追加 tt Stop 段、保留用户已有 Stop hook；幂等；卸载删净 tt 段、留用户项。
    monkeypatch.setattr(hooks, "CODEX_STATUSLINE_HOOK_PATH", str(tmp_path / "tt-statusline.py"))
    base = (
        '[tui]\nstatus_line = ["project"]\n\n'
        '[[hooks.Stop]]\n\n'
        '[[hooks.Stop.hooks]]\ntype = "command"\ncommand = "mine"\ntimeout = 5\n'
    )
    installed = hooks._install_codex_statusline(base, "python3")
    assert "tt-statusline" in installed and 'command = "mine"' in installed
    assert hooks._install_codex_statusline(installed, "python3") == installed  # 幂等
    removed = hooks._uninstall_codex_statusline(installed)
    assert "tt-statusline" not in removed and 'command = "mine"' in removed


def test_codex_statusline_windows_path_toml_parses(tmp_path, monkeypatch):
    # 回归：Windows 路径含 \U \A \P 等被 TOML basic string 当 unicode 转义起始符（issue 用户反馈）
    # —— 写入的 command 必须用 literal string（单引号）包裹，写出来后能被 tomllib 原样解析回来。
    import tomllib
    monkeypatch.setattr(hooks, "CODEX_STATUSLINE_HOOK_PATH",
                        r"C:\Users\test\.config\token-tracker\codex-statusline.py")
    monkeypatch.setattr(hooks, "_write_codex_statusline_script", lambda: None)  # 别在 macOS 上真写 Windows 路径
    py = r"C:\Users\test\AppData\Local\Programs\Python\Python313\python.exe"
    content = hooks._install_codex_statusline("", py)
    parsed = tomllib.loads(content)  # 旧 bug：basic string 下 \U 等触发 TOML 解析错误
    assert parsed["hooks"]["Stop"][0]["hooks"][0]["command"] == \
        rf"{py} C:\Users\test\.config\token-tracker\codex-statusline.py"


def test_codex_statusline_version_roundtrip(tmp_path, monkeypatch):
    # _installed_codex_statusline_version 读回的版本应与写入的 STATUSLINE_HOOK_VERSION 一致，
    # 保证 needs_update 不会因解析偏差而误判。
    script_path = tmp_path / "tt-statusline.py"
    monkeypatch.setattr(hooks, "CODEX_STATUSLINE_HOOK_PATH", str(script_path))
    assert hooks._installed_codex_statusline_version() is None  # 未装
    hooks._write_codex_statusline_script()
    assert hooks._installed_codex_statusline_version() == hooks.STATUSLINE_HOOK_VERSION


def test_setup_components_defaults_all_on():
    # 不传 components 时 setup() 应等价于全装；SetupComponents 默认值也是全开。
    c = hooks.SetupComponents()
    assert c.codex_faux_statusline is True
    assert hooks.SetupComponents.all_on() == c


def test_setup_components_off_skips_install(tmp_path, monkeypatch):
    # codex_faux_statusline=False → Codex 伪 statusline 不装。
    # 隔离 HOME，避免污染主人真实 ~/.claude / ~/.codex
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".codex").mkdir(parents=True)
    settings_path = home / ".claude" / "settings.json"
    settings_path.write_text("{}", encoding="utf-8")
    codex_config = home / ".codex" / "config.toml"
    codex_config.write_text("[tui]\nstatus_line = []\n", encoding="utf-8")
    monkeypatch.setattr(hooks, "CLAUDE_SETTINGS", str(settings_path))
    monkeypatch.setattr(hooks, "HOOK_SCRIPT_PATH", str(home / ".claude" / "tt-statusline.py"))
    monkeypatch.setattr(hooks, "CODEX_DIR", str(home / ".codex"))
    monkeypatch.setattr(hooks, "CODEX_CONFIG", str(codex_config))
    monkeypatch.setattr(hooks, "CODEX_STATUSLINE_HOOK_PATH", str(home / ".codex" / "tt-statusline.py"))

    hooks.setup(components=hooks.SetupComponents(codex_faux_statusline=False))

    # CC statusline 仍装
    assert json.loads(settings_path.read_text())["statusLine"]["command"].endswith("tt-statusline.py")
    # Codex 端：不再动 [tui].status_line（保持用户原配置）；Stop hook（tt-statusline）也不在 config 里
    codex_content = codex_config.read_text()
    assert "status_line = []" in codex_content  # 用户原 status_line 没被动
    assert "tt-statusline" not in codex_content   # Codex 伪 statusline hook 段未追加


def test_cli_setup_wizard_or_auto(monkeypatch):
    # `tt setup` 经 _run_setup_flow：装了 agent 时，双 tty 非会话内 → run_wizard；否则 → _auto_setup。
    from token_tracker import cli, wizard
    calls: dict = {}
    from types import SimpleNamespace
    monkeypatch.setattr(cli, "detect_agents",
                        lambda: [SimpleNamespace(name="Claude Code", id="claude-code")])  # 有 agent
    monkeypatch.setattr(wizard, "run_wizard", lambda: calls.__setitem__("wizard", True))
    monkeypatch.setattr(cli, "_auto_setup", lambda: calls.__setitem__("auto", True))
    monkeypatch.setattr(cli, "is_setup", lambda: True)
    monkeypatch.setattr(cli, "needs_update", lambda: False)
    monkeypatch.setattr("sys.argv", ["tt", "setup"])

    monkeypatch.setattr(cli, "_should_run_wizard", lambda: True)
    cli.main()
    assert calls == {"wizard": True}

    calls.clear()
    monkeypatch.setattr(cli, "_should_run_wizard", lambda: False)
    cli.main()
    assert calls == {"auto": True}


def test_cli_setup_flow_no_agent(monkeypatch):
    # _run_setup_flow 是 agent 守卫单一入口：零 agent → 提示 no_agent_install，不进 wizard / auto。
    from token_tracker import cli, wizard
    calls: dict = {}
    monkeypatch.setattr(cli, "detect_agents", lambda: [])  # 没装 agent
    monkeypatch.setattr(wizard, "run_wizard", lambda: calls.__setitem__("wizard", True))
    monkeypatch.setattr(cli, "_auto_setup", lambda: calls.__setitem__("auto", True))
    monkeypatch.setattr(cli, "is_setup", lambda: False)
    monkeypatch.setattr(cli, "needs_update", lambda: False)
    monkeypatch.setattr("sys.argv", ["tt", "setup"])
    cli.main()
    assert calls == {}  # 既没进 wizard 也没 auto


def test_codex_statusline_uninstall_keeps_other_stop_hooks(tmp_path, monkeypatch):
    # 卸载只移除 tt 自己追加的那段 [[hooks.Stop]]，用户已有的 Stop hook 不动。
    monkeypatch.setattr(hooks, "CODEX_STATUSLINE_HOOK_PATH", str(tmp_path / "tt-statusline.py"))
    user_stop = (
        '\n[[hooks.Stop]]\n\n'
        '[[hooks.Stop.hooks]]\ntype = "command"\ncommand = "/usr/bin/my-other-stop"\ntimeout = 3\n'
    )
    base = '[tui]\nstatus_line = ["project"]\n' + user_stop
    installed = hooks._install_codex_statusline(base, "python3")
    removed = hooks._uninstall_codex_statusline(installed)
    assert "tt-statusline" not in removed
    assert "/usr/bin/my-other-stop" in removed  # 用户的 Stop 完整保留


@pytest.mark.skipif(not shutil.which("git"), reason="需要 git")
def test_statusline_shows_git_diff_stat(tmp_path):
    # statusline 第一行在分支括号内显示相对 HEAD 的未提交增删（+N 绿 / -N 红），0 改动则隐藏。
    script_path = tmp_path / "tt-statusline.py"
    script_path.write_text(hooks._render_hook_script(), encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("1\n2\n3\n")
    (repo / "b.txt").write_text("1\n2\n3\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")

    # 干净工作区 → 括号里只有分支、无 +/-
    line_clean = _run_statusline(script_path, repo)
    assert "[repo]" in line_clean
    assert "+" not in line_clean and "-" not in line_clean

    # a.txt 追加 2 行（+2）、b.txt 删 1 行（-1），未暂存 → 相对 HEAD 共 +2 -1
    (repo / "a.txt").write_text("1\n2\n3\n4\n5\n")
    (repo / "b.txt").write_text("1\n2\n")
    line_dirty = _run_statusline(script_path, repo)
    assert "+2" in line_dirty and "-1" in line_dirty


def _run_statusline_home(script_path, payload, home):
    """隔离 HOME 下跑落盘 statusline 脚本，返回完整 stdout（不污染真实 ~/.claude）。"""
    env = {**os.environ, "HOME": str(home), "COLORTERM": "truecolor"}
    r = subprocess.run([sys.executable, str(script_path)], input=json.dumps(payload),
                       text=True, capture_output=True, env=env)
    return r.stdout


def test_statusline_line4_tps_code_repo(tmp_path):
    # Line 4：本轮 TPS（api_duration 差分）+ Code 行数 + Repo host。
    script = tmp_path / "tt-statusline.py"
    script.write_text(hooks._render_hook_script(), encoding="utf-8")
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    base = {
        "session_id": "S1",
        "workspace": {"project_dir": str(tmp_path), "repo": {"host": "github.com"}},
        "context_window": {"current_usage": {"output_tokens": 10}},
        "cost": {"total_api_duration_ms": 1000, "total_lines_added": 208, "total_lines_removed": 8},
    }
    _run_statusline_home(script, base, home)  # 第一帧：写 tt-status.json 建立 prev
    frame2 = {
        "session_id": "S1",
        "workspace": {"project_dir": str(tmp_path), "repo": {"host": "github.com"}},
        "context_window": {"current_usage": {"output_tokens": 200}},
        "cost": {"total_api_duration_ms": 2000, "total_lines_added": 208, "total_lines_removed": 8},
    }
    out = _run_statusline_home(script, frame2, home)  # 同会话 Δ1000ms / output 200 → TPS 200
    assert "TPS: 200 tokens/s" in out  # 带单位
    assert "Code" in out and "+208" in out and "-8" in out
    assert "Remote: github" in out and "github.com" not in out  # .com 被去除
    # 第三帧空闲（Δ=0、output 小）→ 沿用上次 200，不回落到 -
    frame3 = {**frame2, "context_window": {"current_usage": {"output_tokens": 2}}}
    out3 = _run_statusline_home(script, frame3, home)
    assert "TPS: 200 tokens/s" in out3


def test_statusline_total_tokens(tmp_path):
    # Total：从 transcript 解析会话累计 in+out+cache（去重、跳非 assistant），第 1 行显示总和。
    script = tmp_path / "tt-statusline.py"
    script.write_text(hooks._render_hook_script(), encoding="utf-8")
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    tx = tmp_path / "tx.jsonl"
    rows = [
        {"type": "assistant", "requestId": "r1", "message": {"id": "m1", "usage": {
            "input_tokens": 100, "output_tokens": 2000,
            "cache_creation_input_tokens": 500, "cache_read_input_tokens": 3000}}},
        {"type": "assistant", "requestId": "r1", "message": {"id": "m1", "usage": {  # 重复 → 去重
            "input_tokens": 100, "output_tokens": 2000,
            "cache_creation_input_tokens": 500, "cache_read_input_tokens": 3000}}},
        {"type": "assistant", "requestId": "r2", "message": {"id": "m2", "usage": {
            "input_tokens": 50, "output_tokens": 1000,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 4000}}},
        {"type": "user", "message": {}},  # 非 assistant 跳过
    ]
    tx.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    payload = {"session_id": "S1", "transcript_path": str(tx),
               "workspace": {"project_dir": str(tmp_path)},
               "context_window": {"current_usage": {"output_tokens": 1}},
               "cost": {"total_api_duration_ms": 1000}}
    out = _run_statusline_home(script, payload, home)
    # in=150, out=3000, cache=(500+3000)+(0+4000)=7500；Total=in+out+cache=10650→11k
    assert "Total: 11k" in out
    assert "Cache" not in out  # Cache 单列已删除


def test_statusline_line3_tps_hidden_when_no_prior_value(tmp_path):
    # 从未有过有效值时（output 一直太小）→ TPS 项隐藏（不再显示 "-"）；L3 无其它数据时整行不出现。
    script = tmp_path / "tt-statusline.py"
    script.write_text(hooks._render_hook_script(), encoding="utf-8")
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    base = {"session_id": "S1", "workspace": {"project_dir": str(tmp_path)},
            "context_window": {"current_usage": {"output_tokens": 2}},
            "cost": {"total_api_duration_ms": 5000}}
    _run_statusline_home(script, base, home)
    out = _run_statusline_home(script, base, home)  # Δ=0、output=2、无历史值 → 不显示 TPS 项
    assert "TPS" not in out


def test_statusline_tps_keeps_last_value_when_zero(tmp_path):
    # 算出会显示成 0 的（output 小 / Δ 很大）→ 不刷新，保持上次有效值。
    script = tmp_path / "tt-statusline.py"
    script.write_text(hooks._render_hook_script(), encoding="utf-8")
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)

    def frame(api, out):
        return {"session_id": "S1", "workspace": {"project_dir": str(tmp_path)},
                "context_window": {"current_usage": {"output_tokens": out}},
                "cost": {"total_api_duration_ms": api}}

    _run_statusline_home(script, frame(10000, 5), home)            # 建 prev_api
    out2 = _run_statusline_home(script, frame(11000, 200), home)   # Δ1000ms / out200 → tps 200
    assert "TPS: 200 tokens/s" in out2
    # Δ 很大(100s) + output 小(20) → tps≈0.2 → round 0 → 不刷新、沿用 200
    out3 = _run_statusline_home(script, frame(111000, 20), home)
    assert "TPS: 200 tokens/s" in out3
    assert "TPS: 0 tokens/s" not in out3


def test_statusline_tps_isolated_per_session(tmp_path):
    # 多会话共享 tt-status.json：TPS 差分按 session_id 隔离，别的会话覆盖文件也不把本会话清成 "-"。
    script = tmp_path / "tt-statusline.py"
    script.write_text(hooks._render_hook_script(), encoding="utf-8")
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)

    def frame(sid, api, out):
        return {"session_id": sid, "workspace": {"project_dir": str(tmp_path)},
                "context_window": {"current_usage": {"output_tokens": out}},
                "cost": {"total_api_duration_ms": api}}

    _run_statusline_home(script, frame("A", 1000, 5), home)            # A 建 prev_api
    _run_statusline_home(script, frame("B", 500000, 5), home)          # B 覆盖文件、建自己 prev
    out_a = _run_statusline_home(script, frame("A", 2000, 200), home)  # A：Δ1000 / out200 → 200
    assert "TPS: 200 tokens/s" in out_a                                # 没被 B 的覆盖清成 "-"
    _run_statusline_home(script, frame("B", 502000, 5), home)          # 夹一帧 B
    out_b = _run_statusline_home(script, frame("B", 504000, 300), home)  # B：Δ2000 / out300 → 150
    assert "TPS: 150 tokens/s" in out_b


def test_statusline_progress_bar_empty_grid_tinted(tmp_path):
    # 进度条未填充网格按当前档位色着色；pct=0 时保持灰（裸 ░ 紧跟 reset、不着色）。
    script = tmp_path / "tt-statusline.py"
    script.write_text(hooks._render_hook_script(), encoding="utf-8")
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)

    def bar_out(pct):
        payload = {"session_id": "S1", "workspace": {"project_dir": str(tmp_path)},
                   "rate_limits": {"five_hour": {"used_percentage": pct}}}
        return _run_statusline_home(script, payload, home)

    esc = re.compile(r"\x1b\[[0-9;]*m")

    out0 = bar_out(0)
    assert "░" in out0 and esc.findall(out0)[-1] + "░" in out0      # pct=0：灰格紧跟 reset、未着色

    out60 = bar_out(60)
    assert "░" in out60 and esc.findall(out60)[-1] + "░" not in out60  # pct>0：未填充格被染色、不在 reset 后


def test_setup_codex_creates_missing_config(tmp_path, monkeypatch):
    # 装了 Codex（~/.codex 目录在）但还没 config.toml → setup 应创建该文件并写入伪 statusline hook。
    # 新版不再动 [tui].status_line（伪 statusline 比官方更全）。
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)  # 只有目录、无 config.toml
    codex_config = home / ".codex" / "config.toml"
    monkeypatch.setattr(hooks, "CODEX_DIR", str(home / ".codex"))
    monkeypatch.setattr(hooks, "CODEX_CONFIG", str(codex_config))
    monkeypatch.setattr(hooks, "CODEX_STATUSLINE_HOOK_PATH", str(home / ".codex" / "tt-statusline.py"))
    monkeypatch.setattr(hooks.config, "CONFIG_PATH", str(tmp_path / "tt-config.json"))  # 隔离 config.json

    assert not codex_config.exists()
    hooks._setup_codex(hooks.SetupComponents(), quiet=True)
    assert codex_config.exists()  # 已创建
    content = codex_config.read_text()
    assert "five-hour-limit" not in content  # 新版不接管 status_line
    assert "tt-statusline" in content        # 伪 statusline Stop hook 写入


def test_detect_system_lang_non_darwin_falls_back_to_env(monkeypatch):
    # 非 macOS（或 darwin 检测失败）回退环境变量：LANG=zh → zh，否则 en。
    from token_tracker import i18n
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)
    assert i18n._detect_system_lang() == "zh"
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert i18n._detect_system_lang() == "en"


# --- SETUP_VERSION 引导版本（老用户升级后重新引导） ---


def _isolate_config(monkeypatch, tmp_path):
    """把 config.py 的所有路径常量切到 tmp_path，避免污染主人真实 ~/.config/token-tracker。"""
    from token_tracker import config
    monkeypatch.setattr(config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(config, "_LEGACY_THEME_PATH", str(tmp_path / "theme.json"))
    monkeypatch.setattr(config, "_LEGACY_LANG_PATH", str(tmp_path / "lang.json"))


def test_setup_writes_setup_version(tmp_path, monkeypatch):
    # setup() 真正落地后必须写入 setup_version=当前 SETUP_VERSION——
    # 这是引导机制收口：所有路径（新用户 / wizard / _auto_setup / 手动 tt setup）都经此。
    from token_tracker import config
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".codex").mkdir(parents=True)
    settings_path = home / ".claude" / "settings.json"
    settings_path.write_text("{}", encoding="utf-8")
    codex_config = home / ".codex" / "config.toml"
    codex_config.write_text("", encoding="utf-8")
    monkeypatch.setattr(hooks, "CLAUDE_SETTINGS", str(settings_path))
    monkeypatch.setattr(hooks, "HOOK_SCRIPT_PATH", str(home / ".claude" / "tt-statusline.py"))
    monkeypatch.setattr(hooks, "CODEX_DIR", str(home / ".codex"))
    monkeypatch.setattr(hooks, "CODEX_CONFIG", str(codex_config))
    monkeypatch.setattr(hooks, "CODEX_STATUSLINE_HOOK_PATH", str(home / ".codex" / "tt-statusline.py"))
    _isolate_config(monkeypatch, tmp_path / "cfg")

    assert config.setup_version() == 0  # 老用户初始 0
    hooks.setup(quiet=True)
    assert config.setup_version() == config.SETUP_VERSION  # setup 完成后被打上当前版本


def test_cli_outdated_setup_triggers_setup_flow(monkeypatch, tmp_path):
    # 老用户 is_setup=True 且 setup_version < SETUP_VERSION → 自动走 _run_setup_flow
    # （内部分流真终端 wizard / 会话内 _auto_setup，这里只验触发、不管分流）。
    from token_tracker import cli, config
    _isolate_config(monkeypatch, tmp_path)
    calls: dict = {}

    def fake_flow():
        calls["flow"] = True
        raise SystemExit(0)  # 短路 cli.main 后续数据命令逻辑

    monkeypatch.setattr(cli, "_run_setup_flow", fake_flow)
    monkeypatch.setattr(cli, "is_setup", lambda: True)
    monkeypatch.setattr(cli, "needs_update", lambda: False)
    # setup_version 字段缺失 → 读出 0 < SETUP_VERSION
    monkeypatch.setattr(config, "SETUP_VERSION", 2)
    monkeypatch.setattr("sys.argv", ["tt", "status"])

    with pytest.raises(SystemExit):
        cli.main()
    assert calls == {"flow": True}


def test_cli_setup_up_to_date_skips_flow(monkeypatch, tmp_path):
    # setup_version 已是当前 → 不触发 _run_setup_flow，正常往下跑。
    from token_tracker import cli, config
    _isolate_config(monkeypatch, tmp_path)
    calls: dict = {}

    monkeypatch.setattr(cli, "_run_setup_flow", lambda: calls.__setitem__("flow", True))
    monkeypatch.setattr(cli, "is_setup", lambda: True)
    monkeypatch.setattr(cli, "needs_update", lambda: False)
    monkeypatch.setattr(cli, "_build_status_data", lambda _agents: {})
    from types import SimpleNamespace
    monkeypatch.setattr(cli, "detect_agents",
                        lambda: [SimpleNamespace(name="Claude Code", id="claude-code")])
    config.save_setup_version(config.SETUP_VERSION)  # 已是最新
    monkeypatch.setattr("sys.argv", ["tt", "status"])

    cli.main()
    assert calls == {}
