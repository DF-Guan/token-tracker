import json
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
