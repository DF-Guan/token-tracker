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


def test_report_hooks_render_inject_version_and_python():
    # CC / Codex 报表 hook 模板：版本号 + 解释器都注入、占位符不残留、用 -m 调 tt。
    for render in (hooks._render_cc_report_hook, hooks._render_codex_report_hook):
        rendered = render()
        assert f'__version__ = "{hooks.REPORT_HOOK_VERSION}"' in rendered
        assert "__REPORT_HOOK_VERSION__" not in rendered
        assert "__TT_PYTHON__" not in rendered
        assert "token_tracker.cli" in rendered


def test_codex_statusline_render_injects_version():
    # Codex 伪 statusline 脚本：版本号注入、占位符不残留、语法正确（无 __TT_PYTHON__ 需求）。
    rendered = hooks._render_codex_statusline_hook()
    assert f'__version__ = "{hooks.STATUSLINE_HOOK_VERSION}"' in rendered
    assert "__STATUSLINE_HOOK_VERSION__" not in rendered
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
    assert c.report_hooks is True and c.codex_faux_statusline is True
    assert hooks.SetupComponents.all_on() == c


def test_setup_components_off_skips_install(tmp_path, monkeypatch):
    # components.report_hooks=False → CC report hook 不装；codex_faux_statusline=False → Codex 伪 statusline 不装。
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
    monkeypatch.setattr(hooks, "CC_REPORT_HOOK_PATH", str(home / ".claude" / "tt-report-hook.py"))
    monkeypatch.setattr(hooks, "CC_COMMANDS_DIR", str(home / ".claude" / "commands"))
    monkeypatch.setattr(hooks, "CODEX_CONFIG", str(codex_config))
    monkeypatch.setattr(hooks, "CODEX_REPORT_HOOK_PATH", str(home / ".codex" / "tt-report-hook.py"))
    monkeypatch.setattr(hooks, "CODEX_STATUSLINE_HOOK_PATH", str(home / ".codex" / "tt-statusline.py"))

    hooks.setup(components=hooks.SetupComponents(report_hooks=False, codex_faux_statusline=False))

    # CC statusline 仍装；CC report hook 不装
    assert json.loads(settings_path.read_text())["statusLine"]["command"].endswith("tt-statusline.py")
    assert not os.path.exists(str(home / ".claude" / "tt-report-hook.py"))
    # Codex status_line 仍写、但 Stop hook（tt-statusline）不在 config 里
    codex_content = codex_config.read_text()
    assert "five-hour-limit" in codex_content
    assert "tt-statusline" not in codex_content   # Codex 伪 statusline hook 段未追加
    assert "tt-report-hook" not in codex_content  # report hook 段未追加


def test_cli_setup_dash_i_calls_run_wizard(monkeypatch):
    # `tt setup -i` 进完整重配：调 run_wizard（语言+主题+增强项），而非直接 setup() 全装。
    from token_tracker import cli, wizard
    calls: dict = {}

    def mock_run_wizard():
        calls["run_wizard"] = True

    def mock_setup(components=None):
        calls["setup_direct"] = True  # 不应该走这里

    monkeypatch.setattr(wizard, "run_wizard", mock_run_wizard)
    monkeypatch.setattr("token_tracker.cli.setup", mock_setup)
    monkeypatch.setattr(cli, "is_setup", lambda: True)
    monkeypatch.setattr(cli, "needs_update", lambda: False)
    monkeypatch.setattr("sys.argv", ["tt", "setup", "-i"])
    cli.main()
    assert calls.get("run_wizard") is True
    assert calls.get("setup_direct") is None  # 没绕过 wizard 直接全装


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


def test_is_tt_report_entry():
    tt = {"matcher": "tt-daily", "hooks": [{"type": "command", "command": "py /x/tt-report-hook.py"}]}
    other = {"matcher": "x", "hooks": [{"type": "command", "command": "echo hi"}]}
    assert hooks._is_tt_report_entry(tt)
    assert not hooks._is_tt_report_entry(other)


def test_install_cc_report_merges_and_idempotent(tmp_path, monkeypatch):
    # 合并进 UserPromptExpansion：保留用户项、追加 tt 两项；重复装不翻倍。
    monkeypatch.setattr(hooks, "CC_REPORT_HOOK_PATH", str(tmp_path / "tt-report-hook.py"))
    monkeypatch.setattr(hooks, "CC_COMMANDS_DIR", str(tmp_path / "commands"))
    mine = {"matcher": "mine", "hooks": [{"type": "command", "command": "echo hi"}]}
    settings = {"hooks": {"UserPromptExpansion": [mine]}}
    hooks._install_cc_report(settings, "python3")
    assert [e["matcher"] for e in settings["hooks"]["UserPromptExpansion"]] == ["mine", "tt-daily", "tt-weekly"]
    hooks._install_cc_report(settings, "python3")  # 幂等
    assert [e["matcher"] for e in settings["hooks"]["UserPromptExpansion"]] == ["mine", "tt-daily", "tt-weekly"]
    # 卸载只移除 tt，保留用户项
    hooks._uninstall_cc_report(settings)
    assert settings["hooks"]["UserPromptExpansion"] == [mine]


def test_codex_report_install_uninstall_roundtrip(tmp_path, monkeypatch):
    # 末尾追加 tt 段、保留用户已有 hook；幂等；卸载删净 tt 段、留用户项。
    monkeypatch.setattr(hooks, "CODEX_REPORT_HOOK_PATH", str(tmp_path / "tt-report-hook.py"))
    base = ('[tui]\nstatus_line = ["project"]\n\n[[hooks.UserPromptSubmit]]\n\n'
            '[[hooks.UserPromptSubmit.hooks]]\ntype = "command"\ncommand = "mine"\n')
    installed = hooks._install_codex_report(base, "python3")
    assert "tt-report-hook" in installed and 'command = "mine"' in installed
    assert hooks._install_codex_report(installed, "python3") == installed  # 幂等
    removed = hooks._uninstall_codex_report(installed)
    assert "tt-report-hook" not in removed and 'command = "mine"' in removed


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
