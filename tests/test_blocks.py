from datetime import UTC, datetime, timedelta

from src.adapters.types import DailyStats, UsageEntry
from src.analyzer.blocks import analyze_blocks, calculate_p90


def entry(ts, *, tokens=100, cost=0.5):
    return UsageEntry(
        timestamp=ts,
        session_id="s1",
        message_id=f"m-{ts.isoformat()}",
        request_id=f"r-{ts.isoformat()}",
        model="claude-opus-4-6",
        input_tokens=tokens,
        output_tokens=0,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        cost_usd=cost,
        project="proj",
        agent_id="claude",
    )


def test_empty_entries_returns_no_blocks():
    assert analyze_blocks([]) == []


def test_entries_within_5h_form_single_block():
    # Use a date in the past so the block is never "active" — keeps burn_rate deterministic.
    base = datetime(2020, 1, 1, 10, 0, tzinfo=UTC)
    blocks = analyze_blocks([
        entry(base),
        entry(base + timedelta(hours=1)),
        entry(base + timedelta(hours=2)),
    ])
    real = [b for b in blocks if not b.is_gap]
    assert len(real) == 1
    b = real[0]
    assert b.total_tokens == 300
    assert b.cost_usd == 1.5
    assert b.is_active is False
    assert b.burn_rate == 0.0


def test_gap_block_inserted_after_long_inactivity():
    base = datetime(2020, 1, 1, 10, 0, tzinfo=UTC)
    later = base + timedelta(hours=8)  # past the 5h block, gap far longer than 5 min
    blocks = analyze_blocks([entry(base), entry(later)])
    assert len([b for b in blocks if not b.is_gap]) == 2
    assert len([b for b in blocks if b.is_gap]) == 1


def test_no_gap_block_for_short_inactivity():
    base = datetime(2020, 1, 1, 10, 0, tzinfo=UTC)
    nxt = base + timedelta(hours=5, minutes=2)  # new block, but only a 2 min gap
    blocks = analyze_blocks([entry(base), entry(nxt)])
    assert [b for b in blocks if b.is_gap] == []
    assert len([b for b in blocks if not b.is_gap]) == 2


def test_p90_returns_empty_below_three_days():
    limits = calculate_p90([DailyStats(date="2026-01-01"), DailyStats(date="2026-01-02")])
    assert limits.token_limit == 0
    assert limits.cost_limit == 0.0
    assert limits.message_limit == 0


def test_p90_picks_90th_percentile():
    stats = []
    for i in range(10):
        s = DailyStats(date=f"2026-01-{i + 1:02d}")
        s.total_tokens = (i + 1) * 100   # 100..1000
        s.cost_usd = (i + 1) * 1.0
        s.message_count = (i + 1) * 10
        stats.append(s)
    limits = calculate_p90(stats)
    assert limits.token_limit == 1000
    assert limits.cost_limit == 10.0
    assert limits.message_limit == 100
