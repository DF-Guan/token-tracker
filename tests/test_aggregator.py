from datetime import UTC, datetime

from token_tracker.adapters.types import UsageEntry
from token_tracker.analyzer.aggregator import (
    aggregate_daily,
    aggregate_monthly,
    aggregate_sessions,
    aggregate_weekly,
)


def entry(ts, session_id, *, tokens=100, out=0, cache_read=0, cost=0.5, msgs=1,
          model="claude-opus-4-6", project="proj"):
    # cost_usd is set explicitly so calculate_cost() short-circuits and never
    # touches the pricing network/cache — keeps these tests hermetic.
    return UsageEntry(
        timestamp=ts,
        session_id=session_id,
        message_id=f"m-{ts.isoformat()}-{session_id}",
        request_id=f"r-{ts.isoformat()}-{session_id}",
        model=model,
        input_tokens=tokens,
        output_tokens=out,
        cache_creation_tokens=0,
        cache_read_tokens=cache_read,
        cost_usd=cost,
        project=project,
        agent_id="claude",
        message_count=msgs,
    )


def test_aggregate_daily_groups_by_date_and_counts_unique_sessions():
    d1 = datetime(2026, 1, 1, 10, tzinfo=UTC)
    d1b = datetime(2026, 1, 1, 23, tzinfo=UTC)
    d2 = datetime(2026, 1, 2, 9, tzinfo=UTC)
    daily = aggregate_daily([
        entry(d1, "s1", tokens=100, cost=0.5),
        entry(d1b, "s2", tokens=200, cost=1.0),
        entry(d2, "s1", tokens=300, cost=1.5),
    ])
    assert [d.date for d in daily] == ["2026-01-01", "2026-01-02"]
    jan1 = daily[0]
    assert jan1.total_tokens == 300
    assert jan1.input_tokens == 300
    assert jan1.cost_usd == 1.5
    assert jan1.session_count == 2  # s1 + s2 on the same day
    assert jan1.message_count == 2
    assert daily[1].session_count == 1


def test_aggregate_monthly_groups_by_month():
    jan = datetime(2026, 1, 15, tzinfo=UTC)
    feb = datetime(2026, 2, 3, tzinfo=UTC)
    monthly = aggregate_monthly([entry(jan, "s1", cost=1.0), entry(feb, "s2", cost=2.0)])
    assert [m.month for m in monthly] == ["2026-01", "2026-02"]
    assert monthly[0].cost_usd == 1.0
    assert monthly[1].session_count == 1


def test_aggregate_weekly_groups_by_iso_week():
    thu = datetime(2026, 1, 1, tzinfo=UTC)   # Thursday
    fri = datetime(2026, 1, 2, tzinfo=UTC)   # same ISO week
    next_mon = datetime(2026, 1, 5, tzinfo=UTC)  # next week
    weekly = aggregate_weekly([entry(thu, "s1"), entry(fri, "s1"), entry(next_mon, "s2")])
    assert len(weekly) == 2
    first = weekly[0]
    assert first.week == "2025-12-29"  # Monday of the first week
    assert first.total_tokens == 200


def test_aggregate_sessions_primary_model_by_output_not_cache():
    # 代表模型按 output（真实生成量）选，不被 cache_read 撑高 total 的后台小模型带偏。
    t0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 10, 30, tzinfo=UTC)
    sessions = aggregate_sessions([
        # opus 真正生成（output 高）；haiku 几乎没生成，只读了海量上下文（cache_read 撑高 total）
        entry(t0, "s1", out=500, cost=0.5, model="claude-opus-4-8"),
        entry(t1, "s1", out=5, cache_read=1_000_000, cost=1.5, model="claude-haiku-4-5"),
    ])
    assert len(sessions) == 1
    s = sessions[0]
    assert s.session_id == "s1"
    assert s.duration_minutes == 30.0
    assert s.cost_usd == 2.0
    # 按 total 会误选 haiku（cache_read 巨大）；按 output 正确选 opus
    assert s.model == "claude-opus-4-8"
    # models 按 output 降序，供「最多展示两个」用
    assert list(s.models) == ["claude-opus-4-8", "claude-haiku-4-5"]


def test_aggregate_sessions_models_ordered_by_output_for_display():
    # 三个 model 时 models 仍按 output 降序，渲染层取前两个展示
    t0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    sessions = aggregate_sessions([
        entry(t0, "s1", out=10, model="claude-haiku-4-5"),
        entry(t0, "s1", out=900, model="claude-opus-4-8"),
        entry(t0, "s1", out=300, model="claude-sonnet-4-6"),
    ])
    s = sessions[0]
    assert list(s.models) == ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5"]


def test_aggregate_sessions_active_minutes_drops_large_gaps():
    # 活跃时长：相邻间隔 ≤30min 才累加，大空隙（这里跨 3 天）整段丢弃；duration_minutes 仍是首尾跨度
    base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    from datetime import timedelta
    sessions = aggregate_sessions([
        entry(base, "s1"),                               # 10:00
        entry(base + timedelta(minutes=20), "s1"),       # +20min（≤30，计入）
        entry(base + timedelta(minutes=40), "s1"),       # +20min（≤30，计入）
        entry(base + timedelta(days=3), "s1"),           # 跨 3 天大空隙（>30min，丢弃）
        entry(base + timedelta(days=3, minutes=10), "s1"),  # +10min（≤30，计入）
    ])
    s = sessions[0]
    # 活跃 = 20 + 20 + 10 = 50min（3 天空隙不计）
    assert s.active_minutes == 50.0
    # 跨度 = 首尾 3 天 10 分钟
    assert s.duration_minutes == round((3 * 24 * 60) + 10, 1)


def test_fmt_session_duration_combines_active_and_span():
    from token_tracker.ui.format import _fmt_session_duration
    # 活跃恒小数小时；跨度 ≥1 天用 天d时h（整天省略小时），<1 天用小数小时
    assert _fmt_session_duration(564, 32520) == "9.4h / 22d14h"        # 主例：活跃 9h24m / 跨度 22d14h
    assert _fmt_session_duration(9 * 60, 22 * 24 * 60) == "9.0h / 22d"  # 整天跨度省略小时
    assert _fmt_session_duration(5 * 60, 6 * 60) == "5.0h / 6.0h"      # 跨度 <1 天用小数小时
    assert _fmt_session_duration(45, 90) == "0.8h / 1.5h"             # 活跃/跨度均不足 1h/1 天


def test_aggregate_fills_projects_by_token():
    # projects 维度（weekly 项目分布用）：按 project 累加 token，与 models 同机制
    d = datetime(2026, 1, 1, 10, tzinfo=UTC)
    daily = aggregate_daily([
        entry(d, "s1", tokens=100, project="alpha"),
        entry(d, "s2", tokens=300, project="beta"),
        entry(d, "s3", tokens=50, project="alpha"),
    ])
    assert daily[0].projects == {"alpha": 150, "beta": 300}
