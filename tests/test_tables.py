import contextlib
from datetime import datetime

from token_tracker.adapters.types import DailyStats, MonthlyStats, WeeklyStats
from token_tracker.ui.console import capture_console
from token_tracker.ui.tables import render_monthly


def _month(month, agent="claude-code", tokens=0, cost=0.0, sessions=0, msgs=0,
           models=None, projects=None):
    return MonthlyStats(month=month, total_tokens=tokens, cost_usd=cost,
                        session_count=sessions, message_count=msgs,
                        models=models or {}, projects=projects or {}, agent_id=agent)


def test_render_monthly_weekly_style_blocks(monkeypatch):
    # monthly 重构为 weekly 同款：This Month 卡片 + Weekly Trend 按周柱状 + Monthly Trend 逐月进度条 + Project/Model Trend。
    monkeypatch.setattr("token_tracker.ui.tables.forced_color_console", contextlib.nullcontext)

    # 固定 now=2026-06-22（周一）：Weekly Trend 是固定 30 周窗口，否则 mock 周会随真实日期被挤出窗口、测试失稳
    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 22, tzinfo=tz)

    monkeypatch.setattr("token_tracker.ui.tables.datetime", _Frozen)
    stats = [
        _month("2026-05", tokens=500_000, cost=50.0, sessions=10, msgs=100,
               models={"claude-opus-4-8": 500_000}, projects={"proj-a": 500_000}),
        _month("2026-06", tokens=2_000_000, cost=200.0, sessions=20, msgs=200,
               models={"claude-opus-4-8": 1_500_000, "claude-haiku-4-5": 500_000},
               projects={"token-tracker": 1_400_000, "infohunter": 600_000}),
    ]
    daily = [DailyStats(date=f"2026-06-{d:02d}") for d in range(1, 6)]  # 本月 5 个活跃天
    weekly = [
        # week 是 monday 的 ISO 日期（与 aggregator.aggregate_weekly 一致），barchart 据此补齐缺失周
        WeeklyStats(week="2026-06-08", week_start="06-08", week_end="06-14", total_tokens=400_000),
        WeeklyStats(week="2026-06-15", week_start="06-15", week_end="06-21", total_tokens=1_200_000),
    ]
    with capture_console(160) as buf:
        render_monthly(stats, agents=["Claude Code"], daily=daily, weekly=weekly)
    out = buf.getvalue()

    assert "This Month" in out and "2026-06" in out         # 本月卡片
    assert "Weekly Trend" in out and "6/15" in out          # 按周橙色柱状图（标签 M/DD）
    assert "Monthly Trend" in out and "2026-05" in out      # 逐月进度条含上月
    assert "Project Trend" in out and "token-tracker" in out
    assert "Model Trend" in out and "Opus 4.8" in out
    assert "5/30" in out                                     # Active Days = 5 活跃天 / 6 月 30 天


def test_render_monthly_merges_agents(monkeypatch):
    # 多 agent 同月合并：两条 2026-06（CC + Codex）token 相加。
    monkeypatch.setattr("token_tracker.ui.tables.forced_color_console", contextlib.nullcontext)
    stats = [
        _month("2026-06", agent="claude-code", tokens=1_000_000, cost=100.0),
        _month("2026-06", agent="codex", tokens=2_000_000, cost=50.0),
    ]
    with capture_console(160) as buf:
        render_monthly(stats, agents=["Claude Code", "Codex"])
    out = buf.getvalue()
    assert "3.0M" in out  # 1M + 2M 合并


def test_render_monthly_empty():
    # 空数据不崩、给出无数据提示。
    with capture_console(160) as buf:
        render_monthly([], agents=["Claude Code"])
    assert buf.getvalue().strip() != ""
