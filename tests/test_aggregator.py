from datetime import datetime, timezone

from src.adapters.types import UsageEntry
from src.analyzer.aggregator import (
    aggregate_daily,
    aggregate_monthly,
    aggregate_sessions,
    aggregate_weekly,
)


def entry(ts, session_id, *, tokens=100, cost=0.5, msgs=1, model="claude-opus-4-6", project="proj"):
    # cost_usd is set explicitly so calculate_cost() short-circuits and never
    # touches the pricing network/cache — keeps these tests hermetic.
    return UsageEntry(
        timestamp=ts,
        session_id=session_id,
        message_id=f"m-{ts.isoformat()}-{session_id}",
        request_id=f"r-{ts.isoformat()}-{session_id}",
        model=model,
        input_tokens=tokens,
        output_tokens=0,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        cost_usd=cost,
        project=project,
        agent_id="claude",
        message_count=msgs,
    )


def test_aggregate_daily_groups_by_date_and_counts_unique_sessions():
    d1 = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    d1b = datetime(2026, 1, 1, 23, tzinfo=timezone.utc)
    d2 = datetime(2026, 1, 2, 9, tzinfo=timezone.utc)
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
    jan = datetime(2026, 1, 15, tzinfo=timezone.utc)
    feb = datetime(2026, 2, 3, tzinfo=timezone.utc)
    monthly = aggregate_monthly([entry(jan, "s1", cost=1.0), entry(feb, "s2", cost=2.0)])
    assert [m.month for m in monthly] == ["2026-01", "2026-02"]
    assert monthly[0].cost_usd == 1.0
    assert monthly[1].session_count == 1


def test_aggregate_weekly_groups_by_iso_week():
    thu = datetime(2026, 1, 1, tzinfo=timezone.utc)   # Thursday
    fri = datetime(2026, 1, 2, tzinfo=timezone.utc)   # same ISO week
    next_mon = datetime(2026, 1, 5, tzinfo=timezone.utc)  # next week
    weekly = aggregate_weekly([entry(thu, "s1"), entry(fri, "s1"), entry(next_mon, "s2")])
    assert len(weekly) == 2
    first = weekly[0]
    assert first.week == "2025-12-29"  # Monday of the first week
    assert first.total_tokens == 200


def test_aggregate_sessions_computes_duration_and_primary_model():
    t0 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc)
    sessions = aggregate_sessions([
        entry(t0, "s1", tokens=100, cost=0.5, model="claude-opus-4-6"),
        entry(t1, "s1", tokens=300, cost=1.5, model="claude-sonnet-4-6"),
    ])
    assert len(sessions) == 1
    s = sessions[0]
    assert s.session_id == "s1"
    assert s.duration_minutes == 30.0
    assert s.total_tokens == 400
    assert s.cost_usd == 2.0
    # primary model = the one with the most tokens (sonnet 300 > opus 100)
    assert s.model == "claude-sonnet-4-6"
