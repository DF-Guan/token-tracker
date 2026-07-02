from token_tracker import cli
from token_tracker.adapters.types import DailyStats


def test_apply_sort_by_tokens_uses_authoritative_attr():
    stats = [
        DailyStats(date="2026-01-01", total_tokens=10),
        DailyStats(date="2026-01-02", total_tokens=30),
    ]
    cli._apply_sort(stats, "tokens", descending=True, default_attr="date", default_reverse=True)
    assert [s.total_tokens for s in stats] == [30, 10]


def test_apply_sort_time_falls_back_to_default_attr():
    stats = [
        DailyStats(date="2026-01-01", total_tokens=99),
        DailyStats(date="2026-01-03", total_tokens=1),
    ]
    # "time" 不在 SORT_ATTRS，应按 default_attr=date 排
    cli._apply_sort(stats, "time", descending=True, default_attr="date", default_reverse=True)
    assert [s.date for s in stats] == ["2026-01-03", "2026-01-01"]


def test_apply_sort_unknown_key_falls_back():
    stats = [
        DailyStats(date="2026-01-02", total_tokens=5),
        DailyStats(date="2026-01-01", total_tokens=99),
    ]
    cli._apply_sort(stats, "bogus", descending=True, default_attr="date", default_reverse=True)
    assert [s.date for s in stats] == ["2026-01-02", "2026-01-01"]


def test_extract_theme_arg():
    # --theme NAME 从任意位置提取并从 args 移除；未给则 None；缺值不崩
    assert cli._extract_theme_arg(["monthly", "--theme", "dracula"]) == (["monthly"], "dracula")
    assert cli._extract_theme_arg(["--theme", "nord", "weekly"]) == (["weekly"], "nord")
    assert cli._extract_theme_arg(["monthly"]) == (["monthly"], None)
    assert cli._extract_theme_arg(["--theme"]) == (["--theme"], None)  # 缺值：原样留，不消耗


def test_asc_without_sort_respected():
    # 回归：`tt daily --asc`（不带 --sort）此前被静默忽略；显式方向必须覆盖各命令默认方向。
    args, sort_key, descending = cli._parse_sort_args(["--asc"])
    assert (args, sort_key, descending) == ([], None, False)
    stats = [
        DailyStats(date="2026-01-01", total_tokens=30),
        DailyStats(date="2026-01-02", total_tokens=10),
    ]
    cli._apply_sort(stats, None, descending, default_attr="total_tokens", default_reverse=True)
    assert [s.total_tokens for s in stats] == [10, 30]  # --asc 生效（默认应是降序）
    # 没显式给方向（None）→ 仍走命令默认方向
    args2, key2, desc2 = cli._parse_sort_args([])
    assert desc2 is None
    cli._apply_sort(stats, None, desc2, default_attr="total_tokens", default_reverse=True)
    assert [s.total_tokens for s in stats] == [30, 10]


def test_current_session_agent_ignores_claude_config_dir(monkeypatch):
    # 回归：CLAUDE_CONFIG_DIR 是用户级配置变量（shell profile 长期 export 挪目录），
    # 不能当会话信号——否则独立终端被误判会话内（daily/weekly 被过滤、wizard 永不出现）。
    for var in ("CODEX_THREAD_ID", "CODEX_SANDBOX", "CLAUDECODE", "CLAUDE_CONFIG_DIR"):
        monkeypatch.delenv(var, raising=False)
    assert cli._current_session_agent() is None
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/custom/claude")  # 仅配置变量 → 仍是独立终端
    assert cli._current_session_agent() is None
    monkeypatch.setenv("CLAUDECODE", "1")                      # 真会话信号
    assert cli._current_session_agent() == "claude-code"
    monkeypatch.setenv("CODEX_THREAD_ID", "t1")                # Codex 信号优先级在前
    assert cli._current_session_agent() == "codex"
